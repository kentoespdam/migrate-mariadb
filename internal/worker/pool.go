package worker

import (
	"context"
	"fmt"
	"sync"
)

// MigrateFunc defines the function type for performing a migration job.
// It returns the number of processed rows and an error if any.
type MigrateFunc[J any] func(context.Context, J) (int64, error)

// TableNameFunc extracts the table name from a job.
type TableNameFunc[J any] func(J) string

// Pool orchestrates parallel execution of migration jobs.
type Pool[J any] struct {
	size         int
	migrate      MigrateFunc[J]
	extractTable TableNameFunc[J]
}

// NewPool creates a new worker pool.
func NewPool[J any](size int, migrate MigrateFunc[J], extractTable TableNameFunc[J]) *Pool[J] {
	return &Pool[J]{
		size:         size,
		migrate:      migrate,
		extractTable: extractTable,
	}
}

// Run executes the given jobs in parallel workers.
// It returns a read-only channel of ProgressEvents.
func (p *Pool[J]) Run(ctx context.Context, jobs []J) (<-chan ProgressEvent, error) {
	// Progress channel is buffered to prevent blocking workers.
	// Capacity: size * 10 (fallback rule: drop event if full).
	progress := make(chan ProgressEvent, p.size*10)

	// Job channel is fully buffered for the job list.
	jobCh := make(chan J, len(jobs))
	for _, j := range jobs {
		jobCh <- j
	}
	close(jobCh)

	var wg sync.WaitGroup

	// Spawn workers
	for i := 0; i < p.size; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()

			// Panic recovery to keep the pool alive and report failure.
			defer func() {
				if r := recover(); r != nil {
					err := fmt.Errorf("worker %d panicked: %v", workerID, r)
					// Try to report the panic as an error, if possible (context check applies).
					select {
					case progress <- ProgressEvent{Err: err, Done: true}:
					default:
					}
				}
			}()

			for job := range jobCh {
				select {
				case <-ctx.Done():
					return
				default:
				}

				tableName := p.extractTable(job)
				processed, err := p.migrate(ctx, job)

				event := ProgressEvent{
					Table:     tableName,
					Processed: processed,
					Done:      true,
					Err:       err,
				}

				// Emit final status for the table.
				// Non-blocking select to ensure one worker doesn't stall if TUI is busy.
				select {
				case progress <- event:
				case <-ctx.Done():
					return
				default:
					// If channel is full, we log to stdout or drop?
					// Blueprint says: drop event (progress lag ok).
				}
			}
		}(i)
	}

	// Wait and Close monitor
	go func() {
		wg.Wait()
		close(progress)
	}()

	return progress, nil
}
