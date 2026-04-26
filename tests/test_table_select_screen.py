import unittest
from unittest.mock import MagicMock

from textual.widgets import Button, DataTable, Label

from pysync_maria.db.metadata import TableInfo
from pysync_maria.tui.screens.table_select_screen import TableSelectScreen


class TestTableSelectScreen(unittest.TestCase):
    def setUp(self):
        self.screen = TableSelectScreen()
        self.screen.tables_data = [
            TableInfo(name="table1", row_count=100, data_size_bytes=1024, engine="InnoDB", create_time=None),
            TableInfo(name="table2", row_count=200, data_size_bytes=2048, engine="InnoDB", create_time=None),
        ]
        self.screen.schema_status = {"table1": "✅ Match", "table2": "✅ Match"}

    def test_update_stats(self):
        mock_label = MagicMock(spec=Label)
        mock_button = MagicMock(spec=Button)

        def mock_query_one(selector, type):
            if selector == "#stats-label":
                return mock_label
            if selector == "#start-btn":
                return mock_button
            return MagicMock()

        self.screen.query_one = mock_query_one

        # 0 selected
        self.screen.selected_tables = set()
        self.screen.update_stats()
        mock_label.update.assert_called_with("Selected: 0 tables | Est. rows: 0")
        self.assertTrue(mock_button.disabled)

        # 1 selected
        self.screen.selected_tables = {"table1"}
        self.screen.update_stats()
        mock_label.update.assert_called_with("Selected: 1 tables | Est. rows: 100")
        self.assertFalse(mock_button.disabled)

    def test_apply_filter(self):
        mock_table = MagicMock(spec=DataTable)
        mock_table.add_row = MagicMock()

        def mock_query_one(selector, type):
            if selector == "#table-list":
                return mock_table
            return MagicMock()

        self.screen.query_one = mock_query_one
        self.screen.update_stats = MagicMock()

        # No filter
        self.screen.apply_filter("")
        self.assertEqual(mock_table.add_row.call_count, 2)
        mock_table.clear.assert_called()

        # Filter for "table1"
        mock_table.add_row.reset_mock()
        self.screen.apply_filter("table1")
        self.assertEqual(mock_table.add_row.call_count, 1)
        args, _ = mock_table.add_row.call_args
        self.assertEqual(args[1], "table1")
        self.assertEqual(args[4], "✅ Match")

if __name__ == "__main__":
    unittest.main()
