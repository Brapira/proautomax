"""
ProAutoMax — Agente da VM
=========================
Ponte entre o painel web (Supabase) e o robô que roda nesta máquina Windows.

O que ele faz, em loop:
  1. Procura no Supabase uma execução com status 'queued'.
  2. "Reivindica" a execução (status -> 'running').
  3. Dispara o script certo (main.py p/ manhã, main_tarde.py p/ tarde) como
     subprocesso, NA RAIZ do projeto e numa sessão interativa (pyautogui precisa
     de tela real).
  4. Lê o stdout linha a linha e grava em 'run_logs' (o painel mostra ao vivo
     via Supabase Realtime).
  5. No fim, faz o parse do resumo (salvas/erro/ignoradas + tokens + custo) e
     atualiza a linha em 'runs'.

Opcional: um agendador interno (thread) que lê a tabela 'schedules' e enfileira
execuções no horário. Desligue (ENABLE_SCHEDULER=false) se for agendar por fora
(n8n, Power Automate, Agendador de Tarefas do Windows, etc.) — nesse caso basta
a ferramenta externa inserir uma linha em 'runs' com status='queued'.

Rode SEMPRE nesta VM, na MESMA sessão de desktop onde o robô consegue abrir o
Edge e mexer no mouse. Apenas UMA execução roda por vez (é serial de propósito).

Dependências:  pip install -r requirements.txt
Config:        copie .env.example para .env e preencha.
Executar:      python agent.py
"""

import ast
import os
import re
import json
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, date, timedelta

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ─── Configuração (vem do .env) ──────────────────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Raiz do projeto ProAutoMax (onde estão main.py / main_tarde.py)
PROJECT_DIR = os.getenv("PROJECT_DIR", r"C:\ProAutoMax")
# Interpretador Python que tem as deps do robô instaladas (venv de preferência)
PYTHON_BIN  = os.getenv("PYTHON_BIN", sys.executable)

SCRIPT_MANHA = os.getenv("SCRIPT_MANHA", "main.py")
SCRIPT_TARDE = os.getenv("SCRIPT_TARDE", "main_tarde.py")

# Arquivos JSON de rotinas que cada script lê (na raiz do projeto)
JSON_MANHA = os.getenv("JSON_MANHA", "rotinas.json")
JSON_TARDE = os.getenv("JSON_TARDE", "rotinas_tarde.json")

POLL_SECONDS     = int(os.getenv("POLL_SECONDS", "5"))
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "sim", "yes")

# Regenerar o rotinas.json a partir da tabela 'routines' antes de cada run,
# fazendo o painel virar a fonte da verdade dos toggles ativo/inativo.
SYNC_ROTINAS_JSON = os.getenv("SYNC_ROTINAS_JSON", "true").lower() in ("1", "true", "sim", "yes")

# Janela de tolerância do agendador: dispara se o horário já passou há até
# X minutos e ainda não rodou hoje (evita perder a run se o agente estava
# parado no minuto exato).
AGENDADOR_TOLERANCIA_MIN = int(os.getenv("AGENDADOR_TOLERANCIA_MIN", "10"))

# Config da Crítica (projeto Selenium SEPARADO do ProAutoMax)
CRITICA_DIR    = os.getenv("CRITICA_DIR", r"C:\ProAutoCritica")
CRITICA_PYTHON = os.getenv("CRITICA_PYTHON", PYTHON_BIN)  # venv próprio da crítica
CRITICA_SCRIPT = os.getenv("CRITICA_SCRIPT", "main.py")

# Mapa periodo -> configuração do job.
#   script/cwd/python : o que rodar e onde
#   args              : argumentos de linha de comando
#   sync_json         : nome do JSON de rotinas a sincronizar do painel (None = não sincroniza)
#   parser            : formato de log/resumo ("proautomax" ou "critica")
JOBS = {
    "manha": {
        "script": SCRIPT_MANHA, "cwd": PROJECT_DIR, "python": PYTHON_BIN,
        "args": [], "sync_json": JSON_MANHA, "parser": "proautomax",
    },
    "tarde": {
        "script": SCRIPT_TARDE, "cwd": PROJECT_DIR, "python": PYTHON_BIN,
        "args": [], "sync_json": JSON_TARDE, "parser": "proautomax",
    },
    # Crítica: 1 ciclo por run (--runs 1). O intercalar da tarde vem da ORDEM
    # de enfileiramento na fila, não de encadeamento interno.
    "critica": {
        "script": CRITICA_SCRIPT, "cwd": CRITICA_DIR, "python": CRITICA_PYTHON,
        "args": ["--runs", "1"], "sync_json": None, "parser": "critica",
    },
}

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise SystemExit("❌ SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios no .env")

sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ─── Helpers ──────────────────────────────────────────────────────────────────
# Arquivo de log do agente (útil quando ele roda sem janela / escondido).
LOG_FILE = os.getenv("AGENT_LOG_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "agent.log"
)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_console(msg: str):
    linha = f"[agente {datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    # Sempre grava no arquivo (funciona mesmo sem console)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass
    # E imprime no console se ele existir (sob pythonw/oculto, stdout pode ser None)
    try:
        if sys.stdout:
            print(linha, flush=True)
    except Exception:
        pass


# ─── Buffer de logs (envia em lote pra não martelar o banco) ──────────────────
class BufferLogs:
    """Acumula linhas de log e descarrega em lote no Supabase."""

    def __init__(self, run_id: str, max_linhas: int = 15, max_segundos: float = 0.8):
        self.run_id = run_id
        self.max_linhas = max_linhas
        self.max_segundos = max_segundos
        self._buf = []
        self._ultimo_flush = time.time()
        self.ativo = True  # vira False quando a run some (cancelada/deletada)

    def desativar(self):
        """Para de gravar logs (run não existe mais) e descarta o que sobrou."""
        self.ativo = False
        self._buf = []

    def add(self, nivel: str, mensagem: str):
        if not self.ativo:
            return
        self._buf.append({"run_id": self.run_id, "nivel": nivel, "mensagem": mensagem})
        if len(self._buf) >= self.max_linhas or (time.time() - self._ultimo_flush) >= self.max_segundos:
            self.flush()

    def flush(self):
        if not self.ativo or not self._buf:
            return
        lote, self._buf = self._buf, []
        self._ultimo_flush = time.time()
        try:
            sb.table("run_logs").insert(lote).execute()
        except Exception as e:
            # FK 23503 = a run foi deletada no painel. Para de tentar gravar
            # (senão vira spam) e desativa o buffer.
            if "23503" in str(e) or "run_id_fkey" in str(e):
                self.desativar()
                log_console("run removida no painel — parando de gravar logs dela")
            else:
                log_console(f"⚠️ falha ao gravar log ({len(lote)} linhas): {e}")


# ─── Parsing das linhas vindas do robô ────────────────────────────────────────
# ProAutoMax: "asctime | LEVEL | message"
_RE_LINHA_PROAUTOMAX = re.compile(r"^.*?\|\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|\s*(.*)$")
# Crítica: "[HH:MM:SS] LEVEL nome.do.modulo: message"
_RE_LINHA_CRITICA = re.compile(
    r"^\[\d{1,2}:\d{2}:\d{2}\]\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+\S+:\s*(.*)$"
)


def parse_linha(linha: str, parser: str = "proautomax"):
    """Devolve (nivel, mensagem). Linhas fora do formato viram INFO cru."""
    linha = linha.rstrip("\n").rstrip("\r")
    regex = _RE_LINHA_CRITICA if parser == "critica" else _RE_LINHA_PROAUTOMAX
    m = regex.match(linha)
    if m:
        return m.group(1), m.group(2)
    return "INFO", linha


def _to_int(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s) or 0)


def _to_list(s: str):
    try:
        return ast.literal_eval(s.strip())
    except Exception:
        return []


def _resumo_vazio() -> dict:
    return {
        "salvas": [], "erros": [], "ignoradas": [],
        "qtd_salvas": 0, "qtd_erros": 0, "qtd_ignoradas": 0,
        "input_tokens": 0, "output_tokens": 0, "chamadas_api": 0,
        "custo_usd": 0.0, "custo_brl": 0.0, "duracao_log": None,
        "completou": False,
    }


def parse_resumo(mensagens: list[str], parser: str = "proautomax") -> dict:
    """Escolhe o parser certo conforme o job."""
    if parser == "critica":
        return _parse_resumo_critica(mensagens)
    return _parse_resumo_proautomax(mensagens)


def _parse_resumo_proautomax(mensagens: list[str]) -> dict:
    """
    Resumo do executor do ProAutoMax:
        ✅ Salvas com sucesso:  N  → [...]
        ❌ Com erro:            N → [...]
        ⏭️  Ignoradas:           N → [...]
        Tokens de entrada / saída / Chamadas / Custo estimado / Tempo total
    """
    texto = "\n".join(mensagens)
    res = _resumo_vazio()

    def busca_lista(rotulo):
        m = re.search(rotulo + r"\s*\d+\s*[→\->]+\s*(\[[^\]]*\])", texto)
        return _to_list(m.group(1)) if m else []

    res["salvas"]    = busca_lista(r"Salvas com sucesso:")
    res["erros"]     = busca_lista(r"Com erro:")
    res["ignoradas"] = busca_lista(r"Ignoradas:")
    res["qtd_salvas"]    = len(res["salvas"])
    res["qtd_erros"]     = len(res["erros"])
    res["qtd_ignoradas"] = len(res["ignoradas"])

    if m := re.search(r"Tokens de entrada\s*:\s*([\d.,]+)", texto):
        res["input_tokens"] = _to_int(m.group(1))
    if m := re.search(r"Tokens de sa[íi]da\s*:\s*([\d.,]+)", texto):
        res["output_tokens"] = _to_int(m.group(1))
    if m := re.search(r"Chamadas realizadas\s*:\s*(\d+)", texto):
        res["chamadas_api"] = int(m.group(1))
    if m := re.search(r"Custo estimado\s*:\s*\$([\d.]+)\s*USD\s*\(~R\$\s*([\d.]+)\)", texto):
        res["custo_usd"] = float(m.group(1))
        res["custo_brl"] = float(m.group(2))
    if m := re.search(r"Tempo total de execu[çc][ãa]o:\s*(\d+)\s*s", texto):
        res["duracao_log"] = int(m.group(1))

    res["completou"] = "RESUMO DA EXECU" in texto
    return res


def _parse_resumo_critica(mensagens: list[str]) -> dict:
    """
    Resumo do executor da Crítica:
        RESUMO: X sucesso(s), Y sem pedidos, Z falha(s)
    Mapeia: salvas=X, ignoradas(sem pedidos)=Y, erros=Z. Sem custo de IA.
    """
    texto = "\n".join(mensagens)
    res = _resumo_vazio()

    m = re.search(
        r"RESUMO:\s*(\d+)\s*sucesso.*?,\s*(\d+)\s*sem pedidos.*?,\s*(\d+)\s*falha",
        texto,
        re.IGNORECASE,
    )
    if m:
        res["qtd_salvas"]    = int(m.group(1))
        res["qtd_ignoradas"] = int(m.group(2))
        res["qtd_erros"]     = int(m.group(3))
        res["completou"]     = True
    return res


# ─── Sincroniza o JSON de rotinas a partir do painel ─────────────────────────
def sincronizar_rotinas_json(periodo: str, emite, rotinas_filtro=None) -> bool:
    """
    Regenera o JSON de rotinas (na raiz do projeto) a partir da tabela 'routines',
    fazendo o painel ser a fonte da verdade dos toggles ativo/inativo.

    rotinas_filtro:
      - None  -> comportamento normal: usa TODAS as rotinas do período, cada uma
                 com o seu ativo da tabela (a manhã/tarde "completa").
      - lista de códigos -> run CUSTOMIZADA: gera o JSON só com essas rotinas,
                 TODAS marcadas como ativo=True (roda exatamente o subconjunto),
                 sem tocar nos flags globais da tabela.

    Segurança:
      - Faz backup do JSON atual em <arquivo>.bak antes de sobrescrever.
      - Se não sobrar nenhuma rotina, NÃO toca no arquivo (evita rodar zero
        rotina por engano) e mantém o que já está no disco.

    Retorna True se gravou o arquivo, False se manteve o do disco.
    """
    nome_json = (JOBS.get(periodo) or {}).get("sync_json")
    if not nome_json:
        return False

    try:
        rows = (
            sb.table("routines")
            .select("*")
            .eq("periodo", periodo)
            .order("ordem", desc=False)
            .execute()
            .data
        ) or []
    except Exception as e:
        emite("WARNING", f"Não consegui ler 'routines' ({e}). Usando o {nome_json} do disco.")
        return False

    if not rows:
        emite("WARNING", f"Nenhuma rotina '{periodo}' na tabela — mantendo o {nome_json} atual do disco.")
        return False

    # Run customizada: filtra pelos códigos pedidos e força ativo=True
    custom = isinstance(rotinas_filtro, list) and len(rotinas_filtro) > 0
    if custom:
        alvo = {str(c) for c in rotinas_filtro}
        rows = [r for r in rows if str(r["codigo"]) in alvo]
        if not rows:
            emite("WARNING",
                  f"Nenhuma das rotinas pedidas {sorted(alvo)} existe no período "
                  f"'{periodo}' — mantendo o {nome_json} do disco.")
            return False

    execucao = []
    for r in rows:
        params = dict(r.get("params") or {})
        ext = params.pop("extensao_download", None)   # volta pro topo (formato original)
        item = {
            "codigo": r["codigo"],
            "params": params,
            "destino": r.get("destino") or "",
            "nome": r.get("nome") or f"{r['codigo']}.csv",
            "descricao": r.get("descricao") or r["codigo"],
            # custom => tudo ativo; normal => respeita o flag da tabela
            "ativo": True if custom else bool(r.get("ativo")),
        }
        if ext:
            item["extensao_download"] = ext
        execucao.append(item)

    caminho = os.path.join(PROJECT_DIR, nome_json)

    # Backup do arquivo atual
    try:
        if os.path.exists(caminho):
            shutil.copy2(caminho, caminho + ".bak")
    except Exception as e:
        emite("WARNING", f"Falha ao fazer backup de {nome_json}: {e}")

    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"execucao": execucao}, f, ensure_ascii=False, indent=4)
    except Exception as e:
        emite("ERROR", f"Falha ao gravar {nome_json}: {e}")
        return False

    if custom:
        codigos = [it["codigo"] for it in execucao]
        emite("INFO", f"🔧 {nome_json} CUSTOM — {len(codigos)} rotina(s): {codigos}")
    else:
        ativas = sum(1 for it in execucao if it["ativo"])
        emite("INFO", f"🔄 {nome_json} sincronizado do painel — {ativas} ativa(s) de {len(execucao)}")
    return True


# ─── Execução de uma run ──────────────────────────────────────────────────────
def claim_proxima_run():
    """Pega a run 'queued' mais antiga e a marca como 'running' (claim atômico)."""
    sel = (
        sb.table("runs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not sel.data:
        return None

    run = sel.data[0]
    upd = (
        sb.table("runs")
        .update({"status": "running", "started_at": agora_iso()})
        .eq("id", run["id"])
        .eq("status", "queued")  # só vence se ninguém pegou antes
        .execute()
    )
    if not upd.data:
        return None  # outro processo reivindicou — ignora
    return upd.data[0]


def _matar_processo(proc):
    """Mata o subprocesso e toda a sua árvore (python + msedgedriver + Edge)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
            )
        else:
            proc.terminate()
    except Exception as e:
        log_console(f"⚠️ falha ao matar processo: {e}")


def executar_run(run: dict):
    run_id  = run["id"]
    periodo = (run.get("periodo") or "manha").lower()
    job     = JOBS.get(periodo)

    buf = BufferLogs(run_id)
    mensagens = []

    def emite(nivel, msg):
        mensagens.append(msg)
        buf.add(nivel, msg)

    parser = (job or {}).get("parser", "proautomax")

    if not job:
        log_console(f"▶ run {run_id}: período/job inválido '{periodo}'")
        emite("ERROR", f"Período/job inválido: {periodo}")
        buf.flush()
        finalizar_run(run_id, run, "error", parse_resumo(mensagens, parser))
        return

    script = job["script"]
    cwd    = job["cwd"]
    python = job["python"]
    args   = job.get("args", [])

    log_console(f"▶ iniciando run {run_id} (periodo={periodo}, script={script}, cwd={cwd})")
    emite("INFO", f"🤖 Agente iniciou a execução ({periodo}) — {script} {' '.join(args)}".strip())

    caminho_script = os.path.join(cwd, script)
    if not os.path.exists(caminho_script):
        emite("ERROR", f"Script não encontrado: {caminho_script}")
        buf.flush()
        finalizar_run(run_id, run, "error", parse_resumo(mensagens, parser))
        return

    # Sincroniza o rotinas.json a partir do painel (só jobs que usam a tabela routines)
    if SYNC_ROTINAS_JSON and job.get("sync_json"):
        rotinas_filtro = run.get("rotinas")  # None = completo | lista = custom
        sincronizar_rotinas_json(periodo, emite, rotinas_filtro)
        buf.flush()

    # Força UTF-8 no subprocesso para os emojis/acentos do log não quebrarem
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    rc = None
    estado = {"cancelado": False, "deletado": False}
    parar_watcher = threading.Event()

    # No Windows, evita que o subprocesso pisque uma janela de console
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def watcher(p):
        # A cada 3s, confere se a run ainda existe no banco.
        # Se o painel deletou a linha (botão "Parar execução"), mata o robô.
        while not parar_watcher.wait(3):
            try:
                existe = sb.table("runs").select("id").eq("id", run_id).execute().data
            except Exception:
                continue  # erro de rede momentâneo — tenta de novo
            if not existe:
                estado["cancelado"] = True
                estado["deletado"] = True
                buf.desativar()  # para de tentar gravar log da run que sumiu
                log_console(f"🛑 run {run_id} foi removida no painel — interrompendo o robô")
                _matar_processo(p)
                return

    try:
        proc = subprocess.Popen(
            [python, script, *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # junta stderr (traceback) no mesmo fluxo
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,                  # line-buffered
            env=env,
            creationflags=creationflags,
        )

        threading.Thread(target=watcher, args=(proc,), daemon=True).start()

        for linha in proc.stdout:
            nivel, msg = parse_linha(linha, parser)
            if msg.strip():
                emite(nivel, msg)

        rc = proc.wait()
    except Exception as e:
        emite("ERROR", f"Falha ao rodar o subprocesso: {e}")
    finally:
        parar_watcher.set()  # encerra o vigia

    buf.flush()

    # Cancelada via painel (linha deletada): a run não existe mais — não há o
    # que atualizar. Só registra no console e segue.
    if estado["cancelado"]:
        log_console(f"⏹ run {run_id} interrompida pelo usuário (exit code {rc})")
        return

    resumo = parse_resumo(mensagens, parser)

    # Decide o status final (usa contagens + flag de "completou")
    if rc not in (0, None) and not resumo["completou"]:
        status = "error"
    elif resumo["qtd_erros"] > 0:
        status = "partial" if resumo["qtd_salvas"] > 0 else "error"
    else:
        status = "success"

    emite("INFO", f"🏁 Agente finalizou — status={status} (exit code {rc})")
    buf.flush()

    finalizar_run(run_id, run, status, resumo)
    log_console(f"✔ run {run_id} finalizada: {status}")


def finalizar_run(run_id: str, run: dict, status: str, resumo: dict):
    fim = datetime.now(timezone.utc)
    try:
        inicio = datetime.fromisoformat((run.get("started_at") or agora_iso()).replace("Z", "+00:00"))
        duracao = int((fim - inicio).total_seconds())
    except Exception:
        duracao = resumo.get("duracao_log") or 0

    payload = {
        "status": status,
        "finished_at": fim.isoformat(),
        "duracao_segundos": duracao,
        "salvas": resumo["salvas"],
        "erros": resumo["erros"],
        "ignoradas": resumo["ignoradas"],
        "qtd_salvas": resumo["qtd_salvas"],
        "qtd_erros": resumo["qtd_erros"],
        "qtd_ignoradas": resumo["qtd_ignoradas"],
        "input_tokens": resumo["input_tokens"],
        "output_tokens": resumo["output_tokens"],
        "chamadas_api": resumo["chamadas_api"],
        "custo_usd": resumo["custo_usd"],
        "custo_brl": resumo["custo_brl"],
    }
    try:
        sb.table("runs").update(payload).eq("id", run_id).execute()
    except Exception as e:
        log_console(f"⚠️ falha ao finalizar run {run_id}: {e}")


# ─── Agendador interno (opcional) ─────────────────────────────────────────────
# Convenção de dias_semana: 1=Seg, 2=Ter, 3=Qua, 4=Qui, 5=Sex, 6=Sáb, 7=Dom
# (bate com o painel). Python weekday(): Seg=0 ... Dom=6  ->  +1
def _enfileirar(periodo: str, rotinas=None):
    payload = {"periodo": periodo, "status": "queued", "origem": "agendado"}
    if isinstance(rotinas, list) and rotinas:
        payload["rotinas"] = rotinas
    try:
        sb.table("runs").insert(payload).execute()
        extra = f" (custom: {rotinas})" if rotinas else ""
        log_console(f"⏰ agendamento disparou — run '{periodo}' enfileirada{extra}")
    except Exception as e:
        log_console(f"⚠️ falha ao enfileirar agendamento: {e}")


def _ja_existe_agendada(periodo, ini, fim) -> bool:
    """
    Já existe uma run 'agendado' criada na janela [ini, fim]?
    Se `periodo` for None, considera qualquer período (usado p/ sequências,
    que enfileiram vários períodos numa mesma janela).
    Serve de guarda contra disparo duplo se o agente reiniciar dentro da janela
    de tolerância (o set em memória se perde no restart; o banco não).
    ini/fim são datetimes locais (convertidos p/ UTC, pois created_at é UTC).
    """
    try:
        q = (
            sb.table("runs")
            .select("id")
            .eq("origem", "agendado")
            .gte("created_at", ini.astimezone(timezone.utc).isoformat())
            .lte("created_at", fim.astimezone(timezone.utc).isoformat())
        )
        if periodo is not None:
            q = q.eq("periodo", periodo)
        return bool(q.limit(1).execute().data)
    except Exception:
        return False  # na dúvida não bloqueia (o set em memória ainda protege)


def loop_agendador():
    disparados: set[str] = set()
    log_console(f"⏰ agendador interno ATIVO (tolerância de {AGENDADOR_TOLERANCIA_MIN} min)")
    grace = timedelta(minutes=AGENDADOR_TOLERANCIA_MIN)

    while True:
        try:
            ags = sb.table("schedules").select("*").eq("ativo", True).execute().data or []
            agora = datetime.now()
            hoje = date.today().isoformat()
            dia_atual = agora.weekday() + 1  # 1..7

            # limpa marcações de dias anteriores
            for chave in list(disparados):
                if not chave.startswith(hoje):
                    disparados.discard(chave)

            for ag in ags:
                dias = ag.get("dias_semana") or []
                if dia_atual not in dias:
                    continue

                horario = (ag.get("horario") or "")[:5]  # "HH:MM:SS" -> "HH:MM"
                try:
                    hh, mm = (int(x) for x in horario.split(":")[:2])
                except Exception:
                    continue

                agendado_dt = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)

                # Dispara se o horário já chegou e ainda estamos dentro da tolerância
                if not (agendado_dt <= agora <= agendado_dt + grace):
                    continue

                chave = f"{hoje}:{ag['id']}"
                if chave in disparados:
                    continue  # já tratamos nessa sessão do agente

                janela_fim = agendado_dt + grace + timedelta(minutes=2)
                sequencia = ag.get("sequencia")

                if isinstance(sequencia, list) and sequencia:
                    # Agendamento em SEQUÊNCIA: enfileira a lista inteira, em ordem.
                    # Um horário só dispara T,C,T,C... — a ordem de created_at
                    # (inserts sequenciais) garante que o agente rode nessa ordem.
                    if _ja_existe_agendada(None, agendado_dt, janela_fim):
                        disparados.add(chave)
                        continue
                    disparados.add(chave)
                    log_console(f"⏰ sequência disparou ({len(sequencia)} itens): {sequencia}")
                    for item in sequencia:
                        _enfileirar(str(item).lower())
                else:
                    periodo = (ag.get("periodo") or "manha").lower()
                    rotinas = ag.get("rotinas")  # None = completo | lista = custom
                    if _ja_existe_agendada(periodo, agendado_dt, janela_fim):
                        disparados.add(chave)
                        continue
                    disparados.add(chave)
                    _enfileirar(periodo, rotinas if isinstance(rotinas, list) and rotinas else None)
        except Exception as e:
            log_console(f"⚠️ erro no agendador: {e}")
        time.sleep(20)


# ─── Loop principal ───────────────────────────────────────────────────────────
def main():
    log_console("=" * 50)
    log_console("ProAutoMax — Agente da VM iniciado")
    log_console(f"  Projeto : {PROJECT_DIR}")
    log_console(f"  Python  : {PYTHON_BIN}")
    log_console(f"  Poll    : {POLL_SECONDS}s | Agendador: {'ON' if ENABLE_SCHEDULER else 'OFF'}")
    log_console("=" * 50)

    if ENABLE_SCHEDULER:
        threading.Thread(target=loop_agendador, daemon=True).start()

    while True:
        try:
            run = claim_proxima_run()
            if run:
                executar_run(run)        # bloqueante — uma run por vez
            else:
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log_console("encerrando (Ctrl+C)")
            break
        except Exception as e:
            log_console(f"⚠️ erro no loop principal: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()