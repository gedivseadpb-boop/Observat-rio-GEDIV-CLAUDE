"""Linha de comando da coleta.

Sequência normal de uso (cada passo pode ser repetido e retomado):

    python -m observatorio.coleta descobrir --inicio 2026-01-01     # lê as listagens mensais
    python -m observatorio.coleta piloto --fonte auniao              # até 5 edições de datas diferentes
    python -m observatorio.coleta piloto --fonte cge
    python -m observatorio.coleta lote --fonte auniao                # 1 lote histórico de até 10
    python -m observatorio.coleta lote --fonte auniao --lotes 3 --pausa-entre-lotes 120
    python -m observatorio.coleta progresso                          # situação por mês e por fonte

Outros comandos:

    python -m observatorio.coleta inventario --inicio 2026-01-01     # cobertura dia a dia
    python -m observatorio.coleta importar ARQUIVO.pdf --data AAAA-MM-DD [--url URL_OFICIAL]
    python -m observatorio.coleta conferir                           # reconfere o SHA-256 do acervo

A carga histórica (comando "lote") só é liberada depois de um piloto aprovado em cada fonte oficial.
Códigos de saída: 0 = concluído; 3 = concluído com pendências; 2 = recusado ou erro de uso.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import coletor, inventario, lotes
from .fontes import FONTES

COMANDOS = ["descobrir", "piloto", "lote", "progresso", "inventario", "importar", "conferir"]


def _mostrar(dados) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.coleta", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=COMANDOS)
    ap.add_argument("arquivo", nargs="?")
    ap.add_argument("--dados", default="dados", help="pasta local (fora do Git) com o banco e o acervo")
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2026, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=date.today())
    ap.add_argument("--fonte", action="append", choices=sorted(FONTES))
    ap.add_argument("--refazer", action="store_true", help="descobrir: relê também os meses já varridos")
    ap.add_argument("--tamanho", type=int, help="publicações por lote (padrão: 5 no piloto, 10 no histórico)")
    ap.add_argument("--pausa", type=float, help="segundos entre downloads (padrão: 10 no piloto, 8 no histórico)")
    ap.add_argument("--lotes", type=int, default=1, help="quantidade de lotes históricos em sequência")
    ap.add_argument("--pausa-entre-lotes", type=float, default=120.0)
    ap.add_argument("--mes", help="lote: restringe a um mês (AAAA-MM)")
    ap.add_argument("--data", type=date.fromisoformat)
    ap.add_argument("--url")
    a = ap.parse_args(argv)

    pasta = Path(a.dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    siglas = a.fonte or sorted(FONTES)
    try:
        if a.comando == "descobrir":
            resultado = {}
            for sigla in siglas:
                fonte = FONTES[sigla]()
                resultado[sigla] = coletor.descobrir(fonte, banco, coletor.politica_da(fonte), a.inicio, a.fim, a.refazer)
            _mostrar(resultado)
            return 3 if any("erro" in v for lista in resultado.values() for v in lista) else 0

        if a.comando in ("piloto", "lote"):
            if not a.fonte or len(a.fonte) != 1:
                ap.error(f"{a.comando} exige exatamente uma --fonte")
            if a.tamanho is not None and not 1 <= a.tamanho <= (5 if a.comando == "piloto" else 10):
                ap.error("tamanho máximo: 5 no piloto e 10 no lote histórico")
            fonte = FONTES[a.fonte[0]]()
            base = lotes.PARAMETROS_PILOTO if a.comando == "piloto" else lotes.Parametros()
            parametros = lotes.Parametros(tamanho=a.tamanho or base.tamanho,
                                          pausa=a.pausa if a.pausa is not None else base.pausa,
                                          max_falhas_seguidas=base.max_falhas_seguidas)
            if a.comando == "piloto":
                resumos = [lotes.executar_lote(fonte, banco, acervo, lotes.PILOTO, parametros)]
            else:
                resumos = lotes.executar_sequencia(fonte, banco, acervo, a.lotes, a.pausa_entre_lotes,
                                                   parametros=parametros, mes=a.mes, fontes_exigidas=sorted(FONTES))
            _mostrar(resumos)
            ultimo = resumos[-1]
            if not ultimo["executado"]:
                return 0 if ultimo["motivo"] == "NADA_PENDENTE" else 2
            limpo = all(r["estado"] == "CONCLUIDO" and set(r["resultados"]) <= lotes.SUCESSOS for r in resumos)
            return 0 if limpo and ultimo["aprovado"] is not False else 3

        if a.comando == "progresso":
            _mostrar({
                "piloto_aprovado": {s: banco.piloto_aprovado(s) for s in sorted(FONTES)},
                "carga_historica_liberada": not lotes.fontes_sem_piloto(banco, sorted(FONTES)),
                "por_mes": [dict(linha) for linha in banco.progresso()],
                "varreduras_com_erro": [dict(v) for v in banco.varreduras() if v["erro"]],
                "lotes": [{k: l[k] for k in ("id", "fonte", "tipo", "estado", "aprovado", "iniciado_em", "concluido_em",
                                             "observacao")} for l in banco.lotes()],
            })
            return 0

        if a.comando == "inventario":
            linhas = inventario.cobertura(banco, a.inicio, a.fim, siglas)
            _mostrar({"totais": inventario.totais(linhas), "dias": linhas})
            return 0

        if a.comando == "importar":
            if not a.arquivo or not a.data:
                ap.error("importar exige ARQUIVO e --data")
            origem = Path(a.arquivo)
            resultado = coletor.importar_manual(banco, acervo, origem.read_bytes(), a.data,
                                                a.url or f"manual:{origem.name}", origem.name)
            _mostrar(resultado)
            return 0 if resultado["aceito"] else 2

        corrompidos = [x["sha256"] for x in banco.arquivos() if not acervo.conferir(x["sha256"])]
        _mostrar({"arquivos": len(banco.arquivos()), "corrompidos_ou_ausentes": corrompidos})
        return 3 if corrompidos else 0
    finally:
        banco.fechar()


if __name__ == "__main__":
    sys.exit(main())
