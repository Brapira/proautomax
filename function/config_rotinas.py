"""
Leitura do rotinas.json — compartilhada entre o executor Selenium e o HTTP.
"""

import json
import os
import re
from datetime import date, timedelta

from function.data_func import ano_vigente, gerar_nome_mes_vigente, data_ontem_nome


def carregar_config(caminho_json: str) -> list[dict]:
    with open(caminho_json, encoding="utf-8") as f:
        return json.load(f)["execucao"]


def resolver_caminho(caminho: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), caminho)


def pular_hoje(item: dict) -> bool:
    """pularDomingo: não roda quando ontem foi domingo."""
    return bool(item.get("params", {}).get("pularDomingo")) and \
        (date.today() - timedelta(days=1)).weekday() == 6


def resolver_item(item: dict) -> tuple[str, str, dict]:
    """
    Devolve (destino, nome_arquivo, params) de um item do rotinas.json.
    `params` vem sem as chaves que só servem pro executor (pularDomingo).
    """
    params = {k: v for k, v in item.get("params", {}).items() if k != "pularDomingo"}
    codigo = item["codigo"]

    if params.get("nomeMes") == "MES_ATUAL":
        nome = f"{gerar_nome_mes_vigente()}.csv"
    elif params.get("anoVigente") == "ANO_VIGENTE":
        nome = f"{codigo}_{ano_vigente()}.csv"
    else:
        nome = item.get("nome", f"{codigo}.csv")

    if "{DATA_ONTEM}" in nome:
        nome = nome.replace("{DATA_ONTEM}", data_ontem_nome())

    return resolver_caminho(item["destino"]), nome, params
