# uso do utilitário encontrar_registro_em_bds.py (documentação de apoio) — versão genérica

Resumo rápido
- Objetivo: localizar a presença/ausência de registros em um diretório com vários arquivos de banco (DuckDB / SQLite / Access .mdb/.accdb).
- Modo recomendado e obrigatório para filtros compostos: `--filters "COL1=VAL1,COL2=VAL2,..."`.
- Modo genérico por valor: `--key "VALOR"` (procura em colunas comuns ou coluna específica via `--col`).
- Saída: relatório no terminal e CSV com metadados para auditoria/comparação (`--out-csv`).
- Observação importante: as flags específicas (como --rtuno/--pntno) foram removidas — use `--filters` para filtros compostos.

Instalação / pré‑requisitos
- Python 3.8+ (recomenda-se virtualenv)
- Pacotes:
  - duckdb (se usar .duckdb)
  - pyodbc (para acessar .mdb/.accdb via ODBC)
  - sqlite3 (já incluído no Python)
- No Windows, para `.accdb` via ODBC: instale Microsoft Access Database Engine (ACE) compatível com a arquitetura do Python (32/64 bits).

Como o script funciona (visão geral)
- Varre arquivos em `--dir` com extensões padrão (.duckdb, .db, .sqlite, .sqlite3, .mdb, .accdb) — pode alterar com `--ext`.
- Ordena arquivos por `--order` (`name` por padrão) para análise temporal determinística.
- Para cada arquivo aplica:
  - filtros compostos via `--filters` (quando fornecido) — se `--table` for omitida, o script tenta aplicar os filtros em todas as tabelas do arquivo;
  - ou busca genérica por valor via `--key` (sem filtros compostos).
- Registra `found`, `count`, `sample` (opcional) e metadados do arquivo no CSV (se `--out-csv`).

Uso — exemplos praticos

PowerShell:
```
# buscar rtuno+pntno
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --table RANGER_SOSTAT --out-csv resultados.csv

# buscar rtuno+pntno sem informar a tabela (o script tentara em todas as tabelas de cada arquivo)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --out-csv resultados_todas.csv

# filtro com string contendo virgula
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters 'SUBNAM="U,05",RTUNO=1' --out-csv resultados.csv

# buscar por valor em colunas comuns (sem saber coluna)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --sample --out-csv resultados_key.csv

# buscar em coluna especifica
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --col SUBNAM --table RANGER_SOANALOG --sample
```

Bash:
```
# buscar rtuno+pntno
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --table RANGER_SOSTAT --out-csv resultados.csv

# buscar rtuno+pntno sem informar a tabela (o script tentara em todas as tabelas de cada arquivo)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --out-csv resultados_todas.csv

# filtro com string contendo virgula
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters 'SUBNAM="U,05",RTUNO=1' --out-csv resultados.csv

# buscar por valor em colunas comuns (sem saber coluna)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --sample --out-csv resultados_key.csv

# buscar em coluna especifica
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --col SUBNAM --table RANGER_SOANALOG --sample
```

Zsh:
```
# buscar rtuno+pntno
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --table RANGER_SOSTAT --out-csv resultados.csv

# buscar rtuno+pntno sem informar a tabela (o script tentara em todas as tabelas de cada arquivo)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters "RTUNO=1,PNTNO=2304" --out-csv resultados_todas.csv

# filtro com string contendo virgula
python tools/encontrar_registro_em_bds.py -d "./mdbs" --filters 'SUBNAM="U,05",RTUNO=1' --out-csv resultados.csv

# buscar por valor em colunas comuns (sem saber coluna)
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --sample --out-csv resultados_key.csv

# buscar em coluna especifica
python tools/encontrar_registro_em_bds.py -d "./mdbs" --key "U05" --col SUBNAM --table RANGER_SOANALOG --sample
```

Opções principais
- --dir / -d : diretório com arquivos de BD  
- --filters : filtros compostos (obrigatório para buscas compostas)  
- --key / -k : valor para busca genérica  
- --col / -c : nome da coluna (modo genérico)  
- --table / -t : tabela (ou substring) — se omitido com --filters, o script tenta em todas as tabelas do arquivo  
- --try-all-cols : testar todas as colunas (modo genérico; lento)  
- --order : name | mtime (padrão: name)  
- --brief : saída compacta  
- --sample : retorna uma amostra (se encontrada)  
- --show-cols : colunas a mostrar na amostra  
- --out-csv : salva CSV com metadados  
- --analyze-csv : analisar CSV existente  
- --analyze-after : analisar CSV gerado ao final  
- --verbose / -v : verbose / diagnóstico  
- --ext / -e : lista de extensões a incluir

Formato do CSV de saída
- path, mtime, size_kb, quick_sha1, found, table, count, sample, error, order_idx

Boas práticas
- Sempre grave CSVs com timestamp por execução.  
- Prefira `--filters` para consultas compostas.  
- Se não souber a tabela, omita `--table` e deixe o script tentar em todas as tabelas.  
- Se usar Access (.accdb), garanta `pyodbc` e o driver ACE com arquitetura compatível.

Se quiser, eu:
- removo quaisquer referências remanescentes a `--rtuno/--pntno` no repo e atualizo exemplos adicionais; ou
- adiciono validação extra (mensagem clara quando tabela/coluna não existir) — quer que eu faça isso agora?
