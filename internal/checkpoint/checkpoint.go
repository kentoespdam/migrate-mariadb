package checkpoint

import "time"

// TableState represents the persistent state of a table migration.
type TableState struct {
	Status       string   // pending / in_progress / completed / failed
	LastKey      []string // nil for pending
	RowsDone     int64
	RowsTotalEst int64
}

// State represents the overall migration session state.
type State struct {
	RunID        string
	SourceDB     string
	TargetDB     string
	ConflictMode string
	BatchSize    int
	StartedAt    time.Time
	UpdatedAt    time.Time
	Tables       map[string]TableState
}

// Writer is the interface for persisting checkpoint state.
type Writer interface {
	Save(s *State) error
	UpdateTable(name string, ts TableState) error
}
