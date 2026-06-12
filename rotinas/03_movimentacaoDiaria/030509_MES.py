"""
Rotina: 03.05.09 - Preço Médio
Descrição: Baixa um CSV com o relatório de preço médio em hectolitro por meses.
Autor: Carol
"""

# ─── Imports obrigatórios ────────────────────────────────────────────────────
import logging
import pyautogui
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from function.abrir_rotinas import abrir_rotinas
from function.troca_janela import trocar_para_nova_janela
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import ESTADOS, aguardar_estado_ia, clicar_elemento_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV, CLICAR_CSV

# ─── Imports opcionais (remover os que não usar) ─────────────────────────────
# from function.data_func import data_ontem, primeiro_dia_mes, ano_vigente, gerar_nome_mes_vigente

# ─── Identificação ───────────────────────────────────────────────────────────
# Se esta rotina tiver variantes via params (ex: _SEMDATA), use CODIGOS_ROTINA.
# Caso contrário, mantenha só CODIGO_ROTINA.
CODIGO_ROTINA = "030509_MES"


def executar(driver, **kwargs):
    # ── 1. Abre a rotina no Promax ────────────────────────────────────────────
    focar_janela_promax()
    abrir_rotinas(driver, "030509")
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)

    # Move o mouse pro centro para não bloquear elementos (pyautogui failsafe)
    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    # ── 2. Entra no frame da rotina ───────────────────────────────────────────
    logging.info(f"⚙️ Configurando parâmetros da rotina {CODIGO_ROTINA}...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    # ── 3. Configura os parâmetros da tela ────────────────────────────────────
    wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))
    driver.execute_script("document.all.opcaoRel.value = '07'; document.all.opcaoRel.onchange();")
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Quebra 1 configurada para classificação Cliente")

    driver.execute_script(
        "var radios = document.getElementsByName('fatorConversao');"
        "for (var i = 0; i < radios.length; i++) {"
        "  if (radios[i].value === 'H') { radios[i].click(); break; }"
        "}"
    )
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Fator de conversão configurado para Hectolitro")

    # ── 4. Dispara o Visualizar ───────────────────────────────────────────────
    logging.info(f"📤 Executando Visualizar via JavaScript...")
    try:
        funcao_existe = driver.execute_script("return typeof Visualizar === 'function';")
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")
            return "skip"
        driver.execute_script("return Visualizar();")
    except Exception as e:
        logging.error(f"❌ Erro ao executar Visualizar(): {e}")
        return "skip"

    # ── 5. Aguarda a IA confirmar que o CSV está disponível ───────────────────
    logging.info("⏳ Aguardando processamento do relatório...")
    try:
        analise = aguardar_estado_ia(**AGUARDAR_CSV, contexto=f"Rotina {CODIGO_ROTINA}")
    except TimeoutError:
        logging.error(f"❌ Timeout aguardando relatório na rotina {CODIGO_ROTINA}")
        return "skip"

    if analise.get("estado") in (ESTADOS["SEM_DADOS"], ESTADOS["ERRO"]):
        logging.warning(f"⏭️ {analise.get('mensagem')} — pulando")
        return "skip"

    # ── 6. Clica no botão CSV ─────────────────────────────────────────────────
    logging.info("✅ Relatório gerado! Clicando no CSV...")
    if not clicar_elemento_ia(**CLICAR_CSV):
        logging.error("❌ Falha ao clicar no CSV")
        return "skip"

    logging.info("⏳ Aguardando download...")
    # O executor.py chama salvar_arquivo() após o retorno desta função.
