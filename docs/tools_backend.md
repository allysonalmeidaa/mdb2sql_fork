# ferramentas do backend — guia completo

Este documento cobre utilitarios do repo para conversao, indexacao, diagnostico e validacao.
Todos os comandos assumem que voce esta na raiz do repo.

## mapa geral (ascii)

```
[DB .accdb/.mdb] --> [Conversor] --> [DuckDB .duckdb] --> [_fulltext] --> [Busca UI]
                      |                                |
                      |                                +--> [check_progress]
                      +--> [pyodbc|pyaccess|mdbtools|jackcess]
```

## fluxos principais (ascii)

Fluxo Windows com ODBC:
```
[accdb] -> convert_pyodbc.py -> [duckdb] -> create_fulltext.py -> UI Search
```

Fluxo puro Python:
```
[accdb] -> convert_pyaccess_parser.py -> [duckdb] -> create_fulltext.py -> UI Search
```

Fluxo Linux/macOS com mdbtools:
```
[mdb] -> convert_mdbtools.py -> [duckdb] -> create_fulltext.py -> UI Search
```

Fluxo Jackcess:
```
[accdb/mdb] -> convert_jackcess.py -> [duckdb] -> create_fulltext.py -> UI Search
```

## fluxo de diagnostico (ascii)

```
tools/check_dependencies.py
  -> drivers ODBC ok?
  -> modulos Python ok?
  -> se falha: corrigir e repetir
```

## fluxo de indexacao (ascii)

```
duckdb
  -> create_fulltext.py --drop
  -> check_progress.py
  -> UI Search
```

## 0) diagnostico rapido do ambiente

Uso basico:
```
python tools/check_dependencies.py
```
O que ele mostra:
- versao e arquitetura do Python
- modulos essenciais (duckdb, pyodbc, pypyodbc, access_parser)
- drivers ODBC detectados
- status do driver Access ODBC

Se o Python da venv nao estiver ativo:
```
.\.venv\Scripts\Activate.ps1
python tools/check_dependencies.py
```

## 1) conversores — qual usar

Resumo por plataforma:
- Windows: preferir `convert_pyodbc.py` (driver Access ODBC instalado).
- Linux/macOS: preferir `convert_mdbtools.py` (mais rapido) ou `convert_jackcess.py` (Java).
- Fallback puro Python: `convert_pyaccess_parser.py` (mais lento, mas sem ODBC).

Resumo por formato:
- `.accdb`: melhor com `convert_pyodbc.py`
- `.mdb`: qualquer conversor atende, mdbtools costuma ser rapido

## 2) conversor access -> duckdb via pyodbc (windows)

Quando usar:
- driver Access ODBC instalado
- deseja maior compatibilidade com .accdb

Comando:
```
python convert_pyodbc.py --input "interface\\uploads\\arquivo.accdb" --output "interface\\uploads\\saida.duckdb"
```

Problemas comuns:
- IM002: driver Access ODBC nao encontrado
- mismatch 32/64-bit entre Python e driver

Validacao rapida:
```
python -c "import pyodbc; print(pyodbc.drivers())"
```

## 2.1) medicao de tempo (pyodbc vs pyaccess_parser)

PowerShell (cronometro simples):
```
Measure-Command { python convert_pyodbc.py --input "interface\\uploads\\arquivo.accdb" --output "interface\\uploads\\saida_pyodbc.duckdb" } | Select-Object TotalSeconds
Measure-Command { python convert_pyaccess_parser.py --input "interface\\uploads\\arquivo.accdb" --output "interface\\uploads\\saida_pyaccess.duckdb" } | Select-Object TotalSeconds
```

Template para registrar tempos sem expor dados sensiveis:

```
DB_ALIAS | METODO            | TEMPO_S
DB_A     | pyodbc            | 0000.00
DB_A     | pyaccess_parser   | 0000.00
```

Recomendado: salvar este quadro em um arquivo interno e nao publicar nomes de bases reais.

Exemplo real (anonimizado):

```
DB_ALIAS | METODO            | TEMPO_S
DB_A     | pyodbc            | 100.08
DB_A     | pyaccess_parser   | 363.43
```

Contexto do exemplo (anonimizado):
```
DB_ALIAS | TAMANHO_BYTES | TABELAS_ENCONTRADAS | TABELAS_IMPORTADAS | LINHAS_TOTAIS
DB_A     | 113061888     | 305                 | 164                | 118004
```

Hardware do exemplo (anonimizado):
```
CPU: Intel(R) Core(TM) Ultra 7 258V
RAM: 33873780736 bytes (~31.5 GB)
LAPTOP: 83NM
```

## 3) conversor access -> duckdb via pyaccess_parser (puro python)

Quando usar:
- sem ODBC
- precisa de fallback simples

Comando:
```
python convert_pyaccess_parser.py --input "interface\\uploads\\arquivo.accdb" --output "interface\\uploads\\saida.duckdb"
```

Dicas:
- para arquivos grandes, o processo e mais lento
- se falhar, o erro real aparece no console

## 4) conversor access -> duckdb via mdbtools (linux/macos)

Quando usar:
- Linux/macOS com mdbtools instalado

Comando:
```
python convert_mdbtools.py --input "interface\\uploads\\arquivo.mdb" --output "interface\\uploads\\saida.duckdb"
```

Dependencias:
```
sudo apt install -y mdbtools
```

## 5) conversor access -> duckdb via jackcess (java)

Quando usar:
- precisa de compatibilidade extra
- Java instalado

Comando:
```
python convert_jackcess.py --input "interface\\uploads\\arquivo.accdb" --output "interface\\uploads\\saida.duckdb"
```

Dependencias:
- Java JDK instalado
- JARs em `temp/` (scripts de install ja baixam)

## 6) indexacao do _fulltext

Recriar do zero:
```
python -m interface.create_fulltext --db "interface\\uploads\\arquivo.duckdb" --drop
```

Retomar indexacao:
```
python -m interface.create_fulltext --db "interface\\uploads\\arquivo.duckdb"
```

Parametros uteis:
```
python -m interface.create_fulltext --db "interface\\uploads\\arquivo.duckdb" --drop --chunk 2000 --batch 1000
```

## 7) diagnostico de progresso do _fulltext

Verifica quais tabelas ainda nao foram indexadas:
```
python -m interface.check_progress --db "interface\\uploads\\arquivo.duckdb"
```

## 8) backend flask (app completa)

Rodar servidor local:
```
python main.py
```

Rotas uteis para debug:
- `http://127.0.0.1:5000/` UI
- `http://127.0.0.1:5000/admin/status` status consolidado
- `http://127.0.0.1:5000/admin/logs` logs recentes
- `http://127.0.0.1:5000/api/health` diagnostico do backend

## 9) fluxos completos sugeridos

Fluxo Access (Windows + ODBC):
1) Instale driver Access ODBC
2) Rode `tools/check_dependencies.py`
3) Converta com `convert_pyodbc.py`
4) Indexe com `interface.create_fulltext`
5) Abra a UI e pesquise

Fluxo Access (puro Python):
1) Rode `tools/check_dependencies.py`
2) Converta com `convert_pyaccess_parser.py`
3) Indexe com `interface.create_fulltext`
4) Abra a UI e pesquise

Fluxo DuckDB nativo:
1) Coloque o `.duckdb` em `interface\\uploads`
2) Selecione o DB na UI
3) Indexe `_fulltext`
4) Pesquise

## 10) validacoes rapidas antes de usar

Dependencias:
```
python tools/check_dependencies.py
```

Driver ODBC (Windows):
```
python -c "import pyodbc; print(pyodbc.drivers())"
```

Testes UI (smoke):
```
npx playwright test tests/ui/button_smoke.spec.js --trace on --reporter line
```

## 11) logs e rastreio

Onde olhar:
- `/admin/status` mostra o estado do DB, conversao e indexacao
- `/admin/logs` guarda eventos recentes (backend e cliente)
- no console do servidor aparecem os eventos do log interno

## 12) erros conhecidos e correcoes

IM002 (ODBC):
- driver Access ausente
- mismatch 32/64-bit
- terminal sem reload depois da instalacao

pyaccess_parser falha:
- arquivo corrompido
- permissao/lock no arquivo
- acesso parser nao suporta alguma estrutura do DB

DuckDB sem _fulltext:
- rode `interface.create_fulltext`

## 17) troubleshooting geral

Checklist rapido:
1) Rode `python tools/check_dependencies.py`
2) Confirme driver Access ODBC em `pyodbc.drivers()`
3) Converta via `convert_pyodbc.py` (Windows) ou `convert_pyaccess_parser.py` (fallback)
4) Rode `_fulltext` com `interface.create_fulltext`
5) Confirme `/admin/status` e `/admin/logs`

Erros comuns e correcoes:
- IM002: driver Access ODBC ausente ou mismatch 32/64-bit
- Sem resultados na busca: `_fulltext` ausente ou indexacao incompleta
- Conversao falha: arquivo em uso, caminho invalido, permissao de leitura
- UI travando: abra `/admin/logs` para ver erros do backend/cliente

## 18) conceitos utilizados

- DuckDB: base final para consulta e indexacao
- _fulltext: tabela de indice usado pela busca tolerante
- Conversao: transforma `.mdb/.accdb` em `.duckdb`
- Fluxo UI: selecionar DB -> converter -> indexar -> buscar
- Fallback: quando um conversor falha, tenta o proximo

## 19) tools no backend (lista rapida)

Diagnostico:
- `tools/check_dependencies.py`

Conversores:
- `convert_pyodbc.py` (Windows + ODBC)
- `convert_pyaccess_parser.py` (puro Python)
- `convert_mdbtools.py` (Linux/macOS)
- `convert_jackcess.py` (Java)

Indexacao:
- `interface.create_fulltext`
- `interface.check_progress`

## 20) tools no frontend (lista rapida)

UI principal:
- `static/index.html` + `static/app.js`

Testes UI:
- `tests/ui/button_smoke.spec.js`

Relatorios/artefatos:
- `test-results/` (traces e relatorios do Playwright)

## 13) scripts de instalacao (atalhos)

Windows:
```
install_windows.bat
```

Linux:
```
./install_linux.sh
```

macOS:
```
./install_macos.sh
```

## 14) onde ficam os arquivos

- Uploads da UI: `interface\\uploads\\`
- Logs (API): `GET /admin/logs`
- Config da UI: `config.json` e `interface\\config.json`

## 15) exemplos prontos (com os arquivos do repo)

Converter DB real:
```
python convert_pyaccess_parser.py --input "interface\\uploads\\2025-05-27_DB3.accdb" --output "interface\\uploads\\2025-05-27_DB3_pyaccess.duckdb"
```

Indexar DB convertido:
```
python -m interface.create_fulltext --db "interface\\uploads\\2025-05-27_DB3_pyaccess.duckdb" --drop
```

Checar progresso:
```
python -m interface.check_progress --db "interface\\uploads\\2025-05-27_DB3_pyaccess.duckdb"
```

## 16) observacoes de desempenho

- `convert_pyodbc.py` tende a ser mais rapido no Windows
- `_fulltext` pode levar tempo em bancos grandes; ajuste `--chunk` e `--batch`
- `convert_pyaccess_parser.py` usa mais CPU e e mais lento
