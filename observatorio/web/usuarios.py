"""Contas da gerência para o painel de administração (usuário e senha por pessoa).

    python -m observatorio.web.usuarios --dados dados criar maria.silva --nome "Maria da Silva"
    python -m observatorio.web.usuarios --dados dados senha maria.silva
    python -m observatorio.web.usuarios --dados dados desativar maria.silva
    python -m observatorio.web.usuarios --dados dados ativar maria.silva
    python -m observatorio.web.usuarios --dados dados listar

A senha é digitada sem aparecer na tela (duas vezes) e nunca é gravada em texto.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .contas import Contas


def _pedir_senha() -> str:
    senha = getpass.getpass("Senha (10 caracteres ou mais): ")
    if senha != getpass.getpass("Repita a senha: "):
        raise ValueError("as duas senhas não conferem")
    return senha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.web.usuarios", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", default="dados")
    sub = ap.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("criar"); c.add_argument("usuario"); c.add_argument("--nome", required=True)
    for nome in ("senha", "desativar", "ativar"):
        sub.add_parser(nome).add_argument("usuario")
    sub.add_parser("listar")
    a = ap.parse_args(argv)
    pasta = Path(a.dados)
    pasta.mkdir(parents=True, exist_ok=True)
    contas = Contas(pasta / "contas.sqlite3")
    try:
        if a.acao == "criar":
            contas.criar(a.usuario, a.nome, _pedir_senha())
            print(f"Conta criada: {a.usuario.lower()}")
        elif a.acao == "senha":
            contas.trocar_senha(a.usuario, _pedir_senha())
            print("Senha trocada; as sessões abertas foram encerradas.")
        elif a.acao in ("desativar", "ativar"):
            contas.definir_ativo(a.usuario, a.acao == "ativar")
            print(f"Conta {a.usuario}: {'ativa' if a.acao == 'ativar' else 'desativada (sessões encerradas)'}")
        else:
            for u in contas.listar():
                print(f"{u['usuario']:<24} {'ativa' if u['ativo'] else 'desativada':<11} {u['nome']}  (último acesso: {u['ultimo_acesso'] or '—'})")
    except ValueError as e:
        print(f"Não foi possível: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
