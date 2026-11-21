"""
ProAutoMax - Notificações via Microsoft Teams
==============================================
Envia mensagens para um canal do Teams via Incoming Webhook.

Configuração (uma vez só):
    1. No Teams, abra o canal desejado
    2. Clique em ... → Conectores → Incoming Webhook → Configurar
    3. Dê um nome (ex: "ProAutoMax") e copie a URL gerada
    4. Adicione no .env:  TEAMS_WEBHOOK_URL=https://...

Uso:
    from function.teams_notify import notificar_inicio, notificar_fim

    notificar_inicio()
    # ... execução das rotinas ...
    notificar_fim(salvas=["030111", "120601"], erros=["0421"], ignoradas=[...])
"""

import logging
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")


def _enviar(payload: dict) -> bool:
    """
    Envia um payload JSON para o webhook do Teams.

    Returns:
        True se enviou com sucesso, False se falhou.
    """
    if not WEBHOOK_URL:
        logging.warning("⚠️  TEAMS_WEBHOOK_URL não configurado no .env — notificação ignorada")
        return False

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        if response.status_code in (200, 202):   # 202 = aceito (webhook do Power Automate)
            logging.info("📨 Notificação Teams enviada com sucesso")
            return True
        else:
            logging.warning(f"⚠️  Teams retornou status {response.status_code}: {response.text}")
            return False

    except requests.exceptions.Timeout:
        logging.warning("⚠️  Timeout ao enviar notificação para o Teams")
        return False
    except Exception as e:
        logging.warning(f"⚠️  Erro ao enviar notificação para o Teams: {e}")
        return False


def notificar_inicio(json_ativo: str = "rotinas.json", rotinas_ativas: list = []) -> bool:
    """
    Envia mensagem de início da automação.

    Args:
        json_ativo:      Nome do arquivo JSON sendo executado.
        rotinas_ativas:  Lista de descrições das rotinas com ativo=True.

    Exemplo de mensagem no Teams:
        🤖 Automação iniciada
        📋 rotinas.json | 20/04/2026 16:41
        📌 Rotinas que vão rodar (2):
        • 03.01.11 Rel. Crítica/Resumo de Pedido
        • 12.06.01 - Rel. Títulos Pendentes
    """
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas = []
    if rotinas_ativas:
        linhas.append(f"📌 **Rotinas que vão rodar ({len(rotinas_ativas)}):**")
        for r in rotinas_ativas:
            linhas.append(f"• {r}")

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",  # azul
        "summary": "ProAutoMax iniciado",
        "sections": [{
            "activityTitle": "🤖 Automação iniciada",
            "activitySubtitle": f"📋 {json_ativo}  |  {agora}",
            "activityText": "\n\n".join(linhas) if linhas else "",
            "markdown": True,
        }]
    }

    return _enviar(payload)


def _formatar_tempo(segundos: int) -> str:
    """Formata segundos em texto legível. Ex: 52s → '52 segundos', 744s → '12 minutos e 24 segundos'"""
    if segundos < 60:
        return f"{segundos} segundo{'s' if segundos != 1 else ''}"
    minutos = segundos // 60
    seg_restantes = segundos % 60
    texto = f"{minutos} minuto{'s' if minutos != 1 else ''}"
    if seg_restantes > 0:
        texto += f" e {seg_restantes} segundo{'s' if seg_restantes != 1 else ''}"
    return texto


def notificar_fim(
    salvas: list,
    erros: list,
    ignoradas: list,
    custo_usd: float = 0.0,
    custo_brl: float = 0.0,
    tempo_segundos: int = 0,
) -> bool:
    """
    Envia mensagem de conclusão com o resumo da execução.

    Args:
        salvas:          Lista de códigos de rotinas salvas com sucesso.
        erros:           Lista de códigos de rotinas que falharam.
        ignoradas:       Lista de códigos de rotinas ignoradas (ativo=False ou skip).
        custo_usd:       Custo estimado da sessão em USD (vem do relatorio_uso_tokens).
        tempo_segundos:  Tempo total de execução em segundos.

    Exemplo de mensagem no Teams:
        ✅ Automação finalizada — 14 salvas · 2 com erro · 4 ignoradas
        ✅ Salvas (14): 030111, 120601, ...
        ❌ Com erro (2): 0421, 020304
        💰 Custo IA: $0.032 USD (R$ 0.1824 BRL)
        ⏱️ Tempo de execução: 12 minutos e 24 segundos
    """
    total_salvas   = len(salvas)
    total_erros    = len(erros)
    total_ignoradas = len(ignoradas)

    # Cor do card: verde se sem erros, amarelo se tem erros
    cor = "00B050" if total_erros == 0 else "FFA500"

    # Ícone do título
    icone = "✅" if total_erros == 0 else "⚠️"

    titulo = (
        f"{icone} Automação finalizada — "
        f"{total_salvas} salva(s) · "
        f"{total_erros} com erro · "
        f"{total_ignoradas} ignorada(s)"
    )

    linhas = []

    if salvas:
        linhas.append(f"✅ **Salvas ({total_salvas}):** {', '.join(salvas)}")

    if erros:
        linhas.append(f"❌ **Com erro ({total_erros}):** {', '.join(erros)}")

    if ignoradas:
        linhas.append(f"⏭️ **Ignoradas ({total_ignoradas}):** {', '.join(ignoradas)}")

    if custo_usd > 0:
        linhas.append(f"💰 **Custo IA:** \\${custo_usd:.4f} USD (R\\$ {custo_brl:.4f} BRL)")

    if tempo_segundos > 0:
        linhas.append(f"⏱️ **Tempo de execução:** {_formatar_tempo(tempo_segundos)}")

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas.append(f"🕐 {agora}")

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": cor,
        "summary": titulo,
        "sections": [{
            "activityTitle": titulo,
            "activityText": "\n\n".join(linhas),
            "markdown": True,
        }]
    }

    return _enviar(payload)


def notificar_erro_critico(mensagem: str) -> bool:
    """
    Envia notificação de erro crítico — para quando a automação quebra antes de terminar.
    Ex: credenciais não encontradas, driver falhou, etc.

    Args:
        mensagem: Descrição do erro.
    """
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000",  # vermelho
        "summary": "ProAutoMax — erro crítico",
        "sections": [{
            "activityTitle": "🔴 Automação interrompida por erro crítico",
            "activitySubtitle": agora,
            "activityText": f"```\n{mensagem}\n```",
            "markdown": True,
        }]
    }

    return _enviar(payload)