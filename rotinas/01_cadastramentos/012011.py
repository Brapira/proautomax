"""
Rotina: 01.20.11
Descrição: Baixa um CSV com relatório de Visitas do vendedor
Autor: Carol
"""

import logging
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.funcoes_rotina import aguardar_tela_carregar
from function.img_func import clicar_imagem, encontrar_imagem, CSV_BTN
from function.troca_janela import trocar_para_nova_janela
import time
import pyautogui


# Código da rotina no Promax
CODIGO_ROTINA = "012011"


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
    

    logging.info("⚙️ Configurando parâmetros da rotina 01.20.11...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    # Não me pergunte o porque, é o promax...
    driver.execute_script("""
        var sel = document.getElementsByName('grPerfilVenda')[0];
        if (sel) {
            sel.value = '05';
            sel.fireEvent('onchange');
        }
    """)

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Grupo perfil de vendas configurado para 05 - Segmentada")

    driver.execute_script("""
        var cb = document.getElementsByName('todos')[0];
        if (cb && !cb.checked) {
            cb.checked = true;
            cb.fireEvent('onclick');
        }
    """)

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Checkbox de situação Todos marcada...")

    time.sleep(2)

    # Testando clicar no botão visualizar com JavaScript
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
        logging.info("⏳ Aguardando processamento do relatório (até 2 min)...")
        encontrar_imagem(CSV_BTN, timeout=120)

    except TimeoutError:
        logging.warning("⚠️ Relatório demorou demais. Tentando novamente...")

        try:
            driver.execute_script("return Visualizar();")
            encontrar_imagem(CSV_BTN, timeout=180)
        except TimeoutError:
            logging.error("❌ Falha crítica: relatório não foi gerado.")
            return "skip"

    logging.info("⏳ Relatório gerado! Iniciando download...")
    time.sleep(2)
    clicar_imagem(CSV_BTN)
    logging.info("⏳ Aguardando download...")