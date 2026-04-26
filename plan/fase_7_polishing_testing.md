# Fase 7 — Polishing, Dry Run Validation & Testing

> **Bergantung pada:** Fase 1–6 (semua fitur inti harus berjalan)  
> **Estimasi Durasi:** 2–3 sesi kerja  
> **File yang Dihasilkan/Dimodifikasi:** `tests/test_metadata.py`, `tests/test_engine.py`, `tui/app.py` (finalisasi), semua file yang perlu polish

---

## Tujuan

Fase ini memastikan PySync-Maria siap digunakan secara production. Bukan menambah fitur baru, melainkan mempersolid semua yang sudah ada: Dry Run end-to-end, error handling global, pengalaman keyboard yang mulus, dan test suite yang memadai.

---

## 7.1 Dry Run Mode — End-to-End

### Apa yang Harus Terjadi dalam Dry Run

Dry Run bukan sekadar skip penulisan. Ini adalah simulasi penuh yang harus memberikan laporan komprehensif:

```
Dry Run Report untuk tbl_gaji (891,200 rows)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Koneksi ke Host A: OK
✅ Koneksi ke Host B: OK
✅ Tabel 'tbl_gaji' ada di Host B: OK
⚠️ Schema Diff Terdeteksi:
   - Kolom 'jabatan_id' di Host A tidak ada di Host B
   - Mapping: jabatan_id → posisi_id (custom)
✅ Baris yang akan dimigrasi: 891,200
✅ Estimasi ukuran data: 128.5 MB
✅ Mode: REPLACE INTO
✅ Batch size: 5,000 (179 batches)

[SIMULASI BATCH] Batch 1: 5,000 rows — Query valid
[SIMULASI BATCH] Batch 2: 5,000 rows — Query valid
...

⚠️ CATATAN: Tidak ada data yang ditulis ke Host B (Dry Run Mode)
```

### Implementasi

1. Flag `dry_run` sudah ada di `migrate_table()` (Fase 5) — pastikan berjalan end-to-end dari CLI hingga Worker.
2. Setelah semua tabel selesai disimulasikan, tampilkan **Dry Run Report** di panel terpisah dalam `MigrationScreen` (bukan di log biasa).
3. Laporan harus dapat di-export ke file teks dengan menekan `E` (export).

---

## 7.2 Error Handling Global

### Error yang Harus Ditangani di Level App

| Skenario | Penanganan |
|:---|:---|
| Host A putus di tengah migrasi | Retry 3x, lalu tampilkan modal error dengan opsi "Reconnect atau Abort" |
| Host B disk penuh | Deteksi `mysql.connector.DatabaseError` code 1044/28, tampilkan pesan spesifik |
| Python crash tak terduga | Tulis log error ke `~/.pysync-maria/error.log` sebelum exit |
| Textual crash | Pastikan koneksi database ditutup di `finally` block |

### Handler Global di `app.py`

Textual menyediakan `on_error()` method di kelas `App`. Override ini untuk:
1. Menangkap exception tak terduga.
2. Menutup semua koneksi database yang masih terbuka.
3. Menampilkan modal "Unexpected Error" dengan detail error dan opsi "Exit".
4. Menyimpan error ke log file.

### Log File

Sediakan logging ke file `~/.pysync-maria/pysync.log` menggunakan `logging` module standar Python:
- Level `INFO`: setiap batch selesai, tabel selesai.
- Level `WARNING`: schema diff, tipe data berbeda, kolom di-skip.
- Level `ERROR`: batch gagal, koneksi putus.
- Level `CRITICAL`: crash tak terduga.

---

## 7.3 Keyboard Shortcuts Global (Polishing UX)

### Shortcut yang Harus Berfungsi dari Semua Screen

| Key | Aksi |
|:---|:---|
| `Q` | Buka modal konfirmasi "Keluar dari aplikasi?" |
| `?` | Buka modal "Bantuan Keyboard Shortcuts" |
| `D` | Toggle Dry Run (dengan visual indicator di semua screen) |
| `Ctrl+C` | Sama dengan `Q` (tangkap di level App) |

### Shortcut Spesifik per Screen

| Screen | Key | Aksi |
|:---|:---|:---|
| `ConnectionScreen` | `Tab` | Pindah antar Input field |
| `TableSelectScreen` | `A` | Select All / Deselect All |
| `TableSelectScreen` | `R` | Reload metadata dari kedua host |
| `TableSelectScreen` | `F` | Filter/search nama tabel |
| `MigrationScreen` | `P` | Pause / Resume |
| `MigrationScreen` | `L` | Toggle tampilan log (compac/expanded) |
| `MigrationScreen` | `E` | Export laporan ke file teks |

---

## 7.4 Fitur Filter Tabel

### Deskripsi

Di `TableSelectScreen`, tambahkan `Input` widget di atas DataTable yang berfungsi sebagai filter real-time. Saat user mengetik, DataTable hanya menampilkan tabel yang mengandung teks tersebut (case-insensitive).

### Implementasi

- Dengarkan event `Input.Changed` dari filter input.
- Filter dilakukan di sisi client (bukan re-query ke database) menggunakan list yang sudah dimuat.
- Gunakan atribut `row_key` DataTable untuk mengelola visibilitas baris.

---

## 7.5 Unit Testing

### File Test yang Harus Ada

#### `tests/test_metadata.py`

Test untuk semua fungsi di `db/metadata.py`:

| Test Case | Deskripsi |
|:---|:---|
| `test_get_tables_returns_sorted` | `get_tables()` mengembalikan tabel terurut alphabetically |
| `test_get_tables_excludes_views` | Views tidak muncul di hasil |
| `test_get_columns_ordered` | Kolom terurut berdasarkan `ORDINAL_POSITION` |
| `test_diff_columns_match` | `diff_columns()` mengembalikan `is_compatible=True` jika kolom sama |
| `test_diff_columns_missing_target` | `missing_in_target` terisi jika kolom A tidak ada di B |
| `test_diff_columns_type_mismatch` | `type_mismatches` terisi jika tipe berbeda |
| `test_format_size_bytes` | `format_size(512)` → `"512 B"` |
| `test_format_size_megabytes` | `format_size(1_500_000)` → `"1.4 MB"` |

#### `tests/test_engine.py`

Test untuk semua fungsi di `db/engine.py`:

| Test Case | Deskripsi |
|:---|:---|
| `test_stream_table_yields_batches` | Generator yield baris dalam batch sesuai `batch_size` |
| `test_stream_table_empty_table` | Tabel kosong → generator langsung selesai tanpa error |
| `test_write_batch_replace_mode` | Query yang dibangun menggunakan `REPLACE INTO` |
| `test_write_batch_odku_mode` | Query menggunakan `ON DUPLICATE KEY UPDATE` |
| `test_write_batch_dry_run` | `executemany()` tidak dipanggil jika `dry_run=True` |
| `test_migrate_table_calls_callback` | `on_batch_done` dipanggil setelah setiap batch |
| `test_migrate_table_fail_soft` | Satu batch gagal tidak stop semua — `status="partial"` |

### Cara Mock Koneksi

Gunakan `unittest.mock.MagicMock` untuk mock objek koneksi dan cursor:

```python
from unittest.mock import MagicMock, patch

def test_stream_table_yields_batches():
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [(1, "Alice"), (2, "Bob")],  # batch 1
        [],                           # sinyal selesai
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    batches = list(stream_table(mock_conn, "users", ["id", "name"], batch_size=2))
    assert len(batches) == 1
    assert batches[0] == [(1, "Alice"), (2, "Bob")]
```

---

## 7.6 README & Dokumentasi Pengguna

### `README.md` Harus Mencakup

1. **Prasyarat**: Python 3.11+, akses ke MariaDB source dan target.
2. **Instalasi**: `pip install -e .` dan konfigurasi file `.env`.
3. **Contoh File `.env.source`** dan `.env.target`.
4. **Cara menjalankan**: `pysync-maria`, `pysync-maria --dry-run`.
5. **Keyboard shortcuts** dalam format tabel.
6. **Troubleshooting** untuk error umum.

---

## Kriteria Selesai (Definition of Done)

- [ ] Dry Run menghasilkan laporan yang dapat dibaca dan di-export
- [ ] Error global ditangani tanpa crash ke terminal mentah
- [ ] Log file tersimpan di `~/.pysync-maria/pysync.log`
- [ ] Semua keyboard shortcut berfungsi dari semua screen
- [ ] Filter tabel real-time berfungsi
- [ ] `pytest tests/` berjalan hijau tanpa koneksi database nyata
- [ ] `README.md` lengkap dengan instruksi instalasi dan penggunaan

---

## Perintah Verifikasi Akhir

```bash
# Jalankan semua test
pytest tests/ -v --tb=short

# Verifikasi entry point
pysync-maria --help
pysync-maria --dry-run --source .env.source --target .env.target

# Cek tidak ada import yang rusak
python -c "import pysync_maria; print('Import OK')"

# Cek kode dengan linter
ruff check pysync_maria/
mypy pysync_maria/ --ignore-missing-imports
```
