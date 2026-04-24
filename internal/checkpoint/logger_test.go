package checkpoint

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestLogger(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "logger_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	logPath := filepath.Join(tempDir, "run.log")
	logger, err := NewLogger(logPath)
	if err != nil {
		t.Fatalf("failed to create logger: %v", err)
	}

	logger.Info("users", 1, 1000, 150, "batch committed")
	logger.Warn("users", "truncation occurred")
	logger.Error("orders", 5, os.ErrPermission)
	logger.Close()

	// Verify file content
	f, err := os.Open(logPath)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	lines := 0
	for scanner.Scan() {
		lines++
		var entry LogEntry
		if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
			t.Errorf("line %d is not valid JSON: %v", lines, err)
		}

		switch lines {
		case 1:
			if entry.Level != "INFO" || entry.Table != "users" {
				t.Errorf("unexpected info entry: %+v", entry)
			}
		case 2:
			if entry.Level != "WARN" || entry.Message != "truncation occurred" {
				t.Errorf("unexpected warn entry: %+v", entry)
			}
		case 3:
			if entry.Level != "ERROR" || entry.Error != os.ErrPermission.Error() {
				t.Errorf("unexpected error entry: %+v", entry)
			}
		}
	}

	if lines != 3 {
		t.Errorf("expected 3 log lines, got %d", lines)
	}
}
