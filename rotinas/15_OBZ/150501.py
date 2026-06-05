"""
Rotina: 15.05.01 - Lançamentos detalhados OBZ
Descrição: Relatório de lançamentos do OBZ
Autor: Carol
"""

import logging

from function.abrir_rotinas import abrir_rotinas
from function.aceitar_alertas import aceitar_alertas
from function.funcoes_rotina import aguardar_tela_carregar
from function.troca_janela import trocar_para_nova_janela
from function.img_func import CSV_BTN, aguardar_processamento, clicar_imagem
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pyautogui
from function.data_func import ano_vigente

# Código da rotina no Promax
CODIGO_ROTINA = "150501"


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

    logging.info("⚙️ Configurando parâmetros da rotina 15.05.01...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    # -------------------------
    # Quebra 1 = Período (A)
    # -------------------------
    select_quebra1 = wait.until(EC.presence_of_element_located((By.NAME, "idPeriodo")))

    driver.execute_script(
        "arguments[0].value = 'A'; arguments[0].onchange();", select_quebra1
    )

    logging.info(
        f"ROTINA {CODIGO_ROTINA}:⚙️ Quebra 1 configurada para Período Anual (A)"
    )

    # -------------------------
    # Data = Ano vigente
    # -------------------------

    data_inicial = wait.until(EC.presence_of_element_located((By.NAME, "dtAno")))

    driver.execute_script(f"arguments[0].value = '{ano_vigente()}';", data_inicial)
    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Ano configurado para {ano_vigente()}")

    # Seleciona a opção "99 - TODOS"
    select_nbz = Select(wait.until(EC.presence_of_element_located((By.NAME, "cdNbz"))))
    select_nbz.select_by_value("99")
    driver.execute_script("AdicionaNbz();")
    lista = driver.find_element(By.NAME, "cdNbzLista")

    if lista.find_elements(By.TAG_NAME, "option"):
        logging.info("NBZ adicionada com sucesso")

    time.sleep(1)

    # Seleciona a opção "9999 -  Todos" porque é diferente do de cima? não me pergunte
    select_nbz = Select(
        wait.until(EC.presence_of_element_located((By.NAME, "cdDepto")))
    )
    select_nbz.select_by_value("9999")
    driver.execute_script("AdicionaDepto();")
    lista = driver.find_element(By.NAME, "cdDeptoLista")

    if lista.find_elements(By.TAG_NAME, "option"):
        logging.info("Depto adicionada com sucesso")

    time.sleep(1)

    # Seleciona opção "9999 - Todos" de pacote, e sim... muda novamente o código, virou um botão...
    select_pacote = Select(
        wait.until(EC.presence_of_element_located((By.NAME, "cdPacote")))
    )
    select_pacote.select_by_value("9999")
    driver.execute_script("AdicionaPacote();")

    lista = driver.find_element(By.NAME, "cdPacoteLista")
    if lista.find_elements(By.TAG_NAME, "option"):
        logging.info("Pacote adicionado com sucesso")
    else:
        logging.warning("Pacote não foi adicionado")

    time.sleep(1)

    # Seleciona opção "9999 - Todos" de VBZ
    select_vbz = Select(wait.until(EC.presence_of_element_located((By.NAME, "cdVbz"))))
    select_vbz.select_by_value("9999")
    driver.execute_script("AdicionaVbz();")

    lista = driver.find_element(By.NAME, "cdVbzLista")
    if lista.find_elements(By.TAG_NAME, "option"):
        logging.info("VBZ adicionada com sucesso")
    else:
        logging.warning("VBZ não foi adicionada")

    time.sleep(1)

    # Seleciona opção "9999999999 - Todos" de Conta
    select_vbz = Select(
        wait.until(EC.presence_of_element_located((By.NAME, "cdConta")))
    )
    select_vbz.select_by_value("9999999999")
    driver.execute_script("AdicionaConta();")

    lista = driver.find_element(By.NAME, "cdContaLista")
    if lista.find_elements(By.TAG_NAME, "option"):
        logging.info("Conta adicionada com sucesso")
    else:
        logging.warning("Conta não foi adicionada")

    time.sleep(1)

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
