from datetime import datetime
import subprocess
import time
import pygetwindow as gw
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from function.abrir_rotinas import abrir_rotinas
from function.ai_vision import fechar_popups_inicio, focar_janela_promax
from function.teams_notify import notificar_erro_critico
from function.acoes import CONTEXTO_POPUPS_INICIO
from rotinas.loader import carregar_rotinas
from rotinas.executor import executar_rotinas
from dotenv import load_dotenv
import os

# Configurações de LOG
log_dir = r"\\192.168.1.213\Arquivos\Administrativo\TecInfo\DB_VENDAS\testeProauto\logs"
os.makedirs(log_dir, exist_ok=True)

max_logs = 5
logs = sorted(
    [os.path.join(log_dir, f) for f in os.listdir(log_dir)],
    key=os.path.getmtime
)
while len(logs) >= max_logs:
    os.remove(logs[0])
    logs.pop(0)

data_execucao = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
arquivo_log = os.path.join(log_dir, f"automacao_{data_execucao}.log")

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

file_handler = logging.FileHandler(arquivo_log, encoding="utf-8")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Carrega variáveis de ambiente
load_dotenv()

PROMAX_USER     = os.getenv("PROMAX_USER")
PROMAX_PASSWORD = os.getenv("PROMAX_PASSWORD")

if not PROMAX_USER or not PROMAX_PASSWORD:
    logging.error("CREDENCIAIS DE LOGIN NÃO ENCONTRADAS NO .ENV")
    raise ValueError("CREDENCIAIS DE LOGIN NÃO ENCONTRADAS NO .ENV")
else:
    logging.info("CREDENCIAIS DE LOGIN ENCONTRADAS")

# Configuração do driver
ie_options = webdriver.IeOptions()
ie_options.attach_to_edge_chrome = True
ie_options.edge_executable_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ie_options.ignore_zoom_level = True
ie_options.require_window_focus = True
# ie_options.ensure_clean_session = True
ie_options.ignore_protected_mode_settings = True
ie_options.initial_browser_url = "https://brapira.promaxcloud.com.br"

logging.info("🧹 Limpando processos antigos do driver...")
subprocess.run(["taskkill", "/f", "/im", "IEDriverServer.exe"], capture_output=True)
subprocess.run(["taskkill", "/f", "/im", "msedge.exe"], capture_output=True)
time.sleep(3)

driver = None
for tentativa in range(1, 4):
    try:
        service = webdriver.IeService(executable_path=r".\drivers\IEDriverServer.exe")
        driver  = webdriver.Ie(service=service, options=ie_options)
        logging.info("✅ Driver iniciado com sucesso")
        break
    except Exception as e:
        logging.warning(f"⚠️ Tentativa {tentativa}/3 falhou ao iniciar driver: {e}")
        subprocess.run(["taskkill", "/f", "/im", "IEDriverServer.exe"], capture_output=True)
        subprocess.run(["taskkill", "/f", "/im", "msedge.exe"], capture_output=True)
        if tentativa < 3:
            time.sleep(5)
        else:
            raise RuntimeError("Não foi possível iniciar o IEDriverServer após 3 tentativas") from e

driver.maximize_window()

# Foco na janela
window_title = "PromaxWEB"
for window in gw.getAllTitles():
    if window_title in window:
        gw.getWindowsWithTitle(window)[0].activate()
        break

wait = WebDriverWait(driver, 20)

# Login
driver.switch_to.frame("top")

user_box = wait.until(EC.presence_of_element_located((By.NAME, "Usuario")))
pw_box   = wait.until(EC.presence_of_element_located((By.NAME, "Senha")))

user_box.clear()
driver.execute_script("arguments[0].value = arguments[1];", user_box, PROMAX_USER)
pw_box.clear()
driver.execute_script("arguments[0].value = arguments[1];", pw_box, PROMAX_PASSWORD)

btn = wait.until(EC.presence_of_element_located((By.ID, "BtnConfirm")))
btn.click()

WebDriverWait(driver, 20)

btn = wait.until(EC.presence_of_element_located((By.NAME, "cmdConfirma")))
btn.click()

# ✅ Fecha todos os popups pós-login (JS alerts + popups visuais via IA)
fechar_popups_inicio(driver, contexto=CONTEXTO_POPUPS_INICIO)

# ✅ Garante que o foco voltou para o Promax após fechar os popups
focar_janela_promax()

try:
    rotinas = carregar_rotinas()
    executar_rotinas(driver, rotinas, "rotinas.json")
except Exception as e:
    logging.error(f"🔴 Erro crítico na execução: {e}")
    notificar_erro_critico(str(e))
    raise