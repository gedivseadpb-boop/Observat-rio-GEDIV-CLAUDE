"""Painel de Publicações DOE-PB GEDIV — fluxo completo.

    python -m observatorio.operacao executar PASTA_OU_ARQUIVO.pdf [--data AAAA-MM-DD] [--url URL_OFICIAL]
        importa o(s) PDF(s), lê (texto e OCR) e classifica; os registros ficam PENDENTES de revisão
    python -m observatorio.operacao executar          # sem origem: lê e classifica o que já está no acervo
    python -m observatorio.operacao demonstracao --dados dados-demo
        cria uma base de DEMONSTRAÇÃO com documentos SINTÉTICOS (pessoas e processos fictícios)

Depois: python -m observatorio.web --dados PASTA
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import fluxo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.operacao", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["executar", "demonstracao"])
    ap.add_argument("origem", nargs="?")
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--data", type=date.fromisoformat)
    ap.add_argument("--url")
    a = ap.parse_args(argv)
    if a.comando == "demonstracao":
        from . import demonstracao
        resumo = demonstracao.criar(a.dados)
    else:
        resumo = fluxo.executar(a.dados, a.origem, a.data, a.url)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
