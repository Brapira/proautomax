"""
Robô da portaria: consome a fila do Sentinela e lança no Promax.

    python -m sentinela.robo                    # serviço (fila + aviso)
    python -m sentinela.robo --json envio.json  # processa um envio de arquivo e só imprime (não fala com o Sentinela)
    python -m sentinela.robo --notas TLV2H99    # notas do mapa da placa (ou --notas mapa:361446)

Contrato (doc "Integração Sentinela → Promax"):
    POST {SENTINELA_URL}/proximo             → 200 com o envio | 204 fila vazia
    POST {SENTINELA_URL}/{envioId}/resultado ← {ok, simulado?, erro?, tentarDeNovo?, ...}
    POST http://127.0.0.1:{ROBO_AVISO_PORTA}/acordar  (opcional, o Sentinela avisa que há envio)
    GET  http://127.0.0.1:{ROBO_AVISO_PORTA}/notas?placa=X | ?mapa=N  (Bearer SENTINELA_TOKEN) → {mapa, notas}

.env:
    SENTINELA_URL        padrão http://127.0.0.1:3100/api/integracao/promax
    SENTINELA_TOKEN      o INTEGRACAO_TOKEN do Sentinela
    PROMAX_SENTINELA_USER / PROMAX_SENTINELA_SENHA   conta exclusiva da integração
    PROMAX_UNIDADE
    PROMAX_GRAVAR        0 (padrão) = simulação: só consulta o Promax e devolve o que seria enviado
    ROBO_AVISO_PORTA     padrão 8765 (0 desliga)
    ROBO_INTERVALO       segundos entre consultas à fila, padrão 30
"""

import json
import logging
import os
import sqlite3
import sys
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

from promax_http.cliente import PromaxErro, PromaxHTTP, SessaoInvalida
from sentinela.portaria import Consulta, Portaria

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIARIO = os.path.join(RAIZ, "logs", "sentinela_diario.sqlite")


class ErroDefinitivo(Exception):
    """Erro que não se resolve tentando de novo (dado errado, cadastro faltando)."""


# ---------------------------------------------------------------------------
# Diário de idempotência
# ---------------------------------------------------------------------------

class Diario:
    """
    O que já foi mandado ao Promax, por chave de idempotência. Status:
    'gravando' antes do passo que grava, 'gravado' depois, 'simulado' na simulação.
    Um 'gravando' que sobra (caiu no meio) bloqueia a repetição: alguém confere à mão.
    """

    def __init__(self, caminho=DIARIO):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        self.db = sqlite3.connect(caminho, check_same_thread=False)
        self.db.execute("""create table if not exists envios(
            idempotencia text primary key, envio_id integer, evento text, status text,
            dados text, resposta text, atualizado text default (datetime('now','localtime')))""")
        self.db.commit()

    def status(self, chave: str) -> tuple[str, dict] | None:
        row = self.db.execute("select status, resposta from envios where idempotencia=?", (chave,)).fetchone()
        return (row[0], json.loads(row[1] or "{}")) if row else None

    def marcar(self, envio: dict, status: str, resposta: dict | None = None):
        self.db.execute(
            "insert or replace into envios(idempotencia, envio_id, evento, status, dados, resposta, atualizado) "
            "values (?,?,?,?,?,?,datetime('now','localtime'))",
            (envio["idempotencia"], envio.get("envioId"), envio.get("evento"), status,
             json.dumps(envio, ensure_ascii=False), json.dumps(resposta or {}, ensure_ascii=False)))
        self.db.commit()


# ---------------------------------------------------------------------------
# Processamento de um envio
# ---------------------------------------------------------------------------

def _validar(envio: dict) -> tuple[str, str, str | None]:
    """Devolve (evento, placa, mapa) ou levanta ErroDefinitivo."""
    if not envio.get("idempotencia"):
        raise ErroDefinitivo("envio sem campo idempotencia")
    evento = envio.get("evento")
    if evento not in ("saida", "entrada"):
        raise ErroDefinitivo(f"evento desconhecido: {evento!r}")
    viagem = envio.get("viagem") or {}
    placa = ((viagem.get("veiculo") or {}).get("placa") or "").replace("-", "").strip().upper()
    if not placa:
        raise ErroDefinitivo("viagem sem veiculo.placa")
    mapa = str(viagem.get("mapa") or "").strip() or None
    return evento, placa, mapa


class Robo:
    def __init__(self, gravar: bool, diario: Diario):
        self.gravar = gravar
        self.diario = diario
        self.promax: PromaxHTTP | None = None
        self.trava = threading.Lock()   # uma sessão do Promax: fila e rota /notas se revezam

    def _logar(self):
        self.promax = PromaxHTTP(os.environ["PROMAX_SENTINELA_USER"], os.environ["PROMAX_SENTINELA_SENHA"],
                                 unidade=os.getenv("PROMAX_UNIDADE"), timeout=60)
        self.promax.login()

    def _no_promax(self, fn):
        """Roda fn(Portaria); refaz o login uma vez se a sessão caiu ou expirou."""
        for tentativa in (1, 2):
            if self.promax is None:
                self._logar()
            try:
                return fn(Portaria(self.promax))
            except (SessaoInvalida, PromaxErro) as e:
                if tentativa == 2:
                    raise
                logging.warning(f"Sessão do Promax caiu ({e}); entrando de novo")
                self.promax = None

    def _consultar(self, evento: str, placa: str, mapa: str | None) -> Consulta:
        if evento == "saida":
            return self._no_promax(lambda p: p.consultar_saida(placa, mapa))
        return self._no_promax(lambda p: p.consultar_entrada(placa))

    def notas(self, placa: str | None = None, mapa: str | None = None) -> dict:
        """Rota GET /notas: mapa (descoberto pela placa na tela de entrada, se preciso) e suas notas."""
        with self.trava:
            if not mapa:
                c = self._consultar("entrada", placa.replace("-", "").strip().upper(), None)
                if c.erro:
                    return {"mapa": None, "notas": [], "erro": c.erro}
                mapa = None if c.sem_mapa else c.campos["mapa"].lstrip("0")
            if not mapa:
                return {"mapa": None, "notas": []}
            return {"mapa": mapa, "notas": self._no_promax(lambda p: p.notas_do_mapa(mapa))}

    def processar(self, envio: dict) -> dict:
        """Resultado no formato do /resultado. Nunca levanta exceção."""
        with self.trava:
            return self._processar(envio)

    def _processar(self, envio: dict) -> dict:
        try:
            evento, placa, mapa = _validar(envio)
            chave = envio["idempotencia"]

            anterior = self.diario.status(chave)
            if anterior and anterior[0] == "gravado":
                return {**anterior[1], "repetido": True}
            if anterior and anterior[0] == "gravando":
                raise ErroDefinitivo("tentativa anterior caiu no meio da gravação: conferir no Promax à mão")

            c = self._consultar(evento, placa, mapa)
            info = {"evento": evento, "placa": placa, "mensagensPromax": c.mensagens}

            if c.sem_mapa:
                # Regra do negócio: sem mapa não há lançamento (manutenção, por exemplo)
                res = {"ok": True, "lancado": False, "simulado": not self.gravar,
                       "motivo": "veículo sem mapa no Promax: não há o que lançar", **info}
                self.diario.marcar(envio, "gravado" if self.gravar else "simulado", res)
                return res
            if c.erro:
                raise ErroDefinitivo(f"Promax: {c.erro}")

            avisos = []
            if evento == "entrada" and mapa and c.campos.get("mapa", "").lstrip("0") != mapa.lstrip("0"):
                avisos.append(f"mapa do Sentinela ({mapa}) difere do Promax ({c.campos.get('mapa')})")
            seria = {"call": "PW02212C" if evento == "saida" else "PW02213C", "opcao": "6", **c.campos}
            if evento == "saida":
                km = (envio.get("viagem") or {}).get("km")
                if km:
                    seria["kmAtual"] = str(km)
                cod = ((envio.get("viagem") or {}).get("motorista") or {}).get("codigoPromax")
                if cod:
                    seria["cdMotorista"] = str(cod)

            if evento == "saida" and c.campos.get("mapa"):
                # O Sentinela anexa as notas ao caminhão (devolução na volta)
                info["notas"] = self._no_promax(lambda p: p.notas_do_mapa(c.campos["mapa"].lstrip("0")))

            if not self.gravar:
                res = {"ok": True, "simulado": True, "protocoloPromax": None,
                       "seriaEnviado": seria, "avisos": avisos, **info}
                self.diario.marcar(envio, "simulado", res)
                return res

            self.diario.marcar(envio, "gravando")
            Portaria(self.promax).gravar(c)   # levanta NotImplementedError até a captura
            res = {"ok": True, "protocoloPromax": None, "avisos": avisos, **info}
            self.diario.marcar(envio, "gravado", res)
            return res

        except ErroDefinitivo as e:
            return {"ok": False, "erro": str(e), "tentarDeNovo": False}
        except NotImplementedError as e:
            return {"ok": False, "erro": str(e), "tentarDeNovo": False}
        except Exception as e:
            logging.exception("Falha ao processar envio")
            self.promax = None   # recomeça a sessão na próxima
            return {"ok": False, "erro": f"{type(e).__name__}: {e}", "tentarDeNovo": True}


# ---------------------------------------------------------------------------
# Sentinela
# ---------------------------------------------------------------------------

class Sentinela:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"

    def proximo(self) -> dict | None:
        r = self.http.post(f"{self.url}/proximo", timeout=15)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def resultado(self, envio_id, res: dict):
        r = self.http.post(f"{self.url}/{envio_id}/resultado", json=res, timeout=15)
        r.raise_for_status()


def _servidor(porta: int, acordar: threading.Event, robo: Robo, token: str):
    """POST /acordar (aviso do Sentinela) e GET /notas?placa=|mapa= — só em 127.0.0.1."""
    class Handler(BaseHTTPRequestHandler):
        def _responder(self, codigo: int, corpo: dict | None = None):
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else b""
            self.send_response(codigo)
            if corpo is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_POST(self):
            if self.path.rstrip("/") == "/acordar":
                acordar.set()
                return self._responder(204)
            self._responder(404, {"erro": "rota inexistente"})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") != "/notas":
                return self._responder(404, {"erro": "rota inexistente"})
            if self.headers.get("Authorization") != f"Bearer {token}":
                return self._responder(401, {"erro": "token inválido"})
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if not (q.get("placa") or q.get("mapa")):
                return self._responder(400, {"erro": "informe placa ou mapa"})
            try:
                self._responder(200, robo.notas(placa=q.get("placa"), mapa=q.get("mapa")))
            except Exception as e:
                logging.exception("Falha em /notas")
                robo.promax = None
                self._responder(502, {"erro": f"{type(e).__name__}: {e}"})

        def log_message(self, *_):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logging.info(f"Rotas locais em http://127.0.0.1:{porta} (/acordar, /notas)")


def servir(robo: Robo):
    token = os.environ["SENTINELA_TOKEN"]
    sentinela = Sentinela(os.getenv("SENTINELA_URL", "http://127.0.0.1:3100/api/integracao/promax"), token)
    intervalo = int(os.getenv("ROBO_INTERVALO", "30"))
    acordar = threading.Event()
    porta = int(os.getenv("ROBO_AVISO_PORTA", "8765"))
    if porta:
        _servidor(porta, acordar, robo, token)

    logging.info(f"Robô da portaria no ar ({'GRAVANDO' if robo.gravar else 'simulação'})")
    while True:
        try:
            envio = sentinela.proximo()
        except Exception as e:
            logging.warning(f"Sentinela fora? {e}")
            envio = None
        if envio is None:
            acordar.wait(intervalo)
            acordar.clear()
            continue

        logging.info(f"Envio {envio.get('envioId')} ({envio.get('evento')}, tentativa {envio.get('tentativa')})")
        res = robo.processar(envio)
        logging.info(f"Envio {envio.get('envioId')}: {json.dumps(res, ensure_ascii=False)}")
        try:
            sentinela.resultado(envio.get("envioId"), res)
        except Exception as e:
            # A reserva expira em 5 min e o envio volta pra fila; o diário evita lançar duas vezes
            logging.error(f"Não consegui devolver o resultado do envio {envio.get('envioId')}: {e}")


def main(args: list[str]):
    load_dotenv(os.path.join(RAIZ, ".env"))
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m %H:%M:%S")
    gravar = os.getenv("PROMAX_GRAVAR", "0") == "1"
    robo = Robo(gravar, Diario())

    if args[:1] == ["--json"]:
        with open(args[1], encoding="utf-8") as f:
            envio = json.load(f)
        print(json.dumps(robo.processar(envio), ensure_ascii=False, indent=2))
        return
    if args[:1] == ["--notas"]:
        alvo = args[1]
        r = robo.notas(mapa=alvo[5:]) if alvo.startswith("mapa:") else robo.notas(placa=alvo)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    servir(robo)


if __name__ == "__main__":
    main(sys.argv[1:])
