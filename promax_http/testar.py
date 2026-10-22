"""
Testa rotinas HTTP e compara com o arquivo que o robô (Selenium) salvou.

    python -m promax_http.testar 120601 0421          # algumas
    python -m promax_http.testar                      # todas do rotinas.json
    python -m promax_http.testar --captura 030111     # só compara campos com a captura do navegador

Salva em promax_http/saida/ (NUNCA no destino real) e compara com o arquivo
de produção: cabeçalho igual, nº de linhas e tamanho. Diferença pequena de
linhas é normal (o robô rodou em outro horário).
"""

import json
import logging
import os
import sys
import time

from dotenv import load_dotenv

from function.config_rotinas import carregar_config, resolver_item
from promax_http.cliente import PromaxHTTP, RelatorioVazio
from promax_http.rotinas import ROTINAS

SAIDA = os.path.join(os.path.dirname(__file__), "saida")


def _resumo(conteudo: bytes) -> tuple[bytes, int]:
    linhas = conteudo.splitlines()
    return (linhas[0].strip() if linhas else b""), len(linhas)


def comparar(novo: bytes, caminho_prod: str) -> str:
    if not os.path.exists(caminho_prod):
        return "sem arquivo de produção pra comparar"
    with open(caminho_prod, "rb") as f:
        prod = f.read()
    cab_n, lin_n = _resumo(novo)
    cab_p, lin_p = _resumo(prod)
    idade_h = (time.time() - os.path.getmtime(caminho_prod)) / 3600
    cab = "cabeçalho IGUAL" if cab_n == cab_p else "cabeçalho DIFERENTE"
    dif = (lin_n - lin_p) / lin_p * 100 if lin_p else 0
    return (f"{cab} | linhas {lin_n} vs {lin_p} ({dif:+.1f}%) | "
            f"bytes {len(novo)} vs {len(prod)} | produção de {idade_h:.0f}h atrás")


_IGNORAR = {"SessionID", "SubSessionID", "opcao", "GeraExcel", "BotVisualizar", "frame"}


def comparar_captura(promax: PromaxHTTP, codigo: str, params: dict):
    """
    Compara (sem gerar relatório) os campos que o HTTP montaria com os que o
    navegador enviou — capturados com CAPTURAR_FORM=1 (function/capturar_form.py).
    """
    caminho = os.path.join(os.path.dirname(__file__), "capturas", f"{codigo}.json")
    if not os.path.exists(caminho):
        print(f"{codigo}: sem captura em {caminho}")
        return
    with open(caminho, encoding="utf-8") as f:
        navegador = {k: v for k, v in json.load(f)["campos"] if k not in _IGNORAR}
    rotina = ROTINAS[codigo]
    tela = promax.abrir_rotina(rotina.menu_id)
    http = {k: v for k, v in promax.montar_parametros(tela, rotina.campos(params)).items() if k not in _IGNORAR}

    print(f"\n===== {codigo}: HTTP x navegador =====")
    for k in sorted(set(navegador) | set(http)):
        if navegador.get(k) != http.get(k):
            print(f"  {k:28} http={http.get(k)!r:30} navegador={navegador.get(k)!r}")


def main(codigos: list[str]):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    os.makedirs(SAIDA, exist_ok=True)

    so_captura = "--captura" in codigos
    codigos = [c for c in codigos if c != "--captura"]

    itens = {i["codigo"]: i for i in carregar_config("rotinas.json")}
    codigos = codigos or [c for c in itens if c in ROTINAS]

    promax = PromaxHTTP(os.environ["PROMAX_USER"], os.environ["PROMAX_PASSWORD"],
                        unidade=os.getenv("PROMAX_UNIDADE"))
    promax.login()

    if so_captura:
        for codigo in codigos:
            comparar_captura(promax, codigo, resolver_item(itens[codigo])[2])
        return

    resultados = {}
    for codigo in codigos:
        logging.info(f"===== {codigo} =====")
        inicio = time.time()
        try:
            item = itens[codigo]
            destino, nome, params = resolver_item(item)
            conteudo = ROTINAS[codigo].baixar(promax, params)
            with open(os.path.join(SAIDA, f"{codigo}__{nome}"), "wb") as f:
                f.write(conteudo)
            resultados[codigo] = f"OK {time.time() - inicio:.0f}s | " + comparar(conteudo, os.path.join(destino, nome))
        except RelatorioVazio as e:
            resultados[codigo] = f"VAZIO {e}"
        except Exception as e:
            resultados[codigo] = f"ERRO {type(e).__name__}: {e}"
        logging.info(f"{codigo}: {resultados[codigo]}")

    print("\n===== RESUMO =====")
    for codigo, r in resultados.items():
        print(f"{codigo:16} {r}")


if __name__ == "__main__":
    main(sys.argv[1:])
