# 01 — Konfigurasi & Koneksi Dua Host

> **Paket:** `internal/config`
> **Tujuan:** Membaca kredensial Host A (source) & Host B (target) dari `config.yaml`, lalu membuka dua `*sql.DB` yang siap pakai.

---

## 1. Format `config.yaml`

```yaml
source:
  host: "10.0.0.11"
  port: 3306
  user: "reader"
  password: "xxx"
  database: "crm_prod"
  charset: "utf8mb4"

target:
  host: "10.0.0.22"
  port: 3306
  user: "writer"
  password: "yyy"
  database: "crm_staging"
  charset: "utf8mb4"

migration:
  batch_size: 1000            # baris per commit
  worker_count: 4             # paralelisme antar-tabel
  checkpoint_path: "./.mariasync/checkpoint.json"
  log_path: "./.mariasync/run.log"
```

> **Catatan:** Password **tidak** boleh di-hardcode. Junior dev WAJIB memberi opsi `${ENV_VAR}` substitution, atau minimal `.gitignore` file `config.yaml`.

## 2. Interface Contract

```go
// internal/config/config.go
type DBConfig struct {
    Host     string
    Port     int
    User     string
    Password string
    Database string
    Charset  string
}

type MigrationConfig struct {
    BatchSize      int
    WorkerCount    int
    CheckpointPath string
    LogPath        string
}

type AppConfig struct {
    Source    DBConfig
    Target    DBConfig
    Migration MigrationConfig
}

// Load membaca file YAML & memvalidasi field wajib.
func Load(path string) (*AppConfig, error)

// DSN menghasilkan Data Source Name untuk go-sql-driver/mysql.
func (c DBConfig) DSN() string
```

## 3. Logika Pembuatan DSN

Format driver `go-sql-driver/mysql`:
```
user:password@tcp(host:port)/database?charset=utf8mb4&parseTime=true&multiStatements=false&interpolateParams=false
```

Ketentuan:
- `parseTime=true` → `TIMESTAMP`/`DATETIME` jadi `time.Time` otomatis.
- `multiStatements=false` → kurangi risiko SQL injection saat bulk insert.
- `interpolateParams=false` → gunakan prepared statement (lebih aman).
- `charset=utf8mb4` → wajib untuk data non-ASCII (emoji, aksara).

## 4. Strategi Pool Connection

```go
// Saat membuka DB:
db.SetMaxOpenConns(cfg.Migration.WorkerCount + 2) // +2 untuk query diskoveri paralel
db.SetMaxIdleConns(cfg.Migration.WorkerCount)
db.SetConnMaxLifetime(30 * time.Minute)
```

**Mengapa:** Worker pool akan memakai koneksi per-tabel. Jangan set `MaxOpenConns` terlalu tinggi — MariaDB default `max_connections` sering hanya 151.

## 5. Health Check

Sebelum TUI muncul, jalankan:
1. `ctx, cancel := context.WithTimeout(5s)` untuk kedua `db.PingContext(ctx)`.
2. Bila salah satu gagal, tampilkan error **Bahasa Indonesia** seperti:
   > `Gagal terhubung ke Host Sumber (10.0.0.11:3306): koneksi timeout`
3. `defer dbA.Close()` dan `defer dbB.Close()` di `main.go`.

## 6. Error yang Harus Di-handle

| Kondisi | Pesan TUI (BI) |
| :--- | :--- |
| File `config.yaml` tidak ada | "File konfigurasi tidak ditemukan di `{path}`" |
| YAML invalid | "Format konfigurasi salah: {detail}" |
| Field kosong | "Field wajib `source.host` tidak boleh kosong" |
| Ping gagal | "Gagal terhubung ke {role}: {err}" |
| Database tidak ada | "Database `{name}` tidak ditemukan di host {role}" |

## 7. Checklist Junior Dev

- [ ] Buat struct `AppConfig` & unmarshaling YAML.
- [ ] Tulis `DSN()` method, uji manual dengan `mysql` CLI.
- [ ] Implement `Load(path)` dengan validasi field wajib.
- [ ] Ping kedua DB di `main.go` sebelum start TUI.
- [ ] Pastikan `config.yaml` sudah masuk `.gitignore`.
