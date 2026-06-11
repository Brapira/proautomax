"""
Rotina: 03.08.05 - Conferência de Frete
Descrição: Relatório de conferência de frete por transportadora.
Autor: Isac
"""

# ─── Imports obrigatórios ────────────────────────────────────────────────────
import logging
import pyautogui
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from function.abrir_rotinas import abrir_rotinas
from function.troca_janela import trocar_para_nova_janela
from function.funcoes_rotina import aguardar_tela_carregar
from datetime import date, timedelta

from function.ai_vision import focar_janela_promax
from function.data_func import data_ontem

CODIGO_ROTINA = "030805"


def executar(driver, **kwargs):
    # ── 1. Abre a rotina no Promax ────────────────────────────────────────────
    focar_janela_promax()
    abrir_rotinas(driver, CODIGO_ROTINA)
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)

    # Move o mouse pro centro para não bloquear elementos (pyautogui failsafe)
    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    # ── 2. Entra no frame da rotina ───────────────────────────────────────────
    logging.info(f"⚙️ Configurando parâmetros da rotina {CODIGO_ROTINA}...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    session_id = driver.execute_script(
        "return document.all.SessionID ? document.all.SessionID.value : '';"
    )
    logging.info(f"🔑 SessionID capturado: {session_id[:8]}...")

    # ── 3. Configura os parâmetros da tela ────────────────────────────────────
    wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))
    driver.execute_script("document.all.opcaoRel.value = '1';")
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Classificação configurada para Conferencia")

    wait.until(EC.presence_of_element_located((By.NAME, "dataInicial")))
    driver.execute_script(f"document.all.dataInicial.value = '{data_ontem()}'; document.all.dataFinal.value = '{data_ontem()}';")
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Datas configuradas para {data_ontem()}")

    # ── 4. Dispara o Visualizar ───────────────────────────────────────────────
    logging.info(f"📤 Executando Visualizar via JavaScript...")
    try:
        funcao_existe = driver.execute_script("return typeof Visualizar === 'function';")
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")
            return "skip"
        driver.execute_script("return Visualizar();")
    except Exception as e:
        logging.error(f"❌ Erro ao executar Visualizar(): {e}")
        return "skip"

    # ── 5. Aguarda popup de confirmação e baixa do Gerenciador ──────────────
    logging.info("⏳ Aguardando popup de confirmação...")
    try:
        WebDriverWait(driver, 300).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        logging.info(f"✅ '{alert.text}' — aceitando...")
        alert.accept()
    except Exception as e:
        logging.error(f"❌ Timeout aguardando confirmação do relatório: {e}")
        return "skip"

    driver.get(f"http://brapira.promaxcloud.com.br:8080/?sessionId={session_id}")
    logging.info("🔐 Autenticado no Gerenciador de Arquivos")

    dia = (date.today() - timedelta(days=1)).day
    url = f"http://brapira.promaxcloud.com.br:8080/arquivos/download/file/dvs/2artd{dia:02d}_0001.txt"
    logging.info("📥 Baixando arquivo do Gerenciador...")
    driver.get(url)
    logging.info("⏳ Aguardando download...")
    # O executor.py chama salvar_arquivo() após o retorno desta função.
