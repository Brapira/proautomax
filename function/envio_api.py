"""
Envio do relatório de uma rotina para uma API (opção "Enviar também por API" do painel).

A rotina guarda só o NOME do destino (routines.api_destino); URL e token ficam
no .env do servidor, assim nenhum segredo passa pelo Supabase/painel:

    API_SENTINELA_ESCALA_URL=http://127.0.0.1:3100/api/integracao/escala
    API_SENTINELA_ESCALA_TOKEN=...          (vai como Authorization: Bearer)

O nome vira MAIÚSCULO e o que não for letra/número vira '_'
("sentinela-escala" → API_SENTINELA_ESCALA_*).

Corpo (JSON):
    {"rotina": "031129", "gerado_em": "2026-11-28T09:12:00-03:00",
     "linhas": [{"Data": "28/11/2026", "Mapa": "362606", ...}, ...]}
As chaves são as colunas do CSV do Promax, com os espaços de preenchimento tirados.
"""

import csv
import io
import logging
import os
import re
from datetime import datetime

import requests

TIMEOUT = int(os.getenv("API_TIMEOUT", "60"))


def _prefixo(nome: str) -> str:
    return "API_" + re.sub(r"[^A-Z0-9]+", "_", nome.strip().upper()).strip("_")


def csv_para_linhas(conteudo: bytes) -> list[dict]:
    """CSV do Promax (';', colunas com espaços à direita, ';' sobrando no fim) → lista de dicts."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    leitor = csv.reader(io.StringIO(texto), delimiter=";")
    cabecalho = [c.strip() for c in next(leitor, [])]
    linhas = []
    for valores in leitor:
        if not any(v.strip() for v in valores):
            continue
        linhas.append({col: (valores[i].strip() if i < len(valores) else "")
                       for i, col in enumerate(cabecalho) if col})
    return linhas


def enviar_api(destino: str, codigo: str, conteudo: bytes) -> str:
    """Manda o relatório; devolve o resumo da resposta. Erro (config, rede, HTTP != 2xx) levanta RuntimeError."""
    prefixo = _prefixo(destino)
    url = os.getenv(f"{prefixo}_URL", "").strip()
    if not url:
        raise RuntimeError(f"destino '{destino}' sem {prefixo}_URL no .env")
    cabecalhos = {"Content-Type": "application/json"}
    token = os.getenv(f"{prefixo}_TOKEN", "").strip()
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"

    linhas = csv_para_linhas(conteudo)
    corpo = {"rotina": codigo, "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
             "linhas": linhas}
    try:
        r = requests.post(url, json=corpo, headers=cabecalhos, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"sem resposta de {url}: {e}") from e
    resposta = (r.text or "").strip().replace("\n", " ")[:500]
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} de {url}: {resposta}")
    logging.info(f"🔌 {codigo} enviado para '{destino}' ({len(linhas)} linhas): {resposta}")
    return resposta
