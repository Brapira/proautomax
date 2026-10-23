"""
Executa as rotinas do Promax via HTTP — sem navegador, tela, IA ou pywinauto.

    python main_http.py                  # usa rotinas.json
    python main_http.py rotinas_tarde.json

Lê o mesmo JSON do main.py (ativo, destino, nome, params) e roda as rotinas
ativas que já têm versão HTTP validada (promax_http/rotinas.py). As demais
ficam de fora e aparecem no log — continuam pelo main.py (Selenium).

Paralelismo: um trabalhador por conta de PROMAX_HTTP_CONTAS (ver
promax_http/contas.py), cada um com a sua sessão, pegando a próxima rotina
de uma fila — as pesadas primeiro, pra nenhuma grande sobrar pro final.
"""

import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime

from dotenv import load_dotenv

from function.config_rotinas import carregar_config, pular_hoje, resolver_item
from function.teams_notify import notificar_erro_critico, notificar_fim, notificar_inicio
from promax_http.cliente import PromaxHTTP, RelatorioVazio
from promax_http.contas import contas_http
from promax_http.rotinas import ROTINAS


def configurar_log():
    pasta = os.getenv("LOG_DIR_HTTP", "logs")
    os.makedirs(pasta, exist_ok=True)
    arquivo = os.path.join(pasta, f"http_{datetime.now():%Y-%m-%d_%H-%M-%S}.log")
    formato = logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s")
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


class Resultado:
    def __init__(self):
        self.trava = threading.Lock()
        self.salvas, self.erros, self.ignoradas = [], [], []

    def anotar(self, lista: str, codigo: str):
        with self.trava:
            getattr(self, lista).append(codigo)


def rodar_rotina(promax: PromaxHTTP, item: dict, resultado: Resultado):
    codigo = item["codigo"]
    destino, nome, params = resolver_item(item)
    logging.info(f"▶  {item.get('descricao', codigo)} → {nome}")
    t0 = time.time()
    for tentativa in (1, 2):
        try:
            conteudo = ROTINAS[codigo].baixar(promax, params)
            caminho = salvar(conteudo, destino, nome)
            logging.info(f"✓ {codigo} salvo em {caminho} ({len(conteudo):,} bytes, {time.time() - t0:.0f}s)")
            resultado.anotar("salvas", codigo)
            return
        except RelatorioVazio as e:
            logging.warning(f"⏭️  {codigo} sem relatório: {e}")
            resultado.anotar("ignoradas", codigo)
            return
        except Exception as e:
            if tentativa == 1:
                # Sessão pode ter caído (relatórios longos, outro login): loga de novo e tenta mais uma vez
                logging.warning(f"⚠️ {codigo} falhou ({e}) — refazendo login e tentando de novo")
                try:
                    promax.login()
                except Exception as e_login:
                    logging.error(f"❌ Novo login falhou: {e_login}")
                continue
            logging.error(f"❌ {codigo} falhou: {e}")
            resultado.anotar("erros", codigo)


def trabalhador(usuario: str, senha: str, fila: queue.Queue, resultado: Resultado):
    promax = PromaxHTTP(usuario, senha, unidade=os.getenv("PROMAX_UNIDADE"))
    try:
        promax.login()
    except Exception as e:
        # Os outros trabalhadores seguem com a fila; este só sai
        logging.error(f"❌ Login da conta {usuario} falhou: {e}")
        return
    while True:
        try:
            item = fila.get_nowait()
        except queue.Empty:
            return
        rodar_rotina(promax, item, resultado)


def main(caminho_json: str):
    load_dotenv()
    configurar_log()

    itens = [i for i in carregar_config(caminho_json) if i.get("ativo", True)]
    http = [i for i in itens if i["codigo"] in ROTINAS and ROTINAS[i["codigo"]].validada]
    fora = [i["codigo"] for i in itens if i not in http]
    if fora:
        logging.info(f"↪️  Sem versão HTTP validada (continuam no main.py): {fora}")

    resultado = Resultado()
    for item in [i for i in http if pular_hoje(i)]:
        logging.info(f"⏭️  {item['codigo']} pulada — ontem foi domingo")
        resultado.anotar("ignoradas", item["codigo"])
    http = [i for i in http if not pular_hoje(i)]
    if not http:
        logging.info("Nenhuma rotina ativa com versão HTTP. Nada a fazer.")
        return

    contas = contas_http()
    # Pesadas primeiro: com N contas, as grandes rodam em paralelo desde o início
    http.sort(key=lambda i: not ROTINAS[i["codigo"]].pesada)
    fila = queue.Queue()
    for item in http:
        fila.put(item)

    n = min(len(contas), len(http))
    logging.info(f"🚀 {len(http)} rotina(s) HTTP com {n} conta(s) em paralelo: {[c[0] for c in contas[:n]]}")
    notificar_inicio(caminho_json, rotinas_ativas=[i.get("descricao", i["codigo"]) for i in http])
    inicio = time.time()

    threads = [threading.Thread(target=trabalhador, args=(usuario, senha, fila, resultado), name=usuario)
               for usuario, senha in contas[:n]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Se todos os logins falharam, a fila fica com rotinas não executadas
    sobras = []
    while not fila.empty():
        sobras.append(fila.get_nowait()["codigo"])
    if sobras:
        logging.critical(f"💀 Rotinas não executadas (nenhuma conta conseguiu logar?): {sobras}")
        notificar_erro_critico(f"main_http: rotinas não executadas — {sobras}")
        resultado.erros.extend(sobras)

    tempo = int(time.time() - inicio)
    logging.info(f"📊 Salvas {resultado.salvas} | Erros {resultado.erros} | Ignoradas {resultado.ignoradas} | {tempo}s")
    notificar_fim(salvas=resultado.salvas, erros=resultado.erros, ignoradas=resultado.ignoradas,
                  tempo_segundos=tempo)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rotinas.json")
