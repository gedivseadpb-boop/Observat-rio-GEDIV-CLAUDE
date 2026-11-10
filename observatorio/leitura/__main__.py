"""Linha de comando da leitura.

    python -m observatorio.leitura processar [--limite N]   # lê os arquivos do acervo ainda não lidos
    python -m observatorio.leitura situacao                 # resumo do que já foi lido

Requer a biblioteca pdfplumber (pip install -r requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import leitor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.leitura", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["processar", "situacao"])
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--limite", type=int)
    a = ap.parse_args(argv)
    pasta = Path(a.dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    try:
        if a.comando == "processar":
            contagem = leitor.processar(banco, acervo, a.limite)
            print(json.dumps(contagem, ensure_ascii=False, indent=2))
            return 3 if contagem["ERRO"] or contagem["na_fila"] else 0
        linhas = [{k: l[k] for k in ("sha256", "situacao", "paginas", "paginas_sem_texto", "numero_edicao",
                                     "data_edicao", "erro")} for l in banco.leituras()]
        print(json.dumps({"lidos": len(linhas), "na_fila": len(banco.arquivos_sem_leitura(leitor.VERSAO)),
                          "arquivos": linhas}, ensure_ascii=False, indent=2))
        return 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
