# 05 — Worker Pool & Progress Sync via Channel

> **Paket:** `internal/worker`
> **Tujuan:** Menjalankan beberapa `Engine.Migrate` paralel (per-tabel), dengan *progress bar* yang sinkron ke TUI lewat satu channel.

---

## 1. Arsitektur

```
  [Monitor TUI]◄───── progress chan ─────┐
                                          │
        ┌──────────── worker pool ────────┤
        │                                  │
   ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌──▼──────┐
   │worker 0 │ │worker 1 │ │worker 2 │ │worker 3 │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘
        ▲           ▲           ▲           ▲
        └───────────┴─ job chan ┴───────────┘
                       (TableJob)
```

- **Fixed-size pool** = `cfg.Migration.WorkerCount`.
- **Job queue**: buffered channel `chan TableJob` dengan kapasitas = jumlah tabel terpilih.
- **Progress queue**: buffered `chan ProgressEvent` dengan kapasitas besar (mis. `workerCount * 10`) agar worker tidak blocked menunggu TUI.

## 2. Interface Contract

```go
// internal/worker/pool.go
type ProgressEvent struct {
    Table     string
    Processed int64
    Total     int64     // 0 kalau unknown
    Done      bool
    Err       error
}

type Pool struct {
    engine *engine.Engine
    size   int
}

// Run menjalankan semua jobs hingga selesai atau ctx dibatalkan.
// Channel progress ditutup saat semua worker selesai.
func (p *Pool) Run(ctx context.Context, jobs []engine.TableJob) (<-chan ProgressEvent, error)
```

## 3. Implementasi Inti

```go
func (p *Pool) Run(ctx context.Context, jobs []engine.TableJob) (<-chan ProgressEvent, error) {
    progress := make(chan ProgressEvent, p.size*10)
    jobCh    := make(chan engine.TableJob, len(jobs))

    for _, j := range jobs { jobCh <- j }
    close(jobCh)  // job statis → close langsung

    var wg sync.WaitGroup
    for i := 0; i < p.size; i++ {
        wg.Add(1)
        go func(workerID int) {
            defer wg.Done()
            for job := range jobCh {
                select {
                case <-ctx.Done():
                    return
                default:
                }
                rows, err := p.engine.Migrate(ctx, job) // engine sudah emit progress sendiri
                progress <- ProgressEvent{
                    Table: job.Plan.SourceTable,
                    Done:  true,
                    Err:   err,
                    Processed: rows,
                }
            }
        }(i)
    }

    go func() {
        wg.Wait()
        close(progress) // penting: TUI akan dapat sinyal "selesai"
    }()

    return progress, nil
}
```

## 4. Emitter di Sisi Engine

`engine.Migrate` menerima `chan<- worker.ProgressEvent` di konstruktor `Engine`. Setiap commit batch sukses:

```go
select {
case e.progress <- worker.ProgressEvent{Table: job.Plan.SourceTable, Processed: totalSoFar, Total: estRows}:
case <-ctx.Done():
    return totalSoFar, ctx.Err()
default:
    // channel penuh → buang event (progress lag ok, migrasi tidak boleh blok)
}
```

**Aturan emas:** **JANGAN** pakai unbuffered channel + non-select; worker akan deadlock jika TUI lambat.

## 5. Sinkronisasi ke TUI

Lihat `03-tui-bubbletea.md §5`. Secara singkat:

```go
// Saat phase monitor dimulai:
go func() {
    for ev := range progress {
        program.Send(progressTickMsg(ev)) // program = *tea.Program
    }
    program.Send(monitorDoneMsg{})
}()
```

`program.Send` adalah *thread-safe* → wajib dipakai dari goroutine non-TUI.

## 6. Batalkan / Graceful Shutdown

- User tekan `q` di monitor → TUI kirim `cancel()` ke `ctx` utama.
- Worker cek `ctx.Done()` di awal tiap iterasi dan setelah scan row → keluar loop, commit batch berjalan diselesaikan dulu (agar checkpoint konsisten).
- Pool close `progress` → TUI terima `monitorDoneMsg` → pindah ke `PhaseSummary`.

## 7. Anti Bottleneck Checklist

| Risiko | Mitigasi |
| :--- | :--- |
| Semua worker rebutan 1 connection pool kecil | `MaxOpenConns ≥ workerCount + 2` (lihat `01-config-connection.md §4`). |
| Progress channel penuh → engine blocked | Kapasitas buffer `10×workerCount` + `default` drop di select. |
| Tabel besar memblok tabel kecil | Sortir `jobs` ascending by `RowCount` → kecil duluan biar progress bar aktif cepat. |
| Worker panic | Bungkus badan worker dengan `defer recover()` → kirim ProgressEvent dengan `Err`. |

## 8. Checklist Junior Dev

- [ ] `Pool.Run` dengan WaitGroup + `close(progress)` di goroutine terpisah.
- [ ] `program.Send` dari listener goroutine (bukan langsung `Update`).
- [ ] `context.Context` diteruskan sampai query DB.
- [ ] Uji manual dengan `workerCount = 1` (bukti alur serial) lalu naikkan ke 4.
- [ ] Test kasus: batalkan mid-migrasi → checkpoint tetap konsisten.
