import logging
import time

import requests

_BASE_URL = "http://brapira.promaxcloud.com.br:8080/arquivos/download/file"


def aguardar_e_baixar_arquivo(driver, caminho: str, timeout: int = 300, intervalo: int = 5) -> bool:
    """
    Espera o arquivo aparecer no Gerenciador de Arquivos e dispara o download via driver.

    Args:
        driver:    WebDriver com sessão autenticada no Promax
        caminho:   Caminho relativo ao arquivo, ex: "dvs/2artd10_0001.txt"
        timeout:   Segundos máximos de espera
        intervalo: Segundos entre tentativas de polling

    Returns:
        True se o download foi disparado, False se timeout
    """
    url = f"{_BASE_URL}/{caminho}"
    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}

    logging.info(f"⏳ Aguardando arquivo no Gerenciador: {caminho}")
    inicio = time.time()

    while time.time() - inicio < timeout:
        try:
            resp = requests.head(url, cookies=cookies, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                logging.info(f"✅ Arquivo disponível! Iniciando download via driver...")
                driver.get(url)
                return True
        except requests.RequestException:
            pass
        time.sleep(intervalo)

    logging.error(f"❌ Timeout aguardando arquivo no Gerenciador: {caminho}")
    return False
