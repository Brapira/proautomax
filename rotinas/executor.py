"""
executor.py — atualizado com suporte a IA
==========================================
Mudanças em relação à versão anterior:
    - Log de debug das rotinas registradas removido (não polui mais o log)
    - diagnosticar_e_decidir() chamado automaticamente quando uma rotina falha
    - Resumo final mantido
"""

import json
import logging
import os
import re
import time
import traceback

import pyautogui
from function.download import salvar_arquivo
from function.data_func import ano_vigente, gerar_nome_mes_vigente, data_ontem_nome
from function.ai_vision import diagnosticar_e_decidir, relatorio_uso_tokens
from function.teams_notify import notificar_inicio, notificar_fim, notificar_erro_critico


def _resolver_caminho(caminho: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), caminho)


def executar_rotinas(driver, rotinas_registradas, caminho_json):
    """
    Executa as rotinas definidas no arquivo JSON.

    Args:
        driver:               WebDriver do Selenium
        rotinas_registradas:  Dicionário com as rotinas carregadas
        caminho_json:         Caminho do arquivo rotinas.json
    """
    promaxPrimeiraJanela = driver.current_window_handle

    if not os.path.exists(caminho_json):
        logging.error(f"❌ Arquivo de configuração não encontrado: {caminho_json}")
        return

    try:
        with open(caminho_json, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"❌ Erro ao ler JSON: {e}")
        return

    total = len(config["execucao"])
    ativos = sum(1 for item in config["execucao"] if item.get("ativo", True))
    logging.info(f"📋 {total} rotina(s) no JSON — {ativos} ativa(s)\n")

    # Coleta descrições das rotinas ativas para mostrar na notificação de início
    rotinas_ativas_descricao = [
        item.get("descricao", item["codigo"])
        for item in config["execucao"]
        if item.get("ativo", True)
    ]

    notificar_inicio(caminho_json, rotinas_ativas=rotinas_ativas_descricao)

    # Timer de execução — calculado no fim para mostrar na notificação
    _tempo_inicio = time.time()

    rotinas_salvas = []
    rotinas_erros = []
    rotinas_ignoradas = []

    for idx, item in enumerate(config["execucao"], 1):

        codigo = item["codigo"]

        if not item.get("ativo", True):
            logging.info(f"⏭️  [{idx}/{total}] '{codigo}' ignorada (ativo=False)")
            rotinas_ignoradas.append(codigo)
            continue

        if codigo not in rotinas_registradas:
            logging.error(f"❌ Rotina '{codigo}' não registrada no loader")
            rotinas_erros.append(codigo)
            continue

        # Resolve o nome do arquivo de destino
        params = item.get("params", {})
        if params.get("nomeMes") == "MES_ATUAL":
            nome = f"{gerar_nome_mes_vigente()}.csv"
        elif params.get("anoVigente") == "ANO_VIGENTE":
            nome = f"{codigo}_{ano_vigente()}.csv"
        else:
            nome = item.get("nome", f"{codigo}.csv")

        if "{DATA_ONTEM}" in nome:
            nome = nome.replace("{DATA_ONTEM}", data_ontem_nome())

        destino  = _resolver_caminho(item["destino"])
        descricao = item.get("descricao", codigo)

        logging.info("=" * 60)
        logging.info(f"▶  [{idx}/{total}] {descricao}")
        logging.info(f"   Código:  {codigo}")
        logging.info(f"   Arquivo: {nome}")
        logging.info(f"   Destino: {destino}")
        logging.info("=" * 60)

        try:
            # 1. Executa a rotina (navega e gera o relatório)
            logging.info("📤 Executando rotina...")
            resultado = rotinas_registradas[codigo](driver, **params)

            # Rotina sinalizou para pular (sem dados, erro esperado, etc.)
            if resultado == "skip":
                logging.warning(f"⏭️  Rotina '{codigo}' pulada (retornou skip)\n")
                rotinas_ignoradas.append(codigo)
                _fechar_e_voltar(driver, promaxPrimeiraJanela)
                continue

            # 2. Salva o arquivo
            extensao_download = item.get("extensao_download")
            arquivo_final = salvar_arquivo(destino, nome, extensao_download=extensao_download)
            logging.info(f"✓ Concluído: {arquivo_final}\n")
            rotinas_salvas.append(codigo)

            pyautogui.moveTo(0, 0)
            _fechar_e_voltar(driver, promaxPrimeiraJanela)

        except Exception as e:
            logging.error(f"❌ Erro ao executar '{codigo}': {e}")
            traceback.print_exc()

            # 🤖 IA analisa a tela e sugere o que fazer
            logging.info("🤖 Consultando IA para diagnóstico...")
            try:
                diagnostico = diagnosticar_e_decidir(driver, contexto_rotina=codigo)
                acao_ia = diagnostico.get("acao", "skip")

                if acao_ia == "continuar":
                    logging.info("🤖 IA sugere continuar — tentando salvar mesmo assim...")
                    try:
                        arquivo_final = salvar_arquivo(destino, nome)
                        logging.info(f"✓ Salvo após diagnóstico IA: {arquivo_final}\n")
                        rotinas_salvas.append(codigo)
                    except Exception as e2:
                        logging.error(f"❌ Falha mesmo após diagnóstico IA: {e2}")
                        rotinas_erros.append(codigo)
                else:
                    logging.warning(f"🤖 IA sugere '{acao_ia}' — pulando rotina")
                    rotinas_erros.append(codigo)

            except Exception as e_ia:
                logging.error(f"❌ Falha no diagnóstico IA: {e_ia}")
                rotinas_erros.append(codigo)

            _fechar_e_voltar(driver, promaxPrimeiraJanela)
            continue

    # Resumo
    logging.info("*==" * 25)
    logging.info("📊 RESUMO DA EXECUÇÃO")
    logging.info(f"✅ Salvas com sucesso:  {len(rotinas_salvas)}  → {rotinas_salvas}")
    logging.info(f"❌ Com erro:            {len(rotinas_erros)} → {rotinas_erros}")
    logging.info(f"⏭️  Ignoradas:           {len(rotinas_ignoradas)} → {rotinas_ignoradas}")
    logging.info("^==" * 25)

    uso = relatorio_uso_tokens()

    tempo_total = int(time.time() - _tempo_inicio)
    logging.info(f"⏱️  Tempo total de execução: {tempo_total}s")

    notificar_fim(
        salvas=rotinas_salvas,
        erros=rotinas_erros,
        ignoradas=rotinas_ignoradas,
        custo_usd=uso.get("custo_usd", 0.0),
        custo_brl=uso.get("custo_brl_aprox", 0.0),
        tempo_segundos=tempo_total,
    )

    driver.quit()
    logging.info("=" * 60)
    logging.info("✓ EXECUÇÃO FINALIZADA 🍻")
    logging.info("=" * 60)


def _fechar_e_voltar(driver, janela_principal):
    """Fecha a janela atual e volta para a janela principal do Promax."""
    try:
        if driver.current_window_handle != janela_principal:
            driver.close()
            driver.switch_to.window(janela_principal)
    except Exception as e:
        logging.warning(f"⚠️  Erro ao fechar janela: {e}")