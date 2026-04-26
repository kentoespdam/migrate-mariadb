# Plan: Capture All Errors into Centralized Rotating Error Log

Tanggal: 2026-04-26
Branch: `python`

## Context

Saat ini logging PySync-Maria sudah menulis ke `logs/pysync.log` (INFO) dan `logs/error.log` (ERROR), namun cakupannya tidak lengkap dan ada beberapa kebocoran error yang tidak masuk ke file:

- `migration_screen.run_migration()` (worker thread) — exception hanya ditulis ke `RichLog` widget, tidak ke file (`pysync_maria/tui/screens/migration_screen.py:135-136`).
- `connection_screen.test_connection()` (worker thread) — exception hanya ditampilkan ke status label UI, tidak ke file (`pysync_maria/tui/screens/connection_screen.py:116-125`).
- `table_select_screen.fetch_and_open_mapping()` (async) — exception hanya `notify`, tidak ke file (`pysync_maria/tui/screens/table_select_screen.py:230-231`).
- `main.py` — error config/loader hanya `console.print`, tidak ke file (`pysync_maria/main.py:82-84`).
- Tidak ada hook global untuk uncaught exception di Python (`sys.excepthook`), thread (`threading.excepthook`), maupun asyncio loop. Bila Textual `on_error()` tidak ter-trigger, error bisa hilang.
- `error.log` tumbuh tanpa batas (tidak ada rotasi).
- Format error saat ini hanya `asctime/level/name/msg` — tanpa konteks (screen, table, batch) sehingga sulit di-debug.

Tujuan: pastikan **semua** error (terprediksi & tak terprediksi) dari seluruh modul (db, engine, TUI screens, async, worker thread, uncaught) tertangkap ke `logs/error.log` dengan stack trace lengkap + konteks yang berguna, dan file ber-rotasi otomatis agar tidak meledak.

## Recommended Approach

Sentralisasi error logging melalui satu modul `pysync_maria/logging_setup.py` yang:

1. Mengkonfigurasi root logger dengan **dua** `RotatingFileHandler` (info + error).
2. Memasang **global exception hooks** (`sys.excepthook`, `threading.excepthook`, asyncio loop handler).
3. Menyediakan helper `log_exception(logger, msg, exc, **context)` agar setiap call-site bisa menambahkan konteks (screen, table, batch_index, dsb.).

Lalu **wire** semua call-site yang sekarang masih senyap supaya memakai helper tersebut.

Pilihan user yang diterapkan:
- Lokasi log: tetap di `logs/error.log` (project root).
- Scope: **paling lengkap** — global hooks (sys/thread/asyncio) + wire semua gap.
- Rotasi: aktif (`RotatingFileHandler`, 5 MB × 5 backup).
- Format: stack trace lengkap + konteks (modul, screen, table).

## Files to Modify / Create

### 1. NEW — `pysync_maria/logging_setup.py`

Modul baru, dipanggil sekali di `main.py` sebelum app start.

Isi inti:
- `LOG_DIR = Path("logs")`.
- Format detail untuk error:
  `"%(asctime)s [%(levelname)s] %(name)s [%(threadName)s] %(module)s:%(lineno)d :: %(message)s"`
- `setup_logging()`:
  - Root logger di-set ke `INFO`.
  - `RotatingFileHandler(logs/pysync.log, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")` → INFO.
  - `RotatingFileHandler(logs/error.log, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")` → ERROR.
  - `sys.excepthook = _handle_uncaught` → `logging.getLogger("pysync_maria.uncaught").critical(..., exc_info=...)`.
  - `threading.excepthook = _handle_thread_exc` (Python 3.8+) → log dengan thread name di context.
  - Expose `attach_asyncio_handler(loop)` yang memanggil `loop.set_exception_handler(...)`; dipanggil dari `PySyncMariaApp.on_mount()` karena loop dibuat saat `app.run()`.
- `log_exception(logger, msg: str, exc: BaseException | None = None, **context)`:
  - `logger.error("%s | ctx=%r", msg, context, exc_info=exc or True)`.

### 2. MODIFY — `pysync_maria/tui/app.py`

- Hapus blok `_setup_logging()` (lines 31-50). Logging dilakukan di `main.py` sekarang.
- `__init__`: cukup `self.logger = logging.getLogger("pysync_maria")`.
- `on_mount()`: panggil `attach_asyncio_handler(asyncio.get_running_loop())` dari `logging_setup`.
- `on_error(event)`: gunakan `log_exception(self.logger, "Textual on_error", event.exception, screen=str(self.screen))` lalu `self.notify(...)`.

### 3. MODIFY — `pysync_maria/main.py`

- Sebelum `try:` di `main()`, panggil `from .logging_setup import setup_logging; setup_logging()`.
- Di `except Exception as e` (line 82-84): tambahkan `log_exception(logging.getLogger("pysync_maria.bootstrap"), "Failed to start app", e, source=str(source), target=str(target))` sebelum `console.print` & `typer.Exit(1)`.

### 4. MODIFY — `pysync_maria/tui/screens/migration_screen.py`

Pada `run_migration()` line 135-136 (try/except utama):

```python
except Exception as e:
    from ...logging_setup import log_exception
    log_exception(
        logging.getLogger("pysync_maria.migration"),
        "run_migration crashed",
        e,
        screen="MigrationScreen",
        tables=[t.name for t in self.selected_tables],
        completed=self.tables_completed,
    )
    self.app.call_from_thread(self.log_info, f"[bold red]Critical Error: {e}[/]")
```

Juga pada `action_export_log()` line 215-216 — tambahkan `log_exception(...)` sebelum `notify`.

### 5. MODIFY — `pysync_maria/tui/screens/connection_screen.py`

Pada `test_connection()` line 116-125: tambahkan
`log_exception(logging.getLogger("pysync_maria.connection"), "Test connection failed", e, form_id=form.id, host=form.query_one('#host', Input).value)`
sebelum `mark_failed`/`update_status`. Tidak menampilkan stack trace ke UI — UI tetap singkat.

### 6. MODIFY — `pysync_maria/tui/screens/table_select_screen.py`

- `load_metadata()` line 97-99: ganti `self.app.logger.exception(...)` menjadi `log_exception(..., screen="TableSelectScreen", phase="load_metadata")`.
- `fetch_and_open_mapping()` line 230-231: tambahkan `log_exception(..., table=table_name)` sebelum `notify`.

### 7. MODIFY — `pysync_maria/db/connection.py`

Pada kedua handler `mysql.connector.Error` (line 38-39 dan 74-75): sebelum `raise ConnectionError(...) from err`, panggil
`log_exception(logging.getLogger("pysync_maria.db.connection"), "MariaDB connect failed", err, host=config.host, db=config.database, streaming=<True/False>)`.
Tetap re-raise — caller tetap dapat exception.

### 8. (Opsional, low risk) MODIFY — `pysync_maria/db/engine.py`

Sudah memakai `logger.exception()` di line 212. Tambahkan context via `extra={...}` atau ganti ke `log_exception(... table=table, batch_index=...)` agar konsisten format.

## Reusable Functions / Patterns Found

- `pysync_maria/db/_retry.py:9` sudah punya `logger = logging.getLogger("pysync_maria.db.retry")` dan pola `on_retry` callback — pertahankan, namespace logger akan otomatis ikut handler root.
- `pysync_maria/db/engine.py:14` sudah `logger = logging.getLogger("pysync_maria.engine")` dan memakai `logger.exception()` — sudah benar; cukup tambah konteks.
- Pola `log_exception` cukup tipis (≈10 baris) — tidak overengineering, hanya standardisasi format konteks.

## Verification

1. **Smoke test logging** — `python -c "from pysync_maria.logging_setup import setup_logging; setup_logging(); raise RuntimeError('boom')"` → cek `logs/error.log` mengandung stack trace `RuntimeError: boom`.
2. **Thread excepthook** — script pendek yang `threading.Thread(target=lambda: 1/0).start()` → cek `error.log` mencatat `ZeroDivisionError` dengan thread name.
3. **Connection failure** — set `.env.source` dengan host invalid, jalankan TUI, klik Test Connection → status label merah di UI dan `logs/error.log` punya entry `MariaDB connect failed | ctx={'host': ..., 'db': ..., 'streaming': False}` lengkap dengan stack trace.
4. **Migration failure** — sediakan target tanpa tabel, mulai migrasi → `error.log` punya entry `run_migration crashed` dengan list tables dan stack trace.
5. **Rotation** — set sementara `maxBytes=1024` di `setup_logging()` lokal, generate banyak error → cek `logs/error.log.1`, `error.log.2`, dst. terbentuk lalu kembalikan ke 5 MB.
6. **Pytest** — `pytest tests/` untuk memastikan tidak ada regresi pada engine tests (`test_engine.py`, `test_engine_failure.py`, `test_engine_cancel.py`).
7. **Manual happy-path** — alur connect → table select → migrate sampai selesai; pastikan `logs/error.log` tidak bertambah saat happy path (tidak ada false positive).

## Out of Scope

- Tidak memindah lokasi log ke `~/.pysync-maria/` (user memilih tetap `logs/`).
- Tidak menambah TUI screen/panel untuk view error log (cukup tail file dari shell).
- Tidak mengubah skema export migrasi di `~/.pysync-maria/exports/` (fitur terpisah).
