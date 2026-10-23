"""
Definição das rotinas no modo HTTP.

Cada rotina diz só o que MUDA na tela de parâmetros — o resto vem dos padrões
da própria tela (HTML + JS da página), igual ao navegador. Os campos e valores
são os mesmos que a versão Selenium (rotinas/) preenche.

Convenções dos campos:
    "texto"  → valor do campo/select/radio
    True     → marca o checkbox (com o value dele)
    False    → desmarca o checkbox (não é enviado)
    None     → não envia o campo
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from promax_http.cliente import ENCODING, PromaxHTTP, RelatorioVazio, _motivo


# Datas calculadas na hora (a function/data_func.py congela 'hoje' no import)
def hoje() -> date:
    return date.today()


def ontem() -> str:
    return (hoje() - timedelta(days=1)).strftime("%d/%m/%Y")


def primeiro_dia_mes() -> str:
    return hoje().replace(day=1).strftime("%d/%m/%Y")


def primeiro_dia_ano() -> str:
    return hoje().replace(month=1, day=1).strftime("%d/%m/%Y")


def ano() -> str:
    return hoje().strftime("%Y")


@dataclass(frozen=True)
class RotinaHTTP:
    atalho: str                                   # código do menu (ex.: "120601")
    campos: Callable[[dict], dict] = lambda params: {}
    opcao: str = "1"                              # "1" = Visualizar; outros = download direto
    formato: str = "csv"                          # botão da página do relatório: csv | salvar
    passos: tuple = ()                            # envios intermediários: (("2", {...}),)
    via_quadro: bool = False                      # botão usa EnviarFormulario() (telas de cadastro)
    especial: Callable[[PromaxHTTP, dict], bytes] | None = field(default=None)
    pesada: bool = False                          # relatório grande: começa primeiro no paralelo
    validada: bool = True                         # resultado conferido com o do Selenium?
                                                  # (main_http.py só roda as validadas)

    @property
    def menu_id(self) -> str:
        return self.atalho.ljust(12, "0")

    def baixar(self, promax: PromaxHTTP, params: dict) -> bytes:
        if self.especial:
            return self.especial(promax, params)
        tela = promax.abrir_rotina(self.menu_id)
        return promax.executar(tela, self.campos(params), opcao=self.opcao,
                               formato=self.formato, passos=self.passos, via_quadro=self.via_quadro)


# ---------------------------------------------------------------------------
# Rotinas com fluxo próprio
# ---------------------------------------------------------------------------

GERENCIADOR_ARQUIVOS = "http://brapira.promaxcloud.com.br:8080"


def _baixar_030805(promax: PromaxHTTP, params: dict) -> bytes:
    """
    03.08.05 não tem página de relatório: o Visualizar gera um .txt no
    Gerenciador de Arquivos (porta 8080) e avisa 'Arquivo gerado com sucesso'.
    O arquivo do dia D se chama 2artdDD_0001.txt.
    """
    rotina = ROTINAS["030805"]
    tela = promax.abrir_rotina(rotina.menu_id)
    resp = promax.enviar(tela, {"opcaoRel": "1", "dataInicial": ontem(), "dataFinal": ontem()}, "1")
    html = resp.content.decode(ENCODING, errors="replace")
    if "gerado com sucesso" not in html.lower():
        raise RelatorioVazio(_motivo(html))

    # Abre a sessão no gerenciador com o mesmo SessionID do Promax
    promax.http.get(f"{GERENCIADOR_ARQUIVOS}/?sessionId={promax.session_id}", timeout=promax.timeout).raise_for_status()
    dia = (hoje() - timedelta(days=1)).day
    r = promax.http.get(f"{GERENCIADOR_ARQUIVOS}/arquivos/download/file/dvs/2artd{dia:02d}_0001.txt",
                        timeout=promax.timeout)
    r.raise_for_status()
    return r.content


# ---------------------------------------------------------------------------
# Rotinas — chave = "codigo" do rotinas.json
# ---------------------------------------------------------------------------

# Campos abaixo conferidos com o que o navegador envia (promax_http/capturas/):
# faixas e alçadas que o JS da tela preenche, e campos desabilitados (None)
_030237_COMUM = {
    "quebra1": "14", "itens": "S",
    "quebra1Inicial": "0", "quebra1Final": "99999999", "quebra2Inicial": "0", "quebra2Final": "99999999",
    "quebra3Inicial": None, "quebra3Final": None,
}
_030509 = RotinaHTTP("030509", lambda p: {
    "opcaoRel": "07", "fatorConversao": "H", "consideraCarreto": True,
    "campo1Inicial": "0", "campo1Final": "99999", "campo2Inicial": None, "campo2Final": None, "cdVisao": None})

ROTINAS: dict[str, RotinaHTTP] = {
    # --- 01 Cadastramentos (botões que geram o arquivo direto) ---
    "0111": RotinaHTTP("0111", opcao="9", via_quadro=True),                       # GerarCsv()
    "011501": RotinaHTTP("011501", lambda p: {"numerotabela": "1"}, opcao="12",   # GerarCsv()
                         passos=(("2", {}),), via_quadro=True),                   # CarregarTabela(1)
    "012011": RotinaHTTP("012011", lambda p: {"grPerfilVenda": "05", "todos": True}),
    "012502": RotinaHTTP("012502", opcao="12"),                                   # GerarExcel()
    "01250802": RotinaHTTP("01250802", opcao="12", via_quadro=True),              # GeraPlanilha()

    # --- 02 Controle de Estoque ---
    "020229": RotinaHTTP("020229", lambda p: {"opcaoRel": "1"}, pesada=True),
    "020253": RotinaHTTP("020253", lambda p: {"idClassificacao": "2"}),
    "020512": RotinaHTTP("020512", lambda p: {
        "vasilhame": False, "garrafeira": False, "material": False,
        "idValor": "S", "periodoInicial": primeiro_dia_ano()}),

    # --- 03 Movimentação Diária ---
    "03013604_MES": RotinaHTTP("03013604", lambda p: {
        "dtInicial": primeiro_dia_mes(), "cdAlcadaInicial": "05", "cdAlcadaFinal": "90",
        "idNormal": True, "idBloqueado": True, "idRejeitado": True, "idTransfer": True,
        "idComandado": True, "idSistema": True, "volumePdvInicial": None, "volumePdvFinal": None}, pesada=True),
    "03014701": RotinaHTTP("03014701", lambda p: {
        "quebra1": "01", "dataInicial": primeiro_dia_ano(), "cdAlcadaInicial": "06", "cdAlcadaFinal": "07",
        "pedidosExcluidos": True, "quebra2": None, "quebra3": None,
        "quebra1Inicial": None, "quebra1Final": None, "quebra2Inicial": None, "quebra2Final": None,
        "quebra3Inicial": None, "quebra3Final": None, "subMotivosInicial": None, "subMotivosFinal": None},
        pesada=True, validada=False),  # campos = navegador, mas o Promax respondeu 'Não há CDP' (23/10) — conferir log da VM
    "030237_ENTRADA": RotinaHTTP("030237", lambda p: {
        **_030237_COMUM, "quebra2": "29", "notas": "NE", "listaNotaCompra": True,
        "dataInicial": primeiro_dia_mes()}),
    "030237_SAIDA": RotinaHTTP("030237", lambda p: {
        **_030237_COMUM, "quebra2": "06", "dataInicial": primeiro_dia_mes(), "cdVisao": None}, pesada=True),
    "030509": _030509,
    "030509_MES": _030509,
    "030805": RotinaHTTP("030805", especial=_baixar_030805),
    "031120": RotinaHTTP("031120", lambda p: {"opcaoRel": "1", "dataInicial": primeiro_dia_mes()}),

    # --- 04 Livros Fiscais --- (CSV desabilitado nessa tela: usa o 'Salvar')
    # Parâmetros conferem, mas hoje o Promax devolve só a lista de 'produtos com valor
    # negativo' (inventário bloqueado). O arquivo do Selenium é de 14/08 — decidir antes.
    "0421": RotinaHTTP("0421", lambda p: {
        "opcaoCusto": "3", "checkVasilhame": False, "checkGarrafeira": False,
        "checkMaterial": False, "listaDeposito": "01"}, formato="salvar", validada=False),

    # --- 05 Estatísticas ---
    "0512": RotinaHTTP("0512", lambda p: {"opcaoRel": "06", "idConverteHecto": True}, pesada=True),

    # --- 12 Financeiro ---
    # opcaoRel 01/02 → Habilita() marca 'Pendências de Royalties'
    "120601": RotinaHTTP("120601", lambda p: {"opcaoRel": "01", "idPendRoyalties": True,
                                              "fimVencimento": ontem()}),
    "120601_SEMDATA": RotinaHTTP("120601", lambda p: {"opcaoRel": "01", "idPendRoyalties": True}),

    # --- 15 OBZ --- (listas = códigos concatenados com zeros à esquerda; 99/9999 = Todos)
    "150501": RotinaHTTP("150501", lambda p: {
        "idPeriodo": "A", "dtAno": ano(), "listaNbz": "99", "listaDepto": "9999",
        "listaPacote": "9999", "listaVbz": "9999", "listaConta": "9999999999"}),
}
