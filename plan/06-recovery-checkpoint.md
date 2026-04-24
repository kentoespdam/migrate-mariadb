# 06 — Recovery: Log File + Checkpoint JSON

> **Paket:** `internal/checkpoint`
> **Tujuan:** Jika migrasi gagal / dibatalkan, user bisa jalankan ulang aplikasi dan **resume dari batch terakhir yang sukses commit** — tanpa duplikasi dan tanpa data loss.

---

## 1. Dua Artefak Persistensi

| File | Isi | Kapan ditulis |
| :--- | :--- | :--- |
| `./.mariasync/checkpoint.json` | Map `table → lastLogicalKey` + metadata run. | Setelah **setiap batch commit sukses**. |
| `./.mariasync/run.log` | Log terstruktur (INFO/WARN/ERROR) per tabel per batch. | Selama run berjalan. |

Path keduanya berasal dari `config.yaml` (`migration.checkpoint_path`, `migration.log_path`).

## 2. Skema `checkpoint.json`

```json
{
  "run_id": "2026-04-24T10-22-08Z",
  "source_db": "crm_prod",
  "target_db": "crm_staging",
  "started_at": "2026-04-24T10:22:08Z",
  "updated_at": "2026-04-24T10:35:11Z",
  "conflict_mode": "UPDATE",
  "batch_size": 1000,
  "tables": {
    "users": {
      "status": "in_progress",
      "last_key": ["18234"],
      "rows_done": 18234,
      "rows_total_est": 1200000
    },
    "orders": {
      "status": "completed",
      "last_key": ["OD-99999"],
      "rows_done": 89102,
      "rows_total_est": 89000
    },
    "products": {
      "status": "pending",
      "last_key": null,
      "rows_done": 0,
      "rows_total_est": 15000
    }
  }
}
```

- `last_key` = array agar mendukung composite key.
- `status` ∈ `pending | in_progress | completed | failed`.
- `run_id` dipakai untuk nama folder log historis (opsional).

## 3. Interface Contract

```go
// internal/checkpoint/checkpoint.go
type TableState struct {
    Status       string   // pending / in_progress / completed / failed
    LastKey      []string // nil untuk pending
    RowsDone     int64
    RowsTotalEst int64
}

type State struct {
    RunID        string
    SourceDB     string
    TargetDB     string
    ConflictMode string
    BatchSize    int
    StartedAt    time.Time
    UpdatedAt    time.Time
    Tables       map[string]TableState
}

type Writer interface {
    Load() (*State, error)         // pertama start → mungkin nil
    Save(s *State) error            // atomic write (tulis .tmp + rename)
    UpdateTable(name string, ts TableState) error
    Close() error
}
```

## 4. Atomic Write Pattern

Penulisan `checkpoint.json` harus tahan crash. Gunakan *write-rename*:

```
1. Marshal State → []byte
2. Tulis ke "checkpoint.json.tmp"
3. fsync file tmp
4. os.Rename("checkpoint.json.tmp", "checkpoint.json")
```

`os.Rename` pada filesystem yang sama = atomic. Bila crash di tengah, user hanya kehilangan **batch terakhir yang belum di-commit**, tidak korup.

> **Anti-pola yang harus dihindari junior dev:** menulis langsung ke `checkpoint.json` → crash di tengah = file JSON rusak → aplikasi panic saat resume.

## 5. Throttle: Jangan Fsync Tiap Batch

Jika batch = 1000 baris dan selesai <100ms, menulis checkpoint tiap commit bisa membebani disk. Strategi:

- **Jalur wajib:** tulis checkpoint minimal tiap **5 detik** atau **setiap 10 batch**, mana duluan.
- **Jalur final:** tulis checkpoint sekali lagi saat tabel `completed` dan saat `Pool` selesai/dibatalkan.

Trade-off: bila crash, resume bisa mundur maksimal 10 batch. Ini **aman** karena mode SKIP/UPDATE/OVERWRITE idempotent pada logical key.

## 6. Logic Resume Saat Start

```
main() load config → checkpoint.Load()
   └─ kalau State.Tables[t].Status == "in_progress"
        → TUI Dashboard tampil banner BI:
          "Ditemukan sesi sebelumnya (run_id=...). Lanjutkan atau mulai ulang?"
        └─ [Lanjutkan]  → TableJob.ResumePK = lastKey
        └─ [Mulai ulang] → hapus checkpoint.json, state fresh
```

Penting: user **tidak boleh** mencampur "lanjutkan" dengan *mengubah* pilihan tabel / mapping; banner harus mengunci kedua hal itu (disable edit di Dashboard & Mapping) agar resume konsisten.

## 7. Format `run.log`

Satu baris = satu event, JSON-lines (memudahkan `jq`):

```json
{"ts":"2026-04-24T10:22:09Z","lvl":"INFO","tbl":"users","batch":1,"rows":1000,"ms":87}
{"ts":"2026-04-24T10:22:10Z","lvl":"WARN","tbl":"users","msg":"truncated col=bio src_len=520 tgt_max=500"}
{"ts":"2026-04-24T10:22:15Z","lvl":"ERROR","tbl":"orders","batch":12,"err":"deadlock detected; retrying"}
```

Level minimum yang wajib:
- `INFO` → batch commit sukses (boleh throttled per-10-batch).
- `WARN` → truncation / type coercion.
- `ERROR` → batch rollback, retry, abort.

## 8. Retry Policy (Transient Errors)

Deadlock & lock-wait-timeout di MariaDB adalah transient. Engine harus:

1. Deteksi error code MariaDB:
   - `1205` lock wait timeout
   - `1213` deadlock
2. Retry batch **maksimal 3 kali** dengan backoff `200ms, 500ms, 1s`.
3. Gagal setelah 3× → tandai tabel `failed`, lanjut tabel lain, laporkan di Summary.

## 9. Summary Phase (Setelah Migrasi)

Data yang ditampilkan di TUI Summary berasal dari `State.Tables`:

```
Ringkasan Migrasi
─────────────────────────────────────────────
 ✓ users      1.200.000 baris  03:15
 ✓ orders        89.102 baris  00:12
 ✗ products      2.210 baris  (gagal: deadlock 3×)

 Log   : ./.mariasync/run.log
 Resume: ./.mariasync/checkpoint.json
─────────────────────────────────────────────
 q: keluar  ·  r: coba ulang tabel gagal
```

## 10. Checklist Junior Dev

- [ ] Skema `State` + marshal/unmarshal JSON.
- [ ] `Save()` pakai pola tmp-rename + fsync.
- [ ] Throttle: 5 detik atau 10 batch.
- [ ] `Load()` handle `os.IsNotExist` → return `nil, nil` (fresh run).
- [ ] Banner "Lanjutkan sesi sebelumnya" di Dashboard bila state in_progress.
- [ ] `run.log` sebagai JSON-lines (satu line = satu event).
- [ ] Retry policy untuk deadlock / lock wait.
