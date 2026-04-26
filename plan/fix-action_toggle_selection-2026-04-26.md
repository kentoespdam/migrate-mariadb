# Bug Fix: `action_toggle_selection` raises `CellDoesNotExist`

> **Note on output location.** The user's `dummy_plan.md` requested saving the plan to `plan/{bug-fix}.md`. In plan mode I can only edit the designated plan file, so this document lives here. After approval, the same content can be written to `plan/fix-table-select-update-cell-2026-04-26.md` as part of implementation.

## Context

The Table Selection screen (`pysync_maria/tui/screens/table_select_screen.py`) crashes whenever the user interacts with a row — pressing `space`, clicking, pressing `a`, or saving a custom mapping. The reported failure point is `action_toggle_selection` at line 260, but the same root cause also breaks `on_data_table_row_selected`, `action_toggle_all`, `_toggle_row`, and `save_mapping`. The screen renders correctly on first load because the bug only fires when the code tries to mutate an existing cell.

The fix unblocks the migration flow: without working selection, the user cannot reach the confirmation modal or `MigrationScreen`.

## Symptom → Root Cause → Proposed Fix

### Symptom
- User presses `space` (or clicks a row, or `a`) on the Table Selection screen.
- Textual raises `CellDoesNotExist` from `DataTable.update_cell`.
- The exception propagates out of the `action_toggle_selection` → `_toggle_row` chain (line 256 → 260 → 280/283) and is surfaced as an in-app error; checkbox state never updates.
- Same failure path is also reachable from row click (`on_data_table_row_selected`, lines 116/119), select-all (`action_toggle_all`, lines 268/272), and `save_mapping` (line 254).

### Root Cause
At `pysync_maria/tui/screens/table_select_screen.py:58`:

```python
table_list.add_columns("✓", "Table Name", "Rows", "Size", "Schema")
```

`DataTable.add_columns(*labels)` returns a list of auto-generated `ColumnKey` objects but the call discards them. Subsequent `update_cell(row_key, "✓", value)` and `update_cell(row_key, "Schema", value)` calls pass the *display label* as the column key. Textual's `update_cell` looks the key up in `DataTable._column_locations` (keyed by the auto-generated `ColumnKey.value`, not the label), so the lookup fails with `CellDoesNotExist`.

Confirmed against `textual==8.2.4` (pinned in `uv.lock`) — the public API requires either a stored `ColumnKey` returned from `add_columns` or an explicit `key=` passed to `add_column`.

Affected sites in the file:
- `load_metadata` (line 58) — origin of the discarded keys.
- `on_data_table_row_selected` — lines 116, 119.
- `save_mapping` — line 254 (uses `"Schema"`).
- `action_toggle_all` — lines 268, 272.
- `_toggle_row` — lines 280, 283.

### Proposed Fix (Standard: Ruff/PEP8)

Replace the single `add_columns(...)` with five `add_column(label, key="...")` calls assigning stable, semantic string keys (`check`, `name`, `rows`, `size`, `schema`), and update every `update_cell` site to use those keys.

#### Edit 1 — `load_metadata` `prepare_list`, lines 56–58
Old:
```python
def prepare_list():
    table_list.loading = True
    table_list.clear(columns=True)
    table_list.add_columns("✓", "Table Name", "Rows", "Size", "Schema")
```
New:
```python
def prepare_list():
    table_list.loading = True
    table_list.clear(columns=True)
    table_list.add_column("✓", key="check")
    table_list.add_column("Table Name", key="name")
    table_list.add_column("Rows", key="rows")
    table_list.add_column("Size", key="size")
    table_list.add_column("Schema", key="schema")
```

#### Edit 2 — `on_data_table_row_selected`, lines 116 and 119
- 116: `update_cell(event.row_key, "✓", "[ ]")` → `update_cell(event.row_key, "check", "[ ]")`
- 119: `update_cell(event.row_key, "✓", "[✓]")` → `update_cell(event.row_key, "check", "[✓]")`

#### Edit 3 — `save_mapping`, line 254
- `update_cell(table_name, "Schema", "⚙️ Custom")` → `update_cell(table_name, "schema", "⚙️ Custom")`

#### Edit 4 — `action_toggle_all`, lines 268 and 272
- 268: `update_cell(key, "✓", "[ ]")` → `update_cell(key, "check", "[ ]")`
- 272: `update_cell(key, "✓", "[✓]")` → `update_cell(key, "check", "[✓]")`

#### Edit 5 — `_toggle_row`, lines 280 and 283
- 280: `update_cell(row_key, "✓", "[ ]")` → `update_cell(row_key, "check", "[ ]")`
- 283: `update_cell(row_key, "✓", "[✓]")` → `update_cell(row_key, "check", "[✓]")`

Row keys (`add_row(*row_data, key=table.name)` at line 93/146) are already correct — no change needed.

After edits: `ruff check pysync_maria/tui/screens/table_select_screen.py` and `ruff format --check` to confirm PEP 8 compliance.

## Architecture Decisions

**Explicit string keys over captured `ColumnKey` objects.** Two viable patterns existed:

1. Capture returns: `cols = table_list.add_columns(...)`, then `self._col_check = cols[0]`, etc.
2. Explicit keys: `add_column(label, key="check")` per column.

Pattern 2 wins because:
- **Reload safety.** `load_metadata` calls `clear(columns=True)` and re-creates columns; the filter path calls `clear()` (rows only). Captured `ColumnKey` instance attributes would be stale until every reload reassigns them, an easy bug to introduce. String keys survive all reload paths trivially.
- **Readability.** `update_cell(row, "schema", "⚙️ Custom")` is self-documenting; `update_cell(row, self._col_schema, ...)` requires hunting the attribute.
- **Decoupling.** Display labels can change (e.g. localization) without touching call sites.
- **Testability.** String keys are trivial to assert in tests; `ColumnKey` UUIDs are not.

Trade-off: typo risk on the key string. Mitigation if it ever bites: hoist the keys into module-level constants (`_COL_CHECK = "check"`, etc.) — out of scope for this fix.

No deeper refactor is warranted. The bug is a localized API misuse; column-key handling is the right level of abstraction and `DataTable` is already the right widget.

## Verification

End-to-end (requires reachable source/target MariaDB instances per `pysync_maria/config`):
1. `uv run pysync-maria` (entry point from `pyproject.toml [project.scripts]`).
2. Complete the connection screen for source + target.
3. On the Table Selection screen:
   - Press `space` on a highlighted row → checkbox flips `[ ]` ↔ `[✓]`, no exception.
   - Click a row with the mouse → same toggle via `on_data_table_row_selected`.
   - Press `a` → all rows toggle in sync; press `a` again → all clear.
   - Press `m` on a row, save the mapping → Schema column shows `⚙️ Custom` for that row.
   - Press `r` to reload metadata → columns rebuild, all toggles still work.
   - Type in the search box → filtered list still selectable; selection state preserved.
4. `tail -f logs/error.log` during the above — must remain free of `CellDoesNotExist`.
5. Static checks: `uv run ruff check pysync_maria/tui/screens/table_select_screen.py` and `uv run ruff format --check pysync_maria/tui/screens/table_select_screen.py`.

## Critical Files

- `pysync_maria/tui/screens/table_select_screen.py` — only file modified.
