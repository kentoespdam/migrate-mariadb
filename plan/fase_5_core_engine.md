# Fase 5 — Core Engine: Streaming & Batch Write

> **Bergantung pada:** Fase 1 (koneksi), Fase 2 (metadata model)  
> **Estimasi Durasi:** 2–3 sesi kerja  
> **File yang Dihasilkan:** `pysync_maria/db/engine.py`

---

## Tujuan

Membangun jantung aplikasi — modul `engine.py` yang bertanggung jawab membaca data dari Host A secara streaming aman memori dan menulis ke Host B secara batch yang efisien. Modul ini harus bisa bekerja untuk tabel dengan **satu juta baris atau lebih** tanpa error Out of Memory.

---

## 5.1 Arsitektur Producer–Consumer

### Mengapa Pola Ini

Migrasi database adalah masalah I/O bound klasik: kita membaca dari satu koneksi jaringan dan menulis ke koneksi jaringan lain. Pola Producer–Consumer memungkinkan kedua operasi ini di-pipeline secara efisien.

```
┌──────────────────────────────────────────────────────────┐
│                    engine.py                             │
│                                                          │
│  PRODUCER                      CONSUMER                  │
│  ─────────────────────────     ─────────────────────── │
│  stream_table()                write_batch()             │
│                                                          │
│  conn_a + SSCursor             conn_b + executemany()    │
│  cursor.fetchmany(N)    ──▶    INSERT / REPLACE          │
│  yield List[tuple]             commit() per batch        │
│                                                          │
│  Tidak load semua ke RAM       Satu transaksi per batch  │
└──────────────────────────────────────────────────────────┘
```

---

## 5.2 Fungsi `stream_table()` — Producer

### Spesifikasi

```
stream_table(
    conn: Connection,
    table: str,
    columns: list[str],
    batch_size: int = 5000,
    where_clause: str | None = None,
) -> Generator[list[tuple], None, None]
```

### Mengapa SSCursor (Unbuffered)

Dengan cursor biasa (buffered), `cursor.execute("SELECT * FROM big_table")` akan memuat **semua baris** ke RAM client sebelum bisa diiterasi. Untuk tabel 5 juta baris, ini menyebabkan OOM.

Dengan SSCursor, server MariaDB mem-*stream* baris satu per satu ke client saat diminta. Client hanya menyimpan satu batch di RAM sekaligus.

### Cara Penggunaan SSCursor

- Buat koneksi menggunakan `get_streaming_connection()` dari Fase 1.
- Gunakan `cursor = conn.cursor(MySQLCursorBufferedRaw)` atau kelas SSCursor yang sesuai.
- Setelah `cursor.execute()`, panggil `cursor.fetchmany(batch_size)` dalam loop.

### Logika Generator

```
Loop:
  rows = cursor.fetchmany(batch_size)
  if len(rows) == 0:
    break
  yield rows
Cleanup: cursor.close()
```

### Kolom yang Di-Select

Selalu gunakan `SELECT col1, col2, col3` (explicit nama kolom) — **jangan gunakan `SELECT *`**. Ini memastikan urutan kolom konsisten dengan mapping yang sudah dikonfigurasi user, bahkan jika struktur tabel berbeda.

### Filter `WHERE` (Opsional)

Sediakan parameter `where_clause` untuk mendukung partial migration di masa depan (misal: hanya migrasi data bulan ini). Parameterized query wajib digunakan.

---

## 5.3 Fungsi `write_batch()` — Consumer

### Spesifikasi

```
write_batch(
    conn: Connection,
    table: str,
    rows: list[tuple],
    columns: list[str],
    mode: WriteMode,
    dry_run: bool = False,
) -> BatchResult
```

### `WriteMode` Enum

Definisikan enum untuk mode penulisan yang aman:

```python
from enum import Enum

class WriteMode(Enum):
    REPLACE = "REPLACE"
    ON_DUPLICATE_KEY_UPDATE = "ODKU"
    INSERT_IGNORE = "INSERT_IGNORE"
```

### Membangun Query Dinamis

Query dibangun secara programatik berdasarkan `columns` dan `mode`:

**Mode REPLACE:**
```sql
REPLACE INTO `table_name` (`col1`, `col2`, `col3`) VALUES (%s, %s, %s)
```

**Mode ON DUPLICATE KEY UPDATE:**
```sql
INSERT INTO `table_name` (`col1`, `col2`, `col3`) VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE `col2` = VALUES(`col2`), `col3` = VALUES(`col3`)
```
(Kolom PK tidak disertakan di bagian UPDATE)

**Mode INSERT IGNORE:**
```sql
INSERT IGNORE INTO `table_name` (`col1`, `col2`, `col3`) VALUES (%s, %s, %s)
```

### Eksekusi & Transaksi

- Gunakan `cursor.executemany(query, rows)` — efisiensi jauh lebih tinggi dari loop `cursor.execute()` satu per satu.
- Wrap dalam `conn.start_transaction()` dan `conn.commit()` per batch.
- Jika `executemany()` gagal, lakukan `conn.rollback()` dan catat error ke log (jangan crash seluruh proses).

### Dry Run Mode

Jika `dry_run=True`:
- Bangun query seperti biasa (untuk validasi).
- **Jangan panggil `executemany()`** — hanya log query yang akan dieksekusi.
- Kembalikan `BatchResult` dengan `rows_written=0, dry_run=True`.

### `BatchResult` Data Model

```
BatchResult:
  table_name: str
  batch_number: int
  rows_read: int
  rows_written: int
  elapsed_seconds: float
  error: str | None
  dry_run: bool
```

Model ini dikirim ke Worker (Fase 6) sebagai progress update ke TUI.

---

## 5.4 Fungsi Orkestrasi `migrate_table()`

### Spesifikasi

```
migrate_table(
    conn_a: Connection,
    conn_b: Connection,
    table: str,
    columns_a: list[str],
    column_map: dict[str, str | None],
    mode: WriteMode,
    batch_size: int = 5000,
    dry_run: bool = False,
    on_batch_done: Callable[[BatchResult], None] | None = None,
) -> MigrationResult
```

### Tanggung Jawab

Fungsi ini mengorkestrasi satu tabel penuh:
1. Resolve kolom yang akan di-select dari Host A berdasarkan `column_map` (kolom yang di-map ke `None` di-skip).
2. Panggil `stream_table()` untuk mendapat generator batch.
3. Untuk setiap batch, panggil `write_batch()`.
4. Setelah setiap batch selesai, panggil `on_batch_done(result)` agar Worker bisa mengirim progress ke TUI.
5. Kembalikan `MigrationResult` yang merangkum hasil seluruh tabel.

### `MigrationResult` Data Model

```
MigrationResult:
  table_name: str
  total_rows_read: int
  total_rows_written: int
  total_batches: int
  failed_batches: int
  elapsed_seconds: float
  status: Literal["success", "partial", "failed"]
  errors: list[str]
```

---

## 5.5 Penanganan Error

### Strategi "Fail-Soft"

Engine tidak boleh berhenti total jika satu batch gagal. Strategi:
1. Jika batch gagal, log error dan **lanjutkan ke batch berikutnya**.
2. Tandai `failed_batches += 1` dan tambahkan error ke `MigrationResult.errors`.
3. Jika semua batch gagal, set `status = "failed"`.
4. Jika sebagian batch gagal, set `status = "partial"`.

### Error yang Harus Ditangani

| Error | Penanganan |
|:---|:---|
| `mysql.connector.OperationalError` (koneksi putus) | Retry 3x dengan backoff, lalu tandai batch gagal |
| `mysql.connector.DataError` (tipe data tidak cocok) | Log baris bermasalah, skip batch, lanjut |
| `mysql.connector.IntegrityError` (constraint violation) | Log, jalankan REPLACE sebagai fallback jika mode ODKU |
| `KeyboardInterrupt` | Commit batch terakhir, keluar dengan bersih |

---

## 5.6 Performance Tuning

### Parameter yang Dapat Dikonfigurasi

| Parameter | Default | Keterangan |
|:---|:---|:---|
| `batch_size` | `5000` | Jumlah baris per batch. Naikkan untuk jaringan cepat, turunkan jika RAM terbatas |
| `max_retry` | `3` | Jumlah retry saat koneksi putus |
| `retry_delay_seconds` | `2` | Delay antar retry (gunakan exponential backoff) |

### Rekomendasi `batch_size`

| Kondisi | Rekomendasi `batch_size` |
|:---|:---|
| Jaringan LAN (< 1ms latency) | 10.000 – 50.000 |
| Jaringan WAN (10ms – 100ms) | 1.000 – 5.000 |
| Tabel dengan kolom `TEXT`/`BLOB` besar | 500 – 1.000 |
| RAM client terbatas (< 1 GB) | 500 – 1.000 |

---

## Kriteria Selesai (Definition of Done)

- [ ] `stream_table()` menggunakan SSCursor dan tidak memuat semua baris ke RAM
- [ ] `write_batch()` mendukung ketiga mode (REPLACE, ODKU, INSERT_IGNORE)
- [ ] Semua query menggunakan parameterized query (tidak ada string concatenation untuk data)
- [ ] Dry Run Mode tidak menulis apapun ke Host B
- [ ] Satu batch gagal tidak menghentikan migrasi keseluruhan
- [ ] `on_batch_done` callback dipanggil setelah setiap batch
- [ ] Unit test di `tests/test_engine.py` menggunakan mock koneksi

---

## Perintah Verifikasi

```bash
# Jalankan unit test engine
pytest tests/test_engine.py -v

# Test dry run manual (membutuhkan koneksi aktif)
python -c "
from pysync_maria.db.engine import migrate_table, WriteMode
from pysync_maria.db.connection import get_connection, get_streaming_connection
from pysync_maria.config.settings import HostConfig

src = HostConfig(host='localhost', user='root', password='secret', database='mydb')
tgt = HostConfig(host='localhost', user='root', password='secret', database='mydb_v2')

with get_streaming_connection(src) as conn_a, get_connection(tgt) as conn_b:
    result = migrate_table(
        conn_a, conn_b, 'tbl_pegawai',
        columns_a=['id', 'nama', 'email'],
        column_map={'id': 'id', 'nama': 'nama', 'email': 'email'},
        mode=WriteMode.REPLACE,
        dry_run=True,
        on_batch_done=lambda r: print(f'Batch {r.batch_number}: {r.rows_read} rows')
    )
    print(f'Result: {result.status} — {result.total_rows_read} rows')
"
```
