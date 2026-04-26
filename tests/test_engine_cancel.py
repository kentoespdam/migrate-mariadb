import threading
import unittest
from unittest.mock import MagicMock

from pysync_maria.db.engine import WriteMode, migrate_table


class TestEngineCancel(unittest.TestCase):
    def test_migrate_table_cancellation(self):
        mock_source_cursor = MagicMock()
        # Provide enough rows to allow cancellation between batches
        mock_source_cursor.fetchmany.side_effect = [[(1, "A")], [(2, "B")], [(3, "C")], []]

        mock_source_conn = MagicMock()
        mock_source_conn.cursor.return_value = mock_source_cursor

        mock_target_conn = MagicMock()
        mock_target_cursor = MagicMock()
        mock_target_conn.cursor.return_value.__enter__.return_value = mock_target_cursor

        cancel_event = threading.Event()

        # Set cancel_event after the first batch is processed
        def on_batch(batch_res):
            if batch_res.batch_number == 1:
                cancel_event.set()

        res = migrate_table(
            src_conn=mock_source_conn,
            tgt_conn=mock_target_conn,
            table="t1",
            columns_a=["id", "name"],
            column_map={"id": "id", "name": "name"},
            mode=WriteMode.REPLACE,
            batch_size=1,
            on_batch_done=on_batch,
            cancel_event=cancel_event
        )

        self.assertTrue(res.cancelled)
        self.assertEqual(res.status, "failed")
        self.assertEqual(res.total_batches, 1) # Only one batch processed before cancel
        self.assertEqual(res.total_rows_written, 1)
        mock_target_conn.rollback.assert_called_once()
        self.assertIn("cancelled", res.errors[0].lower())

if __name__ == "__main__":
    unittest.main()
