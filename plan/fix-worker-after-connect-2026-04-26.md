# Fix Plan — Worker Error setelah Klik "Connect & Proceed"

**Tanggal:** 2026-04-26
**Branch:** `python`
**File terdampak utama:** `pysync_maria/tui/screens/table_select_screen.py`
**Perintah uji:** `uv run pysync-maria --dry-run`

---

## 1. Context

Setelah perbaikan tombol **Connect & Proceed** (lihat `plan/fix-connect-proceed-2026-04-26.md`), tombol kini bisa di-enable dan menyebabkan `app.push_screen("table_select")`. Begitu `TableSelectScreen` ter-mount, sebuah worker `@work(exclusive=True, thread=True)` bernama `load_metadata()` berjalan untuk memuat daftar tabel. Worker ini **error** dan Textual menampilkan pesan worker error / `WorkerFailed`.

Tujuan plan ini: identifikasi semua bug yang menyebabkan worker error tersebut dan perbaiki agar `TableSelectScreen` sukses memuat metadata, bisa di-toggle baris, dan bisa di-filter tanpa exception. Semua perbaikan terbatas pada satu file UI; tidak menyentuh layer DB atau engine.

---

## 2. Bukti & Diagnosis

Aplikasi running normal sampai layar Connection (verified via `uv run pysync-maria --dry-run`). Setelah connect proceed, screen baru `TableSelectScreen` di-push. Audit kode `pysync_maria/tui/screens/table_select_screen.py` menemukan beberapa cacat yang konsisten dengan gejala "worker error setelah klik connect".

### 2.1 Bug A — `self.update_stats()` tidak pernah didefinisikan (AttributeError)

Method `update_stats()` **tidak ada** di kelas `TableSelectScreen`, tetapi dipanggil di tiga tempat:

- `table_select_screen.py:102` — `on_data_table_row_selected`
- `table_select_screen.py:238` — `action_toggle_all`
- `table_select_screen.py:249` — `_toggle_row`

Body method tersebut justru ter-inline secara tidak sengaja di **akhir `apply_filter()`** (lines 129–134), ditandai oleh docstring liar:

```python
# table_select_screen.py:128-134
            table_list.add_row(*row_data, key=table.name)
        """Update the footer selection statistics."""   # ← docstring nyasar
        num_selected = len(self.selected_tables)
        total_rows = sum(t.row_count for t in self.tables_data if t.name in self.selected_tables)
        self.query_one("#stats-label").update(...)
        self.query_one("#start-btn").disabled = num_selected == 0
```

Akibatnya:

- Saat user klik baris (atau tekan `space`/`a`), `AttributeError: 'TableSelectScreen' object has no attribute 'update_stats'` di-raise di event handler. Karena event dispatch terjadi di message-pump, exception ini ter-surface sebagai worker/handler error oleh Textual.
- `apply_filter()` saat filter diketik justru meng-update stats di akhir loop, sehingga stats label hanya diperbarui saat user mengetik filter — perilaku tidak diinginkan.

### 2.2 Bug B — `self.notify(...)` dipanggil dari thread worker

`table_select_screen.py:88` (di dalam `except` pada `load_metadata` yang berjalan di thread pool):

```python
except Exception as e:
    self.notify(f"Metadata error: {e!s}", severity="error")
```

Sesuai dokumentasi Textual (`docs/guide/workers.md`): *"you should **avoid calling methods on your UI directly** from a threaded worker… You can work around this with the `App.call_from_thread` method."* `notify` memutasi UI/Screen state, sehingga harus dijadwalkan via `call_from_thread`. Saat metadata fetch gagal (DB unreachable, schema mismatch, dst.), pemanggilan langsung `self.notify` dari thread bisa memicu race / runtime error.

### 2.3 Bug C — Inkonsistensi `self.call_from_thread` vs `self.app.call_from_thread`

Pada commit `7c369f4` ("update TUI thread safety"), `connection_screen.py` sudah konsisten menggunakan `self.app.call_from_thread`. Namun `table_select_screen.py` masih memakai `self.call_from_thread` di tiga tempat:

- `table_select_screen.py:58` — `self.call_from_thread(prepare_list)`
- `table_select_screen.py:85` — `self.call_from_thread(add_tables)`
- `table_select_screen.py:90` — `self.call_from_thread(setattr, table_list, "loading", False)`

Walau `MessagePump.call_from_thread` ada di Textual, pola yang **didokumentasikan resmi** adalah `App.call_from_thread`. Konsistensi penting karena (a) menyamakan pola dengan `connection_screen.py`, (b) menghindari ambiguitas saat self adalah Screen yang belum/tidak aktif. Lebih tegas: panggilan ini terjadi di **`on_mount` worker**, jadi bila screen sempat tergeser sebelum worker selesai (mis. user tekan back), `self.call_from_thread` pada Screen yang sudah pop bisa bermasalah.

### 2.4 Bug D — `apply_filter()` mencampur tugas filter + update stats

Selain bug A, struktur `apply_filter` membuat stats hanya diperbarui saat filter berubah. Setelah `update_stats()` diekstrak menjadi method terpisah, `apply_filter()` harus dibersihkan: filter saja, lalu opsional panggil `self.update_stats()` di akhir.

### 2.5 Catatan tambahan (sekalian dirapikan, bukan penyebab utama)

- `apply_filter` menulis kolom Schema sebagai literal `"Check Table metadata"` (placeholder). Setelah filter, status schema asli (`✅ Match` / `❌ Missing in Target`) hilang. Tidak menyebabkan crash, tapi UX rusak. **Solusi:** simpan schema status per-tabel di `dict` saat initial load, lalu reuse saat filter.
- `self.run_worker(self.fetch_and_open_mapping(...))` di `action_open_mapping` — `fetch_and_open_mapping` adalah `async` function. `run_worker` menerima coroutine, jadi pola ini benar. Tidak diubah.

---

## 3. Strategi Perbaikan

Perbaikan minimal-invasif di satu file: `pysync_maria/tui/screens/table_select_screen.py`.

### 3.1 Ekstrak `update_stats()` jadi method (Bug A & D)

```python
def update_stats(self) -> None:
    """Update the footer selection statistics."""
    num_selected = len(self.selected_tables)
    total_rows = sum(
        t.row_count
        for t in self.tables_data
        if t.name in self.selected_tables
    )
    self.query_one("#stats-label", Label).update(
        f"Selected: {num_selected} tables | Est. rows: {total_rows:,}"
    )
    self.query_one("#start-btn", Button).disabled = num_selected == 0
```

Lalu `apply_filter()` dibersihkan: hilangkan blok stats di akhir + docstring nyasar. Tetap panggil `self.update_stats()` di akhir agar tombol Start sinkron (jumlah selected tidak berubah karena filter, tapi aman dipanggil).

### 3.2 Persist schema status per-tabel (catatan 2.5 + dukung filter)

Tambah atribut `self.schema_status: dict[str, str] = {}` di `__init__`. Isi di `add_tables()` saat initial load:

```python
self.schema_status[table.name] = schema_status
```

Pakai di `apply_filter()`:
```python
schema = self.schema_status.get(table.name, "—")
row_data = [status, table.name, ..., schema]
```

### 3.3 Perbaiki thread-safety di `load_metadata()` (Bug B & C)

- Ganti seluruh `self.call_from_thread(...)` → `self.app.call_from_thread(...)` (3 lokasi).
- Bungkus `self.notify(...)` di branch `except`:
  ```python
  except Exception as e:
      self.app.call_from_thread(
          self.notify, f"Metadata error: {e!s}", severity="error"
      )
      self.app.logger.exception("load_metadata failed")
      # Catatan: logging library thread-safe, tidak perlu call_from_thread
  ```
- Tambah `worker = get_current_worker()` + early return bila `worker.is_cancelled()` (best practice Textual workers — kalau user pop screen sebelum metadata selesai).

### 3.4 (Opsional, out of scope) Cegah crash bila config invalid

`load_metadata` mengasumsikan `self.app.source_config` & `target_config` valid. Karena `ConnectionScreen` sudah memastikan via `source_ok`/`target_ok`, ini cukup ditandai TODO saja, **tidak diubah** dalam plan ini.

---

## 4. Rencana Implementasi (Step-by-step)

| # | Aksi | File | Estimasi |
|---|---|---|---|
| 1 | Tambah `__init__` field `self.schema_status: dict[str, str] = {}` | `table_select_screen.py:17-23` | 2m |
| 2 | Definisikan method `update_stats()` baru di kelas | `table_select_screen.py` (dekat `apply_filter`) | 5m |
| 3 | Bersihkan `apply_filter()`: hapus docstring nyasar + blok stats di akhir, panggil `self.update_stats()` di akhir, gunakan `self.schema_status.get(...)` untuk kolom schema | `table_select_screen.py:109-134` | 8m |
| 4 | Di `load_metadata.add_tables()`, isi `self.schema_status[table.name] = schema_status` | `table_select_screen.py:69-85` | 3m |
| 5 | Ganti 3× `self.call_from_thread` → `self.app.call_from_thread` | `table_select_screen.py:58, 85, 90` | 3m |
| 6 | Bungkus `self.notify(...)` di `except` dengan `self.app.call_from_thread`; tambah `self.app.logger.exception(...)` | `table_select_screen.py:87-90` | 5m |
| 7 | Tambah `from textual.worker import get_current_worker` + cek cancel di awal `load_metadata` | `table_select_screen.py:1-11, 47+` | 5m |
| 8 | Smoke test manual: `uv run pysync-maria` → Connect → verifikasi tabel termuat, klik baris (stats update), filter ketik, kembali ke connection (back) | terminal | 10m |
| 9 | Tambah/extend unit test ringan untuk `update_stats` & `apply_filter` (mock `self.query_one`) | `tests/test_table_select_screen.py` (baru, opsional) | 20m |

Total ±30 menit (tanpa unit test) / ±50 menit (dengan unit test).

---

## 5. Verifikasi Pasca-Perbaikan

1. `uv run pysync-maria --dry-run` → klik **Test Connection** SOURCE & TARGET hingga `✅ Connected`, lalu **Connect & Proceed →**.
2. Layar `Database Overview & Table Selection` muncul tanpa error overlay; loading indicator hilang setelah metadata selesai.
3. Daftar tabel terisi; kolom `Schema` menampilkan `✅ Match` atau `❌ Missing in Target`.
4. Klik baris tabel → kolom centang berubah `[ ]` ↔ `[✓]`, label `Selected: N tables | Est. rows: M` ter-update, tombol `Start Migration →` enable saat ≥ 1 tabel ter-pilih. **Tidak ada `AttributeError`.**
5. Tekan `a` (toggle all) → semua baris terpilih, stats sinkron.
6. Ketik di filter → list terfilter, kolom schema tetap menampilkan status asli (bukan placeholder), stats label tetap konsisten.
7. Tekan `← Back` → kembali ke connection screen tanpa error.
8. Skenario error: matikan target DB sementara, ulangi Connect & Proceed → seharusnya muncul **toast notification "Metadata error: …"** alih-alih worker crash; entri di `logs/error.log` muncul dengan traceback.
9. `uv run pytest -q` → semua test existing tetap hijau.
10. `uv run ruff check pysync_maria/tui/screens/table_select_screen.py` → tanpa warning baru.

---

## 6. File Kritis & Referensi

- `pysync_maria/tui/screens/table_select_screen.py` — satu-satunya file yang diubah.
- `pysync_maria/db/metadata.py` — `TableInfo`, `get_tables`, `format_size` (read-only, tidak diubah).
- `pysync_maria/db/connection.py` — `get_connection(config)` context manager (read-only).
- `pysync_maria/tui/screens/connection_screen.py` — referensi pola threading yang **sudah benar** (commit `7c369f4`); konsistenkan `table_select_screen.py` mengikuti pola ini.
- Textual docs (`docs/guide/workers.md`) — pola `App.call_from_thread` & `get_current_worker`.

---

## 7. Risiko & Catatan

- **Risiko regresi**: rendah. Perubahan terisolasi di satu file UI; layer DB tidak disentuh.
- **Pola serupa**: `migration_screen.py` perlu di-audit terpisah untuk pola threading yang sama (out of scope plan ini, ditandai sebagai follow-up).
