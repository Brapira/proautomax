"""
Executa as rotinas do Promax via HTTP — sem navegador, tela, IA ou pywinauto.

    python main_http.py                  # usa rotinas.json
    python main_http.py rotinas_teste.json       # outro JSON (ex.: teste de uma rotina)

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
import subprocess
import sys
import threading
import time
from datetime import datetime

from dotenv import load_dotenv

from function.config_rotinas import carregar_config, resolver_item
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
    if os.name != "nt" and (len(destino) > 1 and destino[1] == ":" or "${" in destino):
        # No Linux, 'C:/...' viraria uma pasta 'C:' dentro do projeto
        raise RuntimeError(f"Destino inválido neste servidor: {destino} (confira DATABEER_BASE no .env)")
    os.makedirs(destino, exist_ok=True)
    caminho = os.path.join(destino, nome)
    temporario = caminho + ".tmp"
    with open(temporario, "wb") as f:
        f.write(conteudo)
    os.replace(temporario, caminho)
    enviar_nuvem(caminho)
    return caminho


def enviar_nuvem(caminho: str):
    """
    Sem a pasta do OneDrive sincronizada (ex.: Linux), RCLONE_REMOTE manda cada
    arquivo salvo pro mesmo caminho relativo a DATABEER_BASE no remote:
        DATABEER_BASE=/home/.../databeer_local   RCLONE_REMOTE=databeer:
    Vazio (Windows com OneDrive) = não faz nada. Falha no envio = rotina com erro.
    """
    remote = os.getenv("RCLONE_REMOTE", "").strip()
    if not remote:
        return
    rel = os.path.relpath(caminho, os.environ["DATABEER_BASE"])
    if rel.startswith(".."):
        raise RuntimeError(f"{caminho} fora do DATABEER_BASE: não sei pra onde mandar no {remote}")
    rel = rel.replace(os.sep, "/")
    alvo = remote + rel if remote.endswith((":", "/")) else f"{remote}/{rel}"
    r = subprocess.run(["rclone", "copyto", caminho, alvo], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"rclone copyto falhou ({r.returncode}): {(r.stderr or r.stdout).strip()[-500:]}")
    logging.info(f"☁️  enviado para {alvo}")


class Resultado:
    def __init__(self):
        self.trava = threading.Lock()
        self.salvas, self.erros, self.ignoradas = [], [], []

    def anotar(self, lista: str, codigo: str):
        with self.trava:
            getattr(self, lista).append(codigo)


# Quantas vezes uma rotina que falhou volta pro FIM da fila (0 = não tenta de novo)
RETENTATIVAS = int(os.getenv("HTTP_RETENTATIVAS", "2"))


def rodar_rotina(promax: PromaxHTTP, item: dict, tentativa: int, fila: queue.Queue,
                 resultado: Resultado) -> bool:
    """Roda uma rotina. Devolve False se falhou (a sessão pode estar ruim)."""
    codigo = item["codigo"]
    destino, nome, params = resolver_item(item)
    sufixo = f" (tentativa {tentativa}/{RETENTATIVAS + 1})" if tentativa > 1 else ""
    logging.info(f"▶  {item.get('descricao', codigo)} → {nome}{sufixo}")
    t0 = time.time()
    try:
        conteudo = ROTINAS[codigo].baixar(promax, params)
        caminho = salvar(conteudo, destino, nome)
        logging.info(f"✓ {codigo} salvo em {caminho} ({len(conteudo):,} bytes, {time.time() - t0:.0f}s)")
        resultado.anotar("salvas", codigo)
        return True
    except RelatorioVazio as e:
        # Resposta do Promax (sem dados / bloqueado): tentar de novo daria o mesmo
        logging.warning(f"⏭️  {codigo} sem relatório: {e}")
        resultado.anotar("ignoradas", codigo)
        return True
    except Exception as e:
        if tentativa <= RETENTATIVAS:
            # Vai pro fim da fila: as outras seguem e ela tenta de novo mais tarde
            logging.warning(f"⚠️ {codigo} falhou ({e}) — volta pro fim da fila "
                            f"(tentativa {tentativa + 1}/{RETENTATIVAS + 1})")
            fila.put((item, tentativa + 1))
        else:
            logging.error(f"❌ {codigo} falhou após {tentativa} tentativa(s): {e}")
            resultado.anotar("erros", codigo)
        return False


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
            item, tentativa = fila.get_nowait()
        except queue.Empty:
            return
        if not rodar_rotina(promax, item, tentativa, fila, resultado):
            # A falha pode ter sido sessão derrubada: entra de novo antes da próxima
            try:
                promax.login()
            except Exception as e:
                logging.error(f"❌ Novo login da conta {usuario} falhou — saindo: {e}")
                return


RAIZ = os.path.dirname(os.path.abspath(__file__))


def main(caminho_json: str):
    # Caminho explícito: o agente pode chamar o script de outro diretório
    load_dotenv(os.path.join(RAIZ, ".env"))
    configurar_log()

    itens = [i for i in carregar_config(caminho_json) if i.get("ativo", True)]
    http = [i for i in itens if i["codigo"] in ROTINAS and ROTINAS[i["codigo"]].validada]
    fora = [i["codigo"] for i in itens if i not in http]
    if fora:
        logging.info(f"↪️  Sem versão HTTP validada (continuam no main.py): {fora}")

    resultado = Resultado()
    if not http:
        logging.info("Nenhuma rotina ativa com versão HTTP. Nada a fazer.")
        return

    contas = contas_http()
    logging.info(f"👥 Contas HTTP: {[c[0] for c in contas]}")
    # Pesadas primeiro: com N contas, as grandes rodam em paralelo desde o início
    http.sort(key=lambda i: not ROTINAS[i["codigo"]].pesada)
    fila = queue.Queue()
    for item in http:
        fila.put((item, 1))

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
        sobras.append(fila.get_nowait()[0]["codigo"])
    if sobras:
        logging.critical(f"💀 Rotinas não executadas (nenhuma conta conseguiu logar?): {sobras}")
        notificar_erro_critico(f"main_http: rotinas não executadas — {sobras}")
        resultado.erros.extend(sobras)

    tempo = int(time.time() - inicio)
    logar_resumo(resultado, tempo)
    notificar_fim(salvas=resultado.salvas, erros=resultado.erros, ignoradas=resultado.ignoradas,
                  tempo_segundos=tempo)


def logar_resumo(resultado: Resultado, tempo: int):
    """Mesmo formato do rotinas/executor.py — o agente (dash) lê essas linhas."""
    logging.info("*==" * 25)
    logging.info("📊 RESUMO DA EXECUÇÃO")
    logging.info(f"✅ Salvas com sucesso:  {len(resultado.salvas)}  → {resultado.salvas}")
    logging.info(f"❌ Com erro:            {len(resultado.erros)} → {resultado.erros}")
    logging.info(f"⏭️  Ignoradas:           {len(resultado.ignoradas)} → {resultado.ignoradas}")
    logging.info("^==" * 25)
    logging.info(f"⏱️  Tempo total de execução: {tempo}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rotinas.json")
