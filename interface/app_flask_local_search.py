# app_flask_local_search.py
# Complete Flask app for local fuzzy search over DuckDB (and optional Access fallback).
# Features:
# - Upload / list / select / delete uploaded DB files (.duckdb, .mdb, .accdb)
# - Background conversion (.mdb/.accdb -> .duckdb) when access_convert.convert_access_to_duckdb is available
# - Progress reporting for conversion (admin/status)
# - Optional automatic _fulltext index creation via create_fulltext.create_or_resume_fulltext
# - /api/tables, /api/table, /api/search endpoints
# - Priority tables support via /admin/set_priority
# - Fallback search against Access via pyodbc (if installed)
#
# Replace your existing app_flask_local_search.py with this file.
# Requirements: pip install flask duckdb rapidfuzz pandas pyodbc (pyodbc optional)
# Optional helpers (place in same folder):
# - access_convert.py with convert_access_to_duckdb(access_path, duckdb_path, chunk_size=..., progress_callback=...)
# - create_fulltext.py with create_or_resume_fulltext(dbpath, drop=False, chunk=2000, batch_insert=1000)
# - utils.py with normalize_text(value) and serialize_value(value) if you want custom behavior (fallbacks included)
import gzip
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import duckdb
from flask import Flask, Response, jsonify, request, send_from_directory
from rapidfuzz import fuzz
from werkzeug.utils import secure_filename

# Garante que o diretório raiz do projeto esteja em sys.path, para que
# possamos importar access_convert.py e create_fulltext.py mesmo rodando
# este app a partir da pasta "interface".
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Logging setup: reduce request noise and log key events only
def _setup_event_logger():
    logger = logging.getLogger("mdb2sql")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - MDB2SQL - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return logger


_EVENT_LOG = _setup_event_logger()


def _safe_ascii(value):
    try:
        return str(value).encode("ascii", "ignore").decode("ascii")
    except Exception:
        return "?"


def log_event(message):
    try:
        _EVENT_LOG.info(_safe_ascii(message))
    except Exception:
        pass


# Optional modules
try:
    import pyodbc
except Exception:
    pyodbc = None

try:
    from access_convert import convert_access_to_duckdb
except Exception:
    convert_access_to_duckdb = None

create_fulltext_error = None
try:
    from interface.create_fulltext import create_or_resume_fulltext
except Exception as exc:
    create_or_resume_fulltext = None
    create_fulltext_error = str(exc)

try:
    from utils import normalize_text, serialize_value
except Exception:

    def normalize_text(s):
        return str(s).lower() if s is not None else ""

    def serialize_value(v):
        if v is None:
            return ""
        try:
            return str(v)
        except Exception:
            return repr(v)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_FOLDER") or (BASE_DIR / "uploads"))
try:
    UPLOAD_DIR = UPLOAD_DIR.expanduser().resolve(strict=False)
except Exception:
    UPLOAD_DIR = (BASE_DIR / "uploads").resolve(strict=False)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = BASE_DIR / "config.json"
DUCKDB_EXTENSIONS = {".duckdb", ".db", ".sqlite", ".sqlite3"}
ACCESS_EXTENSIONS = {".mdb", ".accdb"}
ALLOWED_EXTENSIONS = DUCKDB_EXTENSIONS | ACCESS_EXTENSIONS

# Conversion & index state
convert_lock = threading.Lock()
convert_status = {
    "running": False,
    "ok": None,
    "msg": None,
    "input": None,
    "output": None,
    "total_tables": 0,
    "processed_tables": 0,
    "current_table": "",
    "percent": 0,
}
convert_thread = None

index_lock = threading.Lock()
index_thread = None


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "db_path": "",
        "priority_tables": [],
        "auto_index_after_convert": True,
        "remember_last_db": False,
    }


def save_config(cfg):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=True, indent=2), encoding="utf-8"
    )


cfg = load_config()
changed_cfg = False
# sanitize priority_tables
if not isinstance(cfg.get("priority_tables"), list):
    cfg["priority_tables"] = []
    changed_cfg = True
else:
    cleaned = [t for t in cfg["priority_tables"] if t and t != "None"]
    if cleaned != cfg["priority_tables"]:
        cfg["priority_tables"] = cleaned
        changed_cfg = True
if "auto_index_after_convert" not in cfg:
    cfg["auto_index_after_convert"] = True
    changed_cfg = True
if "remember_last_db" not in cfg:
    cfg["remember_last_db"] = False
    changed_cfg = True
if not cfg.get("remember_last_db", False) and cfg.get("db_path"):
    cfg["db_path"] = ""
    changed_cfg = True
if changed_cfg:
    save_config(cfg)

_runtime_db_path = None


def remember_last_db_enabled():
    return bool(cfg.get("remember_last_db", False))


def get_db_path():
    env_db = os.environ.get("DB_PATH")
    if env_db:
        return env_db
    if _runtime_db_path:
        return _runtime_db_path
    if remember_last_db_enabled():
        return cfg.get("db_path")
    return ""


def set_db_path(p):
    global _runtime_db_path
    _runtime_db_path = str(p)
    if remember_last_db_enabled():
        cfg["db_path"] = str(p)
        save_config(cfg)
    else:
        if cfg.get("db_path"):
            cfg["db_path"] = ""
        save_config(cfg)


def clear_db_path():
    global _runtime_db_path
    _runtime_db_path = None
    if cfg.get("db_path"):
        cfg["db_path"] = ""
        save_config(cfg)


app = Flask(__name__, static_folder=str(PROJECT_ROOT / "static"), static_url_path="")


# ---------------- Static files ----------------
@app.route("/")
def index():
    resp = app.send_static_file("index.html")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.route("/admin")
def admin_page():
    resp = app.send_static_file("admin.html")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


# ---------------- Helpers ----------------
def duckdb_connect(path):
    # return connection (caller must close)
    return duckdb.connect(str(path))


def is_duckdb_path(dbpath):
    try:
        return Path(dbpath).suffix.lower() in DUCKDB_EXTENSIONS
    except Exception:
        return False


def safe_int(value, default):
    try:
        ivalue = int(value)
        return ivalue if ivalue > 0 else default
    except Exception:
        return default


# Cache simples mas efetivo para tabelas
_tables_cache = {}
_cache_timestamp = {}
_cache_mtime = {}
_cache_ttl = 60  # 60 segundos de cache


def list_tables_duckdb(path):
    """Lista tabelas de um arquivo DuckDB/SQLite com cache otimizado."""
    try:
        cache_key = str(path)
        # Verificar cache
        current_time = time.time()
        current_mtime = None
        try:
            current_mtime = Path(path).stat().st_mtime
        except Exception:
            current_mtime = None
        if cache_key in _tables_cache and cache_key in _cache_timestamp:
            cached_mtime = _cache_mtime.get(cache_key)
            if current_time - _cache_timestamp[cache_key] < _cache_ttl and (
                current_mtime is None or cached_mtime == current_mtime
            ):
                return _tables_cache[cache_key]

        # Buscar do banco
        conn = duckdb_connect(path)
        try:
            # Query mais eficiente - filtrar tabelas do sistema
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_name NOT LIKE '_%'"
            ).fetchall()
            tables = [r[0] for r in rows]
            if not tables:
                rows = conn.execute("SHOW TABLES").fetchall()
                tables = [
                    r[0]
                    for r in rows
                    if r[0]
                    and not str(r[0]).lower().startswith("_")
                    and not str(r[0]).lower().startswith("sqlite_")
                    and not str(r[0]).lower().startswith("duckdb_")
                ]

            # Atualizar cache
            _tables_cache[cache_key] = tables
            _cache_timestamp[cache_key] = current_time
            _cache_mtime[cache_key] = current_mtime

            return tables
        finally:
            conn.close()
    except Exception as exc:
        trace = traceback.format_exc().replace("\n", " ").replace("\r", " ")
        log_event(f"event=list_tables_error err={exc} trace={trace}")
        raise


def list_tables_access(path):
    """Lista tabelas de um banco Access via ODBC (pyodbc)."""
    if pyodbc is None:
        raise RuntimeError("pyodbc not installed")
    conn = None
    conn_strs = [
        rf"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};",
        rf"Driver={{Microsoft Access Driver (*.mdb)}};DBQ={path};",
    ]
    last_err = None
    for cs in conn_strs:
        try:
            conn = pyodbc.connect(cs, autocommit=True, timeout=30)
            break
        except Exception as e:
            last_err = e
            conn = None
    if conn is None:
        raise RuntimeError(f"ODBC connect failed: {last_err}")
    try:
        cur = conn.cursor()
        tables = []
        try:
            for row in cur.tables():
                try:
                    tname = getattr(row, "table_name", None) or (
                        row[2] if len(row) > 2 else None
                    )
                except (AttributeError, IndexError, TypeError):
                    tname = None
                if tname and not str(tname).startswith("MSys"):
                    tables.append(tname)
        except Exception:
            # fallback via MSysObjects
            try:
                rows = cur.execute(
                    "SELECT Name FROM MSysObjects WHERE Type In (1,4) AND Flags = 0"
                ).fetchall()
                tables = [r[0] for r in rows]
            except Exception:
                tables = []
        return tables
    finally:
        try:
            conn.close()
        except Exception as close_exc:
            close_trace = (
                "".join(
                    traceback.format_exception(
                        type(close_exc), close_exc, close_exc.__traceback__
                    )
                )
                .replace("\n", " ")
                .replace("\r", " ")
            )
            log_event(f"event=access_close_error err={close_exc} trace={close_trace}")


# ---------------- Admin endpoints ----------------
@app.route("/admin/list_uploads", methods=["GET"])
def admin_list_uploads():
    files = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.name):
        if p.is_file():
            st = p.stat()
            files.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "ext": p.suffix.lower(),
                }
            )
    return jsonify(
        {
            "uploads": files,
            "current_db": get_db_path(),
            "priority_tables": cfg.get("priority_tables", []),
            "auto_index_after_convert": cfg.get("auto_index_after_convert", True),
            "remember_last_db": cfg.get("remember_last_db", False),
        }
    )


@app.route("/admin/status", methods=["GET"])
def admin_status():
    dbpath = get_db_path()
    status = {
        "indexing": False,
        "db": dbpath or "",
        "fulltext_count": 0,
        "top_tables": [],
    }
    status["indexer_available"] = create_or_resume_fulltext is not None
    if not status["indexer_available"]:
        status["indexer_error"] = create_fulltext_error or "create_fulltext missing"
    with index_lock:
        if index_thread and index_thread.is_alive():
            status["indexing"] = True
    # try _fulltext info
    if dbpath and is_duckdb_path(dbpath) and Path(dbpath).exists():
        try:
            conn = duckdb_connect(dbpath)
            try:
                total = conn.execute("SELECT COUNT(*) FROM _fulltext").fetchone()[0]
                status["fulltext_count"] = int(total)
                rows = conn.execute(
                    "SELECT table_name, COUNT(*) as c FROM _fulltext GROUP BY table_name ORDER BY c DESC LIMIT 50"
                ).fetchall()
                status["top_tables"] = [
                    {"table": r[0], "count": int(r[1])} for r in rows
                ]
            except Exception:
                status["fulltext_count"] = 0
                status["top_tables"] = []
            finally:
                conn.close()
        except Exception as e:
            status["error_fulltext"] = str(e)
    with convert_lock:
        status["conversion"] = dict(convert_status)
    status["priority_tables"] = cfg.get("priority_tables", [])
    status["auto_index_after_convert"] = cfg.get("auto_index_after_convert", True)
    status["remember_last_db"] = cfg.get("remember_last_db", False)
    return jsonify(status)


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check completo com metricas."""
    current_time = time.time()

    # Metricas de cache
    cache_age = 0
    db_path = get_db_path()
    if db_path in _cache_timestamp:
        cache_age = current_time - _cache_timestamp[db_path]

    return jsonify(
        {
            "status": "healthy",
            "current_db": db_path or "none",
            "timestamp": datetime.now().isoformat(),
            "cache_info": {
                "tables_cached": len(_tables_cache),
                "cache_age_seconds": int(cache_age),
                "cache_ttl": _cache_ttl,
            },
            "database": {
                "current_db": db_path or "none",
                "db_exists": Path(db_path).exists() if db_path else False,
            },
            "system": {
                "upload_folder": str(UPLOAD_DIR),
                "allowed_extensions": list(ALLOWED_EXTENSIONS),
            },
            "indexer": {
                "available": create_or_resume_fulltext is not None,
                "error": create_fulltext_error or "",
            },
        }
    )


@app.route("/api/upload", methods=["POST"])
def api_upload():
    return admin_upload()


@app.route("/api/list_uploads", methods=["GET"])
def api_list_uploads():
    files = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.name):
        if p.is_file():
            st = p.stat()
            files.append(
                {
                    "name": p.name,
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                }
            )
    return jsonify({"files": files})


@app.route("/api/select_db", methods=["POST"])
def api_select_db():
    data = request.get_json() or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400
    fpath = UPLOAD_DIR / secure_filename(filename)
    if not fpath.exists():
        return jsonify({"error": "file not found"}), 404
    ext = fpath.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Invalid file type: {ext}"}), 400
    set_db_path(str(fpath))
    log_event(f"event=db_select path={fpath}")
    return jsonify({"ok": True, "db": str(fpath)})


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    global convert_thread
    if "file" not in request.files:
        return jsonify({"error": "arquivo não enviado"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "nome de arquivo inválido"}), 400
    filename = secure_filename(f.filename)
    ext = Path(filename).suffix.lower()
    dest = UPLOAD_DIR / filename
    f.save(dest)
    try:
        log_event(f"event=upload name={filename} ext={ext} size={dest.stat().st_size}")
    except Exception:
        pass
    # duckdb -> select immediately
    if ext == ".duckdb":
        set_db_path(str(dest))
        log_event(f"event=db_select path={dest}")
        return jsonify({"ok": True, "db_path": str(dest)})
    # access -> convert in background if converter available
    if ext in (".mdb", ".accdb"):
        if convert_access_to_duckdb is None:
            return jsonify(
                {
                    "error": "Conversão não disponível: access_convert.py ausente ou dependências não instaladas"
                }
            ), 500
        with convert_lock:
            if convert_status.get("running"):
                return jsonify({"error": "Já existe uma conversão em execução"}), 409
            out_duckdb = UPLOAD_DIR / f"{Path(filename).stem}.duckdb"
            convert_status.update(
                {
                    "running": True,
                    "ok": None,
                    "msg": "started",
                    "input": str(dest),
                    "output": str(out_duckdb),
                    "total_tables": 0,
                    "processed_tables": 0,
                    "current_table": "",
                    "percent": 0,
                }
            )
            log_event(f"event=convert_start input={dest} output={out_duckdb}")

            def progress_cb(p):
                with convert_lock:
                    convert_status.update(
                        {
                            k: v
                            for k, v in p.items()
                            if k
                            in (
                                "total_tables",
                                "processed_tables",
                                "current_table",
                                "percent",
                                "msg",
                            )
                        }
                    )

            def run_convert():
                try:
                    ok, msg = convert_access_to_duckdb(
                        str(dest),
                        str(out_duckdb),
                        chunk_size=20000,
                        progress_callback=progress_cb,
                    )
                    with convert_lock:
                        convert_status["running"] = False
                        convert_status["ok"] = bool(ok)
                        convert_status["msg"] = msg
                        convert_status["percent"] = (
                            100 if ok else convert_status.get("percent", 0)
                        )
                    log_event(
                        f"event=convert_done ok={bool(ok)} output={out_duckdb} msg={msg}"
                    )
                    if ok:
                        set_db_path(str(out_duckdb))
                        log_event(f"event=db_select path={out_duckdb}")
                        if (
                            cfg.get("auto_index_after_convert", True)
                            and not create_or_resume_fulltext
                        ):
                            with convert_lock:
                                base_msg = convert_status.get("msg") or ""
                                suffix = "indexador ausente"
                                if base_msg:
                                    convert_status["msg"] = f"{base_msg} - {suffix}"
                                else:
                                    convert_status["msg"] = suffix
                            log_event(
                                f"event=indexer_missing db={out_duckdb} err={create_fulltext_error}"
                            )
                        # optional auto-index with create_or_resume_fulltext
                        if (
                            cfg.get("auto_index_after_convert", True)
                            and create_or_resume_fulltext
                        ):
                            # reutiliza o mesmo mecanismo de indexação monitorado por /admin/status
                            global index_thread
                            with index_lock:
                                if not index_thread or not index_thread.is_alive():

                                    def run_index_auto():
                                        try:
                                            log_event(
                                                f"event=index_start db={out_duckdb} drop=False chunk=2000 batch=1000"
                                            )
                                            create_or_resume_fulltext(
                                                str(out_duckdb),
                                                drop=False,
                                                chunk=2000,
                                                batch_insert=1000,
                                            )
                                            log_event(
                                                f"event=index_done db={out_duckdb}"
                                            )
                                        except Exception as e:
                                            log_event(
                                                f"event=index_error db={out_duckdb} err={e}"
                                            )

                                    index_thread = threading.Thread(
                                        target=run_index_auto, daemon=True
                                    )
                                    index_thread.start()
                except Exception as e:
                    with convert_lock:
                        convert_status["running"] = False
                        convert_status["ok"] = False
                        convert_status["msg"] = f"exception: {e}"
                    log_event(f"event=convert_error input={dest} err={e}")

            convert_thread = threading.Thread(target=run_convert, daemon=True)
            convert_thread.start()
        return jsonify(
            {
                "ok": True,
                "status": "converting",
                "input": str(dest),
                "output": str(out_duckdb),
            }
        )
    return jsonify({"error": f"extensão não permitida: {ext}"}), 400


@app.route("/admin/select", methods=["POST"])
def admin_select():
    data = request.get_json() or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400
    fpath = UPLOAD_DIR / secure_filename(filename)
    if not fpath.exists():
        return jsonify({"error": "arquivo não encontrado"}), 404
    # set as current DB (duckdb or access). Frontend /api/tables will handle listing with fallback.
    set_db_path(str(fpath))
    log_event(f"event=db_select path={fpath}")
    return jsonify({"ok": True, "db_path": str(fpath)})


@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    data = request.get_json() or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400
    safe = secure_filename(filename)
    target = UPLOAD_DIR / safe
    try:
        target.resolve().relative_to(UPLOAD_DIR.resolve())
    except Exception:
        return jsonify({"error": "invalid filename or path"}), 400
    if not target.exists():
        return jsonify({"error": "arquivo não encontrado"}), 404
    try:
        current = get_db_path()
        if current and Path(current).resolve() == target.resolve():
            clear_db_path()
        target.unlink()
        log_event(f"event=db_delete name={target.name}")
        _tables_cache.pop(str(target), None)
        _cache_timestamp.pop(str(target), None)
        _cache_mtime.pop(str(target), None)
        # remove converted duckdb with same stem
        duck_out = UPLOAD_DIR / f"{target.stem}.duckdb"
        if duck_out.exists():
            try:
                duck_out.unlink()
            except Exception:
                pass
            _tables_cache.pop(str(duck_out), None)
            _cache_timestamp.pop(str(duck_out), None)
            _cache_mtime.pop(str(duck_out), None)
        return jsonify({"ok": True, "deleted": str(target.name)})
    except Exception as e:
        return jsonify({"error": f"falha ao apagar: {e}"}), 500


@app.route("/admin/set_priority", methods=["POST"])
def admin_set_priority():
    data = request.get_json() or {}
    tables = data.get("tables")
    if isinstance(tables, str):
        lst = [t.strip() for t in tables.split(",") if t.strip()]
    elif isinstance(tables, list):
        lst = [str(t).strip() for t in tables]
    else:
        return jsonify({"error": "tables param required"}), 400
    cfg["priority_tables"] = lst
    save_config(cfg)
    return jsonify({"ok": True, "priority_tables": lst})


@app.route("/admin/set_auto_index", methods=["POST"])
def admin_set_auto_index():
    data = request.get_json() or {}
    enabled = data.get("enabled")
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    if enabled is None:
        return jsonify({"error": "enabled required"}), 400
    cfg["auto_index_after_convert"] = bool(enabled)
    save_config(cfg)
    log_event(f"event=auto_index_set enabled={cfg['auto_index_after_convert']}")
    return jsonify(
        {"ok": True, "auto_index_after_convert": cfg["auto_index_after_convert"]}
    )


@app.route("/admin/start_index", methods=["POST"])
def admin_start_index():
    if create_or_resume_fulltext is None:
        err = create_fulltext_error or "create_fulltext missing"
        log_event(f"event=indexer_missing err={err}")
        return jsonify({"error": f"indexador nao disponivel: {err}"}), 503
    data = request.get_json() or {}
    drop = bool(data.get("drop", False))
    chunk = safe_int(data.get("chunk", 2000), 2000)
    batch = safe_int(data.get("batch", 1000), 1000)
    dbpath = get_db_path()
    if not dbpath:
        return jsonify({"error": "nenhum db selecionado"}), 400
    if not is_duckdb_path(dbpath):
        return jsonify({"error": "indice _fulltext requer DuckDB"}), 400
    if not Path(dbpath).exists():
        return jsonify({"error": "db nao encontrado"}), 404
    global index_thread
    with index_lock:
        if index_thread and index_thread.is_alive():
            return jsonify({"error": "indexação já em execução"}), 409

        def run_index():
            try:
                log_event(
                    f"event=index_start db={dbpath} drop={drop} chunk={chunk} batch={batch}"
                )
                if create_or_resume_fulltext:
                    create_or_resume_fulltext(
                        dbpath, drop=drop, chunk=chunk, batch_insert=batch
                    )
                else:
                    # attempt both names
                    try:
                        from create_fulltext import create_or_resume_fulltext as cf

                        cf(dbpath, drop=drop, chunk=chunk, batch_insert=batch)
                    except Exception as e:
                        log_event(f"event=index_error db={dbpath} err={e}")
            except Exception as e:
                log_event(f"event=index_error db={dbpath} err={e}")
            log_event(f"event=index_done db={dbpath}")

        index_thread = threading.Thread(target=run_index, daemon=True)
        index_thread.start()
    return jsonify({"ok": True, "started": True, "db": get_db_path()})


# ---------------- Client log ----------------
@app.route("/client/log", methods=["POST"])
def client_log():
    data = request.get_json() or {}
    level = str(data.get("level", "info")).lower()
    msg = data.get("msg", "")
    if msg:
        msg = msg.replace("\n", " ").replace("\r", " ")
    if len(msg) > 500:
        msg = msg[:500]
    log_event(f"event=client_log level={level} msg={msg}")
    return jsonify({"ok": True})


# ---------------- Search + table endpoints ----------------


# Função de compressão para respostas grandes
def compress_response(response):
    """Comprime respostas JSON grandes com gzip"""
    if response.content_type == "application/json" and len(response.data) > 1000:
        response.data = gzip.compress(response.data)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
    return response


# Função de validação de nomes de tabela
def validar_nome_tabela(table_name):
    """Valida e sanitiza nome de tabela para prevenir SQL injection"""
    if not table_name or not isinstance(table_name, str):
        return False
    # Permitir apenas letras, números e underscores
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        return False
    if len(table_name) > 64:
        return False
    return True


# Adicionar compressão automática após cada requisição
@app.after_request
def after_request(response):
    return compress_response(response)


@app.route("/api/tables", methods=["GET"])
def api_tables():
    dbpath = get_db_path()
    if not dbpath:
        return jsonify(
            {"tables": [], "count": 0, "error": "Nenhum DB selecionado"}
        ), 200

    # Verificar se o arquivo existe
    if not Path(dbpath).exists():
        log_event(f"event=api_tables_missing db={dbpath}")
        return jsonify({"error": f"Database file not found: {dbpath}"}), 404

    # Parâmetro opcional para incluir estatísticas
    include_stats = request.args.get("stats", "false").lower() == "true"

    ext = Path(dbpath).suffix.lower()
    try:
        if ext in (".duckdb", ".db", ".sqlite", ".sqlite3"):
            tables = list_tables_duckdb(dbpath)
        elif ext in (".mdb", ".accdb"):
            # Para Access, usamos o helper específico
            tables = list_tables_access(dbpath)
        else:
            return jsonify({"error": f"Unsupported DB format: {dbpath}"}), 400

        response = {"tables": tables, "count": len(tables)}

        # Adicionar estatísticas apenas se solicitado
        if include_stats:
            stats = {
                "total": len(tables),
                "prefixos": {},
                "tamanho_medio": sum(len(t) for t in tables) / len(tables)
                if tables
                else 0,
            }

            # Análise rápida de prefixos
            for tabela in tables:
                prefixo = tabela.split("_")[0] if "_" in tabela else "OUTROS"
                stats["prefixos"][prefixo] = stats["prefixos"].get(prefixo, 0) + 1

            response["stats"] = stats

        return jsonify(response)
    except Exception as e:
        log_event(f"event=api_tables_error err={e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/table", methods=["GET"])
def api_table():
    table = request.args.get("name")
    if not table:
        return jsonify({"error": "table name required (?name=TABLE_NAME)"}), 400
    dbpath = get_db_path()
    if not dbpath:
        return jsonify({"error": "No DB selected"}), 400
    ext = Path(dbpath).suffix.lower()
    if ext not in (".duckdb", ".db", ".sqlite", ".sqlite3"):
        return jsonify(
            {
                "error": f"Table view only supported for DuckDB/SQLite. Current DB: {dbpath}"
            }
        ), 400
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except Exception:
        return jsonify({"error": "limit and offset must be integers"}), 400

    col = request.args.get("col")
    q = request.args.get("q")
    sort = request.args.get("sort")
    order = request.args.get("order", "ASC").upper()
    if order not in ("ASC", "DESC"):
        order = "ASC"

    try:
        conn = duckdb_connect(dbpath)
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        if table not in tables:
            conn.close()
            return jsonify({"error": f"table not found: {table}"}), 404

        # obter colunas
        cur = conn.execute(f'SELECT * FROM "{table}" LIMIT 0')
        cols = [c[0] for c in cur.description]

        params = []
        where_clause = ""
        if col and q:
            if col not in cols:
                conn.close()
                return jsonify({"error": f"column not found: {col}"}), 400
            where_clause = f'WHERE CAST("{col}" AS VARCHAR) ILIKE ?'
            params.append(f"%{q}%")

        order_clause = ""
        if sort:
            if sort not in cols:
                conn.close()
                return jsonify({"error": f"sort column not found: {sort}"}), 400
            order_clause = f'ORDER BY "{sort}" {order}'

        count_sql = f'SELECT COUNT(*) FROM "{table}"'
        if where_clause:
            count_sql += f" {where_clause}"
        total = conn.execute(count_sql, params).fetchone()[0]

        data_sql = f'SELECT * FROM "{table}"'
        if where_clause:
            data_sql += f" {where_clause}"
        if order_clause:
            data_sql += f" {order_clause}"
        # LIMIT só se limit > 0 (0 significa ilimitado)
        if limit > 0:
            data_sql += f" LIMIT {limit} OFFSET {offset}"

        rows = conn.execute(data_sql, params).fetchall()
        conn.close()

        data = []
        for r in rows:
            row_obj = {}
            for i, cname in enumerate(cols):
                try:
                    row_obj[cname] = serialize_value(r[i])
                except Exception:
                    row_obj[cname] = None
            data.append(row_obj)

        return jsonify(
            {
                "table": table,
                "total": int(total),
                "limit": limit,
                "offset": offset,
                "columns": cols,
                "rows": data,
            }
        )
    except Exception as e:
        try:
            conn.close()
        except Exception as close_exc:
            close_trace = (
                "".join(
                    traceback.format_exception(
                        type(close_exc), close_exc, close_exc.__traceback__
                    )
                )
                .replace("\n", " ")
                .replace("\r", " ")
            )
            log_event(f"event=access_close_error err={close_exc} trace={close_trace}")
        return jsonify({"error": str(e)}), 500


def api_search_duckdb(
    q, per_table, candidate_limit, total_limit, token_mode, min_score, tables=None
):
    q_norm = normalize_text(q)
    tokens = [t for t in q_norm.split() if t]
    if tokens:
        if token_mode == "any":
            where_parts = ["content_norm LIKE ?" for _ in tokens]
            where_sql = " OR ".join(where_parts)
            params = [f"%{t}%" for t in tokens]
        else:
            where_parts = ["content_norm LIKE ?" for _ in tokens]
            where_sql = " AND ".join(where_parts)
            params = [f"%{t}%" for t in tokens]
    else:
        where_sql = "content_norm LIKE ?"
        params = [f"%{q_norm}%"]
    # Ao montar os candidatos SQL, já priorizamos as tabelas marcadas em priority_tables
    priority_tables = cfg.get("priority_tables", []) or []
    if priority_tables:
        in_placeholders = ",".join(["?"] * len(priority_tables))
        sql = (
            "SELECT table_name, pk_col, pk_value, row_offset, content_norm, row_json "
            f"FROM _fulltext WHERE {where_sql} "
            f"ORDER BY CASE WHEN table_name IN ({in_placeholders}) THEN 0 ELSE 1 END, table_name "
            f"LIMIT {candidate_limit}"
        )
        # Atenção: os parâmetros do WHERE vêm primeiro, depois os do IN, na ordem dos placeholders.
        sql_params = params + list(priority_tables)
    else:
        sql = (
            "SELECT table_name, pk_col, pk_value, row_offset, content_norm, row_json "
            f"FROM _fulltext WHERE {where_sql} LIMIT {candidate_limit}"
        )
        sql_params = params
    try:
        conn = duckdb_connect(get_db_path())
        rows = conn.execute(sql, sql_params).fetchall()
        conn.close()
    except Exception as exc:
        try:
            conn.close()
        except Exception as close_exc:
            close_trace = (
                "".join(
                    traceback.format_exception(
                        type(close_exc), close_exc, close_exc.__traceback__
                    )
                )
                .replace("\n", " ")
                .replace("\r", " ")
            )
            log_event(f"event=duckdb_close_error err={close_exc} trace={close_trace}")
        trace = (
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            .replace("\n", " ")
            .replace("\r", " ")
        )
        log_event(f"event=duckdb_search_error err={exc} trace={trace}")
        return {"error": f"search failed: {exc}"}

    # Filtro opcional por lista de tabelas (tables=[...])
    allowed_tables = None
    if tables:
        allowed_tables = {str(t).strip() for t in tables if str(t).strip()}
        if allowed_tables:
            rows = [r for r in rows if r[0] in allowed_tables]
    candidates = []
    for r in rows:
        table_name, pk_col, pk_value, row_offset, content_norm, row_json = r
        score = fuzz.token_set_ratio(q_norm, content_norm)
        if min_score is not None and score < min_score:
            continue
        candidates.append(
            {
                "score": score,
                "table": table_name,
                "pk_col": pk_col,
                "pk_value": pk_value,
                "row_json": row_json,
            }
        )
    candidates.sort(key=lambda x: x["score"], reverse=True)
    grouped = {}
    table_max = {}
    total_count = 0
    for c in candidates:
        if total_count >= total_limit:
            break
        t = c["table"]
        if t not in grouped:
            grouped[t] = []
            table_max[t] = c["score"]
        if per_table > 0 and len(grouped[t]) >= per_table:
            continue
        try:
            row_obj = json.loads(c["row_json"])
        except (TypeError, ValueError):
            row_obj = None
        grouped[t].append({"score": c["score"], "row": row_obj})
        if c["score"] > table_max.get(t, 0):
            table_max[t] = c["score"]
        total_count += 1

    # Garante que cada tabela prioritária com candidatos apareça pelo menos com 1 linha,
    # mesmo que tenha ficado de fora pelo corte de total_limit acima.
    priority_tables = cfg.get("priority_tables", []) or []
    if priority_tables:
        for p in priority_tables:
            if allowed_tables and p not in allowed_tables:
                continue
            if p in grouped:
                continue
            best = None
            for c in candidates:
                if c["table"] == p:
                    if best is None or c["score"] > best["score"]:
                        best = c
            if best is not None:
                try:
                    row_obj = json.loads(best["row_json"])
                except Exception:
                    row_obj = None
                grouped[p] = [{"score": best["score"], "row": row_obj}]
                table_max[p] = best["score"]
                total_count += 1

    # apply priority ordering
    ordered = {}
    for p in priority_tables:
        if p in grouped:
            ordered[p] = grouped.pop(p)
    remaining = sorted(grouped.keys(), key=lambda x: table_max.get(x, 0), reverse=True)
    for t in remaining:
        ordered[t] = grouped[t]
    return {
        "q": q,
        "q_norm": q_norm,
        "candidate_count": len(candidates),
        "returned_count": total_count,
        "results": ordered,
    }


# Fallback search for Access DBs via ODBC (pyodbc)
def fallback_search_access(
    access_path,
    q,
    per_table=10,
    candidate_limit=1000,
    total_limit=500,
    token_mode="any",
    min_score=None,
    max_tables=500,
    max_rows_per_table=2000,
):
    if pyodbc is None:
        return {"error": "pyodbc not installed; fallback unavailable"}
    q_norm = q.lower()
    tokens = [t for t in q_norm.split() if t]
    results = {}
    candidate_count = 0
    returned_count = 0
    conn = None
    try:
        conn_strs = [
            rf"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={access_path};",
            rf"Driver={{Microsoft Access Driver (*.mdb)}};DBQ={access_path};",
        ]
        last_err = None
        for cs in conn_strs:
            try:
                conn = pyodbc.connect(cs, autocommit=True, timeout=30)
                break
            except Exception as e:
                last_err = e
                conn = None
        if conn is None:
            return {"error": f"ODBC connect failed: {last_err}"}
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
                tables = []
        if not tables:
            return {"error": "No user tables found in Access DB."}
        tables = tables[:max_tables]

        def build_where_for_columns(cols):
            if not tokens:
                return None
            parts = []
            for col in cols:
                if token_mode == "any":
                    parts.append(" OR ".join([f"{col} LIKE ?" for _ in tokens]))
                else:
                    parts.append(" AND ".join([f"{col} LIKE ?" for _ in tokens]))
            return "(" + " OR ".join(parts) + ")" if parts else None

        for t in tables:
            cols = []
            try:
                cols_info = cur.columns(table=t)
                for c in cols_info:
                    col_name = getattr(c, "column_name", None) or (
                        c[3] if len(c) > 3 else None
                    )
                    data_type = None
                    try:
                        data_type = getattr(c, "type_name", None) or (
                            c[5] if len(c) > 5 else None
                        )
                    except (AttributeError, IndexError, TypeError):
                        data_type = None
                    if col_name:
                        cols.append(
                            (col_name, str(data_type).upper() if data_type else "")
                        )
            except Exception:
                try:
                    sample = cur.execute(f"SELECT TOP 1 * FROM [{t}]").fetchone()
                    if sample is not None:
                        desc = [d[0] for d in cur.description]
                        cols = [(name, "") for name in desc]
                except Exception:
                    cols = []
            text_cols = (
                [
                    c
                    for c, dt in cols
                    if any(x in dt for x in ("CHAR", "TEXT", "VARCHAR", "MEMO"))
                ]
                if cols
                else []
            )
            search_cols = (
                text_cols if text_cols else [c for c, _ in cols] if cols else []
            )
            if not search_cols:
                continue
            where_sql = build_where_for_columns(search_cols)
            params = []
            if where_sql:
                for _ in search_cols:
                    for tok in tokens:
                        params.append(f"%{tok}%")
                sql = f"SELECT TOP {max_rows_per_table} * FROM [{t}] WHERE {where_sql}"
            else:
                sql = f"SELECT TOP {max_rows_per_table} * FROM [{t}]"
            try:
                rows = (
                    cur.execute(sql, params).fetchall()
                    if params
                    else cur.execute(sql).fetchall()
                )
            except Exception:
                try:
                    rows = cur.execute(
                        f"SELECT TOP {max_rows_per_table} * FROM [{t}]"
                    ).fetchall()
                except Exception:
                    rows = []
            if not rows:
                continue
            desc = [d[0] for d in cur.description] if cur.description else []
            table_results = []
            for r in rows:
                try:
                    row_vals = [("" if v is None else str(v)) for v in r]
                    row_text = " ".join(row_vals).lower()
                except (TypeError, ValueError):
                    row_text = str(r).lower()
                score = fuzz.token_set_ratio(q_norm, row_text)
                if min_score is not None and score < min_score:
                    continue
                pk_col = None
                pk_val = None
                try:
                    if "id" in [c.lower() for c in desc]:
                        idx = [c.lower() for c in desc].index("id")
                        pk_col = desc[idx]
                        pk_val = r[idx]
                    else:
                        pk_col = desc[0] if desc else None
                        pk_val = r[0] if len(r) > 0 else None
                except (AttributeError, IndexError, TypeError):
                    pass
                row_json = {}
                try:
                    for i, cname in enumerate(desc):
                        row_json[cname] = r[i]
                except (AttributeError, IndexError, TypeError):
                    row_json = {"row": str(r)}
                table_results.append(
                    {
                        "score": int(score),
                        "pk_col": pk_col,
                        "pk_value": pk_val,
                        "row": row_json,
                    }
                )
                candidate_count += 1
                if candidate_count >= candidate_limit:
                    break
            if table_results:
                table_results.sort(key=lambda x: x["score"], reverse=True)
                results[t] = table_results[:per_table]
                returned_count += len(results[t])
                if returned_count >= total_limit:
                    break
        try:
            conn.close()
        except Exception:
            pass
        priority_tables = cfg.get("priority_tables", []) or []
        ordered = {}
        for p in priority_tables:
            if p in results:
                ordered[p] = results.pop(p)
        for t in sorted(
            results.keys(),
            key=lambda x: max([it["score"] for it in results[x]]) if results[x] else 0,
            reverse=True,
        ):
            ordered[t] = results[t]
        return {
            "q": q,
            "q_norm": q_norm,
            "candidate_count": candidate_count,
            "returned_count": returned_count,
            "results": ordered,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"error": str(e)}


@app.route("/api/search", methods=["GET"])
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "query param q required"}), 400
    try:
        per_table = int(request.args.get("per_table", 10))
        candidate_limit = int(request.args.get("candidate_limit", 1000))
        total_limit = int(request.args.get("total_limit", 500))
    except (TypeError, ValueError):
        return jsonify(
            {"error": "per_table/candidate_limit/total_limit must be integers"}
        ), 400
    token_mode = request.args.get("token_mode", "any").lower()
    if token_mode not in ("any", "all"):
        token_mode = "any"
    try:
        min_score = request.args.get("min_score", None)
        min_score = int(min_score) if min_score is not None else None
    except (TypeError, ValueError):
        min_score = None

    # Filtro opcional de tabelas: ?tables=TAB1,TAB2
    tables_param = request.args.get("tables")
    tables = None
    if tables_param:
        tables = [t.strip() for t in tables_param.split(",") if t.strip()]
    dbpath = get_db_path()
    if not dbpath:
        log_event("event=api_search_no_db")
        return jsonify({"error": "No DB selected"}), 400
    ext = Path(dbpath).suffix.lower()
    if ext in (".duckdb", ".db", ".sqlite", ".sqlite3"):
        return jsonify(
            api_search_duckdb(
                q,
                per_table,
                candidate_limit,
                total_limit,
                token_mode,
                min_score,
                tables=tables,
            )
        )
    elif ext in (".mdb", ".accdb"):
        fb = fallback_search_access(
            dbpath,
            q,
            per_table=per_table,
            candidate_limit=candidate_limit,
            total_limit=total_limit,
            token_mode=token_mode,
            min_score=min_score,
        )
        if isinstance(fb, dict) and fb.get("error"):
            log_event(f"event=api_search_error err={fb.get('error')}")
            return jsonify({"error": fb.get("error")}), 500
        return jsonify(fb)
    else:
        log_event(f"event=api_search_unsupported db={dbpath}")
        return jsonify({"error": f"Unsupported DB format: {dbpath}"}), 400


if __name__ == "__main__":
    save_config(cfg)
    app.run(host="127.0.0.1", port=5000, debug=True)
