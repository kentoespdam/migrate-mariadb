# Fase 6 — Worker Thread & Migration Screen

> **Bergantung pada:** Fase 3 (TUI App), Fase 5 (engine.py)  
> **Estimasi Durasi:** 2 sesi kerja  
> **File yang Dihasilkan:** `pysync_maria/workers/migration_worker.py`, `tui/screens/migration_screen.py`

---

## Tujuan

Menjembatani Core Engine (Fase 5) dengan TUI (Fase 3): Worker Thread menjalankan proses migrasi di background tanpa membekukan UI, sementara Migration Screen menampilkan progres secara real-time kepada user.

> **Referensi Context7 Wajib:**
> ```bash
> npx ctx7@latest docs /websites/textual_textualize_io "work thread=True call_from_thread Worker ProgressBar RichLog"
> ```

---

## 6.1 Prinsip Thread Safety di Textual

### Aturan Utama

**Textual adalah event-driven framework berbasis asyncio.** UI hanya boleh diupdate dari main thread (event loop). Semua operasi I/O berat (koneksi database, baca/tulis data) harus dijalankan di Worker Thread.

### Dua Jenis Worker di Textual

| Jenis | Dekorator | Kapan Digunakan |
|:---|:---|:---|
| **Async Worker** | `@work` | Untuk operasi `async def` — cocok untuk I/O ringan menggunakan `asyncio` |
| **Thread Worker** | `@work(thread=True)` | Untuk operasi blocking synchronous — cocok untuk `mysql-connector-python` yang tidak async-native |

Karena `mysql-connector-python` **tidak mendukung asyncio natively**, kita **wajib** menggunakan `@work(thread=True)` untuk operasi database.

### Cara Update UI dari Thread

Dari dalam thread worker, **jangan pernah** memanggil widget secara langsung. Gunakan:

```python
# Cara yang SALAH — akan crash
self.app.query_one(ProgressBar).advance(batch.rows_read)

# Cara yang BENAR — thread-safe
self.app.call_from_thread(self.app.query_one(ProgressBar).advance, batch.rows_read)
```

---

## 6.2 Worker (`workers/migration_worker.py`)

### Tanggung Jawab

Worker adalah orkestrator yang:
1. Membuka koneksi ke Host A dan Host B.
2. Menjalankan `migrate_table()` dari `engine.py` untuk setiap tabel yang dipilih, secara **sequential** (satu per satu, bukan paralel) untuk menghindari overload koneksi.
3. Mengirim update progres ke `MigrationScreen` setelah setiap batch dan setiap tabel selesai.
4. Menangani pembatalan (`cancel()`) dengan bersih.

### Spesifikasi Kelas

```
class MigrationWorker:
  Atribut:
    app: PySync MariaApp
    tables: list[TableInfo]              ← tabel yang dipilih
    column_maps: dict[str, dict]         ← mapping kolom per tabel
    source_config: HostConfig
    target_config: HostConfig
    mode: WriteMode
    batch_size: int
    dry_run: bool
```

### Menggunakan `@work(thread=True)`

Buat metode `run()` di kelas `MigrationScreen` (bukan di kelas worker terpisah) yang di-dekorasi dengan `@work(thread=True)`. Di Textual, worker paling idiomatis ditulis sebagai metode di Screen, bukan sebagai kelas standalone.

### Alur Eksekusi Worker

```
run_migration():
  Buka conn_a (SSCursor) dan conn_b
  
  Untuk setiap tabel dalam tables:
    Kirim event: "Memulai tabel X dari Y..."
    
    migrate_table(
      conn_a, conn_b, table,
      on_batch_done = lambda result: call_from_thread(update_progress, result)
    )
    
    Kirim event: "Tabel X selesai — N rows"
  
  Tutup semua koneksi
  Kirim event: "Semua selesai"
```

### Event/Message yang Dikirim ke Screen

Gunakan `call_from_thread` untuk memanggil method di screen yang mengupdate UI:

| Event | Payload | Update UI yang Terjadi |
|:---|:---|:---|
| `on_table_start` | `table_name, total_rows` | Set progress bar max, update header tabel aktif |
| `on_batch_done` | `BatchResult` | Advance progress bar, tambah log entry |
| `on_table_done` | `MigrationResult` | Update status tabel di list, tampilkan ringkasan |
| `on_all_done` | `list[MigrationResult]` | Tampilkan laporan akhir, aktifkan tombol "Done" |
| `on_error` | `table_name, error_msg` | Tambah entri error di log, tandai tabel gagal |

### Pembatalan (Cancellation)

Textual menyediakan mekanisme `worker.cancel()`. Agar pembatalan bersih:
- Cek `self.is_cancelled` sebelum setiap batch baru.
- Jika `is_cancelled`, commit batch terakhir yang sedang berjalan, tutup koneksi, dan return.
- Jangan biarkan transaksi terbuka saat proses dibatalkan.

---

## 6.3 Migration Screen (`screens/migration_screen.py`)

### Tujuan Screen Ini

Menampilkan progres migrasi secara real-time dalam tampilan yang informatif dan menenangkan (bukan sekedar log mentah).

### Layout Visual

```
┌────────────────────────────────────────────────────────────────────────┐
│  PySync-Maria  [DRY RUN]  SOURCE: prod-db → TARGET: dev-db            │
├────────────────────────────────────────────────────────────────────────┤
│  PROGRESS                                                              │
│                                                                        │
│  Overall:  ████████████████░░░░░░░░░░░░  2/3 tables  (66%)           │
│                                                                        │
│  Current Table: tbl_gaji                                               │
│  ████████████████████████░░░░░  450,000 / 891,200 rows  (50.5%)       │
│  Speed: ~8,200 rows/s    ETA: ~54s                                    │
├────────────────────────────────────────────────────────────────────────┤
│  MIGRATION LOG                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  15:23:01 ✅ tbl_pegawai   — 12,450 rows migrated in 1.5s       │ │
│  │  15:23:03 ✅ tbl_organisasi — 234 rows migrated in 0.1s         │ │
│  │  15:23:03 ▶️  tbl_gaji      — Batch 1/178 (5,000 rows)...       │ │
│  │  15:23:04    tbl_gaji      — Batch 2/178 (5,000 rows)...        │ │
│  │  15:23:05    tbl_gaji      — Batch 3/178 (5,000 rows)...        │ │
│  └──────────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│  [⏸ Pause]  [✕ Cancel]                          Elapsed: 00:01:32    │
└────────────────────────────────────────────────────────────────────────┘
```

### Komponen Textual yang Digunakan

| Widget | Kegunaan |
|:---|:---|
| `ProgressBar` | Progress overall (per tabel dari total) |
| `ProgressBar` | Progress tabel aktif (per baris) |
| `RichLog` | Log scrollable real-time |
| `Label` | Kecepatan rows/s dan ETA |
| `Label` | Timer elapsed |
| `Button` | Pause / Cancel |

### Kalkulasi Kecepatan & ETA

Update setiap kali `on_batch_done` dipanggil:
- `speed = rows_done / elapsed_seconds` (rolling average 5 batch terakhir untuk smooth)
- `eta = (total_rows - rows_done) / speed`
- Format ETA dalam `MM:SS` atau `HH:MM:SS`

### Fitur Pause/Resume

- Tombol "Pause" menghentikan sementara loop batch di Worker menggunakan `threading.Event` yang di-clear saat pause dan di-set saat resume.
- Saat paused, progress bar berhenti dan label status berubah menjadi `⏸ Paused`.

### Setelah Semua Tabel Selesai

Saat `on_all_done` diterima:
- Tampilkan modal ringkasan: total baris berhasil, total gagal, waktu total.
- Aktifkan tombol "Done" yang membawa user kembali ke `TableSelectScreen`.
- Ubah progress bar menjadi 100% dengan warna hijau.

---

## Kriteria Selesai (Definition of Done)

- [ ] Worker berjalan di thread terpisah (`@work(thread=True)`)
- [ ] UI tidak freeze selama migrasi berjalan
- [ ] `call_from_thread` digunakan untuk semua update UI dari worker
- [ ] Progress bar overall dan per-tabel update secara real-time
- [ ] `RichLog` menampilkan log dengan timestamp
- [ ] Kecepatan rows/s dan ETA dihitung dan ditampilkan
- [ ] Tombol Cancel menghentikan worker secara bersih (commit terakhir, tutup koneksi)
- [ ] Modal ringkasan tampil setelah semua tabel selesai
