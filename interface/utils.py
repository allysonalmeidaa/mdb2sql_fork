# utils.py
# Funções utilitárias: normalização e serialização para DuckDB local search pipeline.

import decimal
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path


def normalize_text(s: str) -> str:
    """
    Normaliza texto:
      - remove acentos
      - lower-case
      - substitui pontuação por espaço
      - substitui hífen/underscore por espaço
      - colapsa espaços
    Retorna string vazia para None.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return ""
    # remover acentos
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    # substituir pontuação por espaço (mantém letras, números e underscore)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    # substituir underscores/hyphens por espaço
    s = re.sub(r"[_\-]+", " ", s)
    # colapsar espaços
    s = re.sub(r"\s+", " ", s).strip()
    return s


def serialize_value(v):
    """Converte tipos retornados pelo DuckDB em valores JSON-compatíveis (pronto para json.dumps)."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        # representamos decimal como float (pode ajustar para str se preferir precisão)
        return float(v)
    if isinstance(v, memoryview):
        try:
            return v.tobytes().decode("utf-8", errors="replace")
        except Exception:
            return repr(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            return bytes(v).decode("utf-8", errors="replace")
        except Exception:
            return repr(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    # fallback
    try:
        return str(v)
    except Exception:
        return None


def resolve_db_path(explicit_path=None, uploads_dir=None):
    if explicit_path:
        return Path(explicit_path)
    env_path = os.environ.get("DB_PATH", "").strip()
    if env_path:
        return Path(env_path)
    if uploads_dir is None:
        uploads_dir = Path(__file__).resolve().parent / "uploads"
    if not uploads_dir.exists():
        return None
    candidates = list(uploads_dir.glob("*.duckdb"))
    if not candidates:
        return None
    if len(candidates) > 1:
        raise ValueError(
            f"Multiple .duckdb files found in {uploads_dir}. Set DB_PATH or use --db to select."
        )
    return candidates[0]


def clamp_int(value, default, min_value=0, max_value=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result < min_value:
        result = min_value
    if max_value is not None and result > max_value:
        result = max_value
    return result
