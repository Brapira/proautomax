"""
Rotina: 01.15.01 - Preço Cheio
Descrição: Relatório de Preço Cheio
Autor: Carol
"""

import logging

from function.abrir_rotinas import abrir_rotinas
from function.funcoes_rotina import aguardar_tela_carregar
from function.troca_janela import trocar_para_nova_janela
from function.img_func import SALVAR_BTN, encontrar_imagem
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pyautogui

# Código da rotina no Promax
CODIGO_ROTINA = "011501"


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

    logging.info("⚙️ Configurando parâmetros da rotina 01.15.01...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    numero_tabela = wait.until(
        EC.presence_of_element_located((By.NAME, "numerotabela"))
    )
    driver.execute_script(f"arguments[0].value = '{1}';", numero_tabela)
    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Número da tabela configurado para {1}")

    time.sleep(1)

    logging.info("📤 Executando CarregarTabela(); via JavaScript...")
    
    # No código dela a função tem que levar "1" como parametro
    try:
        funcao_existe = driver.execute_script(
            "return typeof CarregarTabela === 'function';"
        )
        if not funcao_existe:
            logging.error("❌ Função CarregarTabela não encontrada na página.")
            return "skip"

        driver.execute_script("return CarregarTabela(1);")

    except Exception as e:
        logging.error(f"❌ Erro ao executar CarregarTabela(): {e}")
        return "skip"

    time.sleep(1)

    # Testando clicar no botão visualizar com JavaScript
    logging.info("📤 Executando GerarCsv(); via JavaScript...")

    try:
        funcao_existe = driver.execute_script("return typeof GerarCsv === 'function';")
        if not funcao_existe:
            logging.error("❌ Função GerarCsv não encontrada na página.")
            return "skip"

        driver.execute_script("return GerarCsv();")

    except Exception as e:
        logging.error(f"❌ Erro ao executar GerarCsv(): {e}")
        return "skip"

    try:
        logging.info("⏳ Aguardando processamento do relatório (até 2 min)...")
        encontrar_imagem(SALVAR_BTN, timeout=120)

    except TimeoutError:
        logging.warning("⚠️ Relatório demorou demais. Tentando novamente...")

        try:
            driver.execute_script("return GerarCsv();")
            encontrar_imagem(SALVAR_BTN, timeout=180)
        except TimeoutError:
            logging.error("❌ Falha crítica: relatório não foi gerado.")
            return "skip"

    logging.info("⏳ Relatório gerado! Iniciando download...")

    logging.info("⏳ Aguardando download...")
    time.sleep(5)
