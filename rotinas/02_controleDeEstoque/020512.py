"""
Rotina: 02.05.12
Descrição: Baixa um CSV com relatório de compras por fornecedor.
Autor: Carol
"""

import logging
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.aceitar_alertas import aceitar_alertas
from function.data_func import primeiro_dia_ano
from function.img_func import CSV_BTN, aguardar_processamento, clicar_imagem
from function.troca_janela import trocar_para_nova_janela
from function.funcoes_rotina import aguardar_tela_carregar, desmarcar_item, marcar_item
import time
import pyautogui

# Código da rotina no Promax
CODIGO_ROTINA = "020512"


def executar(driver, **kwargs):
    """
    Função principal da rotina.    
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
    

    logging.info("⚙️ Configurando parâmetros da rotina 02.05.12 ...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    desmarcar_item("checkbox", wait, driver, "vasilhame", "S", "Vasilhame", CODIGO_ROTINA)
    desmarcar_item("checkbox", wait, driver, "garrafeira", "S", "Garrafeira", CODIGO_ROTINA)
    desmarcar_item("checkbox", wait, driver, "material", "S", "Material", CODIGO_ROTINA)

    marcar_item("radio", wait, driver,"idValor","S","SKU",CODIGO_ROTINA)

    data = wait.until(EC.presence_of_element_located((By.NAME, "periodoInicial")))

    driver.execute_script(f"arguments[0].value = '{primeiro_dia_ano()}';", data)

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Data inicial configurada para {primeiro_dia_ano()}")

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