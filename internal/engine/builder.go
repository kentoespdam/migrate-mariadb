package engine

import (
	"fmt"
	"strings"
)

// placeholders generates a string of placeholders for batch inserts.
// e.g., placeholders(3, 2) returns "(?,?),(?,?),(?,?)"
func placeholders(rowCount, colCount int) string {
	if rowCount <= 0 || colCount <= 0 {
		return ""
	}
	row := "(" + strings.Repeat("?, ", colCount-1) + "?)"
	return strings.Repeat(row+", ", rowCount-1) + row
}

// buildSelectQuery constructs the SELECT query for the source table.
func buildSelectQuery(job TableJob) string {
	var cols []string
	for _, c := range job.Plan.Columns {
		cols = append(cols, c.Source)
	}

	query := fmt.Sprintf("SELECT %s FROM %s", strings.Join(cols, ", "), job.Plan.SourceTable)

	if len(job.ResumePK) > 0 && len(job.Plan.LogicalKey) == len(job.ResumePK) {
		if len(job.Plan.LogicalKey) == 1 {
			query += fmt.Sprintf(" WHERE %s > ?", job.Plan.LogicalKey[0])
		} else {
			// Composite key tuple comparison: (col1, col2) > (?, ?)
			keys := strings.Join(job.Plan.LogicalKey, ", ")
			marks := strings.Repeat("?, ", len(job.ResumePK)-1) + "?"
			query += fmt.Sprintf(" WHERE (%s) > (%s)", keys, marks)
		}
	}

	if len(job.Plan.LogicalKey) > 0 {
		var orderParts []string
		for _, k := range job.Plan.LogicalKey {
			orderParts = append(orderParts, k+" ASC")
		}
		query += " ORDER BY " + strings.Join(orderParts, ", ")
	}

	return query
}

// buildInsertQuery constructs the INSERT/REPLACE query for the target table.
func buildInsertQuery(job TableJob, rowCount int) string {
	var targetCols []string
	var colNames []string
	keyMap := make(map[string]bool)
	for _, k := range job.Plan.LogicalKey {
		keyMap[strings.ToLower(k)] = true
	}

	for _, c := range job.Plan.Columns {
		targetCols = append(targetCols, c.Target)
		colNames = append(colNames, c.Target)
	}

	colsJoined := strings.Join(targetCols, ", ")
	marks := placeholders(rowCount, len(targetCols))

	switch job.Mode {
	case ModeSkip:
		return fmt.Sprintf("INSERT IGNORE INTO %s (%s) VALUES %s", job.Plan.TargetTable, colsJoined, marks)
	case ModeOverwrite:
		return fmt.Sprintf("REPLACE INTO %s (%s) VALUES %s", job.Plan.TargetTable, colsJoined, marks)
	case ModeUpdate:
		query := fmt.Sprintf("INSERT INTO %s (%s) VALUES %s ON DUPLICATE KEY UPDATE ", job.Plan.TargetTable, colsJoined, marks)
		var updates []string
		for _, col := range colNames {
			if !keyMap[strings.ToLower(col)] {
				updates = append(updates, fmt.Sprintf("%s = VALUES(%s)", col, col))
			}
		}
		if len(updates) == 0 {
			// If all columns are keys, fallback to IGNORE style or just a dummy update
			return fmt.Sprintf("INSERT IGNORE INTO %s (%s) VALUES %s", job.Plan.TargetTable, colsJoined, marks)
		}
		query += strings.Join(updates, ", ")
		return query
	default:
		return fmt.Sprintf("INSERT INTO %s (%s) VALUES %s", job.Plan.TargetTable, colsJoined, marks)
	}
}
