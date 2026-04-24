package discovery

import (
	"context"
	"database/sql"
	"fmt"
)

// Discover fetches database metadata from the specified host.
func Discover(ctx context.Context, db *sql.DB, database string) (*SchemaSnapshot, error) {
	snapshot := &SchemaSnapshot{
		Database: database,
		Tables:   make(map[string]Table),
	}

	// 0. Fetch server capability: max_allowed_packet
	err := db.QueryRowContext(ctx, "SELECT @@max_allowed_packet").Scan(&snapshot.MaxAllowedPacket)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch max_allowed_packet: %w", err)
	}

	// 1. Fetch table metadata
	tablesQuery := `
		SELECT TABLE_NAME, TABLE_ROWS,
		       ROUND((DATA_LENGTH + INDEX_LENGTH)/1024/1024, 2) AS size_mb
		FROM   information_schema.TABLES
		WHERE  TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE'
		ORDER  BY TABLE_NAME;
	`
	rows, err := db.QueryContext(ctx, tablesQuery, database)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch tables: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var t Table
		if err := rows.Scan(&t.Name, &t.RowCount, &t.SizeMB); err != nil {
			return nil, fmt.Errorf("failed to scan table row: %w", err)
		}
		snapshot.Tables[t.Name] = t
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows error during table fetch: %w", err)
	}

	// 2. Fetch column metadata for all tables in one go
	columnsQuery := `
		SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
		       IS_NULLABLE, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH
		FROM   information_schema.COLUMNS
		WHERE  TABLE_SCHEMA = ?
		ORDER  BY TABLE_NAME, ORDINAL_POSITION;
	`
	cols, err := db.QueryContext(ctx, columnsQuery, database)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch columns: %w", err)
	}
	defer cols.Close()

	for cols.Next() {
		var tableName string
		var col Column
		var isNullable string
		var columnKey string
		var charMaxLen sql.NullInt64

		err := cols.Scan(
			&tableName,
			&col.Name,
			&col.DataType,
			&isNullable,
			&columnKey,
			&charMaxLen,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan column row: %w", err)
		}

		col.Nullable = (isNullable == "YES")
		col.IsPrimary = (columnKey == "PRI")
		col.IsUnique = (columnKey == "UNI")
		if charMaxLen.Valid {
			val := int(charMaxLen.Int64)
			col.CharMaxLen = &val
		}

		// Group columns into their respective tables
		if table, ok := snapshot.Tables[tableName]; ok {
			table.Columns = append(table.Columns, col)
			snapshot.Tables[tableName] = table
		}
	}
	if err := cols.Err(); err != nil {
		return nil, fmt.Errorf("rows error during column fetch: %w", err)
	}

	return snapshot, nil
}
