# 04 — Batch Migration Engine

> **Paket:** `internal/engine`
> **Tujuan:** Menyalin data satu tabel dari `dbSrc` ke `dbTgt` dengan *streaming + batching + transaksi*, aman dari *memory leak*.

---

## 1. Prinsip Anti Memory Leak

| Masalah Umum | Solusi |
| :--- | :--- |
| `SELECT *` ke slice → OOM pada tabel besar | Streaming via `rows.Next()`, flush per-batch. |
| Prepared statement tidak di-`Close()` | Selalu `defer stmt.Close()`. |
| `rows` tidak di-`Close()` saat error | `defer rows.Close()` **langsung** setelah query. |
| Accumulated `[]interface{}` membengkak | Re-slice ke nol setelah setiap commit: `batch = batch[:0]`. |
| Goroutine bocor di worker | Pakai `context.Context` + `ctx.Done()`. |

## 2. Interface Contract

```go
// internal/engine/engine.go
type ConflictMode int
const (
    ModeSkip      ConflictMode = iota // INSERT IGNORE
    ModeUpdate                         // INSERT ... ON DUPLICATE KEY UPDATE
    ModeOverwrite                      // REPLACE INTO
)

type TableJob struct {
    Plan       mapping.TablePlan
    BatchSize  int
    Mode       ConflictMode
    ResumePK   *string   // nilai PK terakhir dari checkpoint (nil bila fresh)
}

type Engine struct {
    src, tgt *sql.DB
    progress chan<- worker.ProgressEvent
    checkpt  checkpoint.Writer
}

// Migrate menyalin satu tabel. Aman dipanggil paralel per-tabel.
func (e *Engine) Migrate(ctx context.Context, job TableJob) (rowsCopied int64, err error)
```

## 3. Alur Migrate Satu Tabel

```
 ┌──────────────────────────────┐
 │ 1. Build SELECT dgn ORDER BY  │
 │    kolom logical key ASC      │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │ 2. Jika ResumePK != nil       │
 │    → WHERE pk > ResumePK      │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │ 3. rows, _ := db.QueryContext │
 │    defer rows.Close()         │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │ 4. Loop rows.Next():          │
 │    scan → append ke batch     │
 │    jika len==BatchSize:       │
 │       flushBatch(tx)          │
 │       checkpoint.Save(lastPK) │
 │       emit ProgressEvent      │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │ 5. Flush sisa batch terakhir   │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │ 6. Emit Done event            │
 └──────────────────────────────┘
```

## 4. SELECT Streaming (Source)

Contoh query yang dibangun `Engine`:
```sql
SELECT /* key + mapped cols */
  id, email, created_at
FROM   users
WHERE  id > ?       -- (opsional, dari ResumePK)
ORDER  BY id ASC;
```

**Penting:** `ORDER BY` wajib memakai kolom `LogicalKey` agar `ResumePK` deterministik. Tanpa ini, resume bisa melewati / menduplikasi baris.

> Untuk composite key, gunakan *tuple comparison*:
> ```sql
> WHERE (col_a, col_b) > (?, ?)
> ORDER BY col_a ASC, col_b ASC
> ```

## 5. INSERT Builder (Target) per ConflictMode

### 5.1 Mode SKIP → `INSERT IGNORE`
```sql
INSERT IGNORE INTO users (id, email, created_at)
VALUES (?,?,?), (?,?,?), ...
```
Cepat. MariaDB abaikan baris yang bentrok dengan PK/UNIQUE.

### 5.2 Mode UPDATE → `ON DUPLICATE KEY UPDATE`
```sql
INSERT INTO users (id, email, created_at)
VALUES (?,?,?), (?,?,?), ...
ON DUPLICATE KEY UPDATE
   email       = VALUES(email),
   created_at  = VALUES(created_at);
```
- Bangun klausa `UPDATE` hanya untuk kolom **non-key**.
- Aman bila hanya sebagian kolom berubah.

### 5.3 Mode OVERWRITE → `REPLACE INTO`
```sql
REPLACE INTO users (id, email, created_at)
VALUES (?,?,?), (?,?,?), ...
```
- **Peringatan:** `REPLACE` = `DELETE` + `INSERT`. Memicu cascade `ON DELETE` pada foreign key → bisa menghapus data anak tanpa sengaja.
- TUI harus menampilkan konfirmasi BI:
  > "OVERWRITE akan menghapus-lalu-insert. Foreign key CASCADE bisa ikut terhapus. Lanjutkan?"

## 6. Bulk Placeholder Builder

```go
// Menghasilkan "(?,?,?),(?,?,?),..." untuk n baris × c kolom.
// Jangan dijalankan di hot-loop; cukup sekali per-batch size final.
func placeholders(rows, cols int) string {
    row := "(" + strings.Repeat("?,", cols-1) + "?)"
    return strings.Repeat(row+",", rows-1) + row
}
```

**Catatan:** Batch terakhir sering < `BatchSize`. Jangan reuse prepared statement untuk batch dengan jumlah baris berbeda — rebuild query atau pakai `stmt` hanya untuk batch "penuh" + statement kedua untuk batch "sisa".

## 7. Transaksi Per-Batch

```go
// Pseudocode (bukan copy-paste ready)
func flushBatch(ctx context.Context, tgt *sql.DB, sqlText string, args []any) error {
    tx, err := tgt.BeginTx(ctx, nil)
    if err != nil { return err }

    if _, err := tx.ExecContext(ctx, sqlText, args...); err != nil {
        _ = tx.Rollback()
        return fmt.Errorf("flush batch: %w", err)
    }
    return tx.Commit()
}
```

**Mengapa `BeginTx` baru per-batch?**
- Batas transaksi kecil → lock time pendek di target.
- Rollback batch gagal tidak menghancurkan progress batch sebelumnya.
- Checkpoint hanya ditulis *setelah* `Commit()` sukses → konsistensi.

## 8. Type-Safe Scan

Gunakan `sql.RawBytes` atau `any` yang dibentuk dari metadata kolom (`reflect.New(colType.ScanType())`). Ini menghindari alokasi ulang per baris.

```go
cols, _ := rows.ColumnTypes()
scanDest := make([]any, len(cols))
holder   := make([]any, len(cols))
for i := range cols { scanDest[i] = &holder[i] }
// loop:
rows.Scan(scanDest...)
batch = append(batch, append([]any(nil), holder...)...) // salin nilai, jangan pointer
```

> **Gotcha:** Jika batch menyimpan pointer `holder[i]` langsung, semua baris akan menunjuk buffer yang sama. **Wajib** salin isi (`append([]any(nil), holder...)`).

## 9. Checklist Junior Dev

- [ ] Builder SQL per-mode (SKIP / UPDATE / OVERWRITE) dengan unit test.
- [ ] Streaming scan dengan `rows.Next()` + salin nilai holder.
- [ ] `BeginTx` per-batch + `defer rollback jika belum commit`.
- [ ] `context.Context` diteruskan ke semua query (abort cepat saat user batalkan).
- [ ] `ProgressEvent` dikirim setelah commit sukses, bukan sebelum.
- [ ] Checkpoint `lastPK` ditulis hanya setelah commit sukses (lihat `06-recovery-checkpoint.md`).
