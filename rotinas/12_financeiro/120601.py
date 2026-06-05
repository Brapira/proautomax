"""
Rotina: 12.06.01 - Títulos Pendentes
Descrição: Baixa um CSV com os títulos em atraso do Promax.
Autor: Carol e Isac
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
from function.data_func import data_ontem

# Código da rotina no Promax
CODIGO_ROTINA = "120601"


def executar(driver, **kwargs):
    """
    Função principal da rotina.
    Tudo começa por aqui.
    """
    abrir_rotinas(driver, CODIGO_ROTINA)
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)
    time.sleep(5)

    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    logging.info("⚙️ Configurando parâmetros da rotina 12.06.01...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))

    driver.execute_script(
        "arguments[0].value = '01'; arguments[0].onchange();", select_quebra1
    )

    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 1 configurada para classificação numérica"
    )
    time.sleep(0.5)

    vencimento_final = wait.until(
        EC.presence_of_element_located((By.NAME, "fimVencimento"))
    )

    driver.execute_script(f"arguments[0].value = '{data_ontem()}';", vencimento_final)
    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Data inicial configurada para {data_ontem()}"
    )

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
