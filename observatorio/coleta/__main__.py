"""Linha de comando da coleta.

    python -m observatorio.coleta coletar    --inicio 2026-01-01 [--fim AAAA-MM-DD] [--fonte auniao] [--limite N]
    python -m observatorio.coleta inventario --inicio 2026-01-01 [--fim AAAA-MM-DD]
    python -m observatorio.coleta importar ARQUIVO.pdf --data AAAA-MM-DD [--url URL_OFICIAL]
    python -m observatorio.coleta conferir

Códigos de saída: 0 = concluído; 3 = concluído com pendências; 2 = erro de uso ou arquivo recusado.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import coletor, inventario
from .fontes import FONTES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.coleta", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["coletar", "inventario", "importar", "conferir"])
    ap.add_argument("arquivo", nargs="?")
    ap.add_argument("--dados", default="dados", help="pasta local (fora do Git) com o banco e o acervo")
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=date.today())
    ap.add_argument("--fonte", action="append", choices=sorted(FONTES))
    ap.add_argument("--limite", type=int, help="máximo de downloads por fonte nesta execução")
    ap.add_argument("--reverificar", action="store_true", help="baixa de novo o que já existe e compara")
    ap.add_argument("--data", type=date.fromisoformat)
    ap.add_argument("--url")
    a = ap.parse_args(argv)

    pasta = Path(a.dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    siglas = a.fonte or ["auniao", "cge"]
    try:
        if a.comando == "coletar":
            resumo = coletor.coletar([FONTES[s]() for s in siglas], banco, acervo, a.inicio, a.fim,
                                     limite=a.limite, reverificar=a.reverificar)
            print(json.dumps(resumo, ensure_ascii=False, indent=2))
            return 3 if coletor.houve_pendencia(resumo) else 0
        if a.comando == "inventario":
            linhas = inventario.cobertura(banco, a.inicio, a.fim, siglas)
            print(json.dumps({"totais": inventario.totais(linhas), "dias": linhas}, ensure_ascii=False, indent=2))
            return 0
        if a.comando == "importar":
            if not a.arquivo or not a.data:
                ap.error("importar exige ARQUIVO e --data")
            origem = Path(a.arquivo)
            resultado = coletor.importar_manual(banco, acervo, origem.read_bytes(), a.data,
                                                a.url or f"manual:{origem.name}", origem.name)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return 0 if resultado["aceito"] else 2
        corrompidos = [x["sha256"] for x in banco.arquivos() if not acervo.conferir(x["sha256"])]
        print(json.dumps({"arquivos": len(banco.arquivos()), "corrompidos_ou_ausentes": corrompidos}, indent=2))
        return 3 if corrompidos else 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
