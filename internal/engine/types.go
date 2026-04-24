package engine

import (
	"database/sql"
	"mariasyncgo/internal/checkpoint"
	"mariasyncgo/internal/mapping"
	"mariasyncgo/internal/worker"
)

// ConflictMode defines how to handle duplicate keys in the target database.
type ConflictMode int

const (
	ModeSkip      ConflictMode = iota // INSERT IGNORE
	ModeUpdate                        // INSERT ... ON DUPLICATE KEY UPDATE
	ModeOverwrite                     // REPLACE INTO
)

// TableJob contains the configuration for migrating a single table.
type TableJob struct {
	Plan      mapping.TablePlan
	BatchSize int
	Mode      ConflictMode
	ResumePK  []string // slice of PK values from checkpoint
}

// Engine handles the data movement between source and target databases.
type Engine struct {
	src, tgt *sql.DB
	progress chan<- worker.ProgressEvent
	checkpt  checkpoint.Writer
}

// NewEngine creates a new migration engine.
func NewEngine(src, tgt *sql.DB, progress chan<- worker.ProgressEvent, checkpt checkpoint.Writer) *Engine {
	return &Engine{
		src:      src,
		tgt:      tgt,
		progress: progress,
		checkpt:  checkpt,
	}
}
