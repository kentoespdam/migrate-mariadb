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

The application requires two configuration files (or one combined `.env`). By default, it looks for `.env.source` and `.env.target`.

#### 1. Source Host Configuration (`.env.source`)
Create a file named `.env.source` with the following variables:
```env
SOURCE__HOST=127.0.0.1
SOURCE__USER=root
SOURCE__PASSWORD=your_password
SOURCE__DATABASE=source_database
SOURCE__PORT=3306
```

#### 2. Target Host Configuration (`.env.target`)
Create a file named `.env.target` with the following variables:
```env
TARGET__HOST=remote_host
TARGET__USER=db_user
TARGET__PASSWORD=db_password
TARGET__DATABASE=target_database
TARGET__PORT=3306
```

> [!NOTE]
> You can also specify common settings like `DRY_RUN=true` and `BATCH_SIZE=5000` in either file or the main `.env`.

## 🛠️ Usage

### Running the App
You can run the application using `uv` (recommended) or direct python command:

```bash
# Default mode (looks for .env.source and .env.target)
uv run pysync-maria

# Specify custom config files
uv run pysync-maria --source production.env --target backup.env

# Enable Dry Run via CLI
uv run pysync-maria --dry-run
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
