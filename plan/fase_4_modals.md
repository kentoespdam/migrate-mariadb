# Fase 4 — Modal: Custom Mapping & Konfirmasi

> **Bergantung pada:** Fase 2 (SchemaDiff), Fase 3 (TableSelectScreen)  
> **Estimasi Durasi:** 1–2 sesi kerja  
> **File yang Dihasilkan:** `tui/modals/mapping_modal.py`, `tui/modals/confirm_modal.py`

---

## Tujuan

Membangun dua modal dialog yang menangani dua kebutuhan kritis sebelum migrasi dijalankan:
1. **MappingModal** — Memetakan kolom Host A ke kolom Host B ketika schema tidak cocok.
2. **ConfirmModal** — Meminta konfirmasi akhir dari user sebelum proses migrasi yang tidak bisa di-undo dijalankan.

> **Referensi Context7 Wajib:**
> ```bash
> npx ctx7@latest docs /websites/textual_textualize_io "ModalScreen push_screen dismiss callback result"
> ```

---

## 4.1 Konsep Modal di Textual

### Cara Kerja

Modal di Textual diimplementasikan sebagai `Screen` dengan class `ModalScreen`. Perbedaannya dengan screen biasa:
- Modal **tidak menghapus** screen di bawahnya — layer screen sebelumnya masih ada di stack.
- Untuk mengembalikan nilai dari modal ke pemanggil, gunakan metode `self.dismiss(result)`.
- Pemanggil membuka modal dengan `app.push_screen(Modal(), callback_function)` di mana `callback_function` menerima `result` dari `dismiss()`.

### Pola Umum

```
TableSelectScreen
  └─ app.push_screen(MappingModal(table_name, diff), on_mapping_done)
                                                         ↑
                                          dipanggil saat dismiss(mapping_result)
```

---

## 4.2 Modal Custom Mapping (`modals/mapping_modal.py`)

### Kapan Dibuka

Modal ini dibuka ketika user menekan `M` pada tabel yang memiliki status `❌ Diff` di `TableSelectScreen`.

### Tujuan

Membiarkan user menentukan: kolom mana di Host A yang harus dipetakan ke kolom mana di Host B. Hasilnya adalah `dict[str, str | None]` di mana key adalah nama kolom di Host A dan value adalah nama kolom di Host B (atau `None` jika kolom di-skip).

### Layout Visual

```
┌──────────────────────────────────────────────────────────────┐
│              Custom Column Mapping: tbl_log_akses            │
├──────────────────────────────────────┬───────────────────────┤
│   HOST A COLUMNS                     │   HOST B COLUMNS      │
├──────────────────────────────────────┼───────────────────────┤
│  id (bigint)                    ──▶  │  [id           ▾]     │
│  user_id (int)                  ──▶  │  [user_id      ▾]     │
│  action (varchar)               ──▶  │  [activity     ▾]     │
│  timestamp (datetime)           ──▶  │  [created_at   ▾]     │
│  ip_address (varchar)           ──▶  │  [— Skip —     ▾]     │
│  session_id (varchar)           ──▶  │  [— Skip —     ▾]     │
├──────────────────────────────────────┴───────────────────────┤
│  ⚠️ 2 columns will be skipped (NULL will be inserted)        │
│                          [Cancel]  [Save Mapping]            │
└──────────────────────────────────────────────────────────────┘
```

### Komponen Textual yang Digunakan

| Widget | Kegunaan |
|:---|:---|
| `Select` | Dropdown pilihan kolom Host B untuk setiap baris |
| `DataTable` | Menampilkan pasangan kolom |
| `Label` | Warning ringkasan kolom yang di-skip |
| `Button` | Cancel dan Save Mapping |

### Spesifikasi Data Input

Modal menerima:
- `table_name: str` — nama tabel yang sedang dikonfigurasi.
- `diff: SchemaDiff` — objek hasil `diff_columns()` dari Fase 2.
- `cols_b: list[ColumnInfo]` — semua kolom yang tersedia di Host B sebagai pilihan dropdown.

### Spesifikasi Data Output (via `dismiss()`)

```python
# Jika user Save:
dismiss({"user_id": "user_id", "action": "activity", "timestamp": "created_at", "ip_address": None})

# Jika user Cancel:
dismiss(None)
```

### Validasi

- Kolom yang merupakan Primary Key di Host A **harus** selalu di-map (tidak boleh di-skip). Beri tanda `🔑` di label dan disable opsi "Skip" untuk kolom tersebut.
- Jika ada kolom PK yang belum di-map, tombol "Save Mapping" tetap `disabled=True`.

---

## 4.3 Modal Konfirmasi (`modals/confirm_modal.py`)

### Kapan Dibuka

Dibuka ketika user menekan "→ Start Migration" di `TableSelectScreen`, setelah semua tabel yang dipilih sudah memiliki mapping yang valid.

### Tujuan

Menampilkan ringkasan lengkap apa yang akan terjadi dan meminta persetujuan eksplisit user. Ini adalah "last chance" sebelum migrasi berjalan.

### Layout Visual

```
┌─────────────────────────────────────────────────────────────────┐
│                    ⚠️ Konfirmasi Migrasi                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SOURCE  : prod-db:3306 / mydb                                  │
│  TARGET  : dev-db:3306  / mydb_v2                               │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Tabel yang akan dimigrasi:                              │    │
│  │  ✅ tbl_pegawai      —  12,450 rows  (schema match)    │    │
│  │  ✅ tbl_organisasi   —    234 rows   (schema match)    │    │
│  │  ⚠️ tbl_gaji         — 891,200 rows  (custom mapping) │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Mode     : REPLACE INTO    Batch Size: 5,000                   │
│  Dry Run  : OFF  ← WRITE OPERATIONS WILL BE EXECUTED           │
│                                                                 │
│  Total Estimasi : 903,884 rows  (~45.6 MB)                      │
│                                                                 │
│           [✕ Batal]              [✓ Mulai Migrasi]              │
└─────────────────────────────────────────────────────────────────┘
```

### Spesifikasi Data Input

Modal menerima:
- `tables: list[TableInfo]` — tabel yang dipilih beserta metadata.
- `mode: str` — mode penulisan (`"REPLACE"` atau `"ON_DUPLICATE_KEY_UPDATE"`).
- `dry_run: bool` — status Dry Run.
- `batch_size: int` — ukuran batch.
- `source_config: HostConfig`, `target_config: HostConfig` — info koneksi.

### Spesifikasi Data Output

```python
# Jika user konfirmasi:
dismiss(True)

# Jika user batal:
dismiss(False)
```

### Visual Emphasis untuk Dry Run OFF

Jika `dry_run=False`, baris "Dry Run" harus ditampilkan dengan warna merah dan teks tebal untuk menekankan bahwa ini operasi nyata yang **tidak bisa di-undo per baris** (hanya bisa di-undo jika backup ada).

---

## 4.4 Mode Penulisan — Pilihan User

User dapat memilih mode penulisan di `TableSelectScreen` sebelum membuka `ConfirmModal`. Dua opsi:

| Mode | SQL | Kapan Digunakan |
|:---|:---|:---|
| **`REPLACE INTO`** | Hapus baris lama jika PK ada, insert baris baru | Data di target boleh ditimpa sepenuhnya |
| **`ON DUPLICATE KEY UPDATE`** | Hanya update kolom yang berubah | Target sudah punya data, hanya update selisihnya |
| **`INSERT IGNORE`** | Skip baris jika PK sudah ada | Hanya tambah data baru, jangan sentuh yang sudah ada |

---

## Kriteria Selesai (Definition of Done)

- [ ] `MappingModal` membuka daftar kolom dengan dropdown pilihan kolom Host B
- [ ] Kolom PK tidak bisa di-skip
- [ ] "Save Mapping" disabled jika PK belum di-map
- [ ] Hasil mapping dikembalikan via `dismiss()` ke `TableSelectScreen`
- [ ] `ConfirmModal` menampilkan ringkasan semua tabel dengan info rows dan schema status
- [ ] Tombol "Mulai Migrasi" hanya muncul setelah user membaca semua info
- [ ] Dry Run OFF ditampilkan dengan visual peringatan merah
