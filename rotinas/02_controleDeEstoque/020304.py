"""
Rotina: 02.03.04
Descrição: Baixa um CSV com relatório de saldo da grade.
Autor: Carol
"""

import logging
import os
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.data_func import data_ontem
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import ESTADOS, clicar_elemento_ia, aguardar_estado_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV, CLICAR_BOTAO_VISUALIZAR, CLICAR_CSV
from function.troca_janela import trocar_para_nova_janela
import pyautogui


# Código da rotina no Promax
CODIGO_ROTINA = "020304"


def executar(driver, **kwargs):
    """
    Função principal da rotina.    
    """

    abrir_rotinas(driver, CODIGO_ROTINA)
    focar_janela_promax()
    trocar_para_nova_janela(driver)
    driver.maximize_window()

    wait = WebDriverWait(driver, 60)
    aguardar_tela_carregar(wait)
    width, height = pyautogui.size()
    pyautogui.FAILSAFE = False
    pyautogui.moveTo(width / 2, height / 2)
    pyautogui.FAILSAFE = True
    

    logging.info("⚙️ Configurando parâmetros da rotina 02.03.04 ...")

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    data = wait.until(EC.presence_of_element_located((By.NAME, "data")))

    driver.execute_script(f"arguments[0].value = '{data_ontem()}';", data)
    logging.info(f"ROTINA {CODIGO_ROTINA}:⚙️ Data inicial configurada para {data_ontem()}")
    

    # Testando clicar no botão visualizar com JavaScript
    logging.info("📤 Executando Visualizar via JavaScript...")

    try:
        funcao_existe = driver.execute_script("return typeof Visualizar === 'function';")
        if not funcao_existe:
            logging.error("❌ Função Visualizar() não encontrada na página.")

        driver.execute_script("return Visualizar();")
        
            # Usando IA para clicar no botão Visualizar

            
    except TimeoutError:
        logging.warning("⏳ Tempo esgotado para encontrar a função Visualizar(). Pulando...")
        return "skip"

    try:
        analise = aguardar_estado_ia(
    estados_esperados=["csv_disponivel", "sem_dados", "erro"],  # ← sem "alerta"
    timeout=300,
    intervalo=5,
    pergunta=AGUARDAR_CSV["pergunta"],
    contexto=f"Rotina {CODIGO_ROTINA} — aguardando processamento do relatório",
    descricao_adicional=(
        "O relatório foi disparado e pode aparecer um dialog de 'Processando...' "
        "durante a geração — isso é normal e NÃO é um erro. "
        "Aguarde até o botão CSV aparecer na toolbar. "
        "Se a tela mostrar apenas campos de filtro sem CSV, está processando."
        "Caso apareca um pop-up escrito 'Processando...' não é necessário fechar ou executar alguma ação, apenas aguarde até que o relatório seja gerado e o botão CSV apareça na tela. "
    )
)

        if analise.get("estado") in (ESTADOS["SEM_DADOS"], ESTADOS["ERRO"]):
            logging.warning(f"⚠️ Sem dados para {data_ontem()} — fechando dialog e pulando.")
            clicar_elemento_ia(**CLICAR_BOTAO_VISUALIZAR)  # fecha o dialog OK que está na tela
            return "skip"

    except TimeoutError:
        logging.warning(f"⏳ Tempo esgotado aguardando processamento do relatório na rotina {CODIGO_ROTINA}. Pulando...")
        
        return "skip"
    


        
    if not clicar_elemento_ia(**CLICAR_CSV, descricao_adicional="É o botão CSV que fica na toolbar, no canto superior direito da tela, com um fundo cinza claro, escrito em preto 'CSV'."
                              "Ele fica entre o botão 'Salvar' e o botão 'PDF'"
                              "NÃO é o botão 'Voltar'"):
        logging.error("❌ Falha ao clicar no botão CSV via IA.")
        return "skip"


    logging.info("⏳ Aguardando download...")