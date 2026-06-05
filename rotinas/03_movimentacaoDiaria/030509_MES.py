"""
Rotina: 03.05.09 - Preço Médio
Descrição: Baixa um CSV com o relatório de de preço médio em hectolitro por meses.
Autor: Carol
"""

import logging

from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.aceitar_alertas import aceitar_alertas
from function.funcoes_rotina import aguardar_tela_carregar
from function.img_func import CSV_BTN, aguardar_processamento, clicar_imagem
from function.troca_janela import trocar_para_nova_janela
import time
import pyautogui

# Código da rotina no Promax
CODIGO_ROTINA = "030509_MES"


def executar(driver, **kwargs):
    """
    Função principal da rotina.
    Tudo começa por aqui.
    """
    abrir_rotinas(driver, "030509")
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)
    time.sleep(5)

    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    logging.info(
        "⚙️ Configurando parâmetros da rotina 03.05.09 em hectolitro do mês ..."
    )

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))

    driver.execute_script(
        "arguments[0].value = '07'; arguments[0].onchange();", select_quebra1
    )

    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 1 configurada para classificação Cliente"
    )

    radio_itens = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='radio'][name='fatorConversao'][value='H']")
        )
    )

    if not radio_itens.is_selected():
        radio_itens.click()

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Itens configurados para Sim")

    time.sleep(2)

    # Testando clicar no botão visualizar com JavaScript
    logging.info("📤 Executando Visualizar via JavaScript...")

    try:
        funcao_existe = driver.execute_script(
            "return typeof Visualizar === 'function';"
        )
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")
            return "skip"

        driver.execute_script("return Visualizar();")

        time.sleep(2)

        if aceitar_alertas(driver):
            return "skip"

        aguardar_processamento()

    except Exception as e:
        logging.error(f"❌ Erro ao executar Visualizar(): {e}")
        return "skip"

    logging.info("⏳ Relatório gerado! Iniciando download...")
    time.sleep(2)
    clicar_imagem(CSV_BTN)
    logging.info("⏳ Aguardando download...")
