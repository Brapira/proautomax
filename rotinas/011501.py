"""
Rotina: 01.15.01 - Preço Cheio
Descrição: Relatório de Preço Cheio
Autor: Carol
"""

import logging
import pyautogui
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from function.abrir_rotinas import abrir_rotinas
from function.troca_janela import trocar_para_nova_janela
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import focar_janela_promax, aguardar_estado_ia
from function.acoes import AGUARDAR_DOWNLOAD_SALVAR

CODIGO_ROTINA = "011501"


def executar(driver, **kwargs):
    # ── 1. Abre a rotina no Promax ────────────────────────────────────────────
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

    # ── 2. Entra no frame da rotina ───────────────────────────────────────────
    logging.info(f"⚙️ Configurando parâmetros da rotina {CODIGO_ROTINA}...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    # ── 3. Configura os parâmetros ────────────────────────────────────────────
    wait.until(EC.presence_of_element_located((By.NAME, "numerotabela")))
    driver.execute_script("document.all.numerotabela.value = '1';")
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Número da tabela configurado para 1")

    # ── 4. Carrega a tabela e gera o CSV ─────────────────────────────────────
    logging.info("📤 Executando CarregarTabela(1) via JavaScript...")
    try:
        if not driver.execute_script("return typeof CarregarTabela === 'function';"):
            logging.error("❌ Função CarregarTabela não encontrada.")
            return "skip"
        driver.execute_script("CarregarTabela(1);")
    except Exception as e:
        logging.error(f"❌ Erro ao executar CarregarTabela(): {e}")
        return "skip"

    logging.info("📤 Executando GerarCsv() via JavaScript...")
    try:
        if not driver.execute_script("return typeof GerarCsv === 'function';"):
            logging.error("❌ Função GerarCsv não encontrada.")
            return "skip"
        driver.execute_script("GerarCsv();")
    except Exception as e:
        logging.error(f"❌ Erro ao executar GerarCsv(): {e}")
        return "skip"

    # ── 5. Aguarda a barra de download do Edge aparecer ───────────────────────
    logging.info("⏳ Aguardando barra de download...")
    try:
        aguardar_estado_ia(**{**AGUARDAR_DOWNLOAD_SALVAR, "timeout": 120}, contexto=f"Rotina {CODIGO_ROTINA}")
    except TimeoutError:
        logging.warning("⚠️ Timeout — tentando GerarCsv() novamente...")
        try:
            driver.execute_script("GerarCsv();")
            aguardar_estado_ia(**{**AGUARDAR_DOWNLOAD_SALVAR, "timeout": 180}, contexto=f"Rotina {CODIGO_ROTINA} (retry)")
        except TimeoutError:
            logging.error("❌ Barra de download não apareceu após retry.")
            return "skip"

    logging.info("⏳ Aguardando download...")
    # O executor.py chama salvar_arquivo() após o retorno desta função.
