"""
Teste da prova de conceito HTTP com a rotina 03.02.24 (a da captura).

Rodar da raiz do projeto:
    python -m poc_http.teste_030224 [pasta_saida]

Usa PROMAX_USER / PROMAX_PASSWORD do .env (os mesmos do main.py).
Opcional: PROMAX_UNIDADE (padrão: a primeira unidade da lista).
Não mexe no fluxo atual — só baixa o CSV e salva na pasta indicada.
"""

import logging
import os
import sys
import time
from datetime import date

from dotenv import load_dotenv

from poc_http.promax_http import PromaxHTTP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
load_dotenv()

# Mesmos campos que o navegador mandou na captura
PARAMETROS_030224 = {
    "visaoConsolidadora": "", "opcaoRel": "03", "setoresInativos": "S", "converte": "H",
    "resumoVisao": "N", "selecionouROTA": "S", "resumo": "S",
    "idVisaoMultiCdd": "C", "idSelecaoMultiCdd": "T",
    "dataInicial": "01/01/2000", "dataFinal": date.today().strftime("%d/%m/%Y"),
    "campoInicial": "0", "campoFinal": "999999", "nrRoadInicial": "0", "nrRoadFinal": "99",
    "classeInicial": "", "classeFinal": "z",
}


def main():
    saida = sys.argv[1] if len(sys.argv) > 1 else "poc_http/saida"
    os.makedirs(saida, exist_ok=True)

    inicio = time.time()
    promax = PromaxHTTP(os.environ["PROMAX_USER"], os.environ["PROMAX_PASSWORD"],
                        unidade=os.getenv("PROMAX_UNIDADE"))
    promax.login()
    conteudo = promax.baixar_csv("030224000000", PARAMETROS_030224)

    caminho = os.path.join(saida, "030224.csv")
    with open(caminho, "wb") as f:
        f.write(conteudo)
    logging.info(f"💾 Salvo em {caminho} — total {time.time() - inicio:.1f}s")


if __name__ == "__main__":
    main()
