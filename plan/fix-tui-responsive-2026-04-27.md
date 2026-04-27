# Fix: TUI Connection Screen Responsiveness

**Date:** 2026-04-27
**Scope:** `pysync_maria/tui/screens/connection_screen.py`, `pysync_maria/tui/app.tcss`

---

## Symptom

Pada terminal dengan tinggi terbatas (mis. < 28 baris), tombol **Test Connection**
dan label **Status** di dalam `HostConnectionForm` ter-clip / tidak terlihat.
User tidak bisa melakukan tes koneksi karena tombol tertimpa Footer atau
ter-overflow di luar area Screen. Tombol **Connect & Proceed** juga rawan hilang
karena dirender di luar `Container` kolom.

## Root Cause

1. **Tidak ada container scrollable.** `ConnectionScreen.compose` membungkus
   form dalam `Container(), Horizontal()` tanpa `overflow-y: auto`. Saat tinggi
   konten (5 Input × `margin: 1 0` + Label + Button + Status) melebihi tinggi
   Screen, Textual meng-clip widget paling bawah (Button + Status) alih-alih
   mengaktifkan scroll.
2. **Margin Input boros vertikal.** Aturan global `Input { margin: 1 0; }`
   menambahkan 2 baris per Input × 5 Input = 10 baris hanya untuk margin —
   memperburuk overflow di layar pendek.
3. **Layout `.button-row` kaku.** `height: 3` fixed pada `.button-row`, tanpa
   `min-height`/`dock`, sehingga ketika ruang habis tombol tidak punya prioritas
   visibilitas dan ikut ter-clip.
4. **Tombol Connect di-render di luar kolom** namun tidak di-`dock: bottom`,
   sehingga posisinya bergantung pada sisa ruang yang sudah habis dipakai form.
5. **`.connection-column` `border: tall`** memakan 2 baris ekstra per kolom.
   `tall` border bagus secara estetika tetapi memperparah masalah pada layar
   pendek.

## Proposed Fix (Standard: Ruff/PEP8)

### 1. `app.tcss` — buat layout responsif

```tcss
/* Connection Screen: kolom form harus bisa scroll bila layar pendek */
.connection-column {
    width: 50%;
    padding: 0 2;          /* hilangkan padding vertikal: hemat 2 baris */
    border: round $secondary;  /* round = 0 baris vs tall = 2 baris */
    overflow-y: auto;      /* aktifkan scroll vertikal per-kolom */
    height: 1fr;           /* isi sisa ruang Screen */
}

Input {
    margin: 0 0 1 0;       /* 1 baris margin bawah saja, hemat 5 baris */
}

.column-title {
    text-style: bold;
    margin-bottom: 1;
    content-align: center middle;
    height: 1;
}

.button-row {
    height: auto;          /* biarkan button-row mengikuti konten */
    min-height: 3;
    content-align: center middle;
    margin-top: 1;
}

/* Tombol global Connect & Proceed: dock di bawah Screen agar selalu visible */
#connect-btn-row {
    dock: bottom;
    height: 3;
    background: $surface-darken-1;
    content-align: center middle;
}
```

### 2. `connection_screen.py` — strukturkan ulang `compose`

- Bungkus dua `HostConnectionForm` dengan `Horizontal` yang di-set
  `height: 1fr` agar mengambil sisa ruang setelah header/title/footer.
- Pindahkan `Horizontal(... id="connect-btn-row")` ke level Screen dan beri
  id agar bisa di-dock di CSS.
- Title `#connection-title` turunkan `height: 3` → `height: 1` dan `margin: 0`
  untuk hemat 4 baris vertikal.

```python
def compose(self) -> ComposeResult:
    yield Header()
    yield Label("Connection Setup", id="connection-title")

    with Horizontal(id="forms-row"):
        yield HostConnectionForm("SOURCE (HOST A)", self.app.source_config, id="source-form")
        yield HostConnectionForm("TARGET (HOST B)", self.app.target_config, id="target-form")

    with Horizontal(id="connect-btn-row"):
        yield Button("Connect & Proceed →", variant="success",
                     id="connect-btn", disabled=True)

    yield Footer()
```

Tambah CSS:

```tcss
#forms-row { height: 1fr; }
#connection-title { height: 1; margin: 0; }
```

### 3. Verifikasi

- Jalankan TUI di terminal 80×20 dan 80×40; pastikan tombol Test Connection
  dan Connect & Proceed selalu terlihat (scroll bila perlu).
- Jalankan `ruff check pysync_maria/tui/screens/connection_screen.py`.
- Jalankan test suite `pytest tests/` untuk regresi.

---

## Architecture Decisions

Tidak diperlukan refactor besar. Masalah murni layout/CSS:

- **Tetap pakai `HostConnectionForm` sebagai `Vertical`.** Tidak perlu
  `ScrollableContainer` di level form karena dengan `overflow-y: auto` pada
  `.connection-column` Textual otomatis menyediakan scrollbar internal.
- **Dock-bottom untuk action button** adalah pola standar Textual (lihat
  `migration_screen` yang juga memakai dock untuk progress section). Pola ini
  menjamin aksi utama selalu reachable terlepas dari tinggi terminal —
  prinsip yang sama harus diterapkan ke screen lain bila muncul gejala serupa.
- **Tidak menambah breakpoint manual** (`$layout.height < N`) karena Textual
  belum mendukung media query; cukup andalkan `1fr` + `auto` + `overflow`
  untuk perilaku adaptif.
