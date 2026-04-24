# 00 — Blueprint Arsitektur MariaSync-Go

> **Target Pembaca:** Junior developer & small AI models.
> **Bahasa UI:** Bahasa Indonesia (semua label TUI, toast, error message).
> **Bahasa Dokumen:** Bahasa Indonesia.
> **Aturan Utama:** Dokumen ini berisi **how-to**, bukan source code. Cuplikan kode hanya sebagai *interface contract* & ilustrasi logika.

---

## 1. Tujuan Aplikasi

MariaSync-Go adalah CLI interaktif (TUI) berbasis `bubbletea` yang:
1. Membaca skema dua host MariaDB (Host A = source, Host B = target).
2. Menyajikan daftar tabel ke user dalam bentuk *checkbox* untuk dipilih.
3. Memungkinkan *auto-mapping* kolom + *manual override* bila perlu.
4. Menjalankan migrasi batch dengan strategi konflik yang dipilih user.
5. Menampilkan *multi progress bar* real-time per tabel.
6. Menyimpan *checkpoint* agar migrasi yang gagal bisa di-resume.

## 2. Struktur Folder Target

```
migrate-mariadb/
├── cmd/
│   └── mariasyncgo/
│       └── main.go              # entrypoint: load config → start TUI
├── internal/
│   ├── config/                  # YAML loader (lihat 01-config-connection.md)
│   ├── discovery/               # information_schema reader (02-metadata-discovery.md)
│   ├── mapping/                 # column intersection + type validator
│   ├── tui/                     # bubbletea models (03-tui-bubbletea.md)
│   │   ├── dashboard.go
│   │   ├── mapping.go
│   │   ├── config.go
│   │   └── monitor.go
│   ├── engine/                  # batch migrator (04-batch-engine.md)
│   ├── worker/                  # pool & progress channel (05-worker-pool-progress.md)
│   └── checkpoint/              # resume/log writer (06-recovery-checkpoint.md)
├── plan/                        # dokumentasi ini
├── config.yaml                  # kredensial Host A & B
└── go.mod
```

## 3. Alur Eksekusi (High-Level)

```
[main.go]
   │
   ▼
 load config.yaml  ──►  open sql.DB A & B  ──►  ping both
   │
   ▼
 TUI Phase 1: Dashboard  (daftar tabel + metadata + checkbox)
   │
   ▼
 TUI Phase 2: Mapping   (auto-map + manual override opsional)
   │
   ▼
 TUI Phase 3: Config    (batch size, conflict strategy, composite-key picker)
   │
   ▼
 TUI Phase 4: Monitor   (multi progress bar ← channel ← worker pool)
   │                            │
   │                            └── engine.migrateTable(ctx, tbl) per worker
   │                                     └── commit per-batch + checkpoint write
   ▼
 Summary + log path
```

## 4. Prinsip Desain

| Prinsip | Implementasi Kunci |
| :--- | :--- |
| **Tidak bocor memori** | Streaming `rows.Next()`, batch flush, hindari `SELECT *` ke slice besar. |
| **Transaksional** | Commit per-N baris; rollback otomatis jika batch gagal. |
| **Resumable** | Setiap commit sukses → tulis offset/last-PK ke `checkpoint.json`. |
| **Observable** | Satu `progress.Event` channel untuk seluruh worker → TUI monitor. |
| **Aman untuk junior** | Interface kecil, tanggung jawab tunggal per-package. |

## 5. Urutan Baca Dokumen

Baca sesuai urutan nomor — setiap file dapat dikerjakan sebagai satu *pull request* oleh junior dev:

1. `01-config-connection.md` — bootstrap koneksi.
2. `02-metadata-discovery.md` — reader skema.
3. `03-tui-bubbletea.md` — UI layer.
4. `04-batch-engine.md` — query builder + transaksi.
5. `05-worker-pool-progress.md` — orkestrasi paralel.
6. `06-recovery-checkpoint.md` — ketahanan kegagalan.

## 6. Dependency Pinned (rekomendasi)

| Library | ID Context7 | Alasan |
| :--- | :--- | :--- |
| `charmbracelet/bubbletea` | `/websites/pkg_go_dev_github_com_charmbracelet_bubbletea` | TUI framework (Model-View-Update). |
| `charmbracelet/bubbles` | `/charmbracelet/bubbles` | Komponen siap pakai: `list`, `progress`, `textinput`. |
| `go-sql-driver/mysql` | (driver resmi MariaDB-compat) | Driver `database/sql` untuk MariaDB. |
| `gopkg.in/yaml.v3` | — | Parser `config.yaml`. |

> Gunakan skill **find-docs / context7** sebelum menulis kode menggunakan library ini — API bisa berubah antar-versi.
