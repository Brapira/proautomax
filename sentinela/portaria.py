"""
Telas da portaria do Promax: saída 03.11.02.01 (PW02212C) e entrada 03.11.02.02 (PW02213C).

As telas mandam cada passo pelo quadro de baixo (EnviarFormulario) e a resposta
é um script que mexe na tela de cima: põe valores, mostra alertas, habilita
botões. Aqui lemos esse script em vez de executá-lo.

Passos de LEITURA (seguros, os mesmos que a tela faz quando o porteiro digita):
    saída:   opcao 2 = carrega a placa;  opcao 4 = carrega o mapa
    entrada: opcao 9 = carrega a placa;  opcao 2 = carrega o mapa (encadeado pela própria tela)

Passos que GRAVAM (saída 6/3, entrada 6/11): ainda sem captura do Fiddler —
gravar() recusa até lá.

Regra do negócio: sem mapa no Promax não há lançamento (ex.: manutenção). O
Promax responde "Saída liberada, veículo deve estar vazio" e limpa a tela.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from promax_http.cliente import ENCODING, PromaxHTTP, RelatorioVazio, TelaRotina

MENU_SAIDA = "031102010000"
MENU_ENTRADA = "031102020000"
MENU_NOTAS = "030237000000"

# all('campo').value = '...' | "..." | FormataCampo('...', ...)
_RE_VALOR = re.compile(
    r"all\s*\(\s*'(\w+)'\s*\)\s*\.value\s*=\s*"
    r"(?:'([^']*)'|\"([^\"]*)\"|\S*FormataCampo\(\s*'([^']*)')")
_RE_ALERTA = re.compile(r"alert\s*\(\s*'([^']*)'")
# Bloco de erro do servidor (igual nas duas telas): alert('msg'); if( '<campo>' != '' ){ foco no campo
_RE_ERRO = re.compile(r"alert\s*\(\s*'([^']*)'\s*\);\s*if\(\s*'\w*'\s*!=\s*''\s*\)")


def _valores(js: str) -> dict[str, str]:
    """Valores literais que a resposta põe nos campos (o último de cada campo vale)."""
    vals = {}
    for m in _RE_VALOR.finditer(js):
        vals[m.group(1)] = next(g for g in m.groups()[1:] if g is not None)
    return vals


@dataclass
class Consulta:
    """O que o Promax respondeu às consultas (só leitura) de uma placa."""
    evento: str
    placa: str
    lancavel: bool = False          # há o que lançar (tem mapa e nada impede)
    sem_mapa: bool = False          # Promax não tem mapa pra placa: não há lançamento
    erro: str | None = None         # motivo pra não lançar (placa inexistente, mapa em trânsito...)
    mensagens: list[str] = field(default_factory=list)
    campos: dict[str, str] = field(default_factory=dict)   # como ficaria o form antes de salvar
    opcoes_motorista: list[str] = field(default_factory=list)


class Portaria:
    def __init__(self, promax: PromaxHTTP):
        self.promax = promax

    def _passo(self, tela: TelaRotina, campos: dict, opcao: str) -> str:
        resp = self.promax.enviar(tela, campos, opcao, via_quadro=True)
        return resp.content.decode(ENCODING, "replace")

    # ---------- saída ----------

    def consultar_saida(self, placa: str, mapa: str | None) -> Consulta:
        c = Consulta("saida", placa)
        tela = self.promax.abrir_rotina(MENU_SAIDA)

        r = self._passo(tela, {"placa": placa}, "2")
        c.campos.update({"placa": placa, **_valores(r)})
        # O script decide por: if( '<mensagem>' == '' ) ... if( '<código>' == '01' ) cancela
        msg = re.search(r"if\(\s*'([^']*)'\s*==\s*''\s*\)", r)
        cod = re.search(r"if\(\s*'(\d\d)'\s*==\s*'01'\s*\)", r)
        msg, cod = (msg.group(1) if msg else None), (cod.group(1) if cod else None)
        if msg:
            c.mensagens.append(msg)

        if msg is None and cod is None:
            # Sem o bloco de decisão: placa recusada (ex.: "Placa não cadastrada")
            c.erro = "; ".join(_RE_ALERTA.findall(r)) or "resposta inesperada do Promax ao carregar a placa"
            return c
        if cod == "01" and msg and "liberada" in msg.lower():
            c.sem_mapa = True
            return c
        if cod == "01":
            c.erro = msg or "Promax recusou a placa"
            return c
        if cod == "51":
            # A tela habilita Salvar direto, sem pedir mapa (caso ainda não visto)
            c.lancavel = True
            return c

        # Mensagem vazia ou código 52: a tela libera o campo mapa
        if not mapa:
            c.erro = "Promax pede o mapa e o Sentinela não informou"
            return c
        r = self._passo(tela, {**c.campos, "mapa": mapa}, "4")
        c.campos.update({"mapa": mapa, **_valores(r)})
        c.mensagens += _RE_ALERTA.findall(r)
        c.opcoes_motorista = re.findall(r"new Option\s*\(([^)]*)\)", r)
        c.lancavel = True   # sem captura ainda não sabemos distinguir alerta de erro aqui
        return c

    # ---------- entrada ----------

    def consultar_entrada(self, placa: str) -> Consulta:
        """Na entrada só a placa é digitada; mapa e motorista o Promax preenche (travados)."""
        c = Consulta("entrada", placa)
        tela = self.promax.abrir_rotina(MENU_ENTRADA)

        r9 = self._passo(tela, {"placa": placa}, "9")
        alertas9 = _RE_ALERTA.findall(r9)
        if "EnviarFormulario" not in r9:
            c.erro = "; ".join(alertas9) or "Promax recusou a placa"
            return c

        r = self._passo(tela, {"placa": placa}, "2")
        erro = _RE_ERRO.search(r)
        if erro:
            c.erro = erro.group(1)
            return c
        c.campos.update({"placa": placa, **_valores(r)})
        # Os alertas desta resposta estão em todos os ramos do script (nem todos
        # executam); só os da opcao 9 são mensagens reais.
        c.mensagens = alertas9
        mapa = c.campos.get("mapa", "").strip("0")
        if not mapa:
            c.sem_mapa = True
            return c
        c.lancavel = True
        return c

    # ---------- notas do mapa ----------

    def notas_do_mapa(self, mapa: str, dias: int = 20) -> list[dict]:
        """
        Notas do mapa pela 03.02.37 (quebra 19 = Mapa, sem itens): ~2 s.
        status: E = emitida, D = devolvida (entre outros do Promax).
        """
        tela = self.promax.abrir_rotina(MENU_NOTAS)
        hoje = date.today()
        try:
            dados = self.promax.executar(tela, {
                "quebra1": "19", "quebra1Inicial": mapa, "quebra1Final": mapa, "quebra2": "00", "itens": "N",
                "quebra2Inicial": None, "quebra2Final": None, "quebra3Inicial": None, "quebra3Final": None,
                "dataInicial": (hoje - timedelta(days=dias)).strftime("%d/%m/%Y"),
                "dataFinal": hoje.strftime("%d/%m/%Y")})
        except RelatorioVazio:
            return []
        notas = []
        for l in csv.DictReader(io.StringIO(dados.decode(ENCODING, "replace")), delimiter=";"):
            l = {(k or "").strip(): (v or "").strip() for k, v in l.items()}
            if l.get("Mapa", "").replace(".", "").lstrip("0") != mapa.lstrip("0"):
                continue
            notas.append({
                "nota": l["Nota"], "serie": l["Serie"], "status": l["Status"],
                "cliente": l["Nome"], "codCliente": l["Cliente"],
                "valor": float(l["Total"].replace(".", "").replace(",", ".") or 0),
                "chave": l["Chave de Acesso NF-e"], "emissao": l["Emissao"]})
        return notas

    # ---------- gravação ----------

    def gravar(self, consulta: Consulta):
        raise NotImplementedError(
            "Gravação na portaria ainda não implementada: falta a captura do Fiddler "
            "de uma saída e uma entrada reais")
