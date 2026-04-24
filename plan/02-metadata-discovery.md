# 02 — Metadata Discovery & Auto-Mapping

> **Paket:** `internal/discovery` + `internal/mapping`
> **Tujuan:** Membaca `information_schema` dari Host A & B, lalu menghasilkan rencana pemetaan kolom (auto + manual override).

---

## 1. Interface Contract

```go
// internal/discovery/types.go
type Column struct {
    Name       string
    DataType   string   // VARCHAR, INT, TEXT, DATETIME, ...
    Nullable   bool
    IsPrimary  bool
    IsUnique   bool
    CharMaxLen *int     // nil untuk non-string
}

type Table struct {
    Name     string
    RowCount int64    // dari TABLE_ROWS (estimasi)
    SizeMB   float64  // DATA_LENGTH + INDEX_LENGTH
    Columns  []Column
}

type SchemaSnapshot struct {
    Database string
    Tables   map[string]Table  // key = nama tabel
}

// Discover mengisi SchemaSnapshot untuk satu host.
func Discover(ctx context.Context, db *sql.DB, database string) (*SchemaSnapshot, error)
```

## 2. Query yang Dipakai

### 2.1 Daftar tabel + ukuran
```sql
SELECT TABLE_NAME, TABLE_ROWS,
       ROUND((DATA_LENGTH + INDEX_LENGTH)/1024/1024, 2) AS size_mb
FROM   information_schema.TABLES
WHERE  TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE'
ORDER  BY TABLE_NAME;
```

### 2.2 Kolom per tabel
```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
       IS_NULLABLE, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH
FROM   information_schema.COLUMNS
WHERE  TABLE_SCHEMA = ?
ORDER  BY TABLE_NAME, ORDINAL_POSITION;
```

> **Tips performa:** jalankan satu query COLUMNS untuk seluruh database, lalu *group in-memory* per `TABLE_NAME`. Hindari N+1 query.

### 2.3 Primary/Unique detail
`COLUMN_KEY`:
- `PRI` → primary key
- `UNI` → unique
- `MUL` → indexed (non-unique)

## 3. Auto-Mapping: Intersection Algorithm

```go
// internal/mapping/mapping.go
type ColumnMap struct {
    Source string
    Target string
}

type TablePlan struct {
    SourceTable string
    TargetTable string     // default = sama; user boleh ubah
    Columns     []ColumnMap
    Warnings    []string   // tipe data tidak cocok, dsb.
    LogicalKey  []string   // PK atau composite key pilihan user
}

// BuildAutoPlan = intersection berbasis nama kolom (case-insensitive).
func BuildAutoPlan(src, tgt Table) TablePlan
```

**Langkah auto-map:**
1. Normalisasi nama kolom → lowercase.
2. `setSrc = {col.Name for col in src.Columns}`
3. `setTgt = {col.Name for col in tgt.Columns}`
4. `intersection = setSrc ∩ setTgt`
5. Untuk setiap nama di intersection, bentuk `ColumnMap{Source, Target}`.
6. Susun `Warnings` jika ada ketidakcocokan tipe (lihat §4).
7. `LogicalKey`:
   - Jika kedua tabel punya PK yang **sama persis** → pakai PK itu.
   - Jika beda / tidak ada PK → `LogicalKey = nil` → user **wajib** pilih composite key di TUI (lihat `03-tui-bubbletea.md`).

## 4. Type Compatibility Matrix (Warning Rules)

| Sumber → Tujuan | Status | Aksi |
| :--- | :--- | :--- |
| `VARCHAR` → `VARCHAR` (len target < source) | ⚠ Warning | "Potensi truncation: kolom `{name}`" |
| `INT` → `VARCHAR` | ✅ OK | — |
| `VARCHAR` → `INT` | ⛔ Error | Skip kolom + warning merah |
| `DATETIME` → `TIMESTAMP` | ⚠ Warning | Tahun < 1970 / > 2038 akan error |
| `TEXT` → `VARCHAR` | ⚠ Warning | Bisa truncation |
| `DECIMAL(p,s)` → `DECIMAL(p',s')` (p' < p) | ⚠ Warning | Overflow |
| Tipe identik | ✅ OK | — |

> Matrix ini **tidak eksklusif** — junior dev boleh mulai dari baris di atas, tambah sesuai kebutuhan. Jangan diam-diam drop data; selalu warning.

## 5. Output yang Dipakai TUI

`discovery.Discover` dipanggil **paralel** untuk A & B pakai `errgroup`:

```go
g, gctx := errgroup.WithContext(ctx)
var snapA, snapB *SchemaSnapshot
g.Go(func() error { var e error; snapA, e = discovery.Discover(gctx, dbA, cfg.Source.Database); return e })
g.Go(func() error { var e error; snapB, e = discovery.Discover(gctx, dbB, cfg.Target.Database); return e })
if err := g.Wait(); err != nil { /* tampil di TUI */ }
```

Lalu bangun daftar `TablePlan` awal untuk tabel yang **ada di keduanya**.
Tabel yang hanya ada di A → tampilkan di TUI sebagai **merah + tidak bisa dicentang** (butuh `CREATE TABLE` manual dulu).

## 6. Checklist Junior Dev

- [ ] Query TABLES & COLUMNS dengan prepared statement + context timeout 30s.
- [ ] Susun `SchemaSnapshot` dalam satu pass.
- [ ] Implementasi `BuildAutoPlan` dengan unit test (tabel dummy).
- [ ] Tulis type-compat matrix sebagai fungsi kecil `isCompatible(src, tgt Column) (ok bool, warn string)`.
- [ ] Jalankan `Discover` paralel via `errgroup`.
