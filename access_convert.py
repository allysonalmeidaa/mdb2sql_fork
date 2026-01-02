# access_convert.py
# Conversor Access (.mdb / .accdb) -> DuckDB (.duckdb)
# Now supports progress_callback(progress_dict) to report progress during conversion.
#
import os
import subprocess
import tempfile
import shutil
import duckdb
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("access_convert")


def _ensure_clean_duckdb(path):
    try:
        if os.path.exists(path):
            logger.info(
                "Removendo arquivo .duckdb existente para começar limpo: %s", path
            )
            os.remove(path)
    except Exception as e:
        logger.warning("Não foi possível remover %s: %s", path, e)


def convert_access_to_duckdb(
    access_path: str,
    duckdb_path: str,
    chunk_size: int = 50000,
    conversion_mode: str = "odbc_preferred",
    odbc_enabled: bool = True,
    progress_callback=None,
):
    """
    Convert an Access DB (.mdb or .accdb) to a DuckDB file.
    progress_callback: optional callable(dict) where dict contains keys:
      - total_tables (int), processed_tables (int), current_table (str), percent (0..100), msg (str)
    Returns (ok: bool, message: str)
    """
    access_path = os.path.abspath(access_path)
    duckdb_path = os.path.abspath(duckdb_path)
    logger.info("convert_access_to_duckdb: %s -> %s", access_path, duckdb_path)

    def _report(**kw):
        try:
            if callable(progress_callback):
                progress_callback(kw)
        except Exception:
            pass

    def _normalize_mode(value):
        if value is None:
            return "odbc_preferred"
        mode = str(value).strip().lower()
        if mode in ("pure_only", "pure", "no_odbc"):
            return "pure_only"
        if mode in ("odbc_preferred", "odbc", "auto"):
            return "odbc_preferred"
        return "odbc_preferred"

    def try_pyodbc():
        try:
            import pyodbc
        except Exception as e:
            return False, f"pyodbc not installed: {e}"

        conn_strings = [
            rf"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={access_path};",
            rf"Driver={{Microsoft Access Driver (*.mdb)}};DBQ={access_path};",
        ]
        conn = None
        last_err = None
        for cs in conn_strings:
            try:
                conn = pyodbc.connect(cs, autocommit=True)
                logger.info("Conectado via pyodbc com conn string: %s", cs)
                break
            except Exception as e:
                last_err = e
                conn = None
        if conn is None:
            return False, f"ODBC connect failed: {last_err}"

        try:
            cur = conn.cursor()
            tables = []
            try:
                for row in cur.tables():
                    try:
                        tname = getattr(row, "table_name", None) or (
                            row[2] if len(row) > 2 else None
                        )
                    except Exception:
                        tname = None
                    if tname and not str(tname).startswith("MSys"):
                        tables.append(tname)
            except Exception:
                try:
                    rows = cur.execute(
                        "SELECT Name FROM MSysObjects WHERE Type In (1,4) AND Flags = 0"
                    ).fetchall()
                    tables = [r[0] for r in rows]
                except Exception:
                    pass

            if not tables:
                return False, "No user tables found in Access DB."

            total = len(tables)
            _ensure_clean_duckdb(duckdb_path)
            dconn = duckdb.connect(duckdb_path)

            for i, t in enumerate(tables):
                safe_table = str(t).replace('"', '""')
                _report(
                    total_tables=total,
                    processed_tables=i,
                    current_table=str(t),
                    percent=int((i / total) * 100),
                    msg="starting_table",
                )
                logger.info("Convertendo tabela %d/%d: %s", i + 1, total, t)
                try:
                    sql = f"SELECT * FROM [{t}]"
                    # drop if exists to avoid errors
                    dconn.execute(f'DROP TABLE IF EXISTS "{safe_table}"')
                    try:
                        it = pd.read_sql_query(sql, conn, chunksize=chunk_size)
                        first = True
                        for j, df_chunk in enumerate(it):
                            if df_chunk is None or df_chunk.shape[0] == 0:
                                continue
                            tmp_name = f"tmp_{abs(hash((t, j)))}"
                            dconn.register(tmp_name, df_chunk)
                            if first:
                                dconn.execute(
                                    f'CREATE TABLE "{safe_table}" AS SELECT * FROM {tmp_name}'
                                )
                                first = False
                            else:
                                dconn.execute(
                                    f'INSERT INTO "{safe_table}" SELECT * FROM {tmp_name}'
                                )
                            dconn.unregister(tmp_name)
                            # report progress within table (approx)
                            _report(
                                total_tables=total,
                                processed_tables=i + 1,
                                current_table=str(t),
                                percent=int(
                                    (
                                        (
                                            i
                                            + (j + 1)
                                            / (
                                                1
                                                + (
                                                    df_chunk.shape[0]
                                                    / max(1, chunk_size)
                                                )
                                            )
                                        )
                                        / total
                                    )
                                    * 100
                                ),
                                msg="in_table_chunk",
                            )
                    except ValueError:
                        # chunksize not supported: read all
                        df = pd.read_sql_query(sql, conn)
                        if df is None or df.shape[0] == 0:
                            logger.info("Tabela vazia: %s", t)
                        else:
                            tmp_name = f"tmp_{abs(hash((t, 0)))}"
                            dconn.register(tmp_name, df)
                            dconn.execute(
                                f'CREATE TABLE "{safe_table}" AS SELECT * FROM {tmp_name}'
                            )
                            dconn.unregister(tmp_name)
                    _report(
                        total_tables=total,
                        processed_tables=i + 1,
                        current_table=str(t),
                        percent=int(((i + 1) / total) * 100),
                        msg="table_done",
                    )
                except Exception as e:
                    logger.warning("Skipping table %s after errors: %s", t, e)
                    # continue with next table
                    _report(
                        total_tables=total,
                        processed_tables=i + 1,
                        current_table=str(t),
                        percent=int(((i + 1) / total) * 100),
                        msg=f"skipped:{e}",
                    )
                    continue

            dconn.close()
            conn.close()
            _report(
                total_tables=total,
                processed_tables=total,
                current_table="",
                percent=100,
                msg="converted",
            )
            return True, "converted via pyodbc"
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return False, f"pyodbc error: {e}"

    def try_pypyodbc():
        try:
            import pypyodbc as pyodbc  # type: ignore[import-not-found]
        except Exception as e:
            return False, f"pypyodbc not installed: {e}"
        try:
            cs = rf"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={access_path};"
            conn = pyodbc.connect(cs)
            cur = conn.cursor()
            tables = [
                r[2]
                for r in cur.tables()
                if (r[3].upper() == "TABLE" and not str(r[2]).startswith("MSys"))
            ]
            if not tables:
                return False, "No user tables found (pypyodbc)."
            total = len(tables)
            _ensure_clean_duckdb(duckdb_path)
            dconn = duckdb.connect(duckdb_path)
            for i, t in enumerate(tables):
                safe_table = str(t).replace('"', '""')
                _report(
                    total_tables=total,
                    processed_tables=i,
                    current_table=str(t),
                    percent=int((i / total) * 100),
                    msg="starting_table",
                )
                try:
                    dconn.execute(f'DROP TABLE IF EXISTS "{safe_table}"')
                    it = pd.read_sql_query(
                        f"SELECT * FROM [{t}]", conn, chunksize=chunk_size
                    )
                    first = True
                    for j, df_chunk in enumerate(it):
                        if df_chunk is None or df_chunk.shape[0] == 0:
                            continue
                        tmp_name = f"tmp_{abs(hash((t, j)))}"
                        dconn.register(tmp_name, df_chunk)
                        if first:
                            dconn.execute(
                                f'CREATE TABLE "{safe_table}" AS SELECT * FROM {tmp_name}'
                            )
                            first = False
                        else:
                            dconn.execute(
                                f'INSERT INTO "{safe_table}" SELECT * FROM {tmp_name}'
                            )
                        dconn.unregister(tmp_name)
                        _report(
                            total_tables=total,
                            processed_tables=i + 1,
                            current_table=str(t),
                            percent=int(((i + (j + 1) / 1) / total) * 100),
                            msg="in_table_chunk",
                        )
                except Exception as e:
                    logger.warning("Skipping %s: %s", t, e)
                    _report(
                        total_tables=total,
                        processed_tables=i + 1,
                        current_table=str(t),
                        percent=int(((i + 1) / total) * 100),
                        msg=f"skipped:{e}",
                    )
                    continue
            dconn.close()
            conn.close()
            _report(
                total_tables=total,
                processed_tables=total,
                current_table="",
                percent=100,
                msg="converted",
            )
            return True, "converted via pypyodbc"
        except Exception as e:
            return False, f"pypyodbc error: {e}"

    def try_mdbtools():
        if not access_path.lower().endswith(".mdb"):
            return False, "mdbtools supports only .mdb"
        try:
            proc = subprocess.run(
                ["mdb-tables", "-1", access_path],
                capture_output=True,
                text=True,
                check=True,
            )
            tbls = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        except Exception as e:
            return False, f"mdb-tables failed: {e}"
        total = len(tbls)
        _ensure_clean_duckdb(duckdb_path)
        dconn = duckdb.connect(duckdb_path)
        tmpdir = tempfile.mkdtemp(prefix="mdbtools_")
        try:
            for i, t in enumerate(tbls):
                csv_path = os.path.join(tmpdir, f"{t}.csv")
                _report(
                    total_tables=total,
                    processed_tables=i,
                    current_table=str(t),
                    percent=int((i / total) * 100),
                    msg="starting_table",
                )
                try:
                    with open(csv_path, "w", encoding="utf-8") as out:
                        subprocess.run(
                            ["mdb-export", access_path, t],
                            stdout=out,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=True,
                        )
                    csv_path_unix = csv_path.replace("\\", "/").replace("'", "''")
                    safe_table = str(t).replace('"', '""')
                    dconn.execute(f'DROP TABLE IF EXISTS "{safe_table}"')
                    dconn.execute(
                        f"CREATE TABLE \"{safe_table}\" AS SELECT * FROM read_csv_auto('{csv_path_unix}')"
                    )
                    _report(
                        total_tables=total,
                        processed_tables=i + 1,
                        current_table=str(t),
                        percent=int(((i + 1) / total) * 100),
                        msg="table_done",
                    )
                except Exception as e:
                    logger.warning("Failed to export/import table %s: %s", t, e)
                    _report(
                        total_tables=total,
                        processed_tables=i + 1,
                        current_table=str(t),
                        percent=int(((i + 1) / total) * 100),
                        msg=f"skipped:{e}",
                    )
                    continue
            dconn.close()
            _report(
                total_tables=total,
                processed_tables=total,
                current_table="",
                percent=100,
                msg="converted",
            )
            return True, "converted via mdbtools"
        except Exception as e:
            try:
                dconn.close()
            except Exception:
                pass
            return False, f"mdbtools error: {e}"
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

    def try_pyaccess_parser():
        try:
            from convert_pyaccess_parser import convert_mdb_to_duckdb
        except Exception as e:
            return False, f"pyaccess_parser not available: {e}"
        _report(
            total_tables=0,
            processed_tables=0,
            current_table="",
            percent=0,
            msg="starting_pyaccess_parser",
        )
        _ensure_clean_duckdb(duckdb_path)
        ok = bool(
            convert_mdb_to_duckdb(access_path, duckdb_path, batch_mode=True)
        )
        if ok:
            _report(
                total_tables=0,
                processed_tables=0,
                current_table="",
                percent=100,
                msg="converted",
            )
            return True, "converted via pyaccess_parser"
        return False, "pyaccess_parser failed"

    conversion_mode = _normalize_mode(conversion_mode)
    use_odbc = bool(odbc_enabled) and conversion_mode != "pure_only"

    if not use_odbc:
        ok, msg = try_pyaccess_parser()
        if ok:
            return True, msg
        return False, f"pyaccess_parser failed: {msg}"

    ok, msg = try_pyodbc()
    if ok:
        return True, msg
    ok2, msg2 = try_pypyodbc()
    if ok2:
        return True, msg2
    ok3, msg3 = try_pyaccess_parser()
    if ok3:
        return True, msg3
    ok4, msg4 = try_mdbtools()
    if ok4:
        return True, msg4
    return (
        False,
        "All methods failed: "
        f"pyodbc: {msg}; pypyodbc: {msg2}; pyaccess_parser: {msg3}; mdbtools: {msg4}",
    )
