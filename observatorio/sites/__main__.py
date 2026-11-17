"""Comandos administrativos reversíveis para publicações GEDIV.

Uso:
  python -m observatorio.sites verificar
  python -m observatorio.sites designar --vencedor SITE --secundario SITE
  python -m observatorio.sites preparar-desativacao --evidencia EVIDENCIA.json
  python -m observatorio.sites executar --plano PLANO --autorizacao AUTORIZACAO.json --evidencia EVIDENCIA.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .controle import Controle, Recusado, carregar_registro


def json_arquivo(valor):
    try:
        return json.loads(Path(valor).read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise Recusado("Não foi possível ler JSON de autorização/evidência: " + str(erro))


def main(argv=None):
    p = argparse.ArgumentParser(prog="observatorio.sites", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--registro", type=Path, default=Path("config/sites-gediv.json"))
    p.add_argument("--controle", type=Path, help="pasta privada local para backups, planos e diário")
    sub = p.add_subparsers(dest="acao", required=True)
    sub.add_parser("verificar")
    d = sub.add_parser("designar")
    d.add_argument("--vencedor", required=True)
    d.add_argument("--secundario", required=True)
    for nome in ("preparar-desativacao", "preparar-reativacao"):
        a = sub.add_parser(nome)
        a.add_argument("--evidencia", required=True, type=Path)
    e = sub.add_parser("executar")
    e.add_argument("--plano", required=True)
    e.add_argument("--autorizacao", required=True, type=Path)
    e.add_argument("--evidencia", required=True, type=Path)
    sub.add_parser("conciliar")
    args = p.parse_args(argv)
    try:
        controle = Controle(carregar_registro(args.registro), args.controle or Path("../gediv-sites-controle"))
        if args.acao == "verificar":
            resposta = controle.verificar()
        elif args.acao == "designar":
            resposta = controle.designar(args.vencedor, args.secundario)
        elif args.acao.startswith("preparar-"):
            operacao = "desativar" if args.acao.endswith("desativacao") else "reativar"
            resposta = controle.preparar(operacao, json_arquivo(args.evidencia))
        elif args.acao == "executar":
            resposta = controle.executar(args.plano, json_arquivo(args.autorizacao), json_arquivo(args.evidencia))
        else:
            resposta = controle.conciliar()
    except Recusado as erro:
        print(json.dumps({"ok": False, "mensagem": str(erro)}, ensure_ascii=False))
        return 3
    print(json.dumps({"ok": True, "resultado": resposta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
