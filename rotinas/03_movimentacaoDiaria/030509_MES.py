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
from function.img_func import encontrar_imagem, clicar_imagem, CSV_BTN
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
    

    logging.info("⚙️ Configurando parâmetros da rotina 03.05.09 em hectolitro do mês ...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))

    driver.execute_script("arguments[0].value = '07'; arguments[0].onchange();", select_quebra1)

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 1 configurada para classificação Cliente")

    radio_itens = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='radio'][name='fatorConversao'][value='H']")))

    if not radio_itens.is_selected():

      radio_itens.click()

    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Itens configurados para Sim")
    
    time.sleep(2)
    
    logging.info("📤 Executando Visualizar via JavaScript...")

    try:
        funcao_existe = driver.execute_script("return typeof Visualizar === 'function';")
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")
            return "skip"            

        driver.execute_script("return Visualizar();")
        logging.info("⏳ Aguardando sair do 'Processando...'")

        try:
            WebDriverWait(driver, 600).until(
                EC.invisibility_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Processando')]")
                )
            )
        except TimeoutError:
            logging.warning("⚠️ 'Processando...' não sumiu (pode não existir ou mudou texto)")

        time.sleep(2)

    except Exception as e:
        logging.error(f"❌ Erro ao executar Visualizar(): {e}")
        return  "skip"      

    try:
        logging.info("⏳ Aguardando processamento do relatório (até 2 min)...")
        
        # Verifica se há algum alerta if alerta True ? skip : continue 
        if aceitar_alertas(driver):
            return "skip"
        encontrar_imagem(CSV_BTN, timeout=120)

    except TimeoutError:
        logging.warning("⚠️ Relatório demorou demais. Tentando novamente...")

        try:
            driver.execute_script("return Visualizar();")
            encontrar_imagem(CSV_BTN, timeout=180)
        except TimeoutError:
            logging.error("❌ Falha crítica: relatório não foi gerado.")
            return "skip"

    # logging.info("📤 Tentando usar o atalho Alt+V para visualizar...")
    # atalho_alt("v")
    # time.sleep(5)

    # # Verifica se o botão do CSV aparece (sucesso do Alt+V)
    # # Se não aparecer em 300s (5 min), assume falha e tenta clicar no visualizar manualmente
    # try:
    #     # Tenta encontrar o botão CSV que indica que o relatório carregou
    #     logging.info("⏳ Aguardando processamento do relatório (Até 2 min)...")
    #     encontrar_imagem(CSV_BTN, timeout=120) 
    # except TimeoutError:
    #     logging.warning("❌ Atalho Alt+V falhou ou demorou demais. Tentando clicar em Visualizar manualmente...")
    #     clicar_imagem(VISUALIZAR_BTN, timeout=10) # Tenta clicar no botão visualizar
        
    #     # Espera novamente pelo resultado
    #     logging.info("⏳ Aguardando processamento (2ª tentativa)...")
    #     try:
    #         encontrar_imagem(CSV_BTN, timeout=300)
    #     except TimeoutError:
    #         logging.error("❌ Falha crítica: Relatório não carregou.")
    #         return

    logging.info("⏳ Relatório gerado! Iniciando download...")

    # Clica no CSV para baixar
    time.sleep(2)
    clicar_imagem(CSV_BTN)    
    logging.info("⏳ Aguardando download...")