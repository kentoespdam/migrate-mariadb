package checkpoint

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type checkpointWriter struct {
	path  string
	state *State
	mu    sync.RWMutex

	// Throttling fields
	lastWrite   time.Time
	batchCount  int
	maxBatches  int
	maxInterval time.Duration
}

// NewWriter returns a new checkpoint writer with default throttling (10 batches or 5 seconds).
func NewWriter(path string) Writer {
	return &checkpointWriter{
		path:        path,
		maxBatches:  10,
		maxInterval: 5 * time.Second,
		lastWrite:   time.Now(),
	}
}

func (w *checkpointWriter) Load() (*State, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	data, err := os.ReadFile(w.path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil // Fresh run
		}
		return nil, fmt.Errorf("failed to read checkpoint: %w", err)
	}

	var state State
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("failed to unmarshal checkpoint: %w", err)
	}

	w.state = &state
	return &state, nil
}

func (w *checkpointWriter) Save(s *State) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	w.state = s
	return w.saveAtomic()
}

func (w *checkpointWriter) UpdateTable(name string, ts TableState) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.state == nil {
		return fmt.Errorf("no state loaded or saved yet")
	}

	if w.state.Tables == nil {
		w.state.Tables = make(map[string]TableState)
	}

	w.state.Tables[name] = ts
	w.state.UpdatedAt = time.Now()
	w.batchCount++

	// Check if we should flush to disk
	shouldFlush := w.batchCount >= w.maxBatches ||
		time.Since(w.lastWrite) >= w.maxInterval ||
		ts.Status == StatusCompleted ||
		ts.Status == StatusFailed

	if shouldFlush {
		return w.saveAtomic()
	}

	return nil
}

func (w *checkpointWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	// Final save before closing
	if w.state != nil {
		return w.saveAtomic()
	}
	return nil
}

// saveAtomic implements the write-rename pattern to ensure atomic updates.
func (w *checkpointWriter) saveAtomic() error {
	if w.state == nil {
		return nil
	}

	data, err := json.MarshalIndent(w.state, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal state: %w", err)
	}

	// 1. Write to .tmp file
	tmpPath := w.path + ".tmp"

	// Create directory if it doesn't exist
	dir := filepath.Dir(w.path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	f, err := os.OpenFile(tmpPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	if err != nil {
		return fmt.Errorf("failed to open tmp file: %w", err)
	}

	_, err = f.Write(data)
	if err != nil {
		f.Close()
		return fmt.Errorf("failed to write data: %w", err)
	}

	// 2. Fsync to ensure it's on disk
	if err := f.Sync(); err != nil {
		f.Close()
		return fmt.Errorf("failed to sync file: %w", err)
	}
	f.Close()

	// 3. Atomic rename
	if err := os.Rename(tmpPath, w.path); err != nil {
		return fmt.Errorf("failed to rename checkpoint: %w", err)
	}

	w.lastWrite = time.Now()
	w.batchCount = 0
	return nil
}
