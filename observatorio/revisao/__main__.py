"""Painel de Publicações DOE-PB GEDIV — revisão pela linha de comando (a revisão normal é feita no painel web).

    python -m observatorio.revisao fila                                  # atos com decisões pendentes
    python -m observatorio.revisao ato ID --decisao CONFERIR --responsavel "Nome" \\
           --justificativa "Conferido no PDF oficial, p. 3" --confirme-fonte [--confirme-vinculo]
    python -m observatorio.revisao decisao ID --decisao REJEITAR --responsavel "Nome" --justificativa "..."
    python -m observatorio.revisao evento ID --decisao VINCULAR --ato-original ID --responsavel ... --confirme-fonte
    python -m observatorio.revisao trilha
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..nucleo.banco import Banco
from . import servico


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.revisao", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["fila", "ato", "decisao", "evento", "trilha"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--decisao", choices=[servico.CONFERIR, servico.REJEITAR, servico.REABRIR, servico.VINCULAR])
    ap.add_argument("--responsavel", default="")
    ap.add_argument("--justificativa", default="")
    ap.add_argument("--ato-original")
    ap.add_argument("--confirme-fonte", action="store_true")
    ap.add_argument("--confirme-vinculo", action="store_true")
    a = ap.parse_args(argv)
    banco = Banco(Path(a.dados) / "observatorio.sqlite3")
    try:
        if a.comando == "fila":
            linhas = banco.con.execute(
                "SELECT a.id, a.numero, a.data_publicacao, a.pagina, a.vinculo, a.eixo, a.modalidade, a.grupo, a.subcategoria, "
                "COUNT(d.id) AS pendentes FROM ato a JOIN decisao d ON d.ato_id = a.id AND d.validacao = 'PENDENTE' "
                "GROUP BY a.id ORDER BY a.data_publicacao, a.pagina").fetchall()
            print(json.dumps([dict(l) for l in linhas], ensure_ascii=False, indent=2))
            return 0
        if a.comando == "trilha":
            print(json.dumps([dict(l) for l in banco.trilha()], ensure_ascii=False, indent=2))
            return 0
        if not a.id or not a.decisao:
            ap.error("informe o ID e --decisao")
        try:
            if a.comando == "ato":
                r = servico.revisar_ato(banco, a.id, a.decisao, a.responsavel, a.justificativa, a.confirme_fonte, a.confirme_vinculo)
            elif a.comando == "decisao":
                r = servico.revisar_decisoes(banco, [a.id], a.decisao, a.responsavel, a.justificativa, a.confirme_fonte,
                                             a.confirme_vinculo)
            else:
                r = servico.revisar_evento(banco, a.id, a.decisao, a.responsavel, a.justificativa, a.ato_original, a.confirme_fonte)
        except servico.Recusada as e:
            print(f"Recusado: {e}", file=sys.stderr)
            return 2
        print(json.dumps(r, ensure_ascii=False))
        return 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
