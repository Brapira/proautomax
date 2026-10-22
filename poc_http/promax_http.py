"""
Cliente HTTP do Promax — PROVA DE CONCEITO (sem navegador).

Reproduz o que o navegador faz, descoberto a partir de uma captura de tráfego:

    1. Login em 2 etapas (PP00100.exe ppopcao=1 → ppopcao=2).
       A senha da 2ª etapa já vem codificada pelo servidor num campo oculto.
    2. SessionID / SubSessionID são gerados no NAVEGADOR (MontaSessionID() do
       Promax) — aqui fazemos o mesmo em Python. Não há cookies envolvidos.
    3. Abrir rotina:     ppopcao=6 / 7 / 8 / 00 / 9 com call=<MenuID>
    4. Visualizar:       POST com os campos do formulário da rotina + GeraExcel=1
    5. Gerar CSV:        reenvia o form1 da página do relatório com opcao=88
                         → a resposta traz window.open("../tmp/rels/<arquivo>.csv.inf")
    6. Baixar:           GET em /pw/tmp/rels/<arquivo>.csv.inf
"""

import json
import logging
import random
import re
from html.parser import HTMLParser
from urllib.parse import urlencode

import requests
import truststore

# Verifica o HTTPS pelo repositório de certificados do Windows (igual ao Edge).
# O servidor do Promax não envia o certificado intermediário da Sectigo; o
# Windows completa a cadeia sozinho, o bundle padrão do requests (certifi) não.
truststore.inject_into_ssl()

BASE = "https://brapira.promaxcloud.com.br/pw"
CGI = f"{BASE}/cgi-bin/PP00100.exe"
ENCODING = "cp1252"   # o Promax responde e espera windows-1252

# O servidor foi feito pro IE; nos mantemos iguais ao navegador capturado
HEADERS = {
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; "
                  ".NET4.0C; .NET4.0E; .NET CLR 2.0.50727; .NET CLR 3.0.30729; .NET CLR 3.5.30729)",
    "Accept-Language": "pt-BR",
}


class PromaxErro(Exception):
    pass


def gerar_session_id() -> str:
    """Cópia da função JS MontaSessionID() do Promax (ex.: 'y9Jg3o28425100')."""
    con = list("bcdfghjklmnpqrstvyxzw")
    num = list("1234567890")
    vog = ["a", "e", "i", "o", "u", "A", "E", "I", "O", "U", "C", "K", "I", "J", "K", "L"]
    r1, r2 = random.random(), random.random()
    letras = (con[int(r1 * len(con))] + num[int(r1 * len(num))] + vog[int(r1 * len(vog))]
              + con[int(r2 * len(con))] + num[int(r2 * len(num))] + vog[int(r2 * len(vog))])
    return letras + str(int(67891346 * (random.random() + 0.2)))


class _LeitorForm(HTMLParser):
    """Coleta inputs/selects de um <form name=...> (o HTML do Promax é bem 'solto')."""

    def __init__(self, nome_form):
        super().__init__()
        self.nome_form = nome_form.lower()
        self.dentro = False
        self.campos: dict[str, str] = {}
        self.opcoes: dict[str, list[str]] = {}
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self.dentro = a.get("name", "").lower() == self.nome_form
        elif not self.dentro:
            return
        elif tag == "input" and a.get("name") and a.get("type", "").lower() not in ("submit", "button"):
            self.campos[a["name"]] = a.get("value", "").strip()
        elif tag == "select" and a.get("name"):
            self._select = a["name"]
            self.opcoes[self._select] = []
        elif tag == "option" and self._select:
            self.opcoes[self._select].append(a.get("value", "").strip())

    def handle_endtag(self, tag):
        if tag == "form":
            self.dentro = False
        elif tag == "select":
            self._select = None


def ler_form(html: str, nome: str) -> _LeitorForm:
    leitor = _LeitorForm(nome)
    leitor.feed(html)
    return leitor


def alertas(html: str) -> list[str]:
    """Mensagens de alert('...') que o Promax manda dentro do HTML."""
    return re.findall(r"alert\s*\(\s*'([^']*)'", html)


class PromaxHTTP:
    def __init__(self, usuario: str, senha: str, unidade: str | None = None, timeout=120):
        self.usuario = usuario
        self.senha = senha
        self.unidade = unidade
        self.timeout = timeout
        self.http = requests.Session()
        self.http.headers.update(HEADERS)
        self.session_id: str | None = None

    # ---------- baixo nível ----------

    def _get(self, url, **params) -> str:
        r = self.http.get(url, params=params or None, timeout=self.timeout)
        r.raise_for_status()
        return r.content.decode(ENCODING, errors="replace")

    def _post(self, url, campos: dict, referer: str | None = None) -> str:
        corpo = urlencode(campos, encoding=ENCODING)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if referer:
            headers["Referer"] = referer
        r = self.http.post(url, data=corpo, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r.content.decode(ENCODING, errors="replace")

    # ---------- login ----------

    def login(self):
        url = f"{CGI}?ppopcao=1"

        # Etapa 1: usuário + senha em texto (igual ao navegador, via HTTPS)
        campos = {
            "SessionID": "", "ppopcao": "1", "opcaomenu": "", "call": "", "versaoBase": "12.25",
            "Animate": "0", "animpath": "", "ssoLogin": "",
            "Usuario": self.usuario, "Senha": self.senha, "cmdConfirma": "Confirma",
        }
        # Usa os campos reais da página de login se ela vier (ex.: versaoBase atualizada)
        try:
            pagina = ler_form(self._get(url), "frmLogin")
            campos.update({k: v for k, v in pagina.campos.items() if k not in ("Usuario", "Senha")})
        except Exception as e:
            logging.debug(f"Página de login não lida, usando campos padrão: {e}")
        html1 = self._post(url, campos, referer=url)

        # Etapa 2: o servidor devolve a senha já codificada + lista de unidades
        form = ler_form(html1, "frmLogin")
        if "Senha" not in form.campos or not form.campos["Senha"]:
            raise PromaxErro(f"Login etapa 1 falhou. Alertas: {alertas(html1) or 'nenhum'}")

        unidades = form.opcoes.get("unidade", [])
        unidade = self.unidade or (unidades[0] if unidades else "")
        if self.unidade and unidades and self.unidade not in unidades:
            raise PromaxErro(f"Unidade {self.unidade} não disponível. Opções: {unidades}")

        self.session_id = gerar_session_id()
        campos2 = dict(form.campos)
        campos2.update({"SessionID": self.session_id, "Usuario": self.usuario,
                        "unidade": unidade, "cmdConfirma": "Confirma"})
        html2 = self._post(url, campos2, referer=url)
        for msg in alertas(html2):
            logging.info(f"   Promax diz: {msg}")

        # Mesmo passo do navegador após o login (carrega o menu). A validação
        # real da sessão acontece em abrir_rotina() (que exige JSON válido).
        self._post(CGI, {"SessionID": self.session_id, "ppopcao": "3"})
        logging.info(f"✅ Login HTTP ok (unidade {unidade})")

    # ---------- rotina ----------

    def abrir_rotina(self, menu_id: str) -> tuple[str, str, str]:
        """
        Abre a rotina no servidor. Retorna (sub_session_id, programa, url_rotina).
        `menu_id` é o código de 12 dígitos do menu, ex.: '030224000000'.
        """
        sid = self.session_id
        # Responde JSON com o programa da rotina: {"atalho": [{"prg": "PW02084R.exe", ...}]}
        resp = self._post(CGI, {"SessionID": sid, "ppopcao": "6", "call": "PP00101", "opcao": "1", "MenuID": menu_id})
        try:
            atalho = json.loads(resp)["atalho"][0]
        except Exception:
            raise PromaxErro(f"Rotina {menu_id} não abriu (sem permissão ou sessão inválida): {resp[:300]}")
        programa = atalho["prg"].removesuffix(".exe")

        sub = gerar_session_id()
        base = {"SessionID": sid, "SubSessionID": sub}
        self._get(CGI, SessionID=sid, ppopcao="7", call=menu_id, SubSessionID=sub)
        self._get(CGI, **base, ppopcao="8", call=menu_id, ssprx="00")
        url_rotina = f"{CGI}?" + urlencode({**base, "opcao": "0", "frame": "0", "ppopcao": "00", "call": menu_id}) + "&"
        self._get(url_rotina)
        self._get(CGI, **base, ppopcao="9", call=menu_id)
        logging.info(f"📂 Rotina {menu_id} aberta (programa {programa})")
        return sub, programa, url_rotina

    def baixar_csv(self, menu_id: str, parametros: dict) -> bytes:
        """
        Executa a rotina com `parametros` (os campos do formulário dela, como o
        navegador envia) e devolve o conteúdo do CSV.
        """
        sub, programa, url_rotina = self.abrir_rotina(menu_id)

        # Visualizar (com GeraExcel=1, como o navegador manda quando o CSV será gerado)
        campos = {"SessionID": self.session_id, "SubSessionID": sub, "opcao": "1", "ppopcao": "00",
                  "call": programa, **parametros,
                  "BotVisualizar": "<LABEL><U>V</U>isualizar</LABEL>", "GeraExcel": "1"}
        logging.info("📤 Gerando relatório...")
        html_rel = self._post(url_rotina, campos, referer=url_rotina)

        form1 = ler_form(html_rel, "form1").campos
        if not form1:
            msgs = alertas(html_rel)
            raise PromaxErro(f"Relatório não gerado. Alertas: {msgs or 'nenhum'}")

        # Botão CSV: reenvia o form1 do relatório com opcao=88
        form1.update({"opcao": "88", "opcaorelat": "3", "GerExecl": "<LABEL><U>C</U>SV</LABEL>"})
        logging.info("📄 Pedindo CSV...")
        html_csv = self._post(url_rotina, form1, referer=url_rotina)

        m = re.search(r"tmp/rels/([^\"']+\.csv[^\"']*)", html_csv)
        if not m:
            raise PromaxErro(f"Link do CSV não encontrado. Alertas: {alertas(html_csv) or 'nenhum'}")

        r = self.http.get(f"{BASE}/tmp/rels/{m.group(1)}", timeout=self.timeout)
        r.raise_for_status()
        logging.info(f"✅ CSV baixado: {m.group(1)} ({len(r.content)} bytes)")
        return r.content
