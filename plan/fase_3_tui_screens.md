# Fase 3 — TUI: Screen Koneksi & Pemilihan Tabel

> **Bergantung pada:** Fase 1 (koneksi), Fase 2 (metadata)  
> **Estimasi Durasi:** 2–3 sesi kerja  
> **File yang Dihasilkan:** `pysync_maria/tui/app.py`, `tui/app.tcss`, `tui/screens/connection_screen.py`, `tui/screens/table_select_screen.py`

---

## Tujuan

Membangun dua screen pertama dari aplikasi Textual yang menjadi wajah utama PySync-Maria. Screen pertama mengumpulkan konfigurasi koneksi, screen kedua menampilkan daftar tabel yang dapat dipilih untuk dimigrasi.

> **Referensi Context7 Wajib:**
> ```bash
> npx ctx7@latest library Textual "App Screen DataTable Input Worker"
> npx ctx7@latest docs /websites/textual_textualize_io "Screen App compose on_mount DataTable"
> ```

---

## 3.1 Aplikasi Utama (`tui/app.py`)

### Yang Harus Dilakukan

Buat kelas `PySync Maria App(App)` sebagai root aplikasi Textual.

### Spesifikasi

- `TITLE = "PySync-Maria"` — ditampilkan di header terminal.
- `CSS_PATH = "app.tcss"` — pisahkan styling ke file `.tcss` terpisah.
- `SCREENS` — daftarkan semua screen yang digunakan aplikasi agar bisa di-push/pop menggunakan nama string.
- Screen pertama yang dimuat saat startup adalah `ConnectionScreen`.
- Definisikan `BINDINGS` global:
  - `Q` → keluar aplikasi (dengan modal konfirmasi)
  - `D` → toggle Dry Run mode

### Cara Menjalankan Aplikasi

Screen pertama dimuat otomatis saat `app.run()` dipanggil. Gunakan `app.push_screen("connection")` untuk pindah ke screen berikutnya, dan `app.pop_screen()` untuk kembali.

---

## 3.2 Screen Koneksi (`screens/connection_screen.py`)

### Tujuan Screen Ini

Mengumpulkan konfigurasi Host A (sumber) dan Host B (target) dari user. Ini adalah langkah pertama sebelum apapun berjalan.

### Layout Visual

```
┌─────────────────────────────────────────────────────────┐
│                    PySync-Maria                          │
│                  Connection Setup                        │
├─────────────────────┬───────────────────────────────────│
│    HOST A (SOURCE)  │       HOST B (TARGET)             │
│  Host: [_________]  │  Host: [_________]                │
│  Port: [3306_____]  │  Port: [3306_____]                │
│  User: [_________]  │  User: [_________]                │
│  Pass: [*********]  │  Pass: [*********]                │
│  DB:   [_________]  │  DB:   [_________]                │
├─────────────────────┴───────────────────────────────────│
│  [Test Connection A]  [Test Connection B]  [→ Connect]  │
│  Status: ○ Untested   Status: ○ Untested               │
└─────────────────────────────────────────────────────────┘
```

### Komponen Textual yang Digunakan

| Widget | Kegunaan |
|:---|:---|
| `Input` | Field text untuk host, port, user, database |
| `Input(password=True)` | Field password (karakter tersembunyi) |
| `Button` | Tombol "Test Connection" dan "Connect" |
| `Label` | Status koneksi (Untested / Connected / Failed) |
| `Horizontal` | Layout dua kolom (Host A di kiri, Host B di kanan) |

### Logika "Test Connection"

Ketika user menekan "Test Connection A":
1. Kumpulkan nilai dari semua `Input` widget Host A.
2. Jalankan `get_connection()` di dalam `@work` Worker (bukan di main thread!).
3. Update `Label` status menggunakan `call_from_thread()`:
   - Sukses: `✅ Connected (MariaDB 10.6.x)`
   - Gagal: `❌ Connection refused`

### Logika "→ Connect"

Tombol ini hanya aktif (`disabled=False`) jika **kedua** host sudah berhasil di-test. Saat diklik:
1. Simpan kedua `HostConfig` ke atribut app (`self.app.source_config`, `self.app.target_config`).
2. Pindah ke `TableSelectScreen` menggunakan `app.push_screen("table_select")`.

### Validasi Input

- Port harus berupa angka antara 1–65535. Gunakan validator Textual pada `Input`.
- Host dan User tidak boleh kosong.
- Tampilkan pesan error inline (bukan modal) jika validasi gagal.

---

## 3.3 Screen Pemilihan Tabel (`screens/table_select_screen.py`)

### Tujuan Screen Ini

Menampilkan inventaris lengkap tabel dari Host A dengan informasi schema diff versus Host B. User memilih tabel yang akan dimigrasi, mengonfigurasi mapping jika perlu, lalu memulai migrasi.

### Layout Visual

```
┌───────────────────────────────────────────────────────────────────────────┐
│ PySync-Maria   SOURCE: prod-db:3306/mydb  →  TARGET: dev-db:3306/mydb    │
│ [D] Dry Run: OFF    [R] Reload    [Space] Select    [M] Mapping    [→] Go │
├─────┬──────────────────────┬───────────┬──────────┬──────────────────────┤
│  ✓  │ Table Name           │ Rows      │ Size     │ Schema               │
├─────┼──────────────────────┼───────────┼──────────┼──────────────────────┤
│ [✓] │ tbl_pegawai          │ 12,450    │ 4.2 MB   │ ✅ Match             │
│ [ ] │ tbl_gaji             │ 891,200   │ 128.5 MB │ ⚠️ Type Diff         │
│ [✓] │ tbl_organisasi       │ 234       │ 48 KB    │ ✅ Match             │
│ [ ] │ tbl_log_akses        │ 5,200,000 │ 2.1 GB   │ ❌ Diff — Map Needed │
│ ... │ ...                  │ ...       │ ...      │ ...                  │
├─────┴──────────────────────┴───────────┴──────────┴──────────────────────┤
│ Selected: 2 tables   Est. rows: 12,684   [← Back]   [→ Start Migration]  │
└───────────────────────────────────────────────────────────────────────────┘
```

### Komponen Textual yang Digunakan

| Widget | Kegunaan |
|:---|:---|
| `DataTable` | Tabel utama daftar tabel |
| `Header` | Info koneksi source dan target |
| `Footer` | Keyboard shortcuts legend |
| `Label` | Statistik selection di bawah |

### Logika Loading Data

Saat screen di-mount (`on_mount`):
1. Set `data_table.loading = True` — Textual menampilkan animasi loading otomatis.
2. Jalankan `@work` async worker yang memanggil `get_tables()` untuk Host A.
3. Secara paralel, panggil `get_tables()` untuk Host B (untuk mengetahui tabel mana yang exist di target).
4. Untuk setiap tabel di Host A, panggil `diff_columns()`.
5. Setelah semua selesai, populate `DataTable` dan set `loading = False`.

### Interaksi Keyboard

| Key | Aksi |
|:---|:---|
| `↑` / `↓` | Navigasi baris |
| `Space` | Toggle selection tabel (centang/hilang centang) |
| `A` | Select All / Deselect All |
| `M` | Buka `MappingModal` untuk tabel yang di-highlight |
| `R` | Reload metadata dari kedua host |
| `D` | Toggle Dry Run mode (update label di header) |
| `Enter` / `→` | Pindah ke konfirmasi jika ada tabel yang sudah dipilih |
| `←` / `Escape` | Kembali ke `ConnectionScreen` |

### Logika Selection

- Setiap tabel di-track dalam `dict[str, bool]` (nama tabel → dipilih atau tidak).
- Tabel dengan status `❌ Diff` tidak bisa dimigrasi tanpa membuka Mapping Modal terlebih dahulu. Jika user mencoba select, tampilkan inline warning.
- Label di footer update otomatis: "Selected: N tables | Est. rows: X".

### Dry Run Indicator

Jika Dry Run aktif, tampilkan badge menonjol di header: `[DRY RUN MODE — No writes to target]` dengan warna kuning, agar user tidak lupa bahwa ini hanya simulasi.

---

## 3.4 Styling (`tui/app.tcss`)

### Panduan Styling

Gunakan Textual CSS (`.tcss`) untuk mendefinisikan tampilan. Prinsip:
- Gunakan tema gelap sebagai default (`background: $surface`).
- `DataTable` header baris harus memiliki warna yang kontras.
- Baris yang ter-select harus memiliki background highlight berbeda.
- Tombol aksi utama ("Connect", "Start Migration") gunakan `variant="success"`.
- Tombol destruktif ("Disconnect", "Cancel") gunakan `variant="error"`.
- Status label menggunakan warna semantik: hijau (sukses), merah (error), kuning (warning).

> **Referensi Context7:**
> ```bash
> npx ctx7@latest docs /websites/textual_textualize_io "CSS tcss styling DataTable color theme"
> ```

---

## Kriteria Selesai (Definition of Done)

- [ ] `ConnectionScreen` menampilkan form dua kolom dengan semua Input field
- [ ] "Test Connection" berjalan di Worker dan update status tanpa freeze UI
- [ ] Tombol "Connect" hanya aktif setelah kedua koneksi sukses
- [ ] `TableSelectScreen` menampilkan DataTable dengan loading state
- [ ] Semua kolom DataTable (Nama, Rows, Size, Schema) terisi dengan benar
- [ ] Space toggle selection berfungsi
- [ ] Tabel `❌ Diff` menampilkan warning saat dicoba di-select tanpa mapping
- [ ] Keyboard shortcut `Q`, `D`, `R` berfungsi dari screen manapun
