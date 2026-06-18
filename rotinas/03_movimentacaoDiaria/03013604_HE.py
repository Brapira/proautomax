"""
Rotina: 03.01.36.04
Descrição: Baixa um CSV com relatório de pedidos do dia em hectolitro do Promax.
Autor: Carol
"""

import logging
import pyautogui
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import ESTADOS, aguardar_estado_ia, clicar_elemento_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV, CLICAR_CSV
from function.troca_janela import trocar_para_nova_janela

CODIGO_ROTINA = "03013604_HE"


def executar(driver, **kwargs):

    focar_janela_promax()
    abrir_rotinas(driver, '03013604')
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)

    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True

    logging.info("⚙️ Configurando parâmetros da rotina 03.01.36.04 em hectolitro...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    wait.until(EC.presence_of_element_located((By.NAME, "idQtdeHecto")))
    driver.execute_script("""
        var cbs = document.getElementsByName('idQtdeHecto');
        for (var i = 0; i < cbs.length; i++) {
            if (cbs[i].value === 'S' && !cbs[i].checked) { cbs[i].click(); break; }
        }
    """)
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Checkbox de hectolitro selecionada")

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
        analise = aguardar_estado_ia(
            estados_esperados=["csv_disponivel", "sem_dados", "erro"],
            timeout=300,
            intervalo=4,
            pergunta=AGUARDAR_CSV["pergunta"],
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando relatório de pedidos em hectolitro",
            descricao_adicional=(
                "O relatório foi disparado e pode aparecer um dialog de 'Processando...' "
                "durante a geração — isso é normal e NÃO é um erro, apenas aguarde."
            )
        )
    except TimeoutError:
        logging.error(f"❌ Timeout aguardando relatório na rotina {CODIGO_ROTINA}")
        return "skip"

    if analise.get("estado") in (ESTADOS["SEM_DADOS"], ESTADOS["ERRO"]):
        logging.warning(f"⏭️ {analise.get('mensagem')} — pulando")
        return "skip"

    logging.info("✅ Relatório gerado! Clicando no CSV...")
    if not clicar_elemento_ia(**CLICAR_CSV):
        logging.error("❌ Falha ao clicar no CSV")
        return "skip"

    logging.info("⏳ Aguardando download...")
