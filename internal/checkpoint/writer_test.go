package checkpoint

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestWriter_AtomicSave(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "checkpoint_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	checkpointPath := filepath.Join(tempDir, "checkpoint.json")
	writer := NewWriter(checkpointPath)

	state := &State{
		RunID:    "test-run",
		SourceDB: "src",
		TargetDB: "tgt",
		Tables:   make(map[string]TableState),
	}

	// 1. Initial save
	if err := writer.Save(state); err != nil {
		t.Fatalf("failed to save: %v", err)
	}

	// Verify file exists
	if _, err := os.Stat(checkpointPath); os.IsNotExist(err) {
		t.Fatal("checkpoint file was not created")
	}

	// 2. Load and verify
	loaded, err := writer.Load()
	if err != nil {
		t.Fatalf("failed to load: %v", err)
	}
	if loaded.RunID != "test-run" {
		t.Errorf("expected run_id test-run, got %s", loaded.RunID)
	}

	// 3. Update table with throttle
	ts := TableState{Status: StatusInProgress, RowsDone: 100}
	if err := writer.UpdateTable("users", ts); err != nil {
		t.Fatalf("failed to update table: %v", err)
	}

	// Throttle check: UpdateTable with InProgress and batchCount=1 should NOT
	// have updated the file yet (default maxBatches=10).
	// But let's check the memory state.
	if writer.(*checkpointWriter).state.Tables["users"].RowsDone != 100 {
		t.Error("memory state not updated")
	}
}

func TestWriter_Throttle(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "throttle_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	checkpointPath := filepath.Join(tempDir, "checkpoint.json")
	w := &checkpointWriter{
		path:        checkpointPath,
		maxBatches:  3,
		maxInterval: 1 * time.Hour,
		lastWrite:   time.Now(),
		state: &State{
			Tables: make(map[string]TableState),
		},
	}

	// Update 1: batchCount=1
	w.UpdateTable("t1", TableState{Status: StatusInProgress})
	if _, err := os.Stat(checkpointPath); !os.IsNotExist(err) {
		t.Error("file should not exist yet (throttled)")
	}

	// Update 2: batchCount=2
	w.UpdateTable("t1", TableState{Status: StatusInProgress})

	// Update 3: batchCount=3 -> SHOUD FLUSH
	w.UpdateTable("t1", TableState{Status: StatusInProgress})
	if _, err := os.Stat(checkpointPath); os.IsNotExist(err) {
		t.Error("file should exist now (reached maxBatches)")
	}
}

func TestWriter_StatusCompletionForceFlush(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "flush_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	checkpointPath := filepath.Join(tempDir, "checkpoint.json")
	w := &checkpointWriter{
		path:        checkpointPath,
		maxBatches:  100,
		maxInterval: 1 * time.Hour,
		lastWrite:   time.Now(),
		state: &State{
			Tables: make(map[string]TableState),
		},
	}

	// Update with Completed status should ignore batch throttle
	w.UpdateTable("t1", TableState{Status: StatusCompleted})
	if _, err := os.Stat(checkpointPath); os.IsNotExist(err) {
		t.Error("file should exist (StatusCompleted forced flush)")
	}
}
