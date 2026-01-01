#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_analyze_all_dbs.py (atualizado)

O que faz
- Percorre um diretório (recursivo), encontra arquivos de banco por extensão
- Para cada arquivo, executa analyze_single_table_by_column.py
- Organiza a saída em subpastas por arquivo dentro de --outdir, mantendo
  a mesma organização do modo “um único banco” (cada execução do analyze gera
  a pasta <TABELA>__<timestamp> com summary_by_column.csv, columns/, charts/)

Destaques da atualização
- Adicionadas flags --sample-size e --distinct-cap (repassem para o analyze)
- Padrão de TOP = 50 (alinha com seus usos atuais)
- Logs mais claros por arquivo (ok/erro)
- Sem alterar a organização da saída do analyze (continua idêntica ao modo 1-banco)

Uso (PowerShell):
  python tools/batch_analyze_all_dbs.py --db-dir "./import_folder/bancos_atuais" --table "RANGER_SOSTAT" --outdir "./import_folder/analises" --extensions .accdb .mdb .duckdb .sqlite .db --top 50 --sample-size 5000 -v
Uso (Bash/Zsh):
  python tools/batch_analyze_all_dbs.py --db-dir "./import_folder/bancos_atuais" --table "RANGER_SOSTAT" --outdir "./import_folder/analises" --extensions .accdb .mdb .duckdb .sqlite .db --top 50 --sample-size 5000 -v
"""

from pathlib import Path
import argparse
import subprocess
import sys

EXT_TO_ENGINE = {
    ".accdb": "access",
    ".mdb": "access",
    ".duckdb": "duckdb",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".db": "sqlite",  # ajuste manual se seu .db for DuckDB
}


def detect_engine_from_ext(path: Path, override_engine=None):
    if override_engine:
        return override_engine
    return EXT_TO_ENGINE.get(path.suffix.lower(), "sqlite")


def gather_files(db_dir: Path, exts):
    files = []
    for ext in exts:
        patt = ext if ext.startswith(".") else f".{ext}"
        files += list(db_dir.rglob(f"*{patt}"))
    # remover duplicados e ordenar por mtime
    unique = sorted(
        {f.resolve(): f for f in files}.values(), key=lambda p: p.stat().st_mtime
    )
    return unique


def run_analyze_for_file(
    py_exe,
    analyze_script,
    db_file: Path,
    table: str,
    engine: str,
    outdir: Path,
    top: int,
    distinct_cap: int,
    sample_size: int,
    verbose: bool,
):
    per_out = outdir / db_file.stem
    per_out.mkdir(parents=True, exist_ok=True)
    cmd = [
        py_exe,
        str(analyze_script),
        "--db",
        str(db_file),
        "--table",
        table,
        "--engine",
        engine,
        "--outdir",
        str(per_out),
        "--top",
        str(top),
        "--distinct-cap",
        str(distinct_cap),
        "--sample-size",
        str(sample_size),
    ]
    if verbose:
        cmd.append("-v")
        print("[cmd]", " ".join(cmd))
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return res.returncode, res.stdout


def parse_args():
    p = argparse.ArgumentParser(
        description="Executar analyze_single_table_by_column.py em lote para múltiplos arquivos."
    )
    p.add_argument(
        "--db-dir",
        required=True,
        help="Diretório base contendo os arquivos de banco (recursivo).",
    )
    p.add_argument(
        "--table", required=True, help="Nome da tabela a analisar em cada banco."
    )
    p.add_argument(
        "--outdir",
        required=True,
        help="Diretório base onde serão gravadas as pastas por arquivo.",
    )
    p.add_argument(
        "--extensions",
        nargs="*",
        default=[".accdb", ".mdb", ".duckdb", ".sqlite", ".db"],
        help="Extensões a procurar.",
    )
    p.add_argument(
        "--python-exe",
        default=sys.executable,
        help="Executável Python a usar (por padrão o atual).",
    )
    p.add_argument(
        "--analyze-script",
        default="tools/analyze_single_table_by_column.py",
        help="Caminho do script de análise (por arquivo).",
    )
    p.add_argument("--top", type=int, default=50, help="Top N valores por coluna.")
    p.add_argument(
        "--sample-size",
        type=int,
        default=5000,
        help="Tamanho da amostra para quantis aproximados no analyze.",
    )
    p.add_argument(
        "--distinct-cap", type=int, default=200000, help="Cap de distinct no analyze."
    )
    p.add_argument(
        "--engine-override",
        choices=["sqlite", "duckdb", "access"],
        help="Forçar a engine para todos os arquivos (opcional).",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose")
    return p.parse_args()


def main():
    args = parse_args()
    db_dir = Path(args.db_dir)
    if not db_dir.exists():
        print("Diretório não encontrado:", db_dir)
        return 1
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    exts = [e if e.startswith(".") else "." + e for e in args.extensions]

    files = gather_files(db_dir, exts)
    if not files:
        print("Nenhum arquivo encontrado com as extensões fornecidas em", db_dir)
        return 1

    analyze_script = Path(args.analyze_script)
    if not analyze_script.exists():
        print("Script de análise não encontrado:", analyze_script)
        return 1

    total = len(files)
    failed = []
    print(f"Encontrados {total} arquivos. Iniciando processamento...\n")
    for idx, f in enumerate(files, start=1):
        engine = detect_engine_from_ext(f, args.engine_override)
        if args.verbose:
            print(f"[{idx}/{total}] {f} (engine={engine})")
        code, out = run_analyze_for_file(
            args.python_exe,
            analyze_script,
            f,
            args.table,
            engine,
            outdir,
            args.top,
            args.distinct_cap,
            args.sample_size,
            args.verbose,
        )
        if args.verbose:
            print(out)
        if code != 0:
            print(f"[erro] Falha no arquivo {f.name} (exit {code})")
            failed.append((f.name, out))
        else:
            if args.verbose:
                print(f"[ok] {f.name}")

    print(f"\nConcluído. Total arquivos: {total}. Falhas: {len(failed)}")
    if failed:
        print("Arquivos com falha (nome e trecho de log):")
        for n, log in failed:
            print(" -", n, " ->", (log or "")[:300].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
