#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_global_report_from_analyses.py (atualizado: h1 menor + mesmos rótulos do relatório por arquivo)

- Mantém a mesma organização/rotulagem do relatório 1-banco (slim/full)
- Estatísticas globais para numéricos combinadas exatamente a partir de (value_count, mean, variância(pop)) por arquivo
- Nulos (%) global = Σ nulos / Σ linhas_lidas × 100
- "% do valor mais frequente (entre não nulos)" global = (contagem agregada do valor mais frequente) / (Σ linhas_nao_nulas) × 100
- h1 com fonte menor (18pt), body em 14px

Uso (PowerShell):
  python tools/build_global_report_from_analyses.py --analises "./import_folder/analises2" --out-csv "./import_folder/analises2/global_summary_by_column.csv" --out-html "./import_folder/analises2/relatorio_global_RANGER_SOSTAT.html" --out-db "./import_folder/analises2/global_freq_RANGER_SOSTAT.db" --table "RANGER_SOSTAT" --top-n 50 --mode slim
Uso (Bash/Zsh):
  python tools/build_global_report_from_analyses.py --analises "./import_folder/analises2" --out-csv "./import_folder/analises2/global_summary_by_column.csv" --out-html "./import_folder/analises2/relatorio_global_RANGER_SOSTAT.html" --out-db "./import_folder/analises2/global_freq_RANGER_SOSTAT.db" --table "RANGER_SOSTAT" --top-n 50 --mode slim
"""
from pathlib import Path
import argparse
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import plotly.io as pio
import math
import base64
import io
import html
import numpy as np

pio.templates.default = "plotly_white"

# ---------------- localizar artefatos ----------------
def encontrar_columns_csvs(analises_dir: Path, table: str):
    return list(analises_dir.rglob(f"{table}__*/columns/*__top_*.csv"))

def encontrar_summaries_recursivo(analises_dir: Path, table: str):
    return list(analises_dir.rglob(f"{table}__*/summary_by_column.csv"))

# ---------------- ler CSV de top-values ----------------
def ler_top_csv(path: Path):
    try:
        df = pd.read_csv(path, header=0)
        cols = list(df.columns)
        if len(cols) >= 2:
            df = df.rename(columns={cols[0]:'valor', cols[1]:'contagem'})[['valor','contagem']]
        else:
            df.columns = ['valor','contagem']
        df['contagem'] = pd.to_numeric(df['contagem'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame(columns=['valor','contagem'])

def agregar_tops_por_coluna(analises_dir: Path, table: str):
    """
    Percorre recursivamente pastas <...>/<arquivo>/<table>__timestamp/columns/*.csv
    e agrega contagens por (coluna, valor).
    Retorna:
      - df_global(coluna, valor, count_total, files_count)
      - map_top1_count_por_analise: dict[coluna] -> lista de top1_count (um por pasta de análise)
    """
    agreg = {}
    seen = {}
    map_top1 = {}
    cols_csvs = encontrar_columns_csvs(analises_dir, table)
    for csvp in cols_csvs:
        pasta_analise = csvp.parent.parent  # .../columns -> pasta da tabela
        pasta_id = str(pasta_analise.resolve())
        seen[pasta_id] = True
        col_name = csvp.name.split("__top_")[0]
        df = ler_top_csv(csvp)
        # top1 desse arquivo
        if not df.empty:
            top1_cnt = int(df['contagem'].iloc[0])
            map_top1.setdefault(col_name, []).append(top1_cnt)
        # agrega valores
        for _, r in df.iterrows():
            key = (col_name, str(r['valor']))
            ent = agreg.get(key)
            if ent is None:
                ent = {'count_total': 0, 'files': set()}
                agreg[key] = ent
            ent['count_total'] += int(r['contagem'])
            ent['files'].add(pasta_id)
    rows = [{'coluna': k[0], 'valor': k[1], 'count_total': v['count_total'], 'files_count': len(v['files'])}
            for k,v in agreg.items()]
    return pd.DataFrame(rows), list(seen.keys()), map_top1

# ---------------- sumarizar summaries (métricas por coluna) ----------------
def carregar_summaries(analises_dir: Path, table: str):
    """
    Lê todos summary_by_column.csv da tabela, combinando métricas por coluna:
      - tipo aparente mais comum
      - somatórios globais: linhas_lidas, nulos, linhas_nao_nulas
      - listas (n_i, mu_i, var_i) para variância global precisa
      - min_global, max_global
    Retorna dict[coluna] -> dicionário com agregados brutos e listas.
    """
    paths = encontrar_summaries_recursivo(analises_dir, table)
    acc = {}
    for p in paths:
        try:
            df = pd.read_csv(p, dtype=str, encoding='utf-8')
        except Exception:
            try:
                df = pd.read_csv(p, dtype=str, encoding='latin1')
            except Exception:
                continue
        # converter números relevantes
        num_cols = ['linhas_lidas','nulos','linhas_nao_nulas','value_count','mean','variancia','min','max','coef_variacao']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        for _, r in df.iterrows():
            col = str(r.get('coluna') or '').strip()
            if not col:
                continue
            d = acc.setdefault(col, {
                'tipo_counts': {},
                'sum_linhas': 0.0,
                'sum_nulos': 0.0,
                'sum_nao_nulos': 0.0,
                '_list_n': [],
                '_list_mu': [],
                '_list_var': [],
                'mins': [],
                'maxs': []
            })
            # tipo
            tipo = str(r.get('tipo_aparente') or '').strip()
            if tipo:
                d['tipo_counts'][tipo] = d['tipo_counts'].get(tipo, 0) + 1
            # cobertura
            linhas = float(r.get('linhas_lidas') or 0)
            nulos = float(r.get('nulos') or 0)
            nao_nulos = float(r.get('linhas_nao_nulas') or (linhas - nulos))
            d['sum_linhas'] += linhas
            d['sum_nulos'] += nulos
            d['sum_nao_nulos'] += max(0.0, nao_nulos)
            # numéricos (listas para agregação exata)
            n_i = float(r.get('value_count') or 0)
            mu_i = float(r.get('mean') or 0)
            var_i = float(r.get('variancia') or 0)
            if n_i > 0:
                d['_list_n'].append(n_i)
                d['_list_mu'].append(mu_i)
                d['_list_var'].append(var_i)
            # min/max globais
            if pd.notna(r.get('min')):
                d['mins'].append(float(r.get('min')))
            if pd.notna(r.get('max')):
                d['maxs'].append(float(r.get('max')))
    return acc

def agregar_estatisticas_numericas_precisas(acc_raw: dict):
    """
    Recebe acc_raw (com listas) e retorna dict[col] -> métricas agregadas finais.
    """
    agg = {}
    for col, d in acc_raw.items():
        tipo_mais = max(d['tipo_counts'].items(), key=lambda kv: kv[1])[0] if d['tipo_counts'] else ""
        sum_linhas = d['sum_linhas']
        sum_nulos = d['sum_nulos']
        sum_nao_nulos = d['sum_nao_nulos']
        nulos_pct_global = (sum_nulos / sum_linhas * 100.0) if sum_linhas > 0 else 0.0

        n_list = d.get('_list_n', [])
        mu_list = d.get('_list_mu', [])
        var_list = d.get('_list_var', [])
        N = float(np.sum(n_list)) if n_list else 0.0
        if N > 0:
            mu = float(np.sum(np.array(n_list)*np.array(mu_list)) / N)
            # M2_total = Σ n_i (σ_i^2 + (μ_i - μ)^2)
            m2 = 0.0
            for n_i, mu_i, var_i in zip(n_list, mu_list, var_list):
                m2 += n_i * (float(var_i) + (float(mu_i) - mu)**2)
            var_pop = m2 / N
            std_pop = math.sqrt(var_pop) if var_pop >= 0 else 0.0
            cv = (std_pop / mu) if mu != 0 else 0.0
        else:
            mu = var_pop = std_pop = cv = 0.0

        min_g = min(d['mins']) if d['mins'] else None
        max_g = max(d['maxs']) if d['maxs'] else None

        agg[col] = {
            'tipo_aparente_mais_comum': tipo_mais,
            'linhas_lidas_sum': sum_linhas,
            'nulos_sum': sum_nulos,
            'nao_nulos_sum': sum_nao_nulos,
            'nulos_pct_global': nulos_pct_global,
            'value_count_global': N,
            'mean_global': mu,
            'var_pop_global': var_pop,
            'std_pop_global': std_pop,
            'cv_global': cv,
            'min_global': min_g,
            'max_global': max_g
        }
    return agg

# ---------------- agregar top-values em nível global ----------------
def agregar_top_values(analises_dir: Path, table: str):
    df_global, folder_ids, map_top1 = agregar_tops_por_coluna(analises_dir, table)
    if df_global.empty:
        return pd.DataFrame(), [], {}
    return df_global, folder_ids, map_top1

# ---------------- DB opcional ----------------
def gravar_db_global(df_global: pd.DataFrame, caminho_sqlite: Path):
    if not caminho_sqlite:
        return
    conn = sqlite3.connect(str(caminho_sqlite))
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS global_counts (
        coluna TEXT NOT NULL,
        valor TEXT,
        count_total INTEGER NOT NULL DEFAULT 0,
        files_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(coluna, valor)
    )""")
    conn.commit()
    cur.execute("DELETE FROM global_counts")
    conn.commit()
    if not df_global.empty:
        cur.executemany(
            "INSERT INTO global_counts(coluna, valor, count_total, files_count) VALUES (?,?,?,?)",
            [(r['coluna'], r['valor'], int(r['count_total']), int(r['files_count'])) for _, r in df_global.iterrows()]
        )
        conn.commit()
    conn.close()

# ---------------- construir tabela resumo global ----------------
def construir_dataframe_global(df_global_counts: pd.DataFrame, agg_num: dict):
    rows = []
    nao_nulos_por_col = {c: v['nao_nulos_sum'] for c, v in agg_num.items()}
    cols_unicas = set(list(agg_num.keys()) + (list(df_global_counts['coluna'].unique()) if not df_global_counts.empty else []))
    for col in sorted(cols_unicas):
        an = agg_num.get(col, {})
        tipo = an.get('tipo_aparente_mais_comum', "")
        nulos_pct = an.get('nulos_pct_global', 0.0)
        mean_g = an.get('mean_global', 0.0)
        var_g = an.get('var_pop_global', 0.0)
        std_g = an.get('std_pop_global', 0.0)
        cv_g = an.get('cv_global', 0.0)

        # valor mais frequente global
        if not df_global_counts.empty:
            g = df_global_counts[df_global_counts['coluna'] == col]
            if not g.empty:
                g_sorted = g.sort_values(['count_total','files_count'], ascending=[False,False])
                top1_val = str(g_sorted.iloc[0]['valor'])
                top1_cnt_total = int(g_sorted.iloc[0]['count_total'])
            else:
                top1_val = ""
                top1_cnt_total = 0
        else:
            top1_val = ""
            top1_cnt_total = 0

        nao_nulos_sum = float(nao_nulos_por_col.get(col, 0.0) or 0.0)
        pct_valor_mais_freq = (top1_cnt_total / nao_nulos_sum * 100.0) if nao_nulos_sum > 0 else 0.0

        # distinto global = nº de valores diferentes agregados
        if not df_global_counts.empty:
            distinct_global = int(df_global_counts[df_global_counts['coluna']==col]['valor'].nunique())
        else:
            distinct_global = 0

        rows.append({
            'coluna': col,
            'tipo_aparente': tipo,
            'distinct_global': distinct_global,
            'nulos_pct_global': nulos_pct,
            'mean_global': mean_g,
            'std_pop_global': std_g,
            'var_pop_global': var_g,
            'cv_global': cv_g,
            'valor_mais_frequente_global': top1_val,
            'pct_valor_mais_freq_nao_nulos_global': pct_valor_mais_freq,
        })
    df_summary = pd.DataFrame(rows)
    df_summary = df_summary.sort_values(['nulos_pct_global','distinct_global'], ascending=[True, False], ignore_index=True)
    return df_summary

# ---------------- helpers de UI (plotly e HTML) ----------------
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

def csv_para_data_uri(df: pd.DataFrame):
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding='utf-8')
    return "data:text/csv;base64," + base64.b64encode(buf.getvalue().encode('utf-8')).decode('ascii')

def grafico_top(df_top: pd.DataFrame, coluna: str, top_n:int=50):
    if df_top is None or df_top.empty:
        return "<p><em>Sem dados para gráfico.</em></p>"
    dfv = df_top[df_top['coluna']==coluna].copy()
    if dfv.empty:
        return "<p><em>Sem dados para gráfico.</em></p>"
    dfv = dfv[['valor','count_total','files_count']].sort_values(['files_count','count_total'], ascending=[False,False]).head(top_n)
    labels = dfv['valor'].astype(str).tolist()
    counts = dfv['count_total'].astype(int).tolist()
    hover = [f"{html.escape(v)}<br>contagem_total: {ct}<br>apareceu_em_arquivos: {fc}" for v,ct,fc in zip(labels, counts, dfv['files_count'])]
    fig = go.Figure(go.Bar(x=counts, y=labels, orientation='h', marker_color='steelblue', hovertext=hover, hoverinfo='text'))
    fig.update_layout(title=f"Top valores agregados em {coluna}", height=max(300, 25*len(labels)),
                      margin=dict(l=250, r=30, t=40, b=30), xaxis_title="Contagem total (soma nos bancos)", yaxis_title="Valor")
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)

def build_table_html(summary_df: pd.DataFrame, mode:str):
    slim_cols = [
        ('coluna', 'COLUNA'),
        ('tipo_aparente', 'TIPO'),
        ('distinct_global', 'DISTINTO (global)'),
        ('nulos_pct_global', 'NULOS (%)'),
        ('mean_global', 'MÉDIA (global)'),
        ('std_pop_global', 'DESVIO (pop., global)'),
        ('var_pop_global', 'VAR (pop., global)'),
        ('cv_global', 'CV (global)'),
        ('valor_mais_frequente_global', 'Valor mais frequente'),
        ('pct_valor_mais_freq_nao_nulos_global', '% do valor mais frequente (entre não nulos)'),
    ]
    full_cols = slim_cols  # por ora igual
    chosen = full_cols if mode == 'full' else slim_cols
    headers = [h for _, h in chosen]
    values = []
    for c, _h in chosen:
        if c in summary_df.columns:
            if c in ('nulos_pct_global','mean_global','std_pop_global','var_pop_global','cv_global','pct_valor_mais_freq_nao_nulos_global','distinct_global'):
                values.append(summary_df[c].apply(fmt_num).astype(str).tolist())
            else:
                values.append(summary_df[c].fillna("").astype(str).tolist())
        else:
            values.append([""]*len(summary_df))
    # cores por % do valor mais frequente
    fill_colors = []
    ser = summary_df['pct_valor_mais_freq_nao_nulos_global'] if 'pct_valor_mais_freq_nao_nulos_global' in summary_df.columns else None
    for i in range(len(summary_df)):
        v = float(ser.iloc[i]) if ser is not None and pd.notna(ser.iloc[i]) else 0.0
        if v >= 10.0:
            fill_colors.append('#dff0d8')
        elif v >= 2.0:
            fill_colors.append('#fff7bf')
        else:
            fill_colors.append('#ffffff')
    table_fig = go.Figure(go.Table(
        header=dict(values=headers, fill_color='lightgrey', align='left'),
        cells=dict(values=values, fill_color=[fill_colors], align='left', font_size=12)
    ))
    return pio.to_html(table_fig, full_html=False, include_plotlyjs='cdn')

def montar_html(df_summary: pd.DataFrame, df_global_counts: pd.DataFrame, caminho_html: Path, nome_tabela: str, top_n:int=50, mode:str='slim'):
    table_html = build_table_html(df_summary, mode)
    # seções por coluna
    secoes = []
    for _, r in df_summary.iterrows():
        col = r['coluna']
        ghtml = grafico_top(df_global_counts, col, top_n=top_n)
        stats_parts = [
            f"Média (global): {fmt_num(r.get('mean_global'))}",
            f"Desvio (pop., global): {fmt_num(r.get('std_pop_global'))}",
            f"Variância (pop., global): {fmt_num(r.get('var_pop_global'))}",
            f"CV (global): {fmt_num(r.get('cv_global'))}"
        ]
        vfreq = r.get('valor_mais_frequente_global') or ""
        pctfreq = fmt_num(r.get('pct_valor_mais_freq_nao_nulos_global'))
        top_line = f"<strong>Valor mais frequente (global):</strong> {html.escape(str(vfreq))} — {pctfreq}% entre não nulos"
        secoes.append(f"""
        <section id="col_{html.escape(col)}">
          <h2>Coluna: {html.escape(col)}</h2>
          <p>{top_line}</p>
          <p>{" • ".join(stats_parts)}</p>
          <div style="display:flex;gap:20px;align-items:flex-start">
            <div style="flex:1">{ghtml}</div>
          </div>
          <hr/>
        </section>
        """)

    # HTML com CSS (título menor)
    html_parts = []
    html_parts.append("""<html><head><meta charset='utf-8'><title>Relatório Global Consolidado</title>
<style>
  body { font-family: Arial, Helvetica, sans-serif; margin: 20px; font-size: 14px; }
  h1 { font-size: 18pt; line-height: 1.15; margin: 4px 0 12px; }
  h2 { font-size: 14pt; line-height: 1.2; margin: 14px 0 8px; }
</style>
</head>""")
    html_parts.append("<body>")
    html_parts.append(f"<h1>Relatório Global Consolidado — Tabela {html.escape(nome_tabela)}</h1>")
    html_parts.append("<p>Resumo por coluna com foco em Variância, Desvio Padrão e CV, mantendo a mesma organização do relatório por arquivo.</p>")
    html_parts.append("<h2>Tabela Resumo</h2>")
    html_parts.append(table_html)
    html_parts.append("<hr/>")
    html_parts.append("<h2>Seções por coluna</h2>")
    html_parts.extend(secoes)
    html_parts.append("</body></html>")
    caminho_html.write_text("\n".join(html_parts), encoding='utf-8')

# ---------------- CLI ----------------
def parse_args():
    p = argparse.ArgumentParser(description="Construir relatório global (multi-banco) com mesma organização do relatório por arquivo.")
    p.add_argument("--analises", required=True, help="Diretório base com subpastas por arquivo (cada qual contendo <TABELA>__<timestamp>/...).")
    p.add_argument("--out-csv", required=True, help="CSV global de saída.")
    p.add_argument("--out-html", required=True, help="HTML global de saída.")
    p.add_argument("--out-db", help="(Opcional) SQLite com tabela global_counts.")
    p.add_argument("--table", required=True, help="Nome da tabela alvo (ex.: RANGER_SOSTAT).")
    p.add_argument("--top-n", type=int, default=50, help="Top N no gráfico.")
    p.add_argument("--mode", choices=['slim','full'], default='slim', help="Modo da tabela resumo (igual ao relatório por arquivo).")
    return p.parse_args()

# ---------------- main ----------------
def main():
    args = parse_args()
    analises_dir = Path(args.analises)
    if not analises_dir.exists():
        print("Diretório de análises não encontrado:", analises_dir)
        return 1

    # 1) Agregar top-values (contagens globais por valor)
    df_global_counts, folder_ids, map_top1 = agregar_top_values(analises_dir, args.table)

    # 2) Agregar summaries por coluna (cobertura + números)
    acc_raw = carregar_summaries(analises_dir, args.table)
    if not acc_raw:
        print("Nenhum summary_by_column.csv encontrado para a tabela informada.")
        return 1
    agg_dict = agregar_estatisticas_numericas_precisas(acc_raw)

    # 3) Construir dataframe global final
    df_summary = construir_dataframe_global(df_global_counts, agg_dict)

    # 4) Salvar CSV
    out_csv = Path(args.out_csv)
    df_summary.to_csv(out_csv, index=False, encoding='utf-8')
    print("CSV global gerado em:", out_csv)

    # 5) Opcional: salvar SQLite com contagens agregadas
    if args.out_db:
        gravar_db_global(df_global_counts, Path(args.out_db))
        print("SQLite global gravado em:", args.out_db)

    # 6) Gerar HTML
    out_html = Path(args.out_html)
    montar_html(df_summary, df_global_counts, out_html, args.table, top_n=args.top_n, mode=args.mode)
    print("Relatório HTML global gerado em:", out_html)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
