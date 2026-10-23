"""
Contas do Promax usadas pelo modo HTTP.

O Promax aceita UMA sessão por usuário (um novo login derruba o anterior), então
cada trabalhador paralelo precisa da sua conta — e nenhuma deve ser a do robô
Selenium (PROMAX_USER), senão um derruba o outro.

.env:
    PROMAX_HTTP_CONTAS=Robo,Isac
    PROMAX_HTTP_SENHA_Robo=...
    PROMAX_HTTP_SENHA_Isac=...

Sem PROMAX_HTTP_CONTAS, cai pra PROMAX_USER/PROMAX_PASSWORD (uma conta só).
"""

import logging
import os


def contas_http() -> list[tuple[str, str]]:
    nomes = [n.strip() for n in os.getenv("PROMAX_HTTP_CONTAS", "").split(",") if n.strip()]
    if not nomes:
        logging.warning("⚠️ PROMAX_HTTP_CONTAS não encontrado no .env do projeto — usando só PROMAX_USER "
                        f"({os.getenv('PROMAX_USER')}), sem paralelo")
        return [(os.environ["PROMAX_USER"], os.environ["PROMAX_PASSWORD"])]

    contas = []
    for nome in nomes:
        senha = os.getenv(f"PROMAX_HTTP_SENHA_{nome}")
        if not senha:
            raise ValueError(f"Conta HTTP '{nome}' sem senha: defina PROMAX_HTTP_SENHA_{nome} no .env")
        contas.append((nome, senha))
    return contas
