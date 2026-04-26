# PySync-Maria

PySync-Maria is an interactive, high-performance TUI application for migrating data between MariaDB/MySQL hosts. Designed for safety and efficiency, it supports memory-safe streaming for large datasets and granular control over table selection and column mapping.

## ✨ Features

- **Interactive TUI**: Built with Textual for a modern terminal experience.
- **Memory Safe**: Uses `SSCursor` (unbuffered streaming) to handle millions of rows without RAM bloat.
- **Dry Run Mode**: Simulate migrations to verify schema compatibility and estimated row counts.
- **Custom Mapping**: Map source columns to target columns or skip them entirely.
- **Write Modes**: Supports `REPLACE INTO`, `ON DUPLICATE KEY UPDATE`, and `INSERT IGNORE`.
- **Resilient**: Automatic retries with exponential backoff for connection errors.
- **Relational Integrity**: Automatically sorts tables based on foreign key dependencies.

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- `uv` (recommended) or `pip`

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/migrate-mariadb.git
cd migrate-mariadb

# Install dependencies
uv sync
```

### Configuration

Create a `.env` file based on `.env.example`:

```env
SOURCE_HOST=localhost
SOURCE_USER=root
SOURCE_PASS=your_password
SOURCE_DB=source_db

TARGET_HOST=remote_host
TARGET_USER=root
TARGET_PASS=remote_password
TARGET_DB=target_db

DRY_RUN=true
BATCH_SIZE=5000
```

## 🛠️ Usage

Simply run the application:

```bash
uv run pysync-maria
```

### Keyboard Shortcuts

| Key | Action |
| --- | --- |
| `Q` | Quit Application |
| `?` / `F1` | Show Help |
| `D` | Toggle Dry Run Mode |
| `Space` | Toggle Table Selection |
| `A` | Select All / Deselect All |
| `M` | Open Custom Mapping Modal |
| `R` | Reload Table Metadata |
| `P` | Pause / Resume Migration |
| `C` | Cancel Active Migration |
| `E` | Export Migration Log |

## 🧪 Testing

Run the comprehensive test suite:

```bash
uv run pytest tests/ -v
```

## 📁 Logging

Logs are stored in `~/.pysync-maria/pysync.log`.
Migration reports are exported to `~/.pysync-maria/exports/`.

## 📄 License

MIT
