import argparse
from pathlib import Path

import duckdb

from interface.utils import resolve_db_path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"


def quote_ident(name):
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid identifier")
    if "\x00" in name:
        raise ValueError("Invalid identifier")
    return '"' + name.replace('"', '""') + '"'


def main():
    parser = argparse.ArgumentParser(description="Check _fulltext indexing progress")
    parser.add_argument("--db", help="Path to .duckdb file")
    args = parser.parse_args()
    try:
        dbfile = resolve_db_path(args.db, uploads_dir=UPLOAD_DIR)
    except ValueError as exc:
        print(str(exc))
        return
    if not dbfile or not dbfile.exists():
        print("DuckDB file not found. Set DB_PATH or use --db.")
        return
    conn = duckdb.connect(str(dbfile))
    try:
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        # ignore internal/system tables and _fulltext itself
        tables = [
            t
            for t in tables
            if not (
                t.lower().startswith("msys")
                or t.lower().startswith("sqlite_")
                or t.lower().startswith("duckdb_")
                or t.lower() == "_fulltext"
            )
        ]
        print(f"Found {len(tables)} user tables to check.")
        missing = []
        table_counts = {}
        if tables:
            try:
                unions = []
                for t in tables:
                    safe_name = t.replace("'", "''")
                    unions.append(
                        f"SELECT '{safe_name}' AS table_name, COUNT(*) AS table_rows FROM {quote_ident(t)}"
                    )
                counts_sql = " UNION ALL ".join(unions)
                for tname, cnt in conn.execute(counts_sql).fetchall():
                    table_counts[tname] = cnt
            except Exception as e:
                print(f"  Could not read table counts in batch: {e}")
        try:
            rows = conn.execute(
                "SELECT table_name, COUNT(*) FROM _fulltext GROUP BY table_name"
            ).fetchall()
            fulltext_counts = {name: cnt for name, cnt in rows}
        except Exception:
            fulltext_counts = {}
        for t in tables:
            if t not in table_counts:
                try:
                    table_counts[t] = conn.execute(
                        f"SELECT COUNT(*) FROM {quote_ident(t)}"
                    ).fetchone()[0]
                except Exception as e:
                    print(f"  Could not read table {t}: {e}")
                    continue
            cnt_table = table_counts.get(t, 0)
            cnt_indexed = fulltext_counts.get(t, 0)
            if cnt_indexed < cnt_table:
                missing.append((t, cnt_table, cnt_indexed))
        if not missing:
            print("All tables appear fully indexed (or no user tables found).")
        else:
            print("Tables not yet fully indexed (table, table_rows, indexed_rows):")
            for t, total, idx in missing:
                print(f"  {t}: {idx} / {total} indexed (missing {total - idx})")
            print(f"\nTotal tables with missing rows: {len(missing)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
