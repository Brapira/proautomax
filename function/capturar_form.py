"""
Captura o que o NAVEGADOR enviaria no form1 da rotina, logo antes do botão
que gera o relatório — pra montar/conferir a versão HTTP (promax_http/).

Ligue com CAPTURAR_FORM=1 no .env e rode o robô normalmente (main.py).
Cada rotina gera promax_http/capturas/<codigo>.json com os campos na ordem.
Não altera o comportamento do robô: se a captura falhar, só loga.
"""

import json
import logging
import os
import re

PASTA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "promax_http", "capturas")

# Funções JS que disparam o envio do formulário nas rotinas
_GATILHOS = re.compile(r"\b(Visualizar|GerarCsv|GerarExcel|GeraPlanilha)\s*\(")

# Serializa form1 com as regras de envio do navegador. Escrito em JS antigo
# (a página roda em modo IE7: sem JSON, sem forEach).
_JS_SERIALIZAR = """
var f = document.forms['form1'] || document.forms[0];
if (!f) { return null; }
var r = [];
for (var i = 0; i < f.elements.length; i++) {
    var e = f.elements[i];
    if (!e.name || e.disabled) { continue; }
    var t = (e.type || '').toLowerCase();
    if (t == 'button' || t == 'submit' || t == 'reset' || t == 'image' || t == 'file') { continue; }
    if ((t == 'checkbox' || t == 'radio') && !e.checked) { continue; }
    if (e.tagName == 'SELECT') {
        for (var j = 0; j < e.options.length; j++) {
            if (e.options[j].selected) { r.push([e.name, e.options[j].value]); }
        }
        continue;
    }
    r.push([e.name, e.value]);
}
return r;
"""


def instalar(driver, codigo_fn):
    """
    Envolve driver.execute_script: antes de um script que chama Visualizar()/
    GerarCsv()/..., salva o formulário. `codigo_fn()` devolve o código da rotina atual.
    """
    # Lido aqui (não no import): o main.py importa o executor antes do load_dotenv()
    if os.getenv("CAPTURAR_FORM", "").lower() not in ("1", "true", "sim"):
        return
    os.makedirs(PASTA, exist_ok=True)
    original = driver.execute_script

    def execute_script(script, *args):
        if isinstance(script, str) and _GATILHOS.search(script):
            try:
                campos = original(_JS_SERIALIZAR)
                if campos is not None:
                    gatilho = _GATILHOS.search(script).group(1)
                    caminho = os.path.join(PASTA, f"{codigo_fn()}.json")
                    with open(caminho, "w", encoding="utf-8") as f:
                        json.dump({"gatilho": gatilho, "campos": campos}, f, ensure_ascii=False, indent=1)
                    logging.info(f"📸 Formulário capturado ({len(campos)} campos) → {caminho}")
            except Exception as e:
                logging.warning(f"📸 Falha ao capturar formulário: {e}")
        return original(script, *args)

    driver.execute_script = execute_script
    logging.info("📸 Captura de formulários ATIVA (CAPTURAR_FORM=1)")
