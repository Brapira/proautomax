"""
Rotina: 03.02.37 - Rel. Notas Fiscais Plus
Descrição: Relatório de notas fiscais de ENTRADA com quebra por Operação e código fiscal.
Autor: Carol e Isac
"""

import logging

from function.abrir_rotinas import abrir_rotinas
from function.aceitar_alertas import aceitar_alertas
from function.funcoes_rotina import aguardar_tela_carregar
from function.troca_janela import trocar_para_nova_janela
from function.img_func import CSV_BTN, aguardar_processamento, clicar_imagem
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pyautogui
from function.data_func import primeiro_dia_mes


# Código da rotina no Promax
CODIGO_ROTINA = "030237_ENTRADA"


def executar(driver, **kwargs):
    """
    Função principal da rotina.
    """

    abrir_rotinas(driver, "030237")
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)
    time.sleep(5)

    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    logging.info("⚙️ Configurando parâmetros da rotina 03.02.37 de entrada...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    # -------------------------
    # Quebra 1 = Operação (14)
    # -------------------------
    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "quebra1")))

    driver.execute_script(
        "arguments[0].value = '14'; arguments[0].onchange();", select_quebra1
    )

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 1 configurada para Operação (14)")

    # -------------------------
    # Quebra 2 = Código Fiscal (29)
    # -------------------------
    select_quebra2 = wait.until(EC.presence_of_element_located((By.NAME, "quebra2")))

    driver.execute_script(
        "arguments[0].value = '29'; arguments[0].onchange();", select_quebra2
    )

    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 2 configurada para Código Fiscal (29)"
    )

    # -------------------------
    # Itens = Sim
    # Notas = Entrada
    # -------------------------
    radio_itens = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='radio'][name='itens'][value='S']")
        )
    )

    if not radio_itens.is_selected():
        radio_itens.click()
        logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Itens configurados para Sim")

    radio_itens2 = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='radio'][name='notas'][value='NE']")
        )
    )

    if not radio_itens2.is_selected():
        radio_itens2.click()
        logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Notas de entrada configurado para Sim")

    checkbox = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "input[type='checkbox'][name='listaNotaCompra'][value='S']",
            )
        )
    )

    if not checkbox.is_selected():
        driver.execute_script("arguments[0].click();", checkbox)
        logging.info(
            f"ROTINA {CODIGO_ROTINA}:⚙️ Checkbox de Lista NFs de Compra flagada..."
        )

    # -------------------------
    # Data inicial = primeiro dia do mês atual
    # Data final = hoje
    # -------------------------

    data_inicial = wait.until(EC.presence_of_element_located((By.NAME, "dataInicial")))

    driver.execute_script(f"arguments[0].value = '{primeiro_dia_mes()}';", data_inicial)
    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Data inicial configurada para {primeiro_dia_mes()}"
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
