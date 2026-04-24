# MariaSync-Go

MariaSync-Go adalah utilitas CLI interaktif (TUI) berbasis `bubbletea` yang dirancang untuk melakukan migrasi dan sinkronisasi data antar host MariaDB dengan aman, transaksional, dan mudah dipantau secara real-time.

## Fitur Utama

- **Antarmuka TUI Interaktif**: Memudahkan pemilihan tabel, konfigurasi perpindahan data, dan memantau status eksekusi menggunakan Terminal User Interface.
- **Auto-Mapping**: Mengidentifikasi skema antara Host Sumber dan Host Target, melakukan auto-map pada persinggungan kolom, dan mendukung *manual-override* bagi pengguna.
- **Batch Processing & Streaming**: Membaca basis data menggunakan `rows.Next()` dari *prepared statements* untuk menghindari beban memori dan menjalankan transaksi insert/update/skip secara *batching*.
- **Ketahanan (Resumability)**: Otomatis mencatat pos (checkpoint) offset *Primary Key* atau baris terakhir yang sukses agar migrasi yang terputus dapat di-*resume* (dilanjutkan kembali).
- **Paralel & Observability**: Menyediakan multi-*progress bar* real-time berbasis koneksi terpool dan eksekutor *goroutine worker pool*.

## Struktur Proyek

Aplikasi dirancang berlapis-lapis (layered) untuk tujuan *maintenance* yang mudah serta *single-responsibility*.

- `cmd/mariasyncgo/` : *Entrypoint* utama aplikasi (Load Config -> Start TUI).
- `internal/config/` : Pembaca konfigurasi utama `config.yaml` dan pembuatan DSN koneksi `database/sql`.
- `internal/discovery/` : Pengecekan *Information Schema* mendalam; mengambil daftar tabel, tipe data, dan konstrain pada Host Sumber dan Target.
- `internal/mapping/` : Pembuat auto-map pada list kolom-kolom yang sama dan dapat dipindahkan antara Sumber dan Target beserta validator kompatibilitas tipenya.
- `internal/tui/` : Logika *state-machine* *bubbletea* untuk mengelola layar *Dashboard*, *Mapping*, *Config*, *Monitor*, dan hasil *Summary*.
- `internal/engine/` : Mesin utama pembangun *Query Statement* insersi yang terkompilasi dan pengelola transaksi batch dari/ke database.
- `internal/worker/` : Pengelola thread (*worker pool*) dan pengantrian job antartabel serta agregasi log/status progress *channel*.
- `internal/checkpoint/` : Modul pemroduksi log dan JSON resumer (*recovery/safety net*).
- `plan/` : Repositori dokumentasi internal tata-rancang dan spesifikasi arsitektur proyek.

## Konfigurasi

Buat dan gunakan `config.yaml` pada direktori dasar (root) proyek yang mengandung informasi Host MariaDB. (Disiapkan via skema module `internal/config`)

## Cara Menjalankan

Masuk ke dalam direktori proyek ini, lalu jalankan:

```bash
# Menjalankan langsung
go run cmd/mariasyncgo/main.go

# Atau melakukan build executable file
go build -o mariasync cmd/mariasyncgo/main.go
./mariasync
```
