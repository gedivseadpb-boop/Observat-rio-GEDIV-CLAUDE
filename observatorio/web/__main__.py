"""Painel Diário Oficial | GEDIV — servidor do dashboard.

    python -m observatorio.web                      # http://127.0.0.1:8000
    python -m observatorio.web --porta 8080 --dados dados

A autenticação padrão em produção utiliza contas nominais individuais (`observatorio.web.usuarios` em `contas.sqlite3`).
A credencial técnica legada (`GEDIV_TOKEN_GERENCIA`, mínimo de 32 caracteres em produção) permanece DESABILITADA por
padrão e só é ativada mediante `--habilitar-token-tecnico` (ou `GEDIV_HABILITAR_TOKEN_TECNICO=1`).
Para acesso por outras máquinas use --endereco 0.0.0.0 APENAS atrás de HTTPS (proxy institucional).
"""
from __future__ import annotations

import argparse
import os
import sys

from .. import NOME
from .servidor import MIN_TOKEN_TECNICO_PRODUCAO, criar_servidor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.web", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--endereco", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--origem-admin", action="append", default=[],
                    help="endereço HTTPS de origem do painel de administração autorizado a chamar a API (ex.: "
                         "https://gedivseadpb-boop.github.io); repita para mais de um. Também: GEDIV_ORIGENS_ADMIN")
    ap.add_argument("--habilitar-token-tecnico", action="store_true",
                    help="habilita explicitamente o token técnico legado GEDIV_TOKEN_GERENCIA (exige >= 32 caracteres)")
    a = ap.parse_args(argv)
    origens = a.origem_admin + [o.strip() for o in os.environ.get("GEDIV_ORIGENS_ADMIN", "").split(",") if o.strip()]
    usar_token_legado = a.habilitar_token_tecnico or os.environ.get("GEDIV_HABILITAR_TOKEN_TECNICO") == "1"
    token: str | None = None
    if usar_token_legado:
        token = os.environ.get("GEDIV_TOKEN_GERENCIA", "").strip()
        if len(token) < MIN_TOKEN_TECNICO_PRODUCAO:
            raise ValueError(
                f"Quando habilitado, GEDIV_TOKEN_GERENCIA exige no mínimo {MIN_TOKEN_TECNICO_PRODUCAO} caracteres."
            )
    servidor = criar_servidor(a.dados, token, a.endereco, a.porta, origens, exigir_token_32=usar_token_legado)
    print(f"{NOME} — http://{a.endereco}:{servidor.server_address[1]}", flush=True)
    if origens:
        print("Painel de administração autorizado em: " + ", ".join(origens), flush=True)
    if usar_token_legado:
        print("Credencial técnica legada: HABILITADA explicitamente via GEDIV_TOKEN_GERENCIA (perfil gerencia).", flush=True)
    else:
        print("Credencial técnica legada: DESABILITADA por padrão (autenticação exclusiva por contas nominais).", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
