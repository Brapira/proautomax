"""
Rotina: 03.01.11
Descrição: Baixa um CSV com relatório de resumo de pedidos.
Autor: Carol
"""

import logging
import pyautogui
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import ESTADOS, aguardar_estado_ia, clicar_elemento_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV, CLICAR_CSV
from function.troca_janela import trocar_para_nova_janela

CODIGO_ROTINA = "030111"


def executar(driver, **kwargs):

    focar_janela_promax()
    abrir_rotinas(driver, CODIGO_ROTINA)
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)

    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    logging.info("⚙️ Configurando parâmetros da rotina 03.01.11...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))
    driver.execute_script("arguments[0].value = '9'; if(arguments[0].onchange) arguments[0].onchange();", select_quebra1)
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Quebra 1 configurada para Operação (9)")

    logging.info("📤 Executando Visualizar via JavaScript...")
    try:
        funcao_existe = driver.execute_script("return typeof Visualizar === 'function';")
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")
            return "skip"
        driver.execute_script("return Visualizar();")
    except Exception as e:
        logging.error(f"❌ Erro ao executar Visualizar(): {e}")
        return "skip"

    try:
        analise = aguardar_estado_ia(
            **{**AGUARDAR_CSV, "timeout": 600, "intervalo": 8},
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando relatório de resumo de pedidos (até 10 min)",
        )
    except TimeoutError:
        logging.error(f"❌ Timeout aguardando relatório na rotina {CODIGO_ROTINA}")
        return "skip"

    if analise.get("estado") in (ESTADOS["SEM_DADOS"], ESTADOS["ERRO"]):
        logging.warning(f"⏭️ {analise.get('mensagem')} — pulando")
        return "skip"

    logging.info("✅ Relatório gerado! Clicando no CSV...")
    if not clicar_elemento_ia(**CLICAR_CSV):
        logging.error("❌ Falha ao clicar no CSV")
        return "skip"

    logging.info("⏳ Aguardando download...")
