# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MDB2SQL is a tool for converting Microsoft Access databases (MDB/ACCDB) to DuckDB format with a Flask-based web interface for fuzzy searching and managing converted databases. The system supports both offline DuckDB search (fast, with fulltext index) and online Access ODBC search (slower fallback).

## Core Architecture

### Conversion Layer (Multiple Implementations)

The project provides **four independent converter implementations**, each with different dependencies and performance characteristics (see README.md for benchmarks):

1. **convert_mdbtools.py** - Uses mdbtools CLI via subprocess (fastest: ~54s/file)
2. **convert_jackcess.py** - Uses Jackcess Java library (most reliable: ~253s/file, cross-platform)
3. **convert_pyaccess_parser.py** - Pure Python using access-parser (~165s/file, no external deps)
4. **convert_pyodbc.py** - Uses pypyodbc/ODBC (Windows-only, requires Access Database Engine)

**Shared conversion pattern** (all implementations):
- Extract date from filename using patterns: `DD_MM_YYYY`, `YYYY-MM-DD`, `DDMMYYYY`, etc.
- Create timestamped tables: `{original_table_name}_{YYYYMMDD}`
- Store metadata in `_metadata` table (import_id, source_file, file_date, table_name, row_count)
- Support both single-file and batch processing modes

**Key module**: `access_convert.py` - Unified converter wrapper with progress callback support, used exclusively by the web interface. Tries pyodbc first (if available), then falls back to other methods. Progress callbacks emit: `total_tables`, `processed_tables`, `current_table`, `percent`, `msg`.

### Web Interface Layer

**Main entry point**: `main.py` - Launches Flask dev server (default port 5001) with:
- Port availability checking before startup
- Upload folder validation and creation
- Argument parsing for host, port, debug mode, upload folder, max upload size
- Environment variable configuration (FLASK_HOST, FLASK_PORT, etc.)

**Core Flask app**: `interface/app_flask_local_search.py` (~1300 lines) - Complete Flask application with:
- **File upload/management**: Handles `.duckdb`, `.mdb`, `.accdb` files
  - `.duckdb` files → selected immediately
  - `.mdb`/`.accdb` files → converted in background thread, then selected
- **Background conversion**: Threading with `convert_lock`, monitored via `/admin/status`
- **Auto-indexing**: Optional fulltext index creation after conversion (controlled by config)
- **Dual-mode search**: DuckDB (with `_fulltext` index) or Access ODBC (direct query fallback)
- **Priority table support**: Configurable tables that appear first in search results
- **Event logging**: Structured logs via `log_event()` with ASCII-safe output
- **Client-side logging**: `/client/log` endpoint for frontend error reporting
- **Response compression**: Automatic gzip for responses >1000 bytes

**Configuration**: `interface/config.json` stores runtime settings:
- `db_path` - Currently selected database (only persisted if remember_last_db=true)
- `priority_tables` - Array of table names to prioritize in search (e.g., `["RANGER_SOSTAT"]`)
- `auto_index_after_convert` - Boolean for automatic indexing after conversion
- `remember_last_db` - Boolean to persist db_path across sessions

**DB path resolution order**: ENV var `DB_PATH` > runtime `_runtime_db_path` > config file `db_path` (if remember_last_db=true)

### Search System

**Fulltext indexing**: `interface/create_fulltext.py` creates `_fulltext` table with:
- **Schema**: `table_name`, `pk_col`, `pk_value`, `row_offset`, `content_norm`, `row_json`
- **Normalization pipeline**: Unicode NFD normalization → accent removal → lowercase → punctuation to space → space collapse
- **Resume capability**: Detects already-indexed rows and continues from offset (supports interruption/restart)
- **Chunked processing**: Configurable chunk size (default 5000 rows) and batch inserts (default 1000)
- **System table exclusion**: Filters out `_fulltext`, `MSys*`, `sqlite_*`, `duckdb_*` tables

**Search modes**:
1. **DuckDB search** (`api_search_duckdb`):
   - Queries `_fulltext` table with normalized tokens
   - Uses rapidfuzz `token_set_ratio` for scoring (0-100)
   - Supports token modes: `any` (OR) or `all` (AND)
   - Priority tables guaranteed to appear first if they have matches
   - Limits: `per_table` (rows per table), `candidate_limit` (SQL limit), `total_limit` (final result count)

2. **Access fallback search** (`fallback_search_access`):
   - Direct ODBC queries against `.mdb`/`.accdb` files (no index required)
   - Dynamically detects text columns (CHAR, TEXT, VARCHAR, MEMO) for searching
   - Slower but works without conversion or indexing

**Helper utilities**: `interface/utils.py`:
- `normalize_text(s)`: NFD normalization, accent removal, lowercase, punctuation/underscore to space
- `serialize_value(v)`: Converts DuckDB types (datetime, decimal, bytes) to JSON-compatible values

### File Organization

```
/
├── convert_*.py           # Four standalone converter implementations
├── access_convert.py      # Unified converter wrapper (used by web interface)
├── benchmark.py           # Benchmark suite comparing all converters
├── main.py               # Main entry point for Flask interface
├── interface/
│   ├── app_flask_local_search.py  # Flask application (~1300 lines)
│   ├── create_fulltext.py         # Fulltext indexing with resume support
│   ├── utils.py                   # normalize_text() and serialize_value()
│   ├── config.json                # Runtime configuration (git-ignored in practice)
│   └── uploads/                   # Uploaded database files (created on first run)
├── static/
│   ├── index.html        # Main search UI (Vue.js)
│   └── admin.html        # Admin/upload UI (Vue.js)
├── tools/                # Analysis scripts (batch analyze, reports, search utilities)
└── tests/                # Integration tests (requires running server)
    ├── test_geral.py              # General functionality tests
    └── test_web_interface.py      # Web interface tests
```

## Development Commands

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install system dependencies (choose one based on your needs)
brew install mdbtools      # For convert_mdbtools.py (Mac)
brew install openjdk       # For convert_jackcess.py (Mac)
sudo apt install mdbtools  # For convert_mdbtools.py (Linux)
```

### Running the Application

```bash
# Start Flask interface (default port 5001)
python main.py

# Custom configuration
python main.py --port 5002 --debug --upload-folder /path/to/uploads
```

### Running Tests

```bash
# Run integration tests (requires server running on port 5001)
python tests/test_geral.py
python tests/test_web_interface.py

# Run with pytest
python -m pytest tests/
```

### Running Converters Directly

```bash
# Single file conversion
python convert_mdbtools.py --input file.mdb --output database.duckdb

# Batch processing
python convert_mdbtools.py --input import_folder --output database.duckdb --batch
```

### Creating Fulltext Index

```bash
# Create/resume index
python interface/create_fulltext.py database.duckdb

# Rebuild from scratch
python interface/create_fulltext.py database.duckdb --drop
```

## Key Implementation Details

### Threading and Concurrency

**Two independent background threads**:
- `convert_thread`: Handles `.mdb`/`.accdb` → `.duckdb` conversion
  - Protected by `convert_lock` (threading.Lock)
  - Status tracked in `convert_status` dict: `running`, `ok`, `msg`, `input`, `output`, `total_tables`, `processed_tables`, `current_table`, `percent`
  - Only one conversion can run at a time (409 Conflict if attempted)
- `index_thread`: Handles `_fulltext` index creation
  - Protected by `index_lock`
  - Can be triggered manually via `/admin/start_index` or auto-triggered after conversion

**Thread lifecycle**: Both threads are daemon threads, so they terminate when Flask shuts down.

### Caching Strategy

**Table list caching**:
- Cache: `_tables_cache` dict keyed by database path
- TTL: 60 seconds (`_cache_ttl`)
- Invalidation: Automatic on TTL expiry, no manual invalidation
- Purpose: Avoid repeated `information_schema.tables` queries (expensive on large DBs)

**Why caching matters**: Listing tables can take 100ms+ on large DuckDB files. With 60s cache, the `/api/tables` endpoint becomes near-instant for repeated calls.

### Security Measures

- **Filename sanitization**: `secure_filename()` from werkzeug (removes path traversal)
- **Table name validation**: Regex `^[A-Za-z0-9_]+$` before SQL (prevents injection)
- **Parameterized queries**: All WHERE clauses use `?` placeholders, never string interpolation
- **Path validation**: Upload paths validated with `resolve().relative_to()` to prevent directory traversal
- **Response compression**: Gzip applied to JSON responses >1000 bytes (reduces bandwidth)

### Search Behavior

**Token modes**:
- `token_mode="any"`: OR logic across tokens (default) - matches rows with ANY search term
- `token_mode="all"`: AND logic across tokens - matches rows with ALL search terms

**Priority table guarantee**: If a priority table has ANY matching row (even with low score), it will appear in results FIRST, before higher-scoring non-priority tables.

**Score filtering**: Optional `min_score` parameter (0-100) filters out low-quality matches.

**Result limits** (applied in order):
1. `candidate_limit`: SQL LIMIT on `_fulltext` query (default 1000)
2. `per_table`: Max rows per table in results (default 10)
3. `total_limit`: Absolute max rows across all tables (default 500)

### File Naming Convention for Date Extraction

Converters extract dates from filenames using regex patterns:
- `DD_MM_YYYY` or `DD-MM-YYYY` → parsed as day-month-year
- `YYYY_MM_DD` or `YYYY-MM-DD` → parsed as year-month-day
- `DDMMYYYY` (8 digits) → parsed as day-month-year
- `YYYYMMDD` (8 digits) → parsed as year-month-day

If no date found, falls back to current date with a warning. Extracted date becomes the table suffix.

## API Endpoints

Key endpoints:
- `GET /api/health` - Health check with cache metrics
- `GET /api/tables` - List tables in current DB
- `GET /api/table?name=TABLE` - View table data with pagination
- `GET /api/search?q=query` - Fuzzy search across all tables
- `POST /api/upload` - Upload and auto-convert database files
- `POST /admin/select` - Select active database
- `POST /admin/set_priority` - Set priority tables for search
- `POST /admin/start_index` - Trigger fulltext indexing
- `GET /admin/status` - Get conversion/indexing status

## Configuration Details

**Environment variables** (set by `main.py` or externally):
- `DB_PATH` - Overrides config file and runtime DB selection (highest priority)
- `FLASK_HOST` - Server host (default: 127.0.0.1)
- `FLASK_PORT` - Server port (default: 5001)
- `FLASK_DEBUG` - Debug mode boolean (default: False)
- `UPLOAD_FOLDER` - Override default `interface/uploads/` directory
- `MAX_CONTENT_LENGTH` - Max upload size in bytes (default: 500MB)
- `PYTHONWARNINGS` - Set to "ignore" to suppress dependency warnings

**Config file** (`interface/config.json`):
```json
{
  "db_path": "",                     // Path to selected DB (empty if remember_last_db=false)
  "priority_tables": ["TABLE1"],     // Tables to prioritize in search
  "auto_index_after_convert": true,  // Auto-create _fulltext after conversion
  "remember_last_db": false          // Persist db_path across sessions
}
```

**Sanitization on load**: Config is auto-cleaned on startup:
- Non-list `priority_tables` → empty array
- "None" strings in `priority_tables` → removed
- Missing `auto_index_after_convert` → defaults to true
- Missing `remember_last_db` → defaults to false
- If `remember_last_db=false` → `db_path` cleared

## Important Gotchas

1. **Test server port**: Integration tests expect server on port 5001 (not 5000). Use `python main.py` without args.

2. **Fulltext index required for fast search**: DuckDB search requires `_fulltext` table. Without it, queries will fail. Always run indexing after conversion or use auto-indexing.

3. **ODBC drivers on non-Windows**: Access fallback search and `convert_pyodbc.py` require Microsoft Access Database Engine (Windows-only) or complex Wine setup on Linux/Mac.

4. **Cache can show stale tables**: 60-second cache means newly added tables may not appear immediately. Wait 60s or restart server.

5. **Priority tables syntax**: Must be exact table names (case-sensitive in some DBs). Typos will silently fail to prioritize.

6. **Date extraction failures**: If filename has no recognizable date pattern, converter uses current date as fallback - check logs for warnings.

7. **Concurrent conversion blocking**: Only one conversion can run at a time. Uploading a second Access file while converting returns 409 Conflict.

8. **Large file uploads**: Default 500MB limit. Adjust `--max-content-length` or `MAX_CONTENT_LENGTH` env var for larger files.

## Benchmarking

`benchmark.py` provides comparative performance testing:
- Runs all four converter implementations on sample files
- Measures execution time and success rate
- Generates JSON report with statistics
- Useful for choosing the best converter for your environment
