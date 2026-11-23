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
import os
import re
import unicodedata
from pathlib import Path

from ..gerencias.gediv import catalogo as C, processo as gediv_processo
from ..nucleo.banco import Banco, agora, chave_processo, normalizar_matricula, normalizar_processo
from . import documental, projecao

GERENCIA_PERFIL, PUBLICO = projecao.GERENCIA, projecao.PUBLICO
LIMIAR_PUBLICO = 5
ARQUIVO_SNAPSHOT_PUBLICO = "snapshot_publico.json"
CARTOES = ("processos", "resenhas", "decisoes", "deferidos", "indeferidos", "refeitos", "sem_efeito")
ROTULOS = {"processos": "Total de processos", "resenhas": "Total de resenhas", "decisoes": "Total de decisões individuais",
           "deferidos": "Deferidos", "indeferidos": "Indeferidos", "refeitos": "Refeitos", "sem_efeito": "Tornados sem efeito"}
NIVEIS_VERTICAIS = ("A", "B", "C", "D", "E", "F", "NAO_IDENTIFICADO")
SITUACOES_SEM_NIVEL_VERTICAL = ("INDEFERIDO", "NAO_DETERMINADO", "INCONSISTENTE", "NAO_APLICA")
SITUACOES_NIVEL_VERTICAL = ("A", "B", "C", "D", "E", "F", *SITUACOES_SEM_NIVEL_VERTICAL)
FILTROS_NIVEL_ACEITOS = frozenset((*NIVEIS_VERTICAIS, *SITUACOES_SEM_NIVEL_VERTICAL))
_CLASSES_VALIDAS = frozenset("ABCDEF")
META_SITUACAO_NIVEL = {
    "A": ("Nível A", "Progressão vertical deferida com nível de destino A efetivado."),
    "B": ("Nível B", "Progressão vertical deferida com nível de destino B efetivado."),
    "C": ("Nível C", "Progressão vertical deferida com nível de destino C efetivado."),
    "D": ("Nível D", "Progressão vertical deferida com nível de destino D efetivado."),
    "E": ("Nível E", "Progressão vertical deferida com nível de destino E efetivado."),
    "F": ("Nível F", "Progressão vertical deferida com nível de destino F efetivado."),
    "INDEFERIDO": ("Indeferidas (sem nível)", "Progressão vertical indeferida; não houve concessão nem efetivação de nível."),
    "NAO_DETERMINADO": ("Deferidas sem nível", "Progressão vertical deferida cujo nível A–F não constava na publicação ou não pôde ser extraído."),
    "INCONSISTENTE": ("Inconsistência A–F", "Sequência ou classe A–F inconsistente (ex.: regressão D → B, níveis iguais C → C ou letra fora de A–F)."),
    "NAO_APLICA": ("A–F não se aplica", "Carreira ou publicação vertical estruturada fora da escala A–F (ex.: níveis romanos II → III ou numéricos)."),
}
_RE_TOKEN_NAO_AF = re.compile(r"^(?:N[ÍI]VEL\s*)?(?:I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2})$", re.IGNORECASE)
_RE_EVOLUCAO_NAO_AF = re.compile(
    r"(?:N[ÍI]VEL\s*(?:I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2})|\b(?:I{1,3}|IV|V|VI{1,3}|IX|X)\s+(?:I{1,3}|IV|V|VI{1,3}|IX|X)\b|PADR[ÃA]O|REFER[ÊE]NCIA)",
    re.IGNORECASE,
)
_RE_TRECHO_NIVEL_NUM = re.compile(
    r"\b(N[ÍI]VEL\s*(?:I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2}))\s+(?:PARA\s+|->\s*|→\s*)?(N[ÍI]VEL\s*(?:I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2}))\b",
    re.IGNORECASE,
)
_RE_TRECHO_ROMANO = re.compile(r"(?:^|[\s|\[])(I{1,3}|IV|V|VI{1,3}|IX|X)\s+(I{1,3}|IV|V|VI{1,3}|IX|X)\s*$")
_RE_TRECHO_PADRAO = re.compile(
    r"\b((?:PADR[ÃA]O|REFER[ÊE]NCIA)\s+[A-Z0-9-]+)\s+(?:PARA\s+|->\s*|→\s*)?((?:(?:PADR[ÃA]O|REFER[ÊE]NCIA)\s+)?[A-Z0-9-]+)\b",
    re.IGNORECASE,
)
_RE_TRECHO_FORA_AF = re.compile(
    r"(?:^|[\s|\[])(?:CLASSE\s+)?([A-F])\s+(?:PARA\s+|->\s*|→\s*)?([G-H])\s*$|(?:^|[\s|\[])(?:CLASSE\s+)?([G-H])\s+(?:PARA\s+|->\s*|→\s*)?([A-H])\s*$"
)


def _sem_acento(valor) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(valor or "")) if not unicodedata.combining(c)).lower()


def _lista(valor) -> list[str]:
    if valor is None or valor == "":
        return []
    return [v for v in (valor if isinstance(valor, (list, tuple)) else str(valor).split(",")) if v]


def _ret_nivel(
    *,
    categoria: str | None,
    nivel: str | None,
    motivo: str | None,
    classe_anterior: str | None = None,
    classe_posterior: str | None = None,
    transicao: str | None = None,
    observacao: str | None = None,
) -> dict:
    rot, desc = META_SITUACAO_NIVEL.get(categoria or "", (None, None))
    return {
        "classe_anterior": classe_anterior,
        "classe_posterior": classe_posterior,
        "nivel": nivel,
        "categoria": categoria,
        "rotulo": rot,
        "descricao": desc,
        "transicao": transicao,
        "motivo": motivo,
        "observacao": observacao,
    }


def classificar_nivel_vertical(linha: dict) -> dict:
    """Classifica toda Progressão Vertical em 5 situações mutuamente exclusivas e exaustivas:
    1. Deferida com nível de destino A–F efetivado (`categoria` in 'A'..'F', `nivel` == `categoria`)
    2. Indeferida, sem nível efetivado (`categoria='INDEFERIDO'`)
    3. Deferida cujo nível A–F não pôde ser determinado (`categoria='NAO_DETERMINADO'`)
    4. Inconsistência na identificação ou sequência A–F (`categoria='INCONSISTENTE'`)
    5. Estrutura em que a escala A–F comprovadamente não se aplica (`categoria='NAO_APLICA'`)

    Mantém `nivel='NAO_IDENTIFICADO'` nas categorias 2..5 para retrocompatibilidade com consumidores legados.
    """
    if linha.get("eixo") != C.PROGRESSAO or linha.get("modalidade") != C.VERTICAL:
        return _ret_nivel(categoria=None, nivel=None, motivo=None)
    if linha.get("resultado") == "INDEFERIDO":
        return _ret_nivel(
            categoria="INDEFERIDO",
            nivel="NAO_IDENTIFICADO",
            motivo="indeferido_sem_classe",
            observacao="Pedido indeferido; não houve concessão nem efetivação de nível A–F.",
        )
    det = linha.get("detalhe") if isinstance(linha.get("detalhe"), dict) else {}
    ca = str(det.get("classe_anterior") or "").strip().upper()
    cp = str(det.get("classe_posterior") or "").strip().upper()
    if ca in _CLASSES_VALIDAS and cp in _CLASSES_VALIDAS:
        if ca < cp:
            return _ret_nivel(
                categoria=cp,
                nivel=cp,
                motivo="ok",
                classe_anterior=ca,
                classe_posterior=cp,
                transicao=f"{ca} → {cp}",
                observacao=f"Progressão vertical efetivada de {ca} para {cp}.",
            )
        return _ret_nivel(
            categoria="INCONSISTENTE",
            nivel="NAO_IDENTIFICADO",
            motivo="anomalia_ordem_ou_igual",
            classe_anterior=ca,
            classe_posterior=cp,
            transicao=f"{ca} → {cp}",
            observacao=f"Sequência sem avanço ou invertida ({ca} → {cp}); mantida para conferência.",
        )

    if ca or cp:
        if (not ca or _RE_TOKEN_NAO_AF.match(ca)) and (not cp or _RE_TOKEN_NAO_AF.match(cp)):
            tr_nao_af = f"{ca} → {cp}" if (ca and cp) else (ca or cp)
            return _ret_nivel(
                categoria="NAO_APLICA",
                nivel="NAO_IDENTIFICADO",
                motivo="estrutura_nao_aplica",
                transicao=tr_nao_af,
                observacao=f"Publicação estruturada fora da escala A–F ({tr_nao_af}).",
            )
        tr_inc = f"{ca or '?'} → {cp or '?'}"
        return _ret_nivel(
            categoria="INCONSISTENTE",
            nivel="NAO_IDENTIFICADO",
            motivo="classe_fora_faixa_ou_incompleta",
            classe_anterior=ca or None,
            classe_posterior=cp or None,
            transicao=tr_inc,
            observacao=f"Classe fora da faixa A–F ou par incompleto ({tr_inc}).",
        )

    estrutura = str(det.get("estrutura_nivel") or "").strip().upper()
    evolucao_lida = str(det.get("evolucao_lida") or "").strip()
    niv_ant = str(det.get("nivel_anterior") or "").strip()
    niv_atu = str(det.get("nivel_atual") or "").strip()
    if (
        estrutura in ("NAO_AF", "NIVEL_ROMANO", "NIVEL_NUMERICO", "PADRAO", "REFERENCIA")
        or niv_ant
        or niv_atu
        or (evolucao_lida and _RE_EVOLUCAO_NAO_AF.search(evolucao_lida))
    ):
        if niv_ant and niv_atu:
            tr_na = f"{niv_ant} → {niv_atu}"
        elif evolucao_lida:
            toks = evolucao_lida.split()
            tr_na = f"{toks[0]} → {toks[1]}" if len(toks) == 2 else evolucao_lida
        else:
            tr_na = niv_ant or niv_atu or None
        return _ret_nivel(
            categoria="NAO_APLICA",
            nivel="NAO_IDENTIFICADO",
            motivo="estrutura_nao_aplica",
            transicao=tr_na,
            observacao=(
                f"Estrutura fora da escala A–F ({tr_na})."
                if tr_na else "Carreira/estrutura não utiliza níveis A–F."
            ),
        )

    trecho = str(linha.get("trecho") or "")
    idx = trecho.upper().find("LINHA")
    seg = trecho[idx:] if idx >= 0 else trecho
    seg = re.sub(r"Di[aá]rio\s+Ofi\s*cial[\s\S]*$", "", seg, flags=re.IGNORECASE)
    seg = re.sub(r"PUBLIQUE-SE[\s\S]*$", "", seg, flags=re.IGNORECASE)
    limpo_bruto = re.sub(r"\s+", " ", seg.replace("\r", " ").replace("\n", " ")).strip()
    limpo_bruto = re.sub(r"[\s$*%]+$", "", limpo_bruto).strip()
    limpo = re.sub(r"\s+\d{1,2}$", "", limpo_bruto).strip()
    m = (re.search(r"(?:^|[\s|\[])([A-F])\s+([A-F])\s*$", limpo, re.IGNORECASE)
         or re.search(r"(?:^|[\s|\[])([A-F])([A-F])\s*$", limpo, re.IGNORECASE)
         or re.search(r"\bTECNICO\s+['\"]?\s*([A-F])\s+([A-F])(?:\s+[A-Z]+)*\s+ADMINISTRATIVO\s*$", limpo, re.IGNORECASE))
    if m:
        fa, fp = m.group(1).upper(), m.group(2).upper()
        if fa < fp:
            return _ret_nivel(
                categoria=fp,
                nivel=fp,
                motivo="ok",
                classe_anterior=fa,
                classe_posterior=fp,
                transicao=f"{fa} → {fp}",
                observacao=f"Progressão vertical efetivada de {fa} para {fp}.",
            )
        return _ret_nivel(
            categoria="INCONSISTENTE",
            nivel="NAO_IDENTIFICADO",
            motivo="anomalia_ordem_ou_igual",
            classe_anterior=fa,
            classe_posterior=fp,
            transicao=f"{fa} → {fp}",
            observacao=f"Sequência sem avanço ou invertida ({fa} → {fp}); mantida para conferência.",
        )

    m_num = _RE_TRECHO_NIVEL_NUM.search(limpo_bruto)
    m_rom = _RE_TRECHO_ROMANO.search(limpo)
    m_pad = _RE_TRECHO_PADRAO.search(limpo_bruto)
    if m_num or m_rom or m_pad:
        mg = m_num or m_rom or m_pad
        tr_na = f"{mg.group(1).upper()} → {mg.group(2).upper()}"
        return _ret_nivel(
            categoria="NAO_APLICA",
            nivel="NAO_IDENTIFICADO",
            motivo="estrutura_nao_aplica",
            transicao=tr_na,
            observacao=f"Publicação estruturada fora da escala A–F ({tr_na}).",
        )

    m_fora = _RE_TRECHO_FORA_AF.search(limpo)
    if m_fora:
        fa = (m_fora.group(1) or m_fora.group(3) or "").upper()
        fp = (m_fora.group(2) or m_fora.group(4) or "").upper()
        return _ret_nivel(
            categoria="INCONSISTENTE",
            nivel="NAO_IDENTIFICADO",
            motivo="classe_fora_faixa_ou_incompleta",
            classe_anterior=fa or None,
            classe_posterior=fp or None,
            transicao=f"{fa} → {fp}",
            observacao=f"Classe fora da faixa A–F ({fa} → {fp}); mantida para conferência.",
        )

    return _ret_nivel(
        categoria="NAO_DETERMINADO",
        nivel="NAO_IDENTIFICADO",
        motivo="ocr_ou_incompleto",
        observacao="Nível A–F ausente na publicação ou não extraído do texto.",
    )


def _chave_grupo(linha: dict) -> str:
    """Chave de agrupamento que preserva a separação normativa de expressões sem grupo homologado (TEC. ADM, STF)."""
    if linha.get("grupo"):
        return linha["grupo"]
    exp = str(linha.get("grupo_expressao") or "").strip().upper()
    if re.search(r"\bTEC\.?\s*ADM\b", exp):
        return "PENDENTE:TEC. ADM"
    if re.search(r"\bSTF\b", exp):
        return "PENDENTE:STF"
    return "NAO_INFORMADO"


def normalizar_filtros(bruto: dict, perfil: str) -> dict:
    grupos_aceitos = set(C.GRUPO_POR_CODIGO) | {"NAO_INFORMADO", "PENDENTE:TEC. ADM", "PENDENTE:STF"}
    nivel_bruto = (bruto.get("nivel") or "").strip().upper()
    if nivel_bruto == "NI":
        nivel_bruto = "NAO_IDENTIFICADO"
    f = {
        "escopo": bruto.get("escopo") if bruto.get("escopo") in ("conferido", "pendente") else "conferido",
        "inicio": bruto.get("inicio") or None, "fim": bruto.get("fim") or None,
        "eixo": bruto.get("eixo") if bruto.get("eixo") in C.EIXOS else None,
        "modalidade": bruto.get("modalidade") if bruto.get("modalidade") in C.MODALIDADES else None,
        "condicao": bruto.get("condicao") if bruto.get("condicao") in C.CONDICOES else None,
        "grupo": [g for g in _lista(bruto.get("grupo")) if g in grupos_aceitos],
        "nivel": nivel_bruto if nivel_bruto in FILTROS_NIVEL_ACEITOS else None,
        "subcategoria": [s for s in _lista(bruto.get("subcategoria")) if s in C.SUBCATEGORIA_POR_CODIGO or s == "SEM_SUBCATEGORIA"],
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
        "a.grupo_expressao, a.subcategoria, a.pendencias, a.chave_logica, "
        "a.gerencia AS gerencia_painel, SUBSTR(a.texto,1,1200) AS texto_identificacao, l.numero_edicao, l.data_edicao, "
        "EXISTS (SELECT 1 FROM conflito x WHERE x.estado = 'ABERTO' AND "
        "((x.alvo_tipo = 'decisao' AND x.alvo_id = d.id) OR (x.alvo_tipo = 'ato' AND x.alvo_id = a.id))) AS conflito_aberto "
        "FROM decisao d JOIN ato a ON a.id = d.ato_id "
        "JOIN leitura l ON l.sha256 = d.sha256 JOIN classificacao c ON c.sha256 = d.sha256 AND c.gerencia = a.gerencia "
        # Só a representação VIGENTE de cada decisão lógica (Etapa 05.3.3): cópias de outra versão do PDF, ou de uma
        # releitura, não contam duas vezes; correspondências ambíguas ficam fora até a gerência decidir.
        "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND l.situacao <> 'ERRO' AND c.versao_regras = ? "
        "AND (l.revisao IS NULL OR c.revisao_leitura IS l.revisao) "
        "ORDER BY a.data_publicacao DESC, a.pagina, d.rowid", (C.VERSAO_REGRAS,))
    linhas = []
    for l in consulta:
        linha = dict(l)
        linha.update(documental.identificar(linha))
        linha.pop("texto_identificacao")
        linha["detalhe"] = json.loads(linha["detalhe"] or "{}")
        linha["pendencias"] = json.loads(linha["pendencias"] or "[]")
        linha["nivel_info"] = classificar_nivel_vertical(linha)
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
    if f["grupo"]:
        if linha["eixo"] != C.PROGRESSAO:
            return False
        g_efetivo = linha["grupo"] or "NAO_INFORMADO"
        g_chave = _chave_grupo(linha)
        if g_efetivo not in f["grupo"] and g_chave not in f["grupo"]:
            return False
    if f.get("nivel"):
        if not (linha["eixo"] == C.PROGRESSAO and linha["modalidade"] == C.VERTICAL):
            return False
        info = linha.get("nivel_info") or classificar_nivel_vertical(linha)
        if f["nivel"] == "NAO_IDENTIFICADO":
            if info.get("nivel") != "NAO_IDENTIFICADO":
                return False
        elif info.get("categoria") != f["nivel"]:
            return False
    if f["subcategoria"]:
        sub_ef = linha["subcategoria"] or "SEM_SUBCATEGORIA"
        if not (linha["eixo"] == C.TEMPO and sub_ef in f["subcategoria"]):
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


def diagnostico_versao_regras(banco: Banco, perfil: str = PUBLICO) -> dict:
    """Inspeciona explicitamente a compatibilidade entre `C.VERSAO_REGRAS` do código e as versões
    gravadas em `classificacao`, evitando que uma incompatibilidade produza silenciosamente um painel vazio.

    Seguro por padrão (`perfil=PUBLICO`): no perfil público devolve apenas sinalização booleana e mensagem
    neutra, sem expor contagens exatas de decisões (inclusive pendentes) nem telemetria interna por versão.
    O diagnóstico técnico completo é reservado exclusivamente ao perfil `GERENCIA_PERFIL`."""
    linhas_v = banco.con.execute(
        "SELECT versao_regras, COUNT(*) AS n FROM classificacao WHERE gerencia = 'GEDIV' "
        "GROUP BY versao_regras ORDER BY versao_regras"
    ).fetchall()
    por_versao = {r["versao_regras"]: int(r["n"]) for r in linhas_v}
    versoes_banco = sorted(por_versao)
    edicoes_comp = por_versao.get(C.VERSAO_REGRAS, 0)
    edicoes_incomp = sum(n for v, n in por_versao.items() if v != C.VERSAO_REGRAS)
    incompativel = edicoes_incomp > 0
    if perfil != GERENCIA_PERFIL:
        return {
            "versao_codigo": C.VERSAO_REGRAS,
            "versoes_no_banco": [],
            "edicoes_por_versao": None,
            "compativel": not incompativel,
            "incompativel": incompativel,
            "edicoes_compativeis": None,
            "edicoes_incompativeis": None,
            "decisoes_afetadas": None,
            "mensagem": (
                "Incompatibilidade técnica de versão de regras detectada; os indicadores aguardam alinhamento interno."
                if incompativel else None
            ),
        }
    versoes_incomp = [v for v in versoes_banco if v != C.VERSAO_REGRAS]
    decisoes_afetadas = 0
    if incompativel:
        decisoes_afetadas = int(
            banco.con.execute(
                "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
                "JOIN leitura l ON l.sha256 = d.sha256 "
                "JOIN classificacao c ON c.sha256 = d.sha256 AND c.gerencia = a.gerencia "
                "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND l.situacao <> 'ERRO' AND c.versao_regras <> ?",
                (C.VERSAO_REGRAS,),
            ).fetchone()[0]
        )
    mensagem = None
    if incompativel:
        mensagem = (
            f"Incompatibilidade de versão de regras: o código exige '{C.VERSAO_REGRAS}', mas o banco contém "
            f"{', '.join(repr(v) for v in versoes_incomp)} em {edicoes_incomp} edição(ões) "
            f"({decisoes_afetadas} decisão(ões) vigentes bloqueadas até alinhamento ou reclassificação)."
        )
    return {
        "versao_codigo": C.VERSAO_REGRAS,
        "versoes_no_banco": versoes_banco,
        "edicoes_por_versao": por_versao,
        "compativel": not incompativel,
        "incompativel": incompativel,
        "edicoes_compativeis": edicoes_comp,
        "edicoes_incompativeis": edicoes_incomp,
        "decisoes_afetadas": decisoes_afetadas,
        "mensagem": mensagem,
    }


def cobertura(banco: Banco, perfil: str = PUBLICO) -> dict:
    um = lambda sql: banco.con.execute(sql).fetchone()[0]
    datas = banco.con.execute(
        "SELECT MIN(data_publicacao), MAX(data_publicacao) FROM publicacao WHERE sha256 IS NOT NULL").fetchone()
    edicoes = um("SELECT COUNT(*) FROM arquivo")
    diag_vr = diagnostico_versao_regras(banco, perfil=perfil)
    parecer = ("Nenhuma edição carregada." if not edicoes else
               f"Cobertura parcial: {edicoes} edição(ões) no acervo. O inventário completo do período não foi validado; "
               "ausência de registro nesta base não comprova ausência de publicação.")
    if diag_vr["incompativel"] and diag_vr["mensagem"]:
        parecer += " " + diag_vr["mensagem"]
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
        "incompatibilidade_versao_regras": diag_vr["incompativel"],
        "versao_regras_diagnostico": diag_vr,
        "parecer": parecer,
    }


def _calcular_unidades(linhas: list[dict], logico: dict) -> dict:
    """Fonte única de cálculo de unidades (publicações, processos, pedidos individuais, decisões e servidores).
    Garante partições matemáticas exaustivas (soma das categorias == total, erro zero)."""
    publicacoes_set = {logico.get(l["ato_id"], l["ato_id"]) for l in linhas}
    dec_def = sum(l["resultado"] == "DEFERIDO" for l in linhas)
    dec_ind = sum(l["resultado"] == "INDEFERIDO" for l in linhas)
    dec_ni = sum(l["resultado"] == "NAO_INFORMADO" for l in linhas)

    proc_res: dict[str, set[str]] = {}
    proc_linhas: dict[str, int] = {}
    proc_servs: dict[str, set[str]] = {}
    sem_processo = 0
    for l in linhas:
        pk = chave_processo(l.get("processo"), l.get("lotacao") or l.get("sufixo"), l.get("tipo"))
        if not pk:
            sem_processo += 1
            continue
        proc_res.setdefault(pk, set()).add(l["resultado"])
        proc_linhas[pk] = proc_linhas.get(pk, 0) + 1
        mk = normalizar_matricula(l.get("matricula"))
        proc_servs.setdefault(pk, set()).add(f"M:{mk}" if mk else f"L:{l['id']}")

    proc_def = sum(v == {"DEFERIDO"} for v in proc_res.values())
    proc_ind = sum(v == {"INDEFERIDO"} for v in proc_res.values())
    proc_ni = sum(v == {"NAO_INFORMADO"} for v in proc_res.values())
    proc_mistos = sum(len(v) > 1 for v in proc_res.values())
    proc_mistos_di = sum({"DEFERIDO", "INDEFERIDO"}.issubset(v) for v in proc_res.values())
    proc_coletivos = sum(proc_linhas[k] > 1 or len(proc_servs[k]) > 1 for k in proc_res)

    pedidos_keys = set()
    for l in linhas:
        pk = chave_processo(l.get("processo"), l.get("lotacao") or l.get("sufixo"), l.get("tipo")) or f"SEM_PROC:{l['id']}"
        mk = normalizar_matricula(l.get("matricula"))
        sk = f"MAT:{mk}" if mk else f"SEM_MAT:{l['id']}"
        pedidos_keys.add((pk, sk, l.get("eixo") or "", l.get("modalidade") or l.get("subcategoria") or ""))

    serv_res: dict[str, set[str]] = {}
    sem_matricula_valida = 0
    for l in linhas:
        mk = normalizar_matricula(l.get("matricula"))
        if not mk:
            sem_matricula_valida += 1
            continue
        serv_res.setdefault(mk, set()).add(l["resultado"])

    serv_so_def = sum(v == {"DEFERIDO"} for v in serv_res.values())
    serv_misto_com_def = sum("DEFERIDO" in v and len(v) > 1 for v in serv_res.values())
    serv_beneficiados = serv_so_def + serv_misto_com_def
    serv_apenas_ind = sum(v == {"INDEFERIDO"} for v in serv_res.values())
    serv_ind_e_ni = sum("DEFERIDO" not in v and "INDEFERIDO" in v and "NAO_INFORMADO" in v for v in serv_res.values())
    serv_somente_ind = serv_apenas_ind + serv_ind_e_ni
    serv_somente_ni = sum(v == {"NAO_INFORMADO"} for v in serv_res.values())

    return {
        "publicacoes": len(publicacoes_set),
        "processos": {
            "total": len(proc_res),
            "deferidos": proc_def,
            "indeferidos": proc_ind,
            "mistos": proc_mistos,
            "mistos_deferido_indeferido": proc_mistos_di,
            "nao_informado": proc_ni,
            "coletivos": proc_coletivos,
            "decisoes_sem_processo": sem_processo,
        },
        "pedidos_individuais": len(pedidos_keys),
        "decisoes": {
            "total": len(linhas),
            "deferidos": dec_def,
            "indeferidos": dec_ind,
            "nao_informado": dec_ni,
        },
        "servidores": {
            "total": len(serv_res),
            "beneficiados": serv_beneficiados,
            "somente_deferido": serv_so_def,
            "misto_com_deferido": serv_misto_com_def,
            "somente_indeferido": serv_somente_ind,
            "apenas_indeferido": serv_apenas_ind,
            "indeferido_e_nao_informado": serv_ind_e_ni,
            "somente_nao_informado": serv_somente_ni,
            "linhas_sem_matricula_valida": sem_matricula_valida,
        },
    }


def _fonte(banco: Banco, cache: dict, sha: str, pagina) -> dict:
    if sha not in cache:
        cache[sha] = banco.url_oficial(sha)
    url = cache[sha]
    return {"url_oficial": f"{url}#page={pagina}" if url else None, "pdf_no_acervo": f"/api/pdf/{sha}#page={pagina}"}


def _matricula_valida(linha: dict) -> str | None:
    return normalizar_matricula(linha.get("matricula"))


def _pessoas_distintas(linhas: list[dict]) -> int:
    return len({m for l in linhas if (m := _matricula_valida(l))})


def _proteger_inteiro(valor: int | None, pessoas: int) -> int | None:
    if valor is None:
        return None
    if valor == 0:
        return 0
    if valor < LIMIAR_PUBLICO or pessoas < LIMIAR_PUBLICO:
        return None
    return (valor // LIMIAR_PUBLICO) * LIMIAR_PUBLICO


def _mes_competencia(data: str | None) -> str:
    txt = str(data or "").strip()
    return txt[:7] if len(txt) >= 7 and txt[4:5] == "-" else "SEM_DATA"


def _contar_publico(linhas: list[dict]) -> dict:
    total = len(linhas)
    if total == 0:
        return {"total": 0, "deferido": 0, "indeferido": 0, "nao_informado": 0}
    pessoas = _pessoas_distintas(linhas)
    total_prot = _proteger_inteiro(total, pessoas)
    if total_prot is None:
        return {"total": None, "deferido": None, "indeferido": None, "nao_informado": None}
    partes = {
        k: [l for l in linhas if l.get("resultado") == r]
        for k, r in (("deferido", "DEFERIDO"), ("indeferido", "INDEFERIDO"), ("nao_informado", "NAO_INFORMADO"))
    }
    sub_prot = {k: _proteger_inteiro(len(itens), _pessoas_distintas(itens)) for k, itens in partes.items()}
    # Supressao complementar: se qualquer desfecho positivo ficar < LIMIAR, oculta os demais para impedir subtracao.
    if any(len(itens) > 0 and sub_prot[k] is None for k, itens in partes.items()):
        return {"total": total_prot, "deferido": None, "indeferido": None, "nao_informado": None}
    return {"total": total_prot, **sub_prot}


def _suprimir_secundaria(itens: list[dict], positivos: int) -> None:
    """Se exatamente 1 item positivo foi suprimido numa dimensão agregada, suprime também o menor visível."""
    visiveis = [it for it in itens if (it.get("total") or 0) > 0]
    if positivos - len(visiveis) == 1 and visiveis:
        menor = min(visiveis, key=lambda x: x["total"])
        for campo in ("total", "deferido", "indeferido", "nao_informado", "vertical", "horizontal", "tempo"):
            if campo in menor:
                menor[campo] = None


def _var_abs(anterior: int | None, atual: int | None) -> int | None:
    if anterior is None or atual is None:
        return None
    return atual - anterior


def _var_pct(anterior: int | None, atual: int | None) -> float | None:
    if anterior is None or atual is None or anterior <= 0:
        return None
    return round(100.0 * (atual - anterior) / anterior, 1)


def _comparativo_mensal(originais: list[dict], *, publico: bool = False) -> dict:
    """Resumo comparativo mensal entre os dois últimos meses com dados, incluindo distribuição por eixo
    e participação dos grupos do eixo Tempo de Serviço (com Abono de Permanência).

    No modo público (`publico=True`), aplica o limiar k-anonymity (>= 5 decisões e >= 5 matrículas),
    faixas de largura 5 e supressão complementar/secundária, omitindo variações e percentuais sempre
    que qualquer termo envolvido estiver suprimido.
    """
    por_mes: dict[str, list[dict]] = {}
    for l in originais:
        ym = _mes_competencia(l.get("data"))
        if ym != "SEM_DATA":
            por_mes.setdefault(ym, []).append(l)

    meses_ord = sorted(por_mes)

    def _valor(lins: list[dict]) -> int | None:
        return _proteger_inteiro(len(lins), _pessoas_distintas(lins)) if publico else len(lins)

    # Série mensal de Abono de Permanência
    abono_serie_raw: list[dict] = []
    pos_ab_m = 0
    for ym in meses_ord:
        ab_l = [x for x in por_mes[ym] if x["eixo"] == C.TEMPO and x.get("subcategoria") == "ABONO_PERMANENCIA"]
        if ab_l:
            pos_ab_m += 1
        abono_serie_raw.append({"mes": ym, "total": _valor(ab_l)})
    if publico:
        _suprimir_secundaria(abono_serie_raw, pos_ab_m)

    # Seleciona meses elegíveis (no público, apenas meses com total visível >= 5 após supressão secundária)
    totais_mes: list[dict] = []
    for ym in meses_ord:
        totais_mes.append({"mes": ym, "total": _valor(por_mes[ym])})
    if publico:
        _suprimir_secundaria(totais_mes, len(meses_ord))
    elegiveis = [m for m in totais_mes if m["total"] is not None and m["total"] > 0]

    if len(elegiveis) < 2:
        return {
            "disponivel": False,
            "motivo": "menos_de_dois_meses",
            "mes_anterior": None,
            "mes_atual": None,
            "resumo": None,
            "por_eixo": [],
            "por_grupo_tempo": [],
            "abono_por_mes": abono_serie_raw,
        }

    m_ant, m_atu = elegiveis[-2]["mes"], elegiveis[-1]["mes"]
    tot_ant, tot_atu = elegiveis[-2]["total"], elegiveis[-1]["total"]
    lin_ant, lin_atu = por_mes[m_ant], por_mes[m_atu]

    def _eixos_mes(lins: list[dict]) -> dict[str, int | None]:
        partes = {
            "VERTICAL": [x for x in lins if x["eixo"] == C.PROGRESSAO and x["modalidade"] == C.VERTICAL],
            "HORIZONTAL": [x for x in lins if x["eixo"] == C.PROGRESSAO and x["modalidade"] == C.HORIZONTAL],
            "SEM_MOD": [x for x in lins if x["eixo"] == C.PROGRESSAO and x["modalidade"] is None],
            "TEMPO_SERVICO": [x for x in lins if x["eixo"] == C.TEMPO],
        }
        vals = {k: _valor(v) for k, v in partes.items()}
        if publico and any(len(v) > 0 and vals[k] is None for k, v in partes.items()):
            return {"VERTICAL": None, "HORIZONTAL": None, "TEMPO_SERVICO": None}
        return {k: vals[k] for k in ("VERTICAL", "HORIZONTAL", "TEMPO_SERVICO")}

    ex_ant, ex_atu = _eixos_mes(lin_ant), _eixos_mes(lin_atu)
    por_eixo = []
    for chave, rotulo in (
        ("VERTICAL", "Progressão Vertical"),
        ("HORIZONTAL", "Progressão Horizontal"),
        ("TEMPO_SERVICO", "Tempo de Serviço"),
    ):
        va, vt = ex_ant[chave], ex_atu[chave]
        por_eixo.append({
            "chave": chave,
            "rotulo": rotulo,
            "anterior": va,
            "atual": vt,
            "variacao_absoluta": _var_abs(va, vt),
            "variacao_percentual": _var_pct(va, vt),
        })

    # Participação dos grupos do eixo Tempo de Serviço (incluindo Abono de Permanência)
    tempo_all = [x for x in originais if x["eixo"] == C.TEMPO]
    tempo_tot_all = _valor(tempo_all)
    tempo_ant_all = [x for x in lin_ant if x["eixo"] == C.TEMPO]
    tempo_atu_all = [x for x in lin_atu if x["eixo"] == C.TEMPO]

    def _grupos_tempo(lins_ref: list[dict]) -> dict[str, int | None]:
        itens, pos = [], 0
        for s in C.SUBCATEGORIAS:
            xs = [x for x in lins_ref if x.get("subcategoria") == s.codigo]
            if xs:
                pos += 1
            itens.append({"codigo": s.codigo, "total": _valor(xs)})
        sem_xs = [x for x in lins_ref if x.get("subcategoria") is None]
        if sem_xs:
            pos += 1
        itens.append({"codigo": "SEM_SUBCATEGORIA", "total": _valor(sem_xs)})
        if publico:
            _suprimir_secundaria(itens, pos)
        return {it["codigo"]: it["total"] for it in itens}

    gt_ant = _grupos_tempo(tempo_ant_all)
    gt_atu = _grupos_tempo(tempo_atu_all)
    gt_per = _grupos_tempo(tempo_all)

    por_grupo_tempo = []
    for s in C.SUBCATEGORIAS:
        va, vt, vp = gt_ant[s.codigo], gt_atu[s.codigo], gt_per[s.codigo]
        part_pct = (
            round(100.0 * vp / tempo_tot_all, 1)
            if (vp is not None and tempo_tot_all is not None and tempo_tot_all > 0)
            else None
        )
        por_grupo_tempo.append({
            "codigo": s.codigo,
            "nome": s.nome,
            "anterior": va,
            "atual": vt,
            "variacao_absoluta": _var_abs(va, vt),
            "variacao_percentual": _var_pct(va, vt),
            "total_periodo": vp,
            "participacao_tempo_pct": part_pct,
        })

    return {
        "disponivel": True,
        "motivo": None,
        "mes_anterior": m_ant,
        "mes_atual": m_atu,
        "resumo": {
            "anterior": tot_ant,
            "atual": tot_atu,
            "variacao_absoluta": _var_abs(tot_ant, tot_atu),
            "variacao_percentual": _var_pct(tot_ant, tot_atu),
        },
        "por_eixo": por_eixo,
        "por_grupo_tempo": por_grupo_tempo,
        "abono_por_mes": abono_serie_raw,
    }


def _aplicar_protecao_publica(
    originais: list[dict],
    logico: dict,
    refeitos_logicos: set,
    sem_efeito_logicos: set,
    conferido: bool,
    cob: dict,
    meta_base: dict,
) -> dict:
    """Agrega dados públicos com k-anonymity (>= 5 decisões E >= 5 matrículas), faixas de largura 5,
    granularidade temporal mensal e supressão complementar/secundária, removendo resenhas/eventos/filas internas."""
    pessoas_total = _pessoas_distintas(originais)
    total_dec = len(originais)
    total_prot = _proteger_inteiro(total_dec, pessoas_total)
    proc_prot = _proteger_inteiro(
        len({k for l in originais if (k := chave_processo(l.get("processo"), l.get("lotacao") or l.get("sufixo"), l.get("tipo")))}),
        pessoas_total,
    )
    res_prot = _proteger_inteiro(len({logico.get(l["ato_id"], l["ato_id"]) for l in originais}), pessoas_total)

    def_lin = [l for l in originais if l["resultado"] == "DEFERIDO"]
    ind_lin = [l for l in originais if l["resultado"] == "INDEFERIDO"]
    def_prot = _proteger_inteiro(len(def_lin), _pessoas_distintas(def_lin))
    ind_prot = _proteger_inteiro(len(ind_lin), _pessoas_distintas(ind_lin))
    if (len(def_lin) > 0 and def_prot is None) or (len(ind_lin) > 0 and ind_prot is None):
        def_prot, ind_prot = None, None

    ref_lin = [l for l in originais if logico.get(l["ato_id"], l["ato_id"]) in refeitos_logicos]
    se_lin = [l for l in originais if logico.get(l["ato_id"], l["ato_id"]) in sem_efeito_logicos]
    ref_prot = _proteger_inteiro(len(refeitos_logicos), _pessoas_distintas(ref_lin)) if conferido else None
    se_prot = _proteger_inteiro(len(sem_efeito_logicos), _pessoas_distintas(se_lin)) if conferido else None

    indicadores_pub = {
        "processos": proc_prot,
        "resenhas": res_prot,
        "decisoes": total_prot,
        "deferidos": def_prot,
        "indeferidos": ind_prot,
        "refeitos": ref_prot,
        "sem_efeito": se_prot,
    }

    prog = [l for l in originais if l["eixo"] == C.PROGRESSAO]
    tempo = [l for l in originais if l["eixo"] == C.TEMPO]
    verticais = [l for l in prog if l["modalidade"] == C.VERTICAL]
    horizontais = [l for l in prog if l["modalidade"] == C.HORIZONTAL]

    por_assunto = [
        {"chave": "VERTICAL", "rotulo": "Progressão Vertical", **_contar_publico(verticais)},
        {"chave": "HORIZONTAL", "rotulo": "Progressão Horizontal", **_contar_publico(horizontais)},
        {"chave": "TEMPO_SERVICO", "rotulo": "Tempo de Serviço", **_contar_publico(tempo)},
    ]
    _suprimir_secundaria(por_assunto, sum(1 for x in (verticais, horizontais, tempo) if x))

    meses_map: dict[str, list[dict]] = {}
    for l in originais:
        meses_map.setdefault(_mes_competencia(l.get("data")), []).append(l)
    por_data_todos = []
    for mes in sorted(meses_map):
        itens_m = meses_map[mes]
        p_m = _pessoas_distintas(itens_m)
        t_m = _proteger_inteiro(len(itens_m), p_m)
        v_lin = [x for x in itens_m if x["eixo"] == C.PROGRESSAO and x["modalidade"] == C.VERTICAL]
        h_lin = [x for x in itens_m if x["eixo"] == C.PROGRESSAO and x["modalidade"] == C.HORIZONTAL]
        sm_lin = [x for x in itens_m if x["eixo"] == C.PROGRESSAO and x["modalidade"] is None]
        tm_lin = [x for x in itens_m if x["eixo"] == C.TEMPO]
        v_p = _proteger_inteiro(len(v_lin), _pessoas_distintas(v_lin))
        h_p = _proteger_inteiro(len(h_lin), _pessoas_distintas(h_lin))
        sm_p = _proteger_inteiro(len(sm_lin), _pessoas_distintas(sm_lin))
        tm_p = _proteger_inteiro(len(tm_lin), _pessoas_distintas(tm_lin))
        if t_m is None or any(len(s) > 0 and sp is None for s, sp in ((v_lin, v_p), (h_lin, h_p), (sm_lin, sm_p), (tm_lin, tm_p))):
            v_p = h_p = tm_p = None
        por_data_todos.append({"data": mes, "vertical": v_p, "horizontal": h_p, "tempo": tm_p, "total": t_m})
    _suprimir_secundaria(por_data_todos, len(meses_map))
    por_data = [m for m in por_data_todos if m["total"] is not None]

    def _montar_grupos(chaves_e_linhas, campos_extra_fn):
        itens, pos = [], 0
        for chave, lins in chaves_e_linhas:
            if not lins:
                continue
            pos += 1
            cont = _contar_publico(lins)
            v_lin = [x for x in lins if x["modalidade"] == C.VERTICAL]
            h_lin = [x for x in lins if x["modalidade"] == C.HORIZONTAL]
            v_p = _proteger_inteiro(len(v_lin), _pessoas_distintas(v_lin)) if cont["total"] is not None else None
            h_p = _proteger_inteiro(len(h_lin), _pessoas_distintas(h_lin)) if cont["total"] is not None else None
            if (len(v_lin) > 0 and v_p is None) or (len(h_lin) > 0 and h_p is None):
                v_p, h_p = None, None
            itens.append({**campos_extra_fn(chave), "horizontal": h_p, "vertical": v_p, **cont})
        _suprimir_secundaria(itens, pos)
        return [it for it in itens if it["total"] is not None]

    por_grupo = _montar_grupos(
        [(c, [l for l in prog if (l["grupo"] or "NAO_INFORMADO") == c]) for c in [g.codigo for g in C.GRUPOS] + ["NAO_INFORMADO"]],
        lambda codigo: {
            "grupo": codigo,
            "nome": C.GRUPO_POR_CODIGO[codigo].nome if codigo in C.GRUPO_POR_CODIGO else "Grupo não informado",
        },
    )
    NOMES_EXP = {
        "PENDENTE:TEC. ADM": "TEC. ADM · expressão pendente de confirmação (AST)",
        "PENDENTE:STF": "STF · expressão pendente de confirmação (SFT)",
    }
    por_grupo_det = _montar_grupos(
        [(ch, [l for l in prog if _chave_grupo(l) == ch]) for ch in [g.codigo for g in C.GRUPOS] + ["PENDENTE:TEC. ADM", "PENDENTE:STF", "NAO_INFORMADO"]],
        lambda chave: {
            "chave": chave,
            "grupo": chave if chave in C.GRUPO_POR_CODIGO else None,
            "expressao_pendente": chave.split(":", 1)[1] if chave.startswith("PENDENTE:") else None,
            "pendente_confirmacao": chave.startswith("PENDENTE:"),
            "nome": C.GRUPO_POR_CODIGO[chave].nome if chave in C.GRUPO_POR_CODIGO else NOMES_EXP.get(chave, "Grupo não informado"),
        },
    )

    niveis_lista, pos_nv = [], 0
    for nv in NIVEIS_VERTICAIS:
        itens_nv = [l for l in verticais if (l.get("nivel_info") or {}).get("nivel") == nv]
        if itens_nv:
            pos_nv += 1
        niveis_lista.append({
            "nivel": nv,
            "rotulo": "Sem nível A–F efetivado" if nv == "NAO_IDENTIFICADO" else f"Nível {nv}",
            **_contar_publico(itens_nv),
            "transicoes": [],
        })
    _suprimir_secundaria(niveis_lista, pos_nv)

    situacoes_pub, pos_sit = [], 0
    for sit in SITUACOES_NIVEL_VERTICAL:
        itens_s = [l for l in verticais if (l.get("nivel_info") or {}).get("categoria") == sit]
        if itens_s:
            pos_sit += 1
        rot, desc = META_SITUACAO_NIVEL[sit]
        situacoes_pub.append({
            "codigo": sit,
            "nivel": sit if sit in _CLASSES_VALIDAS else "NAO_IDENTIFICADO",
            "rotulo": rot,
            "descricao": desc,
            "grupo_situacao": "nivel_af" if sit in _CLASSES_VALIDAS else "sem_nivel_af",
            **_contar_publico(itens_s),
            "transicoes": [],
        })
    _suprimir_secundaria(situacoes_pub, pos_sit)

    tempo_sem_sub = [l for l in tempo if l["subcategoria"] is None]
    por_sub, pos_sub = [], 0
    for s in C.SUBCATEGORIAS:
        lins = [l for l in tempo if l["subcategoria"] == s.codigo]
        if lins:
            pos_sub += 1
        cont = _contar_publico(lins)
        sit = None if cont["total"] else ("suprimido por privacidade (< 5)" if lins else (
            "sem ocorrência confirmada no período verificado" if cob["completa"] else "cobertura pendente"))
        por_sub.append({"codigo": s.codigo, "nome": s.nome, **cont, "situacao": sit})
    tempo_sem_sub_pub = _contar_publico(tempo_sem_sub)
    if tempo_sem_sub:
        pos_sub += 1
    _suprimir_secundaria(por_sub + [tempo_sem_sub_pub], pos_sub)
    for item in por_sub:
        if item["total"] is None and item.get("situacao") is None:
            item["situacao"] = "suprimido por privacidade (< 5)"

    por_cond, pos_cond = [], 0
    for c, n in C.CONDICOES.items():
        lins = [l for l in prog if (l["condicao"] or "NAO_INFORMADA") == c]
        if lins:
            pos_cond += 1
        por_cond.append({"condicao": c, "nome": n, "total": _proteger_inteiro(len(lins), _pessoas_distintas(lins))})
    _suprimir_secundaria(por_cond, pos_cond)

    sem_mod = [l for l in prog if l["modalidade"] is None]
    cls_lin = [l for l in verticais if (l.get("nivel_info") or {}).get("nivel") in _CLASSES_VALIDAS]
    ni_lin = [l for l in verticais if (l.get("nivel_info") or {}).get("nivel") == "NAO_IDENTIFICADO"]
    cls_p = _proteger_inteiro(len(cls_lin), _pessoas_distintas(cls_lin))
    ni_p = _proteger_inteiro(len(ni_lin), _pessoas_distintas(ni_lin))
    if (len(cls_lin) > 0 and cls_p is None) or (len(ni_lin) > 0 and ni_p is None):
        cls_p = ni_p = None

    sem_nivel_pub_itens, pos_sn = [], 0
    for sit in SITUACOES_SEM_NIVEL_VERTICAL:
        itens_s = [l for l in verticais if (l.get("nivel_info") or {}).get("categoria") == sit]
        if itens_s:
            pos_sn += 1
        val_s = _proteger_inteiro(len(itens_s), _pessoas_distintas(itens_s)) if ni_p is not None else None
        sem_nivel_pub_itens.append({"codigo": sit, "total": val_s})
    if ni_p is not None:
        _suprimir_secundaria(sem_nivel_pub_itens, pos_sn)
    sem_nivel_pub_map = {x["codigo"]: x["total"] for x in sem_nivel_pub_itens}

    apoio_nulo = {
        "eventos_de_alteracao": None, "eventos_por_tipo": None, "eventos_sem_vinculo": None,
        "eventos_fora_do_acervo": None,
        "decisoes_pendentes": None, "decisoes_conferidas": None, "decisoes_excluidas_integridade": None,
        "decisoes_conferidas_com_conflito": None, "decisoes_rejeitadas": None,
        "conflitos_abertos": None, "classificacoes_desatualizadas": None, "vinculo_nao_expresso_pendente": None,
    }
    meta_pub = {
        **meta_base,
        "privacidade": {
            "protegido": True, "limiar": LIMIAR_PUBLICO, "faixa": LIMIAR_PUBLICO,
            "granularidade_temporal": "mensal", "filtros_dinamicos_bloqueados": True,
        },
    }
    return {
        "meta": meta_pub,
        "indicadores": indicadores_pub,
        "ajuda": {c: ROTULOS[c] for c in CARTOES},
        "apoio": apoio_nulo,
        "series": {
            "por_assunto": por_assunto,
            "progressao_sem_modalidade": _proteger_inteiro(len(sem_mod), _pessoas_distintas(sem_mod)),
            "por_data": por_data,
            "por_grupo": por_grupo,
            "por_grupo_detalhado": por_grupo_det,
            "por_nivel_vertical": niveis_lista,
            "por_situacao_nivel_vertical": situacoes_pub,
            "resumo_nivel_vertical": {
                "total_progressao": _proteger_inteiro(len(prog), _pessoas_distintas(prog)),
                "total_horizontal": _proteger_inteiro(len(horizontais), _pessoas_distintas(horizontais)),
                "total_vertical": _proteger_inteiro(len(verticais), _pessoas_distintas(verticais)),
                "classificados": cls_p,
                "nao_identificados": ni_p,
                "indeferidos": sem_nivel_pub_map["INDEFERIDO"],
                "nao_determinados": sem_nivel_pub_map["NAO_DETERMINADO"],
                "inconsistentes": sem_nivel_pub_map["INCONSISTENTE"],
                "nao_aplica": sem_nivel_pub_map["NAO_APLICA"],
            },
            "por_subcategoria": por_sub,
            "tempo_sem_subcategoria": tempo_sem_sub_pub,
            "por_condicao": por_cond,
            "comparativo_mensal": _comparativo_mensal(originais, publico=True),
        },
        "resenhas": [],
        "linhas": [],
        "eventos": [],
    }


def resumo_cobertura_edicoes(banco: Banco) -> dict:
    """Calcula `ausencia_tecnica_edicoes` e `inconclusivas` em somente-leitura, considerando como
    edicoes com atos relevantes tanto aquelas com atos GEDIV (PROGRESSAO/TEMPO_SERVICO) quanto
    as que possuem registros reconhecidos de Abono de Permanencia em `outra_publicacao`."""
    from . import adaptador

    inconclusivas = banco.con.execute(
        "SELECT COUNT(*) FROM leitura WHERE situacao='ERRO' OR data_edicao IS NULL OR numero_edicao IS NULL"
    ).fetchone()[0]
    shas_validos = {
        r[0] for r in banco.con.execute(
            "SELECT sha256 FROM leitura WHERE situacao != 'ERRO' AND data_edicao IS NOT NULL AND numero_edicao IS NOT NULL"
        )
    }
    shas_ato = {
        r[0] for r in banco.con.execute(
            "SELECT DISTINCT sha256 FROM ato WHERE gerencia = 'GEDIV' AND eixo IN ('PROGRESSAO', 'TEMPO_SERVICO')"
        )
    }
    shas_abono = {
        r["sha256"] for r in banco.con.execute(
            "SELECT sha256, tipo, titulo, trecho FROM outra_publicacao WHERE gerencia = 'GEDIV'"
        )
        if adaptador._eh_abono_permanencia(dict(r))
    }
    ausencia = len(shas_validos - (shas_ato | shas_abono))
    return {"ausencia_tecnica_edicoes": int(ausencia), "inconclusivas": int(inconclusivas)}


def _validar_inteiro_publico(valor, contexto: str) -> None:
    if valor is None:
        return
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(f"snapshot público inválido ({contexto}): valor não inteiro {valor!r}")
    if valor == 0:
        return
    if valor < LIMIAR_PUBLICO or (valor % LIMIAR_PUBLICO) != 0:
        raise ValueError(
            f"snapshot público inválido ({contexto}): valor {valor} viola limiar/faixa de {LIMIAR_PUBLICO}"
        )


def gerar_snapshot_publico(banco: Banco) -> dict:
    """Gera a representação pública congelada para `/api/painel` e `/api/data` a partir do banco
    (compatível com conexões somente-leitura), separada da operação transacional em tempo real."""
    from . import adaptador

    p_pub = painel(banco, {}, PUBLICO, proteger_publico=True)
    d_pub = adaptador.projetar_para_dashboard_2910(p_pub, [], [])
    d_pub["backend"]["papel"] = "publico"
    d_pub["backend"]["ehAdmin"] = False
    snap = {
        "versao_snapshot": 1,
        "gerado_em": agora(),
        "painel": p_pub,
        "data": d_pub,
    }
    return validar_snapshot_publico(snap)


def validar_snapshot_publico(snap: dict) -> dict:
    """Valida integralmente um snapshot público contra vazamento de PII, contagens < 5, datas diárias,
    quebra de supressão complementar e inconsistência de contrato antes de permitir sua publicação."""
    if not isinstance(snap, dict) or snap.get("versao_snapshot") != 1:
        raise ValueError("snapshot público inválido: estrutura ou versão incompatível")
    p_pub = snap.get("painel")
    d_pub = snap.get("data")
    if not isinstance(p_pub, dict) or not isinstance(d_pub, dict):
        raise ValueError("snapshot público inválido: blocos 'painel' e 'data' obrigatórios")

    meta_p = p_pub.get("meta") or {}
    priv_p = meta_p.get("privacidade") or {}
    if (
        meta_p.get("perfil") != PUBLICO
        or meta_p.get("escopo") != "conferido"
        or meta_p.get("dados_individuais") is not False
        or priv_p.get("protegido") is not True
        or priv_p.get("limiar") != LIMIAR_PUBLICO
        or priv_p.get("faixa") != LIMIAR_PUBLICO
        or priv_p.get("granularidade_temporal") != "mensal"
    ):
        raise ValueError("snapshot público inválido: metadados de privacidade ausentes ou violados")

    for chave_vazia in ("linhas", "resenhas", "eventos"):
        if p_pub.get(chave_vazia) != []:
            raise ValueError(f"snapshot público inválido: painel.{chave_vazia} deve ser lista vazia")

    apoio_p = p_pub.get("apoio")
    if not isinstance(apoio_p, dict) or any(v is not None for v in apoio_p.values()):
        raise ValueError("snapshot público inválido: contadores internos em 'apoio' devem ser nulos")

    ind = p_pub.get("indicadores")
    if not isinstance(ind, dict) or set(ind.keys()) != set(CARTOES):
        raise ValueError("snapshot público inválido: cartões de indicadores incompletos")
    for k, v in ind.items():
        _validar_inteiro_publico(v, f"indicadores.{k}")
    if (ind.get("deferidos") is None) != (ind.get("indeferidos") is None):
        raise ValueError("snapshot público inválido: supressão complementar violada em deferidos/indeferidos")

    series = p_pub.get("series")
    if not isinstance(series, dict):
        raise ValueError("snapshot público inválido: bloco 'series' ausente")
    for chave_priv_serie in ("unidades", "eventos_detalhados", "outras_publicacoes_resumo"):
        if chave_priv_serie in series:
            raise ValueError(f"snapshot público inválido: bloco privado series.{chave_priv_serie} não permitido")

    _validar_inteiro_publico(series.get("progressao_sem_modalidade"), "series.progressao_sem_modalidade")
    for pt in series.get("por_data") or []:
        dt_val = str(pt.get("data") or "")
        if not (dt_val == "SEM_DATA" or re.fullmatch(r"\d{4}-\d{2}", dt_val)):
            raise ValueError(f"snapshot público inválido: data não mensal em por_data ({dt_val!r})")
        for campo in ("vertical", "horizontal", "tempo", "total"):
            _validar_inteiro_publico(pt.get(campo), f"por_data[{dt_val}].{campo}")

    for nome_serie in (
        "por_assunto",
        "por_grupo",
        "por_grupo_detalhado",
        "por_nivel_vertical",
        "por_situacao_nivel_vertical",
        "por_subcategoria",
    ):
        itens_serie = series.get(nome_serie) or []
        for item in itens_serie:
            for campo in ("total", "deferido", "indeferido", "nao_informado", "vertical", "horizontal"):
                if campo in item:
                    _validar_inteiro_publico(item.get(campo), f"{nome_serie}.{campo}")
            if (item.get("deferido") is None) != (item.get("indeferido") is None):
                raise ValueError(f"snapshot público inválido: supressão complementar violada em {nome_serie}")
            if nome_serie in ("por_nivel_vertical", "por_situacao_nivel_vertical") and item.get("transicoes") not in (None, []):
                raise ValueError(f"snapshot público inválido: transições detalhadas expostas em {nome_serie}")
        if nome_serie == "por_situacao_nivel_vertical" and itens_serie:
            suprimidas_sit = sum(1 for x in itens_serie if x.get("total") is None)
            visiveis_sit = sum(1 for x in itens_serie if (x.get("total") or 0) > 0)
            if suprimidas_sit == 1 and visiveis_sit > 0:
                raise ValueError("snapshot público inválido: supressão secundária violada em por_situacao_nivel_vertical")

    sub_itens_val = list(series.get("por_subcategoria") or [])
    if "tempo_sem_subcategoria" in series:
        ts_sem = series.get("tempo_sem_subcategoria") or {}
        for campo in ("total", "deferido", "indeferido", "nao_informado"):
            if campo in ts_sem:
                _validar_inteiro_publico(ts_sem.get(campo), f"tempo_sem_subcategoria.{campo}")
        if (ts_sem.get("deferido") is None) != (ts_sem.get("indeferido") is None):
            raise ValueError("snapshot público inválido: supressão complementar violada em tempo_sem_subcategoria")
        if ts_sem.get("total") is None and any(ts_sem.get(c) is not None for c in ("deferido", "indeferido", "nao_informado")):
            raise ValueError("snapshot público inválido: subcontagem exposta com total suprimido em tempo_sem_subcategoria")
        sub_itens_val.append(ts_sem)
    suprimidas_sub = sum(1 for x in sub_itens_val if x.get("total") is None)
    visiveis_sub = sum(1 for x in sub_itens_val if (x.get("total") or 0) > 0)
    if suprimidas_sub == 1 and visiveis_sub > 0:
        raise ValueError("snapshot público inválido: supressão secundária violada em subcategorias de Tempo de Serviço")

    for item in series.get("por_condicao") or []:
        _validar_inteiro_publico(item.get("total"), "por_condicao.total")
    res_nv = series.get("resumo_nivel_vertical") or {}
    for campo in (
        "total_progressao",
        "total_horizontal",
        "total_vertical",
        "classificados",
        "nao_identificados",
        "indeferidos",
        "nao_determinados",
        "inconsistentes",
        "nao_aplica",
    ):
        _validar_inteiro_publico(res_nv.get(campo), f"resumo_nivel_vertical.{campo}")
    sub_sn_vals = [res_nv.get(c) for c in ("indeferidos", "nao_determinados", "inconsistentes", "nao_aplica") if c in res_nv]
    if res_nv.get("nao_identificados") is None and any(v is not None for v in sub_sn_vals):
        raise ValueError("snapshot público inválido: subcontagem de nível exposta com nao_identificados suprimido")
    if sub_sn_vals and sum(1 for v in sub_sn_vals if v is None) == 1 and sum(1 for v in sub_sn_vals if (v or 0) > 0) > 0:
        raise ValueError("snapshot público inválido: supressão secundária violada em resumo_nivel_vertical")

    cmp_m = series.get("comparativo_mensal")
    if isinstance(cmp_m, dict):
        for campo_m in ("mes_anterior", "mes_atual"):
            mv = cmp_m.get(campo_m)
            if mv is not None and not re.fullmatch(r"\d{4}-\d{2}", str(mv)):
                raise ValueError(f"snapshot público inválido: {campo_m} não mensal ({mv!r})")
        res_cm = cmp_m.get("resumo")
        if isinstance(res_cm, dict):
            _validar_inteiro_publico(res_cm.get("anterior"), "comparativo_mensal.resumo.anterior")
            _validar_inteiro_publico(res_cm.get("atual"), "comparativo_mensal.resumo.atual")
            if (res_cm.get("anterior") is None or res_cm.get("atual") is None) and (
                res_cm.get("variacao_absoluta") is not None or res_cm.get("variacao_percentual") is not None
            ):
                raise ValueError("snapshot público inválido: variação exposta com mês suprimido em comparativo_mensal")
        for it_e in cmp_m.get("por_eixo") or []:
            _validar_inteiro_publico(it_e.get("anterior"), "comparativo_mensal.por_eixo.anterior")
            _validar_inteiro_publico(it_e.get("atual"), "comparativo_mensal.por_eixo.atual")
            if (it_e.get("anterior") is None or it_e.get("atual") is None) and (
                it_e.get("variacao_absoluta") is not None or it_e.get("variacao_percentual") is not None
            ):
                raise ValueError("snapshot público inválido: variação de eixo exposta com valor suprimido")
        for it_g in cmp_m.get("por_grupo_tempo") or []:
            _validar_inteiro_publico(it_g.get("anterior"), "comparativo_mensal.por_grupo_tempo.anterior")
            _validar_inteiro_publico(it_g.get("atual"), "comparativo_mensal.por_grupo_tempo.atual")
            _validar_inteiro_publico(it_g.get("total_periodo"), "comparativo_mensal.por_grupo_tempo.total_periodo")
            if (it_g.get("anterior") is None or it_g.get("atual") is None) and (
                it_g.get("variacao_absoluta") is not None or it_g.get("variacao_percentual") is not None
            ):
                raise ValueError("snapshot público inválido: variação de grupo Tempo exposta com valor suprimido")
            if it_g.get("total_periodo") is None and it_g.get("participacao_tempo_pct") is not None:
                raise ValueError("snapshot público inválido: participação exposta com total suprimido em por_grupo_tempo")
        for it_a in cmp_m.get("abono_por_mes") or []:
            if not re.fullmatch(r"\d{4}-\d{2}", str(it_a.get("mes") or "")):
                raise ValueError("snapshot público inválido: mês inválido em comparativo_mensal.abono_por_mes")
            _validar_inteiro_publico(it_a.get("total"), "comparativo_mensal.abono_por_mes.total")

    if d_pub.get("rows") != [] or d_pub.get("events") != [] or d_pub.get("otherPublications") not in (None, []):
        raise ValueError("snapshot público inválido: data.rows, data.events e data.otherPublications devem estar vazios")
    if (d_pub.get("otherPublicationsSummary") or {}).get("total", 0) != 0:
        raise ValueError("snapshot público inválido: data.otherPublicationsSummary.total deve ser zero")
    meta_d = d_pub.get("meta") or {}
    if any(meta_d.get(c) != 0 for c in ("pendentes", "rejeitados", "eventosPendentes")) or meta_d.get("outrasPublicacoes", 0) != 0:
        raise ValueError("snapshot público inválido: contadores de fila não zerados em data.meta")
    dash = d_pub.get("dashboard") or {}
    counts = dash.get("counts") or {}
    if dash.get("defaultScope") != "conferido" or any(
        counts.get(c) != 0 for c in ("received", "pending", "confirmed", "rejected", "unlinkedEvents")
    ) or counts.get("otherPublications", 0) != 0:
        raise ValueError("snapshot público inválido: contadores de data.dashboard.counts inconsistentes")
    for nome_v, visao_v in (dash.get("views") or {}).items():
        if visao_v.get("rowIds"):
            raise ValueError(f"snapshot público inválido: data.dashboard.views.{nome_v}.rowIds deve estar vazio")
        if (visao_v.get("metrics") or {}).get("otherPublications", 0) != 0:
            raise ValueError(f"snapshot público inválido: data.dashboard.views.{nome_v}.metrics.otherPublications deve ser zero")
    back = d_pub.get("backend") or {}
    if (
        back.get("autenticado") is not False
        or back.get("ehAdmin") is not False
        or back.get("resenhas") != []
        or bool(back.get("eventos"))
        or bool(back.get("outras"))
        or back.get("indicadores") != ind
        or any(v is not None for v in (back.get("apoio") or {}).values())
    ):
        raise ValueError("snapshot público inválido: bloco data.backend contém dados restritos ou divergentes")

    # Garantir que o diagnóstico de versão de regras no snapshot público nunca exponha contagens exatas/pendentes
    diags_publicos = (
        ("painel.meta.versao_regras_diagnostico", meta_p.get("versao_regras_diagnostico")),
        ("painel.meta.cobertura.versao_regras_diagnostico", (meta_p.get("cobertura") or {}).get("versao_regras_diagnostico")),
        ("data.meta.versaoRegrasDiagnostico", meta_d.get("versaoRegrasDiagnostico")),
        ("data.backend.versaoRegrasDiagnostico", back.get("versaoRegrasDiagnostico")),
    )
    for rot_d, diag_d in diags_publicos:
        if not isinstance(diag_d, dict) or not diag_d:
            continue
        for campo_proib in ("decisoes_afetadas", "edicoes_por_versao", "edicoes_compativeis", "edicoes_incompativeis"):
            if diag_d.get(campo_proib) is not None:
                raise ValueError(f"snapshot público inválido: {rot_d}.{campo_proib} deve ser nulo no perfil público")
        if diag_d.get("versoes_no_banco"):
            raise ValueError(f"snapshot público inválido: {rot_d}.versoes_no_banco deve ser vazio no perfil público")
        msg_d = str(diag_d.get("mensagem") or "")
        if re.search(r"\d+\s+decis", msg_d, re.I):
            raise ValueError(f"snapshot público inválido: {rot_d}.mensagem expõe contagem de decisões")
    for rot_txt, txt_val in (
        ("painel.meta.cobertura.parecer", (meta_p.get("cobertura") or {}).get("parecer")),
        ("data.meta.coverage", meta_d.get("coverage")),
    ):
        if re.search(r"\d+\s+decis", str(txt_val or ""), re.I):
            raise ValueError(f"snapshot público inválido: {rot_txt} expõe contagem de decisões")

    bruto_json = json.dumps(snap, ensure_ascii=False)
    if (
        "pdf_sha256" in bruto_json
        or "#page=" in bruto_json
        or re.search(r"SAD-PSE-202\d/\d+", bruto_json)
        or re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", bruto_json)
    ):
        raise ValueError("snapshot público inválido: referência documental individual ou dado pessoal detectado")
    return snap


def publicar_snapshot_publico(
    banco: Banco | None,
    caminho_saida: Path | str,
    *,
    snapshot: dict | None = None,
) -> dict:
    """Valida e publica atomicamente (`.tmp` -> `os.replace`) o snapshot público em disco.
    Se a validação falhar, levanta `ValueError` sem tocar no arquivo anterior."""
    destino = Path(caminho_saida)
    snap = validar_snapshot_publico(snapshot if snapshot is not None else gerar_snapshot_publico(banco))
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.parent / f"{destino.name}.tmp"
    conteudo = json.dumps(snap, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, destino)
    return snap


def carregar_snapshot_publico(caminho: Path | str) -> dict | None:
    """Carrega e valida o snapshot público congelado em disco, ou retorna `None` se ainda não existir."""
    arq = Path(caminho)
    if not arq.is_file():
        return None
    bruto = json.loads(arq.read_text(encoding="utf-8"))
    return validar_snapshot_publico(bruto)


def painel(banco: Banco, bruto: dict | None = None, perfil: str = PUBLICO, *, proteger_publico: bool = False) -> dict:
    """Todas as consultas do painel leem o banco num mesmo momento (instantâneo), para que indicadores, séries e tabela
    nunca misturem estados de uma reclassificação em andamento."""
    with banco.instantaneo():
        return _painel(banco, bruto, perfil, proteger_publico=proteger_publico)


def _resumo_outras_publicacoes(banco: Banco) -> dict:
    """Contagem separada de `outra_publicacao` (incluindo Abono de Permanência), nunca somada às decisões."""
    from . import adaptador

    por_tipo: dict[str, int] = {}
    abono = 0
    total = 0
    for r in banco.con.execute("SELECT tipo, titulo, trecho FROM outra_publicacao WHERE gerencia = 'GEDIV'"):
        total += 1
        t = r["tipo"] or "OUTRA"
        por_tipo[t] = por_tipo.get(t, 0) + 1
        if adaptador._eh_abono_permanencia(dict(r)):
            abono += 1
    return {"total": total, "abono_permanencia": abono, "por_tipo": por_tipo}


def _painel(banco: Banco, bruto: dict | None, perfil: str, *, proteger_publico: bool = False) -> dict:
    restringir_publico = bool(proteger_publico and perfil != GERENCIA_PERFIL)
    f = normalizar_filtros({} if restringir_publico else (bruto or {}), perfil)
    estado = "CONFERIDO" if f["escopo"] == "conferido" else "PENDENTE"
    conferido = f["escopo"] == "conferido"
    todas = _linhas(banco)
    logico = {a["id"]: (a["chave_logica"] or a["id"]) for a in banco.con.execute("SELECT id, chave_logica FROM ato")}

    # Eventos: somente vínculos VALIDADOS a atos originais do recorte; a data relevante dos cartões de evento é a do evento.
    # Eventos pendentes/sugeridos/rejeitados NUNCA alteram os números oficiais.
    eventos = [dict(e) for e in banco.con.execute("SELECT * FROM evento WHERE gerencia = 'GEDIV' ORDER BY data_publicacao, pagina, id")]
    vinculos_dec = [dict(v) for v in banco.eventos_decisoes()]
    links_por_evento: dict[str, list[dict]] = {}
    for v in vinculos_dec:
        links_por_evento.setdefault(v["evento_id"], []).append(v)

    arquivos_vigentes = {r[0] for r in banco.con.execute(
        "SELECT c.sha256 FROM classificacao c JOIN leitura l ON l.sha256 = c.sha256 "
        "WHERE c.gerencia = 'GEDIV' AND c.versao_regras = ? AND l.situacao <> 'ERRO' "
        "AND (l.revisao IS NULL OR c.revisao_leitura IS l.revisao)", (C.VERSAO_REGRAS,))}

    f_sem_merito = {**f, "resultado": None, "nivel": None}
    todas_estado = [l for l in todas if l["validacao"] == estado]
    dim_base = [l for l in todas_estado if _passa(l, f_sem_merito)]
    atos_dim_base = {logico.get(l["ato_id"], l["ato_id"]) for l in dim_base if l["natureza"] == C.ORIGINAL}

    validos_todos = [
        e for e in eventos
        if e["estado"] == "VALIDADO"
        and logico.get(e["ato_original_id"], e["ato_original_id"]) in atos_dim_base
        and e["sha256"] in arquivos_vigentes
    ]

    decisoes_desconstituidas_ids: set[str] = set()
    decisoes_retificadas_map: dict[str, list[dict]] = {}
    decisoes_republicadas_ids: set[str] = set()
    decisoes_sem_efeito_por_evento: dict[str, set[str]] = {}
    decisoes_retificadas_por_evento: dict[str, set[str]] = {}

    if conferido:
        # Indexar decisões originais por ato lógico para resolução segura quando evento_decisao não estiver populado
        decs_por_logico: dict[str, list[dict]] = {}
        for l in dim_base:
            if l["natureza"] == C.ORIGINAL:
                decs_por_logico.setdefault(logico.get(l["ato_id"], l["ato_id"]), []).append(l)

        for e in validos_todos:
            ev_id = e["id"]
            alvo_log = logico.get(e["ato_original_id"], e["ato_original_id"])
            links = links_por_evento.get(ev_id, [])
            if e["tipo"] == C.SEM_EFEITO:
                atingidas: set[str] = set()
                if links:
                    atingidas = {lk["decisao_id"] for lk in links}
                else:
                    # Fallback seguro (bancos legados v8): exige resolução inequívoca sem presumir processos coletivos.
                    resolv, erro_ambig = gediv_processo.resolver_decisoes_por_referencias(
                        e, decs_por_logico.get(alvo_log, [])
                    )
                    if not erro_ambig and resolv:
                        atingidas = set(resolv)
                decisoes_sem_efeito_por_evento[ev_id] = atingidas
                decisoes_desconstituidas_ids |= atingidas
            elif e["tipo"] in (C.RETIFICACAO, C.CORRECAO) and links:
                atingidas_ret: set[str] = set()
                for lk in links:
                    did = lk["decisao_id"]
                    atingidas_ret.add(did)
                    campos_corr = json.loads(lk["campos_corrigidos"]) if lk.get("campos_corrigidos") else {}
                    decisoes_retificadas_map.setdefault(did, []).append({
                        "evento_id": ev_id,
                        "tipo": e["tipo"],
                        "data_publicacao": e["data_publicacao"],
                        "resultado_novo": lk.get("resultado_novo"),
                        "campos_corrigidos": campos_corr,
                    })
                decisoes_retificadas_por_evento[ev_id] = atingidas_ret
            elif e["tipo"] == C.REPUBLICACAO:
                if links:
                    decisoes_republicadas_ids |= {lk["decisao_id"] for lk in links}

    # Aplicar efeitos de retificação (preservando histórico original) e separar decisões desconstituídas
    dim_processadas: list[dict] = []
    desconstituidas_lista: list[dict] = []
    for l_orig in todas_estado:
        l = dict(l_orig)
        l["detalhe"] = dict(l_orig.get("detalhe") or {})
        l["resultado_original"] = l["resultado"]
        l["retificacoes_aplicadas"] = []
        l["desconstituida"] = l["id"] in decisoes_desconstituidas_ids

        if conferido and l["id"] in decisoes_retificadas_map:
            for ret in decisoes_retificadas_map[l["id"]]:
                if ret["resultado_novo"]:
                    l["resultado"] = ret["resultado_novo"]
                for k_c, v_c in (ret["campos_corrigidos"] or {}).items():
                    if k_c in ("classe_anterior", "classe_posterior", "nivel_anterior", "nivel_atual"):
                        l["detalhe"][k_c] = v_c
                    elif k_c in ("processo", "servidor", "matricula", "lotacao", "cargo", "resultado"):
                        l[k_c] = v_c
                l["retificacoes_aplicadas"].append({
                    "evento_id": ret["evento_id"],
                    "tipo": ret["tipo"],
                    "data_publicacao": ret["data_publicacao"],
                    "resultado_novo": ret["resultado_novo"],
                })
            l["nivel_info"] = classificar_nivel_vertical(l)

        if l["desconstituida"]:
            if _passa(l, f):
                desconstituidas_lista.append(l)
            continue
        if _passa(l, f):
            dim_processadas.append(l)

    dim = dim_processadas
    originais = [l for l in dim if l["natureza"] == C.ORIGINAL and _no_periodo(l["data"], f)]

    atos_dim = atos_dim_base if conferido else {logico.get(l["ato_id"], l["ato_id"]) for l in dim if l["natureza"] == C.ORIGINAL}
    validos = [e for e in validos_todos if _no_periodo(e["data_publicacao"], f)]

    rep_logicos = {logico.get(e["ato_original_id"], e["ato_original_id"]) for e in validos if e["tipo"] == C.REPUBLICACAO}
    ret_logicos = {logico.get(e["ato_original_id"], e["ato_original_id"]) for e in validos if e["tipo"] == C.RETIFICACAO}
    cor_logicos = {logico.get(e["ato_original_id"], e["ato_original_id"]) for e in validos if e["tipo"] == C.CORRECAO}
    refeitos_logicos = {logico.get(e["ato_original_id"], e["ato_original_id"]) for e in validos if e["tipo"] in C.TIPOS_REFEITO}
    sem_efeito_logicos = {
        logico.get(e["ato_original_id"], e["ato_original_id"])
        for e in validos
        if e["tipo"] == C.SEM_EFEITO and decisoes_sem_efeito_por_evento.get(e["id"])
    }
    decisoes_se_periodo = {did for e in validos if e["tipo"] == C.SEM_EFEITO for did in decisoes_sem_efeito_por_evento.get(e["id"], ())}
    decisoes_ret_periodo = {did for e in validos if e["tipo"] in (C.RETIFICACAO, C.CORRECAO) for did in decisoes_retificadas_por_evento.get(e["id"], ())}

    refeitos = {l["ato_id"] for l in dim if logico.get(l["ato_id"], l["ato_id"]) in refeitos_logicos}
    sem_efeito = {l["ato_id"] for l in (dim + desconstituidas_lista) if logico.get(l["ato_id"], l["ato_id"]) in sem_efeito_logicos}

    unidades = _calcular_unidades(originais, logico)
    outras_resumo = _resumo_outras_publicacoes(banco)

    indicadores = {
        "processos": unidades["processos"]["total"],
        "resenhas": unidades["publicacoes"],
        "decisoes": unidades["decisoes"]["total"],
        "deferidos": unidades["decisoes"]["deferidos"],
        "indeferidos": unidades["decisoes"]["indeferidos"],
        "refeitos": len(refeitos_logicos) if conferido else None,
        "sem_efeito": len(sem_efeito_logicos) if conferido else None,
    }

    # Clique em um cartão: a tabela e os gráficos mostram exclusivamente o universo daquele indicador.
    cartao = f["cartao"]
    if cartao == "processos":
        recorte = [l for l in originais if l["processo"]]
    elif cartao in ("deferidos", "indeferidos"):
        recorte = [l for l in originais if l["resultado"] == ("DEFERIDO" if cartao == "deferidos" else "INDEFERIDO")]
    elif cartao == "refeitos":
        recorte = [l for l in dim if l["ato_id"] in refeitos and l["natureza"] == C.ORIGINAL] if conferido else []
    elif cartao == "sem_efeito":
        recorte = (
            [l for l in desconstituidas_lista if l["id"] in decisoes_se_periodo and l["natureza"] == C.ORIGINAL]
            if conferido else []
        )
    else:
        recorte = originais

    def conta(linhas):
        return {"total": len(linhas), "deferido": sum(l["resultado"] == "DEFERIDO" for l in linhas),
                "indeferido": sum(l["resultado"] == "INDEFERIDO" for l in linhas),
                "nao_informado": sum(l["resultado"] == "NAO_INFORMADO" for l in linhas)}

    prog = [l for l in recorte if l["eixo"] == C.PROGRESSAO]
    tempo = [l for l in recorte if l["eixo"] == C.TEMPO]
    cob = cobertura(banco, perfil=(PUBLICO if restringir_publico else perfil))
    diag_vr = cob["versao_regras_diagnostico"]
    if restringir_publico:
        meta_base = {
            "sistema": "Painel Diário Oficial | GEDIV",
            "versao_regras": C.VERSAO_REGRAS,
            "incompatibilidade_versao_regras": diag_vr["incompativel"],
            "versao_regras_diagnostico": diag_vr,
            "perfil": perfil,
            "escopo": f["escopo"],
            "preliminar": not conferido,
            "rotulo": "Decisões conferidas",
            "dados_individuais": False,
            "filtros": f,
            "cartao": f["cartao"],
            "cobertura": cob,
        }
        resp_pub = _aplicar_protecao_publica(
            originais, logico, refeitos_logicos, sem_efeito_logicos, conferido, cob, meta_base
        )
        return {k: resp_pub[k] for k in projecao.CHAVES_PAINEL}
    conferidas_vigentes = sum(l["validacao"] == "CONFERIDO" for l in todas)
    conferidas_com_conflito = sum(l["validacao"] == "CONFERIDO" and l["conflito_aberto"] for l in todas)
    conferidas_base = banco.con.execute(
        "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
        "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'CONFERIDO' AND d.vigente = 1").fetchone()[0]
    excluidas_integridade = conferidas_base - conferidas_vigentes
    if excluidas_integridade:
        cob["parecer"] += (f" {excluidas_integridade} decisão(ões) conferida(s) estão fora dos indicadores por "
                           "classificação desatualizada, até reconciliação.")
    if conferidas_com_conflito:
        cob["parecer"] += (f" {conferidas_com_conflito} decisão(ões) conferida(s) contadas têm conflito aberto "
                           "e aguardam revisão.")
    verticais = [l for l in prog if l["modalidade"] == C.VERTICAL]
    niveis_lista = []
    for nv in NIVEIS_VERTICAIS:
        itens_nv = [l for l in verticais if (l.get("nivel_info") or {}).get("nivel") == nv]
        cont_trans: dict[str, int] = {}
        for it in itens_nv:
            tr = (it.get("nivel_info") or {}).get("transicao")
            if tr:
                cont_trans[tr] = cont_trans.get(tr, 0) + 1
        transicoes_ord = [{"transicao": k, "total": v}
                          for k, v in sorted(cont_trans.items(), key=lambda x: (-x[1], x[0]))]
        niveis_lista.append({
            "nivel": nv,
            "rotulo": "Sem nível A–F efetivado" if nv == "NAO_IDENTIFICADO" else f"Nível {nv}",
            **conta(itens_nv),
            "transicoes": transicoes_ord,
        })
    situacoes_lista = []
    for sit in SITUACOES_NIVEL_VERTICAL:
        itens_s = [l for l in verticais if (l.get("nivel_info") or {}).get("categoria") == sit]
        cont_trans: dict[str, int] = {}
        for it in itens_s:
            tr = (it.get("nivel_info") or {}).get("transicao")
            if tr:
                cont_trans[tr] = cont_trans.get(tr, 0) + 1
        transicoes_ord = [{"transicao": k, "total": v}
                          for k, v in sorted(cont_trans.items(), key=lambda x: (-x[1], x[0]))]
        rot, desc = META_SITUACAO_NIVEL[sit]
        situacoes_lista.append({
            "codigo": sit,
            "nivel": sit if sit in _CLASSES_VALIDAS else "NAO_IDENTIFICADO",
            "rotulo": rot,
            "descricao": desc,
            "grupo_situacao": "nivel_af" if sit in _CLASSES_VALIDAS else "sem_nivel_af",
            **conta(itens_s),
            "transicoes": transicoes_ord,
        })
    NOMES_EXPRESSAO_PENDENTE = {
        "PENDENTE:TEC. ADM": "TEC. ADM · expressão incompatível ou pendente de confirmação (AST)",
        "PENDENTE:STF": "STF · expressão sem enquadramento fiscal verificado (SFT)",
    }
    eventos_detalhados = {
        "republicacoes_atos": len(rep_logicos) if conferido else None,
        "retificacoes_atos": len(ret_logicos) if conferido else None,
        "correcoes_atos": len(cor_logicos) if conferido else None,
        "sem_efeito_atos": len(sem_efeito_logicos) if conferido else None,
        "decisoes_republicadas": len(decisoes_republicadas_ids) if conferido else None,
        "decisoes_retificadas": len(decisoes_ret_periodo) if conferido else None,
        "decisoes_sem_efeito": len(decisoes_se_periodo) if conferido else None,
        "eventos_pendentes": sum(e["estado"] in ("PENDENTE_VINCULACAO", "SUGERIDO") for e in eventos),
        "eventos_fora_do_acervo": sum(e["estado"] == "FORA_DO_ACERVO" for e in eventos),
    }
    series = {
        "unidades": unidades,
        "eventos_detalhados": eventos_detalhados,
        "outras_publicacoes_resumo": outras_resumo,
        "por_assunto": [
            {"chave": "VERTICAL", "rotulo": "Progressão Vertical", **conta(verticais)},
            {"chave": "HORIZONTAL", "rotulo": "Progressão Horizontal", **conta([l for l in prog if l["modalidade"] == C.HORIZONTAL])},
            {"chave": "TEMPO_SERVICO", "rotulo": "Tempo de Serviço", **conta(tempo)},
        ],
        "progressao_sem_modalidade": sum(l["modalidade"] is None for l in prog),
        "por_data": [
            {"data": data,
             "vertical": sum(l["eixo"] == C.PROGRESSAO and l["modalidade"] == C.VERTICAL for l in grupo),
             "horizontal": sum(l["eixo"] == C.PROGRESSAO and l["modalidade"] == C.HORIZONTAL for l in grupo),
             "progressao_sem_modalidade": sum(l["eixo"] == C.PROGRESSAO and l["modalidade"] is None for l in grupo),
             "tempo": sum(l["eixo"] == C.TEMPO for l in grupo),
             "total": len(grupo)}
            for data in sorted({l["data"] or "" for l in recorte}) for grupo in [[l for l in recorte if (l["data"] or "") == data]]
        ],
        "por_grupo": [
            {"grupo": codigo, "nome": (C.GRUPO_POR_CODIGO[codigo].nome if codigo in C.GRUPO_POR_CODIGO else "Grupo não informado"),
             "horizontal": sum(l["modalidade"] == C.HORIZONTAL for l in linhas), "vertical": sum(l["modalidade"] == C.VERTICAL for l in linhas),
             **conta(linhas)}
            for codigo in [g.codigo for g in C.GRUPOS] + ["NAO_INFORMADO"]
            for linhas in [[l for l in prog if (l["grupo"] or "NAO_INFORMADO") == codigo]] if linhas
        ],
        "por_grupo_detalhado": [
            {"chave": chave,
             "grupo": chave if chave in C.GRUPO_POR_CODIGO else None,
             "expressao_pendente": chave.split(":", 1)[1] if chave.startswith("PENDENTE:") else None,
             "pendente_confirmacao": chave.startswith("PENDENTE:"),
             "nome": (C.GRUPO_POR_CODIGO[chave].nome if chave in C.GRUPO_POR_CODIGO
                      else NOMES_EXPRESSAO_PENDENTE.get(chave, "Grupo não informado")),
             "horizontal": sum(l["modalidade"] == C.HORIZONTAL for l in linhas),
             "vertical": sum(l["modalidade"] == C.VERTICAL for l in linhas),
             **conta(linhas)}
            for chave in [g.codigo for g in C.GRUPOS] + ["PENDENTE:TEC. ADM", "PENDENTE:STF", "NAO_INFORMADO"]
            for linhas in [[l for l in prog if _chave_grupo(l) == chave]] if linhas
        ],
        "por_nivel_vertical": niveis_lista,
        "por_situacao_nivel_vertical": situacoes_lista,
        "resumo_nivel_vertical": {
            "total_progressao": len(prog),
            "total_horizontal": sum(l["modalidade"] == C.HORIZONTAL for l in prog),
            "total_vertical": len(verticais),
            "classificados": sum((l.get("nivel_info") or {}).get("nivel") in _CLASSES_VALIDAS for l in verticais),
            "nao_identificados": sum((l.get("nivel_info") or {}).get("nivel") == "NAO_IDENTIFICADO" for l in verticais),
            "indeferidos": sum((l.get("nivel_info") or {}).get("categoria") == "INDEFERIDO" for l in verticais),
            "nao_determinados": sum((l.get("nivel_info") or {}).get("categoria") == "NAO_DETERMINADO" for l in verticais),
            "inconsistentes": sum((l.get("nivel_info") or {}).get("categoria") == "INCONSISTENTE" for l in verticais),
            "nao_aplica": sum((l.get("nivel_info") or {}).get("categoria") == "NAO_APLICA" for l in verticais),
        },
        # As sete subcategorias aparecem sempre; zero sem cobertura completa é "cobertura pendente", não "inexistente".
        "por_subcategoria": [
            {"codigo": s.codigo, "nome": s.nome, **conta(linhas),
             "situacao": None if linhas else ("sem ocorrência confirmada no período verificado" if cob["completa"] else "cobertura pendente")}
            for s in C.SUBCATEGORIAS for linhas in [[l for l in tempo if l["subcategoria"] == s.codigo]]
        ],
        "tempo_sem_subcategoria": conta([l for l in tempo if l["subcategoria"] is None]),
        "por_condicao": [{"condicao": c, "nome": n, "total": sum((l["condicao"] or "NAO_INFORMADA") == c for l in prog)}
                         for c, n in C.CONDICOES.items()],
        "comparativo_mensal": _comparativo_mensal(recorte, publico=False),
    }

    individual = perfil == GERENCIA_PERFIL
    cache: dict = {}
    resenhas: dict[str, dict] = {}
    for l in recorte:
        r = resenhas.setdefault(l["ato_id"], {
            "ato_id": l["ato_id"], "resenha": l["resenha"], "sufixo": l["sufixo"], "data": l["data"], "pagina": l["pagina"],
            "eixo": l["eixo"], "modalidade": l["modalidade"], "condicao": l["condicao"], "grupo": l["grupo"],
            "subcategoria": l["subcategoria"], "vinculo": l["vinculo"], "natureza": l["natureza"], "decisoes": 0,
            "deferido": 0, "indeferido": 0, "nao_informado": 0, "pendencias": l["pendencias"], "conflito_aberto": False,
            "refeito": l["ato_id"] in refeitos, "sem_efeito": l["ato_id"] in sem_efeito,
            **{campo: l[campo] for campo in documental.CAMPOS},
            **_fonte(banco, cache, l["sha256"], l["pagina"])})
        r["decisoes"] += 1
        r["deferido"] += l["resultado"] == "DEFERIDO"
        r["indeferido"] += l["resultado"] == "INDEFERIDO"
        r["nao_informado"] += l["resultado"] == "NAO_INFORMADO"
        r["conflito_aberto"] = r["conflito_aberto"] or bool(l["conflito_aberto"])

    um = lambda sql: banco.con.execute(sql).fetchone()[0]
    resposta = {
        "meta": {
            "sistema": "Painel Diário Oficial | GEDIV",
            "versao_regras": C.VERSAO_REGRAS,
            "incompatibilidade_versao_regras": diag_vr["incompativel"],
            "versao_regras_diagnostico": diag_vr,
            "perfil": perfil,
            "escopo": f["escopo"],
            "preliminar": not conferido,
            "rotulo": "Decisões conferidas" if conferido else "Em conferência · dados preliminares, não homologados",
            "dados_individuais": individual,
            "filtros": f,
            "cartao": cartao,
            "cobertura": cob,
        },
        "indicadores": indicadores,
        "ajuda": {c: ROTULOS[c] for c in CARTOES},
        "apoio": {
            "eventos_de_alteracao": len([e for e in validos if e["tipo"] in C.TIPOS_REFEITO]) if conferido else None,
            "eventos_por_tipo": {t: sum(e["tipo"] == t for e in validos) for t in C.ALTERACOES} if conferido else None,
            "eventos_sem_vinculo": sum(e["estado"] in ("PENDENTE_VINCULACAO", "SUGERIDO") for e in eventos),
            "eventos_fora_do_acervo": sum(e["estado"] == "FORA_DO_ACERVO" for e in eventos),
            "decisoes_pendentes": um("SELECT COUNT(*) FROM decisao WHERE validacao = 'PENDENTE' AND vigente = 1"),
            "decisoes_conferidas": conferidas_vigentes,
            "decisoes_excluidas_integridade": excluidas_integridade,
            "decisoes_conferidas_com_conflito": conferidas_com_conflito,
            "decisoes_rejeitadas": um("SELECT COUNT(*) FROM decisao WHERE validacao = 'REJEITADO'"),
            "conflitos_abertos": um("SELECT COUNT(*) FROM conflito WHERE estado = 'ABERTO'"),
            "classificacoes_desatualizadas": banco.classificacoes_desatualizadas("GEDIV", C.VERSAO_REGRAS),
            "vinculo_nao_expresso_pendente": um(
                "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE d.validacao = 'PENDENTE' AND a.vinculo <> 'EXPRESSO'"),
        },
        "series": series,
        "resenhas": [projecao.projetar("resenha", r, perfil)
                     for r in sorted(resenhas.values(), key=lambda r: (r["data"] or "", r["pagina"]), reverse=True)],
        "linhas": [{**{k: v for k, v in l.items() if k not in ("sha256", "pendencias")}, **_fonte(banco, cache, l["sha256"], l["pagina"]),
                    "refeito": l["ato_id"] in refeitos, "sem_efeito": l["ato_id"] in sem_efeito}
                   for l in recorte] if individual else [],
        "eventos": [projecao.projetar("evento", {**e, "resenhas_citadas": json.loads(e["resenhas_citadas"] or "[]"),
                                                  "processos_citados": json.loads(e["processos_citados"] or "[]"),
                                                  "decisoes_vinculadas": [lk["decisao_id"] for lk in links_por_evento.get(e["id"], [])],
                                                  **_fonte(banco, cache, e["sha256"], e["pagina"])}, perfil)
                    for e in eventos if individual or e["estado"] == "VALIDADO"],
    }
    return {k: resposta[k] for k in projecao.CHAVES_PAINEL}


def outras_publicacoes(banco: Banco, perfil: str = PUBLICO) -> list[dict]:
    """Página "Outras publicações": republicado por incorreção, portarias, atos normativos, alterações de lei.
    São resultados de triagem, pendentes de conferência; o trecho só é entregue à gerência."""
    cache: dict = {}
    saida = []
    for o in banco.con.execute("SELECT * FROM outra_publicacao WHERE gerencia = 'GEDIV' ORDER BY data_publicacao DESC, pagina"):
        item = {"id": o["id"], "tipo": o["tipo"], "nome_tipo": C.OUTRAS.get(o["tipo"], o["tipo"]), "data": o["data_publicacao"],
                "pagina": o["pagina"], "titulo": o["titulo"], "vinculo": o["vinculo"], "situacao": "triagem, a conferir",
                "trecho": o["trecho"], **_fonte(banco, cache, o["sha256"], o["pagina"])}
        saida.append(projecao.projetar("outra_publicacao", item, perfil))
    return saida
