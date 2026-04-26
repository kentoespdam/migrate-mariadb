import unittest
from unittest.mock import MagicMock

from pysync_maria.db.engine import (
    WriteMode,
    build_write_query,
    migrate_table,
    stream_table,
    write_batch,
)


class TestEngine(unittest.TestCase):
    def test_build_write_query(self):
        cols = ["id", "name"]

        q_replace = build_write_query("t1", cols, WriteMode.REPLACE)
        self.assertEqual(q_replace, "REPLACE INTO `t1` (`id`, `name`) VALUES (%s, %s)")

        q_ignore = build_write_query("t1", cols, WriteMode.IGNORE)
        self.assertEqual(q_ignore, "INSERT IGNORE INTO `t1` (`id`, `name`) VALUES (%s, %s)")

        q_update = build_write_query("t1", cols, WriteMode.UPDATE)
        self.assertIn("ON DUPLICATE KEY UPDATE", q_update)
        self.assertIn("`name` = VALUES(`name`)", q_update)

    def test_stream_table(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [
            [(1, "A"), (2, "B")],
            [(3, "C")],
            []
        ]

        batches = list(stream_table(mock_cursor, "t1", ["id", "name"], batch_size=2))

        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 2)
        self.assertEqual(len(batches[1]), 1)
        self.assertEqual(mock_cursor.fetchmany.call_count, 3)

    def test_write_batch_dry_run(self):
        mock_cursor = MagicMock()
        rows = [(1, "A"), (2, "B")]

        written = write_batch(mock_cursor, "t1", rows, ["id", "name"], WriteMode.REPLACE, dry_run=True)

        self.assertEqual(written, 0)
        mock_cursor.executemany.assert_not_called()

    def test_migrate_table_success(self):
        mock_source_cursor = MagicMock()
        mock_source_cursor.fetchmany.side_effect = [[(1, "A")], []]

        mock_source_conn = MagicMock()
        mock_source_conn.cursor.return_value = mock_source_cursor

        mock_target_conn = MagicMock()
        mock_target_cursor = MagicMock()
        mock_target_conn.cursor.return_value.__enter__.return_value = mock_target_cursor

        results = []
        def on_batch(res):
            results.append(res)

        res = migrate_table(
            src_conn=mock_source_conn,
            tgt_conn=mock_target_conn,
            table="t1",
            columns_a=["id", "name"],
            column_map={"id": "id", "name": "name_v2"},
            mode=WriteMode.REPLACE,
            on_batch_done=on_batch
        )

        self.assertEqual(res.status, "success")
        self.assertEqual(res.total_rows_read, 1)
        self.assertEqual(len(results), 1)
        mock_target_cursor.executemany.assert_called_once()
        mock_target_conn.commit.assert_called_once()
        mock_source_conn.cursor.assert_called_with(buffered=False)

if __name__ == "__main__":
    unittest.main()
