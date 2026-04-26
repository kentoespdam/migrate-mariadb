# PySync-Maria — Indeks Rencana Pengembangan

> **Dibuat untuk:** Junior Developer / AI Model  
> **Peran:** Senior Database Engineer & Python Systems Architect  
> **Tanggal:** 2026-04-24  
> **Bahasa:** Indonesia

---

## Gambaran Umum

**PySync-Maria** adalah aplikasi CLI interaktif berbasis TUI (Terminal User Interface) untuk memigrasikan data antar dua host MariaDB. Tampilan visual ala Navicat, namun berjalan sepenuhnya di terminal.

**Masalah yang diselesaikan:** `mysqldump` tidak interaktif, tidak ada umpan balik real-time, dan rawan OOM pada tabel besar. PySync-Maria mengisi celah ini dengan streaming aman memori, schema diff otomatis, dan progress bar real-time.

---

## Stack Library

| Komponen | Library | Versi Min |
|:---|:---|:---|
| TUI Framework | `textual` | ≥ 0.80 |
| Output / Progress | `rich` | ≥ 13.0 |
| DB Driver | `mysql-connector-python` | ≥ 9.0 |
| Config & Validasi | `pydantic-settings` | ≥ 2.0 |
| CLI Entry | `typer` | ≥ 0.12 |

> **Wajib:** Gunakan `context7` sebelum mengimplementasikan API dari library apapun.
> ```bash
> npx ctx7@latest library <nama> "<pertanyaan>"
> npx ctx7@latest docs <id> "<pertanyaan>"
> ```

---

## Struktur Direktori Proyek

```
pysync_maria/
├── pyproject.toml
├── pysync_maria/
│   ├── main.py                        # CLI entry point (Typer)
│   ├── config/
│   │   └── settings.py               # HostConfig, AppSettings (Pydantic)
│   ├── db/
│   │   ├── connection.py             # Factory koneksi & SSCursor
│   │   ├── metadata.py               # Query information_schema
│   │   └── engine.py                 # Streaming producer + batch writer
│   ├── tui/
│   │   ├── app.py                    # Kelas App utama Textual
│   │   ├── app.tcss                  # CSS styling
│   │   ├── screens/
│   │   │   ├── connection_screen.py  # Form koneksi Host A & B
│   │   │   ├── table_select_screen.py# DataTable pemilihan tabel
│   │   │   └── migration_screen.py   # Progress & log real-time
│   │   └── modals/
│   │       ├── mapping_modal.py      # Custom column mapping
│   │       └── confirm_modal.py      # Konfirmasi sebelum eksekusi
│   └── workers/
│       └── migration_worker.py       # Worker thread orkestrasi
└── tests/
    ├── test_metadata.py
    └── test_engine.py
```

---

## Diagram Alur Data (Producer–Consumer)

```
TUI Main Thread
  ├─ ConnectionScreen  ──▶  TableSelectScreen ──▶ MigrationScreen
  │                                                    ▲
  │                                          call_from_thread()
  │                                                    │
  └─ @work(thread=True) ──────────────────────────────┘
       MigrationWorker
         ├─ PRODUCER: stream_table() [Host A, SSCursor]
         │    └─▶ yield batch (5.000 baris)
         └─ CONSUMER: write_batch() [Host B, executemany()]
              └─▶ REPLACE / ON DUPLICATE KEY UPDATE / INSERT IGNORE
```

---

## Daftar Fase Pengembangan

| # | Fase | File Detail | Output Utama |
|:---|:---|:---|:---|
| 1 | **Fondasi & Konfigurasi** | [fase_1_fondasi_konfigurasi.md](fase_1_fondasi_konfigurasi.md) | `pyproject.toml`, `settings.py`, `connection.py`, `main.py` |
| 2 | **Metadata Discovery** | [fase_2_metadata_discovery.md](fase_2_metadata_discovery.md) | `metadata.py` |
| 3 | **TUI: Screens** | [fase_3_tui_screens.md](fase_3_tui_screens.md) | `app.py`, `connection_screen.py`, `table_select_screen.py` |
| 4 | **Modal Dialogs** | [fase_4_modals.md](fase_4_modals.md) | `mapping_modal.py`, `confirm_modal.py` |
| 5 | **Core Engine** | [fase_5_core_engine.md](fase_5_core_engine.md) | `engine.py` |
| 6 | **Worker & Migration Screen** | [fase_6_worker_migration_screen.md](fase_6_worker_migration_screen.md) | `migration_worker.py`, `migration_screen.py` |
| 7 | **Polishing & Testing** | [fase_7_polishing_testing.md](fase_7_polishing_testing.md) | `tests/`, `README.md`, error handling global |

**Urutan pengerjaan wajib:** 1 → 2 → 3 → 4 → 5 → 6 → 7. Setiap fase bergantung pada fase sebelumnya.

---

## Aturan Implementasi (Wajib Diikuti)

1. **Gunakan Context7** sebelum mengimplementasikan API library apapun.
2. **Jangan muat semua baris ke RAM** — selalu gunakan SSCursor + generator.
3. **Jangan jalankan I/O di Main Thread** — semua database operation harus di `@work(thread=True)`.
4. **Split file sesuai struktur direktori** — hindari file monolitik.
5. **Dry Run Mode wajib** diimplementasikan sebelum dianggap production-ready.
6. **Gunakan virtual environment** yang sudah ada, jangan install global.
7. **Semua SQL wajib parameterized query** — tidak ada string concatenation untuk data.
8. **Bangun versi minimal yang bekerja** dahulu, baru tambahkan polish (Fase 7).

---

## Perintah untuk Memulai

```bash
# Aktifkan virtual environment
source .venv/bin/activate

# Install proyek
pip install -e .

# Jalankan aplikasi
pysync-maria --help
pysync-maria --source .env.source --target .env.target
pysync-maria --dry-run --source .env.source --target .env.target

# Jalankan test
pytest tests/ -v
```

---

## Pro Tip: Dry Run Mode

Selalu jalankan **Dry Run** terlebih dahulu sebelum eksekusi nyata, terutama untuk tabel besar. Dry Run memvalidasi koneksi, schema diff, dan kalkulasi baris tanpa menulis apapun ke Host B.

---

*Untuk detail teknis setiap fase, buka file fase yang sesuai di folder `plan/`.*
