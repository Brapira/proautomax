"""
Executa as rotinas do Promax via HTTP — sem navegador, tela, IA ou pywinauto.

    python main_http.py                  # usa rotinas.json
    python main_http.py rotinas_tarde.json

Lê o mesmo JSON do main.py (ativo, destino, nome, params) e roda as rotinas
ativas que já têm versão HTTP validada (promax_http/rotinas.py). As demais
ficam de fora e aparecem no log — continuam pelo main.py (Selenium).
"""

import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from function.config_rotinas import carregar_config, pular_hoje, resolver_item
from function.teams_notify import notificar_erro_critico, notificar_fim, notificar_inicio
from promax_http.cliente import PromaxHTTP, RelatorioVazio
from promax_http.rotinas import ROTINAS


def configurar_log():
    pasta = os.getenv("LOG_DIR_HTTP", "logs")
    os.makedirs(pasta, exist_ok=True)
    arquivo = os.path.join(pasta, f"http_{datetime.now():%Y-%m-%d_%H-%M-%S}.log")
    formato = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for handler in (logging.FileHandler(arquivo, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(formato)
        raiz.addHandler(handler)


def salvar(conteudo: bytes, destino: str, nome: str) -> str:
    """Grava num .tmp e troca no fim: quem lê a pasta nunca pega arquivo pela metade."""
    os.makedirs(destino, exist_ok=True)
    caminho = os.path.join(destino, nome)
    temporario = caminho + ".tmp"
    with open(temporario, "wb") as f:
        f.write(conteudo)
    os.replace(temporario, caminho)
    return caminho


def main(caminho_json: str):
    load_dotenv()
    configurar_log()

    itens = [i for i in carregar_config(caminho_json) if i.get("ativo", True)]
    http = [i for i in itens if i["codigo"] in ROTINAS and ROTINAS[i["codigo"]].validada]
    fora = [i["codigo"] for i in itens if i not in http]
    if fora:
        logging.info(f"↪️  Sem versão HTTP validada (continuam no main.py): {fora}")
    if not http:
        logging.info("Nenhuma rotina ativa com versão HTTP. Nada a fazer.")
        return

    notificar_inicio(caminho_json, rotinas_ativas=[i.get("descricao", i["codigo"]) for i in http])
    inicio = time.time()
    salvas, erros, ignoradas = [], [], []

    promax = PromaxHTTP(os.environ["PROMAX_USER"], os.environ["PROMAX_PASSWORD"],
                        unidade=os.getenv("PROMAX_UNIDADE"))
    try:
        promax.login()
    except Exception as e:
        logging.critical(f"💀 Login HTTP falhou: {e}")
        notificar_erro_critico(f"Login HTTP no Promax falhou: {e}")
        raise

    for idx, item in enumerate(http, 1):
        codigo = item["codigo"]
        if pular_hoje(item):
            logging.info(f"⏭️  [{idx}/{len(http)}] {codigo} pulada — ontem foi domingo")
            ignoradas.append(codigo)
            continue

        destino, nome, params = resolver_item(item)
        logging.info(f"▶  [{idx}/{len(http)}] {item.get('descricao', codigo)} → {nome}")
        t0 = time.time()
        for tentativa in (1, 2):
            try:
                conteudo = ROTINAS[codigo].baixar(promax, params)
                caminho = salvar(conteudo, destino, nome)
                logging.info(f"✓ {codigo} salvo em {caminho} ({len(conteudo):,} bytes, {time.time() - t0:.0f}s)")
                salvas.append(codigo)
                break
            except RelatorioVazio as e:
                logging.warning(f"⏭️  {codigo} sem relatório: {e}")
                ignoradas.append(codigo)
                break
            except Exception as e:
                if tentativa == 1:
                    # Sessão pode ter caído (relatórios longos): loga de novo e tenta mais uma vez
                    logging.warning(f"⚠️ {codigo} falhou ({e}) — refazendo login e tentando de novo")
                    try:
                        promax.login()
                    except Exception as e_login:
                        logging.error(f"❌ Novo login falhou: {e_login}")
                    continue
                logging.error(f"❌ {codigo} falhou: {e}")
                erros.append(codigo)

    tempo = int(time.time() - inicio)
    logging.info(f"📊 Salvas {salvas} | Erros {erros} | Ignoradas {ignoradas} | {tempo}s")
    notificar_fim(salvas=salvas, erros=erros, ignoradas=ignoradas, tempo_segundos=tempo)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rotinas.json")
