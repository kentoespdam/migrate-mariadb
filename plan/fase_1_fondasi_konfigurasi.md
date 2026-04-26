# Fase 1 — Fondasi & Konfigurasi

> **Dependensi Fase Berikutnya:** Fase 2, 3, 4, 5, 6, 7 semuanya bergantung pada fase ini.  
> **Estimasi Durasi:** 1–2 sesi kerja  
> **File yang Dihasilkan:** `pyproject.toml`, `pysync_maria/main.py`, `pysync_maria/config/settings.py`, `pysync_maria/db/connection.py`

---

## Tujuan

Membangun tulang punggung proyek: struktur direktori, model konfigurasi koneksi, factory koneksi database, dan entri poin CLI. Fase ini tidak boleh dilewati — semua komponen lain bergantung padanya.

---

## 1.1 Inisiasi Proyek

### Yang Harus Dilakukan

Buat struktur direktori proyek sesuai dengan rencana arsitektur. Gunakan `pyproject.toml` sebagai satu-satunya sumber kebenaran untuk metadata proyek dan dependencies.

### Struktur yang Harus Ada Setelah Fase Ini

```
pysync_maria/
├── pyproject.toml
├── pysync_maria/
│   ├── __init__.py          ← tandai sebagai package Python
│   ├── main.py              ← CLI entry point
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   └── db/
│       ├── __init__.py
│       └── connection.py
```

### Isi `pyproject.toml`

File ini mendefinisikan nama proyek, dependencies, dan script entry point:

```toml
[project]
name = "pysync-maria"
version = "0.1.0"
description = "Interactive TUI for MariaDB-to-MariaDB data migration"
requires-python = ">=3.11"
dependencies = [
    "textual>=0.80",
    "rich>=13.0",
    "mysql-connector-python>=9.0",
    "pydantic-settings>=2.0",
    "typer>=0.12",
]

[project.scripts]
pysync-maria = "pysync_maria.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Mengapa `pyproject.toml` Bukan `requirements.txt`

`pyproject.toml` adalah standar modern Python (PEP 517/518). Ini memungkinkan instalasi proyek sebagai package (`pip install -e .`) sehingga entry point `pysync-maria` dapat digunakan langsung dari terminal.

---

## 1.2 Model Konfigurasi Koneksi (`config/settings.py`)

### Yang Harus Dilakukan

Buat model `HostConfig` menggunakan **Pydantic BaseSettings** untuk merepresentasikan satu host database. Model ini bisa dibaca dari environment variable atau file `.env`.

### Kenapa Pydantic

Pydantic memvalidasi tipe data secara otomatis saat runtime. Jika user memberikan `port` sebagai string `"3306"`, Pydantic otomatis mengkonversinya ke `int`. Ini mencegah error tipe data saat koneksi dibuat.

### Spesifikasi `HostConfig`

Field yang wajib ada:

| Field | Tipe | Default | Keterangan |
|:---|:---|:---|:---|
| `host` | `str` | — | Hostname atau IP address |
| `port` | `int` | `3306` | Port MariaDB |
| `user` | `str` | — | Username database |
| `password` | `SecretStr` | — | Password (disimpan aman, tidak terprint ke log) |
| `database` | `str` | — | Nama database target |
| `charset` | `str` | `"utf8mb4"` | Charset koneksi |
| `connect_timeout` | `int` | `10` | Timeout dalam detik |

### Spesifikasi `AppSettings`

Buat satu model tingkat atas `AppSettings` yang mengandung dua `HostConfig`:

```
AppSettings
├── source: HostConfig   ← Host A (sumber data)
└── target: HostConfig   ← Host B (tujuan data)
```

Baca konfigurasi dari file `.env` dengan prefix berbeda:
- `SOURCE_HOST`, `SOURCE_PORT`, `SOURCE_USER`, dst. untuk Host A
- `TARGET_HOST`, `TARGET_PORT`, `TARGET_USER`, dst. untuk Host B

> **Referensi Context7:** Sebelum implementasi, jalankan:
> ```bash
> npx ctx7@latest library pydantic-settings "BaseSettings env_prefix nested model"
> npx ctx7@latest docs <id> "nested model env prefix configuration"
> ```

---

## 1.3 Factory Koneksi Database (`db/connection.py`)

### Yang Harus Dilakukan

Buat dua fungsi factory yang mengembalikan koneksi MySQL:
1. `get_connection(config: HostConfig)` — koneksi standar (buffered), untuk query metadata ringan.
2. `get_streaming_connection(config: HostConfig)` — koneksi dengan `use_pure=True` dan kursor `SSCursor` (unbuffered), untuk membaca jutaan baris tanpa OOM.

### Perbedaan Buffered vs Unbuffered (SSCursor)

| Jenis | Cara Kerja | Kapan Digunakan |
|:---|:---|:---|
| **Buffered** (default) | Semua hasil query dimuat ke RAM client sekaligus | Query metadata ringan (< 10.000 baris) |
| **Unbuffered (SSCursor)** | Baris dibaca satu per satu dari server saat dipanggil | Streaming tabel besar (jutaan baris) |

### Spesifikasi Fungsi

Setiap fungsi factory harus:
- Menerima `HostConfig` sebagai parameter.
- Mengembalikan objek koneksi MySQL.
- Melakukan validasi `ping()` setelah koneksi dibuat untuk memastikan koneksi aktif.
- Melempar `ConnectionError` dengan pesan yang informatif jika koneksi gagal (bukan membiarkan exception MySQL mentah).
- Menyediakan context manager (`with get_connection(...) as conn:`) agar koneksi otomatis ditutup.

### Anti-Pattern yang Harus Dihindari

- ❌ Jangan buat koneksi global/singleton — setiap operasi harus mendapat koneksi segar.
- ❌ Jangan tangkap `Exception` secara luas — tangkap `mysql.connector.Error` spesifik.
- ❌ Jangan print password ke log — gunakan `config.password.get_secret_value()` hanya saat dibutuhkan.

> **Referensi Context7:**
> ```bash
> npx ctx7@latest library mysql-connector-python "SSCursor unbuffered streaming connection"
> npx ctx7@latest docs <id> "SSCursor fetchmany streaming large table"
> ```

---

## 1.4 CLI Entry Point (`main.py`)

### Yang Harus Dilakukan

Buat CLI entry point menggunakan **Typer** yang menjadi pintu masuk aplikasi sebelum TUI diluncurkan.

### Spesifikasi Perintah CLI

```
pysync-maria [OPTIONS]

Options:
  --source TEXT     Path ke file .env untuk Host A  [default: .env.source]
  --target TEXT     Path ke file .env untuk Host B  [default: .env.target]
  --batch-size INT  Ukuran batch per iterasi         [default: 5000]
  --dry-run         Jalankan tanpa menulis ke Host B
  --version         Tampilkan versi aplikasi
  --help            Tampilkan bantuan
```

### Alur di `main.py`

1. Parse argumen CLI menggunakan Typer.
2. Muat `AppSettings` dari file `.env` yang ditentukan.
3. Validasi bahwa file `.env` ada — jika tidak, tampilkan pesan error yang jelas dan exit.
4. Teruskan konfigurasi ke aplikasi TUI Textual.
5. Jalankan `app.run()` untuk memulai TUI.

### Mengapa Typer

Typer menghasilkan `--help` secara otomatis, mendukung tipe Python (seperti `Path`, `int`, `bool`) dengan validasi bawaan, dan tidak memerlukan boilerplate argparse.

> **Referensi Context7:**
> ```bash
> npx ctx7@latest library typer "CLI options Path env file"
> npx ctx7@latest docs <id> "typer options default value path"
> ```

---

## Kriteria Selesai (Definition of Done)

- [ ] `pyproject.toml` ada dan dapat di-install dengan `pip install -e .`
- [ ] `pysync-maria --help` menampilkan semua opsi CLI
- [ ] `HostConfig` menolak koneksi dengan field yang tidak valid
- [ ] `get_connection()` berhasil terhubung ke MariaDB lokal dan melempar error informatif jika gagal
- [ ] `get_streaming_connection()` mengembalikan koneksi dengan SSCursor aktif
- [ ] Tidak ada hardcoded credential di source code

---

## Perintah Verifikasi

```bash
# Install proyek dalam mode development
pip install -e .

# Cek entry point terdaftar
pysync-maria --help

# Test koneksi manual (opsional, gunakan Python REPL)
python -c "
from pysync_maria.config.settings import HostConfig
from pysync_maria.db.connection import get_connection

cfg = HostConfig(host='localhost', user='root', password='secret', database='test')
with get_connection(cfg) as conn:
    print('Koneksi berhasil:', conn.is_connected())
"
```
