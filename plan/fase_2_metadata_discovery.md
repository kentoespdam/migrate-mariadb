# Fase 2 — Metadata Discovery

> **Bergantung pada:** Fase 1 (koneksi database harus sudah berfungsi)  
> **Estimasi Durasi:** 1 sesi kerja  
> **File yang Dihasilkan:** `pysync_maria/db/metadata.py`

---

## Tujuan

Membangun modul `metadata.py` yang bertugas membaca dan membandingkan informasi skema dari `information_schema` MariaDB. Modul ini adalah "otak intelijen" aplikasi — hasilnya digunakan TUI untuk menampilkan daftar tabel, ukuran data, dan peringatan schema mismatch.

---

## 2.1 Struktur Data (Data Models)

### Mengapa Perlu Model Data Terpisah

Daripada mengembalikan data mentah (list of tuples dari cursor), buat dataclass atau TypedDict yang terstruktur. Ini memudahkan TUI mengakses field secara eksplisit dan mencegah bug akibat salah urutan index.

### Model yang Harus Dibuat

**`TableInfo`** — Merepresentasikan satu tabel dari satu host:

| Field | Tipe | Keterangan |
|:---|:---|:---|
| `name` | `str` | Nama tabel |
| `row_count` | `int` | Estimasi jumlah baris (`TABLE_ROWS`) |
| `data_size_bytes` | `int` | Ukuran data dalam bytes (`DATA_LENGTH`) |
| `engine` | `str` | Storage engine (`InnoDB`, `MyISAM`, dst.) |
| `create_time` | `datetime \| None` | Waktu tabel dibuat |

**`ColumnInfo`** — Merepresentasikan satu kolom dari satu tabel:

| Field | Tipe | Keterangan |
|:---|:---|:---|
| `name` | `str` | Nama kolom |
| `data_type` | `str` | Tipe data (`varchar`, `int`, `datetime`, dst.) |
| `is_nullable` | `bool` | Apakah kolom bisa NULL |
| `column_default` | `str \| None` | Nilai default |
| `extra` | `str` | Info extra (`auto_increment`, dst.) |
| `ordinal_position` | `int` | Urutan kolom dalam tabel |

**`SchemaDiff`** — Hasil perbandingan kolom dua host:

| Field | Tipe | Keterangan |
|:---|:---|:---|
| `table_name` | `str` | Nama tabel yang dibandingkan |
| `missing_in_target` | `list[str]` | Kolom ada di Host A, tidak ada di Host B |
| `missing_in_source` | `list[str]` | Kolom ada di Host B, tidak ada di Host A |
| `type_mismatches` | `list[tuple[str, str, str]]` | `(nama_kolom, tipe_di_A, tipe_di_B)` |
| `is_compatible` | `bool` | True jika tidak ada perbedaan kritis |

---

## 2.2 Fungsi `get_tables()`

### Spesifikasi

```
get_tables(conn, database: str) -> list[TableInfo]
```

### Query yang Digunakan

Fungsi ini harus query ke `information_schema.TABLES` dengan filter:
- `TABLE_SCHEMA = database`
- `TABLE_TYPE = 'BASE TABLE'` (exclude views)

Field yang diambil: `TABLE_NAME`, `TABLE_ROWS`, `DATA_LENGTH`, `ENGINE`, `CREATE_TIME`.

### Catatan Penting

- `TABLE_ROWS` di InnoDB adalah **estimasi**, bukan jumlah pasti. Ini sudah cukup untuk keperluan progress bar.
- Urutkan hasil berdasarkan `TABLE_NAME` secara ascending agar tampilan di DataTable konsisten.
- Jika database tidak ditemukan atau kosong, kembalikan list kosong (bukan exception).

---

## 2.3 Fungsi `get_columns()`

### Spesifikasi

```
get_columns(conn, database: str, table: str) -> list[ColumnInfo]
```

### Query yang Digunakan

Query ke `information_schema.COLUMNS` dengan filter:
- `TABLE_SCHEMA = database`
- `TABLE_NAME = table`

Urutkan berdasarkan `ORDINAL_POSITION` untuk menjaga urutan kolom sesuai definisi tabel.

### Kapan Dipanggil

Fungsi ini dipanggil **dua kali** untuk setiap tabel yang dipilih user — sekali untuk Host A, sekali untuk Host B — sebelum hasil ketiga fungsi `diff_columns()` dikombinasikan.

---

## 2.4 Fungsi `diff_columns()`

### Spesifikasi

```
diff_columns(cols_a: list[ColumnInfo], cols_b: list[ColumnInfo], table_name: str) -> SchemaDiff
```

### Logika Perbandingan

1. Buat dua set nama kolom: `set_a` dan `set_b`.
2. `missing_in_target` = kolom di `set_a` yang tidak ada di `set_b`.
3. `missing_in_source` = kolom di `set_b` yang tidak ada di `set_a`.
4. `type_mismatches` = kolom yang ada di kedua host tapi memiliki `data_type` berbeda.
5. `is_compatible = True` jika `missing_in_target` kosong (migrasi masih bisa dilakukan jika Host B punya kolom extra, tapi tidak bisa jika kolom sumber tidak ada di target).

### Aturan Kompatibilitas

| Kondisi | `is_compatible` | Aksi di UI |
|:---|:---:|:---|
| Semua kolom sama persis | `True` | Tampilkan `✅ Match` |
| Host B punya kolom extra | `True` | Tampilkan `⚠️ Extra Cols` (tidak blocking) |
| Host A punya kolom tidak ada di B | `False` | Tampilkan `❌ Diff` — wajib buka Mapping Modal |
| Tipe data kolom berbeda | `True` | Tampilkan `⚠️ Type Diff` — beri peringatan |

---

## 2.5 Fungsi Helper `format_size()`

### Spesifikasi

```
format_size(bytes: int) -> str
```

Fungsi utilitas sederhana yang mengkonversi bytes ke format yang ramah manusia:
- `< 1 KB` → `"512 B"`
- `< 1 MB` → `"128.5 KB"`
- `< 1 GB` → `"45.2 MB"`
- `>= 1 GB` → `"1.3 GB"`

Digunakan oleh TUI untuk menampilkan kolom `Size` di DataTable.

---

## 2.6 Caching Metadata

### Mengapa Perlu Cache

Query `information_schema` bisa lambat pada database dengan ratusan tabel. Hasil metadata tidak berubah selama sesi migrasi, sehingga cache dalam memori aman digunakan.

### Strategi

Gunakan `functools.lru_cache` atau simpan hasil di atribut instance di worker. Cache harus dapat di-invalidasi ketika user menekan tombol `R` (reload) di TUI.

---

## Kriteria Selesai (Definition of Done)

- [ ] `get_tables()` mengembalikan list `TableInfo` terurut berdasarkan nama
- [ ] `get_columns()` mengembalikan kolom dalam urutan `ORDINAL_POSITION`
- [ ] `diff_columns()` mendeteksi perbedaan kolom dan tipe data dengan benar
- [ ] `format_size()` memformat ukuran dengan tepat
- [ ] Semua fungsi menggunakan **parameterized query** (bukan string concatenation)
- [ ] Unit test di `tests/test_metadata.py` menggunakan mock koneksi

---

## Perintah Verifikasi

```bash
# Jalankan unit test
pytest tests/test_metadata.py -v

# Test manual dengan Python REPL
python -c "
from pysync_maria.db.connection import get_connection
from pysync_maria.db.metadata import get_tables, get_columns, diff_columns
from pysync_maria.config.settings import HostConfig

cfg = HostConfig(host='localhost', user='root', password='secret', database='mydb')
with get_connection(cfg) as conn:
    tables = get_tables(conn, 'mydb')
    for t in tables:
        print(f'{t.name}: {t.row_count} rows, {t.data_size_bytes} bytes')
"
```
