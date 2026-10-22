"""
Cliente HTTP do Promax — gera e baixa relatórios SEM navegador.

Reproduz o que o navegador faz (descoberto por captura de tráfego):

    1. Login em 2 etapas (PP00100.exe ppopcao=1 → ppopcao=2).
       A senha da 2ª etapa já vem codificada pelo servidor num campo oculto.
    2. SessionID / SubSessionID são gerados no NAVEGADOR (MontaSessionID() do
       Promax) — aqui fazemos o mesmo em Python. Não há cookies envolvidos.
    3. Abrir rotina:  ppopcao=6 (devolve o programa) → 7 / 8 / 00 / 9.
       A resposta do ppopcao=00 é a tela de parâmetros (form1).
    4. Visualizar:    POST do form1 com opcao=1 (+ GeraExcel=1).
    5. Gerar CSV:     reenvia o form1 da página do relatório com opcao=88
                      → a resposta traz window.open("../tmp/rels/<arquivo>")
    6. Baixar:        GET em /pw/tmp/rels/<arquivo>
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


class SessaoInvalida(PromaxErro):
    """O Promax derrubou a sessão — ele só aceita UMA sessão por usuário, então
    outro login com o mesmo usuário (outro robô, outra máquina) invalida esta."""


class RelatorioVazio(PromaxErro):
    """O Promax não gerou relatório (sem dados ou parâmetro recusado)."""


def gerar_session_id() -> str:
    """Cópia da função JS MontaSessionID() do Promax (ex.: 'y9Jg3o28425100')."""
    con = list("bcdfghjklmnpqrstvyxzw")
    num = list("1234567890")
    vog = ["a", "e", "i", "o", "u", "A", "E", "I", "O", "U", "C", "K", "I", "J", "K", "L"]
    r1, r2 = random.random(), random.random()
    letras = (con[int(r1 * len(con))] + num[int(r1 * len(num))] + vog[int(r1 * len(vog))]
              + con[int(r2 * len(con))] + num[int(r2 * len(num))] + vog[int(r2 * len(vog))])
    return letras + str(int(67891346 * (random.random() + 0.2)))


# ---------------------------------------------------------------------------
# Leitura de formulários
# ---------------------------------------------------------------------------

class _LeitorForm(HTMLParser):
    """
    Lê um <form name=...> e monta o que o navegador ENVIARIA ao submetê-lo:
    texto/ocultos com o valor, checkbox/radio só se marcados, select com a
    opção selecionada (ou a primeira). O HTML do Promax é bem 'solto', por isso
    um parser tolerante em vez de BeautifulSoup/lxml estrito.
    """

    def __init__(self, nome_form):
        super().__init__(convert_charrefs=True)
        self.nome_form = nome_form.lower()
        self.dentro = False
        self.achou = False
        self.campos: dict[str, str] = {}
        self.opcoes: dict[str, list[str]] = {}
        self._select = None
        self._select_tem_selecionada = False
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            self.dentro = a.get("name", "").lower() == self.nome_form
            self.achou |= self.dentro
            return
        if not self.dentro:
            return
        nome = a.get("name")
        if tag == "input" and nome:
            tipo = a.get("type", "text").lower()
            if tipo in ("submit", "button", "image", "reset", "file"):
                return
            if tipo in ("checkbox", "radio"):
                if "checked" in a:
                    self.campos[nome] = a.get("value", "on").strip()
            else:
                self.campos[nome] = a.get("value", "").strip()
        elif tag == "select" and nome:
            self._select = nome
            self._select_tem_selecionada = False
            self.opcoes[nome] = []
        elif tag == "option" and self._select:
            valor = a.get("value", "").strip()
            self.opcoes[self._select].append(valor)
            # Vale a opção 'selected'; sem nenhuma, vale a primeira (como no navegador)
            if "selected" in a and not self._select_tem_selecionada:
                self.campos[self._select] = valor
                self._select_tem_selecionada = True
            elif len(self.opcoes[self._select]) == 1:
                self.campos[self._select] = valor
        elif tag == "textarea" and nome:
            self._textarea = nome
            self.campos[nome] = ""

    def handle_data(self, data):
        if self._textarea:
            self.campos[self._textarea] += data

    def handle_endtag(self, tag):
        if tag == "form":
            self.dentro = False
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def ler_form(html: str, nome: str) -> _LeitorForm:
    leitor = _LeitorForm(nome)
    leitor.feed(html)
    return leitor


_LITERAIS = r"""(?:'[^'\n]*'|"[^"\n]*")(?:\s*\+\s*(?:'[^'\n]*'|"[^"\n]*"))*"""
_RE_JS_VALUE = re.compile(
    r"document\.(?:all|form1|forms\[0\])\.(\w+)\.value\s*=\s*(" + _LITERAIS + r")\s*;")


def _concat_literais(expr: str) -> str:
    return "".join(m.group(1) if m.group(1) is not None else m.group(2)
                   for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", expr))


def defaults_js(html: str) -> dict[str, str]:
    """
    Valores que a página põe via JavaScript ao carregar, ex.:
        document.all.classeFinal.value = 'z';
        document.all.dataFinal.value = '22' + '/' + '10' + '/' + '2026';
    Só pega atribuições de literais (sem variáveis). O mesmo campo costuma
    aparecer em várias funções (iniciar, limpar, desabilitar...): vale o último
    valor NÃO vazio, que é o de inicialização na prática.
    Marcações (.checked = ...) NÃO são lidas: ficam em funções de evento
    (clicar, limpar), não na carga — o estado inicial é o do HTML.
    """
    valores: dict[str, str] = {}
    for m in _RE_JS_VALUE.finditer(html):
        valor = _concat_literais(m.group(2))
        if valor or m.group(1) not in valores:
            valores[m.group(1)] = valor
    return valores


def alertas(html: str) -> list[str]:
    """Mensagens de alert('...') no HTML (podem estar em código não executado)."""
    return [a.replace("\\n", " ").strip() for a in re.findall(r"alert\s*\(\s*'([^']*)'", html)]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

# Botões da página do relatório: todos reenviam o form1 com opcao=88
FORMATOS = {"csv": "3", "salvar": "2"}


class TelaRotina:
    """Rotina aberta no servidor, pronta pra receber os parâmetros."""

    def recarregada(self, html: str) -> "TelaRotina":
        """A mesma rotina após um envio intermediário (a tela volta atualizada)."""
        return TelaRotina(self.menu_id, self.sub_session_id, self.programa, self.url, html)

    def __init__(self, menu_id, sub_session_id, programa, url, html):
        self.menu_id = menu_id
        self.sub_session_id = sub_session_id
        self.programa = programa
        self.url = url
        self.html = html
        form = ler_form(html, "form1")
        if not form.achou:
            raise PromaxErro(f"Tela de parâmetros da rotina {menu_id} não tem form1. "
                             f"Alertas: {alertas(html) or 'nenhum'}")
        self.campos = form.campos
        self.opcoes = form.opcoes
        self.js = defaults_js(html)
        # Telas de cadastro enviam pelo quadro de baixo (EnviarFormulario → SendForm),
        # que a própria tela aponta pra '...ppopcao=00&call=<prog>&frame=9&opcao=1&'
        m = re.search(r"bottom_rotina\.document\.location\.href\s*=\s*\"\.\./cgi-bin/([^\"]+)\"", html)
        self.url_quadro = f"{BASE}/cgi-bin/{m.group(1)}" if m else None


class PromaxHTTP:
    def __init__(self, usuario: str, senha: str, unidade: str | None = None, timeout=900):
        self.usuario = usuario
        self.senha = senha
        self.unidade = unidade
        self.timeout = timeout   # relatórios grandes demoram (a 12.06.01 leva minutos)
        self.http = requests.Session()
        self.http.headers.update(HEADERS)
        self.session_id: str | None = None

    # ---------- baixo nível ----------

    def _get(self, url, **params) -> str:
        r = self.http.get(url, params=params or None, timeout=self.timeout)
        r.raise_for_status()
        return _checar_sessao(r.content.decode(ENCODING, errors="replace"))

    def _post_raw(self, url, campos: dict, referer: str | None = None) -> requests.Response:
        corpo = urlencode(campos, encoding=ENCODING, errors="replace")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if referer:
            headers["Referer"] = referer
        r = self.http.post(url, data=corpo, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r

    def _post(self, url, campos: dict, referer: str | None = None) -> str:
        return _checar_sessao(self._post_raw(url, campos, referer).content.decode(ENCODING, errors="replace"))

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
        if not form.campos.get("Senha"):
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

    def abrir_rotina(self, menu_id: str) -> TelaRotina:
        """`menu_id`: código de 12 dígitos do menu, ex.: '030224000000'."""
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
        url = f"{CGI}?" + urlencode({**base, "opcao": "0", "frame": "0", "ppopcao": "00", "call": menu_id}) + "&"
        html = self._get(url)
        self._get(CGI, **base, ppopcao="9", call=menu_id)
        logging.info(f"📂 Rotina {menu_id} aberta (programa {programa})")
        return TelaRotina(menu_id, sub, programa, url, html)

    def montar_parametros(self, tela: TelaRotina, alteracoes: dict) -> dict:
        """
        Parâmetros que o navegador enviaria: padrões do HTML + valores postos
        pelo JS da página + `alteracoes` da rotina (None = não enviar o campo;
        True/False em checkbox = marcar/desmarcar com o valor do HTML).
        """
        for nome in alteracoes:
            if not re.search(rf"""name=['"]?{re.escape(nome)}\b""", tela.html, re.I):
                logging.warning(f"⚠️ Campo '{nome}' não existe na tela da rotina {tela.menu_id}")

        campos = dict(tela.campos)
        for nome, valor in {**tela.js, **alteracoes}.items():
            if valor is None or valor is False:
                campos.pop(nome, None)
            elif valor is True:
                campos[nome] = tela.campos.get(nome) or _valor_checkbox(tela.html, nome)
            else:
                campos[nome] = str(valor)
        campos.update({"SessionID": self.session_id, "SubSessionID": tela.sub_session_id,
                       "ppopcao": "00", "call": tela.programa})
        return campos

    def enviar(self, tela: TelaRotina, alteracoes: dict, opcao: str,
               via_quadro: bool = False) -> requests.Response:
        """
        Envia o form1 da tela com `opcao` (o que cada botão da tela faz).
        via_quadro: botões que usam EnviarFormulario() mandam pelo quadro de baixo.
        """
        campos = self.montar_parametros(tela, alteracoes)
        campos["opcao"] = opcao
        if opcao == "1" and not via_quadro:   # Visualizar
            campos.update({"GeraExcel": "1", "BotVisualizar": "<LABEL><U>V</U>isualizar</LABEL>"})
        url = tela.url
        if via_quadro:
            if not tela.url_quadro:
                raise PromaxErro(f"Rotina {tela.menu_id} não tem quadro de envio (bottom_rotina)")
            url = tela.url_quadro
            self._get(url)          # o navegador carrega o quadro antes de usar
            campos["frame"] = "9"   # campo próprio do form do quadro
        return self._post_raw(url, campos, referer=url)

    def executar(self, tela: TelaRotina, alteracoes: dict, opcao: str = "1",
                 formato: str = "csv", passos=(), via_quadro: bool = False) -> bytes:
        """
        Roda a rotina e devolve o arquivo.

        opcao:      botão da tela — "1" = Visualizar (relatório → botão CSV/Salvar);
                    outros (ex.: "9", "12") = botões que já geram o arquivo direto.
        formato:    botão usado na página do relatório: "csv" ou "salvar".
        passos:     envios intermediários antes do final, como [("2", {...})] —
                    ex.: 'Carregar tabela' da 01.15.01. Cada um devolve a tela atualizada.
        via_quadro: o botão usa EnviarFormulario() (telas de cadastro).
        """
        for opcao_passo, alt_passo in passos:
            logging.info(f"↪️  Passo intermediário (opcao={opcao_passo})...")
            resp = self.enviar(tela, {**alteracoes, **alt_passo}, opcao_passo, via_quadro)
            html = resp.content.decode(ENCODING, "replace")
            # Pelo quadro, a resposta só atualiza a tela; relê a tela inteira
            tela = tela.recarregada(self._get(tela.url) if via_quadro else html)

        logging.info("📤 Gerando relatório...")
        resp = self.enviar(tela, alteracoes, opcao, via_quadro)
        if _eh_arquivo(resp):
            logging.info(f"✅ Arquivo recebido direto ({len(resp.content)} bytes)")
            return resp.content
        html_rel = _checar_sessao(resp.content.decode(ENCODING, errors="replace"))

        # Botões de download direto (e algumas rotinas) já devolvem o link
        link = _link_relatorio(html_rel)
        if not link:
            form1 = ler_form(html_rel, "form1")
            if not form1.achou or "paginaatual" not in form1.campos:
                raise RelatorioVazio(_motivo(html_rel))

            # Botão CSV/Salvar da página do relatório: reenvia o form1 com opcao=88
            form1.campos.update({"opcao": "88", "opcaorelat": FORMATOS[formato]})
            logging.info(f"📄 Pedindo arquivo ({formato})...")
            html_arq = self._post(tela.url, form1.campos, referer=tela.url)
            link = _link_relatorio(html_arq)
            if not link:
                raise PromaxErro(f"Link do arquivo não encontrado. {_motivo(html_arq)}")

        r = self.http.get(f"{BASE}/tmp/rels/{link}", timeout=self.timeout)
        r.raise_for_status()
        logging.info(f"✅ Arquivo baixado: {link} ({len(r.content)} bytes)")
        return r.content


def _eh_arquivo(resp: requests.Response) -> bool:
    disp = resp.headers.get("Content-Disposition", "").lower()
    tipo = resp.headers.get("Content-Type", "").lower()
    return "attachment" in disp or (bool(tipo) and "html" not in tipo and "json" not in tipo)


def _checar_sessao(html: str) -> str:
    if "Sessão inválida" in html[:3000]:
        raise SessaoInvalida("Sessão do Promax derrubada (outro login com o mesmo usuário?)")
    return html


def _valor_checkbox(html: str, nome: str) -> str:
    m = re.search(rf"""name=['"]?{re.escape(nome)}['"]?[^>]*value=['"]?([^'" >]*)""", html, re.I)
    return m.group(1).strip() if m else "S"


def _link_relatorio(html: str) -> str | None:
    m = re.search(r"tmp/rels/([^\"'\s]+)", html)
    return m.group(1) if m else None


def _motivo(html: str) -> str:
    """Tenta extrair a mensagem do Promax de uma resposta sem relatório."""
    msgs = alertas(html)
    texto = re.sub(r"(?s)<script.*?</script>|<[^>]+>", " ", html)
    texto = re.sub(r"\s+", " ", texto).strip()
    return f"Alertas: {msgs or 'nenhum'} | Texto: {texto[:300] or '(vazio)'}"
