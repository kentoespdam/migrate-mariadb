import unittest
import threading
import time
from unittest.mock import MagicMock
from pysync_maria.workers.pipeline import run_pipeline
from pysync_maria.db.engine import WriteMode

class TestPipeline(unittest.TestCase):
    def test_run_pipeline_happy_path(self):
        mock_src_cursor = MagicMock()
        mock_src_cursor.fetchmany.side_effect = [
            [(1, "A"), (2, "B")],
            [(3, "C")],
            []
        ]
        
        mock_tgt_conn = MagicMock()
        mock_tgt_cursor = MagicMock()
        mock_tgt_conn.cursor.return_value.__enter__.return_value = mock_tgt_cursor
        
        results = []
        def on_batch(res):
            results.append(res)
            
        read, written, batches, errors = run_pipeline(
            src_cursor=mock_src_cursor,
            tgt_conn=mock_tgt_conn,
            table="t1",
            source_cols=["id", "name"],
            target_cols=["id", "name"],
            mode=WriteMode.REPLACE,
            batch_size=2,
            dry_run=False,
            on_batch_done=on_batch
        )
        
        self.assertEqual(read, 3)
        self.assertEqual(written, 3)
        self.assertEqual(batches, 2)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].batch_number, 1)
        self.assertEqual(results[1].batch_number, 2)
        
    def test_run_pipeline_cancel(self):
        mock_src_cursor = MagicMock()
        # Provide many batches so we can cancel in middle
        mock_src_cursor.fetchmany.side_effect = [
            [(i, "Name") for i in range(j, j+2)] for j in range(0, 40, 2)
        ]
        
        mock_tgt_conn = MagicMock()
        mock_tgt_cursor = MagicMock()
        mock_tgt_conn.cursor.return_value.__enter__.return_value = mock_tgt_cursor
        
        cancel_event = threading.Event()
        
        results = []
        def on_batch(res):
            results.append(res)
            if len(results) == 1:
                cancel_event.set()
        
        read, written, batches, errors = run_pipeline(
            src_cursor=mock_src_cursor,
            tgt_conn=mock_tgt_conn,
            table="t1",
            source_cols=["id", "name"],
            target_cols=["id", "name"],
            mode=WriteMode.REPLACE,
            batch_size=2,
            dry_run=False,
            on_batch_done=on_batch,
            cancel_event=cancel_event
        )
        
        # Should have stopped after seeing cancel
        # Because of overlap, it might have processed 1 or 2 batches depending on timing,
        # but certainly not all 20 batches.
        self.assertTrue(len(results) < 5) 
        self.assertTrue(cancel_event.is_set())

    def test_run_pipeline_pause_resume(self):
        mock_src_cursor = MagicMock()
        mock_src_cursor.fetchmany.side_effect = [
            [(1, "A")],
            [(2, "B")],
            [(3, "C")],
            []
        ]
        
        mock_tgt_conn = MagicMock()
        mock_tgt_cursor = MagicMock()
        mock_tgt_conn.cursor.return_value.__enter__.return_value = mock_tgt_cursor
        
        pause_event = threading.Event()
        pause_event.set() # Start unpaused
        
        results = []
        def on_batch(res):
            results.append(res)
            if len(results) == 1:
                pause_event.clear() # Pause after first batch
        
        # Start in a separate thread because run_pipeline is blocking
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        
        future = executor.submit(
            run_pipeline,
            src_cursor=mock_src_cursor,
            tgt_conn=mock_tgt_conn,
            table="t1",
            source_cols=["id", "name"],
            target_cols=["id", "name"],
            mode=WriteMode.REPLACE,
            batch_size=1,
            dry_run=False,
            on_batch_done=on_batch,
            pause_event=pause_event,
            queue_size=1
        )
            
        # Wait a bit to ensure it's paused
        time.sleep(0.5)
        # With queue_size=1:
        # 1. Producer puts Batch 1 (Queue: [B1])
        # 2. Consumer gets Batch 1 (Queue: [])
        # 3. Producer puts Batch 2 (Queue: [B2])
        # 4. Consumer calls on_batch for B1 -> clears pause_event
        # 5. Producer tries Batch 3 -> waits at pause_event.wait()
        # 6. Consumer gets Batch 2 (Queue: []) -> calls on_batch for B2
        # 7. Consumer waits at q.get()
        self.assertEqual(len(results), 2)
        
        # Resume
        pause_event.set()
        read, written, batches, errors = future.result()
        executor.shutdown()
            
        self.assertEqual(len(results), 3)
        self.assertEqual(read, 3)

    def test_run_pipeline_producer_error(self):
        mock_src_cursor = MagicMock()
        mock_src_cursor.fetchmany.side_effect = Exception("Read failed")
        
        mock_tgt_conn = MagicMock()
        
        with self.assertRaisesRegex(Exception, "Read failed"):
            run_pipeline(
                src_cursor=mock_src_cursor,
                tgt_conn=mock_tgt_conn,
                table="t1",
                source_cols=["id", "name"],
                target_cols=["id", "name"],
                mode=WriteMode.REPLACE,
                batch_size=1,
                dry_run=False
            )
