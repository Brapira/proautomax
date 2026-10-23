"""
Ferramenta de desenvolvimento: abre a TELA de parâmetros de rotinas (sem
gerar relatório) e salva o HTML + um resumo dos campos, pra montar a versão
HTTP de cada rotina.

    python -m promax_http.inspecionar 120601 0421 150501

Saída em promax_http/inspecao/ (fora do git).
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv

from promax_http.cliente import PromaxHTTP
from promax_http.contas import contas_http

PASTA = os.path.join(os.path.dirname(__file__), "inspecao")


def menu_id(atalho: str) -> str:
    return atalho.ljust(12, "0")


def main(atalhos: list[str]):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    os.makedirs(PASTA, exist_ok=True)

    usuario, senha = contas_http()[0]   # conta HTTP, pra não derrubar o robô Selenium
    promax = PromaxHTTP(usuario, senha, unidade=os.getenv("PROMAX_UNIDADE"))
    promax.login()
    for atalho in atalhos:
        try:
            tela = promax.abrir_rotina(menu_id(atalho))
        except Exception as e:
            logging.error(f"❌ {atalho}: {e}")
            continue
        with open(os.path.join(PASTA, f"{atalho}.html"), "w", encoding="utf-8") as f:
            f.write(tela.html)
        resumo = {"programa": tela.programa, "campos": tela.campos, "opcoes": tela.opcoes, "js": tela.js}
        with open(os.path.join(PASTA, f"{atalho}.json"), "w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=2)
        logging.info(f"💾 {atalho}: {len(tela.campos)} campos ({tela.programa})")


if __name__ == "__main__":
    main(sys.argv[1:])
