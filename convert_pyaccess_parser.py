#!/usr/bin/env python3
"""
MDB to DuckDB Converter using access-parser library
Created: 2025-01-20T00:00:00Z
Last Modified: 2025-01-20T00:00:00Z

Description:
    Pure Python implementation for converting Microsoft Access MDB/ACCDB files
    to DuckDB format using the access-parser library. No external dependencies
    beyond Python packages.

Provides:
    - extract_date_from_filename(filename: str) -> str | None
    - sanitize_table_name(name: str) -> str
    - convert_mdb_to_duckdb(mdb_path: str, duckdb_path: str, batch_mode: bool) -> bool
    - main() - CLI entry point

Dependencies:
    - access-parser: Pure Python MDB parser
    - duckdb: Embedded SQL database
"""

import argparse
import decimal
import re
import sys
from pathlib import Path
from datetime import datetime, date
import importlib

LAST_ERROR = ""


def _set_last_error(msg):
    global LAST_ERROR
    LAST_ERROR = msg or ""


def get_last_error():
    return LAST_ERROR


def extract_date_from_filename(filename):
    patterns = [
        r"(\d{2})_(\d{2})_(\d{4})",
        r"(\d{4})_(\d{2})_(\d{2})",
        r"(\d{2})-(\d{2})-(\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            parts = match.groups()
            if len(parts[0]) == 4:
                year, month, day = parts
            else:
                day, month, year = parts

            try:
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


def sanitize_table_name(name):
    # Keep the original behavior: replace non-alphanumeric/underscore with underscore
    # and prefix names that start with a digit with 'T_'.
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name and name[0].isdigit():
        name = "T_" + name
    return name


def _infer_column_type(values):
    sample = [v for v in values if v is not None][:50]
    if not sample:
        return "VARCHAR"
    if any(isinstance(v, (bytes, bytearray, memoryview)) for v in sample):
        return "BLOB"
    if all(isinstance(v, bool) for v in sample):
        return "BOOLEAN"
    if any(isinstance(v, (datetime, date)) for v in sample):
        if any(isinstance(v, datetime) for v in sample):
            return "TIMESTAMP"
        return "DATE"
    if any(isinstance(v, decimal.Decimal) for v in sample):
        return "DECIMAL(38,10)"
    has_int = any(isinstance(v, int) and not isinstance(v, bool) for v in sample)
    has_float = any(isinstance(v, float) for v in sample)
    has_str = any(isinstance(v, str) for v in sample)
    if has_str and (has_int or has_float):
        return "VARCHAR"
    if has_float:
        return "DOUBLE"
    if has_int:
        return "BIGINT"
    return "VARCHAR"


def _normalize_cell(value, target_type):
    if value is None:
        return None
    if target_type == "BLOB":
        if isinstance(value, memoryview):
            return value.tobytes()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return str(value).encode("utf-8", errors="ignore")
    if target_type == "BOOLEAN":
        return bool(value)
    if target_type in ("DATE", "TIMESTAMP"):
        if isinstance(value, (datetime, date)):
            return value
        return str(value)
    if target_type in ("BIGINT", "DOUBLE", "DECIMAL(38,10)"):
        if isinstance(value, bool):
            return int(value)
        return value
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return value


def convert_mdb_to_duckdb(
    mdb_path, duckdb_path, batch_mode=False, create_fulltext=False
):
    """
    Convert an MDB file to a DuckDB database. Returns True on success, False on failure.
    Local imports are used to avoid requiring top-level imports elsewhere in the file.
    """
    import traceback

    ap = None
    for mod in ("access_parser", "access_parser_access"):
        try:
            ap = importlib.import_module(mod)
            break
        except Exception:
            continue

    try:
        duckdb = importlib.import_module("duckdb")
    except Exception:
        duckdb = None

    mdb_file = Path(mdb_path)

    if not mdb_file.exists():
        err = f"File not found: {mdb_path}"
        _set_last_error(err)
        print(f"Error: {err}")
        return False

    print(f"\nProcessing: {mdb_file.name}")

    date_str = extract_date_from_filename(mdb_file.name)
    if date_str:
        print(f"Date extracted: {date_str}")
        date_suffix = date_str.replace("-", "")
    else:
        print("Warning: Could not extract date from filename")
        date_suffix = datetime.now().strftime("%Y%m%d")

    if ap is None:
        err = "access_parser module not available. Please install access-parser."
        _set_last_error(err)
        print(f"Error: {err}")
        return False

    if duckdb is None:
        err = "duckdb module not available. Please install duckdb."
        _set_last_error(err)
        print(f"Error: {err}")
        return False

    conn = None
    try:
        print("Opening MDB file...")
        db = ap.AccessParser(str(mdb_file))

        # Get table names from the catalog (fallback if attribute differs)
        try:
            table_names = list(db.catalog.keys())
        except Exception:
            # Try alternative attribute name or method
            tables_attr = getattr(db, "tables", None)
            if tables_attr and hasattr(tables_attr, "keys"):
                table_names = list(tables_attr.keys())
            elif tables_attr:
                table_names = list(tables_attr)
            else:
                table_names = []

        print(f"Tables found: {len(table_names)}")

        conn = duckdb.connect(str(duckdb_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS _metadata (
                import_date TIMESTAMP,
                source_file VARCHAR,
                table_name VARCHAR,
                row_count INTEGER,
                date_suffix VARCHAR
            )
        """)

        total_tables = 0
        total_rows = 0

        for table_name in table_names:
            try:
                sanitized_name = sanitize_table_name(table_name)
                final_table_name = f"{sanitized_name}_{date_suffix}"

                if not batch_mode:
                    print(f"  Importing: {table_name}...", end=" ", flush=True)

                table_data = db.parse_table(table_name)

                # table_data expected to be a dict: {col_name: [values,...], ...}
                if not table_data:
                    if not batch_mode:
                        print("OK (0 rows)")
                    conn.execute(
                        "INSERT INTO _metadata VALUES (?, ?, ?, ?, ?)",
                        [
                            datetime.now(),
                            mdb_file.name,
                            final_table_name,
                            0,
                            date_suffix,
                        ],
                    )
                    continue

                column_names = list(table_data.keys())
                if not column_names:
                    if not batch_mode:
                        print("OK (0 rows)")
                    conn.execute(
                        "INSERT INTO _metadata VALUES (?, ?, ?, ?, ?)",
                        [
                            datetime.now(),
                            mdb_file.name,
                            final_table_name,
                            0,
                            date_suffix,
                        ],
                    )
                    continue

                sanitized_columns = [sanitize_table_name(col) for col in column_names]
                column_types = {
                    col: _infer_column_type(table_data.get(col, []))
                    for col in column_names
                }

                # Determine row count from the first column
                row_count = len(table_data[column_names[0]])

                if row_count == 0:
                    if not batch_mode:
                        print("OK (0 rows)")
                    conn.execute(
                        "INSERT INTO _metadata VALUES (?, ?, ?, ?, ?)",
                        [
                            datetime.now(),
                            mdb_file.name,
                            final_table_name,
                            0,
                            date_suffix,
                        ],
                    )
                    continue

                # Drop existing table if present
                conn.execute(f'DROP TABLE IF EXISTS "{final_table_name}"')

                column_defs = ", ".join(
                    [
                        f'"{sanitize_table_name(col)}" {column_types.get(col, "VARCHAR")}'
                        for col in column_names
                    ]
                )
                conn.execute(f'CREATE TABLE "{final_table_name}" ({column_defs})')

                placeholders = ", ".join(["?" for _ in sanitized_columns])
                insert_sql = f'INSERT INTO "{final_table_name}" VALUES ({placeholders})'
                batch_size = 1000
                batch_rows = []
                for i in range(row_count):
                    row_data = [
                        _normalize_cell(table_data[col][i], column_types.get(col, "VARCHAR"))
                        for col in column_names
                    ]
                    batch_rows.append(row_data)
                    if len(batch_rows) >= batch_size:
                        conn.executemany(insert_sql, batch_rows)
                        batch_rows = []
                if batch_rows:
                    conn.executemany(insert_sql, batch_rows)

                conn.execute(
                    "INSERT INTO _metadata VALUES (?, ?, ?, ?, ?)",
                    [
                        datetime.now(),
                        mdb_file.name,
                        final_table_name,
                        row_count,
                        date_suffix,
                    ],
                )

                if not batch_mode:
                    print(f"OK ({row_count} rows)")

                total_tables += 1
                total_rows += row_count

            except Exception as e:
                if not batch_mode:
                    print(f"ERROR: {str(e)}")
                # continue with next table
                continue

        if create_fulltext:
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS _fulltext (table_name VARCHAR, pk_col VARCHAR, pk_value VARCHAR, row_offset BIGINT, content_norm TEXT, row_json TEXT)"
                )
            except Exception as e:
                if not batch_mode:
                    print(f"Warning: _fulltext creation failed: {e}")

        # Close connection if open
        if conn is not None:
            conn.close()

        _set_last_error("")
        print("\nSummary:")
        print(f"  Tables imported: {total_tables}")
        print(f"  Total rows: {total_rows}")
        print(f"  Output: {duckdb_path}")

        return True

    except Exception as e:
        _set_last_error(str(e))
        print(f"Error processing MDB file: {e}")
        traceback.print_exc()
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert Microsoft Access MDB files to DuckDB using access-parser"
    )
    parser.add_argument("--input", "-i", required=True, help="Input MDB file path")
    parser.add_argument("--output", "-o", required=True, help="Output DuckDB file path")
    parser.add_argument(
        "--batch", "-b", action="store_true", help="Batch mode (less verbose output)"
    )
    parser.add_argument(
        "--fulltext",
        action="store_true",
        help="Create _fulltext table (empty) after import",
    )

    args = parser.parse_args()

    success = convert_mdb_to_duckdb(
        args.input, args.output, args.batch, args.fulltext
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
