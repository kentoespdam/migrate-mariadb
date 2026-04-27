# Concurrency Opsi 1 — Producer-Consumer Pipeline di `migrate_table`

**Date:** 2026-04-27
**Branch:** `python`
**Scope:** `pysync_maria/db/engine.py` (+ modul baru `pysync_maria/workers/pipeline.py`)
**Status:** Proposal — belum diimplementasi

---

## Ringkasan

`migrate_table()` saat ini berjalan sepenuhnya **sequential** di dalam
satu thread (lihat `engine.py:155`). Loop melakukan `fetchmany` dari
source → `executemany` ke target → `commit` secara berurutan; selama
target sedang menulis, koneksi source idle, dan sebaliknya.

Proposal ini menambahkan satu lapisan paralelisme paling ringan:
**dua thread saling overlap melalui `queue.Queue`**.

- **Producer thread** — membaca batch dari source (`stream_table`).
- **Consumer thread** — menulis batch ke target (`write_batch` +
  `commit`) dan memanggil `on_batch_done`.
- **Antrian terbatas** — `queue.Queue(maxsize=N)` memberikan
  back-pressure: producer berhenti saat consumer lambat, sebaliknya.

Tujuan: meng-overlap I/O source dan target tanpa mengubah API publik
`migrate_table()`, tanpa membuka beberapa koneksi target, dan tanpa
mengubah arsitektur Textual worker yang sudah ada.

---

## Tujuan & Non-Tujuan

### Tujuan
- Throughput migrasi naik untuk tabel besar dengan latency tulis target
  yang material (umumnya 1.3–2× pada batch 5k+ rows; tergantung rasio
  waktu read vs write).
- API publik `migrate_table()` dan kontrak `BatchResult` /
  `MigrationResult` **tidak berubah**.
- Mekanisme `cancel_event` / `pause_event` tetap berfungsi.
- Kompatibel dengan Textual `@work(thread=True)` di `MigrationScreen`.

### Non-Tujuan
- Tidak menambah multiple writer thread (itu Opsi 2).
- Tidak memparalelkan migrasi antar tabel (itu Opsi 3).
- Tidak mengganti `mysql-connector-python` dengan async driver.
- Tidak menyentuh logika retry/backoff `_retry.py` selain memastikan
  ia tetap dipanggil di consumer thread.

---

## Desain

### Modul Baru: `pysync_maria/workers/pipeline.py`

Folder `workers/` saat ini kosong (lihat `audit-2026-04-26.md`). Folder
ini sudah disiapkan oleh fase 6 namun tidak terpakai — modul pipeline
ini akan menjadi penghuni pertamanya.

```
pysync_maria/workers/pipeline.py
  └── run_pipeline(
        src_cursor, tgt_conn,
        table, source_cols, target_cols,
        mode, batch_size, dry_run,
        on_batch_done, cancel_event, pause_event,
        queue_size=2,
      ) -> tuple[int, int, int, list[str]]
        # returns (total_rows_read, total_rows_written,
        #          total_batches, errors_per_batch)
```

`run_pipeline` adalah inti producer-consumer. `migrate_table()` di
`engine.py` akan dipersempit menjadi orchestrator tipis yang
mempersiapkan kolom, memanggil `run_pipeline`, lalu mengisi
`MigrationResult`.

### Sentinel & Antrian

```python
SENTINEL = object()  # ditaruh oleh producer setelah batch terakhir

q: queue.Queue[list[tuple] | object] = queue.Queue(maxsize=queue_size)
```

`maxsize=2` cukup: satu batch sedang di-write, satu menunggu, producer
akan menambahkan batch ketiga begitu salah satu tervakum. Nilai ini
dapat dikonfigurasi tetapi default kecil sengaja: memori tambahan =
`maxsize × batch_size × avg_row_bytes`.

### Skema Thread

```
producer_thread (daemon=True)
  ├─ loop stream_table(src_cursor, ...)
  │    ├─ cek cancel_event → break
  │    ├─ pause_event.wait()
  │    └─ q.put(batch)              ← blok bila queue penuh (back-pressure)
  └─ q.put(SENTINEL)                ← tanda EOF

consumer_thread (running di thread pemanggil migrate_table)
  ├─ loop q.get()
  │    ├─ batch == SENTINEL → break
  │    ├─ cek cancel_event → drain & break
  │    ├─ retry_with_backoff(write_batch + commit)
  │    └─ on_batch_done(BatchResult(...))
  └─ join producer
```

**Mengapa consumer tetap di thread pemanggil?** Agar Textual worker
(`@work(thread=True)` di `MigrationScreen`) tidak melihat thread
tambahan yang tidak dimilikinya. Producer yang dipindahkan ke daemon
thread baru — itu yang "menghilang" begitu `migrate_table` selesai.
Pendekatan ini menghindari kebutuhan koordinasi tambahan dengan
runtime Textual.

### Penanganan `cancel_event`

Kanal pembatalan harus benar di **dua titik**:

1. **Producer** memeriksa `cancel_event.is_set()` setiap iterasi
   `fetchmany`, lalu `q.put(SENTINEL)` dan exit. Tanpa SENTINEL,
   consumer akan menunggu selamanya.
2. **Consumer** memeriksa `cancel_event.is_set()` setelah `q.get()`.
   Jika di-set, consumer **drain** sisa queue (tanpa menulis), tunggu
   producer selesai (`producer_thread.join(timeout)`), lalu rollback
   transaksi target dan return.

Karena `q.put` bisa blok, producer yang di-cancel saat queue penuh
perlu pakai `q.put(batch, timeout=0.5)` di dalam loop yang juga
memeriksa `cancel_event` — jangan `q.put()` blocking tak terbatas.

### Penanganan `pause_event`

`pause_event.wait()` cukup di **producer** saja: bila producer
berhenti, queue mengering, consumer otomatis idle di `q.get()`.
Menambah `pause_event.wait()` di consumer akan menggandakan latency
resume tanpa manfaat.

### Penanganan Error

- Error **read** (di producer): tangkap exception di producer thread,
  simpan ke variabel `producer_exc`, lalu `q.put(SENTINEL)`. Consumer
  selesai, `migrate_table` me-`raise` ulang `producer_exc` agar masuk
  jalur `except` existing di `engine.py:223` (status="failed",
  rollback).
- Error **write** (di consumer): sudah di-handle oleh
  `retry_with_backoff` + try/except per batch. Tetap pertahankan
  perilaku "fail batch ini, lanjut ke batch berikutnya" — tidak perlu
  membatalkan pipeline kecuali user memang men-set `cancel_event`.

### Urutan Commit & `on_batch_done`

`on_batch_done` dipanggil dari **consumer thread**, sama seperti
sekarang dipanggil dari thread pemanggil `migrate_table`. Karena
`MigrationScreen.handle_batch_done` sudah memakai
`call_from_thread`, tidak ada perubahan kontrak threading dari sisi
UI.

`batch_number` dijaga monotonik dengan counter di consumer (bukan di
producer) — agar nomor batch sesuai urutan tulis, bukan urutan baca
(walaupun pada pipeline FIFO ini keduanya identik).

---

## Perubahan File

### `pysync_maria/workers/pipeline.py` (baru)
Implementasi `run_pipeline` seperti dijabarkan di atas. Tidak boleh
import dari `tui/` atau `textual` — modul ini murni I/O.

### `pysync_maria/db/engine.py`
- Tambah import `from ..workers.pipeline import run_pipeline`.
- Di `migrate_table()`, ganti blok `for batch_rows in stream_table(...)`
  (`engine.py:155`–`213`) dengan satu pemanggilan `run_pipeline()`.
- Pertahankan blok `try/except/finally` luar (`engine.py:154`,
  `engine.py:223`, `engine.py:239`) — pengelolaan `src_cursor`,
  rollback, dan `MigrationResult` finalization tetap di sini.
- Tambah parameter opsional `queue_size: int = 2` ke `migrate_table()`
  untuk eksperimen tuning. Default 2 = perilaku konservatif.

### `pysync_maria/workers/__init__.py`
- Ekspor `run_pipeline` agar lebih mudah diimport: `from .pipeline
  import run_pipeline`.

### Tidak diubah
- `pysync_maria/db/_retry.py`
- `pysync_maria/db/connection.py`
- `pysync_maria/tui/screens/migration_screen.py`
- API publik `migrate_table` (signature lama tetap kompatibel — hanya
  ada parameter opsional baru di akhir).

---

## Test Plan

1. **Unit — happy path.** Mock `src_cursor.fetchmany` mengembalikan 3
   batch lalu `[]`. Mock `tgt_conn.cursor().__enter__().executemany`.
   Verifikasi: jumlah `on_batch_done` = 3, `total_rows_written` benar,
   urutan `batch_number` 1,2,3.
2. **Unit — cancel di tengah.** Set `cancel_event` setelah batch ke-2
   dipublikasikan ke `on_batch_done`. Verifikasi: tidak ada batch
   ke-3 yang ditulis, `tgt_conn.rollback` dipanggil, producer thread
   ter-join (`is_alive() == False`).
3. **Unit — pause/resume.** Clear `pause_event` setelah batch 1.
   Verifikasi consumer idle (waktu antara batch 1 → 2 ≥ delay set).
   Set kembali `pause_event`, verifikasi batch 2 menyusul.
4. **Unit — write error retry.** `executemany` raise
   `mysql.connector.Error` dua kali lalu sukses. Verifikasi
   `on_retry` terpanggil, batch akhirnya success, error tidak masuk
   `MigrationResult.errors`.
5. **Unit — read error.** `fetchmany` raise di batch ke-2. Verifikasi
   `migrate_table` mengembalikan `status="failed"`, error tercatat,
   rollback dipanggil, producer thread tidak menggantung.
6. **Integrasi — DB nyata.** Tabel 50k rows pada dua MariaDB lokal.
   Bandingkan wall-clock vs branch sequential. Catat hasil di komentar
   PR (target ≥ 1.3× pada batch 5k).
7. **TUI smoke.** Jalankan migrasi via TUI, pastikan progress bar
   tetap inkremental, cancel button tetap responsif < 1 detik.

---

## Kelebihan

1. **Throughput naik tanpa menambah koneksi.** Source dan target
   tidak lagi saling menunggu. Untuk tabel di mana `executemany +
   commit` mengambil waktu setara dengan `fetchmany`, peningkatannya
   mendekati 2×.
2. **API publik tidak berubah.** `MigrationScreen` dan
   `migrate_table` callers tetap bekerja apa adanya. Risiko regresi
   pada UI kecil.
3. **Risiko data minimal.** Tetap satu writer, tetap urutan FIFO,
   tetap satu transaksi per batch — tidak ada deadlock baru, tidak
   ada interleaving commit antar batch.
4. **Back-pressure built-in.** `queue.Queue(maxsize)` menjaga
   memori bounded; tidak ada risiko producer membanjiri RAM saat
   target lambat.
5. **Cancellation tetap kooperatif.** Cancel event diperiksa di dua
   titik (producer dan consumer), dan SENTINEL menjamin tidak ada
   thread yang menggantung.
6. **Mempunyai rumah arsitektural.** Folder `workers/` yang selama
   ini kosong akhirnya terpakai sesuai niat awal di
   `plan/fase_6_worker_migration_screen.md`.

---

## Kekurangan

1. **Kompleksitas debugging meningkat.** Stack trace pada error
   producer kini melewati thread boundary; pesan error harus
   dipropagasi eksplisit (variabel `producer_exc` + re-raise di
   thread utama). Test #5 wajib ada untuk memastikan ini benar.
2. **Memori tambahan.** Hingga `maxsize × batch_size` rows menumpuk
   di queue. Pada `batch_size=5000` dan `maxsize=2`, ini ~10k rows
   tambahan di RAM. Untuk tabel dengan baris besar (BLOB, TEXT
   panjang), tuning `queue_size=1` mungkin diperlukan.
3. **Tidak menolong jika bottleneck murni di salah satu sisi.**
   Bila target sangat cepat dan source sangat lambat (atau
   sebaliknya), overlap tidak memberi banyak. Ekspektasi performa
   harus disesuaikan per tabel.
4. **`fetchmany` dan `commit` tidak lagi terjadi di thread yang
   sama.** Bila ada library state yang berasumsi single-thread per
   koneksi (mysql-connector-python sebenarnya thread-safe per
   koneksi terpisah, tapi **tidak** untuk satu koneksi dipakai dari
   dua thread), kita harus memastikan `src_conn` hanya dipakai
   producer dan `tgt_conn` hanya dipakai consumer. Ini ditegakkan
   oleh konvensi modul, bukan oleh tipe — dokumentasi inline wajib.
5. **Risiko leaked thread saat exception path tidak lengkap.** Jika
   consumer raise sebelum sempat drain queue, producer bisa blok di
   `q.put()` selamanya. Mitigasi: `finally` di consumer harus
   `cancel_event.set()` + drain queue + `producer_thread.join(
   timeout=...)`.
6. **`batch_number` urutan baca vs urutan tulis tampak identik di
   pipeline FIFO ini, tetapi bila kelak di-extend ke multi-writer
   (Opsi 2), urutan akan kacau.** Dokumentasikan invariant agar
   tidak menjadi jebakan saat upgrade berikutnya.
7. **Sulit di-cancel saat blocking SQL.** `executemany` panjang di
   consumer atau `fetchmany` panjang di producer tidak bisa
   diinterupsi murni dengan `Event`. Ini sudah merupakan keterbatasan
   yang sama seperti sequential, tetapi sekarang muncul di dua
   thread alih-alih satu — perceived cancel-latency bisa terasa
   lebih lama bila keduanya kebetulan blocking.

---

## Rencana Eksekusi (estimasi 1 sesi)

1. Tulis `pysync_maria/workers/pipeline.py` + ekspor di
   `__init__.py`.
2. Refactor `migrate_table()` di `engine.py` untuk memanggil
   `run_pipeline`. Hapus loop lama, pertahankan finalisasi
   `MigrationResult`.
3. Tulis 5 unit test dari Test Plan #1–5 (mock-based, tanpa DB
   nyata).
4. Jalankan test plan #6 (DB nyata) di lingkungan lokal,
   benchmarkan terhadap branch ini, catat angka di body PR.
5. Smoke test TUI #7.
6. Update `MEMORY.md` bila ada lesson-learned non-obvious dari
   benchmark (misalnya `queue_size` sweet spot untuk dataset
   tertentu).

---

## Referensi

- `pysync_maria/db/engine.py:121-246` — `migrate_table` saat ini.
- `pysync_maria/db/engine.py:155` — loop sequential yang akan
  digantikan.
- `plan/fase_6_worker_migration_screen.md:5,49` — niat awal modul
  `workers/`.
- `plan/audit-2026-04-26.md:251` — catatan bahwa engine blocking
  tidak punya hook cancellation; pipeline tidak menyembuhkan ini
  tetapi minimal tidak memperburuk.
- Python stdlib: `queue.Queue`, `threading.Thread`,
  `threading.Event`.
