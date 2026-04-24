package checkpoint

import "time"

// TableStatus represents the current state of a table migration.
type TableStatus string

const (
	StatusPending    TableStatus = "pending"
	StatusInProgress TableStatus = "in_progress"
	StatusCompleted  TableStatus = "completed"
	StatusFailed     TableStatus = "failed"
)

// TableState contains persistence data for a single table.
type TableState struct {
	Status       TableStatus `json:"status"`
	LastKey      []string    `json:"last_key"` // Current offset (PK values)
	RowsDone     int64       `json:"rows_done"`
	RowsTotalEst int64       `json:"rows_total_est"`
}

// State represents the global migration state for a run.
type State struct {
	RunID        string                `json:"run_id"`
	SourceDB     string                `json:"source_db"`
	TargetDB     string                `json:"target_db"`
	ConflictMode string                `json:"conflict_mode"`
	BatchSize    int                   `json:"batch_size"`
	StartedAt    time.Time             `json:"started_at"`
	UpdatedAt    time.Time             `json:"updated_at"`
	Tables       map[string]TableState `json:"tables"`
}

// Writer defines the interface for state persistence.
type Writer interface {
	Load() (*State, error)
	Save(s *State) error
	UpdateTable(name string, ts TableState) error
	Close() error
}
