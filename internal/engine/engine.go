package engine

import (
	"context"
	"fmt"
	"mariasyncgo/internal/checkpoint"
	"mariasyncgo/internal/worker"
)

// Migrate copies data from source table to target table in batches.
func (e *Engine) Migrate(ctx context.Context, job TableJob) (int64, error) {
	selectQuery := buildSelectQuery(job)

	var selectArgs []any
	if len(job.ResumePK) > 0 {
		for _, val := range job.ResumePK {
			selectArgs = append(selectArgs, val)
		}
	}

	rows, err := e.src.QueryContext(ctx, selectQuery, selectArgs...)
	if err != nil {
		return 0, fmt.Errorf("source query: %w", err)
	}
	defer rows.Close()

	colTypes, err := rows.ColumnTypes()
	if err != nil {
		return 0, fmt.Errorf("column types: %w", err)
	}

	numCols := len(colTypes)
	batch := make([]any, 0, job.BatchSize*numCols)
	var totalRows int64
	var lastPK []string

	for rows.Next() {
		select {
		case <-ctx.Done():
			return totalRows, ctx.Err()
		default:
		}

		scanDest := make([]any, numCols)
		rowValues := make([]any, numCols)
		for i := range scanDest {
			scanDest[i] = &rowValues[i]
		}

		if err := rows.Scan(scanDest...); err != nil {
			return totalRows, fmt.Errorf("row scan: %w", err)
		}

		// Keep track of logical key for checkpointing
		currentPK := make([]string, 0, len(job.Plan.LogicalKey))
		for _, keyName := range job.Plan.LogicalKey {
			for i, col := range job.Plan.Columns {
				if col.Source == keyName {
					val := rowValues[i]
					currentPK = append(currentPK, fmt.Sprintf("%v", val))
					break
				}
			}
		}
		lastPK = currentPK

		// Append to batch
		batch = append(batch, rowValues...)
		totalRows++

		if totalRows%int64(job.BatchSize) == 0 {
			if err := e.flushBatch(ctx, job, batch); err != nil {
				return totalRows - int64(job.BatchSize), err
			}
			batch = batch[:0]
			e.reportProgress(job.Plan.SourceTable, totalRows, false, nil)
			e.saveCheckpoint(job.Plan.SourceTable, totalRows, lastPK)
		}
	}

	if err := rows.Err(); err != nil {
		return totalRows, fmt.Errorf("rows error: %w", err)
	}

	// Flush remaining
	if len(batch) > 0 {
		count := len(batch) / numCols
		if err := e.flushBatch(ctx, job, batch); err != nil {
			return totalRows - int64(count), err
		}
	}

	e.reportProgress(job.Plan.SourceTable, totalRows, true, nil)
	e.saveCheckpoint(job.Plan.SourceTable, totalRows, lastPK)

	return totalRows, nil
}

func (e *Engine) flushBatch(ctx context.Context, job TableJob, args []any) error {
	rowCount := len(args) / len(job.Plan.Columns)
	if rowCount == 0 {
		return nil
	}

	query := buildInsertQuery(job, rowCount)

	tx, err := e.tgt.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(ctx, query, args...); err != nil {
		return fmt.Errorf("exec batch: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}

	return nil
}

func (e *Engine) reportProgress(table string, processed int64, done bool, err error) {
	if e.progress == nil {
		return
	}
	// Total estimation could be passed in job if available, for now 0
	event := worker.ProgressEvent{
		Table:     table,
		Processed: processed,
		Done:      done,
		Err:       err,
	}

	select {
	case e.progress <- event:
	default:
		// non-blocking progress report
	}
}

func (e *Engine) saveCheckpoint(table string, processed int64, lastPK []string) {
	if e.checkpt == nil {
		return
	}
	_ = e.checkpt.UpdateTable(table, checkpoint.TableState{
		Status:   "in_progress",
		LastKey:  lastPK,
		RowsDone: processed,
	})
}
