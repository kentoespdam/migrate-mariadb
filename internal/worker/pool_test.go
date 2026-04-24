package worker

import (
	"context"
	"errors"
	"testing"
	"time"
)

type mockJob struct {
	name  string
	fail  bool
	panic bool
}

func TestPool_Run(t *testing.T) {
	jobs := []mockJob{
		{name: "table1"},
		{name: "table2"},
		{name: "table3", fail: true},
		{name: "table4", panic: true},
	}

	migrator := func(ctx context.Context, j mockJob) (int64, error) {
		if j.panic {
			panic("simulated panic")
		}
		if j.fail {
			return 0, errors.New("simulated error")
		}
		time.Sleep(10 * time.Millisecond)
		return 100, nil
	}

	extractor := func(j mockJob) string {
		return j.name
	}

	pool := NewPool(2, migrator, extractor)
	ctx := context.Background()

	progress, err := pool.Run(ctx, jobs)
	if err != nil {
		t.Fatalf("failed to run pool: %v", err)
	}

	completed := 0
	for ev := range progress {
		completed++
		switch ev.Table {
		case "table1", "table2":
			if ev.Err != nil {
				t.Errorf("table %s should have succeeded, got: %v", ev.Table, ev.Err)
			}
			if ev.Processed != 100 {
				t.Errorf("table %s should have 100 rows, got: %d", ev.Table, ev.Processed)
			}
		case "table3":
			if ev.Err == nil {
				t.Errorf("table3 should have failed")
			}
		case "table4":
			// We check for panic message in the error
			if ev.Err == nil {
				t.Errorf("table4 should have an error from panic recovery")
			}
		}
	}

	if completed < 4 {
		t.Errorf("expected 4 events, got %d", completed)
	}
}

func TestPool_Cancellation(t *testing.T) {
	jobs := []mockJob{
		{name: "slow1"},
		{name: "slow2"},
	}

	migrator := func(ctx context.Context, j mockJob) (int64, error) {
		select {
		case <-ctx.Done():
			return 0, ctx.Err()
		case <-time.After(100 * time.Millisecond):
			return 200, nil
		}
	}

	extractor := func(j mockJob) string { return j.name }

	pool := NewPool(2, migrator, extractor)
	ctx, cancel := context.WithCancel(context.Background())

	// Run and cancel immediately
	progress, _ := pool.Run(ctx, jobs)
	cancel()

	for ev := range progress {
		// Just drain it. Since we cancelled, some might error with context canceled.
		_ = ev
	}
	// Test passes if it finishes and closes the channel without hanging.
}
