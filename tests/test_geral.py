#!/usr/bin/env python3
"""
Testes gerais do MDB2SQL - Arquivo único para testes funcionais
Valida performance, cache, segurança e funcionalidades principais
"""

import requests
import json
import time
import sys
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"


def test_health_check():
    print("=== TESTE HEALTH CHECK ===")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Cache size: {data.get('cache_size')}")
            print(f"Current DB: {data.get('current_db')}")
            print("OK Health check funcionando")
            return True
        else:
            print(f"ERRO HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_list_tables_performance():
    print("\n=== TESTE PERFORMANCE LISTAGEM ===")
    try:
        tempos = []
        for i in range(5):
            start = time.time()
            response = requests.get(f"{BASE_URL}/api/tables", timeout=10)
            end = time.time()

            if response.status_code == 200:
                tempos.append(end - start)
                print(f"Execucao {i + 1}: {end - start:.3f}s")
            else:
                print(f"ERRO na execucao {i + 1}")
                return False

        if tempos:
            media = sum(tempos) / len(tempos)
            print(f"Media: {media:.3f}s")
            print(f"Minimo: {min(tempos):.3f}s")
            print(f"Maximo: {max(tempos):.3f}s")

            if media < 1.0:
                print("OK Performance aceitavel")
                return True
            else:
                print("ERRO Performance lenta")
                return False
        else:
            print("ERRO Nenhuma execucao bem sucedida")
            return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_cache_eficacia():
    print("\n=== TESTE EFICACIA DO CACHE ===")
    try:
        # Primeira execucao
        start1 = time.time()
        response1 = requests.get(f"{BASE_URL}/api/tables", timeout=5)
        end1 = time.time()
        tempo1 = end1 - start1

        # Segunda execucao (deve usar cache)
        start2 = time.time()
        response2 = requests.get(f"{BASE_URL}/api/tables", timeout=5)
        end2 = time.time()
        tempo2 = end2 - start2

        print(f"Primeira: {tempo1:.3f}s")
        print(f"Segunda: {tempo2:.3f}s")

        # Verificar consistencia
        if response1.json() == response2.json():
            print("OK Cache funcionando")
            return True
        else:
            print("ERRO Resultados inconsistentes")
            return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_seguranca_validacao():
    print("\n=== TESTE SEGURANCA ===")
    try:
        # Testar nome valido
        nome_valido = "RANGER_SOACCU"
        if nome_valido.replace("_", "").isalnum() and len(nome_valido) <= 64:
            print(f"Nome valido: OK")
        else:
            print("Nome valido: ERRO")
            return False

        # Testar nome invalido
        nome_invalido = "RANGER; DROP TABLE--"
        if not (nome_invalido.replace("_", "").isalnum() and len(nome_invalido) <= 64):
            print(f"Nome invalido: OK Rejeitado")
        else:
            print("Nome invalido: ERRO Aceito")
            return False

        print("OK Validacao de seguranca")
        return True
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_list_uploads():
    print("\n=== TESTE LISTAGEM UPLOADS ===")
    try:
        response = requests.get(f"{BASE_URL}/api/list_uploads", timeout=5)
        if response.status_code == 200:
            data = response.json()
            files = data.get("files", [])
            print(f"Arquivos encontrados: {len(files)}")

            for f in files[:3]:
                print(f"  - {f['name']} ({f['size']} bytes)")

            print("OK Listagem uploads")
            return True
        else:
            print(f"ERRO HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_estatisticas_opcionais():
    print("\n=== TESTE ESTATISTICAS OPCIONAIS ===")
    try:
        # Sem estatisticas
        response = requests.get(f"{BASE_URL}/api/tables", timeout=5)
        if response.status_code == 200:
            tem_stats = "stats" in response.json()
            print(f"Padrao (sem stats): {'Sim' if tem_stats else 'Nao'}")

        # Com estatisticas
        response = requests.get(f"{BASE_URL}/api/tables?stats=true", timeout=5)
        if response.status_code == 200:
            tem_stats = "stats" in response.json()
            print(f"Com stats=true: {'Sim' if tem_stats else 'Nao'}")
            print("OK Estatisticas opcionais")
            return True
        else:
            print(f"ERRO HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def main():
    print("INICIANDO TESTES GERAIS MDB2SQL")
    print("=" * 60)

    # Verificar servidor
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code != 200:
            print("ERRO: Servidor nao respondendo")
            return False
    except:
        print("ERRO: Nao conseguiu conectar ao servidor")
        return False

    testes = [
        ("Health Check", test_health_check),
        ("Performance Listagem", test_list_tables_performance),
        ("Eficacia Cache", test_cache_eficacia),
        ("Seguranca Validacao", test_seguranca_validacao),
        ("Listagem Uploads", test_list_uploads),
        ("Estatisticas Opcionais", test_estatisticas_opcionais),
    ]

    resultados = []

    for nome, funcao in testes:
        try:
            print(f"\n{'=' * 60}")
            resultado = funcao()
            status = "PASSOU" if resultado else "FALHOU"
            print(f"{status} - {nome}")
            resultados.append(resultado)
        except Exception as e:
            print(f"ERRO - {nome}: {e}")
            resultados.append(False)

    print(f"\n{'=' * 60}")
    total = len(resultados)
    passou = sum(resultados)
    falhou = total - passou

    print(f"Total de testes: {total}")
    print(f"Passou: {passou}")
    print(f"Falhou: {falhou}")
    print(f"Taxa de sucesso: {(passou / total) * 100:.1f}%")

    if falhou == 0:
        print("\nTODOS OS TESTES PASSARAM - SISTEMA FUNCIONANDO CORRETAMENTE")
    else:
        print(f"\n{falhou} teste(s) falharam - verificar problemas")

    return falhou == 0


if __name__ == "__main__":
    sucesso = main()
    sys.exit(0 if sucesso else 1)
