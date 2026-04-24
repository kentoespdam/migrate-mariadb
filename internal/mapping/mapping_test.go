package mapping

import (
	"mariasyncgo/internal/discovery"
	"strings"
	"testing"
)

func TestBuildAutoPlan(t *testing.T) {
	char10 := 10
	char20 := 20

	src := discovery.Table{
		Name: "users",
		Columns: []discovery.Column{
			{Name: "id", DataType: "INT", IsPrimary: true},
			{Name: "username", DataType: "VARCHAR", CharMaxLen: &char20},
			{Name: "email", DataType: "VARCHAR", CharMaxLen: &char20},
			{Name: "bio", DataType: "TEXT"},
			{Name: "created_at", DataType: "DATETIME"},
		},
	}

	tgt := discovery.Table{
		Name: "users",
		Columns: []discovery.Column{
			{Name: "id", DataType: "INT", IsPrimary: true},
			{Name: "username", DataType: "VARCHAR", CharMaxLen: &char10}, // Truncation warning
			{Name: "email", DataType: "INT"},                             // Incompatible
			{Name: "bio", DataType: "VARCHAR", CharMaxLen: &char20},      // TEXT to VARCHAR warning
			{Name: "created_at", DataType: "TIMESTAMP"},                  // DATETIME to TIMESTAMP warning
		},
	}

	plan := BuildAutoPlan(src, tgt)

	// email is skipped, so expect 4 columns: id, username, bio, created_at
	if len(plan.Columns) != 4 {
		t.Errorf("expected 4 columns mapped, got %d", len(plan.Columns))
	}

	// Warnings: username (truncation), email (incompat), bio (text->varchar), created_at (datetime->timestamp)
	expectedWarnings := 4
	if len(plan.Warnings) != expectedWarnings {
		t.Errorf("expected %d warnings, got %d. Warnings: %v", expectedWarnings, len(plan.Warnings), plan.Warnings)
	}

	foundIncompat := false
	for _, w := range plan.Warnings {
		if strings.Contains(w, "Inkompatibel") {
			foundIncompat = true
		}
	}
	if !foundIncompat {
		t.Error("expected an incompatibility warning for email")
	}

	// Check Logical Key
	if len(plan.LogicalKey) != 1 || plan.LogicalKey[0] != "id" {
		t.Errorf("expected LogicalKey ['id'], got %v", plan.LogicalKey)
	}
}
