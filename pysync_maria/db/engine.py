import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Generator, Tuple, Dict, Callable, Any
import mysql.connector
from .connection import ConnectionError

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
    error: Optional[str] = None
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
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

def stream_table(
    cursor: Any, 
    table: str, 
    columns: List[str], 
    batch_size: int = 5000,
    where_clause: Optional[str] = None
) -> Generator[List[Tuple], None, None]:
    """
    Producer: Stream data from Host A using SSCursor.
    Expects cursor to be an unbuffered cursor (SSCursor).
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

def build_write_query(table: str, columns: List[str], mode: WriteMode) -> str:
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
    rows: List[Tuple],
    columns: List[str],
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

def migrate_table(
    conn_a: Any,
    conn_b: Any,
    table: str,
    columns_a: List[str],
    column_map: Dict[str, Optional[str]],
    mode: WriteMode = WriteMode.REPLACE,
    batch_size: int = 5000,
    dry_run: bool = False,
    on_batch_done: Optional[Callable[[BatchResult], None]] = None
) -> MigrationResult:
    """Orchestrator: Migrate one table from source to target."""
    start_time = time.time()
    res = MigrationResult(table_name=table)
    
    # Resolve target columns
    target_cols = [column_map[c] for c in columns_a if column_map.get(c)]
    source_cols = [c for c in columns_a if column_map.get(c)]
    
    # Use the unbuffered streaming connection/cursor passed in conn_a
    # We assume conn_a is (connection, cursor) tuple from get_streaming_connection
    source_conn, source_cursor = conn_a
    target_conn = conn_b
    
    batch_num = 0
    try:
        for batch_rows in stream_table(source_cursor, table, source_cols, batch_size):
            batch_num += 1
            batch_start = time.time()
            batch_err = None
            rows_written = 0
            
            max_retries = 3
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    with target_conn.cursor() as target_cursor:
                        rows_written = write_batch(target_cursor, table, batch_rows, target_cols, mode, dry_run)
                        if not dry_run:
                            target_conn.commit()
                        break # Success
                except (mysql.connector.OperationalError, mysql.connector.InterfaceError) as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        batch_err = f"Failed after {max_retries} retries: {str(e)}"
                        break
                    wait_time = 2 ** retry_count
                    logger.warning(f"Connection error in batch {batch_num}, retrying in {wait_time}s... ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                    # Re-ping connections
                    try:
                        target_conn.ping(reconnect=True)
                    except:
                        pass
                except mysql.connector.Error as e:
                    if not dry_run:
                        target_conn.rollback()
                    batch_err = str(e)
                    break
            
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

        if res.failed_batches == 0:
            res.status = "success"
        elif res.failed_batches < res.total_batches:
            res.status = "partial"
        else:
            res.status = "failed"

    except Exception as e:
        res.status = "failed"
        res.errors.append(f"Critical error: {str(e)}")
        logger.critical(f"Critical error migrating {table}: {e}")
    
    res.elapsed_seconds = time.time() - start_time
    return res
