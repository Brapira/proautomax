import logging
import time
import pyautogui
import os

# Variaveis de imagens
CSV_BTN = os.getenv("PATH_IMAGE_CSV")
CSV_BTN_2 = os.getenv("PATH_IMAGE_CSV_2")
SALVAR_BTN = os.getenv("PATH_IMAGE_SAVE")
SALVAR_BTN_2 = os.getenv("PATH_IMAGE_SAVE_2")
VISUALIZAR_BTN = os.getenv("PATH_IMAGE_VISUALIZAR")
PROCESSANDO_IMG = os.getenv("PATH_IMAGE_PROCESSANDO")


def encontrar_imagem(caminhoImagem, timeout=None, confidence=0.6, opcional=False):
    inicio = time.time()
    tentativas = 0
    ja_encontrou = False  # 🆕 rastreia se já apareceu alguma vez

    while True:
        try:
            pos = pyautogui.locateOnScreen(caminhoImagem, confidence=confidence)

            if pos:
                if "processando" not in caminhoImagem.lower():
                    logging.info(f"✅ Imagem encontrada: {caminhoImagem}")
                ja_encontrou = True
                return pos

        except pyautogui.ImageNotFoundException:
            pass

        tentativas += 1

        if tentativas % 10 == 0:
            logging.info(f"🔍 Procurando imagem... ({tentativas} tentativas)")

        if timeout and (time.time() - inicio > timeout):
            # 🆕 Se é opcional OU já apareceu antes (processou rápido), não é erro
            if opcional or ja_encontrou:
                logging.info(f"⏭️ Imagem não encontrada (ignorado): {caminhoImagem}")
                return None

            logging.error(f"❌ Imagem não encontrada após {timeout}s: {caminhoImagem}")
            raise TimeoutError(f"Imagem não encontrada: {caminhoImagem}")

        try:
            pyautogui.moveRel(1, 0)
            pyautogui.moveRel(-1, 0)
        except:
            pass

        time.sleep(0.5)


# Encontra a imagem e clica
def clicar_imagem(caminhoImagem, timeout=120):
    try:
        pos = encontrar_imagem(caminhoImagem, timeout=timeout)
        if pos:
            logging.info("Clicando no botão...")
            time.sleep(1)
            pyautogui.click(pyautogui.center(pos))
            logging.info("Botão clicado!")
    except TimeoutError:
        logging.error(
            f"❌ Não foi possível encontrar/clicar na imagem: {caminhoImagem}"
        )


def aguardar_processamento():
    logging.info("⏳ Verificando processamento visual...")
    try:
        # espera a tela de processamento aparecer
        encontrar_imagem(PROCESSANDO_IMG, timeout=15)

        logging.info("⏳ Processamento detectado")

        # agora espera ela SUMIR
        inicio = time.time()
        ultimo_log = 0

        while True:
            try:
                encontrar_imagem(PROCESSANDO_IMG, timeout=3)
                agora = time.time()

                # ainda existe
                if agora - ultimo_log > 15:
                    logging.info("🐢 Ainda processando...")
                    ultimo_log = agora

            except TimeoutError:
                # sumiu
                break

            if time.time() - inicio > 600:
                raise TimeoutError("Processamento demorou demais")

        logging.info("✅ Processamento finalizado")

    except TimeoutError:
        logging.info("ℹ️ Tela de processamento não apareceu")
