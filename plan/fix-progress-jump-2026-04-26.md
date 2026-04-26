# Fix: Progress Bar Tidak Update Inkremental, Loncat ke Selesai

**Date:** 2026-04-26
**Branch:** `python`
**Auditor:** Senior Lead Engineer & Database Integrity Auditor
**Standard:** Ruff / PEP8

---

## Ringkasan

Pengguna melaporkan bahwa pada `MigrationScreen` progress bar (current
table dan/atau overall) tidak bergerak selama proses berjalan, lalu
"tiba-tiba" tampil sudah selesai. Audit menemukan **3 root cause yang
berdiri sendiri** dan saling memperkuat ilusi tersebut. Semua perbaikan
bersifat lokal di `pysync_maria/db/engine.py`,
`pysync_maria/db/connection.py`, dan
`pysync_maria/tui/screens/migration_screen.py`.

Rincian per-bug menggunakan format **Symptom -> Root Cause -> Proposed
Fix**.

---

## Bug #1 — `total` ProgressBar memakai estimasi `TABLE_ROWS` InnoDB

### Symptom
- Progress bar `current-progress` saturasi di tengah jalan (langsung
  100%) padahal data masih mengalir, atau
- Bar diam di < 100% lalu langsung lompat ke `Migration completed!`
  tanpa pernah mencapai akhir.
- Stat "Speed/ETA" terlihat absurd (ETA negatif atau melonjak).

### Root Cause
`pysync_maria/db/metadata.py:69` mengisi `TableInfo.row_count` dari
`information_schema.TABLES.TABLE_ROWS`. Untuk engine **InnoDB**, kolom
ini adalah **estimasi statistik** (sample-based), bukan jumlah nyata —
deviasi 30–90% adalah hal lumrah, dan untuk tabel kecil sering bernilai
`0`.

Nilai estimasi ini lalu dipakai langsung sebagai `total` ProgressBar:

```python
# migration_screen.py:161
self.query_one("#current-progress").update(total=table.row_count, progress=0)
```

…dan sebagai denominator `total_rows` untuk ETA:

```python
# migration_screen.py:41
self.total_rows = sum(t.row_count for t in selected_tables)
```

Akibatnya:
- Jika estimasi terlalu kecil → `advance(rows_read)` melewati `total`
  dengan cepat, bar mentok → **terlihat "selesai" padahal belum**.
- Jika estimasi terlalu besar → bar tidak pernah penuh, lalu loop
  selesai dan `all_done()` dipanggil → **terlihat "loncat ke selesai"**.
- Jika estimasi `0` (tabel baru / belum di-`ANALYZE`) → bar diam di 0%
  selama seluruh durasi.

### Proposed Fix (Standard: Ruff/PEP8)

**A. Mode "indeterminate" untuk total yang tidak dapat dipercaya.**
Lakukan `COUNT(*)` real-time *sekali* per tabel sebelum streaming
dimulai (sebagai job ringan di worker thread), lalu set sebagai `total`.
Untuk tabel sangat besar, fallback ke `total=None` (Textual ProgressBar
akan menjadi pulse/indeterminate) dan gunakan `rows_read` sebagai
`progress` mentah pada label tekstual.

**B. Pisahkan estimasi ETA dari progress bar.** ETA boleh memakai
estimasi total; ProgressBar tidak boleh.

**C. Tambah `update(total=actual)` setelah migrasi tabel selesai** untuk
menutup gap visual ketika `rows_read != estimasi`.

**Patch sketch (`engine.py` — tambah hitungan eksak):**

```python
def count_rows(conn: Any, table: str, where_clause: str | None = None) -> int:
    """Exact row count. Use sparingly; cheaper than re-streaming."""
    sql = f"SELECT COUNT(*) FROM `{table}`"
    if where_clause:
        sql += f" WHERE {where_clause}"
    with conn.cursor() as cur:
        cur.execute(sql)
        (n,) = cur.fetchone()
    return int(n)
```

**Patch sketch (`migration_screen.py` — `prepare_table` + worker):**

```python
def prepare_table(self, table: TableInfo, exact_rows: int | None, index: int) -> None:
    label = self.query_one("#current-table-label", Label)
    label.update(f"Current Table: [bold]{table.name}[/]")
    pb = self.query_one("#current-progress", ProgressBar)
    pb.update(total=exact_rows, progress=0)  # None -> indeterminate
    self.log_info(
        f"\u25B6\uFE0F Processing [cyan]{table.name}[/] "
        f"({(exact_rows if exact_rows is not None else table.row_count):,} rows)\u2026"
    )
```

Lalu di worker:

```python
exact = count_rows(src_conn, table.name)  # cheap dedicated cursor
self.app.call_from_thread(self.prepare_table, table, exact, i)
```

---

## Bug #2 — Cursor unbuffered "yatim" di `get_streaming_connection`

### Symptom
- Pada beberapa kondisi (terutama tabel pertama), batch pertama tidak
  pernah datang; user hanya melihat header lalu pesan completion.
- Log menampilkan `Unread result found` atau koneksi reset di tengah
  migrasi pada multi-table run.

### Root Cause
`pysync_maria/db/connection.py:80` membuat sebuah unbuffered cursor lalu
mengembalikan tuple `(cnx, cursor)`:

```python
cursor = cnx.cursor(buffered=False)
yield cnx, cursor
```

`migration_screen.py:97` membuangnya (`with ... as (src_conn, _):`) dan
`engine.py:137` membuat **cursor unbuffered kedua** pada koneksi yang
sama:

```python
src_cursor = src_conn.cursor(buffered=False)
```

`mysql-connector-python` melarang dua cursor unbuffered aktif pada satu
koneksi: jika cursor pertama tidak ditutup tepat waktu, cursor kedua
melempar `InternalError: Unread result found` atau memblokir hingga
timeout. Error tersebut **tertangkap** oleh blok `except Exception` di
`engine.py:209` → `res.status = "failed"` → loop berlanjut ke tabel
berikutnya tanpa progress event apapun → user melihat "loncat ke
selesai".

### Proposed Fix (Standard: Ruff/PEP8)
Hapus pembuatan cursor di `get_streaming_connection`; biarkan engine
yang **memiliki** lifecycle cursor (sudah konsisten dengan komentar
`E1: SSCursor ownership` di `engine.py:135`).

```python
@contextmanager
def get_streaming_connection(config: HostConfig):
    """Streaming-capable connection. Engine owns the cursor."""
    cnx = None
    try:
        cnx = mysql.connector.connect(
            host=config.host, port=config.port,
            user=config.user, password=config.password.get_secret_value(),
            database=config.database, charset=config.charset,
            collation=config.collation, connect_timeout=config.connect_timeout,
            use_pure=True,
        )
        if not cnx.is_connected():
            raise ConnectionError(f"Failed to connect to {config.host} (Streaming)")
        cnx.ping(reconnect=True, attempts=3, delay=1)
        yield cnx
    except mysql.connector.Error as err:
        # …existing logging…
        raise ConnectionError(...) from err
    finally:
        if cnx and cnx.is_connected():
            cnx.close()
```

Update call-site:

```python
# migration_screen.py
with get_streaming_connection(self.app.source_config) as src_conn:
    with get_connection(self.app.target_config) as tgt_conn:
        ...
```

---

## Bug #3 — Eksepsi di `_update_ui_batch` membungkam progress events

### Symptom
- Worker selesai sukses, tapi ProgressBar tidak pernah maju, hanya
  log `[bold]X[/] finished: N rows` yang muncul di akhir.
- Tidak ada error yang terlihat di TUI; di `logs/error.log` mungkin
  ditemukan `KeyError` / `NoMatches` jika sempat tercatat.

### Root Cause
`migration_screen.py:165` melakukan
`self.query_one("#current-progress", ProgressBar)` *di setiap batch*.
Jika batch pertama dipancarkan **sebelum** `compose()` selesai mounting
(race window pendek antara `on_mount` → `run_migration()` →
`call_from_thread(prepare_table, …)`), `query_one` melempar `NoMatches`.
Karena `_update_ui_batch` dipanggil via `call_from_thread` yang
**mengonsumsi exception secara diam-diam**, semua update UI berikutnya
juga gagal in-flight tanpa pesan ke user.

Kombinasi kedua: pemanggilan
`progressbar.advance(batch.rows_read)` mengabaikan kasus
`pb.total is None` → di Textual ≥0.80 advance pada total None malah
me-reset progress ke `pulse` mode setiap kali → terlihat "diam".

### Proposed Fix (Standard: Ruff/PEP8)

1. Cache widget references di `on_mount` setelah `compose` selesai,
   bukan `query_one` per batch.
2. Bungkus `_update_ui_batch` dengan guard eksplisit dan log via
   `log_exception` agar kegagalan UI **terlihat**, bukan hilang.
3. Tangani `total is None` dengan `update(progress=...)` absolut bukan
   `advance(...)`.

```python
def on_mount(self) -> None:
    self._pb_current = self.query_one("#current-progress", ProgressBar)
    self._pb_overall = self.query_one("#overall-progress", ProgressBar)
    self._lbl_speed = self.query_one("#speed-label", Label)
    self._lbl_elapsed = self.query_one("#elapsed-label", Label)
    self._lbl_eta = self.query_one("#eta-label", Label)
    self.log_info(f"Starting migration for {len(self.selected_tables)} tables\u2026")
    if self.dry_run:
        self.log_info("[yellow]DRY RUN MODE ENABLED[/]")
    self.start_time = time.time()
    self.run_migration()

def _update_ui_batch(self, batch: BatchResult) -> None:
    try:
        self.rows_completed += batch.rows_read
        if self._pb_current.total is None:
            self._pb_current.update(progress=self.rows_completed_in_table)
        else:
            self._pb_current.advance(batch.rows_read)
        elapsed = time.time() - self.start_time
        speed = self.rows_completed / elapsed if elapsed > 0 else 0
        self._lbl_speed.update(f"Speed: {int(speed):,} rows/s")
        self._lbl_elapsed.update(
            f"Elapsed: {timedelta(seconds=int(elapsed))!s}"
        )
        remaining = max(self.total_rows - self.rows_completed, 0)
        eta = remaining / speed if speed > 0 else 0
        self._lbl_eta.update(f"ETA: {timedelta(seconds=int(eta))!s}")
    except Exception as e:
        from ..logging_setup import log_exception
        import logging
        log_exception(
            logging.getLogger("pysync_maria.tui.migration"),
            "UI batch update failed", e, batch=batch.batch_number,
        )
```

Tambahan: tambahkan atribut `self.rows_completed_in_table` yang di-reset
di `prepare_table` agar mode indeterminate tetap menampilkan progress
per-tabel.

---

## Architecture Decisions

### AD-1 — Engine memiliki seluruh lifecycle cursor sumber
Konsisten dengan komentar `E1: SSCursor ownership` yang sudah ada di
`engine.py`. `get_streaming_connection` **hanya** mengembalikan
`Connection` yang siap-streaming (use_pure=True, ping ok). Tidak ada
pembuatan cursor di context manager koneksi. Ini menutup seluruh kelas
bug "dual unbuffered cursor on one connection".

### AD-2 — Estimasi vs. eksak: dua sumber kebenaran
- `TableInfo.row_count` (estimasi InnoDB) → hanya untuk **ringkasan UI
  pre-flight** (Confirm Modal, total awal), bukan untuk progres
  realtime.
- `count_rows()` eksak → sumber kebenaran untuk `total` ProgressBar dan
  ETA per-tabel saat migrasi berjalan.

Trade-off: tambahan `SELECT COUNT(*)` per tabel. Untuk 99% tabel
overhead < 1 detik. Untuk tabel sangat besar, biaya tetap lebih murah
daripada mis-progress yang membingungkan operator.

### AD-3 — UI updates wajib terobservasi
Semua callback dari worker thread ke UI **harus** dibungkus error handler
yang mencatat ke `logs/error.log` via `log_exception`. Diam-diam
menelan eksepsi UI adalah anti-pola yang langsung menyebabkan kelas bug
"progress hilang" (lihat Bug #3). Tambahkan helper
`MigrationScreen._safe_ui(fn, *args)` jika pola ini berulang.

### AD-4 — Tidak ada refactor total
Tiga bug di atas dapat diselesaikan tanpa membongkar arsitektur worker
atau memperkenalkan async — semua dalam ruang lingkup edit lokal.
Refactor ke `asyncio` / `aiomysql` ditolak untuk PR ini karena di luar
cakupan dan akan memperluas blast radius.

---

## Test Plan

1. **Reproduksi**: tabel InnoDB 1 juta baris yang `TABLE_ROWS = 0`
   (baru di-`TRUNCATE`) → migrasi → bar harus bergerak inkremental.
2. **Tabel kosong** (0 baris real, estimasi 0) → bar langsung 100% +
   log "0 rows", tanpa ETA NaN.
3. **Multi-table run**, tabel ke-2 berukuran besar → cursor dari tabel
   ke-1 sudah closed sebelum tabel ke-2 mulai (bukti tidak ada
   "Unread result").
4. **Dry-run** → `rows_written=0` per batch tapi `rows_read` tetap
   memajukan bar.
5. **Cancel di tengah tabel** → bar berhenti di posisi terakhir,
   bukan loncat ke 100%.
6. Tambah unit test di `tests/test_engine.py` yang memverifikasi
   `on_batch_done` dipanggil **setidaknya `ceil(rows/batch_size)`**
   kali, dengan total `rows_read` == jumlah baris.

---

## File yang Disentuh

- `pysync_maria/db/engine.py` — tambah `count_rows()`.
- `pysync_maria/db/connection.py` — `get_streaming_connection` tidak
  lagi membuat cursor.
- `pysync_maria/tui/screens/migration_screen.py` — cache widget refs,
  guarded UI updates, gunakan eksak count untuk total.
- `tests/test_engine.py` — test progres event count.

Tidak ada perubahan di `metadata.py`, `_retry.py`, atau modal lain.
