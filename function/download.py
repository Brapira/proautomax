"""
Sistema de download híbrido - combina o melhor das duas abordagens.
Monitora Downloads padrão + PyWinAuto pra confirmar.
"""

import logging
import os
import time
import shutil
from pywinauto.keyboard import send_keys
from pywinauto import Desktop
from dotenv import load_dotenv
from function.ai_vision import clicar_elemento_ia
from function.acoes import CLICAR_DOWNLOAD_SALVAR

load_dotenv()
# Pasta Downloads padrão do Windows
PASTA_DOWNLOADS =  os.getenv("PATH_USER") #str(Path.home() / "Downloads")

# Se o Edge estiver configurado para baixar SEM perguntar (sem barra de 'Salvar'),
# ligue isto no .env: DOWNLOAD_AUTOMATICO=true
# Aí o robô pula o passo do 'Salvar' (que a IA erra) e só espera o arquivo cair.
DOWNLOAD_AUTOMATICO = os.getenv("DOWNLOAD_AUTOMATICO", "false").lower() in ("1", "true", "sim", "yes")


def _clicar_salvar_uia(timeout=20) -> bool:
    """
    Clica no 'Salvar' da barra de download do IE-mode por ACESSIBILIDADE.

    Estrutura descoberta na VM:
        Pane class='Frame Notification Bar' (rect embaixo, ~top 990)
          ToolBar name='Notificação'
            SplitButton name='Salvar'   ← alvo

    Estratégia robusta: varre os descendentes das janelas do Edge procurando
    controles chamados 'Salvar' e escolhe o que está EMBAIXO (top alto) — assim
    não confunde com o 'Salvar' do TOPO do relatório (top ~141).
    """
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            for w in Desktop(backend="uia").windows():
                try:
                    if "Edge" not in (w.window_text() or ""):
                        continue
                    if w.rectangle().top < -10000:   # minimizada/fora da tela
                        continue
                except Exception:
                    continue

                try:
                    candidatos = w.descendants(title="Salvar")
                except Exception:
                    continue

                for c in candidatos:
                    try:
                        r = c.rectangle()
                        ctype = getattr(c.element_info, "control_type", "")
                    except Exception:
                        continue
                    # Só o da barra de download (metade de baixo da tela).
                    # O 'Salvar' do relatório fica no topo (top pequeno) e é ignorado.
                    if ctype in ("SplitButton", "Button") and r.top > 800:
                        try:
                            c.invoke()
                        except Exception:
                            try:
                                c.click_input()
                            except Exception:
                                continue
                        logging.info(f"✅ 'Salvar' da barra de download acionado via acessibilidade (top={r.top})")
                        return True
        except Exception as e:
            logging.debug(f"UIA varrendo janelas: {e}")
        time.sleep(1)
    return False


def confirmar_download(metodo="uia"):
    """
    Confirma o 'Salvar' da barra de download.
      metodo='uia'     -> DETERMINÍSTICO: clica o SplitButton 'Salvar' da barra
                          de notificação por acessibilidade (recomendado).
      metodo='ia'      -> IA localiza e clica por coordenada (fallback).
      metodo='teclado' -> Alt+Shift+S (instável neste ambiente; evitar).
    """
    time.sleep(2)

    if metodo == "uia":
        logging.info("🎯 Confirmando download (Salvar) via acessibilidade...")
        if _clicar_salvar_uia():
            return
        logging.warning("   barra 'Salvar' não encontrada via UIA; caindo pra IA")

    if metodo == "teclado":
        logging.info("⌨️ Confirmando download via teclado (Alt+Shift+S)...")
        try:
            send_keys("%+s")   # Alt+Shift+S = 'Salvar' na barra de notificação do IE-mode
            logging.info("⌨️ Alt+Shift+S enviado")
            return
        except Exception as e:
            logging.warning(f"   teclado falhou ({e}); caindo pra IA")

    logging.info("⏳ Procurando botão Salvar...")
    # Tenta clicar no botão Salvar da barra de download
    if not clicar_elemento_ia(**CLICAR_DOWNLOAD_SALVAR):
        logging.error("❌ Botão Salvar não encontrado.")
        raise TimeoutError("Botão Salvar não apareceu.")

    logging.info("🎯 Continuando execução...")


def aguardar_novo_arquivo(timeout=120, extensao=".inf"):
    logging.info(f"⏳ Aguardando arquivo {extensao.upper()}...")
    logging.info(f"📂 Monitorando: {PASTA_DOWNLOADS}")

    inicio = time.time()
    ultimo_log = 0

    while time.time() - inicio < timeout:
        try:
            arquivos = [
                f for f in os.listdir(PASTA_DOWNLOADS)
                if f.lower().endswith(extensao.lower())
                and not f.endswith((".crdownload", ".tmp", ".partial"))
                and os.path.isfile(os.path.join(PASTA_DOWNLOADS, f))
            ]

            if arquivos:
                # pega o mais recente
                arquivo_mais_recente = max(
                    arquivos,
                    key=lambda f: os.path.getmtime(os.path.join(PASTA_DOWNLOADS, f))
                )

                caminho = os.path.join(PASTA_DOWNLOADS, arquivo_mais_recente)

                if _arquivo_esta_pronto(caminho):
                    logging.info(f"✓ Arquivo detectado e pronto: {arquivo_mais_recente}")
                    return arquivo_mais_recente

            # log a cada 5s
            tempo = time.time() - inicio
            if tempo - ultimo_log >= 5:
                logging.info(f"   ⏱️ {int(tempo)}s - Aguardando arquivo...")
                ultimo_log = tempo

        except Exception as e:
            logging.error(f"   ⚠️ Erro ao monitorar: {e}")

        time.sleep(1)

    raise TimeoutError(f"Nenhum arquivo {extensao.upper()} apareceu após {timeout}s")



def _arquivo_esta_pronto(caminho, tempo_estabilidade=2.0):
    """
    Verifica se o arquivo terminou de ser baixado monitorando a estabilidade do tamanho
    e se o arquivo está acessível para escrita.
    
    Args:
        caminho: Caminho completo do arquivo
        tempo_estabilidade: Tempo (segundos) que o tamanho deve permanecer inalterado
    
    Returns:
        True se o arquivo está pronto, False caso contrário
    """
    start_stable = None
    last_size = -1
    
    # Tenta monitorar por no máximo 15 segundos (timeout interno de segurança)
    max_check_time = 15 
    check_start = time.time()

    while (time.time() - check_start) < max_check_time:
        try:
            if not os.path.exists(caminho):
                return False
                
            current_size = os.path.getsize(caminho)
            
            if current_size == last_size and current_size > 0:
                if start_stable is None:
                    start_stable = time.time()
                elif (time.time() - start_stable) >= tempo_estabilidade:
                    # Tamanho estável pelo tempo necessário. Tenta abrir.
                    try:
                        with open(caminho, 'rb'):
                            return True
                    except (OSError, PermissionError):
                        # Arquivo bloqueado (ex: Windows processando .inf), reseta estabilidade
                        start_stable = None
            else:
                # Tamanho mudou ou é 0, reseta contagem
                last_size = current_size
                start_stable = None
                
            time.sleep(0.5)
            
        except Exception:
            # Erro ao acessar arquivo (talvez sumiu momentaneamente)
            return False

    return False


def mover_arquivo_com_retry(origem, destino, max_tentativas=5):
    """
    Move o arquivo com retry em caso de erro de permissão.
    
    Args:
        origem: Caminho do arquivo de origem
        destino: Caminho do arquivo de destino
        max_tentativas: Número máximo de tentativas
    
    Returns:
        True se conseguiu mover, False caso contrário
    """
    for tentativa in range(max_tentativas):
        try:
            if tentativa > 0:
                logging.warning(f"   🔄 Tentativa {tentativa + 1}/{max_tentativas}")
                time.sleep(2)
            
            shutil.move(origem, destino)
            return True
            
        except PermissionError as e:
            if tentativa == max_tentativas - 1:
                # Última tentativa: copia em vez de mover
                logging.error(f"   💡 Erro de permissão, tentando copiar...")
                try:
                    shutil.copy2(origem, destino)
                    os.remove(origem)
                    return True
                except:
                    logging.warning(f"   ⚠️ Arquivo mantido em: {origem}")
                    return False
        
        except Exception as e:
            logging.error(f"   ❌ Erro ao mover: {e}")
            if tentativa == max_tentativas - 1:
                return False
    
    return False


def _confirmar_e_aguardar_arquivo(extensao, tentativas=3, espera_por_tentativa=40):
    """
    Confirma o 'Salvar' e espera o arquivo aparecer. Se não vier dentro de
    `espera_por_tentativa` segundos, RE-confirma e espera de novo.

    Método principal: UIA (acessibilidade) — clica o SplitButton 'Salvar' da
    barra de notificação pelo nome, sem pixel/IA. A última tentativa cai pra IA
    só como rede de segurança. Orçamento total ≈ tentativas * espera_por_tentativa.

    Retorna o nome do arquivo baixado, ou None se esgotar as tentativas.
    """
    # UIA nas primeiras, IA na última como fallback
    metodos = ["uia"] * (tentativas - 1) + ["ia"] if tentativas > 1 else ["uia"]
    for i in range(1, tentativas + 1):
        metodo = metodos[i - 1]
        logging.info(f"💾 Confirmação de download — tentativa {i}/{tentativas} (via {metodo})")
        try:
            confirmar_download(metodo=metodo)
        except Exception as e:
            logging.warning(f"   confirmar_download falhou: {e}")

        try:
            return aguardar_novo_arquivo(timeout=espera_por_tentativa, extensao=extensao)
        except TimeoutError:
            logging.warning(
                f"   ⏱️ arquivo não apareceu em {espera_por_tentativa}s — "
                f"re-confirmando o Salvar"
            )
    logging.error("❌ Arquivo não baixou após todas as tentativas de confirmação")
    return None


def salvar_arquivo(destino, nome_arquivo, extensao_download=None):
    """
    Fluxo completo de salvamento.

    Args:
        destino: Pasta de destino final
        nome_arquivo: Nome final do arquivo (ex: "0111.csv")
        extensao_download: Extensão do arquivo em Downloads quando diferente do nome final
                           (ex: baixa .txt mas salva como .csv)

    Returns:
        Caminho completo do arquivo salvo

    Raises:
        Exception: Se não conseguir salvar o arquivo
    """
    logging.info("💾 Iniciando salvamento...")

    extensao = extensao_download or ".inf"

    if DOWNLOAD_AUTOMATICO:
        # Edge baixa sem perguntar — não há botão 'Salvar' pra clicar.
        # Só esperamos o arquivo aparecer na pasta monitorada.
        logging.info("⚡ Modo download automático (sem 'Salvar') — aguardando arquivo...")
        try:
            arquivo_baixado = aguardar_novo_arquivo(timeout=120, extensao=extensao)
        except TimeoutError as e:
            logging.error(f"❌ {e}")
            raise Exception("Timeout: arquivo não foi baixado")
    else:
        # Modo antigo: confirma o 'Salvar' (via IA), re-tentando se não vier.
        arquivo_baixado = _confirmar_e_aguardar_arquivo(extensao)
        if not arquivo_baixado:
            raise Exception("Timeout: arquivo não foi baixado")
    
    # 3. Move para o destino final
    origem = os.path.join(PASTA_DOWNLOADS, arquivo_baixado)
    
    # Garante que a pasta de destino existe
    os.makedirs(destino, exist_ok=True)
    
    # Caminho final
    caminho_final = os.path.join(destino, nome_arquivo)
    
    logging.info(f"📦 Movendo arquivo...")
    logging.info(f"   De: {origem}")
    logging.info(f"   Para: {caminho_final}")
    
    # Remove arquivo antigo se existir
    if os.path.exists(caminho_final):
        try:
            os.remove(caminho_final)
            logging.info(f"   🗑️ Arquivo antigo removido")
        except Exception as e:
            logging.error(f"   ⚠️ Não foi possível remover arquivo antigo: {e}")
    
    # Move o arquivo
    if mover_arquivo_com_retry(origem, caminho_final):
        logging.info(f"✓ Arquivo salvo com sucesso!")
        return caminho_final
    else:
        raise Exception("Não foi possível mover o arquivo para o destino")


def limpar_pasta_temp():
    """
    Função de compatibilidade - não necessária nessa abordagem.
    """
    pass


def confirmar_download_com_retry(tentativas=3):
    """
    Função de compatibilidade - chama confirmar_download().
    """
    confirmar_download()


def mover_arquivo(destino, nome_arquivo):
    """
    Função de compatibilidade com o executor.py.
    Apenas chama salvar_arquivo().
    """
    return salvar_arquivo(destino, nome_arquivo)


# Inicialização
logging.info(f"✓ Sistema de download carregado")
logging.info(f"📂 Pasta de downloads: {PASTA_DOWNLOADS}")