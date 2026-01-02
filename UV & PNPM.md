## `uv`


## comandos `uv`

| Tarefa                             | Comando do `uv`                                     | Observacao                                                                 |
| ---------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------- |
| Instalar um pacote                 | `uv pip install <nome_do_pacote>`                   | Instala o pacote mantendo `pyproject.toml` e `uv.lock` intactos [[9]].     |
| Remover um pacote                  | `uv pip uninstall <nome_do_pacote>`                 | Comando direto para desinstalacao.                                         |
| Atualizar um pacote                | `uv pip install --upgrade <nome_do_pacote>`         | Forca a instalacao da versao mais recente.                                 |
| Instalar uma 'tool' Python         | `uv tool install <nome_da_tool>`                    | Instala e disponibiliza uma ferramenta Python globalmente.                 |
| Atualizacao geral de pacotes       | `uv pip sync requirements.txt` ou `uv sync`        | Sincroniza o ambiente com os requisitos do projeto.                        |
| Criar ambiente virtual com Python  | `uv venv --python <versao>`                         | Se a versao nao estiver instalada, `uv` a busca e instala [[7]].           |

| Tarefa                              | Comando do `uv` ou Conceito              | Observacao                                                                               |
| ----------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------- |
| Instalar uma ferramenta globalmente | `uv tool install <nome_da_tool>`         | Torna a ferramenta disponivel globalmente para o usuario, mantendo isolamento.           |
| Atualizar todas as 'tools'          | `uv tool upgrade --all`                  | Atualiza todas as ferramentas instaladas via `uv tool` para suas versoes mais recentes.  |
| Instalacao System-Wide de Pacotes   | Nao e o foco principal; nao recomendado. | O `uv` foca em ambientes isolados e `tools`. Instalacoes system-wide sao desencorajadas. |

## `pnpm`

| Tarefa                                      | Comando                                                             | Observacao                                                      |
| ------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| Instalar pacotes listados em `package.json` | `pnpm install` ou `pnpm i`                                          | Instala todas as dependencias do projeto [[19]].                |
| Instalar um pacote globalmente              | `pnpm add -g <nome_do_pacote>`                                      | Adiciona um pacote como dependencia global.                     |
| Remover um pacote                           | `pnpm uninstall <nome_do_pacote>` ou `pnpm remove <nome_do_pacote>` | Desinstala o pacote especificado.                               |
| Atualizar um pacote                         | `pnpm update <nome_do_pacote>` ou `pnpm up <nome_do_pacote>`        | Atualiza para a versao mais recente compativel.                 |
| Instalar uma 'tool' Node.js                 | `pnpm dlx <nome_do_pacote>`                                         | Executa uma ferramenta Node.js sem adiciona-la ao projeto.      |
| Atualizacao geral de pacotes                | `pnpm update --latest` ou `pnpm up --latest`                        | Atualiza todas as dependencias para suas versoes mais recentes. |
| Instalar apenas dependencias de producao    | `pnpm install --prod` ou `pnpm i --prod`                            | Ignora dependencias de desenvolvimento.                         |

| Tarefa                                  | Comando                                         | Observacao                                                                        |
| --------------------------------------- | ----------------------------------------------- | --------------------------------------------------------------------------------- |
| Instalar um pacote globalmente          | `pnpm add -g <nome_do_pacote>`                  | Torna o pacote e seus executaveis disponiveis globalmente para o usuario.         |
| Atualizar todos os pacotes globais      | `pnpm update -g`                                | Atualiza todos os pacotes instalados globalmente para suas versoes mais recentes. |
| Instalacao System-Wide (todos usuarios) | `sudo pnpm add -g <nome_do_pacote>` (Linux/Mac) | Requer permissao elevada; nao e o padrao e pode causar conflitos.                 |
| Executar uma ferramenta temporariamente | `pnpm dlx <nome_do_pacote>`                     | Executa uma ferramenta sem instala-la globalmente.                                |
