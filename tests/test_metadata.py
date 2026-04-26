import unittest
from unittest.mock import MagicMock
from pysync_maria.db.metadata import (
    TableInfo, ColumnInfo, FKInfo, 
    sort_tables_by_dependency, diff_columns, format_size
)

class TestMetadata(unittest.TestCase):
    def test_format_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(512), "512.0 B")
        self.assertEqual(format_size(1024 * 1.5), "1.5 KB")
        self.assertEqual(format_size(1024 * 1024 * 2.5), "2.5 MB")

    def test_diff_columns_compatibility(self):
        cols_a = [ColumnInfo("id", "int", False, None, "", 1)]
        cols_b = [ColumnInfo("id", "int", False, None, "", 1)]
        diff = diff_columns(cols_a, cols_b, "test_table")
        self.assertTrue(diff.is_compatible)
        self.assertEqual(len(diff.missing_in_target), 0)

    def test_diff_columns_missing_target(self):
        cols_a = [ColumnInfo("id", "int", False, None, "", 1), ColumnInfo("email", "varchar", False, None, "", 2)]
        cols_b = [ColumnInfo("id", "int", False, None, "", 1)]
        diff = diff_columns(cols_a, cols_b, "test_table")
        self.assertFalse(diff.is_compatible)
        self.assertIn("email", diff.missing_in_target)

    def test_diff_columns(self):
        cols_a = [
            ColumnInfo("id", "int", False, None, "auto_increment", 1),
            ColumnInfo("name", "varchar", True, None, "", 2),
        ]
        cols_b = [
            ColumnInfo("id", "int", False, None, "auto_increment", 1),
            ColumnInfo("name", "text", True, None, "", 2), # Type mismatch
            ColumnInfo("extra", "varchar", True, None, "", 3), # Missing in source
        ]
        
        diff = diff_columns(cols_a, cols_b, "test_table")
        
        self.assertEqual(diff.table_name, "test_table")
        self.assertEqual(diff.missing_in_target, [])
        self.assertEqual(diff.missing_in_source, ["extra"])
        self.assertEqual(diff.type_mismatches, [("name", "varchar", "text")])
        self.assertTrue(diff.is_compatible)

        # Test incompatible
        cols_c = [ColumnInfo("id", "int", False, None, "", 1)]
        diff_incompat = diff_columns(cols_a, cols_c, "test_table")
        self.assertFalse(diff_incompat.is_compatible)
        self.assertIn("name", diff_incompat.missing_in_target)

    def test_sort_tables_by_dependency(self):
        # Tables: A, B, C
        # B depends on A (B -> A)
        # C depends on B (C -> B)
        # Expected order: A, B, C
        
        tables = [
            TableInfo("C", 0, 0, "InnoDB", None),
            TableInfo("A", 0, 0, "InnoDB", None),
            TableInfo("B", 0, 0, "InnoDB", None),
        ]
        
        fks = [
            FKInfo("fk_ba", "B", "a_id", "A", "id"),
            FKInfo("fk_cb", "C", "b_id", "B", "id"),
        ]
        
        sorted_tables = sort_tables_by_dependency(tables, fks)
        
        names = [t.name for t in sorted_tables]
        self.assertEqual(names, ["A", "B", "C"])

    def test_circular_dependency(self):
        # A <-> B helper should not hang
        tables = [
            TableInfo("A", 0, 0, "InnoDB", None),
            TableInfo("B", 0, 0, "InnoDB", None),
        ]
        fks = [
            FKInfo("fk_ab", "A", "b_id", "B", "id"),
            FKInfo("fk_ba", "B", "a_id", "A", "id"),
        ]
        
        sorted_tables = sort_tables_by_dependency(tables, fks)
        self.assertEqual(len(sorted_tables), 2)
        # In circular, any order is "best effort" but shouldn't crash

if __name__ == "__main__":
    unittest.main()
