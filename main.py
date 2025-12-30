#!/usr/bin/env python3
"""
MDB2SQL - Interface Dev Test

Script para testar a versão de desenvolvimento da interface Flask com melhorias.
Ultima modificacao: 2025-12-29T14:30:00
"""

import os
import sys
import argparse
import socket
from pathlib import Path
from datetime import datetime


def verificar_porta_disponivel(host, porta):
    """Verifica se a porta está disponível para uso."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            resultado = s.connect_ex((host, porta))
            return resultado != 0
    except socket.error:
        return False


def validar_configuracao(args):
    """Valida a configuração antes de iniciar o servidor."""
    erros = []

    # Validar porta
    if not 1 <= args.port <= 65535:
        erros.append(f"Porta invalida: {args.port}. Deve estar entre 1 e 65535")

    # Validar pasta de uploads
    if args.upload_folder:
        upload_path = Path(args.upload_folder)
        if not upload_path.exists():
            try:
                upload_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                erros.append(f"Sem permissao para criar pasta: {args.upload_folder}")
        elif not upload_path.is_dir():
            erros.append(f"Caminho nao e uma pasta: {args.upload_folder}")

    # Validar tamanho máximo
    if args.max_content_length <= 0:
        erros.append("Tamanho maximo de upload deve ser maior que zero")

    return erros


def configurar_logging():
    """Configura o sistema de logging."""
    # Configurar para suprimir warnings de dependencias
    os.environ["PYTHONWARNINGS"] = "ignore"

    # Configurar Flask para modo menos verboso em producao
    if not os.environ.get("FLASK_DEBUG") == "True":
        os.environ["FLASK_ENV"] = "production"


def main():
    parser = argparse.ArgumentParser(
        description="MDB2SQL - Interface Dev Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python main_dev.py                    # Executar versao dev na porta 5001
  python main_dev.py --port 5002        # Usar porta diferente
  python main_dev.py --debug            # Modo debug completo
        """,
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host para rodar o servidor (padrao: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=5001, help="Porta do servidor dev (padrao: 5001)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Ativar modo debug completo"
    )
    parser.add_argument(
        "--upload-folder", help="Pasta para uploads (padrao: interface/uploads)"
    )
    parser.add_argument(
        "--max-content-length",
        type=int,
        default=500 * 1024 * 1024,
        help="Tamanho maximo de upload em bytes (padrao: 500MB)",
    )
    parser.add_argument(
        "--threaded",
        action="store_true",
        default=True,
        help="Usar threads para melhor desempenho (padrao: ativado)",
    )

    args = parser.parse_args()

    # Gerar timestamp unico para esta execucao
    timestamp_exec = datetime.now().isoformat()

    # Validar configuracao
    erros = validar_configuracao(args)
    if erros:
        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print("Erros de configuracao:")
        for erro in erros:
            print(f"  - {erro}")
        sys.exit(1)

    # Verificar se a porta está disponivel
    if not verificar_porta_disponivel(args.host, args.port):
        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print(f"Erro: Porta {args.port} ja esta em uso no host {args.host}")
        sys.exit(1)

    # Configurar variaveis de ambiente
    os.environ["FLASK_HOST"] = args.host
    os.environ["FLASK_PORT"] = str(args.port)
    os.environ["FLASK_DEBUG"] = str(args.debug)

    if args.upload_folder:
        os.environ["UPLOAD_FOLDER"] = args.upload_folder

    os.environ["MAX_CONTENT_LENGTH"] = str(args.max_content_length)

    # Configurar logging
    configurar_logging()

    # Adicionar diretorio raiz ao path
    script_dir = Path(__file__).parent.absolute()
    sys.path.insert(0, str(script_dir))

    # Importar e executar o app Flask
    try:
        from interface.app_flask_local_search import app

        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print(f"Iniciando servidor Flask")
        print(f"Pasta de uploads: {args.upload_folder or 'interface/uploads'}")
        print(f"Servidor: http://{args.host}:{args.port}")
        print(f"Debug: {'Ativado' if args.debug else 'Desativado'}")
        print(f"Modo threaded: {'Ativado' if args.threaded else 'Desativado'}")
        print("=" * 50)

        # Configuracoes adicionais para melhor desempenho
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0 if args.debug else 31536000
        app.config["TEMPLATES_AUTO_RELOAD"] = args.debug

        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            threaded=args.threaded,
            use_reloader=args.debug,  # So usar reloader em debug
        )

    except ImportError as e:
        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print(f"Erro ao importar o modulo Flask: {e}")
        print("Verifique se as dependencias estao instaladas:")
        print("   pip install -r requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print("Servidor interrompido pelo usuario")
        sys.exit(0)
    except OSError as e:
        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print(f"Erro de sistema operacional: {e}")
        if "Address already in use" in str(e):
            print("A porta ja esta em uso por outro processo")
        sys.exit(1)
    except Exception as e:
        print(f"{timestamp_exec} - MDB2SQL - Interface Dev Test")
        print(f"Erro ao iniciar o servidor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
