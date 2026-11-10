"""Aplica a classificação GEDIV aos arquivos já lidos e grava os candidatos no banco.

Nada do que é gravado aqui entra nos indicadores: todo registro nasce PENDENTE e só a
revisão humana (observatorio.revisao) pode torná-lo CONFERIDO.
"""
from __future__ import annotations

import json

from ...nucleo.banco import Banco
from . import catalogo as C
from .classificador import classificar

GERENCIA = "GEDIV"


def classificar_pendentes(banco: Banco, refazer: bool = False) -> dict:
    """Classifica os arquivos lidos ainda não classificados com a versão atual das regras."""
    if refazer:
        fila = [l["sha256"] for l in banco.leituras() if l["situacao"] != "ERRO"]
    else:
        fila = [l["sha256"] for l in banco.arquivos_sem_classificacao(GERENCIA, C.VERSAO_REGRAS)]
    resumo = {"arquivos": 0, "atos": 0, "decisoes": 0, "eventos": 0, "outras": 0, "descartados": 0,
              "preservadas_por_revisao": 0}
    for sha in fila:
        paginas = banco.paginas(sha)
        resultado = classificar([(p["numero"], p["texto"]) for p in paginas], sha)
        ruins = [p["numero"] for p in paginas if p["qualidade"] not in ("OK", "VAZIA")]
        if ruins:
            resultado.pendencias.append(
                f"páginas com leitura pendente ou de baixa confiança: {', '.join(map(str, ruins))}; pode haver atos não extraídos")
        if any(p["metodo"] != "TEXTO" for p in paginas):
            resultado.pendencias.append("há páginas lidas por OCR; conferir página e colunas no PDF")
        parte = banco.gravar_classificacao(GERENCIA, sha, C.VERSAO_REGRAS, banco.data_do_arquivo(sha), resultado)
        resumo["arquivos"] += 1
        for chave in parte:
            resumo[chave] += parte[chave]
    resumo["vinculos_sugeridos"] = sugerir_vinculos(banco)
    return resumo


def sugerir_vinculos(banco: Banco) -> int:
    """Propõe o ato original de cada evento de alteração quando a correspondência é única.

    É apenas uma SUGESTÃO para o revisor: o evento não conta em REFEITOS nem em TORNADOS SEM EFEITO
    enquanto o vínculo não for validado por uma pessoa. Sem correspondência inequívoca (nenhum ato,
    ou mais de um, com o número citado), o evento permanece PENDENTE_VINCULACAO.
    """
    sugeridos = 0
    eventos = banco.con.execute("SELECT * FROM evento WHERE estado = 'PENDENTE_VINCULACAO' AND gerencia = ?", (GERENCIA,)).fetchall()
    for evento in eventos:
        candidatos = set()
        for numero in json.loads(evento["resenhas_citadas"] or "[]"):
            for ato in banco.con.execute(
                    "SELECT id FROM ato WHERE gerencia = ? AND tipo = 'RESENHA' AND natureza = 'ORIGINAL' AND numero = ? "
                    "AND id <> COALESCE(?, '') AND (data_publicacao IS NULL OR ? IS NULL OR data_publicacao <= ?)",
                    (GERENCIA, numero, evento["ato_id"], evento["data_publicacao"], evento["data_publicacao"])):
                candidatos.add(ato["id"])
        if len(candidatos) == 1:
            with banco.con:
                banco.con.execute(
                    "UPDATE evento SET ato_sugerido_id = ?, estado = 'SUGERIDO', fundamento = ? WHERE id = ?",
                    (candidatos.pop(), "número de resenha citado no ato modificador; ato original único com esse número na base",
                     evento["id"]))
            sugeridos += 1
    return sugeridos


def situacao(banco: Banco) -> dict:
    um = lambda sql: banco.con.execute(sql).fetchone()[0]
    return {
        "versao_regras": C.VERSAO_REGRAS,
        "arquivos_classificados": um("SELECT COUNT(*) FROM classificacao WHERE gerencia = 'GEDIV'"),
        "na_fila": len(banco.arquivos_sem_classificacao(GERENCIA, C.VERSAO_REGRAS)),
        "atos": um("SELECT COUNT(*) FROM ato WHERE gerencia = 'GEDIV'"),
        "decisoes": {l[0]: l[1] for l in banco.con.execute("SELECT validacao, COUNT(*) FROM decisao GROUP BY validacao")},
        "eventos": {l[0]: l[1] for l in banco.con.execute("SELECT estado, COUNT(*) FROM evento GROUP BY estado")},
        "outras_publicacoes": um("SELECT COUNT(*) FROM outra_publicacao WHERE gerencia = 'GEDIV'"),
    }
