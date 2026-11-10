"""Painel de Publicações DOE-PB GEDIV — classificação das edições lidas.

    python -m observatorio.gerencias.gediv classificar            # classifica o que ainda não foi classificado
    python -m observatorio.gerencias.gediv classificar --refazer  # reclassifica tudo, preservando o que já foi revisado
    python -m observatorio.gerencias.gediv situacao
    python -m observatorio.gerencias.gediv catalogo               # dicionário de eixos, grupos e subcategorias

Todo registro produzido é CANDIDATO e fica pendente até a revisão humana.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...nucleo.banco import Banco
from . import catalogo, processo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.gerencias.gediv", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["classificar", "situacao", "catalogo"])
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args(argv)
    if a.comando == "catalogo":
        print(json.dumps(catalogo.como_dicionario(), ensure_ascii=False, indent=2))
        return 0
    banco = Banco(Path(a.dados) / "observatorio.sqlite3")
    try:
        dados = processo.classificar_pendentes(banco, a.refazer) if a.comando == "classificar" else processo.situacao(banco)
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
