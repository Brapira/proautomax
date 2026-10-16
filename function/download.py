"""
Sistema de download híbrido - combina o melhor das duas abordagens.
Monitora Downloads padrão + PyWinAuto pra confirmar.
"""

import logging
import os
import time
import shutil
from collections import deque
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

# Instante em que a rotina atual começou (marcado pelo executor). Só aceitamos
# arquivos criados/modificados DEPOIS disso — senão um arquivo velho que sobrou
# em Downloads (ex.: falha ao mover) seria salvo como se fosse o da rotina atual.
_inicio_rotina: float | None = None
# Folga p/ granularidade do timestamp do sistema de arquivos
_FOLGA_TIMESTAMP = 2.0


def marcar_inicio_rotina():
    """Chamar antes de cada rotina, antes de ela disparar o download."""
    global _inicio_rotina
    _inicio_rotina = time.time()


# Classes UIA que hospedam o CONTEÚDO da página (relatório do Promax / web).
# Não descemos nelas: além de lento (milhares de nós), é lá que fica o 'Salvar'
# do relatório, que não é o que queremos. A barra de download e os botões do
# Edge ficam na moldura, fora dessas classes.
_CLASSES_CONTEUDO = {"Internet Explorer_Server", "Chrome_RenderWidgetHostHWND"}


def _janelas_edge():
    """Janelas de topo do Edge visíveis (não minimizadas)."""
    janelas = []
    try:
        for w in Desktop(backend="uia").windows():
            try:
                if "Edge" not in (w.window_text() or ""):
                    continue
                if w.rectangle().top < -10000:   # minimizada/fora da tela
                    continue
                janelas.append(w)
            except Exception:
                continue
    except Exception as e:
        logging.debug(f"UIA listando janelas: {e}")
    return janelas


def _iter_controles_moldura(raiz, fim, max_nos=3000):
    """
    Percorre (em largura) os controles UIA de `raiz` SEM entrar no conteúdo da
    página. Para no prazo `fim` ou após `max_nos` nós, pra nunca estourar o timeout.
    """
    fila = deque([raiz])
    vistos = 0
    while fila and vistos < max_nos and time.time() < fim:
        el = fila.popleft()
        vistos += 1
        yield el
        try:
            if el.element_info.class_name in _CLASSES_CONTEUDO:
                continue
            fila.extend(el.children())
        except Exception:
            continue


def _acionar(controle) -> bool:
    try:
        controle.invoke()
        return True
    except Exception:
        try:
            controle.click_input()
            return True
        except Exception:
            return False


def _clicar_salvar_uia(timeout=20) -> bool:
    """
    Clica no 'Salvar' da barra de download do IE-mode por ACESSIBILIDADE.

    Estrutura descoberta na VM:
        Pane class='Frame Notification Bar' (rect embaixo, ~top 990)
          ToolBar name='Notificação'
            SplitButton name='Salvar'   ← alvo

    Varre só a moldura do Edge (não entra no conteúdo da página, ver
    _CLASSES_CONTEUDO) e, por segurança, só aceita um 'Salvar' na parte de
    BAIXO da janela (proporcional ao tamanho dela, independe da resolução).
    """
    fim = time.time() + timeout
    while time.time() < fim:
        for w in _janelas_edge():
            try:
                wr = w.rectangle()
                limite = wr.top + wr.height() * 0.6
            except Exception:
                continue
            for c in _iter_controles_moldura(w, fim):
                try:
                    info = c.element_info
                    if info.name != "Salvar" or info.control_type not in ("SplitButton", "Button"):
                        continue
                    r = c.rectangle()
                except Exception:
                    continue
                if r.top > limite and _acionar(c):
                    logging.info(f"✅ 'Salvar' da barra de download acionado via acessibilidade (top={r.top})")
                    return True
        time.sleep(1)
    return False


def fechar_barra_download(timeout=5) -> bool:
    """
    Fecha a barra de download do EDGE MODERNO ('Download concluído', com
    'Abrir pasta' / 'Fechar downloads') que fica na moldura do navegador após
    o arquivo baixar. Se não for fechada, ela sobra na tela e confunde a
    detecção de estado da PRÓXIMA rotina (ela fica presa em 'download_salvar').

    Usa acessibilidade (UIA) pra clicar em 'Fechar downloads'. Não é fatal:
    se não achar, só loga e segue.
    """
    fim = time.time() + timeout
    while time.time() < fim:
        for w in _janelas_edge():
            for b in _iter_controles_moldura(w, fim):
                try:
                    info = b.element_info
                    if info.control_type != "Button":
                        continue
                    nome = (info.name or "").lower()
                except Exception:
                    continue
                # botão específico da barra de download concluído
                if "fechar" in nome and "download" in nome and _acionar(b):
                    logging.info("🧹 Barra de download do Edge fechada")
                    return True
        time.sleep(0.5)
    logging.debug("Barra de download não encontrada pra fechar (ok, pode não estar visível)")
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


def _timestamp(caminho) -> float:
    # ctime no Windows = criação; mtime pode vir preservado se o arquivo foi movido
    return max(os.path.getmtime(caminho), os.path.getctime(caminho))


def aguardar_novo_arquivo(timeout=120, extensao=".inf", desde=None):
    """
    Espera um arquivo `extensao` em Downloads. Se `desde` for dado, ignora
    arquivos com timestamp anterior (sobras de downloads antigos).
    """
    logging.info(f"⏳ Aguardando arquivo {extensao.upper()}...")
    logging.info(f"📂 Monitorando: {PASTA_DOWNLOADS}")

    inicio = time.time()
    corte = (desde - _FOLGA_TIMESTAMP) if desde else None
    ultimo_log = 0

    while time.time() - inicio < timeout:
        try:
            arquivos = [
                f for f in os.listdir(PASTA_DOWNLOADS)
                if f.lower().endswith(extensao.lower())
                and not f.endswith((".crdownload", ".tmp", ".partial"))
                and os.path.isfile(os.path.join(PASTA_DOWNLOADS, f))
                and (corte is None or _timestamp(os.path.join(PASTA_DOWNLOADS, f)) >= corte)
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


def _confirmar_e_aguardar_arquivo(extensao, desde, tentativas=3, espera_por_tentativa=40):
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
            return aguardar_novo_arquivo(timeout=espera_por_tentativa, extensao=extensao, desde=desde)
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
    # Sem marca do executor (chamada avulsa), vale só o que surgir daqui pra frente
    desde = _inicio_rotina or time.time()

    if DOWNLOAD_AUTOMATICO:
        # Edge baixa sem perguntar — não há botão 'Salvar' pra clicar.
        # Só esperamos o arquivo aparecer na pasta monitorada.
        logging.info("⚡ Modo download automático (sem 'Salvar') — aguardando arquivo...")
        try:
            arquivo_baixado = aguardar_novo_arquivo(timeout=120, extensao=extensao, desde=desde)
        except TimeoutError as e:
            logging.error(f"❌ {e}")
            raise Exception("Timeout: arquivo não foi baixado")
    else:
        # Confirma o 'Salvar' (UIA, IA de fallback), re-tentando se não vier.
        arquivo_baixado = _confirmar_e_aguardar_arquivo(extensao, desde)
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
        # Fecha a barra de download do Edge pra não sobrar na tela e confundir
        # a detecção de estado da próxima rotina.
        try:
            fechar_barra_download()
        except Exception as e:
            logging.debug(f"fechar_barra_download: {e}")
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