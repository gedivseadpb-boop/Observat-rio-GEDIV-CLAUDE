"""Painel Diário Oficial | GEDIV — servidor do dashboard.

    python -m observatorio.web                      # http://127.0.0.1:8000
    python -m observatorio.web --porta 8080 --dados dados

A credencial da gerência vem da variável de ambiente GEDIV_TOKEN_GERENCIA (16 caracteres ou mais).
Sem ela, o servidor gera uma credencial aleatória a cada inicialização e a mostra somente no terminal.
Para acesso por outras máquinas use --endereco 0.0.0.0 APENAS atrás de HTTPS (proxy institucional).
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys

from .. import NOME
from .servidor import criar_servidor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.web", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--endereco", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--origem-admin", action="append", default=[],
                    help="endereço de origem do painel de administração autorizado a chamar a API (ex.: "
                         "https://gedivseadpb-boop.github.io); repita para mais de um. Também: GEDIV_ORIGENS_ADMIN")
    a = ap.parse_args(argv)
    origens = a.origem_admin + [o.strip() for o in os.environ.get("GEDIV_ORIGENS_ADMIN", "").split(",") if o.strip()]
    token = os.environ.get("GEDIV_TOKEN_GERENCIA", "")
    gerado = not token
    if gerado:
        token = secrets.token_urlsafe(24)
    servidor = criar_servidor(a.dados, token, a.endereco, a.porta, origens)
    print(f"{NOME} — http://{a.endereco}:{servidor.server_address[1]}", flush=True)
    if origens:
        print("Painel de administração autorizado em: " + ", ".join(origens), flush=True)
    if gerado:
        print(f"Credencial da gerência (válida só nesta execução): {token}", flush=True)
    else:
        print("Credencial da gerência: definida por GEDIV_TOKEN_GERENCIA.", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
