"""
Rotina: 03.11.20 - Planilha de Acompanhamento
Descrição: Breve descrição do que este relatório faz.
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
from function.ai_vision import ESTADOS, aguardar_estado_ia, clicar_elemento_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV, CLICAR_CSV

from function.data_func import primeiro_dia_mes

CODIGO_ROTINA = "031120"


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

    # ── 3. Configura os parâmetros da tela ────────────────────────────────────
    select_classificacao = wait.until(EC.presence_of_element_located((By.NAME, "opcaoRel")))
    driver.execute_script("arguments[0].value = '1'; if(arguments[0].onchange) arguments[0].onchange();", select_classificacao)
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Classificação configurada para Mapa")

    data_inicial = wait.until(EC.presence_of_element_located((By.NAME, "dataInicial")))
    driver.execute_script(f"arguments[0].value = '{primeiro_dia_mes()}';", data_inicial)
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Data inicial configurada para {primeiro_dia_mes()}")

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

    logging.info("⏳ Aguardando processamento do relatório...")
    try:
        analise = aguardar_estado_ia(
            estados_esperados=["csv_disponivel", "sem_dados", "erro"],
            timeout=300,
            intervalo=4,
            pergunta=AGUARDAR_CSV["pergunta"],
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando relatório de remuneração de transportadora",
        )
    except TimeoutError:
        logging.error(f"❌ Timeout aguardando relatório na rotina {CODIGO_ROTINA}")
        return "skip"

    if analise.get("estado") in (ESTADOS["SEM_DADOS"], ESTADOS["ERRO"]):
        logging.warning(f"⏭️ {analise.get('mensagem')} — pulando")
        return "skip"

    # ── 6. Clica no botão CSV ─────────────────────────────────────────────────
    logging.info("✅ Relatório gerado! Clicando no CSV...")
    if not clicar_elemento_ia(**CLICAR_CSV):
        logging.error("❌ Falha ao clicar no CSV")
        return "skip"

    logging.info("⏳ Aguardando download...")
    # O executor.py chama salvar_arquivo() após o retorno desta função.
