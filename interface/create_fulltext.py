"""
create_fulltext.py (versão segura)

- Obtém a lista de tabelas ANTES de criar/alterar _fulltext (evita re-indexar _fulltext).
- Filtra tabelas de sistema e ignora explicitamente '_fulltext'.
- Suporta --drop para remover _fulltext antes de recriar.
- Suporta resuming: se _fulltext já contém linhas de uma tabela, continua a partir do offset já indexado.
- Imprime progresso claro por tabela.
"""
import argparse
import json
from pathlib import Path

import duckdb

from interface.utils import normalize_text, serialize_value

BATCH_INSERT = 1000
CHUNK = 5000

def detect_pk_col(cols):
    lower = [c.lower() for c in cols]
    if 'id' in lower:
        return cols[lower.index('id')]
    for c in cols:
        if c.lower().endswith('_id'):
            return c
    return None

def get_all_tables(conn):
    rows = conn.execute("SHOW TABLES").fetchall()
    tables = [r[0] for r in rows]
    filtered = [t for t in tables if not (t.lower() == '_fulltext' or t.lower().startswith('msys') or t.lower().startswith('sqlite_') or t.lower().startswith('duckdb_'))]
    return filtered

def create_or_resume_fulltext(db_path, drop=False, chunk=CHUNK, batch_insert=BATCH_INSERT):
    dbfile = Path(db_path)
    if not dbfile.exists():
        raise SystemExit(f"DuckDB file not found: {db_path}")

    conn = duckdb.connect(db_path)
    try:
        all_tables = get_all_tables(conn)
        print(f"Found {len(all_tables)} user tables to consider (system tables and '_fulltext' excluded).")

        if drop:
            print("Dropping existing _fulltext (because --drop specified)...")
            conn.execute("DROP TABLE IF EXISTS _fulltext")
            conn.commit()

        conn.execute("""
        CREATE TABLE IF NOT EXISTS _fulltext (
          table_name VARCHAR,
          pk_col VARCHAR,
          pk_value VARCHAR,
          row_offset BIGINT,
          content_norm TEXT,
          row_json TEXT
        )
        """)
        conn.commit()

        total_scanned = 0
        for table in all_tables:
            print(f"\nProcessing table: {table}")
            try:
                total_rows_in_table = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except Exception as e:
                print(f"  Cannot read table {table} row count, skipping. Error: {e}")
                continue

            already = conn.execute("SELECT COUNT(*) FROM _fulltext WHERE table_name = ?", [table]).fetchone()[0]
            if already >= total_rows_in_table:
                print(f"  Already indexed ({already}/{total_rows_in_table}), skipping.")
                continue
            if already > 0:
                print(f"  Resuming index for table {table}: already indexed {already} / {total_rows_in_table} rows (will continue from offset {already}).")

            try:
                cur = conn.execute(f'SELECT * FROM "{table}" LIMIT 0')
                cols = [c[0] for c in cur.description]
            except Exception as e:
                print(f"  Skipping {table} (cannot read columns): {e}")
                continue
            if not cols:
                print("  No columns, skipping.")
                continue

            pk_col = detect_pk_col(cols)
            print(f"  Columns: {len(cols)}, detected pk_col: {pk_col}")

            offset = already
            inserted_for_table = 0
            while offset < total_rows_in_table:
                try:
                    rows = conn.execute(f'SELECT * FROM "{table}" LIMIT {chunk} OFFSET {offset}').fetchall()
                except Exception as e:
                    print(f"  SELECT failed at offset {offset} for table {table}: {e}")
                    break
                if not rows:
                    break

                batch = []
                for rid_in_chunk, row in enumerate(rows):
                    row_offset = offset + rid_in_chunk
                    pk_value = None
                    if pk_col:
                        try:
                            idx = cols.index(pk_col)
                            pk_value = serialize_value(row[idx])
                        except Exception:
                            pk_value = None
                    try:
                        raw_concat = " ".join("" if row[i] is None else str(row[i]) for i in range(len(cols)))
                    except Exception:
                        raw_concat = " ".join(serialize_value(row[i]) or "" for i in range(len(cols)))
                    content_norm = normalize_text(raw_concat)
                    row_dict = { cols[i]: serialize_value(row[i]) for i in range(len(cols)) }
                    row_json = json.dumps(row_dict, ensure_ascii=False)
                    batch.append((table, pk_col, str(pk_value) if pk_value is not None else None, row_offset, content_norm, row_json))

                    if len(batch) >= batch_insert:
                        conn.executemany("INSERT INTO _fulltext VALUES (?, ?, ?, ?, ?, ?)", batch)
                        conn.commit()
                        inserted_for_table += len(batch)
                        total_scanned += len(batch)
                        batch = []
                if batch:
                    conn.executemany("INSERT INTO _fulltext VALUES (?, ?, ?, ?, ?, ?)", batch)
                    conn.commit()
                    inserted_for_table += len(batch)
                    total_scanned += len(batch)
                offset += len(rows)
                print(f"  Indexed offset up to {offset} (total inserted for table so far: {inserted_for_table})")
            print(f"Finished table {table}, total indexed for this table: {inserted_for_table}, table size: {total_rows_in_table}")
        print(f"\n_all tables processed. Total rows inserted into _fulltext in this run: {total_scanned}")
    finally:
        conn.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="caminho para arquivo .duckdb")
    p.add_argument("--chunk", type=int, default=CHUNK, help="linhas por SELECT chunk")
    p.add_argument("--batch", type=int, default=BATCH_INSERT, help="quantos inserir por batch executemany")
    p.add_argument("--drop", action="store_true", help="dropar _fulltext antes de criar (reindex do zero)")
    args = p.parse_args()
    create_or_resume_fulltext(args.db, drop=args.drop, chunk=args.chunk, batch_insert=args.batch)

if __name__ == "__main__":
    main()
