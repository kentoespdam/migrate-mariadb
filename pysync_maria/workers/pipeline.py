import logging
import queue
import threading
import time
from typing import Any, Callable

import mysql.connector

from ..db._retry import retry_with_backoff
from ..db.engine import BatchResult, WriteMode, stream_table, write_batch

logger = logging.getLogger("pysync_maria.pipeline")

SENTINEL = object()

def run_pipeline(
    src_cursor: Any,
    tgt_conn: Any,
    table: str,
    source_cols: list[str],
    target_cols: list[str],
    mode: WriteMode,
    batch_size: int,
    dry_run: bool,
    on_batch_done: Callable[[BatchResult], None] | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    queue_size: int = 2,
) -> tuple[int, int, int, list[str]]:
    """
    Producer-Consumer pipeline for migrating data.
    Returns (total_rows_read, total_rows_written, total_batches, errors)
    """
    q: queue.Queue = queue.Queue(maxsize=queue_size)
    producer_exc: Exception | None = None
    internal_stop = threading.Event()
    
    total_rows_read = 0
    total_rows_written = 0
    total_batches = 0
    errors = []

    def is_cancelled():
        return (cancel_event and cancel_event.is_set()) or internal_stop.is_set()

    def producer():
        nonlocal producer_exc
        try:
            for batch_rows in stream_table(src_cursor, table, source_cols, batch_size):
                if is_cancelled():
                    break
                
                if pause_event:
                    # Interruptible wait for pause_event
                    while not pause_event.wait(timeout=0.1):
                        if is_cancelled():
                            break
                    if is_cancelled():
                        break

                # Use timeout for put to allow checking cancellation if queue is full
                pushed = False
                while not pushed and not is_cancelled():
                    try:
                        q.put(batch_rows, timeout=0.1)
                        pushed = True
                    except queue.Full:
                        continue
                
                if is_cancelled():
                    break
                    
        except Exception as e:
            producer_exc = e
            logger.error(f"Producer error for {table}: {e}")
        finally:
            # Always put SENTINEL to unblock consumer unless we're sure it's already gone
            try:
                q.put(SENTINEL, timeout=0.5)
            except queue.Full:
                pass

    prod_thread = threading.Thread(target=producer, name=f"prod-{table}", daemon=True)
    prod_thread.start()

    batch_num = 0
    try:
        while True:
            try:
                # Use short timeout to allow checking cancellation
                item = q.get(timeout=0.1)
            except queue.Empty:
                if is_cancelled():
                    break
                if not prod_thread.is_alive() and q.empty():
                    # Safeguard: if producer died without sentinel
                    break
                continue

            if item is SENTINEL:
                break
            
            if is_cancelled():
                break

            batch_rows = item
            total_rows_read += len(batch_rows)
            batch_num += 1
            batch_start = time.time()
            batch_err = None
            rows_written_in_batch = 0

            def attempt_batch(rows=batch_rows):
                nonlocal rows_written_in_batch
                with tgt_conn.cursor() as target_cursor:
                    rows_written_in_batch = write_batch(
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
                errors.append(f"Batch {batch_num}: {batch_err}")
            
            total_rows_written += rows_written_in_batch
            total_batches += 1

            batch_res = BatchResult(
                table_name=table,
                batch_number=batch_num,
                rows_read=len(batch_rows),
                rows_written=rows_written_in_batch,
                elapsed_seconds=time.time() - batch_start,
                error=batch_err,
                dry_run=dry_run
            )

            if on_batch_done:
                on_batch_done(batch_res)

    finally:
        # Signal cancellation to producer
        internal_stop.set()
        
        # Drain queue to unblock producer if it's stuck at q.put
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
                
        prod_thread.join(timeout=2.0)
        if prod_thread.is_alive():
            logger.warning(f"Producer thread for {table} did not terminate gracefully")

    if producer_exc:
        raise producer_exc

    return total_rows_read, total_rows_written, total_batches, errors
