# app_flask_search.py
# Backend Flask para pesquisa global e visualização paginada de tabelas em DuckDB.
# Ajuste DB_PATH se o seu arquivo .duckdb estiver em outro local.
import decimal
import time
from datetime import date, datetime
from pathlib import Path

import duckdb
from flask import Flask, jsonify, request, g

from interface.utils import resolve_db_path, clamp_int

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploads"
MAX_LIMIT = 1000
MAX_PER_TABLE = 200
MAX_TABLES = 200
METADATA_TTL_SECONDS = 30
_METADATA_CACHE = {"ts": 0.0, "tables": [], "columns": {}, "db_path": None}

app = Flask(__name__, static_folder=str(PROJECT_ROOT / "static"), static_url_path="")


def connect_db():
    try:
        db_file = resolve_db_path(uploads_dir=UPLOAD_DIR)
    except ValueError as exc:
        raise FileNotFoundError(str(exc)) from exc
    if not db_file:
        raise FileNotFoundError(
            "DB_PATH not set and no .duckdb found in interface/uploads"
        )
    if not db_file.exists():
        raise FileNotFoundError(f"DuckDB file not found: {db_file}")
    return duckdb.connect(str(db_file)), db_file


def get_conn():
    conn = getattr(g, "_duckdb_conn", None)
    if conn is None:
        conn, db_file = connect_db()
        g._duckdb_conn = conn
        g._duckdb_path = str(db_file)
    return conn


def get_db_path():
    return getattr(g, "_duckdb_path", None)


@app.teardown_appcontext
def close_conn(exception):
    conn = g.pop("_duckdb_conn", None)
    if conn is not None:
        conn.close()


def quote_ident(name):
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid identifier")
    if "\x00" in name:
        raise ValueError("Invalid identifier")
    return '"' + name.replace('"', '""') + '"'


def list_tables(conn):
    rows = conn.execute("SHOW TABLES").fetchall()
    return [r[0] for r in rows]


def get_columns_map(conn, tables=None):
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position"
    ).fetchall()
    cols_by_table = {}
    for table_name, column_name in rows:
        if tables is not None and table_name not in tables:
            continue
        cols_by_table.setdefault(table_name, []).append(column_name)
    return cols_by_table


def get_metadata(conn, tables=None):
    db_path = get_db_path()
    if db_path and _METADATA_CACHE["db_path"] != db_path:
        _METADATA_CACHE["ts"] = 0.0
        _METADATA_CACHE["tables"] = []
        _METADATA_CACHE["columns"] = {}
        _METADATA_CACHE["db_path"] = db_path
    now = time.time()
    if _METADATA_CACHE["ts"] and (now - _METADATA_CACHE["ts"] < METADATA_TTL_SECONDS):
        all_tables = _METADATA_CACHE["tables"]
        cols_map = _METADATA_CACHE["columns"]
    else:
        all_tables = list_tables(conn)
        cols_map = get_columns_map(conn)
        _METADATA_CACHE["ts"] = now
        _METADATA_CACHE["tables"] = all_tables
        _METADATA_CACHE["columns"] = cols_map
        _METADATA_CACHE["db_path"] = db_path
    if tables is None:
        return all_tables, cols_map
    table_set = set(tables)
    filtered_tables = [t for t in all_tables if t in table_set]
    filtered_cols = {t: cols_map.get(t, []) for t in filtered_tables}
    return filtered_tables, filtered_cols


def serialize_value(v):
    """Converte tipos não-serializáveis para representação JSON-friendly."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return repr(v)
    try:
        if isinstance(v, (int, float, str, bool)):
            return v
    except Exception:
        pass
    return str(v)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/tables", methods=["GET"])
def api_tables():
    try:
        conn = get_conn()
        tables, _ = get_metadata(conn)
        return jsonify({"tables": tables})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/table", methods=["GET"])
def api_table():
    """
    Retorna paginação e colunas de uma tabela.
    Parâmetros:
      - name (obrigatório): nome da tabela
      - limit (opcional): rows por pagina (default 50, 0 usa limite maximo)
      - offset (opcional): offset (default 0)
      - col, q, sort, order (opcional): filtros/ordenação usados na visão por tabela
    """
    table = request.args.get("name")
    if not table:
        return jsonify({"error": "table name required (?name=TABLE_NAME)"}), 400
    limit = clamp_int(
        request.args.get("limit", 50), 50, min_value=0, max_value=MAX_LIMIT
    )
    offset = clamp_int(request.args.get("offset", 0), 0, min_value=0)
    if limit == 0:
        limit = MAX_LIMIT

    col = request.args.get("col")
    q = request.args.get("q")
    sort = request.args.get("sort")
    order = request.args.get("order", "ASC").upper()
    if order not in ("ASC", "DESC"):
        order = "ASC"

    try:
        conn = get_conn()
        tables, cols_map = get_metadata(conn)
        if table not in tables:
            return jsonify({"error": f"table not found: {table}"}), 404

        cols = cols_map.get(table, [])
        if not cols:
            return jsonify({"error": f"no columns found for table: {table}"}), 404

        params = []
        where_clause = ""
        if col and q:
            if col not in cols:
                return jsonify({"error": f"column not found: {col}"}), 400
            where_clause = f"WHERE CAST({quote_ident(col)} AS VARCHAR) ILIKE ?"
            params.append(f"%{q}%")

        order_clause = ""
        if sort:
            if sort not in cols:
                return jsonify({"error": f"sort column not found: {sort}"}), 400
            order_clause = f"ORDER BY {quote_ident(sort)} {order}"

        table_ident = quote_ident(table)
        count_sql = f"SELECT COUNT(*) FROM {table_ident}"
        if where_clause:
            count_sql += f" {where_clause}"
        total = conn.execute(count_sql, params).fetchone()[0]

        data_sql = f"SELECT * FROM {table_ident}"
        if where_clause:
            data_sql += f" {where_clause}"
        if order_clause:
            data_sql += f" {order_clause}"
        data_sql += f" LIMIT {limit} OFFSET {offset}"

        rows = conn.execute(data_sql, params).fetchall()

        # serializar rows
        rows_serial = [[serialize_value(v) for v in row] for row in rows]

        return jsonify(
            {
                "columns": cols,
                "rows": rows_serial,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search", methods=["GET"])
def api_search():
    """
    Busca global que retorna LINHAS COMPLETAS por tabela (limitadas por per_table).
    Parâmetros:
      - q (obrigatório): termo a buscar
      - per_table (opcional): maximo de linhas retornadas por tabela (default 25, 0 usa limite maximo).
      - limit_tables (opcional): maximo de tabelas a escanear (default 100, 0 usa limite maximo).
      - tables (opcional): lista separada por vírgula para limitar escopo
    Resposta:
      { q: "...", scanned_tables: N, results: { table_name: { columns: [...], rows: [[...], ...] } } }
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "query parameter 'q' required"}), 400

    per_table = clamp_int(
        request.args.get("per_table", 25), 25, min_value=0, max_value=MAX_PER_TABLE
    )
    limit_tables = clamp_int(
        request.args.get("limit_tables", 100), 100, min_value=0, max_value=MAX_TABLES
    )
    if per_table == 0:
        per_table = MAX_PER_TABLE
    if limit_tables == 0:
        limit_tables = MAX_TABLES

    tables_param = request.args.get("tables")
    requested_tables = (
        [t.strip() for t in tables_param.split(",")] if tables_param else None
    )
    like_param = f"%{q}%"

    results = {}
    scanned = 0
    try:
        conn = get_conn()
        all_tables, cols_all = get_metadata(conn)
        # opcional: filtrar apenas nas tabelas requisitadas
        tables = [
            t for t in all_tables if (requested_tables is None or t in requested_tables)
        ]
        # limitar tabelas escaneadas: se limit_tables == 0 => sem limite
        if limit_tables > 0:
            tables = tables[:limit_tables]
        cols_map = {t: cols_all.get(t, []) for t in tables}

        for table in tables:
            scanned += 1
            cols = cols_map.get(table, [])

            if not cols:
                continue

            # construir WHERE: CAST(col AS VARCHAR) ILIKE ? para cada coluna
            try:
                checks = [f"CAST({quote_ident(c)} AS VARCHAR) ILIKE ?" for c in cols]
            except ValueError:
                continue
            params = [like_param] * len(cols)
            where_clause = " OR ".join(checks)
            sql = f"SELECT * FROM {quote_ident(table)} WHERE {where_clause}"
            # se per_table > 0 aplicamos LIMIT
            sql += f" LIMIT {per_table}"

            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                # se falhar por tipos estranhos, pula tabela
                continue

            if rows:
                # serializar linhas
                rows_serial = [[serialize_value(v) for v in row] for row in rows]
                results[table] = {"columns": cols, "rows": rows_serial}

        return jsonify({"q": q, "results": results, "scanned_tables": scanned})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Dev server
    app.run(host="127.0.0.1", port=5000, debug=True)
