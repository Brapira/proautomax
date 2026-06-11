"""
Rotina: XX.XX.XX - Nome da Rotina
Descrição: Breve descrição do que este relatório faz.
Autor:
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

# ─── Imports opcionais (remover os que não usar) ─────────────────────────────
# from function.data_func import data_ontem, primeiro_dia_mes, ano_vigente, gerar_nome_mes_vigente

# ─── Identificação ───────────────────────────────────────────────────────────
# Se esta rotina tiver variantes via params (ex: _SEMDATA), use CODIGOS_ROTINA.
# Caso contrário, mantenha só CODIGO_ROTINA.
CODIGO_ROTINA = "XXXXXX"                            # ← código do Promax, sem pontos
# CODIGOS_ROTINA = ["XXXXXX", "XXXXXX_VARIANTE"]   # ← descomente se tiver variantes


def executar(driver, **kwargs):
    # ── Leitura de params vindos do rotinas.json (se houver) ─────────────────
    # meu_param = kwargs.get("meuParam", False)

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
    # Exemplo — select/combo:
    # select = wait.until(EC.presence_of_element_located((By.NAME, "nomeDoSelect")))
    # driver.execute_script("arguments[0].value = '01'; arguments[0].onchange();", select)
    # logging.info(f"ROTINA {CODIGO_ROTINA}: ⚙️ <campo> configurado para <valor>")

    # Exemplo — campo de data:
    # campo_data = wait.until(EC.presence_of_element_located((By.NAME, "nomeDoInput")))
    # driver.execute_script(f"arguments[0].value = '{data_ontem()}';", campo_data)

    # Exemplo — radio button:
    # radio = wait.until(
    #     EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='radio'][name='nome'][value='S']"))
    # )
    # if not radio.is_selected():
    #     radio.click()

    # Exemplo — checkbox:
    # checkbox = wait.until(EC.presence_of_element_located((By.NAME, "nomeDoCheckbox")))
    # if not checkbox.is_selected():
    #     driver.execute_script("arguments[0].click();", checkbox)

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

    # ── 5. Aguarda a IA confirmar que o CSV está disponível ───────────────────
    # timeout padrão: 300s (5 min). Relatórios pesados: até 600s (10 min).
    # descricao_adicional: contexto extra para a IA, ex: avisar sobre dialogs de "Processando..."
    logging.info("⏳ Aguardando processamento do relatório...")
    try:
        analise = aguardar_estado_ia(
            estados_esperados=["csv_disponivel", "sem_dados", "erro"],
            timeout=300,
            intervalo=4,
            pergunta=AGUARDAR_CSV["pergunta"],
            contexto=f"Rotina {CODIGO_ROTINA} — aguardando relatório de <descrição>",
            # descricao_adicional=(
            #     "Pode aparecer um dialog de 'Processando...' — isso é normal, apenas aguarde."
            # ),
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
