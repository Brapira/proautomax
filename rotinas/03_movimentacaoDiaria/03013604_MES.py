"""
Rotina: 03.01.36.04
Descrição: Baixa um CSV com relatório de pedidos em caixa do mês inteiro do Promax.
Autor: Carol
"""

import logging
import time
import pyautogui
from function.abrir_rotinas import abrir_rotinas
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.data_func import primeiro_dia_mes
from function.funcoes_rotina import aguardar_tela_carregar
from function.ai_vision import ESTADOS, aguardar_estado_ia, clicar_elemento_ia, focar_janela_promax
from function.acoes import AGUARDAR_CSV_PESADO, CLICAR_CSV
from function.download import salvar_arquivo as _salvar_arquivo
from function.troca_janela import trocar_para_nova_janela

CODIGO_ROTINA = "03013604_MES"


def executar(driver, _destino=None, _nome=None, _extensao_download=None, **kwargs):

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

    logging.info("⚙️ Configurando parâmetros da rotina 03.01.36.04 em caixa do mês inteiro...")
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "rotina")))

    data_inicial = wait.until(EC.presence_of_element_located((By.NAME, "dtInicial")))
    driver.execute_script(f"arguments[0].value = '{primeiro_dia_mes()}';", data_inicial)
    logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ Data inicial configurada para {primeiro_dia_mes()}")

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

    # Relatório do mês inteiro — pode demorar bastante, usa AGUARDAR_CSV_PESADO
    logging.info("⏳ Aguardando processamento do relatório (até 10 min)...")
    try:
        analise = aguardar_estado_ia(
            **AGUARDAR_CSV_PESADO,
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando relatório do mês inteiro",
            descricao_adicional=(
                "Este relatório processa o mês inteiro e pode demorar vários minutos. "
                "O dialog de 'Processando...' é normal — aguarde o botão CSV aparecer."
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

    # Retry automático: o Promax às vezes deleta o arquivo temp antes do Edge terminar de baixar.
    # Clicar no CSV novamente força o Promax a gerar um novo arquivo temp.
    if _destino and _nome:
        logging.info("⏳ Aguardando download (1ª tentativa)...")
        try:
            _salvar_arquivo(_destino, _nome, extensao_download=_extensao_download)
            return "salvo"
        except Exception as e:
            logging.warning(f"⚠️ 1ª tentativa falhou: {e}. Clicando CSV novamente...")

        time.sleep(3)
        if not clicar_elemento_ia(**CLICAR_CSV):
            logging.error("❌ Falha ao re-clicar CSV no retry")
            return "skip"

        logging.info("⏳ Aguardando download (2ª tentativa)...")
        try:
            _salvar_arquivo(_destino, _nome, extensao_download=_extensao_download)
            return "salvo"
        except Exception as e:
            logging.error(f"❌ Download falhou após retry: {e}")
            return "skip"

    logging.info("⏳ Aguardando download...")
