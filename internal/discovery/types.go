package discovery

// Column represents metadata for a table column.
type Column struct {
	Name       string
	DataType   string // VARCHAR, INT, TEXT, DATETIME, ...
	Nullable   bool
	IsPrimary  bool
	IsUnique   bool
	CharMaxLen *int // nil for non-string
}

// Table represents metadata for a database table.
type Table struct {
	Name     string
	RowCount int64   // from TABLE_ROWS (estimate)
	SizeMB   float64 // DATA_LENGTH + INDEX_LENGTH
	Columns  []Column
}

// SchemaSnapshot contains the metadata discovered for a database.
type SchemaSnapshot struct {
	Database         string
	MaxAllowedPacket int64            // session variable max_allowed_packet
	Tables           map[string]Table // key = table name
}
