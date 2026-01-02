#### tabela de comparação: comandos do wsl vs. systemd

Para facilitar a compreensão, aqui está uma tabela comparando os principais comandos e seus propósitos:

|**Categoria**|**Comando**|**Propósito**|**Exemplo**|
|---|---|---|---|
|WSL|wsl --list|Listar distribuições instaladas|wsl --list --all|
|WSL|wsl --install -d <nome_da_distribuição>|Instalar nova distribuição|wsl --install -d Debian|
|WSL|wsl --set-default <nome_da_distribuição>|Definir distribuição padrão|wsl --set-default Debian|
|WSL|wsl --shutdown|Desligar o WSL|wsl --shutdown|
|WSL|wsl --update|Atualizar o WSL|wsl --update|
|WSL|wsl --version|Verificar versão do WSL|wsl --version|
|WSL|wsl -d <nome_da_distribuição>|Iniciar distribuição específica|wsl -d Debian|
|WSL|wsl -d <nome_da_distribuição> -- <comando>|Executar comando em distribuição específica|wsl -d Debian -- ls|
|Systemd|sudo systemctl start <nome_do_serviço>|Iniciar um serviço|sudo systemctl start cron|
|Systemd|sudo systemctl stop <nome_do_serviço>|Parar um serviço|sudo systemctl stop cron|
|Systemd|sudo systemctl restart <nome_do_serviço>|Reiniciar um serviço|sudo systemctl restart cron|
|Systemd|sudo systemctl status <nome_do_serviço>|Verificar status de um serviço|sudo systemctl status cron|
|Systemd|sudo systemctl enable <nome_do_serviço>|Habilitar serviço na inicialização|sudo systemctl enable cron|
|Systemd|sudo systemctl disable <nome_do_serviço>|Desabilitar serviço na inicialização|sudo systemctl disable cron|
|Systemd|sudo systemctl list-units --type=service|Listar serviços ativos||
|Systemd|ps -p 1 -o comm=|Verificar se o systemd é PID 1|ps -p 1 -o comm=|
