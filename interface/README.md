# interface — visao geral e relacoes

Este diretório contém o backend Flask e utilitários para busca local em bases DuckDB (com fallback opcional para Access via ODBC) e a construção do índice `_fulltext`.

## componentes

- `app_flask_search.py`: Backend Flask simples.
  - Endpoints: `/` (serve `static/index.html`), `/api/tables`, `/api/table`, `/api/search`.
  - Busca por ILIKE diretamente nas colunas das tabelas (sem `_fulltext`).
  - Usa `DB_PATH` fixo (`minha.duckdb`). Ideal para demo rápida.

- `app_flask_local_search.py`: Backend Flask completo para operação local.
  - Upload/seleção/remoção de arquivos: `/admin/upload`, `/admin/select`, `/admin/delete`, `/admin/list_uploads`.
  - Conversão Access→DuckDB (se existir `access_convert.convert_access_to_duckdb`).
  - Status consolidado: `/admin/status` (progresso de conversão, contagem `_fulltext`, top tabelas).
  - Iniciar indexação `_fulltext`: `/admin/start_index` (usa `create_fulltext.create_or_resume_fulltext`).
  - Definir prioridade de tabelas: `/admin/set_priority` (afeta ordenação de resultados na UI).
  - Busca principal `/api/search`:
    - Com `.duckdb`: usa `_fulltext` e ranking `RapidFuzz` (mais rápido e tolerante).
    - Com `.mdb/.accdb`: fallback via `pyodbc` (se instalado), faz LIKE e ranking em Python.
  - Lê/atualiza `config.json` com `db_path`, `priority_tables` e `auto_index_after_convert`.

- `create_fulltext.py`: Indexador seguro de `_fulltext`.
  - Ignora tabelas de sistema e a própria `_fulltext`.
  - Suporta `drop` para reindex do zero e resume a partir do que já foi indexado.
  - Normaliza texto com `utils.normalize_text` e serializa com `utils.serialize_value`.
- Pode ser usado via CLI: `python -m interface.create_fulltext --db ./arquivo.duckdb [--drop] [--chunk N] [--batch N]`.

- `check_progress.py`: Diagnóstico de progresso.
  - Compara linhas por tabela com o que já está em `_fulltext`.
  - Lista quais tabelas ainda não estão totalmente indexadas.
  - Exemplo: `python -m interface.check_progress --db ./arquivo.duckdb`.

- `utils.py`: Funções utilitárias comuns.
  - `normalize_text(s)`: remove acentos, lowercase, normaliza pontuação/underscores/hífens e colapsa espaços.
  - `serialize_value(v)`: converte tipos (datas, decimals, bytes etc.) para valores JSON-compatíveis.

## relacoes entre arquivos

- UI (`static/index.html`) → chama endpoints do `app_flask_local_search.py`:
  - Estado inicial: `/admin/list_uploads`.
  - Listar tabelas: `/api/tables`.
  - Busca: `/api/search` (usa `_fulltext` em DuckDB; fallback Access com `pyodbc`).
  - Indexação `_fulltext`: `/admin/start_index`.
  - Prioridade de tabelas: `/admin/set_priority`.
  - Upload/seleção/remoção: `/admin/upload`, `/admin/select`, `/admin/delete`.

- `app_flask_local_search.py` chama:
  - `create_fulltext.create_or_resume_fulltext` para construir/retomar o índice `_fulltext`.
  - `utils.normalize_text` e `utils.serialize_value` (normalização/serialização).
  - Opcional `access_convert.convert_access_to_duckdb` para conversão.

- `app_flask_search.py` é independente de `_fulltext` e de `utils.py` (usa ILIKE direto). Serve `static/index.html` como o completo, mas com menos recursos.

## quando precisam estar juntos

- Para a app completa (uploads, conversão, indexação `_fulltext`, prioridade):
  - Necessários: `app_flask_local_search.py`, `create_fulltext.py`, `utils.py` e `static/index.html` (fora deste diretório).
  - O `check_progress.py` é opcional (diagnóstico).
  - `access_convert.py` é opcional, porém necessário para conversão de `.mdb/.accdb` para `.duckdb` via UI.
  - `pyodbc` é opcional (apenas para fallback Access).

- Para a versão simples:
  - Basta `app_flask_search.py` e `static/index.html`, com `minha.duckdb` disponível.

## dependencias

- Obrigatórias: `flask`, `duckdb`, `rapidfuzz`, `pyodbc`, `pandas`, `matplotlib`.
- Sistema (Windows): driver ODBC Microsoft Access (Access Database Engine 2016/2019).
- O backend executa verificação de dependências e registra no log. O status aparece em `/admin/status` e `/api/health`.
- Script local de verificação: `python tools/check_dependencies.py`.

## como rodar

- Versao simples:
PowerShell:
```
python -m interface.app_flask_search
```
Bash:
```
python -m interface.app_flask_search
```
Zsh:
```
python -m interface.app_flask_search
```
Acesse `http://127.0.0.1:5000/`.

- Versao completa:
PowerShell:
```
python -m interface.app_flask_local_search
```
Bash:
```
python -m interface.app_flask_local_search
```
Zsh:
```
python -m interface.app_flask_local_search
```
Acesse `http://127.0.0.1:5000/`.

Selecione um DB em "Configurar/Upload"; para `.duckdb`, a busca usa `_fulltext` quando disponível. Para `.mdb/.accdb`, se `pyodbc` estiver instalado, o fallback faz a busca direta.

## observacoes

- Após converter Access→DuckDB, a indexação automática pode ser acionada (se `auto_index_after_convert` estiver habilitado).
- A prioridade de tabelas influencia a ordem de exibição dos resultados.
- Use `check_progress.py` para verificar se `_fulltext` já cobre todas as tabelas.
