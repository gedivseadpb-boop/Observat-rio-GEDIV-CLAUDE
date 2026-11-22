"""Aplica a classificação GEDIV aos arquivos já lidos e grava os candidatos no banco.

Nada do que é gravado aqui entra nos indicadores: todo registro nasce PENDENTE e só a
revisão humana (observatorio.revisao) pode torná-lo CONFERIDO.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from ...nucleo.banco import Banco, normalizar_matricula, normalizar_processo, normalizar_texto
from . import catalogo as C
from .classificador import PAT_MATRICULA, PAT_PROCESSO, PAT_PROCESSO_ANTIGO, _tema, classificar

GERENCIA = "GEDIV"
INICIO_DA_BASE = "2026-01-01"     # primeira data coberta pela coleta histórica


def classificar_pendentes(banco: Banco, refazer: bool = False) -> dict:
    """Classifica os arquivos lidos ainda não classificados com a versão atual das regras."""
    if refazer:
        fila = [l["sha256"] for l in banco.leituras() if l["situacao"] != "ERRO"]
    else:
        fila = [l["sha256"] for l in banco.arquivos_sem_classificacao(GERENCIA, C.VERSAO_REGRAS)]
    resumo = {"arquivos": 0, "atos": 0, "decisoes": 0, "eventos": 0, "outras": 0, "fora_escopo": 0, "descartados": 0,
              "preservadas_por_revisao": 0, "conflitos": 0, "com_erro": 0, "erros": []}
    for sha in fila:
        try:
            paginas = banco.paginas(sha)
            resultado = classificar([(p["numero"], p["texto"]) for p in paginas], sha)
            from .paddle_complementar import preservar_propostas
            preservar_propostas(banco, resultado, sha)
            ruins = [p["numero"] for p in paginas if p["qualidade"] not in ("OK", "VAZIA")]
            if ruins:
                resultado.pendencias.append(
                    f"páginas com leitura pendente ou de baixa confiança: {', '.join(map(str, ruins))}; pode haver atos não extraídos")
            if any(p["metodo"] != "TEXTO" for p in paginas):
                resultado.pendencias.append("há páginas lidas por OCR; conferir página e colunas no PDF")
            parte = banco.gravar_classificacao(GERENCIA, sha, C.VERSAO_REGRAS, banco.data_do_arquivo(sha), resultado)
        except Exception as e:
            # Um arquivo problemático não para a fila. Nada dele é gravado pela metade (gravar_classificacao é uma
            # transação) e ele continua na fila de classificação para a próxima execução. Só o tipo do erro é
            # registrado: a mensagem poderia trazer trechos do documento.
            resumo["com_erro"] += 1
            resumo["erros"].append({"sha256": sha[:12], "erro": type(e).__name__})
            continue
        resumo["arquivos"] += 1
        for chave in parte:
            resumo[chave] += parte[chave]
    resumo["vinculos_sugeridos"] = sugerir_vinculos(banco)
    return resumo


def eixo_do_evento(evento, ato_mod=None) -> str | None:
    """Identifica o eixo temático esperado de um evento modificador para evitar colisões entre séries
    (ex.: Resenha 353/2026 de Abono de Permanência vs. Resenha 353/2026 de Progressão GAJ)."""
    if ato_mod is not None and ato_mod["eixo"]:
        return ato_mod["eixo"]
    texto_norm = C.normalizar(evento["texto"] or "")
    if not texto_norm:
        return None
    tema = _tema(texto_norm)
    if tema["eixo"]:
        return tema["eixo"]
    if "ABONO DE PERMANENCIA" in texto_norm or "EMENDA CONSTITUCIONAL FEDERAL 103/2019" in texto_norm or "EC 103/2019" in texto_norm:
        return "OUTROS_ABONO"
    return None


_eixo_do_evento = eixo_do_evento


def extrair_matriculas_citadas(texto: str) -> set[str]:
    """Extrai matrículas válidas citadas no texto do evento, removendo antes números de processo
    (inclusive processos legados no formato 999.999-9) para evitar falsas correspondências."""
    norm = C.normalizar(texto or "")
    if not norm:
        return set()
    limpo = PAT_PROCESSO.sub(" ", norm)
    limpo = PAT_PROCESSO_ANTIGO.sub(" ", limpo)
    return {m for raw in PAT_MATRICULA.findall(limpo) if (m := normalizar_matricula(raw))}


def _nome_citado(servidor: str | None, texto_ev_norm: str) -> bool:
    nome = normalizar_texto(servidor)
    if not nome or len(nome.split()) < 2 or len(nome) < 8:
        return False
    return re.search(rf"(?<![A-Z0-9]){re.escape(nome)}(?![A-Z0-9])", texto_ev_norm) is not None


def resolver_decisoes_por_referencias(evento, decs_ato) -> tuple[list[str], str | None]:
    """Resolve as decisões individuais atingidas por um evento a partir das referências documentais.

    Regra para processos coletivos: quando o processo citado contém múltiplas decisões no ato original,
    NUNCA vincula automaticamente todas as decisões do processo coletivo. Exige identificação individual
    inequívoca (matrícula e/ou nome completo compatível e sem contradição). Havendo ambiguidade, devolve
    `([], motivo)` para que o evento permaneça pendente até identificação explícita (`decisoes_ids`)."""
    procs_cit = list(dict.fromkeys(
        p for raw in json.loads(evento["processos_citados"] or "[]")
        if (p := normalizar_processo(raw))
    ))
    texto_ev = evento["texto"] or ""
    texto_ev_norm = normalizar_texto(texto_ev)
    mats_cit = extrair_matriculas_citadas(texto_ev)
    resolvidas: list[str] = []

    if procs_cit:
        for proc_norm in procs_cit:
            cands = [d for d in decs_ato if normalizar_processo(d["processo"]) == proc_norm]
            if not cands:
                continue
            if len(cands) == 1:
                unico = cands[0]
                m_unico = normalizar_matricula(unico["matricula"])
                # Se o evento cita apenas este processo e uma matrícula explícita divergente, recusa por ambiguidade.
                if len(procs_cit) == 1 and mats_cit and m_unico and m_unico not in mats_cit:
                    return [], "matrícula citada no evento diverge da decisão do processo informado; vínculo mantido pendente"
                resolvidas.append(unico["id"])
                continue

            # Processo coletivo (> 1 decisão no mesmo processo): exigir identificação individual inequívoca.
            por_mat = [d for d in cands if (m := normalizar_matricula(d["matricula"])) and m in mats_cit]
            por_nome = [d for d in cands if _nome_citado(d["servidor"], texto_ev_norm)]

            if por_mat:
                if por_nome and {d["id"] for d in por_mat} != {d["id"] for d in por_nome}:
                    return [], "referências individuais (matrícula e servidor) divergem no processo coletivo; informe decisoes_ids explicitamente"
                cont_m = Counter(normalizar_matricula(d["matricula"]) for d in por_mat)
                if any(v > 1 for v in cont_m.values()):
                    return [], "mais de uma decisão compartilha a mesma matrícula no processo coletivo; informe decisoes_ids explicitamente"
                resolvidas.extend(d["id"] for d in por_mat)
            elif not mats_cit and por_nome:
                cont_n = Counter(normalizar_texto(d["servidor"]) for d in por_nome)
                if any(v > 1 for v in cont_n.values()):
                    return [], "mais de uma decisão compartilha o mesmo nome no processo coletivo; informe decisoes_ids explicitamente"
                resolvidas.extend(d["id"] for d in por_nome)
            else:
                return [], (
                    "processo coletivo com múltiplos servidores exige identificação individual inequívoca "
                    "(matrícula/referência documental ou decisoes_ids explícito); evento mantido pendente"
                )
    else:
        # Sem processo citado: só resolve se matrícula ou nome identificar inequivocamente no ato
        por_mat = [d for d in decs_ato if (m := normalizar_matricula(d["matricula"])) and m in mats_cit]
        por_nome = [d for d in decs_ato if _nome_citado(d["servidor"], texto_ev_norm)]
        if por_mat:
            if por_nome and {d["id"] for d in por_mat} != {d["id"] for d in por_nome}:
                return [], "matrícula e servidor citados no evento divergem nas decisões do ato; informe decisoes_ids explicitamente"
            cont_m = Counter(normalizar_matricula(d["matricula"]) for d in por_mat)
            if any(v > 1 for v in cont_m.values()):
                return [], "matrícula citada corresponde a múltiplas decisões no ato; informe decisoes_ids explicitamente"
            resolvidas.extend(d["id"] for d in por_mat)
        elif not mats_cit and por_nome:
            cont_n = Counter(normalizar_texto(d["servidor"]) for d in por_nome)
            if any(v > 1 for v in cont_n.values()):
                return [], "nome citado corresponde a múltiplas decisões no ato; informe decisoes_ids explicitamente"
            resolvidas.extend(d["id"] for d in por_nome)

    return list(dict.fromkeys(resolvidas)), None


def _ato_compativel_com_evento(banco: Banco, evento, ato_cand, ato_mod, eixo_ev: str | None,
                               procs_ev: set[str], datas_citadas: set[str]) -> tuple[bool, int]:
    """Verifica compatibilidade entre um ato ORIGINAL candidato e o evento modificador.
    Devolve (compativel, qtd_processos_em_comum). Nunca sugere vínculo apenas por coincidência de número."""
    if eixo_ev is not None and ato_cand["eixo"] != eixo_ev:
        return False, 0
    if datas_citadas and ato_cand["data_publicacao"] and ato_cand["data_publicacao"] not in datas_citadas:
        return False, 0
    comum = 0
    if procs_ev:
        procs_ato = {
            p for r in banco.con.execute(
                "SELECT processo FROM decisao WHERE ato_id = ? AND vigente = 1 AND processo IS NOT NULL",
                (ato_cand["id"],),
            )
            if (p := normalizar_processo(r[0]))
        }
        if procs_ato:
            comum = len(procs_ev & procs_ato)
            if comum == 0:
                return False, 0
        else:
            return False, 0
    return True, comum


def sugerir_vinculos(banco: Banco) -> int:
    """Propõe o ato original de cada evento de alteração quando a correspondência é única e compatível
    em eixo, data citada e processos (nunca apenas por número isolado de resenha).

    É apenas uma SUGESTÃO para o revisor: o evento não conta em REFEITOS nem em TORNADOS SEM EFEITO
    enquanto o vínculo não for validado por uma pessoa. Sem correspondência inequívoca e compatível,
    o evento permanece PENDENTE_VINCULACAO.
    """
    sugeridos = 0
    eventos = banco.con.execute("SELECT * FROM evento WHERE estado = 'PENDENTE_VINCULACAO' AND gerencia = ?", (GERENCIA,)).fetchall()
    for evento in eventos:
        res_citadas = json.loads(evento["resenhas_citadas"] or "[]")
        procs_ev = {p for raw in json.loads(evento["processos_citados"] or "[]") if (p := normalizar_processo(raw))}
        citadas = json.loads(evento["publicacoes_citadas"] or "[]")
        datas_citadas = set(citadas)
        ato_mod = (
            banco.con.execute("SELECT * FROM ato WHERE id = ?", (evento["ato_id"],)).fetchone()
            if evento["ato_id"] else None
        )
        eixo_ev = _eixo_do_evento(evento, ato_mod)

        if citadas and all(d < INICIO_DA_BASE for d in citadas):
            if not evento["fundamento"]:
                with banco.con:
                    banco.con.execute(
                        "UPDATE evento SET fundamento = ? WHERE id = ?",
                        ("ato original publicado no DOE de " + ", ".join(f"{d[8:]}/{d[5:7]}/{d[:4]}" for d in citadas)
                         + f", antes do início da base ({INICIO_DA_BASE[8:]}/{INICIO_DA_BASE[5:7]}/{INICIO_DA_BASE[:4]}); "
                         "vínculo automático impossível", evento["id"]),
                    )
            continue

        candidatos: dict[str, tuple[str, int, int]] = {}

        def _registrar_cand(ato_row, comum_n: int) -> None:
            chave_log = ato_row["chave_logica"] or ato_row["id"]
            d_vig = int(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE ato_id = ? AND vigente = 1", (ato_row["id"],)).fetchone()[0])
            atual = candidatos.get(chave_log)
            if atual is None or (d_vig > 0, comum_n, d_vig) > (atual[2] > 0, atual[1], atual[2]):
                candidatos[chave_log] = (ato_row["id"], comum_n, d_vig)

        # 1. Busca por resenha citada + compatibilidade de eixo/processos/data
        for numero in res_citadas:
            for ato in banco.con.execute(
                "SELECT * FROM ato WHERE gerencia = ? AND tipo = 'RESENHA' AND natureza = 'ORIGINAL' AND numero = ? "
                "AND id <> COALESCE(?, '') AND (data_publicacao IS NULL OR ? IS NULL OR data_publicacao <= ?)",
                (GERENCIA, numero, evento["ato_id"], evento["data_publicacao"], evento["data_publicacao"]),
            ):
                ok, comum = _ato_compativel_com_evento(banco, evento, ato, ato_mod, eixo_ev, procs_ev, datas_citadas)
                if ok:
                    _registrar_cand(ato, comum)

        # 2. Se não citou número de resenha, mas citou processo(s) explícito(s), busca atos originais compatíveis pelos processos
        if not candidatos and not res_citadas and procs_ev:
            for ato in banco.con.execute(
                "SELECT DISTINCT a.* FROM ato a JOIN decisao d ON d.ato_id = a.id "
                "WHERE a.gerencia = ? AND a.natureza = 'ORIGINAL' AND d.vigente = 1 AND d.processo IS NOT NULL "
                "AND a.id <> COALESCE(?, '') AND (a.data_publicacao IS NULL OR ? IS NULL OR a.data_publicacao <= ?)",
                (GERENCIA, evento["ato_id"], evento["data_publicacao"], evento["data_publicacao"]),
            ):
                ok, comum = _ato_compativel_com_evento(banco, evento, ato, ato_mod, eixo_ev, procs_ev, datas_citadas)
                if ok and comum > 0:
                    _registrar_cand(ato, comum)

        if len(candidatos) == 1:
            ato_id_sug, comum, _ = next(iter(candidatos.values()))
            detalhes_match = []
            if res_citadas:
                detalhes_match.append("número de resenha citado")
            if comum > 0:
                detalhes_match.append(f"{comum} processo(s) em comum")
            if eixo_ev:
                detalhes_match.append(f"eixo compatível ({eixo_ev})")
            fundamento = "; ".join(detalhes_match) or "ato original único compatível na base"
            with banco.con:
                banco.con.execute(
                    "UPDATE evento SET ato_sugerido_id = ?, estado = 'SUGERIDO', fundamento = ? WHERE id = ?",
                    (ato_id_sug, fundamento, evento["id"]),
                )
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
        "fora_escopo": {l[0]: l[1] for l in banco.con.execute(
            "SELECT motivo, COUNT(*) FROM fora_escopo WHERE gerencia = 'GEDIV' GROUP BY motivo")},
    }
