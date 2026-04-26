# Fix Plan — Tidak Bisa "Connect & Proceed" pada TUI

**Tanggal:** 2026-04-26
**Branch:** `python`
**Perintah uji:** `uv run pysync-maria --dry-run`
**File terdampak utama:** `pysync_maria/tui/screens/connection_screen.py`

---

## 1. Ringkasan Masalah

Saat menjalankan TUI, kedua tombol **Test Connection** (SOURCE & TARGET) dapat berhasil dan menampilkan `✅ Connected`, tetapi tombol **"Connect & Proceed →"** tetap **disabled** sehingga user tidak bisa lanjut ke layar berikutnya (table_select). Akibatnya seluruh proses migrasi terhenti di langkah pertama, walaupun koneksi DB sebenarnya sehat.

---

## 2. Bukti Reproduksi

Verifikasi koneksi langsung melalui `mysql.connector` (di luar TUI) menggunakan konfigurasi yang sama:

```text
=== Source Config ===
host=192.168.230.84, port=3307, user=dev, db=smartoffice
charset=utf8mb4, collation=utf8mb4_general_ci

=== Testing Source Connection ===
Source OK: connected=True, server=11.1.5-MariaDB-log

=== Testing Target Connection ===
Target OK: connected=True, server=11.4.10-MariaDB-ubu2404
```

Kesimpulan: layer DB (`pysync_maria/db/connection.py`) **berfungsi normal**. Bug ada murni di logika TUI.

---

## 3. Root Cause

File: `pysync_maria/tui/screens/connection_screen.py:96-102`

```python
def check_all_ready(self) -> None:
    """Enable the Connect button if both connections are verified."""
    source_status = self.query_one("#source-form #status", Label).renderable
    target_status = self.query_one("#target-form #status", Label).renderable

    if "✅" in str(source_status) and "✅" in str(target_status):
        self.query_one("#connect-btn", Button).disabled = False
```

Masalah:

- `Label.renderable` di Textual bersifat **write-only** untuk teks yang dipasang via `update()` dengan markup (`f"Status: [{color}]{text}[/]"`). Saat dibaca kembali, atribut `renderable` tidak menjamin string asli yang menyertakan emoji `✅` — pada banyak versi Textual ia berupa objek `Text`/`Strip` internal, atau string tanpa simbol yang diharapkan.
- Akibatnya `"✅" in str(source_status)` hampir selalu `False`, sehingga `connect-btn` tidak pernah di-enable meskipun kedua koneksi sukses.
- Pola anti-pattern ini sudah tercatat di memory (`feedback_textual_label_renderable.md`): _Textual widget text adalah write-only; lacak status di atribut, bukan dengan membaca konten widget_.

Bug tambahan terkait (yang juga harus dibersihkan):

- `check_all_ready()` dipanggil dari `commit_config()` yang **dijadwalkan via `call_from_thread`**, sehingga membaca state widget dari hasil `update()` yang mungkin **belum di-flush** ke DOM saat pengecekan dilakukan. Bahkan jika `renderable` dapat dibaca, urutan event-loop bisa bikin status terbaca stale.
- `update_status()` mengubah `Label` dari thread worker. Saat ini sudah ditangani via `call_from_thread`, tapi pengecekan kesiapan tidak boleh bergantung pada teks UI sama sekali.

---

## 4. Strategi Perbaikan

Pindahkan **state** dari widget ke atribut Python pada screen. Widget hanya untuk menampilkan; logic enable/disable membaca atribut.

### 4.1 Perubahan inti (`connection_screen.py`)

1. Tambah dua atribut boolean pada `ConnectionScreen`:
   - `self.source_ok: bool = False`
   - `self.target_ok: bool = False`
   Inisialisasi di `__init__` atau `on_mount`.

2. Pada `test_connection()`, setelah `with get_connection(config) as conn:` sukses dan `commit_config()` jalan, **set flag** sesuai form:
   ```python
   def commit_config():
       if form.id == "source-form":
           self.app.source_config = config
           self.source_ok = True
       else:
           self.app.target_config = config
           self.target_ok = True
       self.check_all_ready()
   ```

3. Pada cabang `except`, **reset flag ke False** (juga via `call_from_thread`) supaya jika user mengubah kredensial dan retest, button kembali disabled bila salah satu gagal:
   ```python
   def mark_failed():
       if form.id == "source-form":
           self.source_ok = False
       else:
           self.target_ok = False
       self.check_all_ready()
   self.app.call_from_thread(mark_failed)
   self.app.call_from_thread(update_status, f"❌ {str(e)[:40]}...", "red")
   ```

4. Refactor `check_all_ready()` agar tidak menyentuh `Label.renderable`:
   ```python
   def check_all_ready(self) -> None:
       self.query_one("#connect-btn", Button).disabled = not (
           self.source_ok and self.target_ok
       )
   ```

5. Tambah handler invalidasi: jika user mengetik ulang di `Input` apa pun (`#host`, `#port`, dst.) **setelah** sukses, anggap koneksi belum tervalidasi lagi. Implementasi:
   ```python
   def on_input_changed(self, event: Input.Changed) -> None:
       form_id = event.input.parent.parent.id  # source-form / target-form
       if form_id == "source-form":
           self.source_ok = False
       elif form_id == "target-form":
           self.target_ok = False
       self.check_all_ready()
       # opsional: reset status label ke "○ Untested"
   ```
   Ini mencegah user mengubah host setelah test sukses lalu lompat ke screen berikutnya dengan kredensial lama.

### 4.2 Perbaikan pendukung

- **Hapus** import `Label` jika tidak lagi dipakai pada `check_all_ready`. Saat ini masih dipakai untuk `update_status`, jadi biarkan.
- **Pastikan `commit_config` tidak race**: panggilan `self.app.source_config = config` & `self.source_ok = True` keduanya berjalan di thread UI (karena dibungkus `call_from_thread`), aman.
- Tambahkan **logging** ringkas saat sukses/gagal melalui `self.app.logger` (via `call_from_thread`) untuk memudahkan diagnosis di `logs/pysync.log`.

---

## 5. Rencana Implementasi (Step-by-step)

| # | Aksi | File | Estimasi |
|---|---|---|---|
| 1 | Tambah atribut `source_ok`/`target_ok` di `ConnectionScreen` | `connection_screen.py` | 5m |
| 2 | Set/reset flag di `test_connection` (sukses & gagal) | `connection_screen.py` | 10m |
| 3 | Refactor `check_all_ready` agar membaca atribut, bukan `Label.renderable` | `connection_screen.py` | 5m |
| 4 | Tambah `on_input_changed` untuk invalidasi flag saat user ubah field | `connection_screen.py` | 10m |
| 5 | Smoke test manual: jalankan `uv run pysync-maria`, pastikan tombol enable setelah dua sukses, dan kembali disable jika salah satu input diubah | terminal | 10m |
| 6 | Tambah unit test ringan untuk `check_all_ready` (mock screen tanpa Textual app) jika feasible | `tests/test_connection_screen.py` (baru) | 20m (opsional) |

Total ±40 menit (tanpa unit test) / ±60 menit (dengan unit test).

---

## 6. Verifikasi Pasca-Perbaikan

1. `uv run pysync-maria` → klik **Test Connection** SOURCE → status `✅ Connected`.
2. Klik **Test Connection** TARGET → status `✅ Connected`.
3. **Tombol "Connect & Proceed →" harus enable**.
4. Ubah field `host` SOURCE → tombol kembali disable.
5. Test ulang SOURCE sukses → tombol enable lagi.
6. Set host TARGET ke nilai invalid → status `❌ ...`, tombol disable.
7. `uv run pytest -q` → seluruh test existing tetap hijau.
8. `uv run ruff check pysync_maria/tui/screens/connection_screen.py` → tanpa warning baru.

---

## 7. Risiko & Catatan

- Perubahan terbatas pada satu file dan tidak menyentuh lapisan DB / engine, sehingga risiko regresi rendah.
- Pola yang sama (membaca state dari widget) **tidak ditemukan di tempat lain** setelah `grep renderable` — hanya `connection_screen.py`. Tetap waspadai pola serupa di review berikutnya.
- Bug ini sudah konsisten dengan memory entry `feedback_textual_label_renderable.md`; perbaikan ini menutup celah implementasi yang masih melanggar pedoman tersebut.
