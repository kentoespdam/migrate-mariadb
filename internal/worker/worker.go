package worker

// ProgressEvent represents a progress update from a migration worker.
type ProgressEvent struct {
	Table     string
	Processed int64
	Total     int64 // 0 if unknown
	Done      bool
	Err       error
}
