# MDB2SQL

Conversor de Access (mdb/accdb) para DuckDB com interface local e ferramentas de analise.

Leia o [readme original](docs/README_original.md) para o conteudo historico.

## Visao geral

- Conversao de arquivos Access para DuckDB
- Interface Flask local para upload, selecao, indexacao e busca
- Ferramentas auxiliares em tools/
- Testes em tests/

## Estrutura

- interface/ - app Flask e utilitarios
- static/ - UI
- tools/ - scripts de apoio
- tests/ - testes automatizados

## Conversores

- convert_mdbtools.py - recomendado para Linux e macOS
- convert_jackcess.py - mais confiavel, usa Java
- convert_pyaccess_parser.py - puro Python
- convert_pyodbc.py - Windows e ODBC

Detalhes completos em [readme original](docs/README_original.md).

## Requisitos

- Python 3.13.7 (recomendado)
- Dependencias em requirements.txt
- Opcional: direnv e pyenv para ativacao automatica

## Ambiente automatico (direnv + pyenv)

Este repo inclui `.envrc` para ativar `.venv` ao entrar no diretorio.
Quando possivel, usa Python 3.13.7 via pyenv. Se nao estiver disponivel, usa o Python encontrado no PATH e avisa.

Habilitar direnv por shell:

PowerShell:
```
direnv hook pwsh | Out-String | Invoke-Expression
```

Bash:
```
eval "$(direnv hook bash)"
```

Zsh:
```
eval "$(direnv hook zsh)"
```

Permitir o .envrc:

PowerShell:
```
direnv allow
```

Bash:
```
direnv allow
```

Zsh:
```
direnv allow
```

## Fallback manual (sem direnv)

PowerShell:
```
pyenv install 3.13.7
pyenv local 3.13.7
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Bash:
```
pyenv install 3.13.7
pyenv local 3.13.7
python -m venv .venv
. .venv/bin/activate
```

Zsh:
```
pyenv install 3.13.7
pyenv local 3.13.7
python -m venv .venv
. .venv/bin/activate
```

Se pyenv nao estiver disponivel:

PowerShell:
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Bash:
```
python3 -m venv .venv
. .venv/bin/activate
```

Zsh:
```
python3 -m venv .venv
. .venv/bin/activate
```

## Dependencias

PowerShell:
```
python -m pip install -r requirements.txt
```

Bash:
```
python -m pip install -r requirements.txt
```

Zsh:
```
python -m pip install -r requirements.txt
```

## Interface local (Flask)

A interface completa esta em `interface/app_flask_local_search.py`.
Veja `interface/README.md` para detalhes e endpoints.

PowerShell:
```
python main.py
```

Bash:
```
python main.py
```

Zsh:
```
python main.py
```

Fluxos principais na UI:
- DuckDB: selecione ou envie um .duckdb (sem conversao)
- Access: envie .mdb/.accdb, a conversao gera um .duckdb

O indice _fulltext melhora a busca. Sem ele, a busca fica indisponivel.

## Ferramentas e scripts

Veja `tools/README.md` para scripts de analise e relatorios.

## Testes e lint

PowerShell:
```
python -m pytest
python -m unittest discover -s tests
python -m flake8
python -m ruff check interface tools tests
```

Bash:
```
python -m pytest
python -m unittest discover -s tests
python -m flake8
python -m ruff check interface tools tests
```

Zsh:
```
python -m pytest
python -m unittest discover -s tests
python -m flake8
python -m ruff check interface tools tests
```

Notas:
- `.flake8` exclui node_modules e ignora E302/E303/E501 para reduzir ruido.
