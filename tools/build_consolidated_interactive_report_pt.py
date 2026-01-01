#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_consolidated_interactive_report_pt.py (rótulos autoexplicativos)

Resumo:
- Lê a pasta de análise MAIS RECENTE "<TABELA>__*" (ou uma pasta específica se você passar diretamente).
- Mostra tabela resumo focada em:
    COLUNA | TIPO | DISTINTOS (est.) | NULOS (%) | MÉDIA | DESVIO (pop.) | VAR (pop.) | CV |
    Valor mais frequente | % do valor mais frequente (entre não nulos)
- Se quiser a visão completa (com linhas, min, mediana, max, ocorrências do valor mais frequente), use --mode full.
- “Valor mais frequente” é o valor que mais aparece na coluna (moda); o percentual é calculado entre registros não nulos, quando disponível.

Uso (PowerShell):
  python tools/build_consolidated_interactive_report_pt.py --analises "./import_folder/analises" --table "RANGER_SOSTAT" --out "./import_folder/analises/relatorio_sostat_interativo.html" --top-n 50 --mode slim
Uso (Bash/Zsh):
  python tools/build_consolidated_interactive_report_pt.py --analises "./import_folder/analises" --table "RANGER_SOSTAT" --out "./import_folder/analises/relatorio_sostat_interativo.html" --top-n 50 --mode slim
"""

from pathlib import Path
import argparse
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import base64
import math
from typing import Any

pio.templates.default = "plotly_white"


def find_latest_analysis_folder(base_dir: Path, table_name: str):
    candidates = sorted(
        [
            d
            for d in base_dir.iterdir()
            if d.is_dir() and d.name.startswith(f"{table_name}__")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_summary_folder(folder: Path):
    summary_csv = folder / "summary_by_column.csv"
    if not summary_csv.exists():
        raise FileNotFoundError(f"summary_by_column.csv não encontrado em {folder}")
    df = pd.read_csv(summary_csv, dtype=str)

    # conversões numéricas relevantes
    num_cols = [
        "linhas_lidas",
        "linhas_nao_nulas",
        "nulos",
        "distinct_est",
        "mean",
        "variancia",
        "desvio_padrao_pop",
        "coef_variacao",
        "top1_count",
        "top1_pct_of_column",
        "top1_pct_of_table",
        "min",
        "median_approx",
        "q25_approx",
        "q75_approx",
        "max",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # nulos (%) para exibir na tabela
    if "linhas_lidas" in df.columns and "nulos" in df.columns:
        with pd.option_context("mode.use_inf_as_na", True):
            df["nulos_pct"] = (df["nulos"] / df["linhas_lidas"] * 100.0).round(3)
    else:
        df["nulos_pct"] = None

    return df


def read_top_values_csv(csv_path: Path):
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, header=0)
        cols = list(df.columns)
        if len(cols) >= 2:
            df = df.rename(columns={cols[0]: "valor", cols[1]: "contagem"})[
                ["valor", "contagem"]
            ]
        else:
            df.columns = ["valor", "contagem"]
        df["contagem"] = (
            pd.to_numeric(df["contagem"], errors="coerce").fillna(0).astype(int)
        )
        return df
    except Exception:
        return None


def fig_from_top_values(df_top: pd.DataFrame, title: str):
    if df_top is None or df_top.empty:
        return None
    labels = df_top["valor"].astype(str).tolist()
    counts = df_top["contagem"].astype(int).tolist()
    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color="steelblue",
            hovertemplate="%{y}: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        height=max(300, 25 * len(labels)),
        margin=dict(l=250, r=30, t=40, b=30),
        xaxis_title="Contagem absoluta",
        yaxis_title="Valor",
    )
    return fig


def embed_png_base64(png_path: Path):
    if not png_path.exists():
        return ""
    b = png_path.read_bytes()
    enc = base64.b64encode(b).decode("ascii")
    return f"data:image/png;base64,{enc}"


def fmt_num(v, decimals=3):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return ""
        vf = float(v)
        if abs(vf - round(vf)) < 1e-9:
            return str(int(round(vf)))
        return f"{vf:.{decimals}f}"
    except Exception:
        return str(v) if v is not None else ""


def build_table_html(summary_df: pd.DataFrame, mode: str):
    # Escolha dos rótulos autoexplicativos
    slim_cols = [
        ("coluna", "COLUNA"),
        ("tipo_aparente", "TIPO"),
        ("distinct_est", "DISTINTOS (est.)"),
        ("nulos_pct", "NULOS (%)"),
        ("mean", "MÉDIA"),
        ("desvio_padrao_pop", "DESVIO (pop.)"),
        ("variancia", "VAR (pop.)"),
        ("coef_variacao", "CV"),
        ("top1_val", "Valor mais frequente"),
    ]
    pct_col = (
        "top1_pct_of_column"
        if "top1_pct_of_column" in summary_df.columns
        else (
            "top1_pct_of_table" if "top1_pct_of_table" in summary_df.columns else None
        )
    )
    if pct_col:
        slim_cols.append(
            (
                pct_col,
                "% do valor mais frequente (entre não nulos)"
                if pct_col == "top1_pct_of_column"
                else "% do valor mais frequente (na tabela)",
            )
        )

    full_cols = [
        ("coluna", "COLUNA"),
        ("tipo_aparente", "TIPO"),
        ("linhas_lidas", "LINHAS (lidas)"),
        ("linhas_nao_nulas", "NÃO NULOS"),
        ("nulos", "NULOS"),
        ("distinct_est", "DISTINTOS (est.)"),
        ("mean", "MÉDIA"),
        ("desvio_padrao_pop", "DESVIO (pop.)"),
        ("variancia", "VAR (pop.)"),
        ("coef_variacao", "CV"),
        ("min", "MIN"),
        ("median_approx", "MEDIANA (aprox.)"),
        ("max", "MAX"),
        ("top1_val", "Valor mais frequente"),
        ("top1_count", "Ocorrências do valor mais frequente"),
    ]
    if pct_col:
        full_cols.append(
            (
                pct_col,
                "% do valor mais frequente (entre não nulos)"
                if pct_col == "top1_pct_of_column"
                else "% do valor mais frequente (na tabela)",
            )
        )
    if "top_values_csv" in summary_df.columns:
        full_cols.append(("top_values_csv", "CSV (top valores)"))

    chosen = full_cols if mode == "full" else slim_cols
    headers = [h for _, h in chosen]
    values = []
    for col, _h in chosen:
        if col in summary_df.columns:
            if col in (
                "mean",
                "desvio_padrao_pop",
                "variancia",
                "coef_variacao",
                "nulos_pct",
                pct_col,
            ):
                values.append(summary_df[col].apply(fmt_num).astype(str).tolist())
            else:
                values.append(summary_df[col].fillna("").astype(str).tolist())
        else:
            values.append([""] * len(summary_df))

    # cores por % do valor mais frequente (se existir)
    fill_colors = []
    series = summary_df[pct_col] if pct_col and pct_col in summary_df.columns else None
    for i in range(len(summary_df)):
        val = (
            float(series.iloc[i])
            if series is not None and pd.notna(series.iloc[i])
            else 0.0
        )
        if val >= 10.0:
            fill_colors.append("#dff0d8")  # verde claro (valor dominante)
        elif val >= 2.0:
            fill_colors.append(
                "#fff7bf"
            )  # amarelo claro (valor relativamente frequente)
        else:
            fill_colors.append("#ffffff")

    table_fig = go.Figure(
        go.Table(
            header=dict(values=headers, fill_color="lightgrey", align="left"),
            cells=dict(
                values=values, fill_color=[fill_colors], align="left", font_size=12
            ),
        )
    )
    include_plotlyjs: Any = "cdn"
    return pio.to_html(table_fig, full_html=False, include_plotlyjs=include_plotlyjs)


def build_html(
    summary_df: pd.DataFrame,
    analysis_folder: Path,
    table_name: str,
    out_file: Path,
    top_n_show: int = 25,
    mode: str = "slim",
):
    table_html = build_table_html(summary_df, mode)

    # Seções por coluna (gráfico + principais estatísticas)
    sections = []
    for _, row in summary_df.iterrows():
        col = row["coluna"]
        title = f"Coluna: {col}"

        # CSV dos top valores
        top_csv_path = Path(str(row.get("top_values_csv") or "")).expanduser()
        if top_csv_path and not top_csv_path.is_absolute():
            top_csv_path = analysis_folder / (
                top_csv_path.name if top_csv_path.name else ""
            )
        df_top = (
            read_top_values_csv(top_csv_path)
            if top_csv_path and top_csv_path.exists()
            else None
        )
        df_show = df_top.head(top_n_show) if df_top is not None else None
        fig = (
            fig_from_top_values(df_show, f"Top valores em {col}")
            if df_show is not None
            else None
        )
        fig_html = (
            pio.to_html(fig, full_html=False, include_plotlyjs=False)
            if fig is not None
            else "<p><em>Sem dados para gráfico.</em></p>"
        )
        download_link = (
            f"<a href='file:///{top_csv_path.as_posix()}' target='_blank'>Baixar CSV (top valores)</a>"
            if top_csv_path and top_csv_path.exists()
            else ""
        )

        # Estatísticas (se houver)
        parts = []
        if pd.notna(row.get("mean", None)):
            parts.append(f"Média: {fmt_num(row.get('mean'))}")
        if pd.notna(row.get("desvio_padrao_pop", None)):
            parts.append(f"Desvio (pop.): {fmt_num(row.get('desvio_padrao_pop'))}")
        if pd.notna(row.get("variancia", None)):
            parts.append(f"Variância (pop.): {fmt_num(row.get('variancia'))}")
        if pd.notna(row.get("coef_variacao", None)):
            parts.append(f"CV: {fmt_num(row.get('coef_variacao'))}")
        if (
            pd.notna(row.get("min", None))
            or pd.notna(row.get("median_approx", None))
            or pd.notna(row.get("max", None))
        ):
            parts.append(
                "Min: {0} • Mediana (aprox.): {1} • Max: {2}".format(
                    fmt_num(row.get("min")),
                    fmt_num(row.get("median_approx")),
                    fmt_num(row.get("max")),
                )
            )
        stats_line = " • ".join([p for p in parts if p])

        # % do valor mais frequente
        pct_col = (
            "top1_pct_of_column"
            if "top1_pct_of_column" in summary_df.columns
            else (
                "top1_pct_of_table"
                if "top1_pct_of_table" in summary_df.columns
                else None
            )
        )
        pct_val = row.get(pct_col) if pct_col else None
        top1_line = "<strong>Valor mais frequente:</strong> {0} — {1} ocorrências ({2} % {3})".format(
            row.get("top1_val") or "",
            row.get("top1_count") or "",
            fmt_num(pct_val),
            "entre não nulos" if pct_col == "top1_pct_of_column" else "na tabela",
        )

        sections.append(f"""
        <section id="col_{col}">
          <h2>{title}</h2>
          <p>{top1_line}</p>
          <p>{stats_line}</p>
          <p>{download_link}</p>
          <div style="display:flex;gap:20px;align-items:flex-start">
            <div style="flex:1">{fig_html}</div>
          </div>
          <hr/>
        </section>
        """)

    methodology_html = f"""
    <h2>Metodologia (resumida)</h2>
    <ul>
      <li><strong>Valor mais frequente</strong>: a “moda” — o valor que mais aparece na coluna.</li>
      <li>O percentual é calculado sobre os <em>não nulos</em>, quando disponível (campo <code>top1_pct_of_column</code>); caso não exista, usa o total da tabela.</li>
      <li>Variância/Desvio/CV são calculados com Welford (streaming) sobre os valores numéricos da coluna.</li>
      <li>Quantis (P25/P50/P75) são aproximados via amostragem (reservoir) e aparecem nas seções por coluna.</li>
    </ul>
    <p>Modo atual: <strong>{"ENXUTO" if mode == "slim" else "COMPLETO"}</strong></p>
    """

    html_parts = []
    html_parts.append(
        "<html><head><meta charset='utf-8'><title>Relatório Consolidado - Interativo (PT)</title></head><body style='font-family:Arial,Helvetica,sans-serif;margin:20px'>"
    )
    html_parts.append(f"<h1>Relatório Consolidado — Tabela {table_name}</h1>")
    html_parts.append(
        "<p>Resumo por coluna com foco em Variância, Desvio Padrão e CV.</p>"
    )
    html_parts.append("<h2>Tabela Resumo</h2>")
    html_parts.append(table_html)
    html_parts.append("<hr/>")
    html_parts.append(methodology_html)
    html_parts.append("<h2>Seções por coluna</h2>")
    html_parts.extend(sections)
    html_parts.append(
        "<p style='font-size:0.9em;color:#666'>Gerado automaticamente.</p>"
    )
    html_parts.append("</body></html>")

    out_file.write_text("\n".join(html_parts), encoding="utf-8")
    return out_file


def parse_args():
    p = argparse.ArgumentParser(
        description="Gerar relatório interativo (PT) a partir da pasta Analises."
    )
    p.add_argument(
        "--analises",
        required=True,
        help="Diretório base das análises (ou a própria pasta da análise).",
    )
    p.add_argument("--table", required=True, help="Nome da tabela (ex.: RANGER_SOSTAT)")
    p.add_argument(
        "--out",
        required=True,
        help="Arquivo HTML de saida (ex: ./saida/relatorio_interativo.html)",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=25,
        help="Top N mostrado nos gráficos (somente leitura).",
    )
    p.add_argument(
        "--mode",
        choices=["slim", "full"],
        default="slim",
        help="slim=visão enxuta (padrão), full=visão completa.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    analises = Path(args.analises)
    if not analises.exists():
        print("Diretório de análises não encontrado:", analises)
        return 1
    # aceitar tanto o diretório base quanto a própria pasta de análise
    folder = (
        analises
        if (analises.is_dir() and analises.name.startswith(f"{args.table}__"))
        else find_latest_analysis_folder(analises, args.table)
    )
    if not folder:
        print(
            f"Nenhuma pasta de análise encontrada para a tabela {args.table} em {analises}"
        )
        return 1
    df = read_summary_folder(folder)
    out_file = Path(args.out)
    res = build_html(
        df, folder, args.table, out_file, top_n_show=args.top_n, mode=args.mode
    )
    print("Relatório consolidado gerado em:", res)
    return 0


if __name__ == "__main__":
    main()
