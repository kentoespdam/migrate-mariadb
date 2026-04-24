package engine

import (
	"mariasyncgo/internal/mapping"
	"testing"
)

func TestPlaceholders(t *testing.T) {
	tests := []struct {
		rows, cols int
		expected   string
	}{
		{3, 2, "(?, ?), (?, ?), (?, ?)"},
		{1, 1, "(?)"},
		{0, 5, ""},
		{5, 0, ""},
	}

	for _, tt := range tests {
		res := placeholders(tt.rows, tt.cols)
		if res != tt.expected {
			t.Errorf("placeholders(%d, %d) = %s; want %s", tt.rows, tt.cols, res, tt.expected)
		}
	}
}

func TestBuildSelectQuery(t *testing.T) {
	job := TableJob{
		Plan: mapping.TablePlan{
			SourceTable: "users",
			Columns: []mapping.ColumnMap{
				{Source: "id"},
				{Source: "email"},
			},
			LogicalKey: []string{"id"},
		},
	}

	// Fresh run
	q := buildSelectQuery(job)
	expected := "SELECT id, email FROM users ORDER BY id ASC"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}

	// Resume run
	job.ResumePK = []string{"100"}
	q = buildSelectQuery(job)
	expected = "SELECT id, email FROM users WHERE id > ? ORDER BY id ASC"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}

	// Composite key
	job.Plan.LogicalKey = []string{"org_id", "user_id"}
	job.ResumePK = []string{"1", "100"}
	q = buildSelectQuery(job)
	expected = "SELECT id, email FROM users WHERE (org_id, user_id) > (?, ?) ORDER BY org_id ASC, user_id ASC"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}
}

func TestBuildInsertQuery(t *testing.T) {
	job := TableJob{
		Plan: mapping.TablePlan{
			TargetTable: "users_tgt",
			Columns: []mapping.ColumnMap{
				{Target: "id"},
				{Target: "email"},
				{Target: "updated_at"},
			},
			LogicalKey: []string{"id"},
		},
		Mode: ModeUpdate,
	}

	// Mode UPDATE
	q := buildInsertQuery(job, 2)
	expected := "INSERT INTO users_tgt (id, email, updated_at) VALUES (?, ?, ?), (?, ?, ?) ON DUPLICATE KEY UPDATE email = VALUES(email), updated_at = VALUES(updated_at)"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}

	// Mode SKIP
	job.Mode = ModeSkip
	q = buildInsertQuery(job, 1)
	expected = "INSERT IGNORE INTO users_tgt (id, email, updated_at) VALUES (?, ?, ?)"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}

	// Mode OVERWRITE
	job.Mode = ModeOverwrite
	q = buildInsertQuery(job, 1)
	expected = "REPLACE INTO users_tgt (id, email, updated_at) VALUES (?, ?, ?)"
	if q != expected {
		t.Errorf("got %q; want %q", q, expected)
	}
}
