import logging
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import mysql.connector

from ._retry import retry_with_backoff

# Configure logger
logger = logging.getLogger("pysync_maria.engine")

class WriteMode(Enum):
    REPLACE = "REPLACE"
    UPDATE = "UPDATE"  # ON DUPLICATE KEY UPDATE
    IGNORE = "IGNORE"   # INSERT IGNORE

@dataclass
class BatchResult:
    table_name: str
    batch_number: int
    rows_read: int
    rows_written: int
    elapsed_seconds: float
    error: str | None = None
    dry_run: bool = False

@dataclass
class MigrationResult:
    table_name: str
    total_rows_read: int = 0
    total_rows_written: int = 0
    total_batches: int = 0
    failed_batches: int = 0
    elapsed_seconds: float = 0.0
    status: str = "success" # success, partial, failed
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
    cancelled: bool = False

def stream_table(
    cursor: Any,
    table: str,
    columns: list[str],
    batch_size: int = 5000,
    where_clause: str | None = None
) -> Generator[list[tuple], None, None]:
    """
    Producer: Stream data from Host A using buffered=False cursor.
    Expects cursor to be an unbuffered cursor.
    """
    cols_str = ", ".join([f"`{c}`" for c in columns])
    query = f"SELECT {cols_str} FROM `{table}`"
    if where_clause:
        query += f" WHERE {where_clause}"

    cursor.execute(query)

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows

def build_write_query(table: str, columns: list[str], mode: WriteMode) -> str:
    """Build the SQL query based on the selected write mode."""
    cols_str = ", ".join([f"`{c}`" for c in columns])
    placeholders = ", ".join(["%s"] * len(columns))

    if mode == WriteMode.REPLACE:
        return f"REPLACE INTO `{table}` ({cols_str}) VALUES ({placeholders})"

    if mode == WriteMode.IGNORE:
        return f"INSERT IGNORE INTO `{table}` ({cols_str}) VALUES ({placeholders})"

    if mode == WriteMode.UPDATE:
        update_part = ", ".join([f"`{c}` = VALUES(`{c}`)" for c in columns])
        return f"INSERT INTO `{table}` ({cols_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_part}"

    raise ValueError(f"Unsupported write mode: {mode}")

def write_batch(
    cursor: Any,
    table: str,
    rows: list[tuple],
    columns: list[str],
    mode: WriteMode,
    dry_run: bool = False
) -> int:
    """Consumer: Write a batch of rows to Host B."""
    if not rows:
        return 0

    query = build_write_query(table, columns, mode)

    if dry_run:
        logger.debug(f"[DRY RUN] Would execute: {query} with {len(rows)} rows")
        return 0

    cursor.executemany(query, rows)
    return len(rows)

def count_rows(conn: Any, table: str, where_clause: str | None = None) -> int:
    """Exact row count. Use sparingly; cheaper than re-streaming."""
    sql = f"SELECT COUNT(*) FROM `{table}`"
    if where_clause:
        sql += f" WHERE {where_clause}"
    with conn.cursor() as cur:
        cur.execute(sql)
        (n,) = cur.fetchone()
    return int(n)


def migrate_table(
    src_conn: Any,
    tgt_conn: Any,
    table: str,
    columns_a: list[str],
    column_map: dict[str, str | None],
    mode: WriteMode = WriteMode.REPLACE,
    batch_size: int = 5000,
    dry_run: bool = False,
    on_batch_done: Callable[[BatchResult], None] | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None
) -> MigrationResult:
    """Orchestrator: Migrate one table from source to target."""
    start_time = time.time()
    res = MigrationResult(table_name=table, dry_run=dry_run)

    # Pre-flight validation: Check for unmapped columns
    unmapped = [c for c in columns_a if not column_map.get(c)]
    if unmapped:
        msg = f"Unmapped source columns dropped for {table}: {unmapped}"
        logger.warning(msg)
        res.warnings.append(msg)

    # Resolve target columns
    target_cols = [column_map[c] for c in columns_a if column_map.get(c)]
    source_cols = [c for c in columns_a if column_map.get(c)]

    # E1: SSCursor ownership - the engine now manages the unbuffered cursor lifecycle
    # We use buffered=False for streaming large datasets (Equivalent to SSCursor in other libs)
    src_cursor = src_conn.cursor(buffered=False)

    batch_num = 0
    try:
        for batch_rows in stream_table(src_cursor, table, source_cols, batch_size):
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                res.cancelled = True
                res.status = "failed"
                res.errors.append("Migration cancelled by user")
                if not dry_run:
                    tgt_conn.rollback()
                break

            if pause_event:
                pause_event.wait()

            batch_num += 1
            batch_start = time.time()
            batch_err = None
            rows_written = 0

            def attempt_batch(rows=batch_rows):
                nonlocal rows_written
                with tgt_conn.cursor() as target_cursor:
                    rows_written = write_batch(
                        target_cursor, table, rows, target_cols, mode, dry_run
                    )
                    if not dry_run:
                        tgt_conn.commit()

            def on_retry(count, err, b_num=batch_num):
                logger.warning(
                    f"Retry {count} for batch {b_num} of {table} after error: {err}"
                )
                try:
                    tgt_conn.ping(reconnect=True)
                except mysql.connector.Error as ping_err:
                    logger.warning(f"Reconnect failed in batch {b_num}: {ping_err}")

            try:
                retry_with_backoff(attempt_batch, on_retry=on_retry)
            except Exception as e:
                batch_err = str(e)
                res.failed_batches += 1
                res.errors.append(f"Batch {batch_num}: {batch_err}")

            res.total_rows_read += len(batch_rows)
            res.total_rows_written += rows_written
            res.total_batches += 1

            batch_res = BatchResult(
                table_name=table,
                batch_number=batch_num,
                rows_read=len(batch_rows),
                rows_written=rows_written,
                elapsed_seconds=time.time() - batch_start,
                error=batch_err,
                dry_run=dry_run
            )

            if on_batch_done:
                on_batch_done(batch_res)

        if not res.cancelled:
            if res.failed_batches == 0:
                res.status = "success"
            elif res.failed_batches < res.total_batches:
                res.status = "partial"
            else:
                res.status = "failed"

    except Exception as e:
        res.status = "failed"
        res.errors.append(f"Critical error: {e!s}")
        from ..logging_setup import log_exception
        log_exception(
            logger,
            f"Critical error migrating {table}",
            e,
            table=table,
            batch_num=batch_num
        )
        try:
            if not dry_run:
                tgt_conn.rollback()
        except mysql.connector.Error as rb_err:
            logger.error(f"Rollback failed for {table}: {rb_err}")
    finally:
        if src_cursor:
            import contextlib
            with contextlib.suppress(Exception):
                src_cursor.close()

    res.elapsed_seconds = time.time() - start_time
    return res
