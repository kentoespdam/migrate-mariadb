> **Peran:** Senior Backend Engineer & Database Architect (Expert in Go & MariaDB).
>
> **Konteks:** Saya membangun aplikasi CLI interaktif "MariaSync-Go" untuk migrasi data antar host MariaDB. Aplikasi ini meniru fungsionalitas visual Navicat tetapi berjalan di terminal (TUI).
>
> **Tugas:** Buatkan plan arsitektur teknis dan cuplikan logika (logic snippets) dengan format markdown kedalam folder `plan/` dalam Go yang mencakup:
> 1.  **Metadata & Discovery Module:** Logic untuk mengambil `information_schema.TABLES` dan `COLUMNS` dari Host A dan B, lalu melakukan perbandingan (*intersection*) kolom untuk auto-mapping.
> 2.  **TUI Interactive Selection:** Desain antarmuka menggunakan `bubbletea` yang memungkinkan user:
>     - Memilih tabel via *checkbox*.
>     - Masuk ke sub-menu "Mapping" untuk memetakan kolom secara manual (Optional).
>     - Memilih mekanisme konflik: **SKIP**, **OVERWRITE** (Replace), atau **UPDATE**.
> 3.  **Batch Migration Engine:**
>     - Implementasi `sql.Tx` untuk melakukan **Commit per N-baris** (configurable batch size).
>     - Penggunaan `INSERT ... ON DUPLICATE KEY UPDATE` untuk opsi *Update* atau `INSERT IGNORE` untuk opsi *Skip*.
> 4.  **Concurreny & Progress:** Menggunakan `worker pool` untuk memproses migrasi beberapa tabel sekaligus dengan pelacakan *progress bar* yang sinkron via *channel*.
>
> **Format Output:** Struktur *interface* Go, logika pemetaan kolom, dan contoh strategi *batching* yang aman dari *memory leak*.
>
> **Thought Process**
> 1. DECONSTRUCT: Goal, roles, routes, and Indonesian UX constraints.
> 2. DIAGNOSE: Map needs to existing codebase. Cross-reference memory index.
> 3. ARCHITECT (Plan Phase Only): Define file changes, state (URL vs Local), query keys, and RBAC gating.
> 4. PRESENT: Output in mandatory Markdown format.
> 5. CLARIFYING: Ask 2-3 targeted clarifying questions
---

### **Blueprint Arsitektur: "MariaSync-Go"**

#### **1. Modul Pemetaan (The Mapping Engine)**
Aplikasi akan melakukan *Auto-Discovery* dengan membandingkan kolom yang ada di Host A dan B.

| Fitur | Implementasi Teknis |
| :--- | :--- |
| **Auto-Mapping** | Mencari irisan (*intersection*) set kolom: `ColumnsA ∩ ColumnsB`. |
| **Custom Mapping** | Menggunakan `Map[string]string` di mana *Key* adalah kolom asal dan *Value* adalah kolom tujuan. |
| **Validation** | Cek tipe data. Jika kolom tujuan memiliki tipe data yang tidak kompatibel (misal: `VARCHAR` ke `INT`), berikan *warning*. |

#### **2. Mekanisme Konflik (Pre-Execution Choice)**
Sebelum tombol "Mulai" ditekan, user memilih strategi melalui menu TUI:
* **Skip:** Menggunakan `INSERT IGNORE INTO...`. Sangat cepat karena MariaDB akan mengabaikan error *duplicate key*.
* **Overwrite:** Menggunakan `REPLACE INTO...` atau `DELETE` lalu `INSERT`.
* **Update:** Menggunakan `INSERT ... ON DUPLICATE KEY UPDATE`. Paling aman untuk menjaga data eksis tetap sinkron.

#### **3. Engine Migrasi & Batching (The Worker)**
Untuk efisiensi memori dan meminimalkan bug, kita akan menggunakan **Fixed-Size Batching**.

```go
// Konsep Batching dengan sql.Tx
func migrateBatch(dbB *sql.DB, data []Records, batchSize int) error {
    tx, err := dbB.Begin()
    if err != nil {
        return err
    }
    
    // Menyiapkan statement bulk insert
    // INSERT INTO table (cols) VALUES (?,?), (?,?) ...
    stmt, err := tx.Prepare(buildBulkInsertQuery(len(data)))
    
    // Eksekusi N-baris
    _, err = stmt.Exec(flattenData(data)...)
    
    return tx.Commit() // Commit dilakukan per N-baris
}
```
---

### **Detail Antarmuka (Navicat-like TUI)**

Menggunakan **Bubble Tea**, aplikasi akan memiliki tiga fase layar:
1.  **Dashboard:** Tabel metadata (Nama Tabel | Baris | Ukuran | Status Skema).
2.  **Config:** Dialog interaktif untuk memilih *Batch Size* (misal: 1.000 atau 5.000 baris) dan *Conflict Strategy*.
3.  **Monitor:** Panel berisi *multi-progress bars* yang menunjukkan kecepatan transfer (rows/sec) per tabel.

### **Rules**
- NO SOURCE CODE: Write "how-to", not "the code".
- USE SKILL: use all available skill related this topic
- REUSE FIRST: Mandatory check of existing hooks (`usePagination`, `useQueryState`, etc.) in memory.
- LANGUAGE: All UI/Toast/Labels must be BAHASA INDONESIA.
- SPLIT FILE: split plan file based plan/task.
- USERS: This plan is for the basis of work by junior developers and small AI models. 