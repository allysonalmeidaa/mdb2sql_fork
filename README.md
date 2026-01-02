# mdb2sql

Conversor de Access (mdb/accdb) para DuckDB com interface local e ferramentas de analise.

Leia o [readme original](docs/readme_original.md) para o conteudo historico.

## visao geral

- Conversao de arquivos Access para DuckDB
- Interface Flask local para upload, selecao, indexacao e busca
- Ferramentas auxiliares em tools/
- Testes em tests/

Checagem rapida de dependencias (na raiz do repo):
```
python tools/check_dependencies.py
```
Ele valida modulos Python (`duckdb`, `pyodbc`, `pypyodbc`, `access_parser`), lista drivers ODBC e indica se o driver Access esta presente.

## estrutura

- interface/ - app Flask e utilitarios
- static/ - UI
- tools/ - scripts de apoio
- tests/ - testes automatizados

## conversores

- convert_mdbtools.py - recomendado para Linux e macOS
- convert_jackcess.py - mais confiavel, usa Java
- convert_pyaccess_parser.py - puro Python
- convert_pyodbc.py - Windows e ODBC

Detalhes completos em [readme original](docs/readme_original.md).

## requisitos

- Python 3.13.x (recomendado)
- Dependencias em `requirements.txt` (inclui: `pyodbc`, `pandas`, `matplotlib`)
- Windows: driver Microsoft Access ODBC instalado (Access Database Engine 2016/2019)
- Opcional: `direnv` e `pyenv` para ativacao automatica

## ambiente automatico (direnv + pyenv)

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

## fallback manual (sem direnv)

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

## dependencias (obrigatorio)

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

Verificacao (recomendado):
```
python tools/check_dependencies.py
```

A interface completa registra o status de dependencias no log e expõe em `/admin/status` e `/api/health`.

## checklist rapido (windows)

1) Instale Python 3.13 (64-bit)
```
winget install --id Microsoft.Python.3.13 -e
```
2) Instale o driver ODBC do Access (64-bit)
```
winget install --id Microsoft.AccessDatabaseEngine -e
```
3) Crie e ative a venv
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
4) Instale dependencias e verifique
```
python -m pip install -r requirements.txt
python tools/check_dependencies.py
```
5) Rode o servidor
```
python main.py
```

## driver odbc do access (windows) - obrigatorio

Sem o driver, o `pyodbc` falha com IM002. Instale um destes:
- Microsoft Access Database Engine 2016 (64-bit): https://www.microsoft.com/en-us/download/details.aspx?id=54920
- Microsoft Access Database Engine 2010 (64-bit): https://www.microsoft.com/en-us/download/details.aspx?id=13255

Após instalar, confirme:
```
python -c "import pyodbc; print(pyodbc.drivers())"
```
Deve aparecer: `Microsoft Access Driver (*.mdb, *.accdb)`.

Se o driver aparece mas ainda recebe IM002:
- Confirme que o Python em uso é 64-bit.
- Garanta que a venv ativa é a mesma usada para rodar o servidor.
- Reabra o terminal após instalar o driver.

## instalacao rapida (windows)

Opcao 1: Winget
```
winget install --id Microsoft.Python.3.13 -e
winget install --id Microsoft.AccessDatabaseEngine -e
```

Opcao 2: Chocolatey
```
choco install python --version=3.13.7 -y
choco install accessdatabaseengine -y
```

Opcao 3: Scoop
```
scoop install python
```
Depois instale o Access Database Engine pelo link oficial acima.

## instalacao rapida (linux/macos)

Linux (Ubuntu/Debian):
```
sudo apt update
sudo apt install -y python3 python3-venv
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python tools/check_dependencies.py
```

macOS:
```
brew install python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python tools/check_dependencies.py
```

## validacao completa (antes de usar)

```
python tools/check_dependencies.py
python -c "import pyodbc; print(pyodbc.drivers())"
python -m pytest
```

Se houver falha, consulte os logs do servidor em `/admin/status` (Alertas e logs).

## interface local (flask)

A interface completa esta em `interface/app_flask_local_search.py`.
Veja `interface/readme.md` para detalhes e endpoints.

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

## ferramentas e scripts

Veja `tools/readme.md` para scripts de analise e relatorios.

## ferramentas do backend (guia completo)

Esta secao foi movida para `docs/tools_backend.md`.
Use este arquivo como referencia principal para conversao, indexacao, diagnostico e debug.

## testes e lint

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
