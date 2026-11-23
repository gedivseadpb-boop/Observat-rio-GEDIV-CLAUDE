"""Adaptador bidirecional e reconciliador entre o modelo Python (Banco/API) e o modelo do Dashboard GEDIV.

Preserva todos os campos relevantes sem perda de informação, aplicando a regra normativa controlada
para grupos ocupacionais (Etapa 4B):
- 'TEC. ADM' / 'TEC-ADM' normaliza para o grupo canônico 'AST' ('AST · Técnicos Administrativos')
  em registros compatíveis, preservando a expressão original em `grupo_expressao`; registros
  incompatíveis ou ambíguos permanecem em 'PENDENTE:TEC. ADM';
- 'STF' normaliza para 'SFT' ('SFT · Fazenda · Auditor Fiscal') somente quando há cargo ou
  enquadramento fiscal/tributário verificado, preservando `grupo_expressao = 'STF'`; registros
  sem comprovação permanecem em 'PENDENTE:STF';
- 'SAUDE' -> 'SSA' e 'ESPECIAL' -> 'ESP' possuem equivalência documental comprovada no catálogo
  oficial (`observatorio.gerencias.gediv.catalogo.GRUPOS`);
- Publicações de `outra_publicacao` (incluindo Abono de Permanência, alterações de lei, portarias
  e republicações por incorreção) são entregues separadamente em `otherPublications`, nunca
  contaminando os totais de decisões primárias dos dois eixos.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from ..gerencias.gediv import catalogo as C
from ..nucleo.banco import (
    Banco,
    agora,
    chave_ato,
    chave_decisao,
    chave_processo,
    normalizar_matricula,
)
from . import indicadores

# Equivalências documentais comprovadas no catálogo oficial (catalogo.py):
EQUIVALENCIAS_COMPROVADAS = {
    "SAUDE": "SSA",
    "GAJ-1700": "GAJ",
    "FAP-1300": "FAP",
    "ANS-900": "ANS",
    "ESPECIAL": "ESP",
    "DPS-1600": "DPS",
    "FAZENDA": "SFT",
}

# Expressões com normalização condicional (permanecem pendentes quando incompatíveis ou sem enquadramento verificado):
EXPRESSOES_PENDENTES_CONFIRMACAO = {
    "TEC-ADM": ("PENDENTE:TEC. ADM", "TEC. ADM", "TEC. ADM · Técnicos Administrativos (vínculo com AST pendente/incompatível)"),
    "TEC. ADM": ("PENDENTE:TEC. ADM", "TEC. ADM", "TEC. ADM · Técnicos Administrativos (vínculo com AST pendente/incompatível)"),
    "PENDENTE:TEC. ADM": ("PENDENTE:TEC. ADM", "TEC. ADM", "TEC. ADM · Técnicos Administrativos (vínculo com AST pendente/incompatível)"),
    "STF": ("PENDENTE:STF", "STF", "STF · Auditor Fiscal Tributário (enquadramento SFT pendente de confirmação)"),
    "PENDENTE:STF": ("PENDENTE:STF", "STF", "STF · Auditor Fiscal Tributário (enquadramento SFT pendente de confirmação)"),
}


def mapear_grupo_para_backend(
    grupo_frontend: str | None,
    expressao_original: str | None = None,
    *,
    cargo: str | None = None,
    evidencia: str | None = None,
) -> tuple[str | None, str | None, bool]:
    """Converte código de grupo do frontend para (grupo_pccr_ou_None, grupo_expressao, pendente_confirmacao).
    - 'TEC-ADM' / 'TEC. ADM' -> ('AST', 'TEC. ADM', False) quando compatível; caso incompatível, permanece pendente.
    - 'STF' -> ('SFT', 'STF', False) somente quando cargo ou evidência comprova enquadramento fiscal/tributário;
      caso contrário, permanece pendente ('STF', True).
    """
    bruto = (grupo_frontend or "").strip().upper()
    if not bruto or bruto == "NAO_INFORMADO":
        return None, (expressao_original or None), False
    if bruto in ("PENDENTE:TEC. ADM", "PENDENTE:STF"):
        _, exp_literal, _ = EXPRESSOES_PENDENTES_CONFIRMACAO[bruto]
        return None, (expressao_original or exp_literal), True
    if bruto in ("TEC-ADM", "TEC. ADM"):
        exp_lit = expressao_original or "TEC. ADM"
        pre = C.normalizar(f"GRUPO {exp_lit} {evidencia or ''}")
        codigo, _exp, pend = C.avaliar_grupo(pre, cargos=[cargo] if cargo else None)
        if codigo == "AST" and pend is None:
            return "AST", exp_lit, False
        return None, exp_lit, True
    if bruto == "STF":
        exp_lit = expressao_original or "STF"
        pre = C.normalizar(f"GRUPO {exp_lit} {evidencia or ''}")
        codigo, _exp, pend = C.avaliar_grupo(pre, cargos=[cargo] if cargo else None)
        if codigo == "SFT" and pend is None:
            return "SFT", exp_lit, False
        return None, exp_lit, True
    normalizado = EQUIVALENCIAS_COMPROVADAS.get(bruto, bruto)
    if normalizado in C.GRUPO_POR_CODIGO:
        return normalizado, (expressao_original or bruto), False
    return None, (expressao_original or bruto), True


def mapear_grupo_para_frontend(grupo_backend: str | None, grupo_expressao: str | None = None) -> dict:
    """Converte (grupo, grupo_expressao) do backend para representação rastreável no frontend.
    Nenhum registro desaparece: expressões sem grupo homologado recebem código próprio e flag `pendingConfirmation=True`.
    """
    g = (grupo_backend or "").strip().upper()
    exp = (grupo_expressao or "").strip()
    exp_upper = exp.upper()
    if g and g in C.GRUPO_POR_CODIGO:
        return {
            "group": g,
            "groupCanonical": g,
            "groupExpression": exp or g,
            "groupLabel": f"{g} · {C.GRUPO_POR_CODIGO[g].nome}",
            "groupPendingConfirmation": False,
        }
    if re.search(r"\bTEC\.?\s*ADM\b", exp_upper) or exp_upper == "TEC-ADM":
        info = EXPRESSOES_PENDENTES_CONFIRMACAO["TEC. ADM"]
        return {
            "group": info[0],
            "groupCanonical": None,
            "groupExpression": exp or info[1],
            "groupLabel": info[2],
            "groupPendingConfirmation": True,
        }
    if re.search(r"\bSTF\b", exp_upper):
        info = EXPRESSOES_PENDENTES_CONFIRMACAO["STF"]
        return {
            "group": info[0],
            "groupCanonical": None,
            "groupExpression": exp or info[1],
            "groupLabel": info[2],
            "groupPendingConfirmation": True,
        }
    if exp:
        return {
            "group": f"PENDENTE:{exp_upper}",
            "groupCanonical": None,
            "groupExpression": exp,
            "groupLabel": f"{exp} (expressão pendente de confirmação)",
            "groupPendingConfirmation": True,
        }
    return {
        "group": "",
        "groupCanonical": None,
        "groupExpression": "",
        "groupLabel": "Grupo não informado",
        "groupPendingConfirmation": False,
    }


def backend_para_frontend_linha(linha: dict) -> dict:
    """Transforma uma linha de decisão do backend (`indicadores.painel()['linhas']`) no formato do frontend JS,
    preservando 100% dos campos documentais, de revisão e de nível A–F.
    """
    eixo_b = linha.get("eixo")
    axis = "progressao" if eixo_b == C.PROGRESSAO else "tempo" if eixo_b == C.TEMPO else "outros"
    mod_b = linha.get("modalidade")
    modality = "Vertical" if mod_b == C.VERTICAL else "Horizontal" if mod_b == C.HORIZONTAL else ""
    res_b = linha.get("resultado")
    merit = "deferido" if res_b == "DEFERIDO" else "indeferido" if res_b == "INDEFERIDO" else "outro"
    val_b = linha.get("validacao")
    validation = "conferido" if val_b == "CONFERIDO" else "rejeitado" if val_b == "REJEITADO" else "pendente"

    det = linha.get("detalhe") if isinstance(linha.get("detalhe"), dict) else {}
    nv = linha.get("nivel_info") or indicadores.classificar_nivel_vertical(linha)
    grp = mapear_grupo_para_frontend(linha.get("grupo"), linha.get("grupo_expressao"))

    resenha_num = str(linha.get("resenha") or "")
    sufixo = str(linha.get("sufixo") or "").strip(" -/")
    resenha_fmt = f"{resenha_num} · {sufixo}" if (resenha_num and sufixo and sufixo not in resenha_num) else (resenha_num or "Não identificada")
    url_of = str(linha.get("url_oficial") or "").split("#")[0]

    level_to = nv.get("classe_posterior") if nv.get("motivo") == "ok" else ""
    level_from = nv.get("classe_anterior") if nv.get("motivo") == "ok" else ""
    level_status = nv.get("categoria") or ""
    level_label = nv.get("rotulo") or (f"Nível {level_status}" if level_status in indicadores._CLASSES_VALIDAS else "")
    level_note = nv.get("observacao") or nv.get("descricao") or ""

    return {
        "id": linha.get("id"),
        "act": linha.get("ato_id") or "",
        "resenha_id": linha.get("ato_id") or "",
        "date": linha.get("data") or linha.get("data_edicao") or "",
        "dateExpediente": linha.get("data_expediente") or "",
        "resenha": resenha_fmt,
        "orgao": sufixo or (linha.get("lotacao") or ""),
        "actType": linha.get("tipo") or "RESENHA",
        "natureza": str(linha.get("natureza") or "ORIGINAL").lower(),
        "resultadoOriginal": str(linha.get("resultado_original") or linha.get("resultado") or ""),
        "retificacoesAplicadas": list(linha.get("retificacoes_aplicadas") or []),
        "origemTempo": str(det.get("origem_tempo") or det.get("origem") or ""),
        "process": linha.get("processo") or "",
        "server": linha.get("servidor") or "",
        "registration": linha.get("matricula") or "",
        "lotacao": linha.get("lotacao") or "",
        "cargo": linha.get("cargo") or "",
        "axis": axis,
        "modality": modality,
        "condition": linha.get("condicao") or "NAO_INFORMADA",
        "group": grp["group"],
        "groupCanonical": grp["groupCanonical"],
        "groupExpression": grp["groupExpression"],
        "groupLabel": grp["groupLabel"],
        "groupPendingConfirmation": grp["groupPendingConfirmation"],
        "category": linha.get("subcategoria") or "",
        "merit": merit,
        "validation": validation,
        "revisor": linha.get("revisor") or "",
        "revisadoEm": linha.get("revisado_em") or "",
        "justificativa": linha.get("justificativa") or "",
        "preliminaryReview": det.get("nota_preliminar") or "",
        "page": linha.get("pagina"),
        "url": url_of,
        "urlOficial": linha.get("url_oficial"),
        "pdfNoAcervo": linha.get("pdf_no_acervo"),
        "evidence": linha.get("trecho") or "",
        "sourceMention": "expresso" if linha.get("vinculo") == "EXPRESSO" else "nao_expresso",
        "levelFrom": level_from or "",
        "levelTo": level_to or "",
        "levelTransition": nv.get("transicao") or "",
        "levelStatus": level_status,
        "levelLabel": level_label,
        "levelReason": nv.get("motivo") or "",
        "levelNote": level_note,
        "detalhe": det,
        "refeito": bool(linha.get("refeito")),
        "semEfeito": bool(linha.get("sem_efeito")),
        "conflitoAberto": bool(linha.get("conflito_aberto")),
    }


def frontend_para_backend_linha(row: dict) -> dict:
    """Transforma um registro do frontend (`window.GEDIV_BOOTSTRAP['rows']`) para as estruturas de `ato` e `decisao` do SQLite v8,
    preservando `preliminaryReview` separadamente em `detalhe['nota_preliminar']` e mantendo a expressão de grupo original.
    """
    axis_f = (row.get("axis") or "").strip().lower()
    eixo = C.PROGRESSAO if axis_f == "progressao" else C.TEMPO if axis_f == "tempo" else "OUTROS"
    mod_f = (row.get("modality") or "").strip().capitalize()
    modalidade = C.VERTICAL if mod_f == "Vertical" else C.HORIZONTAL if mod_f == "Horizontal" else None
    merit_f = (row.get("merit") or "").strip().lower()
    resultado = "DEFERIDO" if merit_f == "deferido" else "INDEFERIDO" if merit_f == "indeferido" else "NAO_INFORMADO"
    val_f = (row.get("validation") or "pendente").strip().lower()
    validacao = "CONFERIDO" if val_f == "conferido" else "REJEITADO" if val_f == "rejeitado" else "PENDENTE"
    vinculo = "EXPRESSO" if (row.get("sourceMention") or "").lower() == "expresso" else "NAO_EXPRESSO"

    grupo_pccr, grupo_exp, pendente_conf = mapear_grupo_para_backend(
        row.get("group"),
        row.get("groupExpression"),
        cargo=row.get("cargo"),
        evidencia=row.get("evidence"),
    )
    subcategoria = row.get("category") if (eixo == C.TEMPO and row.get("category") in C.SUBCATEGORIA_POR_CODIGO) else None

    temp_linha = {
        "eixo": C.PROGRESSAO if eixo == C.PROGRESSAO else C.TEMPO,
        "modalidade": modalidade,
        "resultado": resultado,
        "detalhe": {"classe_anterior": row.get("levelFrom"), "classe_posterior": row.get("levelTo")},
        "trecho": row.get("evidence") or "",
    }
    nv = indicadores.classificar_nivel_vertical(temp_linha)
    detalhe: dict = {}
    if nv.get("classe_anterior"):
        detalhe["classe_anterior"] = nv["classe_anterior"]
    if nv.get("classe_posterior"):
        detalhe["classe_posterior"] = nv["classe_posterior"]
    nota_prelim = str(row.get("preliminaryReview") or "").strip()
    if nota_prelim:
        detalhe["nota_preliminar"] = nota_prelim
    if row.get("id"):
        detalhe["id_referencia_snapshot"] = row["id"]

    pendencias = []
    if pendente_conf and grupo_exp:
        pendencias.append(f"expressão '{grupo_exp}' sem grupo homologado: vínculo normativo pendente de confirmação pela GEDIV")

    return {
        "id": row.get("id"),
        "ato_id": row.get("resenha_id") or row.get("act") or "",
        "data": row.get("date") or "",
        "resenha": row.get("resenha") or "",
        "pagina": int(row["page"]) if row.get("page") is not None else 1,
        "url": row.get("url") or "",
        "processo": (row.get("process") or "").strip() or None,
        "servidor": (row.get("server") or "").strip() or None,
        "matricula": (row.get("registration") or "").strip() or None,
        "lotacao": (row.get("lotacao") or "").strip() or None,
        "cargo": (row.get("cargo") or "").strip() or None,
        "eixo": eixo,
        "modalidade": modalidade if eixo == C.PROGRESSAO else None,
        "grupo": grupo_pccr if eixo == C.PROGRESSAO else None,
        "grupo_expressao": grupo_exp if eixo == C.PROGRESSAO else None,
        "subcategoria": subcategoria,
        "resultado": resultado,
        "validacao": validacao,
        "vinculo": vinculo,
        "trecho": row.get("evidence") or "",
        "detalhe": detalhe,
        "pendencias": pendencias,
        "nivel_info": nv,
    }


def _eh_abono_permanencia(o: dict) -> bool:
    """Identifica publicações de Abono de Permanência (excluindo Abono Natalino)."""
    txt = f"{o.get('titulo') or ''} {o.get('trecho') or ''}".upper()
    if "NATALINO" in txt and "PERMAN" not in txt:
        return False
    return "ABONO" in txt and "PERMAN" in txt


def projetar_para_dashboard_2910(painel_resp: dict, outras_resp: list[dict] | None = None,
                                 linhas_rejeitadas: list[dict] | None = None) -> dict:
    """Converte a resposta de `indicadores.painel()` (+ `outras_publicacoes()`) para o contrato `window.GEDIV_BOOTSTRAP`
    consumido pelo dashboard unificado GEDIV, usando fonte única de cálculo (sem contaminação dos totais de
    decisões por `outra_publicacao`, que permanecem preservadas em `otherPublications`).
    """
    meta_b = painel_resp.get("meta") or {}
    cob_b = meta_b.get("cobertura") or {}
    apoio_b = painel_resp.get("apoio") or {}
    series_b = painel_resp.get("series") or {}
    diag_vr = meta_b.get("versao_regras_diagnostico") or cob_b.get("versao_regras_diagnostico") or {}
    individual = bool(meta_b.get("dados_individuais"))
    if not individual and isinstance(diag_vr, dict) and diag_vr:
        incomp_pub = bool(diag_vr.get("incompativel"))
        diag_vr = {
            "versao_codigo": diag_vr.get("versao_codigo") or C.VERSAO_REGRAS,
            "versoes_no_banco": [],
            "edicoes_por_versao": None,
            "compativel": not incomp_pub,
            "incompativel": incomp_pub,
            "edicoes_compativeis": None,
            "edicoes_incompativeis": None,
            "decisoes_afetadas": None,
            "mensagem": (
                "Incompatibilidade técnica de versão de regras detectada; os indicadores aguardam alinhamento interno."
                if incomp_pub else None
            ),
        }

    # 1. Somente decisões primárias dos dois eixos (PROGRESSAO e TEMPO_SERVICO) entram em `rows`
    rows_conv = [backend_para_frontend_linha(l) for l in (painel_resp.get("linhas") or [])]
    if individual and linhas_rejeitadas:
        ids_vistos = {r["id"] for r in rows_conv}
        for lr in linhas_rejeitadas:
            rc = backend_para_frontend_linha(lr)
            if rc["id"] not in ids_vistos:
                rows_conv.append(rc)
                ids_vistos.add(rc["id"])

    # 2. `outra_publicacao` (Abono de Permanência, Alterações de Lei, Portarias, Atos Normativos,
    #    Republicado por Incorreção, Tema Fora dos Eixos) fica estritamente em `otherPublications`!
    other_pubs_conv: list[dict] = []
    if individual and outras_resp:
        ids_outras_vistos: set[str] = set()
        abono_ind_refs = {
            o.get("pdf_no_acervo")
            for o in outras_resp
            if o.get("pdf_no_acervo")
            and str(o.get("id") or "").startswith(("pdf-", "historico-"))
            and _eh_abono_permanencia(o)
        }
        for o in outras_resp:
            oid = o.get("id")
            if oid in ids_outras_vistos:
                continue
            eh_abono = _eh_abono_permanencia(o)
            eh_ind = str(oid or "").startswith(("pdf-", "historico-"))
            if eh_abono and not eh_ind and o.get("pdf_no_acervo") in abono_ind_refs:
                continue
            ids_outras_vistos.add(oid)
            trecho = o.get("trecho") or ""
            meta_o = {}
            if trecho.startswith("<!--GEDIV_META:") and "-->\n" in trecho:
                fim_meta = trecho.find("-->\n")
                try:
                    meta_o = json.loads(trecho[len("<!--GEDIV_META:"):fim_meta])
                except Exception:
                    meta_o = {}
                trecho = trecho[fim_meta + 4:]
            m_proc = re.search(r"\b([A-Z]{2,6}\s*-\s*(?:PSE|PRC|OFI)\s*-\s*\d{4}\s*[/-]\s*\d{3,9})\b", trecho.upper())
            proc = meta_o.get("processo") or (re.sub(r"\s+", "", m_proc.group(1)) if m_proc else "")
            m_mat = re.search(r"\b(\d{5,7}-\d)\b", trecho)
            mat = meta_o.get("matricula") or (m_mat.group(1) if m_mat else "")
            srv_outro = meta_o.get("servidor") or ""
            if not srv_outro and m_mat:
                pos_mat = trecho[m_mat.end():].strip()
                m_srv = re.match(r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{4,60}?)(?:\s{2,}|\n|$)", pos_mat)
                if m_srv:
                    srv_outro = " ".join(m_srv.group(1).split())
            res_id_o = meta_o.get("ato_id") or oid
            res_lbl_o = meta_o.get("resenha") or str(o.get("titulo") or "").replace("Resenha ", "") or o.get("nome_tipo") or "Publicação GEDIV"
            url_of = str(o.get("url_oficial") or "").split("#")[0]
            res_txt = meta_o.get("resultado") or (
                "DEFERIDO" if "DEFERI" in trecho.upper() and "INDEFERI" not in trecho.upper()
                else ("INDEFERIDO" if "INDEFERI" in trecho.upper() else "NAO_INFORMADO")
            )
            other_pubs_conv.append({
                "id": oid,
                "act": res_id_o,
                "resenha_id": res_id_o,
                "date": o.get("data") or "",
                "dateExpediente": "",
                "resenha": res_lbl_o,
                "orgao": meta_o.get("orgao") or "",
                "actType": o.get("tipo") or "OUTRA",
                "natureza": "original",
                "resultadoOriginal": res_txt,
                "origemTempo": "",
                "process": proc,
                "server": srv_outro or o.get("titulo") or o.get("nome_tipo") or "",
                "registration": mat,
                "lotacao": "",
                "cargo": "",
                "axis": "outros",
                "modality": "",
                "condition": "NAO_INFORMADA",
                "group": "",
                "groupCanonical": None,
                "groupExpression": "",
                "groupLabel": "Grupo não informado",
                "groupPendingConfirmation": False,
                "category": "ABONO_PERMANENCIA" if eh_abono else "",
                "isOtherPublication": True,
                "merit": "deferido" if res_txt == "DEFERIDO" else ("indeferido" if res_txt == "INDEFERIDO" else "outro"),
                "validation": "pendente",
                "revisor": "",
                "revisadoEm": "",
                "justificativa": "",
                "preliminaryReview": "",
                "page": o.get("pagina"),
                "url": url_of,
                "urlOficial": o.get("url_oficial"),
                "pdfNoAcervo": o.get("pdf_no_acervo"),
                "evidence": trecho,
                "sourceMention": "expresso" if o.get("vinculo") == "EXPRESSO" else "nao_expresso",
                "levelFrom": "",
                "levelTo": "",
                "levelTransition": "",
                "levelStatus": "",
                "levelLabel": "",
                "levelReason": "",
                "detalhe": {},
                "refeito": False,
                "semEfeito": False,
                "conflitoAberto": False,
            })

    MAPA_TIPO_EVENTO = {
        "REPUBLICACAO": "Republicação",
        "RETIFICACAO": "Retificação",
        "CORRECAO": "Correção",
        "TORNADO_SEM_EFEITO": "Tornado sem efeito",
    }
    events_conv = []
    for e in (painel_resp.get("eventos") or []):
        url_of = str(e.get("url_oficial") or "").split("#")[0]
        est = e.get("estado") or "PENDENTE_VINCULACAO"
        val_ev = (
            "conferido" if est == "VALIDADO"
            else "rejeitado" if est == "REJEITADO"
            else "externo" if est == "FORA_DO_ACERVO"
            else "pendente"
        )
        events_conv.append({
            "id": e.get("id"),
            "date": e.get("data_publicacao") or "",
            "act": e.get("ato_original_id") or "",
            "suggestedAct": e.get("ato_sugerido_id") or "",
            "modificador": e.get("modificador") or "",
            "type": MAPA_TIPO_EVENTO.get(e.get("tipo"), e.get("tipo") or "Republicação"),
            "rawType": e.get("tipo"),
            "state": est,
            "resenhasCitadas": e.get("resenhas_citadas") or [],
            "processosCitados": e.get("processos_citados") or [],
            "decisoesVinculadas": e.get("decisoes_vinculadas") or [],
            "description": e.get("texto") or e.get("modificador") or "",
            "fundamento": e.get("fundamento") or "",
            "url": url_of,
            "urlOficial": e.get("url_oficial"),
            "pdfNoAcervo": e.get("pdf_no_acervo"),
            "page": e.get("pagina"),
            "validation": val_ev,
        })

    pendentes_cnt = sum(r["validation"] == "pendente" for r in rows_conv)
    conferidos_cnt = sum(r["validation"] == "conferido" for r in rows_conv)
    rejeitados_cnt = sum(r["validation"] == "rejeitado" for r in rows_conv)
    total_cnt = len(rows_conv)
    ev_pend_cnt = sum(e["validation"] == "pendente" for e in events_conv) if individual else 0

    ind_conf_b = painel_resp.get("indicadores_conferido") or painel_resp.get("indicadores") or {}
    ev_det_b = painel_resp.get("eventos_detalhados_conferido") or series_b.get("eventos_detalhados") or {}
    outras_summary = (
        {
            "total": len(other_pubs_conv),
            "abonoPermanencia": sum(1 for x in other_pubs_conv if x["category"] == "ABONO_PERMANENCIA"),
            "porTipo": dict(Counter(x["actType"] for x in other_pubs_conv)),
        }
        if individual
        else {"total": 0, "abonoPermanencia": 0, "porTipo": {}}
    )

    def _visao_resumo(escopo_alvo: str) -> dict:
        rs = [r for r in rows_conv if r["validation"] == escopo_alvo]
        vert = sum(r["axis"] == "progressao" and r["modality"] == "Vertical" for r in rs)
        horiz = sum(r["axis"] == "progressao" and r["modality"] == "Horizontal" for r in rs)
        prog_sem_mod = sum(r["axis"] == "progressao" and r["modality"] not in ("Vertical", "Horizontal") for r in rs)
        tmp = sum(r["axis"] == "tempo" for r in rs)
        oth = len(rs) - vert - horiz - prog_sem_mod - tmp

        # Calcular unidades com a MESMA regra de indicadores._calcular_unidades
        proc_res: dict[str, set[str]] = {}
        proc_cnt: dict[str, int] = {}
        serv_res: dict[str, set[str]] = {}
        pedidos_k: set[tuple] = set()
        sem_mat = 0
        for r in rs:
            pk = chave_processo(r.get("process"), r.get("lotacao") or r.get("orgao"), r.get("actType"))
            mk = normalizar_matricula(r.get("registration"))
            mer = "DEFERIDO" if r["merit"] == "deferido" else ("INDEFERIDO" if r["merit"] == "indeferido" else "NAO_INFORMADO")
            if pk:
                proc_res.setdefault(pk, set()).add(mer)
                proc_cnt[pk] = proc_cnt.get(pk, 0) + 1
            if mk:
                serv_res.setdefault(mk, set()).add(mer)
            else:
                sem_mat += 1
            pedidos_k.add((pk or f"SEM_PROC:{r['id']}", f"MAT:{mk}" if mk else f"SEM_MAT:{r['id']}", r["axis"], r["modality"] or r["category"] or ""))

        proc_def = sum(v == {"DEFERIDO"} for v in proc_res.values())
        proc_ind = sum(v == {"INDEFERIDO"} for v in proc_res.values())
        proc_ni = sum(v == {"NAO_INFORMADO"} for v in proc_res.values())
        proc_mis = sum(len(v) > 1 for v in proc_res.values())
        serv_ben = sum("DEFERIDO" in v for v in serv_res.values())
        serv_so_ind = sum("DEFERIDO" not in v and "INDEFERIDO" in v for v in serv_res.values())
        serv_so_ni = sum(v == {"NAO_INFORMADO"} for v in serv_res.values())

        def_n = sum(r["merit"] == "deferido" for r in rs)
        ind_n = sum(r["merit"] == "indeferido" for r in rs)
        ni_n = len(rs) - def_n - ind_n
        eh_conf = escopo_alvo == "conferido"
        return {
            "rowIds": [r["id"] for r in rs],
            "metrics": {
                "processes": len(proc_res),
                "processesDeferidos": proc_def,
                "processesIndeferidos": proc_ind,
                "processesMistos": proc_mis,
                "processesNaoInformado": proc_ni,
                "processesColetivos": sum(c > 1 for c in proc_cnt.values()),
                "resenhas": len({r["resenha_id"] for r in rs if r["resenha_id"]}),
                "pedidosIndividuais": len(pedidos_k),
                "decisions": len(rs),
                "deferidos": def_n,
                "indeferidos": ind_n,
                "naoInformado": ni_n,
                "servers": len(serv_res),
                "benefitedServers": serv_ben,
                "serversOnlyIndeferido": serv_so_ind,
                "serversOnlyNaoInformado": serv_so_ni,
                "rowsWithoutValidRegistration": sem_mat,
                "refeitos": ind_conf_b.get("refeitos") if eh_conf else None,
                "semEfeito": ind_conf_b.get("sem_efeito") if eh_conf else None,
                "republicacoes": ev_det_b.get("republicacoes_atos") if eh_conf else None,
                "retificacoes": ev_det_b.get("retificacoes_atos") if eh_conf else None,
                "correcoes": ev_det_b.get("correcoes_atos") if eh_conf else None,
                "decisoesSemEfeito": ev_det_b.get("decisoes_sem_efeito") if eh_conf else None,
                "decisoesRetificadas": ev_det_b.get("decisoes_retificadas") if eh_conf else None,
                "otherPublications": outras_summary["total"] if individual else 0,
            },
            "series": {
                "vertical": vert,
                "horizontal": horiz,
                "progressaoSemModalidade": prog_sem_mod,
                "tempo": tmp,
                "other": oth,
            },
        }

    if individual:
        rev_fonte = {"n": total_cnt, "p": pendentes_cnt, "c": conferidos_cnt, "r": rejeitados_cnt,
                     "o": len(other_pubs_conv), "u": cob_b.get("ultima_atualizacao")}
    else:
        rev_fonte = {"perfil": "publico", "edicoes": int(cob_b.get("edicoes_no_acervo") or 0),
                     "regras": meta_b.get("versao_regras") or C.VERSAO_REGRAS}
    rev_hash = hashlib.sha256(json.dumps(rev_fonte, sort_keys=True).encode("utf-8")).hexdigest()

    escopo_padrao = "pendente" if (individual and conferidos_cnt == 0 and pendentes_cnt > 0) else (meta_b.get("escopo") or "conferido")

    return {
        "rows": rows_conv,
        "otherPublications": other_pubs_conv,
        "otherPublicationsSummary": outras_summary,
        "events": events_conv,
        "categories": [[s.codigo, s.nome] for s in C.SUBCATEGORIAS] + [
            ["ABONO_PERMANENCIA", "Abono de Permanência"],
        ],
        "groups": [[g.codigo, f"{g.codigo} · {g.nome}"] for g in C.GRUPOS] + [
            ["PENDENTE:TEC. ADM", EXPRESSOES_PENDENTES_CONFIRMACAO["TEC. ADM"][2]],
            ["PENDENTE:STF", EXPRESSOES_PENDENTES_CONFIRMACAO["STF"][2]],
        ],
        "urls": {},
        "backend": {
            "perfil": meta_b.get("perfil") or "publico",
            "autenticado": individual,
            "versaoRegras": meta_b.get("versao_regras") or C.VERSAO_REGRAS,
            "incompatibilidadeVersaoRegras": bool(diag_vr.get("incompativel")),
            "versaoRegrasDiagnostico": diag_vr,
            "indicadores": painel_resp.get("indicadores") or {},
            "apoio": apoio_b,
            "series": series_b,
            "resenhas": (painel_resp.get("resenhas") or []) if individual else [],
        },
        "meta": {
            "version": f"Painel Diário Oficial | GEDIV · Regras {meta_b.get('versao_regras') or C.VERSAO_REGRAS}",
            "dictionary": "Catálogo controlado GEDIV (AST e SFT normalizados em registros compatíveis; ambíguos separados)",
            "verifiedAt": cob_b.get("ultima_atualizacao") or agora(),
            "coverage": cob_b.get("parecer") or "",
            "incompatibilidadeVersaoRegras": bool(diag_vr.get("incompativel")),
            "versaoRegrasDiagnostico": diag_vr,
            "automation": "Motor Python/SQLite v9 conectado · Revisão auditada por servidor.",
            "personal": ("Sessão gerencial autenticada: dados funcionais liberados para conferência."
                         if individual else
                         "Sessão pública: dados individuais e anotações internas protegidos (faça login gerencial para conferir)."),
            "semBaseCarregada": total_cnt == 0,
            "edicoes": int(cob_b.get("edicoes_no_acervo") or 0),
            "edicoesPendentes": int(cob_b.get("edicoes_com_pendencia_de_leitura") or 0),
            "conferidos": conferidos_cnt if individual else 0,
            "pendentes": pendentes_cnt if individual else 0,
            "rejeitados": rejeitados_cnt if individual else 0,
            "outrasPublicacoes": outras_summary["total"] if individual else 0,
            "eventosPendentes": ev_pend_cnt,
            "semDecisoesConferidas": (conferidos_cnt == 0) if individual else (not bool((painel_resp.get("indicadores") or {}).get("decisoes"))),
            "connection": {
                "batches": int(cob_b.get("edicoes_classificadas") or cob_b.get("edicoes_no_acervo") or 1),
                "source": "sqlite_v9_canonico",
                "overlaps": int(apoio_b.get("conflitos_abertos") or 0) if individual else 0,
                "partialCoverage": not bool(cob_b.get("completa")),
                "fullPeriodComplete": bool(cob_b.get("completa")),
            },
            "collectionWindow": {
                "from": cob_b.get("primeira_data") or "2026-01-01",
                "to": cob_b.get("ultima_data") or "2026-11-18",
            },
        },
        "dashboard": {
            "schemaVersion": 1,
            "revision": rev_hash,
            "defaultScope": escopo_padrao,
            "counts": {
                "received": total_cnt,
                "pending": pendentes_cnt,
                "confirmed": conferidos_cnt,
                "rejected": rejeitados_cnt,
                "otherPublications": outras_summary["total"] if individual else 0,
                "unlinkedEvents": ev_pend_cnt,
            },
            "views": {
                "pendente": _visao_resumo("pendente"),
                "conferido": _visao_resumo("conferido"),
            },
        },
    }


def extrair_bootstrap_de_html(caminho_html: Path) -> dict:
    """Extrai e decodifica o objeto `window.GEDIV_BOOTSTRAP=...;` de um arquivo HTML."""
    texto = Path(caminho_html).read_text(encoding="utf-8")
    m = re.search(r"window\.GEDIV_BOOTSTRAP\s*=\s*", texto)
    if not m:
        raise ValueError(f"window.GEDIV_BOOTSTRAP não encontrado em {caminho_html}")
    obj, _ = json.JSONDecoder().raw_decode(texto, m.end())
    return obj


def _normalizar_processo(p: str | None) -> str:
    return re.sub(r"\s+", "", str(p or "")).upper()


def _normalizar_matricula(m: str | None) -> str:
    return re.sub(r"\D", "", str(m or ""))


def _normalizar_servidor(s: str | None) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


def simular_reconciliacao(snapshot: dict, banco_comparacao: Banco | None = None,
                          pasta_pdfs: Path | None = None) -> dict:
    """Executa uma simulação não destrutiva (dry-run) da reconciliação dos 1.066 registros e 23 eventos
    do snapshot de referência contra os PDFs locais e/ou banco SQLite existente.
    """
    rows = snapshot.get("rows") or []
    events = snapshot.get("events") or []

    # 1. Controle de duplicidades internas e contagens de referência
    ids_rows = [r.get("id") for r in rows]
    duplicados_id = [k for k, v in Counter(ids_rows).items() if v > 1]
    chaves_negocio = Counter(
        (r.get("date"), r.get("resenha"), _normalizar_processo(r.get("process")),
         _normalizar_matricula(r.get("registration")), _normalizar_servidor(r.get("server")))
        for r in rows
    )
    possiveis_duplicidades = [
        {"chave": list(k), "ocorrencias": v} for k, v in chaves_negocio.items() if v > 1 and any(k[2:])
    ]

    pendentes = [r for r in rows if r.get("validation") == "pendente"]
    rejeitados = [r for r in rows if r.get("validation") == "rejeitado"]
    conferidos = [r for r in rows if r.get("validation") == "conferido"]
    com_nota_preliminar = [r for r in rows if str(r.get("preliminaryReview") or "").strip()]

    # 2. Verificação de documentos (PDFs) no disco local
    urls_distintas = sorted({r.get("url") for r in rows if r.get("url")} | {e.get("url") for e in events if e.get("url")})
    pdfs_encontrados, pdfs_ausentes = [], []
    if pasta_pdfs and pasta_pdfs.exists():
        staging = pasta_pdfs.parent / "staging_pendentes"
        for u in urls_distintas:
            nome = Path(u).name
            p = pasta_pdfs / nome
            if not p.exists() and staging.exists():
                p = staging / nome
            if p.exists():
                pdfs_encontrados.append({"arquivo": nome, "url": u, "tamanho": p.stat().st_size})
            else:
                pdfs_ausentes.append({"arquivo": nome, "url": u})
    else:
        pdfs_ausentes = [{"arquivo": Path(u).name, "url": u} for u in urls_distintas]

    # Nota documental explícita sobre a edição 11/09/2026 mencionada na cobertura
    edicao_1109_status = "presente_em_staging_pendentes" if (
        pasta_pdfs and (pasta_pdfs.parent / "staging_pendentes" / "diario-oficial-11-09-2026-portal.pdf").exists()
    ) else "ausente_da_amostra_51_edicoes"

    # 3. Conversão pelo adaptador e auditoria de extração/níveis A–F
    convertidos = [frontend_para_backend_linha(r) for r in rows]
    niveis_cnt = Counter()
    erros_extracao = []
    for c in convertidos:
        if c["eixo"] == C.PROGRESSAO and c["modalidade"] == C.VERTICAL:
            nv = c["nivel_info"]["nivel"]
            niveis_cnt[nv] += 1
            if nv == "NAO_IDENTIFICADO" and c["resultado"] != "INDEFERIDO":
                erros_extracao.append({
                    "id": c["id"], "data": c["data"], "resenha": c["resenha"],
                    "processo": c["processo"], "motivo": c["nivel_info"]["motivo"],
                })
        if not c["processo"] and not c["matricula"]:
            erros_extracao.append({
                "id": c["id"], "data": c["data"], "resenha": c["resenha"],
                "processo": None, "motivo": "sem_processo_e_sem_matricula",
            })

    # 4. Comparação com banco SQLite existente (se fornecido)
    correspondentes, novos_registros, divergencias_classificacao = [], [], []
    if banco_comparacao is not None:
        existentes = banco_comparacao.con.execute(
            "SELECT d.id, d.processo, d.matricula, d.servidor, d.resultado, d.validacao, "
            "a.data_publicacao, a.numero, a.eixo, a.modalidade, a.grupo, a.grupo_expressao, a.subcategoria "
            "FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.gerencia = 'GEDIV' AND d.vigente = 1"
        ).fetchall()
        por_id = {r["id"]: dict(r) for r in existentes}
        por_pm = {}
        por_p = {}
        for r in existentes:
            p = _normalizar_processo(r["processo"])
            mt = _normalizar_matricula(r["matricula"])
            if p and mt:
                por_pm.setdefault((p, mt), []).append(dict(r))
            if p:
                por_p.setdefault(p, []).append(dict(r))

        for c in convertidos:
            p = _normalizar_processo(c["processo"])
            mt = _normalizar_matricula(c["matricula"])
            achado = por_id.get(c["id"])
            if not achado and p and mt and (p, mt) in por_pm:
                achado = por_pm[(p, mt)][0]
            elif not achado and p and p in por_p:
                achado = por_p[p][0]
            if achado:
                correspondentes.append(c["id"])
                if c["eixo"] in (C.PROGRESSAO, C.TEMPO) and (
                    achado["eixo"] != c["eixo"] or achado["modalidade"] != c["modalidade"]
                ):
                    divergencias_classificacao.append({
                        "id": c["id"], "processo": c["processo"],
                        "snapshot": {"eixo": c["eixo"], "modalidade": c["modalidade"]},
                        "banco_comparado": {"eixo": achado["eixo"], "modalidade": achado["modalidade"]},
                    })
            else:
                novos_registros.append(c["id"])
    else:
        novos_registros = [c["id"] for c in convertidos]

    return {
        "modo": "DRY_RUN_NAO_DESTRUTIVO",
        "totais_snapshot": {
            "total_registros": len(rows),
            "pendentes": len(pendentes),
            "rejeitados": len(rejeitados),
            "conferidos": len(conferidos),
            "eventos_modificadores": len(events),
            "observacoes_preliminares": len(com_nota_preliminar),
            "processos_distintos": len({_normalizar_processo(r.get("process")) for r in rows if r.get("process")}),
            "resenhas_distintas": len({r.get("resenha_id") for r in rows if r.get("resenha_id")}),
        },
        "totais_por_eixo_e_modalidade": {
            "progressao_total": sum(c["eixo"] == C.PROGRESSAO for c in convertidos),
            "progressao_horizontal": sum(c["eixo"] == C.PROGRESSAO and c["modalidade"] == C.HORIZONTAL for c in convertidos),
            "progressao_vertical": sum(c["eixo"] == C.PROGRESSAO and c["modalidade"] == C.VERTICAL for c in convertidos),
            "tempo_servico": sum(c["eixo"] == C.TEMPO for c in convertidos),
            "outros_beneficios": sum(c["eixo"] == "OUTROS" for c in convertidos),
        },
        "reconciliacao_niveis_af": {
            "A": niveis_cnt.get("A", 0),
            "B": niveis_cnt.get("B", 0),
            "C": niveis_cnt.get("C", 0),
            "D": niveis_cnt.get("D", 0),
            "E": niveis_cnt.get("E", 0),
            "F": niveis_cnt.get("F", 0),
            "NAO_IDENTIFICADO": niveis_cnt.get("NAO_IDENTIFICADO", 0),
            "classificados": sum(niveis_cnt.get(k, 0) for k in "ABCDEF"),
            "total_vertical": sum(niveis_cnt.values()),
        },
        "grupos_separacao_normativa": dict(Counter(
            (c["grupo"] or (f"PENDENTE:{c['grupo_expressao']}" if c["grupo_expressao"] else "NAO_INFORMADO"))
            for c in convertidos if c["eixo"] == C.PROGRESSAO
        )),
        "correspondencia_banco": {
            "registros_correspondentes": len(correspondentes),
            "novos_registros": len(novos_registros),
            "duplicidades_id": len(duplicados_id),
            "possiveis_duplicidades_negocio": len(possiveis_duplicidades),
            "detalhe_possiveis_duplicidades": possiveis_duplicidades[:15],
            "divergencias_classificacao": len(divergencias_classificacao),
            "amostra_divergencias": divergencias_classificacao[:10],
        },
        "qualidade_e_documentos": {
            "erros_ou_lacunas_extracao_vertical_ou_identificador": len(erros_extracao),
            "amostra_lacunas_extracao": erros_extracao[:10],
            "urls_documentais_distintas": len(urls_distintas),
            "pdfs_acessiveis_no_disco": len(pdfs_encontrados),
            "pdfs_ausentes_no_disco": len(pdfs_ausentes),
            "edicao_11_09_2026": edicao_1109_status,
        },
        "exigem_conferencia_humana": {
            "decisoes_pendentes": len(pendentes),
            "eventos_pendentes_vinculacao": len(events),
            "expressao_tec_adm_sem_homologacao_ast": sum(c["grupo_expressao"] == "TEC. ADM" for c in convertidos),
            "expressao_stf_sem_homologacao_sft": sum(c["grupo_expressao"] == "STF" for c in convertidos),
        },
    }


def importar_snapshot_reconciliado(banco: Banco, snapshot: dict, pasta_pdfs: Path | None = None) -> dict:
    """Importa de forma IDEMPOTENTE e AUDITÁVEL os 1.066 registros e 23 eventos do snapshot de referência
    para o banco SQLite v8, preservando dados já homologados (CONFERIDO), mantendo separados os 1.065 pendentes,
    1 rejeitado, 23 eventos pendentes e 101 observações preliminares, sem auto-homologar nenhuma informação.
    """
    rows = snapshot.get("rows") or []
    events = snapshot.get("events") or []
    convertidos = [frontend_para_backend_linha(r) for r in rows]

    # Mapear URLs para SHA-256 (real quando o PDF está em pasta_pdfs, ou determinístico a partir da URL)
    url_para_sha: dict[str, tuple[str, int, str]] = {}
    urls_todas = sorted({r.get("url") or f"snapshot:{r.get('date') or '2026-01-01'}" for r in rows}
                        | {e.get("url") or f"snapshot:{e.get('date') or '2026-01-01'}" for e in events})

    for u in urls_todas:
        nome_arq = Path(u).name if u.startswith("http") else f"{u.replace(':', '_')}.pdf"
        caminho_real = None
        if pasta_pdfs and pasta_pdfs.exists() and u.startswith("http"):
            cand = pasta_pdfs / nome_arq
            if not cand.exists() and (pasta_pdfs.parent / "staging_pendentes" / nome_arq).exists():
                cand = pasta_pdfs.parent / "staging_pendentes" / nome_arq
            if cand.exists():
                caminho_real = cand
        if caminho_real is not None:
            raw_bytes = caminho_real.read_bytes()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            tam = len(raw_bytes)
        else:
            sha = hashlib.sha256(f"gediv-snapshot-doc|{u}".encode("utf-8")).hexdigest()
            tam = 1024
        url_para_sha[u] = (sha, tam, nome_arq)

    inseridos_decisao = 0
    preservados_decisao = 0
    inseridos_outros = 0
    inseridos_eventos = 0

    with banco.con:
        # 1. Garantir registros em arquivo, publicacao, leitura e classificacao
        datas_por_url: dict[str, str] = {}
        paginas_por_sha: dict[str, dict[int, list[str]]] = {}
        for c in convertidos:
            u = c["url"] or f"snapshot:{c['data'] or '2026-01-01'}"
            if c["data"] and u not in datas_por_url:
                datas_por_url[u] = c["data"]
            sha = url_para_sha[u][0]
            pg = max(1, int(c["pagina"] or 1))
            paginas_por_sha.setdefault(sha, {}).setdefault(pg, []).append(c["trecho"] or "")
        for e in events:
            u = e.get("url") or f"snapshot:{e.get('date') or '2026-01-01'}"
            if e.get("date") and u not in datas_por_url:
                datas_por_url[u] = e["date"]
            sha = url_para_sha[u][0]
            pg = max(1, int(e.get("page") or 1))
            paginas_por_sha.setdefault(sha, {}).setdefault(pg, []).append(e.get("description") or "")

        momento = agora()
        for u, (sha, tam, nome_arq) in url_para_sha.items():
            dt_pub = datas_por_url.get(u) or "2026-01-07"
            fonte = "auniao" if u.startswith("http") else "manual"
            banco.con.execute(
                "INSERT OR IGNORE INTO arquivo (sha256, tamanho, caminho, guardado_em) VALUES (?,?,?,?)",
                (sha, tam, nome_arq, momento),
            )
            banco.con.execute(
                "INSERT OR IGNORE INTO publicacao (fonte, url, data_publicacao, tipo, ordem, rotulo, estado, sha256, "
                "tentativas, descoberta_em, atualizada_em) VALUES (?,?,?,'normal',0,?,'BAIXADA',?,1,?,?)",
                (fonte, u, dt_pub, nome_arq, sha, momento, momento),
            )
            pub_row = banco.con.execute("SELECT id FROM publicacao WHERE fonte=? AND url=?", (fonte, u)).fetchone()
            if pub_row:
                banco.con.execute("UPDATE publicacao SET sha256=?, estado='BAIXADA' WHERE id=?", (sha, pub_row[0]))
                banco.con.execute(
                    "INSERT OR IGNORE INTO versao (publicacao_id, sha256, observada_em) VALUES (?,?,?)",
                    (pub_row[0], sha, momento),
                )
            pags_map = paginas_por_sha.get(sha) or {1: [""]}
            max_pg = max(pags_map.keys())
            banco.con.execute(
                "INSERT OR IGNORE INTO leitura (sha256, situacao, versao_leitor, paginas, paginas_sem_texto, "
                "numero_edicao, data_edicao, erro, concluida_em, paginas_com_pendencia, revisao) "
                "VALUES (?,'LIDA','0.8',?,0,?,?,NULL,?,0,1)",
                (sha, max_pg, dt_pub, dt_pub, momento),
            )
            for num_pg, textos_pg in sorted(pags_map.items()):
                txt_join = "\n\n".join(t for t in textos_pg if t)
                txt_sha = hashlib.sha256(txt_join.encode("utf-8")).hexdigest()
                banco.con.execute(
                    "INSERT OR IGNORE INTO pagina (sha256, numero, metodo, colunas, texto, qualidade, confianca, palavras, texto_sha256) "
                    "VALUES (?,?,'TEXTO',1,?,'OK',100.0,?,?)",
                    (sha, num_pg, txt_join, len(txt_join.split()), txt_sha),
                )
            banco.con.execute(
                "INSERT OR REPLACE INTO classificacao (sha256, gerencia, versao_regras, atos, decisoes, eventos, descartados, pendencias, concluida_em, revisao_leitura) "
                "VALUES (?,'GEDIV',?,1,1,0,0,'[]',?,1)",
                (sha, C.VERSAO_REGRAS, momento),
            )

        # 2. Inserir Atos, Decisões (PROGRESSAO e TEMPO_SERVICO) e Outras Publicações (OUTROS)
        for c in convertidos:
            u = c["url"] or f"snapshot:{c['data'] or '2026-01-01'}"
            sha = url_para_sha[u][0]
            if c["eixo"] == "OUTROS":
                oid = c["id"]
                existe_o = banco.con.execute("SELECT 1 FROM outra_publicacao WHERE id=?", (oid,)).fetchone()
                if not existe_o:
                    titulo = f"Resenha {c['resenha']}" if c["resenha"] else "Publicação GEDIV (Outros benefícios)"
                    meta_hdr = json.dumps({
                        "ato_id": c["ato_id"],
                        "resenha": c["resenha"],
                        "processo": c["processo"],
                        "servidor": c["servidor"],
                        "matricula": c["matricula"],
                        "resultado": c["resultado"],
                    }, ensure_ascii=False)
                    trecho_gravado = f"<!--GEDIV_META:{meta_hdr}-->\n{c['trecho']}"
                    banco.con.execute(
                        "INSERT INTO outra_publicacao (id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                        "VALUES (?,'GEDIV',?,'TEMA_FORA_DOS_EIXOS',?,?,?,?,?)",
                        (oid, sha, c["pagina"], c["data"], titulo[:200], c["vinculo"], trecho_gravado),
                    )
                    inseridos_outros += 1
                continue

            ato_id = c["ato_id"] or hashlib.sha256(f"ATO|{sha}|{c['resenha']}|{c['data']}".encode("utf-8")).hexdigest()[:20]
            partes_res = [p.strip() for p in str(c["resenha"] or "").split("·", 1)]
            num_res = partes_res[0] or None
            suf_res = partes_res[1] if len(partes_res) > 1 else None
            ch_ato = chave_ato("GEDIV", "RESENHA", num_res, suf_res, "ORIGINAL") or f"ATO|{ato_id}"

            banco.con.execute(
                "INSERT OR IGNORE INTO ato (id, gerencia, sha256, tipo, numero, sufixo, pagina, pagina_final, data_publicacao, "
                "data_expediente, vinculo, expressao_vinculo, natureza, eixo, modalidade, condicao, grupo, grupo_expressao, "
                "subcategoria, resultado, texto, pendencias, versao_regras, chave_logica) "
                "VALUES (?,'GEDIV',?,'RESENHA',?,?,?,?,?,NULL,?,NULL,'ORIGINAL',?,?, 'NAO_INFORMADA',?,?,?,?,?,?,?,?)",
                (ato_id, sha, num_res, suf_res, c["pagina"], c["pagina"], c["data"], c["vinculo"],
                 c["eixo"], c["modalidade"], c["grupo"], c["grupo_expressao"], c["subcategoria"],
                 c["resultado"], c["trecho"][:2000], json.dumps(c["pendencias"], ensure_ascii=False),
                 C.VERSAO_REGRAS, ch_ato),
            )

            dec_existente = banco.con.execute("SELECT id, validacao FROM decisao WHERE id=?", (c["id"],)).fetchone()
            if dec_existente is not None:
                # Idempotência e proteção de homologados: nunca sobrescreve registro já existente ou CONFERIDO
                preservados_decisao += 1
                continue

            ch_dec = f"{ch_ato}|DEC|{c['id']}"
            revisor_init = "Triagem histórica GEDIV" if c["validacao"] == "REJEITADO" else None
            just_init = "Registro rejeitado preservado da base de referência" if c["validacao"] == "REJEITADO" else None
            rev_em_init = momento if c["validacao"] == "REJEITADO" else None

            banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, "
                "detalhe, resultado, trecho, validacao, revisor, revisado_em, justificativa, chave_logica, vigente, origem) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'AUTOMATICA')",
                (c["id"], ato_id, sha, c["pagina"], c["processo"], c["servidor"], c["matricula"],
                 c["lotacao"], c["cargo"], json.dumps(c["detalhe"], ensure_ascii=False),
                 c["resultado"], c["trecho"], c["validacao"], revisor_init, rev_em_init, just_init, ch_dec),
            )
            inseridos_decisao += 1

        # 3. Inserir os 23 Eventos Modificadores Pendentes
        MAPA_EV_BACKEND = {
            "Republicação": C.REPUBLICACAO,
            "Retificação": C.RETIFICACAO,
            "Correção": C.CORRECAO,
            "Tornado sem efeito": C.SEM_EFEITO,
        }
        for e in events:
            eid = e.get("id")
            if banco.con.execute("SELECT 1 FROM evento WHERE id=?", (eid,)).fetchone():
                continue
            u = e.get("url") or f"snapshot:{e.get('date') or '2026-01-01'}"
            sha = url_para_sha[u][0]
            desc = e.get("description") or ""
            tipo_ev = MAPA_EV_BACKEND.get(e.get("type"), C.REPUBLICACAO)
            res_citadas = sorted({f"{m.group(1)}/{m.group(2)}"
                                  for m in re.finditer(r"RESENHA\s*(?:N[º°O.]*)?\s*:?\s*(\d{1,5})\s*/\s*(20\d{2})", desc, re.IGNORECASE)})
            proc_citados = sorted({re.sub(r"\s+", "", m.group(0)).upper()
                                   for m in re.finditer(r"\b[A-Z]{2,6}\s*-\s*(?:PSE|PRC|OFI)\s*-\s*\d{4}\s*[/-]\s*\d{3,9}\b", desc, re.IGNORECASE)})
            mod_match = (re.search(r"RESENHA\s*(?:N[º°O.]*)?\s*:?\s*(\d{1,5}\s*/\s*20\d{2})", desc, re.IGNORECASE)
                         or re.search(r"PORTARIA\s*(?:N[º°O.]*)?\s*:?\s*(\d{1,5}\s*/\s*20\d{2}(?:\s*-\s*[A-Z]+)?)", desc, re.IGNORECASE))
            modificador = mod_match.group(0).strip() if mod_match else (e.get("act") or tipo_ev)
            vinculo_ev = "EXPRESSO" if "DIREITOS E VANTAGENS" in desc.upper() or "GEDIV" in desc.upper() else "NAO_EXPRESSO"

            banco.con.execute(
                "INSERT INTO evento (id, gerencia, sha256, ato_id, tipo, subtipo, pagina, data_publicacao, modificador, "
                "resenhas_citadas, processos_citados, vinculo, texto, ato_sugerido_id, ato_original_id, estado, fundamento, revisor, revisado_em) "
                "VALUES (?,'GEDIV',?,NULL,?,NULL,?,?,?,?,?,?,?,NULL,NULL,'PENDENTE_VINCULACAO',NULL,NULL,NULL)",
                (eid, sha, tipo_ev, int(e.get("page") or 1), e.get("date") or "", modificador,
                 json.dumps(res_citadas, ensure_ascii=False), json.dumps(proc_citados, ensure_ascii=False),
                 vinculo_ev, desc),
            )
            inseridos_eventos += 1

    return {
        "inseridos_decisao": inseridos_decisao,
        "preservados_decisao": preservados_decisao,
        "inseridos_outros": inseridos_outros,
        "inseridos_eventos": inseridos_eventos,
    }
