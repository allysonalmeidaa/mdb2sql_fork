#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_single_table_by_column.py

Objetivo
- Analisar UMA tabela de UM banco por coluna, lendo linha a linha (streaming) e produzindo:
  - summary_by_column.csv com métricas por coluna
  - columns/<COL>__top_<N>.csv com os valores mais frequentes por coluna
  - charts/<COL>__top_<N>.png com gráfico de barras dos top valores

Destaques (o que este script calcula/gera)
- Para colunas numéricas (detectadas por heurística robusta):
  - Estatísticas valor-level exatas via Welford (streaming):
    * mean (média)
    * variancia (populacional = M2/N)
    * desvio_padrao_pop (populacional)
    * variancia_amostral (M2/(N-1), se N>1)
    * desvio_padrao_amostral (amostral)
    * coef_variacao = desvio_padrao_pop / mean (0 se mean==0)
    * min, max
  - Quantis aproximados (q25_approx, median_approx, q75_approx) via reservoir sampling
- Para colunas de texto:
  - Contagem de nulos, estimativa de distintos, top valores (CSV + gráfico)
- Em todas as colunas:
  - top1_val, top1_count, top1_pct_of_column (AGORA usando denominador = linhas_lidas - nulos)
  - linhas_lidas, nulos, linhas_nao_nulas, distinct_est, distinct_cap_excedido

Robustez p/ Access (pyodbc) e formatos “estranhos”:
- Detecta e converte números apresentados como:
  * Decimal (objeto), "Decimal('119')", "(119,)", "('119',)" etc.
- Decide tipo_aparente no FINAL do streaming: "numérico" se ≥60% dos não-nulos forem parseados como número.

Fallbacks SQL (garantia de resultado):
- Se o streaming falhar para uma coluna:
  * COUNT(*), COUNT(IS NULL), COUNT DISTINCT (se possível)
  * TOP-N via GROUP BY
  * Inferência de tipo baseada no TOP-1

Suportado:
- SQLite (.sqlite/.sqlite3/.db), DuckDB (.duckdb), Access (.mdb/.accdb via pyodbc)

Uso (exemplo - PowerShell):
  python tools/analyze_single_table_by_column.py --db "./import_folder/bancos_atuais/2025-11-05_DB4.accdb" --table "RANGER_SOSTAT" --engine access --outdir "./import_folder/analises" --top 50 -v
Uso (exemplo - Bash/Zsh):
  python tools/analyze_single_table_by_column.py --db "./import_folder/bancos_atuais/2025-11-05_DB4.accdb" --table "RANGER_SOSTAT" --engine access --outdir "./import_folder/analises" --top 50 -v
"""

from pathlib import Path
import argparse
import csv
import sqlite3
import sys
import time
import math
import re
from decimal import Decimal
from collections import Counter
import pandas as pd
import matplotlib.pyplot as plt
import random
import numpy as np

# opcionais
try:
    import duckdb
except Exception:
    duckdb = None
try:
    import pyodbc
except Exception:
    pyodbc = None

# ---------------- estatistica (Welford) ----------------


class Welford:
    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0
        self.min = None
        self.max = None

    def add(self, x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return
        self.n += 1
        if self.min is None or x < self.min:
            self.min = x
        if self.max is None or x > self.max:
            self.max = x
        d = x - self.mean
        self.mean += d / self.n
        d2 = x - self.mean
        self.M2 += d * d2

    def var_pop(self):
        return (self.M2 / self.n) if self.n > 0 else 0.0

    def std_pop(self):
        return math.sqrt(self.var_pop()) if self.n > 0 else 0.0

    def var_sample(self):
        return (self.M2 / (self.n - 1)) if self.n > 1 else 0.0

    def std_sample(self):
        return math.sqrt(self.var_sample()) if self.n > 1 else 0.0


class ReservoirSampler:
    def __init__(self, k):
        self.k = int(k)
        self.n = 0
        self.sample = []

    def add(self, x):
        self.n += 1
        if len(self.sample) < self.k:
            self.sample.append(x)
        else:
            i = random.randint(1, self.n)
            if i <= self.k:
                self.sample[i - 1] = x

    def get_sample(self):
        return self.sample


# ---------------- normalizacao/conversao de valores ----------------
_DECIMAL_RE = re.compile(r"""^\s*Decimal\(\s*'(?P<num>[^']+)'\s*\)\s*$""")
_TUPLE_ONE_RE = re.compile(r"""^\s*\(\s*'?(?P<inner>[^']+?)'?\s*,\s*\)\s*$""")


def try_parse_number(v):
    """
    Tenta converter 'v' para float.
    - Aceita: Decimal, strings "Decimal('119')", "(119,)", "('119',)", " 1 234,56 % " etc.
    - Retorna float ou None (se não for número).
    """
    if v is None:
        return None
    if isinstance(v, Decimal):
        try:
            return float(v)
        except Exception:
            return None
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8", errors="ignore")
        except Exception:
            v = str(v)
    s = str(v).strip()

    m = _TUPLE_ONE_RE.match(s)
    if m:
        s = m.group("inner").strip()

    m = _DECIMAL_RE.match(s)
    if m:
        s = m.group("num").strip()

    # limpeza básica
    s = s.replace("%", "").replace(" ", "")
    # vírgula decimal pt-BR (se não houver ponto decimal)
    if "," in s and "." not in s:
        s = s.replace(".", "")  # remove separador de milhar com ponto (se existir)
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def to_nice_number_str(x):
    """Converte float em string 'bonita': 119.0 -> '119', 119.50 -> '119.5'."""
    try:
        if x is None:
            return ""
        f = float(x)
        if abs(f - round(f)) < 1e-12:
            return str(int(round(f)))
        s = f"{f:.12g}"
        return s
    except Exception:
        return str(x)


def clean_value_for_top(v):
    """
    Limpa valor para escrita no CSV de top values (texto):
    - remove wrappers Decimal('...'), ('...'), ( ... ,)
    - se número, normaliza
    """
    if v is None:
        return ""
    if isinstance(v, (int, float, np.number, Decimal)):
        try:
            return to_nice_number_str(float(v))
        except Exception:
            return str(v)
    s = str(v).strip()
    m = _TUPLE_ONE_RE.match(s)
    if m:
        s = m.group("inner").strip()
    m = _DECIMAL_RE.match(s)
    if m:
        s = m.group("num").strip()
    # normaliza casos numéricos em string
    xf = try_parse_number(s)
    if xf is not None:
        return to_nice_number_str(xf)
    return s


# ---------------- conexões ----------------
def detect_engine(db_path: Path):
    sfx = db_path.suffix.lower()
    if sfx == ".duckdb" and duckdb is not None:
        return "duckdb"
    if sfx in (".sqlite", ".sqlite3") or (sfx == ".db" and duckdb is None):
        return "sqlite"
    if sfx in (".mdb", ".accdb"):
        return "access"
    return "sqlite"


def open_conn(db_path: Path, engine: str):
    if engine == "duckdb":
        if duckdb is None:
            raise RuntimeError("duckdb não está instalado")
        return duckdb.connect(str(db_path))
    if engine == "sqlite":
        return sqlite3.connect(str(db_path))
    if engine == "access":
        if pyodbc is None:
            raise RuntimeError("pyodbc necessário para Access (.mdb/.accdb).")
        conn_strs = [
            rf"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={str(db_path)};",
            rf"Driver={{Microsoft Access Driver (*.mdb)}};DBQ={str(db_path)};",
        ]
        last = None
        for cs in conn_strs:
            try:
                return pyodbc.connect(cs, autocommit=True, timeout=30)
            except Exception as e:
                last = e
        if last is not None:
            raise last
        raise RuntimeError("Falha ao conectar via ODBC")
    raise RuntimeError("engine desconhecida: " + str(engine))


def list_columns(db_path: Path, table: str, engine: str):
    conn = open_conn(db_path, engine)
    try:
        if engine == "duckdb":
            cur = conn.execute(f'SELECT * FROM "{table}" LIMIT 0')
            return [c[0] for c in cur.description]
        if engine == "sqlite":
            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{table}")')
            return [r[1] for r in cur.fetchall()]
        cur = conn.cursor()  # Access
        cur.execute(f"SELECT TOP 1 * FROM [{table}]")
        return [d[0] for d in cur.description] if cur.description else []
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------- helpers SQL (fallbacks e contagens) ----------------
def sql_count_total(db_path: Path, table: str, engine: str):
    q = (
        f'SELECT COUNT(*) FROM "{table}"'
        if engine != "access"
        else f"SELECT COUNT(*) FROM [{table}]"
    )
    conn = open_conn(db_path, engine)
    try:
        if engine == "duckdb":
            row = conn.execute(q).fetchone()
            return int(row[0]) if row else 0
        cur = conn.cursor()
        cur.execute(q)
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sql_count_nulls(db_path: Path, table: str, col: str, engine: str):
    q = (
        f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NULL'
        if engine != "access"
        else f"SELECT COUNT(*) FROM [{table}] WHERE [{col}] IS NULL"
    )
    conn = open_conn(db_path, engine)
    try:
        if engine == "duckdb":
            row = conn.execute(q).fetchone()
            return int(row[0]) if row else 0
        cur = conn.cursor()
        cur.execute(q)
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sql_count_distinct(db_path: Path, table: str, col: str, engine: str):
    if engine in ("duckdb", "sqlite"):
        q = f'SELECT COUNT(DISTINCT "{col}") FROM "{table}"'
    else:
        q = f"SELECT COUNT(*) FROM (SELECT DISTINCT [{col}] FROM [{table}])"
    conn = open_conn(db_path, engine)
    try:
        if engine == "duckdb":
            row = conn.execute(q).fetchone()
            return int(row[0]) if row else 0
        cur = conn.cursor()
        cur.execute(q)
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sql_top_values_fallback(
    db_path: Path, table: str, col: str, engine: str, limit: int = 50
):
    try:
        if engine in ("duckdb", "sqlite"):
            q = f'SELECT "{col}" as value, COUNT(*) as cnt FROM "{table}" GROUP BY "{col}" ORDER BY cnt DESC LIMIT {limit}'
            conn = open_conn(db_path, engine)
            rows = conn.execute(q).fetchall()
            return [(r[0], int(r[1])) for r in rows]
        conn = open_conn(db_path, engine)
        cur = conn.cursor()
        q = f"SELECT TOP {limit} [{col}] as value, COUNT(*) as cnt FROM [{table}] GROUP BY [{col}] ORDER BY COUNT(*) DESC"
        cur.execute(q)
        rows = cur.fetchall()
        return [(r[0], int(r[1])) for r in rows]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def infer_tipo_aparente_fallback(db_path: Path, table: str, col: str, engine: str):
    vals = sql_top_values_fallback(db_path, table, col, engine, limit=1)
    if not vals:
        return "desconhecido"
    v = vals[0][0]
    if v is None:
        return "desconhecido"
    return "numérico" if try_parse_number(v) is not None else "texto"


# ---------------- streaming values ----------------
def stream_column_values(
    db_path: Path, table: str, col: str, engine: str, batch_size: int = 2000
):
    if engine == "duckdb":
        conn = open_conn(db_path, engine)
        try:
            cur = conn.execute(f'SELECT "{col}" FROM "{table}"')
            try:
                while True:
                    batch = cur.fetchmany(batch_size)
                    if not batch:
                        break
                    for row in batch:
                        yield row[0]
            except Exception:
                for row in cur.fetchall():
                    yield row[0]
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return

    conn = open_conn(db_path, engine)
    try:
        cur = conn.cursor()
        q = (
            f"SELECT [{col}] FROM [{table}]"
            if engine == "access"
            else f'SELECT "{col}" FROM "{table}"'
        )
        cur.execute(q)
        while True:
            batch = cur.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                yield row[0] if not isinstance(row, (list, tuple)) else row[0]
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------- principal ----------------
def analyze_table(
    db_path: Path,
    table: str,
    outdir: Path,
    engine: str | None = None,
    top: int = 20,
    sample_size: int = 5000,
    distinct_cap: int = 200000,
    verbose: bool = False,
):
    db_path = Path(db_path)
    engine = engine or detect_engine(db_path)
    if verbose:
        print(f"[info] engine: {engine}")

    cols = list_columns(db_path, table, engine)
    if not cols:
        raise RuntimeError(f"Tabela {table} não encontrada ou sem colunas.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    base_out = outdir / f"{table}__{ts}"
    cols_dir = base_out / "columns"
    charts_dir = base_out / "charts"
    base_out.mkdir(parents=True, exist_ok=True)
    cols_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for col in cols:
        if verbose:
            print(f"[processando] {col}")

        total = 0
        nulls = 0
        counter = Counter()
        distinct_set = set()
        distinct_overflow = False
        w = Welford()
        sampler = ReservoirSampler(sample_size)
        type_apparent = None
        streaming_ok = True
        numeric_hits = 0
        text_hits = 0

        # tentar streaming
        try:
            for v in stream_column_values(db_path, table, col, engine):
                total += 1
                if v is None:
                    nulls += 1
                    continue

                xf = try_parse_number(v)
                if xf is not None:
                    numeric_hits += 1
                    # estatística numérica
                    w.add(xf)
                    sampler.add(xf)
                    # também contar para top-values (numeric) usando representação bonita
                    key = to_nice_number_str(xf)
                    counter[key] += 1
                    # distinct
                    if distinct_set is not None:
                        if len(distinct_set) <= distinct_cap:
                            distinct_set.add(key)
                        else:
                            distinct_overflow = True
                            distinct_set = None
                else:
                    text_hits += 1
                    sval = clean_value_for_top(v)
                    counter[sval] += 1
                    if distinct_set is not None:
                        if len(distinct_set) <= distinct_cap:
                            distinct_set.add(sval)
                        else:
                            distinct_overflow = True
                            distinct_set = None
                    sampler.add(sval)
        except Exception as e:
            streaming_ok = False
            if verbose:
                print(f"  [aviso] streaming falhou em {col}: {e}")

        # decidir tipo por maioria dos não-nulos
        non_null_seen = numeric_hits + text_hits
        if non_null_seen > 0 and numeric_hits >= 0.6 * non_null_seen:
            type_apparent = "numérico"
        elif non_null_seen > 0:
            type_apparent = "texto"

        # fallbacks se streaming falhar
        if not streaming_ok:
            try:
                total = sql_count_total(db_path, table, engine)
            except Exception:
                total = total or 0
            try:
                nulls = sql_count_nulls(db_path, table, col, engine)
            except Exception:
                nulls = nulls or 0
            try:
                t = infer_tipo_aparente_fallback(db_path, table, col, engine)
                type_apparent = type_apparent or t
            except Exception:
                type_apparent = type_apparent or "desconhecido"
            # obter top por GROUP BY (pelo menos para o relatório)
            try:
                for vv, cc in sql_top_values_fallback(
                    db_path, table, col, engine, limit=top
                ):
                    counter[clean_value_for_top(vv)] += int(cc)
            except Exception:
                pass
            # distinct estimado
            try:
                d = sql_count_distinct(db_path, table, col, engine)
                if d is not None:
                    if distinct_set is not None and d <= distinct_cap:
                        # representamos com cardinalidade (sem guardar os valores)
                        distinct_set = set(range(d))
                    else:
                        distinct_set = None
                        distinct_overflow = True
            except Exception:
                pass

        # top values
        top_vals = counter.most_common(top)

        # salvar CSV top
        top_csv_path = cols_dir / f"{col}__top_{top}.csv"
        with open(top_csv_path, "w", newline="", encoding="utf-8") as fh:
            wcsv = csv.writer(fh)
            wcsv.writerow(["valor", "contagem"])
            for val, cnt in top_vals:
                wcsv.writerow([clean_value_for_top(val), int(cnt)])

        # quantis aproximados (somente se numérico)
        q25 = q50 = q75 = ""
        if type_apparent == "numérico" and sampler.sample:
            try:
                arr = np.array(
                    [float(x) for x in sampler.sample if x is not None], dtype=float
                )
                if arr.size > 0:
                    q25 = float(np.percentile(arr, 25))
                    q50 = float(np.percentile(arr, 50))
                    q75 = float(np.percentile(arr, 75))
            except Exception:
                q25 = q50 = q75 = ""

        # TOP1
        top1_val = top_vals[0][0] if top_vals else ""
        top1_count = int(top_vals[0][1]) if top_vals else 0

        # % sobre NÃO NULOS
        non_null = max(0, total - nulls)
        top1_pct = (
            round(100.0 * top1_count / non_null, 3)
            if (non_null and top1_count)
            else None
        )

        # distinct
        distinct_est = -1 if distinct_set is None else len(distinct_set)

        # estatística (pop e amostral)
        variancia_pop = w.var_pop() if w.n > 0 else 0.0
        desvio_pop = w.std_pop() if w.n > 0 else 0.0
        variancia_sample = w.var_sample() if w.n > 1 else 0.0
        desvio_sample = w.std_sample() if w.n > 1 else 0.0
        coef_variacao = (desvio_pop / w.mean) if (w.n > 0 and w.mean != 0) else 0.0
        top1_domina = top1_pct is not None and top1_pct >= 50.0

        summary_rows.append(
            {
                "coluna": col,
                "tipo_aparente": type_apparent or "",
                "linhas_lidas": total,
                "nulos": nulls,
                "linhas_nao_nulas": non_null,
                "distinct_est": distinct_est,
                "distinct_cap_excedido": bool(distinct_overflow),
                "value_count": w.n,
                "mean": w.mean if w.n > 0 else 0.0,
                "M2": w.M2 if w.n > 0 else 0.0,
                "variancia": variancia_pop,
                "desvio_padrao_pop": desvio_pop,
                "variancia_amostral": variancia_sample,
                "desvio_padrao_amostral": desvio_sample,
                "coef_variacao": coef_variacao,
                "min": w.min if w.min is not None else "",
                "q25_approx": q25,
                "median_approx": q50,
                "q75_approx": q75,
                "max": w.max if w.max is not None else "",
                "top1_val": "" if top1_val is None else top1_val,
                "top1_count": top1_count,
                "top1_pct_of_column": top1_pct,  # % sobre NÃO NULOS
                "top1_domina": top1_domina,
                "top_values_csv": str(top_csv_path),
                "chart_png": "",
            }
        )

        # gráfico top
        labels = [("" if v is None else str(v)) for v, cnt in top_vals]
        counts = [int(cnt) for v, cnt in top_vals]
        if (
            distinct_est
            and isinstance(distinct_est, int)
            and distinct_est > len(top_vals)
            and non_null
        ):
            others = max(0, non_null - sum(counts))
            if others > 0:
                labels.append("OUTROS")
                counts.append(others)
        if counts:
            fig, ax = plt.subplots(figsize=(8, max(2, 0.4 * len(labels))))
            y = list(range(len(labels)))
            ax.barh(y, counts, color="steelblue")
            ax.set_yticks(y)
            ax.set_yticklabels(labels, fontsize=9)
            ax.invert_yaxis()
            ax.set_xlabel("Contagem absoluta")
            ax.set_title(f"Top {len(labels)} valores em {col}")
            plt.tight_layout()
            chart_path = charts_dir / f"{col}__top_{top}.png"
            try:
                fig.savefig(str(chart_path), dpi=150)
                summary_rows[-1]["chart_png"] = str(chart_path)
            except Exception as e:
                if verbose:
                    print(f"  [aviso] falha ao salvar gráfico {col}: {e}")
            plt.close(fig)

    # salvar summary
    summary_path = base_out / "summary_by_column.csv"
    df = pd.DataFrame(summary_rows)
    preferred = [
        "coluna",
        "tipo_aparente",
        "linhas_lidas",
        "nulos",
        "linhas_nao_nulas",
        "distinct_est",
        "distinct_cap_excedido",
        "value_count",
        "mean",
        "M2",
        "variancia",
        "desvio_padrao_pop",
        "variancia_amostral",
        "desvio_padrao_amostral",
        "coef_variacao",
        "min",
        "q25_approx",
        "median_approx",
        "q75_approx",
        "max",
        "top1_val",
        "top1_count",
        "top1_pct_of_column",
        "top1_domina",
        "top_values_csv",
        "chart_png",
    ]
    cols = [c for c in preferred if c in df.columns] + [
        c for c in df.columns if c not in preferred
    ]
    df[cols].to_csv(summary_path, index=False, encoding="utf-8")

    print("\nConcluído. Saída em:", base_out)
    print("Resumo:", summary_path)
    return base_out


# ---------------- CLI ----------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Analisar uma tabela por coluna e gerar contagens, gráficos e estatísticas valor-level."
    )
    p.add_argument(
        "--db",
        required=True,
        help="Caminho para o arquivo de banco (SQLite / DuckDB / Access).",
    )
    p.add_argument("--table", required=True, help="Nome da tabela a analisar.")
    p.add_argument(
        "--engine",
        choices=["sqlite", "duckdb", "access"],
        help="Forçar engine (opcional).",
    )
    p.add_argument(
        "--outdir",
        default=".",
        help="Diretório base de saída (será criada subpasta com timestamp).",
    )
    p.add_argument(
        "--top", type=int, default=20, help="Top N valores por coluna a listar/plotar."
    )
    p.add_argument(
        "--sample-size",
        type=int,
        default=5000,
        help="Tamanho da amostra por coluna para quantis aproximados.",
    )
    p.add_argument(
        "--distinct-cap",
        type=int,
        default=200000,
        help="Cap para distinct (se exceder, não manter set completo).",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose")
    return p.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print("Arquivo de banco não encontrado:", db_path)
        sys.exit(1)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    analyze_table(
        db_path,
        args.table,
        outdir,
        engine=args.engine,
        top=args.top,
        sample_size=args.sample_size,
        distinct_cap=args.distinct_cap,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    main()
