"""Inventário da cobertura: o que foi listado, baixado e o que falta, dia a dia.

Um dia sem arquivo só é declarado SEM_PUBLICACAO_LISTADA quando as listagens
do mês foram lidas com sucesso em todas as fontes consultadas. Caso contrário
o dia fica NAO_VERIFICADO: ausência de evidência não é evidência de ausência.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..nucleo import banco as B


def cobertura(banco: B.Banco, inicio: date, fim: date, fontes: list[str]) -> list[dict]:
    varridos = {(v["fonte"], v["ano"], v["mes"]) for v in banco.varreduras() if v["erro"] is None}
    por_dia: dict[str, list] = {}
    for p in banco.publicacoes():
        if p["data_publicacao"]:
            por_dia.setdefault(p["data_publicacao"], []).append(p)
    linhas, dia = [], inicio
    while dia <= fim:
        pubs = por_dia.get(dia.isoformat(), [])
        baixadas = [p for p in pubs if p["estado"] == B.BAIXADA]
        verificado = all((f, dia.year, dia.month) in varridos for f in fontes)
        if not pubs:
            situacao = "SEM_PUBLICACAO_LISTADA" if verificado else "NAO_VERIFICADO"
        elif len(baixadas) == len(pubs):
            situacao = "COMPLETO"
        elif baixadas:
            situacao = "PARCIAL"
        else:
            situacao = "PENDENTE"
        fontes_do_dia = sorted({p["fonte"] for p in pubs})
        linhas.append({
            "data": dia.isoformat(),
            "dia_util": dia.weekday() < 5,
            "situacao": situacao,
            "listadas": len(pubs),
            "baixadas": len(baixadas),
            "arquivos_distintos": len({p["sha256"] for p in baixadas}),
            "fontes": fontes_do_dia,
            "so_em_uma_fonte": verificado and len(fontes) > 1 and len(fontes_do_dia) == 1 and fontes_do_dia[0] in fontes,
        })
        dia += timedelta(days=1)
    return linhas


def totais(linhas: list[dict]) -> dict:
    resultado: dict[str, int] = {}
    for linha in linhas:
        resultado[linha["situacao"]] = resultado.get(linha["situacao"], 0) + 1
    resultado["dias"] = len(linhas)
    resultado["divergencias_entre_fontes"] = sum(linha["so_em_uma_fonte"] for linha in linhas)
    return resultado
