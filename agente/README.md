# ProAutoMax — Agente da VM

Ponte entre o painel web (Supabase) e o robô que roda nesta máquina Windows.
O painel **enfileira**; este agente **executa** e devolve logs/status/custos.

```
Painel (Lovable)  ──insere run 'queued'──▶  Supabase  ◀──lê/escreve──  Agente (esta VM)
       ▲                                       │                            │
       └──────── logs ao vivo (Realtime) ──────┘             dispara main.py / main_tarde.py
```

## Por que um agente, e não só n8n / Power Automate?

O robô precisa de uma **sessão de desktop real** nesta VM (o `pyautogui` mexe no
mouse/tela e o IEDriver controla o Edge). Então a *execução* tem que acontecer aqui.

- **n8n** — ótimo para **agendar** (cron → insere run `queued` no Supabase) e
  notificar. Mas roda fora da VM e o nó "Execute Command" só entrega o stdout no
  fim, sem log ao vivo. Não substitui o agente.
- **Power Automate Desktop** — roda na máquina e até dispara `python main.py`,
  mas streamar log linha a linha e capturar o resumo/custo de volta é sofrível.
  Bom como gatilho, ruim como agente.

**Resumo:** mantenha este agente como núcleo. Se já usa n8n/PAD, use-os só para
agendar: ponha `ENABLE_SCHEDULER=false` e deixe a ferramenta externa inserir uma
linha em `runs` com `status='queued'` (e `periodo` = `manha` ou `tarde`).

## Instalação (na VM)

1. Copie a pasta `agent/` para a VM (pode ser dentro do projeto ou ao lado).
2. Crie/ative um venv e instale as deps:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. `copy .env.example .env` e preencha (URL, **service_role key**, `PROJECT_DIR`,
   `PYTHON_BIN`).
4. Rode:
   ```bat
   python agent.py
   ```

> Rode na **mesma sessão de desktop** onde o robô consegue abrir o Edge. Não rode
> como serviço "session 0" sem desktop interativo — o `pyautogui` não funciona lá.

### Deixar ligado sempre
Crie um atalho/`.bat` na pasta de Inicialização do Windows, ou uma tarefa no
Agendador de Tarefas com gatilho "Ao fazer logon" e opção **"Executar somente
quando o usuário estiver conectado"** (interativo).

## O que ele faz

- Pega a run `queued` mais antiga e marca como `running` (claim atômico — seguro
  mesmo com mais de um agente, embora o ideal seja **um só**).
- Dispara `main.py` (manhã) ou `main_tarde.py` (tarde) na raiz do projeto.
- Lê o stdout linha a linha → grava em `run_logs` (em lote, p/ não martelar o DB).
- No fim, faz parse do resumo do `executor.py` (salvas/erro/ignoradas, tokens,
  custo USD/BRL, duração) e atualiza a linha em `runs`.
- Executa **uma run por vez** (serial, de propósito — não dá pra dois robôs
  disputando a tela).
- Opcional: agendador interno lê a tabela `schedules` e enfileira no horário.

Convenção de `dias_semana`: `1=Seg, 2=Ter, 3=Qua, 4=Qui, 5=Sex, 6=Sáb, 7=Dom`
(bate com o painel).

## Captura de custo/resumo: como funciona (e como deixar 100% à prova de bala)

Por padrão o agente **lê o resumo do log** que o `executor.py` já imprime — não
precisa mexer em nada no projeto. Funciona bem.

Se quiser blindar (não depender de texto do log), dá pra fazer o `executor.py`
gravar um JSON no fim. Patch opcional, ~6 linhas, no fim de `executar_rotinas`,
logo após `uso = relatorio_uso_tokens()`:

```python
import json as _json, os as _os
_res = {
    "salvas": rotinas_salvas, "erros": rotinas_erros, "ignoradas": rotinas_ignoradas,
    "input_tokens": uso.get("input_tokens", 0), "output_tokens": uso.get("output_tokens", 0),
    "chamadas_api": uso.get("chamadas", 0),
    "custo_usd": uso.get("custo_usd", 0.0), "custo_brl": uso.get("custo_brl_aprox", 0.0),
    "duracao_segundos": tempo_total,
}
_destino_res = _os.environ.get("PROAUTOMAX_RESULT_FILE")
if _destino_res:
    with open(_destino_res, "w", encoding="utf-8") as _f:
        _json.dump(_res, _f, ensure_ascii=False)
```

Aí o agente passaria `PROAUTOMAX_RESULT_FILE=...\result_<runid>.json` no env e
leria esse arquivo no fim. Se você topar esse caminho, me avisa que eu ajusto o
`agent.py` pra preferir o JSON e cair no parser de log só como reserva.

## Tabelas usadas (criadas pelo painel/Lovable)

`runs`, `run_logs`, `schedules` — ver o modelo no prompt do Lovable.
Habilite **Realtime** em `runs` e `run_logs` para o log ao vivo no painel.
