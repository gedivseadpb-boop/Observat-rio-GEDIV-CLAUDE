"""Projeção do painel: os sete indicadores gerenciais, séries, tabela e cobertura.

Contrato dos indicadores (Especificação V3, seção 6):

| Cartão              | Unidade                                   | Data usada                      |
|---------------------|-------------------------------------------|---------------------------------|
| Processos           | processos distintos das decisões originais| publicação original             |
| Resenhas            | atos (resenhas) originais distintos       | publicação original             |
| Decisões            | decisões individuais originais            | publicação original             |
| Deferidos           | decisões originais com resultado deferido | publicação original             |
| Indeferidos         | decisões originais com resultado indeferido| publicação original            |
| Refeitos            | atos originais com evento VALIDADO de retificação, correção ou republicação | publicação do EVENTO |
| Tornados sem efeito | atos originais com evento VALIDADO de "sem efeito" | publicação do EVENTO   |

Só registros CONFERIDOS por revisão humana entram nos indicadores. O escopo "pendente" existe
apenas para a gerência acompanhar a fila, e é sempre rotulado como preliminar; nele, Refeitos e
Tornados sem efeito não são calculados. Os cartões não se somam entre si.
"""
from __future__ import annotations

import json
import unicodedata

from ..gerencias.gediv import catalogo as C
from ..nucleo.banco import Banco

GERENCIA_PERFIL, PUBLICO = "gerencia", "publico"
CARTOES = ("processos", "resenhas", "decisoes", "deferidos", "indeferidos", "refeitos", "sem_efeito")
ROTULOS = {"processos": "Total de processos", "resenhas": "Total de resenhas", "decisoes": "Total de decisões individuais",
           "deferidos": "Deferidos", "indeferidos": "Indeferidos", "refeitos": "Refeitos", "sem_efeito": "Tornados sem efeito"}


def _sem_acento(valor) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(valor or "")) if not unicodedata.combining(c)).lower()


def _lista(valor) -> list[str]:
    if valor is None or valor == "":
        return []
    return [v for v in (valor if isinstance(valor, (list, tuple)) else str(valor).split(",")) if v]


def normalizar_filtros(bruto: dict, perfil: str) -> dict:
    f = {
        "escopo": bruto.get("escopo") if bruto.get("escopo") in ("conferido", "pendente") else "conferido",
        "inicio": bruto.get("inicio") or None, "fim": bruto.get("fim") or None,
        "eixo": bruto.get("eixo") if bruto.get("eixo") in C.EIXOS else None,
        "modalidade": bruto.get("modalidade") if bruto.get("modalidade") in C.MODALIDADES else None,
        "condicao": bruto.get("condicao") if bruto.get("condicao") in C.CONDICOES else None,
        "grupo": [g for g in _lista(bruto.get("grupo")) if g in C.GRUPO_POR_CODIGO or g == "NAO_INFORMADO"],
        "subcategoria": [s for s in _lista(bruto.get("subcategoria")) if s in C.SUBCATEGORIA_POR_CODIGO],
        "resultado": bruto.get("resultado") if bruto.get("resultado") in C.RESULTADOS else None,
        "vinculo": bruto.get("vinculo") if bruto.get("vinculo") in ("EXPRESSO", "NAO_EXPRESSO") else None,
        "cartao": bruto.get("cartao") if bruto.get("cartao") in CARTOES else None,
        "busca": (bruto.get("busca") or "").strip()[:80] or None,
    }
    if perfil != GERENCIA_PERFIL:               # sem autorização: só agregados conferidos, sem busca individual
        f["escopo"], f["busca"] = "conferido", None
    return f


def _linhas(banco: Banco) -> list[dict]:
    consulta = banco.con.execute(
        "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, d.cargo, d.detalhe, "
        "d.resultado, d.trecho, d.validacao, d.revisor, d.revisado_em, d.justificativa, a.numero AS resenha, a.sufixo, a.tipo, "
        "a.data_publicacao AS data, a.data_expediente, a.vinculo, a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, "
        "a.grupo_expressao, a.subcategoria, a.pendencias FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.gerencia = 'GEDIV' "
        "ORDER BY a.data_publicacao DESC, a.pagina, d.rowid")
    linhas = []
    for l in consulta:
        linha = dict(l)
        linha["detalhe"] = json.loads(linha["detalhe"] or "{}")
        linha["pendencias"] = json.loads(linha["pendencias"] or "[]")
        linhas.append(linha)
    return linhas


def _passa(linha: dict, f: dict) -> bool:
    if f["eixo"] and linha["eixo"] != f["eixo"]:
        return False
    # Filtros de uma dimensão são neutros para o eixo ao qual ela não se aplica... a menos que o eixo
    # tenha sido escolhido: grupo, modalidade e condição só existem na Progressão; subcategoria, no Tempo de Serviço.
    if f["modalidade"] and not (linha["eixo"] == C.PROGRESSAO and linha["modalidade"] == f["modalidade"]):
        return False
    if f["condicao"] and not (linha["eixo"] == C.PROGRESSAO and (linha["condicao"] or "NAO_INFORMADA") == f["condicao"]):
        return False
    if f["grupo"] and not (linha["eixo"] == C.PROGRESSAO and (linha["grupo"] or "NAO_INFORMADO") in f["grupo"]):
        return False
    if f["subcategoria"] and not (linha["eixo"] == C.TEMPO and linha["subcategoria"] in f["subcategoria"]):
        return False
    if f["resultado"] and linha["resultado"] != f["resultado"]:
        return False
    if f["vinculo"] and linha["vinculo"] != f["vinculo"]:
        return False
    if f["busca"]:
        alvo = _sem_acento(" ".join(str(linha.get(c) or "") for c in ("resenha", "processo", "servidor", "matricula", "lotacao", "cargo")))
        if _sem_acento(f["busca"]) not in alvo:
            return False
    return True


def _no_periodo(data, f: dict) -> bool:
    if not f["inicio"] and not f["fim"]:
        return True
    return bool(data) and (not f["inicio"] or data >= f["inicio"]) and (not f["fim"] or data <= f["fim"])


def cobertura(banco: Banco) -> dict:
    um = lambda sql: banco.con.execute(sql).fetchone()[0]
    datas = banco.con.execute(
        "SELECT MIN(data_publicacao), MAX(data_publicacao) FROM publicacao WHERE sha256 IS NOT NULL").fetchone()
    edicoes = um("SELECT COUNT(*) FROM arquivo")
    return {
        "edicoes_no_acervo": edicoes,
        "edicoes_lidas": um("SELECT COUNT(*) FROM leitura WHERE situacao <> 'ERRO'"),
        "edicoes_com_pendencia_de_leitura": um("SELECT COUNT(*) FROM leitura WHERE situacao <> 'LIDA'"),
        "edicoes_classificadas": um("SELECT COUNT(*) FROM classificacao WHERE gerencia = 'GEDIV'"),
        "paginas_lidas": um("SELECT COUNT(*) FROM pagina"),
        "paginas_com_pendencia": um("SELECT COUNT(*) FROM pagina WHERE qualidade NOT IN ('OK', 'VAZIA')"),
        "primeira_data": datas[0], "ultima_data": datas[1],
        "ultima_atualizacao": um("SELECT MAX(concluida_em) FROM classificacao"),
        "completa": False,
        "parecer": ("Nenhuma edição carregada." if not edicoes else
                    f"Cobertura parcial: {edicoes} edição(ões) no acervo. O inventário completo do período não foi validado; "
                    "ausência de registro nesta base não comprova ausência de publicação."),
    }


def _fonte(banco: Banco, cache: dict, sha: str, pagina) -> dict:
    if sha not in cache:
        cache[sha] = banco.url_oficial(sha)
    url = cache[sha]
    return {"url_oficial": f"{url}#page={pagina}" if url else None, "pdf_no_acervo": f"/api/pdf/{sha}#page={pagina}"}


def painel(banco: Banco, bruto: dict | None = None, perfil: str = PUBLICO) -> dict:
    f = normalizar_filtros(bruto or {}, perfil)
    estado = "CONFERIDO" if f["escopo"] == "conferido" else "PENDENTE"
    todas = _linhas(banco)
    dim = [l for l in todas if l["validacao"] == estado and _passa(l, f)]
    originais = [l for l in dim if l["natureza"] == C.ORIGINAL and _no_periodo(l["data"], f)]

    # Eventos: somente vínculos VALIDADOS a atos originais do recorte; a data relevante é a do evento.
    atos_dim = {l["ato_id"] for l in dim if l["natureza"] == C.ORIGINAL}
    eventos = [dict(e) for e in banco.con.execute("SELECT * FROM evento WHERE gerencia = 'GEDIV' ORDER BY data_publicacao, pagina")]
    validos = [e for e in eventos if e["estado"] == "VALIDADO" and e["ato_original_id"] in atos_dim and _no_periodo(e["data_publicacao"], f)]
    refeitos = {e["ato_original_id"] for e in validos if e["tipo"] in C.TIPOS_REFEITO}
    sem_efeito = {e["ato_original_id"] for e in validos if e["tipo"] == C.SEM_EFEITO}
    conferido = f["escopo"] == "conferido"

    indicadores = {
        "processos": len({l["processo"] for l in originais if l["processo"]}),
        "resenhas": len({l["ato_id"] for l in originais}),
        "decisoes": len(originais),
        "deferidos": sum(l["resultado"] == "DEFERIDO" for l in originais),
        "indeferidos": sum(l["resultado"] == "INDEFERIDO" for l in originais),
        "refeitos": len(refeitos) if conferido else None,
        "sem_efeito": len(sem_efeito) if conferido else None,
    }

    # Clique em um cartão: a tabela e os gráficos mostram exclusivamente o universo daquele indicador.
    cartao = f["cartao"]
    if cartao == "processos":
        recorte = [l for l in originais if l["processo"]]
    elif cartao in ("deferidos", "indeferidos"):
        recorte = [l for l in originais if l["resultado"] == ("DEFERIDO" if cartao == "deferidos" else "INDEFERIDO")]
    elif cartao in ("refeitos", "sem_efeito"):
        alvo = refeitos if cartao == "refeitos" else sem_efeito
        recorte = [l for l in dim if l["ato_id"] in alvo and l["natureza"] == C.ORIGINAL] if conferido else []
    else:
        recorte = originais

    def conta(linhas):
        return {"total": len(linhas), "deferido": sum(l["resultado"] == "DEFERIDO" for l in linhas),
                "indeferido": sum(l["resultado"] == "INDEFERIDO" for l in linhas),
                "nao_informado": sum(l["resultado"] == "NAO_INFORMADO" for l in linhas)}

    prog = [l for l in recorte if l["eixo"] == C.PROGRESSAO]
    tempo = [l for l in recorte if l["eixo"] == C.TEMPO]
    cob = cobertura(banco)
    series = {
        "por_assunto": [
            {"chave": "VERTICAL", "rotulo": "Progressão Vertical", **conta([l for l in prog if l["modalidade"] == C.VERTICAL])},
            {"chave": "HORIZONTAL", "rotulo": "Progressão Horizontal", **conta([l for l in prog if l["modalidade"] == C.HORIZONTAL])},
            {"chave": "TEMPO_SERVICO", "rotulo": "Tempo de Serviço", **conta(tempo)},
        ],
        "progressao_sem_modalidade": sum(l["modalidade"] is None for l in prog),
        "por_data": [
            {"data": data, "vertical": sum(l["modalidade"] == C.VERTICAL for l in grupo), "horizontal": sum(l["modalidade"] == C.HORIZONTAL for l in grupo),
             "tempo": sum(l["eixo"] == C.TEMPO for l in grupo), "total": len(grupo)}
            for data in sorted({l["data"] or "" for l in recorte}) for grupo in [[l for l in recorte if (l["data"] or "") == data]]
        ],
        "por_grupo": [
            {"grupo": codigo, "nome": (C.GRUPO_POR_CODIGO[codigo].nome if codigo in C.GRUPO_POR_CODIGO else "Grupo não informado"),
             "horizontal": sum(l["modalidade"] == C.HORIZONTAL for l in linhas), "vertical": sum(l["modalidade"] == C.VERTICAL for l in linhas),
             **conta(linhas)}
            for codigo in [g.codigo for g in C.GRUPOS] + ["NAO_INFORMADO"]
            for linhas in [[l for l in prog if (l["grupo"] or "NAO_INFORMADO") == codigo]] if linhas
        ],
        # As sete subcategorias aparecem sempre; zero sem cobertura completa é "cobertura pendente", não "inexistente".
        "por_subcategoria": [
            {"codigo": s.codigo, "nome": s.nome, **conta(linhas),
             "situacao": None if linhas else ("sem ocorrência confirmada no período verificado" if cob["completa"] else "cobertura pendente")}
            for s in C.SUBCATEGORIAS for linhas in [[l for l in tempo if l["subcategoria"] == s.codigo]]
        ],
        "por_condicao": [{"condicao": c, "nome": n, "total": sum((l["condicao"] or "NAO_INFORMADA") == c for l in prog)}
                         for c, n in C.CONDICOES.items()],
    }

    individual = perfil == GERENCIA_PERFIL
    cache: dict = {}
    resenhas: dict[str, dict] = {}
    for l in recorte:
        r = resenhas.setdefault(l["ato_id"], {
            "ato_id": l["ato_id"], "resenha": l["resenha"], "sufixo": l["sufixo"], "data": l["data"], "pagina": l["pagina"],
            "eixo": l["eixo"], "modalidade": l["modalidade"], "condicao": l["condicao"], "grupo": l["grupo"],
            "subcategoria": l["subcategoria"], "vinculo": l["vinculo"], "natureza": l["natureza"], "decisoes": 0,
            "deferido": 0, "indeferido": 0, "pendencias": l["pendencias"] if individual else [],
            "refeito": l["ato_id"] in refeitos, "sem_efeito": l["ato_id"] in sem_efeito,
            **(_fonte(banco, cache, l["sha256"], l["pagina"]) if individual else
               {"url_oficial": _fonte(banco, cache, l["sha256"], l["pagina"])["url_oficial"], "pdf_no_acervo": None})})
        r["decisoes"] += 1
        r["deferido"] += l["resultado"] == "DEFERIDO"
        r["indeferido"] += l["resultado"] == "INDEFERIDO"

    um = lambda sql: banco.con.execute(sql).fetchone()[0]
    return {
        "meta": {
            "sistema": "Painel de Publicações DOE-PB GEDIV", "versao_regras": C.VERSAO_REGRAS, "perfil": perfil, "escopo": f["escopo"],
            "preliminar": not conferido,
            "rotulo": "Decisões conferidas" if conferido else "Em conferência · dados preliminares, não homologados",
            "dados_individuais": individual, "filtros": f, "cartao": cartao, "cobertura": cob,
        },
        "indicadores": indicadores,
        "ajuda": {c: ROTULOS[c] for c in CARTOES},
        "apoio": {
            "eventos_de_alteracao": len([e for e in validos if e["tipo"] in C.TIPOS_REFEITO]) if conferido else None,
            "eventos_por_tipo": {t: sum(e["tipo"] == t for e in validos) for t in C.ALTERACOES} if conferido else None,
            "eventos_sem_vinculo": sum(e["estado"] in ("PENDENTE_VINCULACAO", "SUGERIDO") for e in eventos),
            "decisoes_pendentes": um("SELECT COUNT(*) FROM decisao WHERE validacao = 'PENDENTE'"),
            "decisoes_conferidas": um("SELECT COUNT(*) FROM decisao WHERE validacao = 'CONFERIDO'"),
            "decisoes_rejeitadas": um("SELECT COUNT(*) FROM decisao WHERE validacao = 'REJEITADO'"),
            "vinculo_nao_expresso_pendente": um(
                "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE d.validacao = 'PENDENTE' AND a.vinculo <> 'EXPRESSO'"),
        },
        "series": series,
        "resenhas": sorted(resenhas.values(), key=lambda r: (r["data"] or "", r["pagina"]), reverse=True),
        "linhas": [{**{k: v for k, v in l.items() if k not in ("sha256", "pendencias")}, **_fonte(banco, cache, l["sha256"], l["pagina"]),
                    "refeito": l["ato_id"] in refeitos, "sem_efeito": l["ato_id"] in sem_efeito}
                   for l in recorte] if individual else [],
        "eventos": [{k: e[k] for k in ("id", "tipo", "subtipo", "data_publicacao", "pagina", "modificador", "estado",
                                       "ato_original_id", "ato_sugerido_id", "vinculo", "fundamento")}
                    | {"resenhas_citadas": json.loads(e["resenhas_citadas"] or "[]"),
                       "processos_citados": json.loads(e["processos_citados"] or "[]") if individual else [],
                       "texto": e["texto"] if individual else None,
                       **(_fonte(banco, cache, e["sha256"], e["pagina"]) if individual else {})}
                    for e in eventos if individual or e["estado"] == "VALIDADO"],
    }


def outras_publicacoes(banco: Banco, perfil: str = PUBLICO) -> list[dict]:
    """Página "Outras publicações": republicado por incorreção, portarias, atos normativos, alterações de lei.
    São resultados de triagem, pendentes de conferência; o trecho só é entregue à gerência."""
    cache: dict = {}
    saida = []
    for o in banco.con.execute("SELECT * FROM outra_publicacao WHERE gerencia = 'GEDIV' ORDER BY data_publicacao DESC, pagina"):
        item = {"id": o["id"], "tipo": o["tipo"], "nome_tipo": C.OUTRAS.get(o["tipo"], o["tipo"]), "data": o["data_publicacao"],
                "pagina": o["pagina"], "titulo": o["titulo"], "vinculo": o["vinculo"], "situacao": "triagem, a conferir"}
        fonte = _fonte(banco, cache, o["sha256"], o["pagina"])
        item["url_oficial"] = fonte["url_oficial"]
        if perfil == GERENCIA_PERFIL:
            item["trecho"], item["pdf_no_acervo"] = o["trecho"], fonte["pdf_no_acervo"]
        saida.append(item)
    return saida
