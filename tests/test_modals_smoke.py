import unittest
from pysync_maria.tui.modals.mapping_modal import MappingModal
from pysync_maria.tui.modals.confirm_modal import ConfirmModal
from pysync_maria.tui.screens.table_select_screen import TableSelectScreen
from pysync_maria.db.metadata import ColumnInfo, TableInfo
from pydantic import SecretStr

class TestModalSmoke(unittest.TestCase):
    def test_mapping_modal_init(self):
        source_cols = [ColumnInfo("id", "int", False, None, "", 1, is_pk=True)]
        target_cols = [ColumnInfo("id", "int", False, None, "", 1, is_pk=True)]
        modal = MappingModal("test_table", source_cols, target_cols)
        self.assertEqual(modal.table_name, "test_table")
        self.assertTrue(modal.mapping["id"] == "id")

    def test_confirm_modal_init(self):
        tables = [TableInfo("t1", 100, 1024, "InnoDB", None)]
        modal = ConfirmModal(tables, "src", "tgt", "REPLACE", False, 1000)
        self.assertEqual(modal.mode, "REPLACE")

    def test_table_select_screen_init(self):
        screen = TableSelectScreen()
        self.assertEqual(screen.write_mode, "REPLACE")
        # BINDINGS is a list of tuples: (key, action, description)
        keys = [b[0] for b in screen.BINDINGS]
        self.assertIn("m", keys)

if __name__ == "__main__":
    unittest.main()
