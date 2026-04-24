# 03 — TUI Bubble Tea (Multi-Phase)

> **Paket:** `internal/tui`
> **Library:** `charmbracelet/bubbletea` + `charmbracelet/bubbles` (list, progress, textinput).
> **Catatan:** Gunakan skill **find-docs / context7** (ID `/charmbracelet/bubbles`) sebelum menulis; API v2 sedikit berbeda dari v1.

---

## 1. State Machine (Top-Level Model)

```
             ┌──────────────┐
             │ PhaseLoading │  ← ping DB + discovery
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │PhaseDashboard│  pilih tabel (checkbox)
             └──────┬───────┘
            [Enter]│
                    ▼
             ┌──────────────┐
             │ PhaseMapping │  opsional: override kolom & composite key
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ PhaseConfig  │  batch size + conflict strategy
             └──────┬───────┘
            [Mulai]│
                    ▼
             ┌──────────────┐
             │ PhaseMonitor │  multi progress bar real-time
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ PhaseSummary │  log ringkas + lokasi checkpoint
             └──────────────┘
```

### Top-Level Model

```go
// internal/tui/model.go
type Phase int
const (
    PhaseLoading Phase = iota
    PhaseDashboard
    PhaseMapping
    PhaseConfig
    PhaseMonitor
    PhaseSummary
)

type Model struct {
    phase     Phase
    dashboard DashboardModel
    mapping   MappingModel
    config    ConfigModel
    monitor   MonitorModel
    err       error
}

func (m Model) Init() tea.Cmd { /* start discovery */ }
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) { /* delegate per phase */ }
func (m Model) View() string { /* delegate per phase */ }
```

## 2. Phase Dashboard — Pilih Tabel

**Layout (ASCII mockup):**
```
MariaSync-Go · Dashboard (Host A → Host B)
────────────────────────────────────────────────────────────
 [x] users            1.2 Mrows   78 MB   ✓ skema cocok
 [ ] orders             89 Krows   12 MB   ⚠ 2 kolom beda tipe
 [x] products           15 Krows    3 MB   ✓ skema cocok
 [ ] _migration_logs     —          —      ⛔ hanya di A
────────────────────────────────────────────────────────────
 Space: pilih  ·  a: pilih semua  ·  Enter: lanjut  ·  q: keluar
```

**Implementasi kunci:**
- Pakai `bubbles/list` dengan custom `ItemDelegate`.
- `item struct { plan mapping.TablePlan; selected bool }`.
- Handler `KeyMsg`:
  - `space` → toggle `selected` untuk item kursor.
  - `a` → toggle semua *eligible* (skip yang ⛔).
  - `enter` → validasi minimal 1 tabel dipilih → pindah ke `PhaseMapping`.

## 3. Phase Mapping — Opsional Override

Masuk per-tabel terpilih. User dapat:
1. **Lihat** auto-mapping.
2. **Edit** satu kolom (dropdown kolom target).
3. **Unassign** kolom (skip migrasi untuk kolom itu).
4. **Pilih Logical Key** (wajib jika auto-discovery tidak menemukan PK bersama).

**Layout:**
```
Mapping: users (3/3 tabel)
────────────────────────────────────────────────────────────
 Kolom Sumber      →   Kolom Tujuan       Status
 ──────────────────────────────────────────────────────────
 id                →   id                 🔑 key
 email             →   email              ok
 created_at        →   created_at         ⚠ DATETIME→TIMESTAMP
 legacy_flag       →   (abaikan)          skip
 ──────────────────────────────────────────────────────────
 Logical Key: [ id ]  · k: ubah key · e: edit map · n: lanjut
```

**State:**
```go
type MappingModel struct {
    plans   []mapping.TablePlan
    cursor  int             // index tabel aktif
    rowCur  int             // kolom aktif dalam tabel
    editing bool            // textinput / list aktif
    picker  list.Model      // untuk memilih kolom target / key
}
```

**Wajib:** jika `LogicalKey == nil`, tombol `n` **disabled**; tampilkan toast BI "Pilih minimal 1 kolom sebagai Logical Key".

## 4. Phase Config — Strategi Konflik & Batch

**Layout:**
```
Konfigurasi Migrasi
────────────────────────────────────────────────────────────
 Ukuran Batch   :   [ 1000 ]    (opsi: 500 / 1000 / 5000 / 10000)
 Jumlah Worker  :   [    4 ]    (1-8)
 Strategi Konflik:
    ( ) SKIP       — abaikan baris yang sudah ada
    (•) UPDATE     — timpa kolom non-key jika sudah ada
    ( ) OVERWRITE  — hapus dulu, lalu insert

 [ Mulai Migrasi ]    [ Kembali ]
```

**Mapping strategi → SQL** (detail di `04-batch-engine.md`):
| Pilihan TUI | Mode Engine |
| :--- | :--- |
| SKIP | `INSERT IGNORE` |
| UPDATE | `INSERT ... ON DUPLICATE KEY UPDATE` |
| OVERWRITE | `REPLACE INTO` |

## 5. Phase Monitor — Multi Progress Bar

**Layout:**
```
Migrasi Berjalan · 3 tabel · batch=1000 · worker=4
────────────────────────────────────────────────────────────
 users       ████████████░░░░░░░  60.1%   720K/1.2M  4.2k row/s
 orders      ████████████████████ 100.0%   89K/89K    selesai
 products    ███░░░░░░░░░░░░░░░░  15.3%   2.2K/15K   1.1k row/s
────────────────────────────────────────────────────────────
 total: 811K/1.3M · elapsed: 03:12 · ETA: 02:05
 q: batalkan (commit batch berjalan akan diselesaikan)
```

**Implementasi kunci:**
- Satu `progress.Model` per tabel (bubbles v2) → simpan di `map[string]progress.Model`.
- Worker mengirim `ProgressEvent` via channel (lihat `05-worker-pool-progress.md`).
- Di `Update`, konversi event ke `tea.Msg` via `tea.Cmd` adapter:

```go
func listenProgress(ch <-chan worker.ProgressEvent) tea.Cmd {
    return func() tea.Msg {
        ev, ok := <-ch
        if !ok { return monitorDoneMsg{} }
        return progressTickMsg(ev)
    }
}
```

- Setiap terima `progressTickMsg`, update percent table terkait → return `listenProgress(ch)` lagi agar channel terus dipompa.

## 6. Bahasa & Toast Standard (Bahasa Indonesia)

| Event | Pesan |
| :--- | :--- |
| Tidak ada tabel terpilih | "Pilih minimal 1 tabel untuk dimigrasi" |
| Logical key kosong | "Pilih minimal 1 kolom sebagai Logical Key" |
| Batch gagal | "Batch {n} tabel {x} gagal — rollback dilakukan" |
| Migrasi selesai | "Migrasi selesai. Total: {n} baris. Log: {path}" |
| Dibatalkan user | "Migrasi dibatalkan. Checkpoint tersimpan di {path}" |

## 7. Checklist Junior Dev

- [ ] Buat `Model` top-level dengan enum `Phase`.
- [ ] Implement `Dashboard` dengan `bubbles/list` + custom delegate.
- [ ] `Mapping` — mulai tanpa composite key picker dulu, baru tambah.
- [ ] `Config` — gunakan `bubbles/textinput` untuk batch size, validasi angka.
- [ ] `Monitor` — satu progress bar per-tabel, channel listener via `tea.Cmd`.
- [ ] Semua string user-facing dalam Bahasa Indonesia.
