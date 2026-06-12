"""
Rotina: 01.25.02 - Preço Mínimo
Descrição: Relatório de Preço Mínimo
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

CODIGO_ROTINA = "012502"


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

    # ── 3. Gera o Excel ───────────────────────────────────────────────────────
    logging.info("📤 Executando GerarExcel() via JavaScript...")
    try:
        if not driver.execute_script("return typeof GerarExcel === 'function';"):
            logging.error("❌ Função GerarExcel não encontrada.")
            return "skip"
        driver.execute_script("GerarExcel();")
    except Exception as e:
        logging.error(f"❌ Erro ao executar GerarExcel(): {e}")
        return "skip"

    # ── 4. Aguarda a barra de download do Edge aparecer ───────────────────────
    logging.info("⏳ Aguardando barra de download...")
    try:
        aguardar_estado_ia(**{**AGUARDAR_DOWNLOAD_SALVAR, "timeout": 120}, contexto=f"Rotina {CODIGO_ROTINA}")
    except TimeoutError:
        logging.warning("⚠️ Timeout — tentando GerarExcel() novamente...")
        try:
            driver.execute_script("GerarExcel();")
            aguardar_estado_ia(**{**AGUARDAR_DOWNLOAD_SALVAR, "timeout": 180}, contexto=f"Rotina {CODIGO_ROTINA} (retry)")
        except TimeoutError:
            logging.error("❌ Barra de download não apareceu após retry.")
            return "skip"

    logging.info("⏳ Aguardando download...")
    # O executor.py chama salvar_arquivo() após o retorno desta função.
