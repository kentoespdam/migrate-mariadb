import unittest
from unittest.mock import MagicMock, patch

import mysql.connector

from pysync_maria.db.engine import WriteMode, migrate_table


class TestEngineFailure(unittest.TestCase):
    def setUp(self):
        self.mock_source_cursor = MagicMock()
        self.mock_source_cursor.fetchmany.side_effect = [[(1, "A")], [(2, "B")], []]

        self.mock_source_conn = MagicMock()
        self.mock_source_conn.cursor.return_value = self.mock_source_cursor

        self.mock_target_conn = MagicMock()
        self.mock_target_cursor = MagicMock()
        self.mock_target_conn.cursor.return_value.__enter__.return_value = self.mock_target_cursor

    def test_migrate_table_partial_failure(self):
        # First batch succeeds, second batch fails even after retries
        self.mock_target_cursor.executemany.side_effect = [
            None, # First batch success
            mysql.connector.OperationalError("Lost connection"), # Second batch fail
            mysql.connector.OperationalError("Lost connection"), # Second batch retry 1
            mysql.connector.OperationalError("Lost connection"), # Second batch retry 2
        ]

        # Patch time.sleep to speed up tests
        with patch("time.sleep"):
            res = migrate_table(
                src_conn=self.mock_source_conn,
                tgt_conn=self.mock_target_conn,
                table="t1",
                columns_a=["id", "name"],
                column_map={"id": "id", "name": "name"},
                mode=WriteMode.REPLACE,
                batch_size=1
            )

        self.assertEqual(res.status, "partial")
        self.assertEqual(res.total_batches, 2)
        self.assertEqual(res.failed_batches, 1)
        self.assertEqual(res.total_rows_read, 2)
        self.assertEqual(res.total_rows_written, 1)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("Batch 2", res.errors[0])

    def test_migrate_table_recovery_after_retry(self):
        # Second batch fails once but succeeds on retry
        self.mock_target_cursor.executemany.side_effect = [
            None, # First batch success
            mysql.connector.OperationalError("Lost connection"), # Second batch fail
            None # Second batch retry 1 success
        ]

        # Patch time.sleep to speed up tests
        with patch("time.sleep"):
            res = migrate_table(
                src_conn=self.mock_source_conn,
                tgt_conn=self.mock_target_conn,
                table="t1",
                columns_a=["id", "name"],
                column_map={"id": "id", "name": "name"},
                mode=WriteMode.REPLACE,
                batch_size=1
            )

        self.assertEqual(res.status, "success")
        self.assertEqual(res.failed_batches, 0)
        self.assertEqual(res.total_rows_written, 2)
        # Verify ping was called on retry
        self.mock_target_conn.ping.assert_called()

    def test_migrate_table_critical_error_rollback(self):
        # Error outside of batch retry (e.g. streaming error)
        self.mock_source_cursor.fetchmany.side_effect = Exception("Streaming failed")

        res = migrate_table(
            src_conn=self.mock_source_conn,
            tgt_conn=self.mock_target_conn,
            table="t1",
            columns_a=["id", "name"],
            column_map={"id": "id", "name": "name"},
            mode=WriteMode.REPLACE
        )

        self.assertEqual(res.status, "failed")
        self.mock_target_conn.rollback.assert_called_once()
        self.assertIn("Critical error", res.errors[0])

if __name__ == "__main__":
    unittest.main()
