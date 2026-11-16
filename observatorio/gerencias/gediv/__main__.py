"""Painel Diário Oficial | GEDIV — classificação das edições lidas.

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
    ap.add_argument("comando", choices=["classificar", "complementar", "situacao", "catalogo"])
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--paddleocr-modelos", type=Path, help="complementar: diretório local dos pesos verificados")
    ap.add_argument("--paddleocr-python", default=sys.executable, help="Python do ambiente CPU opcional")
    ap.add_argument("--limite", type=int, help="complementar: máximo de arquivos")
    a = ap.parse_args(argv)
    if a.comando == "complementar" and (not a.paddleocr_modelos or (a.limite is not None and a.limite < 1)):
        ap.error("complementar exige --paddleocr-modelos e limite positivo, se informado")
    if a.comando == "catalogo":
        print(json.dumps(catalogo.como_dicionario(), ensure_ascii=False, indent=2))
        return 0
    banco = Banco(Path(a.dados) / "observatorio.sqlite3")
    try:
        if a.comando == "complementar":
            from ...nucleo.acervo import Acervo
            from .paddle_complementar import Config, complementar
            dados = complementar(banco, Acervo(Path(a.dados)/"acervo"),
                                 Config(a.paddleocr_modelos, a.paddleocr_python), a.limite)
        else:
            dados = processo.classificar_pendentes(banco, a.refazer) if a.comando == "classificar" else processo.situacao(banco)
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 3 if a.comando == "complementar" and (dados["recuperados"] or dados["sinalizados"] or dados["falhas"]) else 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
