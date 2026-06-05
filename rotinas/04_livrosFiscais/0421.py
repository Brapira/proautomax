"""
Rotina: 04.21
Descrição: Baixa um CSV com relatório de registro de inventário.
Autor: Carol
"""

import logging
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.aceitar_alertas import aceitar_alertas
from function.funcoes_rotina import aguardar_tela_carregar
from function.img_func import SALVAR_BTN_2, aguardar_processamento, clicar_imagem
from function.troca_janela import trocar_para_nova_janela
import time
import pyautogui

# Código da rotina no Promax
CODIGO_ROTINA = "0421"


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

    logging.info("⚙️ Configurando parâmetros da rotina 04.21...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))
    logging.info(f"Janelas abertas: {driver.window_handles}")
    logging.info(f"Janela atual: {driver.current_window_handle}")

    combo = driver.find_element("name", "opcaoCusto")

    driver.execute_script(
        """
        var select = arguments[0];
        select.value = "3";
        if (select.onchange) {
            select.onchange();
        }
    """,
        combo,
    )
    logging.info("⚙️ Selecionando opção de preço médio de reposição...")
    time.sleep(0.5)

    checkbox_vasilhame = driver.find_element("name", "checkVasilhame")

    driver.execute_script(
        """
        var cb = arguments[0];
        cb.checked = false;
        if (cb.onclick) cb.onclick();
        if (cb.onchange) cb.onchange();
    """,
        checkbox_vasilhame,
    )
    logging.info("⚙️ Revomendo flag de Vasilhame...")
    time.sleep(0.5)

    checkbox_garrafeira = driver.find_element("name", "checkGarrafeira")

    driver.execute_script(
        """
        var cb = arguments[0];
        cb.checked = false;
        if (cb.onclick) cb.onclick();
        if (cb.onchange) cb.onchange();
    """,
        checkbox_garrafeira,
    )
    logging.info("⚙️ Revomendo flag de Garrafeira...")
    time.sleep(0.5)

    checkbox_material = driver.find_element("name", "checkMaterial")

    driver.execute_script(
        """
        var cb = arguments[0];
        cb.checked = false;
        if (cb.onclick) cb.onclick();
        if (cb.onchange) cb.onchange();
    """,
        checkbox_material,
    )
    logging.info("⚙️ Revomendo flag de Material...")
    time.sleep(0.5)

    driver.execute_script("""
        document.getElementsByName('cdDeposito')[0].value = '01';
        AdicionaDeposito();
    """)
    logging.info("⚙️ Selecionando Depósito opção 01 Central...")

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
    clicar_imagem(SALVAR_BTN_2)
    logging.info("⏳ Aguardando download...")
