package mapping

import (
	"fmt"
	"strings"

	"mariasyncgo/internal/discovery"
)

// ColumnMap represents a mapping between source and target columns.
type ColumnMap struct {
	Source string
	Target string
}

// TablePlan represents the migration plan for a single table.
type TablePlan struct {
	SourceTable string
	TargetTable string
	Columns     []ColumnMap
	Warnings    []string
	LogicalKey  []string // PK or user-selected composite key
}

// BuildAutoPlan generates a TablePlan by performing an intersection based on column names.
func BuildAutoPlan(src, tgt discovery.Table) TablePlan {
	plan := TablePlan{
		SourceTable: src.Name,
		TargetTable: tgt.Name,
		Columns:     make([]ColumnMap, 0),
		Warnings:    make([]string, 0),
	}

	tgtCols := make(map[string]discovery.Column)
	for _, col := range tgt.Columns {
		tgtCols[strings.ToLower(col.Name)] = col
	}

	for _, sCol := range src.Columns {
		sNameLower := strings.ToLower(sCol.Name)
		if tCol, exists := tgtCols[sNameLower]; exists {
			ok, warn := isCompatible(sCol, tCol)
			if !ok {
				plan.Warnings = append(plan.Warnings, fmt.Sprintf("Skip kolom '%s': %s", sCol.Name, warn))
				continue
			}
			if warn != "" {
				plan.Warnings = append(plan.Warnings, fmt.Sprintf("Kolom '%s': %s", sCol.Name, warn))
			}

			plan.Columns = append(plan.Columns, ColumnMap{
				Source: sCol.Name,
				Target: tCol.Name,
			})
		}
	}

	// Logical Key Logic
	srcPKs := getPKs(src)
	tgtPKs := getPKs(tgt)

	if len(srcPKs) > 0 && equalStringSlice(srcPKs, tgtPKs) {
		plan.LogicalKey = srcPKs
	}

	return plan
}

func isCompatible(src, tgt discovery.Column) (bool, string) {
	sTyp := strings.ToUpper(src.DataType)
	tTyp := strings.ToUpper(tgt.DataType)

	if sTyp == tTyp {
		// Length check for string types
		if strings.Contains(sTyp, "CHAR") || strings.Contains(sTyp, "TEXT") {
			if src.CharMaxLen != nil && tgt.CharMaxLen != nil {
				if *tgt.CharMaxLen < *src.CharMaxLen {
					return true, fmt.Sprintf("Potensi truncation: target (%d) < source (%d)", *tgt.CharMaxLen, *src.CharMaxLen)
				}
			}
		}
		return true, ""
	}

	// Specific rules from plan
	switch {
	case strings.Contains(sTyp, "INT") && strings.Contains(tTyp, "VARCHAR"):
		return true, ""
	case strings.Contains(sTyp, "VARCHAR") && strings.Contains(tTyp, "INT"):
		return false, "Inkompatibel: VARCHAR ke INT tidak diizinkan secara otomatis"
	case sTyp == "DATETIME" && tTyp == "TIMESTAMP":
		return true, "Warning: Tahun < 1970 atau > 2038 akan menyebabkan error pada TIMESTAMP"
	case sTyp == "TEXT" && tTyp == "VARCHAR":
		return true, "Potensi truncation dari TEXT ke VARCHAR"
	}

	// Generic fallback
	return true, fmt.Sprintf("Tipe berbeda (%s -> %s), periksa manual", sTyp, tTyp)
}

func getPKs(t discovery.Table) []string {
	var pks []string
	for _, col := range t.Columns {
		if col.IsPrimary {
			pks = append(pks, col.Name)
		}
	}
	return pks
}

func equalStringSlice(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if !strings.EqualFold(a[i], b[i]) {
			return false
		}
	}
	return true
}
