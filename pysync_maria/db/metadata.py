from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Set
from functools import lru_cache
from .connection import get_connection

@dataclass(frozen=True)
class TableInfo:
    """Represents basic information about a table."""
    name: str
    row_count: int
    data_size_bytes: int
    engine: str
    create_time: Optional[datetime]

@dataclass(frozen=True)
class ColumnInfo:
    """Represents information about a column."""
    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str]
    extra: str
    ordinal_position: int

@dataclass(frozen=True)
class FKInfo:
    """Represents a Foreign Key relationship."""
    constraint_name: str
    table_name: str
    column_name: str
    referenced_table_name: str
    referenced_column_name: str

@dataclass
class SchemaDiff:
    """Represents the difference in schema between two tables."""
    table_name: str
    missing_in_target: List[str]
    missing_in_source: List[str]
    type_mismatches: List[Tuple[str, str, str]]  # (col_name, source_type, target_type)
    
    @property
    def is_compatible(self) -> bool:
        """
        Migration is compatible if all source columns exist in target.
        Target having extra columns is fine.
        """
        return len(self.missing_in_target) == 0

@lru_cache(maxsize=128)
def get_tables(conn, database: str) -> List[TableInfo]:
    """Fetch list of tables from information_schema.TABLES."""
    tables = []
    query = """
        SELECT 
            TABLE_NAME, 
            TABLE_ROWS, 
            DATA_LENGTH, 
            ENGINE, 
            CREATE_TIME 
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME ASC
    """
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute(query, (database,))
        for row in cursor.fetchall():
            tables.append(TableInfo(
                name=row['TABLE_NAME'],
                row_count=row['TABLE_ROWS'] or 0,
                data_size_bytes=row['DATA_LENGTH'] or 0,
                engine=row['ENGINE'] or 'Unknown',
                create_time=row['CREATE_TIME']
            ))
    return tables

@lru_cache(maxsize=512)
def get_columns(conn, database: str, table: str) -> List[ColumnInfo]:
    """Fetch list of columns from information_schema.COLUMNS."""
    columns = []
    query = """
        SELECT 
            COLUMN_NAME, 
            DATA_TYPE, 
            IS_NULLABLE, 
            COLUMN_DEFAULT, 
            EXTRA, 
            ORDINAL_POSITION 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION ASC
    """
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute(query, (database, table))
        for row in cursor.fetchall():
            columns.append(ColumnInfo(
                name=row['COLUMN_NAME'],
                data_type=row['DATA_TYPE'],
                is_nullable=row['IS_NULLABLE'] == 'YES',
                column_default=row['COLUMN_DEFAULT'],
                extra=row['EXTRA'],
                ordinal_position=row['ORDINAL_POSITION']
            ))
    return columns

@lru_cache(maxsize=128)
def get_foreign_keys(conn, database: str) -> List[FKInfo]:
    """Fetch foreign key relationships from information_schema.KEY_COLUMN_USAGE."""
    fks = []
    query = """
        SELECT 
            CONSTRAINT_NAME, 
            TABLE_NAME, 
            COLUMN_NAME, 
            REFERENCED_TABLE_NAME, 
            REFERENCED_COLUMN_NAME 
        FROM information_schema.KEY_COLUMN_USAGE 
        WHERE TABLE_SCHEMA = %s 
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute(query, (database,))
        for row in cursor.fetchall():
            fks.append(FKInfo(
                constraint_name=row['CONSTRAINT_NAME'],
                table_name=row['TABLE_NAME'],
                column_name=row['COLUMN_NAME'],
                referenced_table_name=row['REFERENCED_TABLE_NAME'],
                referenced_column_name=row['REFERENCED_COLUMN_NAME']
            ))
    return fks

def sort_tables_by_dependency(tables: List[TableInfo], fks: List[FKInfo]) -> List[TableInfo]:
    """
    Sort tables based on their dependencies (Foreign Keys).
    Uses topological sort to ensure parent tables come before child tables.
    """
    # Create adjacency list for dependencies (child -> parent)
    adj: Dict[str, Set[str]] = {t.name: set() for t in tables}
    for fk in fks:
        if fk.table_name in adj and fk.referenced_table_name in adj:
            if fk.table_name != fk.referenced_table_name: # Avoid self-dependency
                adj[fk.table_name].add(fk.referenced_table_name)

    # Topological sort
    visited = set()
    stack = []
    
    def visit(table_name: str):
        if table_name in visited:
            return
        visited.add(table_name)
        for parent in adj.get(table_name, []):
            visit(parent)
        stack.append(table_name)

    for t in tables:
        visit(t.name)

    # Reorder tables sequence based on stack
    table_map = {t.name: t for t in tables}
    return [table_map[name] for name in stack]

def diff_columns(cols_a: List[ColumnInfo], cols_b: List[ColumnInfo], table_name: str) -> SchemaDiff:
    """Compare columns between source (A) and target (B)."""
    dict_a = {c.name: c for c in cols_a}
    dict_b = {c.name: c for c in cols_b}
    
    set_a = set(dict_a.keys())
    set_b = set(dict_b.keys())
    
    missing_in_target = sorted(list(set_a - set_b))
    missing_in_source = sorted(list(set_b - set_a))
    
    type_mismatches = []
    common_cols = set_a & set_b
    for col in common_cols:
        if dict_a[col].data_type != dict_b[col].data_type:
            type_mismatches.append((col, dict_a[col].data_type, dict_b[col].data_type))
            
    return SchemaDiff(
        table_name=table_name,
        missing_in_target=missing_in_target,
        missing_in_source=missing_in_source,
        type_mismatches=type_mismatches
    )

def format_size(bytes_val: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            if unit == 'B':
                return f"{int(bytes_val)} {unit}"
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"
