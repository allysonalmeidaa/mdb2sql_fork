# mdb to duckdb converter

Converts Microsoft Access database files (MDB/ACCDB) to DuckDB format.

## features

- Extracts date from filename automatically
- Preserves table structure
- Creates timestamped tables for historical tracking
- Metadata tracking for all imports
- Batch processing support
- Four implementation options

## implementation options

### 1. convert_mdbtools.py (recommended for linux/mac)

Uses mdbtools CLI utility.

**Pros:**
- Easy installation
- Works on Linux/Mac without additional setup
- No Java required

**Cons:**
- Text-based (CSV intermediate)
- Encoding issues possible
- Slower for large files

**Installation:**
```bash
# macos
brew install mdbtools

# linux
sudo apt install mdbtools
```

### 2. convert_jackcess.py (recommended for reliability)

Uses Jackcess Java library.

**Pros:**
- Most reliable
- Direct binary reading
- Better encoding handling
- Cross-platform

**Cons:**
- Requires Java JDK
- Slightly more complex setup

**Installation:**
```bash
# requires java jdk
# macos
brew install openjdk

# linux
sudo apt install default-jdk

# jars are downloaded automatically to temp/ folder
```

### 3. convert_pyaccess_parser.py (pure python)

Uses access-parser library (pure Python).

**Pros:**
- No external dependencies
- Pure Python implementation
- Easy installation
- Cross-platform

**Cons:**
- Slower than native implementations
- May have compatibility issues with some MDB formats

**Installation:**
```bash
pip install access-parser
```

### 4. convert_pyodbc.py (windows only)

Uses pypyodbc with ODBC driver.

**Pros:**
- Native Windows support
- Fast on Windows

**Cons:**
- Requires Microsoft Access Database Engine
- Windows only (or Wine on Linux/Mac)
- Complex setup on non-Windows

**Installation (Windows):**
1. Install Microsoft Access Database Engine:
   https://www.microsoft.com/en-us/download/details.aspx?id=54920
2. Install Python package:
   ```bash
   pip install pypyodbc
   ```

## performance comparison

Based on benchmark tests with 5 files (~90MB each) on macOS:

| Implementation | Success Rate | Avg Time/File | Total Time | Notes |
|---------------|--------------|---------------|------------|-------|
| **mdbtools** | 100% (5/5) | 53.80s | 268.98s | Fastest |
| **pyaccess_parser** | 100% (5/5) | 165.08s | 825.41s | Pure Python |
| **jackcess** | 100% (5/5) | 252.80s | 1264.01s | Most reliable |
| **pypyodbc** | 0% (0/5) | N/A | N/A | Windows-only |

**Recommendations:**
- **macOS/Linux:** Use `convert_mdbtools.py` (fastest) or `convert_pyaccess_parser.py` (pure Python)
- **Windows:** Use `convert_pyodbc.py` (native) or `convert_jackcess.py` (cross-platform)
- **Maximum reliability:** Use `convert_jackcess.py` (works everywhere with Java)

## quick start

```bash
# clone repository
git clone <repository-url>
cd mdb2sql

# create virtual environment
python3 -m venv venv

# activate virtual environment
# macos/linux:
source venv/bin/activate
# windows:
venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# install system dependencies (choose one)
brew install mdbtools            # For convert_mdbtools.py
brew install openjdk             # For convert_jackcess.py
# or install access engine        # for convert_pyodbc.py
```

## usage

### single file

```bash
# using mdbtools
python convert_mdbtools.py --input file.mdb --output database.duckdb

# using jackcess
python convert_jackcess.py --input file.mdb --output database.duckdb

# using pyaccess_parser
python convert_pyaccess_parser.py --input file.mdb --output database.duckdb

# using pypyodbc (windows)
python convert_pyodbc.py --input file.mdb --output database.duckdb
```

### batch processing

```bash
# process all mdb/accdb files in directory
python convert_mdbtools.py --input import_folder --output database.duckdb --batch
```

## file naming convention

Files should contain date in one of these formats:
- DD_MM_YYYY or DD-MM-YYYY
- YYYY_MM_DD or YYYY-MM-DD
- DDMMYYYY
- YYYYMMDD

Examples:
- DB3_04_09_2013.mdb -> 2013-09-04
- database_20190801.accdb -> 2019-08-01

## database structure

### tables

Each imported table is named: `{original_table_name}_{YYYYMMDD}`

Example:
- Original: RANGER_SOACCU
- Imported: RANGER_SOACCU_20130904

### metadata table

```sql
CREATE TABLE _metadata (
    import_id INTEGER PRIMARY KEY,
    source_file VARCHAR,
    file_date DATE,
    import_timestamp TIMESTAMP,
    table_name VARCHAR,
    row_count INTEGER
);
```

### query examples

```sql
-- View all imports
SELECT * FROM _metadata ORDER BY import_timestamp DESC;

-- Find tables from specific date
SELECT * FROM _metadata WHERE file_date = '2013-09-04';

-- List all table versions
SELECT 
    SUBSTRING(table_name, 1, POSITION('_2' IN table_name)-1) as base_table,
    file_date,
    row_count
FROM _metadata
ORDER BY base_table, file_date;

-- Query specific table version
SELECT * FROM RANGER_SOACCU_20130904 LIMIT 10;
```

## platform-specific notes

### macos
- Use convert_mdbtools.py or convert_jackcess.py
- mdbtools: `brew install mdbtools`
- Java: `brew install openjdk`

### linux
- Use convert_mdbtools.py or convert_jackcess.py
- mdbtools: `sudo apt install mdbtools`
- Java: `sudo apt install default-jdk`

### windows
- Use convert_pyodbc.py (recommended)
- Or use convert_jackcess.py with Java
- Install Access Database Engine or ODBC

## troubleshooting

### mdbtools encoding errors
Files may have encoding issues. Try convert_jackcess.py instead.

### java not found
```bash
# macos
brew install openjdk
export PATH="/usr/local/opt/openjdk/bin:$PATH"

# linux
sudo apt install default-jdk
```

### odbc driver not found
- Windows: Install Access Database Engine
- Linux/Mac: Install mdbtools ODBC driver or use different method

## development

```bash
# run tests
python -m pytest tests/

# check code
python -m pylint convert*.py
```

## license

MIT

## version history

- v0.1.0-mdbtools: Initial release with mdbtools
- v0.2.0: Added Jackcess, pyaccess_parser, and pypyodbc implementations
