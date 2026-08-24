"""
ProAutoMax - Módulo de Visão com IA
=====================================
Substitui o template matching de imagem por análise visual inteligente via Claude API.

Dependências:
    pip install anthropic

.env:
    ANTHROPIC_API_KEY=sk-ant-...
"""

import base64
import json
import logging
import os
import time
from io import BytesIO

import pyautogui
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


# ===========================================================================
# Configuração
# ===========================================================================

_client = None

def _get_client() -> Anthropic:
    """Inicializa o cliente Anthropic uma única vez (singleton)."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY não encontrada no .env. "
                "Adicione: ANTHROPIC_API_KEY=sk-ant-..."
            )
        _client = Anthropic(api_key=api_key)
        logging.info("✓ Cliente Anthropic inicializado")
    return _client


MODELO = "claude-haiku-4-5-20251001"
MAX_TOKENS = 500

# Preços por milhão de tokens — Sonnet 4 (atualizar se a Anthropic mudar)
# https://www.anthropic.com/pricing
_PRECO_INPUT_POR_MILHAO  = 1.0    # USD
_PRECO_OUTPUT_POR_MILHAO = 5.0   # USD

# Estados padronizados reconhecidos pelo sistema
ESTADOS = {
    "CSV_DISPONIVEL":  "csv_disponivel",
    "PROCESSANDO":     "processando",
    "SEM_DADOS":       "sem_dados",
    "ERRO":            "erro",
    "ALERTA":          "alerta",
    "PRONTO":          "pronto",
    "DOWNLOAD_SALVAR": "download_salvar",
    "DESCONHECIDO":    "desconhecido",
}


# ===========================================================================
# Contador de tokens — acumulador global da sessão
# ===========================================================================

_uso = {
    "input_tokens":  0,
    "output_tokens": 0,
    "chamadas":      0,
    "erros_api":     0,
}


def _registrar_uso(input_tokens: int, output_tokens: int):
    """Acumula o consumo de tokens de uma chamada."""
    _uso["input_tokens"]  += input_tokens
    _uso["output_tokens"] += output_tokens
    _uso["chamadas"]      += 1


def relatorio_uso_tokens(logar: bool = True) -> dict:
    """
    Retorna (e opcionalmente loga) o consumo total de tokens da sessão.

    Returns:
        Dict com: input_tokens, output_tokens, chamadas, custo_usd, custo_brl_aprox
    """
    i = _uso["input_tokens"]
    o = _uso["output_tokens"]
    c = _uso["chamadas"]
    e = _uso["erros_api"]

    custo_usd = (i * _PRECO_INPUT_POR_MILHAO + o * _PRECO_OUTPUT_POR_MILHAO) / 1_000_000
    custo_brl = custo_usd * 5.70  # taxa aproximada — ajuste conforme necessário

    resultado = {
        "input_tokens":    i,
        "output_tokens":   o,
        "total_tokens":    i + o,
        "chamadas":        c,
        "erros_api":       e,
        "custo_usd":       round(custo_usd, 6),
        "custo_brl_aprox": round(custo_brl, 4),
    }

    if logar:
        logging.info("─" * 50)
        logging.info("🔢 CONSUMO DE TOKENS DA SESSÃO")
        logging.info(f"   Chamadas realizadas : {c}")
        logging.info(f"   Erros de API        : {e}")
        logging.info(f"   Tokens de entrada   : {i:,}")
        logging.info(f"   Tokens de saída     : {o:,}")
        logging.info(f"   Total de tokens     : {i + o:,}")
        logging.info(f"   Custo estimado      : ${custo_usd:.6f} USD (~R$ {custo_brl:.4f})")
        logging.info("─" * 50)

    return resultado


def resetar_contador():
    """Zera o acumulador. Útil em testes ou execuções múltiplas no mesmo processo."""
    global _uso
    _uso = {"input_tokens": 0, "output_tokens": 0, "chamadas": 0, "erros_api": 0}


# ===========================================================================
# Core: Screenshot + Chamada à API
# ===========================================================================

# Fator de escala do último screenshot.
# A IA recebe a imagem reduzida (1280px) e devolve coordenadas relativas a ela.
# Precisamos multiplicar por _escala_x/_escala_y para chegar na posição real da tela.
_escala_x: float = 1.0
_escala_y: float = 1.0
# Dimensões da imagem reduzida enviada à IA (p/ validar coordenadas devolvidas)
_img_w: int = 0
_img_h: int = 0


def tirar_screenshot() -> str:
    """
    Tira screenshot da tela inteira e retorna como base64 PNG.
    Reduz para 1280px de largura para economizar tokens.

    IMPORTANTE: armazena _escala_x/_escala_y para que clicar_elemento_ia()
    converta coordenadas da IA (espaço da imagem reduzida) para a tela real.
    """
    global _escala_x, _escala_y, _img_w, _img_h

    screenshot   = pyautogui.screenshot()
    largura_real = screenshot.width
    altura_real  = screenshot.height

    largura_max = 1280
    if largura_real > largura_max:
        proporcao    = largura_max / largura_real
        nova_largura = largura_max
        nova_altura  = int(altura_real * proporcao)
        screenshot   = screenshot.resize((nova_largura, nova_altura))

        _escala_x = largura_real / nova_largura   # ex: 1920/1280 = 1.5
        _escala_y = altura_real  / nova_altura
        _img_w, _img_h = nova_largura, nova_altura
    else:
        _escala_x = 1.0
        _escala_y = 1.0
        _img_w, _img_h = largura_real, altura_real

    buffer = BytesIO()
    screenshot.save(buffer, format="PNG", optimize=True)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def analisar_tela(
    pergunta: str,
    screenshot_b64: str | None = None,
) -> dict:
    """
    Envia um screenshot para o Claude e obtém uma análise estruturada.

    Args:
        pergunta:       O que você quer saber sobre a tela.
        screenshot_b64: Screenshot em base64. Se None, tira um novo.

    Returns:
        Dict com chaves: estado, confianca, mensagem, acao, coordenadas (opcional)
    """
    if screenshot_b64 is None:
        screenshot_b64 = tirar_screenshot()

    system_prompt = """Você é um assistente especializado em analisar screenshots de sistemas ERP web.
O sistema é o Promax, rodando no Edge (modo IE) via Selenium em uma VM Windows.

Identifique o estado atual da tela e retorne APENAS um JSON válido (sem markdown, sem explicações).

Estados possíveis:
- "csv_disponivel"   → Botão CSV/Exportar visível e clicável na barra de ferramentas
- "processando"      → Loader, spinner, ou texto "Processando..." / "Aguarde..."
- "sem_dados"        → Dialog ou mensagem informando que não há registros
- "erro"             → Mensagem de erro do sistema
- "alerta"           → Qualquer popup ou dialog aberto (OK, Confirmar, X, filtros, etc.)
- "pronto"           → Tela principal carregada, sem popups, pronta para interação
- "download_salvar"  → Barra de download do Edge com botão "Salvar" visível na parte inferior
- "desconhecido"     → Nenhum dos estados acima identificado claramente

Formato de resposta (JSON puro):
{
  "estado": "<estado>",
  "confianca": <0-10>,
  "mensagem": "<descrição objetiva do que você viu na tela>",
  "acao": "<continuar|skip|aguardar|clicar_csv|aceitar_alerta|salvar_download|fechar_popup>",
  "coordenadas": {"x": <int>, "y": <int>}
}

"coordenadas" é opcional — inclua apenas se um elemento precisa ser clicado e está visível.
"confianca": 10 = certeza absoluta, 0 = chute."""

    try:
        client = _get_client()

        response = client.messages.create(
            model=MODELO,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": pergunta},
                    ],
                }
            ],
        )

        # Registra o consumo real retornado pela API
        _registrar_uso(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        logging.debug(
            f"🔢 +{response.usage.input_tokens} in / +{response.usage.output_tokens} out "
            f"(sessão: {_uso['input_tokens'] + _uso['output_tokens']:,} tokens)"
        )

        resposta = response.content[0].text.strip()
        resposta = resposta.replace("```json", "").replace("```", "").strip()
        return json.loads(resposta)

    except json.JSONDecodeError as e:
        _uso["erros_api"] += 1
        logging.error(f"❌ IA retornou JSON inválido: {e}")
        return {"estado": "desconhecido", "confianca": 0, "mensagem": "Resposta inválida da IA", "acao": "skip"}

    except Exception as e:
        _uso["erros_api"] += 1
        logging.error(f"❌ Erro na chamada à API: {e}")
        return {"estado": "desconhecido", "confianca": 0, "mensagem": str(e), "acao": "skip"}


# ===========================================================================
# Funções de alto nível
# ===========================================================================

def aguardar_estado_ia(
    estados_esperados: list[str],
    timeout: int = 120,
    intervalo: int = 3,
    pergunta: str = "Qual é o estado atual da tela?",
    contexto: str = "",
    descricao_adicional: str = "",
) -> dict:
    """
    Loop de análise: tira screenshots e consulta a IA até um estado esperado aparecer.

    Substitui: encontrar_imagem(CSV_BTN, timeout=120) + time.sleep()

    Args:
        estados_esperados: Ex: ["csv_disponivel", "sem_dados", "erro"]
        timeout:           Tempo máximo em segundos.
        intervalo:         Segundos entre cada chamada à IA.
        pergunta:          Prompt específico (vem do acoes.py).
        contexto:          Info extra para o log.

    Returns:
        O dict da última análise da IA.

    Raises:
        TimeoutError: Se nenhum estado esperado aparecer no tempo limite.
    """
    inicio = time.time()
    ultimo_log = 0
    tentativa = 0

    pergunta_completa = pergunta
    if descricao_adicional:
        pergunta_completa = f"{pergunta} Informação adicional para esse uso específico: {descricao_adicional}"

    pergunta_completa = f"{pergunta_completa} {contexto}".strip()
    logging.info(f"👁️  Aguardando: {estados_esperados} | timeout={timeout}s | intervalo={intervalo}s")

    while time.time() - inicio < timeout:
        tentativa += 1

        # Mantém tela viva no VNC
        try:
            pyautogui.moveRel(1, 0)
            pyautogui.moveRel(-1, 0)
        except Exception:
            pass

        analise = analisar_tela(pergunta_completa)
        estado_atual = analise.get("estado", "desconhecido")
        tempo_decorrido = int(time.time() - inicio)

        # Loga a cada ~15s ou quando encontra o estado esperado
        if tempo_decorrido - ultimo_log >= 15 or estado_atual in estados_esperados:
            tokens_sessao = _uso["input_tokens"] + _uso["output_tokens"]
            logging.info(
                f"   ⏱️  {tempo_decorrido}s | estado={estado_atual} "
                f"(conf {analise.get('confianca', '?')}/10) "
                f"| tokens: {tokens_sessao:,} "
                f"| {analise.get('mensagem', '')}"
            )
            ultimo_log = tempo_decorrido

        if estado_atual in estados_esperados:
            logging.info(f"✅ '{estado_atual}' encontrado após {tempo_decorrido}s ({tentativa} chamada(s))")
            return analise

        # Alerta inesperado durante a espera — tenta fechar automaticamente
        if estado_atual == ESTADOS["ALERTA"]:
            logging.warning("⚠️  Alerta inesperado durante espera — tentando fechar...")
            _fechar_popup_visual(analise)

        time.sleep(intervalo)

    nome = f"timeout_{int(time.time())}.png"
    pyautogui.screenshot(nome)
    logging.error(f"❌ Timeout {timeout}s. Screenshot salvo: {nome}")
    raise TimeoutError(f"Timeout: nenhum de {estados_esperados} em {timeout}s")


def clicar_elemento_ia(
    descricao: str,
    timeout: int = 30,
    screenshot_b64: str | None = None,
    descricao_adicional: str = "",
) -> bool:
    """
    Pede para a IA localizar um elemento por descrição e clica nele.

    Substitui: clicar_imagem(CSV_BTN)

    Args:
        descricao:      Descrição do elemento (vem do acoes.py).
        timeout:        Tempo máximo para encontrar o elemento.
        screenshot_b64: Screenshot já tirado (evita chamada dupla).

    Returns:
        True se clicou, False se não encontrou.
    """
    inicio = time.time()

    descricao_completa = descricao
    if descricao_adicional:
        descricao_completa = f"{descricao} Informação adicional para esse uso específico: {descricao_adicional}"

    pergunta = (
        f"Encontre este elemento na tela: '{descricao_completa}'. "
        f"Se visível, retorne as coordenadas exatas (x, y) do centro do elemento. "
        f"Se não estiver visível, retorne estado 'desconhecido'."
    )

    while time.time() - inicio < timeout:
        if screenshot_b64 is None:
            screenshot_b64 = tirar_screenshot()

        analise = analisar_tela(pergunta, screenshot_b64)
        coords = analise.get("coordenadas")

        if coords and analise.get("confianca", 0) >= 6:
            x_img, y_img = coords.get("x"), coords.get("y")
            if x_img and y_img:
                # VALIDA: coordenada fora dos limites da imagem = resposta ruim
                # do modelo (ex.: y=1263 numa imagem de 720px). Sem isto, o
                # ×escala manda o clique pra fora da tela e o download falha.
                if _img_w and _img_h and not (0 <= x_img <= _img_w and 0 <= y_img <= _img_h):
                    logging.warning(
                        f"⚠️ Coordenada da IA fora da imagem ({x_img},{y_img}) vs "
                        f"{_img_w}x{_img_h} — descartando e re-analisando"
                    )
                    screenshot_b64 = None
                    time.sleep(1)
                    continue

                # Converte coordenadas da imagem reduzida para a tela real
                x_real = int(x_img * _escala_x)
                y_real = int(y_img * _escala_y)
                logging.info(
                    f"🎯 Elemento em ({x_img},{y_img}) imagem "
                    f"→ ({x_real},{y_real}) tela real (escala {_escala_x:.2f}x) — clicando"
                )
                time.sleep(0.3)
                pyautogui.moveTo(x_real, y_real, duration=0.2)
                time.sleep(0.2)
                pyautogui.click()
                logging.info("✅ Clique realizado")
                return True

        logging.debug("🔍 Elemento ainda não visível, aguardando...")
        screenshot_b64 = None
        time.sleep(2)

    logging.error(f"❌ Elemento não encontrado em {timeout}s: '{descricao[:60]}'")
    return False


def focar_janela_promax(titulo_parcial: str = "PromaxWEB") -> bool:
    """
    Traz a janela do Promax para o foco usando pygetwindow.

    Chame isso:
      - Após fechar_popups_inicio() no main.py
      - No início de cada rotina, antes de abrir_rotinas()
      - Sempre que suspeitar que a janela perdeu o foco

    Args:
        titulo_parcial: Parte do título da janela do Promax.

    Returns:
        True se encontrou e focou, False se não encontrou.
    """
    try:
        import pygetwindow as gw
        janelas = [w for w in gw.getAllWindows() if titulo_parcial in w.title]
        if janelas:
            janela = janelas[0]
            janela.restore()   # garante que não está minimizada
            janela.activate()
            time.sleep(0.5)
            logging.info(f"🪟 Janela '{janela.title}' focada com sucesso")
            return True
        else:
            logging.warning(f"⚠️  Janela com '{titulo_parcial}' não encontrada")
            return False
    except Exception as e:
        logging.warning(f"⚠️  Erro ao focar janela: {e}")
        return False


def fechar_popups_inicio(driver, contexto: str, max_tentativas: int = 10) -> bool:
    """
    Detecta e fecha todos os popups que aparecem após o login no Promax.

    Lida com alerts JS (Selenium) e popups visuais (IA) de forma combinada.
    Continua tentando até a tela estar limpa ou atingir max_tentativas.

    Args:
        driver:          WebDriver do Selenium.
        contexto:        Descrição dos popups esperados (use CONTEXTO_POPUPS_INICIO do acoes.py).
        max_tentativas:  Número máximo de ciclos.

    Returns:
        True se a tela ficou limpa, False se ainda havia popups ao fim.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    logging.info("🤖🔍 Verificando popups de inicialização...")

    for tentativa in range(1, max_tentativas + 1):
        logging.info(f"🤖:   Ciclo {tentativa}/{max_tentativas}")

        # 1. Alert JS (rápido, sem custo de API)
        try:
            alert = WebDriverWait(driver, 2).until(EC.alert_is_present())
            texto = alert.text
            alert.accept()
            logging.info(f"🤖:   ✅ Alert JS fechado: '{texto}'")
            time.sleep(0.5)
            continue
        except TimeoutException:
            pass

        # 2. Analisa visualmente
        pergunta = (
            f"{contexto}\n\n"
            "Agora: a tela está limpa e pronta para uso (pronto), "
            "ou ainda há algum popup/dialog aberto (alerta)?" \
            "Lembrando que a parte onde aparece 'Gerenciador de Arquivos', 'Atalho' e 'Pesquisa' não é um pop-up, é a tela principal do Promax. O botão 'Ok' não precisa ser precionado"
        )
        analise = analisar_tela(pergunta)
        estado = analise.get("estado")

        logging.info(
            f"   Estado: {estado} (conf {analise.get('confianca', '?')}/10) "
            f"| {analise.get('mensagem', '')}"
        )

        if estado == ESTADOS["PRONTO"]:
            logging.info("🤖: ✅ Promax pronto — sem popups")
            return True

        if estado == ESTADOS["ALERTA"]:
            fechou = _fechar_popup_visual(analise)
            if not fechou:
                logging.warning("🤖:   ⚠️  Sem coordenadas — tentando Enter/Escape")
                pyautogui.press("enter")
                time.sleep(0.5)
                pyautogui.press("escape")
                time.sleep(0.5)
            time.sleep(1)
            continue

        time.sleep(1)

    logging.warning(f"🤖:   ⚠️  Ainda havia popups após {max_tentativas} ciclos")
    return False


def diagnosticar_e_decidir(driver=None, contexto_rotina: str = "") -> dict:
    """
    Analisa a tela após uma falha e sugere uma ação para o executor.
    """
    pergunta = (
        f"Ocorreu um erro na rotina '{contexto_rotina}' do Promax. "
        f"O que está na tela agora? "
        f"Devo tentar continuar, pular essa rotina, ou há outro problema?"
    )

    analise = analisar_tela(pergunta)

    if analise.get("estado") == ESTADOS["ALERTA"] and driver:
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            logging.info(f"🔔 Alert JS detectado: '{alert.text}' — aceitando")
            alert.accept()
            analise["acao"] = "continuar"
        except Exception:
            pass

    logging.info(
        f"🤖 Diagnóstico [{contexto_rotina}]: "
        f"estado={analise.get('estado')} | ação={analise.get('acao')} | "
        f"{analise.get('mensagem', '')}"
    )
    return analise


# ===========================================================================
# Helpers internos
# ===========================================================================

def _fechar_popup_visual(analise: dict) -> bool:
    """Clica no botão de fechar usando coordenadas da IA. Fallback: Enter."""
    coords = analise.get("coordenadas")
    if coords:
        x_img, y_img = coords.get("x"), coords.get("y")
        if x_img and y_img:
            x_real = int(x_img * _escala_x)
            y_real = int(y_img * _escala_y)
            logging.info(f"   🖱️  Clicando em ({x_img},{y_img}) → ({x_real},{y_real}) tela real")
            pyautogui.click(x_real, y_real)
            time.sleep(0.5)
            return True

    logging.info("   ⌨️  Pressionando Enter (sem coordenadas)")
    pyautogui.press("enter")
    time.sleep(0.5)
    return False


# ===========================================================================
# Inicialização
# ===========================================================================

logging.info("✓ Módulo ai_vision carregado | Modelo: %s | ~$%.1f/M input, $%.1f/M output", MODELO, _PRECO_INPUT_POR_MILHAO, _PRECO_OUTPUT_POR_MILHAO)