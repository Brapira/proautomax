"""
Rotina: 01.25.08.02 - Faixa de Preços
Descrição: Relatório de faixa de preços
Autor: Carol
"""

import logging
import time

from function.abrir_rotinas import abrir_rotinas
from function.funcoes_rotina import aguardar_tela_carregar
from function.troca_janela import trocar_para_nova_janela
from function.ai_vision import aguardar_estado_ia, focar_janela_promax
from function.acoes import AGUARDAR_DOWNLOAD_SALVAR
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyautogui

# Código da rotina no Promax
CODIGO_ROTINA = "01250802"

def executar(driver, **kwargs):
    """
    Função principal da rotina.
    """
    abrir_rotinas(driver, CODIGO_ROTINA)
    trocar_para_nova_janela(driver)
    focar_janela_promax()
    driver.maximize_window()
    
    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)
    time.sleep(5)
    
    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True
    
    logging.info("⚙️ Configurando parâmetros da rotina 01.25.08.02...")
    
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
 
    time.sleep(2)
    
    # Testando clicar no botão visualizar com JavaScript
    logging.info("📤 Executando GeraPlanilha(); via JavaScript...")

    try:
        funcao_existe = driver.execute_script("return typeof GeraPlanilha === 'function';")
        if not funcao_existe:
            logging.error("❌ Função GeraPlanilha não encontrada na página.")
            return "skip"            

        driver.execute_script("return GeraPlanilha();")

    except Exception as e:
        logging.error(f"❌ Erro ao executar GeraPlanilha(): {e}")
        return "skip"

    logging.info("⏳ Aguardando barra de download aparecer...")
    try:
        analise = aguardar_estado_ia(
            **AGUARDAR_DOWNLOAD_SALVAR,
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando download de faixa de preços",
        )
    except TimeoutError:
        logging.error(f"❌ Timeout aguardando barra de download na rotina {CODIGO_ROTINA}")
        return "skip"

    if analise.get("estado") != "download_salvar":
        logging.error(f"❌ Barra de download não apareceu: {analise.get('estado')}")
        return "skip"

    logging.info("✅ Barra de download detectada — executor.py vai salvar o arquivo")