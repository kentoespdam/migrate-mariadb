package checkpoint

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// LogEntry represents a single structured log line.
type LogEntry struct {
	Timestamp string `json:"ts"`
	Level     string `json:"lvl"`
	Table     string `json:"tbl,omitempty"`
	Batch     int    `json:"batch,omitempty"`
	Rows      int64  `json:"rows,omitempty"`
	Duration  int64  `json:"ms,omitempty"`
	Message   string `json:"msg,omitempty"`
	Error     string `json:"err,omitempty"`
}

// Logger defines the interface for session logging.
type Logger interface {
	Info(tbl string, batch int, rows int64, ms int64, msg string)
	Warn(tbl string, msg string)
	Error(tbl string, batch int, err error)
	Close() error
}

type fileLogger struct {
	f  *os.File
	mu sync.Mutex
}

// NewLogger creates a new JSON-line logger at the specified path.
func NewLogger(path string) (Logger, error) {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file: %w", err)
	}

	return &fileLogger{f: f}, nil
}

func (l *fileLogger) log(entry LogEntry) {
	l.mu.Lock()
	defer l.mu.Unlock()

	data, err := json.Marshal(entry)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to marshal log entry: %v\n", err)
		return
	}

	fmt.Fprintln(l.f, string(data))
}

func (l *fileLogger) Info(tbl string, batch int, rows int64, ms int64, msg string) {
	l.log(LogEntry{
		Timestamp: time.Now().Format(time.RFC3339),
		Level:     "INFO",
		Table:     tbl,
		Batch:     batch,
		Rows:      rows,
		Duration:  ms,
		Message:   msg,
	})
}

func (l *fileLogger) Warn(tbl string, msg string) {
	l.log(LogEntry{
		Timestamp: time.Now().Format(time.RFC3339),
		Level:     "WARN",
		Table:     tbl,
		Message:   msg,
	})
}

func (l *fileLogger) Error(tbl string, batch int, err error) {
	errMsg := ""
	if err != nil {
		errMsg = err.Error()
	}
	l.log(LogEntry{
		Timestamp: time.Now().Format(time.RFC3339),
		Level:     "ERROR",
		Table:     tbl,
		Batch:     batch,
		Error:     errMsg,
	})
}

func (l *fileLogger) Close() error {
	if l.f != nil {
		return l.f.Close()
	}
	return nil
}
