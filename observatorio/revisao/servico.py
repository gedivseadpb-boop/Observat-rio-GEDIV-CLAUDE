"""Decisões de revisão, com trilha de auditoria.

Regras:
- toda decisão exige responsável e justificativa;
- CONFERIR exige a declaração de que o PDF oficial foi conferido (`confirma_fonte`) e, quando o ato
  não expressa a GEDIV, a confirmação explícita do vínculo (`confirma_vinculo`);
- um evento de alteração só é vinculado a um ato original existente, por decisão humana;
- nada é apagado: cada mudança registra autor, momento, estado anterior e posterior, e pode ser reaberta.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..gerencias.gediv import catalogo as C
from ..nucleo.banco import Banco, agora, chave_decisao, normalizar_texto

CONFERIR, REJEITAR, REABRIR, VINCULAR = "CONFERIR", "REJEITAR", "REABRIR", "VINCULAR"
ACEITAR, MANTER = "ACEITAR", "MANTER"
_ESTADO = {CONFERIR: "CONFERIDO", REJEITAR: "REJEITADO", REABRIR: "PENDENTE"}
CAMPOS_CORRIGIVEIS = ("processo", "servidor", "matricula", "lotacao", "cargo", "resultado")
# Etapa 05.3.3: classe e nível (guardados em `detalhe`) também são corrigíveis, sempre nos domínios publicados.
CAMPOS_DETALHE = ("classe_anterior", "classe_posterior", "nivel_anterior", "nivel_atual")
CAMPOS_ATO = ("eixo", "modalidade", "condicao", "grupo", "subcategoria")
_CLASSES = set("ABCDEF")
_NIVEL = re.compile(r"^(?:[IVX]{1,5}|NIVEL \d{1,2})$")


class Recusada(ValueError):
    """A decisão não atende às regras de revisão."""


def _exigir(autor: str, justificativa: str) -> tuple[str, str]:
    autor, justificativa = (autor or "").strip(), (justificativa or "").strip()
    if len(autor) < 3:
        raise Recusada("informe o responsável pela revisão")
    if len(justificativa) < 5:
        raise Recusada("informe a justificativa da decisão")
    return autor[:120], justificativa[:1000]


def _validar_detalhe(correcoes: dict) -> None:
    for campo in ("classe_anterior", "classe_posterior"):
        if correcoes.get(campo) is not None and correcoes[campo] not in _CLASSES:
            raise Recusada(f"{campo}: as classes documentadas são A, B, C, D, E e F")
    for campo in ("nivel_anterior", "nivel_atual"):
        if correcoes.get(campo) is not None:
            correcoes[campo] = re.sub(r"^N[IÍ]VEL\s*", "NIVEL ", correcoes[campo].upper())
            if not _NIVEL.match(correcoes[campo]):
                raise Recusada(f"{campo}: use o nível como publicado (algarismos romanos, ex.: III, ou 'NIVEL 3')")


def _limpar(correcoes: dict | None) -> dict:
    return {k: (str(v).strip().upper() if k in CAMPOS_DETALHE + CAMPOS_ATO + ("resultado",) else str(v).strip()) or None
            for k, v in (correcoes or {}).items()}


def _registrar_correcao(banco: Banco, alvo_tipo, alvo_id, campo, anterior, corrigido, autor, justificativa) -> None:
    """Valor extraído (o primeiro, antes de qualquer correção), anterior, corrigido, autor, momento e justificativa."""
    primeira = banco.con.execute("SELECT valor_extraido FROM correcao WHERE alvo_tipo = ? AND alvo_id = ? AND campo = ? "
                                 "ORDER BY id LIMIT 1", (alvo_tipo, alvo_id, campo)).fetchone()
    extraido = primeira[0] if primeira else json.dumps(anterior, ensure_ascii=False)
    banco.con.execute(
        "INSERT INTO correcao (alvo_tipo, alvo_id, campo, valor_extraido, valor_anterior, valor_corrigido, autor, momento, justificativa) "
        "VALUES (?,?,?,?,?,?,?,?,?)", (alvo_tipo, alvo_id, campo, extraido, json.dumps(anterior, ensure_ascii=False),
                                       json.dumps(corrigido, ensure_ascii=False), autor, agora(), justificativa))


def revisar_decisoes(banco: Banco, ids, decisao: str, autor: str, justificativa: str, confirma_fonte: bool = False,
                     confirma_vinculo: bool = False, correcoes: dict | None = None) -> dict:
    if decisao not in _ESTADO:
        raise Recusada("decisão inválida")
    autor, justificativa = _exigir(autor, justificativa)
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise Recusada("nenhum registro informado")
    correcoes = _limpar(correcoes)
    invalidos = set(correcoes) - set(CAMPOS_CORRIGIVEIS) - set(CAMPOS_DETALHE)
    if invalidos:
        raise Recusada("campo não corrigível: " + ", ".join(sorted(invalidos)))
    if correcoes and len(ids) != 1:
        raise Recusada("correções de campos valem para um registro por vez")
    if correcoes and not confirma_fonte:
        raise Recusada("para corrigir é preciso declarar que o PDF oficial foi consultado")
    if correcoes.get("resultado") not in (None, *C.RESULTADOS):
        raise Recusada("resultado inválido")
    _validar_detalhe(correcoes)
    marcas = ",".join("?" * len(ids))
    linhas = banco.con.execute(
        f"SELECT d.*, a.vinculo, a.eixo FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE d.id IN ({marcas})", ids).fetchall()
    if len(linhas) != len(ids):
        raise Recusada("registro não encontrado")
    if decisao == CONFERIR:
        if not confirma_fonte:
            raise Recusada("para conferir é preciso declarar que o PDF oficial foi consultado")
        if any(l["vinculo"] != "EXPRESSO" for l in linhas) and not confirma_vinculo:
            raise Recusada("o ato não expressa a GEDIV: confirme o vínculo institucional para conferir")
    momento, novo = agora(), _ESTADO[decisao]
    with banco.con:
        for l in linhas:
            detalhe = json.loads(l["detalhe"] or "{}")
            anterior = {c: l[c] for c in ("validacao", *CAMPOS_CORRIGIVEIS)} | {c: detalhe.get(c) for c in CAMPOS_DETALHE if c in detalhe or c in correcoes}
            posterior = {**anterior, **correcoes, "validacao": novo}
            for campo, valor in correcoes.items():
                if valor != anterior.get(campo):
                    _registrar_correcao(banco, "decisao", l["id"], campo, anterior.get(campo), valor, autor, justificativa)
            detalhe.update({c: correcoes[c] for c in CAMPOS_DETALHE if c in correcoes})
            chave_do_ato = banco.con.execute("SELECT chave_logica FROM ato WHERE id = ?", (l["ato_id"],)).fetchone()[0]
            banco.con.execute(
                "UPDATE decisao SET validacao = ?, revisor = ?, revisado_em = ?, justificativa = ?, processo = ?, servidor = ?, "
                "matricula = ?, lotacao = ?, cargo = ?, resultado = ?, detalhe = ?, chave_logica = ? WHERE id = ?",
                (novo, autor, momento, justificativa, *(posterior[c] for c in CAMPOS_CORRIGIVEIS),
                 json.dumps(detalhe, ensure_ascii=False), chave_decisao(chave_do_ato, posterior["processo"], posterior["matricula"]), l["id"]))
            banco.auditar(autor, decisao, "decisao", l["id"], anterior, posterior, justificativa)
        if correcoes or decisao in (CONFERIR, REABRIR):
            chaves = {r[0] for r in banco.con.execute(
                f"SELECT DISTINCT a.chave_logica FROM ato a JOIN decisao d ON d.ato_id = a.id WHERE d.id IN ({marcas})", ids)}
            banco._reconciliar_atos(chaves)
    return {"alterados": len(linhas), "estado": novo}


def corrigir_ato(banco: Banco, ato_id: str, correcoes: dict, autor: str, justificativa: str, confirma_fonte: bool = False) -> dict:
    """Corrige a classificação temática do ato (eixo, modalidade, condição, grupo PCCR, assunto do Tempo de Serviço),
    sempre dentro do catálogo: dois eixos, 16 grupos, 7 assuntos. Nenhuma equivalência é presumida (TEC. ADM e STF
    continuam sem grupo até homologação). A correção vale para todas as decisões do ato e fica na trilha."""
    autor, justificativa = _exigir(autor, justificativa)
    if not confirma_fonte:
        raise Recusada("para corrigir é preciso declarar que o PDF oficial foi consultado")
    correcoes = _limpar(correcoes)
    if not correcoes or set(correcoes) - set(CAMPOS_ATO):
        raise Recusada("campos corrigíveis do ato: " + ", ".join(CAMPOS_ATO))
    ato = banco.con.execute("SELECT * FROM ato WHERE id = ?", (ato_id,)).fetchone()
    if ato is None:
        raise Recusada("ato não encontrado")
    final = {c: ato[c] for c in CAMPOS_ATO} | correcoes
    if final["eixo"] not in C.EIXOS:
        raise Recusada("eixo inválido: o painel tem exatamente dois eixos")
    if final["eixo"] == C.PROGRESSAO:
        if final["subcategoria"] is not None:
            raise Recusada("assunto do Tempo de Serviço não se aplica à Progressão Funcional")
        if final["modalidade"] not in (None, *C.MODALIDADES):
            raise Recusada("modalidade inválida (Horizontal ou Vertical)")
        if final["grupo"] not in (None, *C.GRUPO_POR_CODIGO):
            raise Recusada("grupo PCCR fora do catálogo")
        if final["condicao"] not in (None, *C.CONDICOES):
            raise Recusada("condição inválida")
    else:
        if any(final[c] is not None for c in ("modalidade", "grupo", "condicao")):
            raise Recusada("modalidade, grupo e condição só se aplicam à Progressão Funcional")
        if final["subcategoria"] not in (None, *C.SUBCATEGORIA_POR_CODIGO):
            raise Recusada("assunto do Tempo de Serviço fora do catálogo")
    mudou = {c: v for c, v in final.items() if v != ato[c]}
    if not mudou:
        return {"alterados": 0}
    with banco.con:
        for campo, valor in mudou.items():
            _registrar_correcao(banco, "ato", ato_id, campo, ato[campo], valor, autor, justificativa)
        banco.con.execute(f"UPDATE ato SET {', '.join(f'{c} = ?' for c in mudou)} WHERE id = ?", (*mudou.values(), ato_id))
        banco.auditar(autor, "CORRIGIR", "ato", ato_id, {c: ato[c] for c in mudou}, mudou, justificativa)
    return {"alterados": len(mudou)}


def registrar_decisao_omitida(banco: Banco, ato_id: str, pagina: int, trecho: str, campos: dict, autor: str, justificativa: str,
                              confirma_fonte: bool = False) -> dict:
    """Registro CONTROLADO de uma decisão que o robô não extraiu. Exige o trecho literal do documento, que precisa
    constar do texto lido daquela página; processo, matrícula e nome informados precisam constar do trecho. Nada é
    inventado: o que não estiver no trecho fica vazio. Entra como CONFERIDA (decisão humana), origem MANUAL."""
    autor, justificativa = _exigir(autor, justificativa)
    if not confirma_fonte:
        raise Recusada("para registrar é preciso declarar que o PDF oficial foi consultado")
    ato = banco.con.execute("SELECT * FROM ato WHERE id = ?", (ato_id,)).fetchone()
    if ato is None:
        raise Recusada("ato não encontrado")
    trecho = " ".join((trecho or "").split())
    if len(trecho) < 15:
        raise Recusada("informe o trecho literal do documento que contém a decisão")
    texto = banco.con.execute("SELECT texto FROM pagina WHERE sha256 = ? AND numero = ?", (ato["sha256"], int(pagina))).fetchone()
    if texto is None or normalizar_texto(trecho) not in normalizar_texto(texto[0]):
        raise Recusada("o trecho não consta do texto lido dessa página do documento")
    campos = _limpar(campos)
    invalidos = set(campos) - set(CAMPOS_CORRIGIVEIS) - set(CAMPOS_DETALHE)
    if invalidos:
        raise Recusada("campo não aceito: " + ", ".join(sorted(invalidos)))
    for campo in ("processo", "matricula", "servidor"):
        if campos.get(campo) and normalizar_texto(campos[campo]) not in normalizar_texto(trecho):
            raise Recusada(f"{campo} informado não consta do trecho")
    if campos.get("resultado") not in (None, *C.RESULTADOS):
        raise Recusada("resultado inválido")
    _validar_detalhe(campos)
    if not (campos.get("processo") or campos.get("matricula")):
        raise Recusada("informe ao menos o processo ou a matrícula, como constam do trecho")
    ident = hashlib.sha256("|".join(("MANUAL", ato_id, campos.get("processo") or "", campos.get("matricula") or "",
                                     normalizar_texto(trecho))).encode()).hexdigest()[:20]
    if banco.con.execute("SELECT 1 FROM decisao WHERE id = ?", (ident,)).fetchone():
        raise Recusada("essa decisão já foi registrada")
    detalhe = {c: campos[c] for c in CAMPOS_DETALHE if campos.get(c)}
    with banco.con:
        banco.con.execute(
            "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, detalhe, resultado, trecho, "
            "validacao, revisor, revisado_em, justificativa, chave_logica, origem) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'CONFERIDO',?,?,?,?,'MANUAL')",
            (ident, ato_id, ato["sha256"], int(pagina), campos.get("processo"), campos.get("servidor"), campos.get("matricula"),
             campos.get("lotacao"), campos.get("cargo"), json.dumps(detalhe, ensure_ascii=False), campos.get("resultado") or "NAO_INFORMADO",
             trecho, autor, agora(), justificativa, chave_decisao(ato["chave_logica"], campos.get("processo"), campos.get("matricula"))))
        banco.auditar(autor, "REGISTRAR_OMITIDA", "decisao", ident, None, {**campos, "pagina": int(pagina), "ato_id": ato_id}, justificativa)
        banco._reconciliar_atos({ato["chave_logica"]})
    return {"id": ident, "estado": "CONFERIDO"}


def resolver_conflito(banco: Banco, conflito_id: int, decisao: str, autor: str, justificativa: str, confirma_fonte: bool = False) -> dict:
    """ACEITAR aplica a proposta (com registro de correção) ou, para vigência, passa a contar a decisão como distinta;
    MANTER conserva o valor vigente. As duas ficam na trilha e não voltam a ser propostas."""
    autor, justificativa = _exigir(autor, justificativa)
    c = banco.con.execute("SELECT * FROM conflito WHERE id = ?", (int(conflito_id),)).fetchone()
    if c is None or c["estado"] != "ABERTO":
        raise Recusada("conflito inexistente ou já resolvido")
    if decisao not in (ACEITAR, MANTER):
        raise Recusada("decisão inválida (ACEITAR ou MANTER)")
    if decisao == ACEITAR and not confirma_fonte:
        raise Recusada("para aceitar é preciso declarar que o PDF oficial foi consultado")
    proposto = json.loads(c["valor_proposto"])
    if decisao == ACEITAR and c["campo"] not in ("vigencia", "presenca"):
        if c["alvo_tipo"] == "ato":
            corrigir_ato(banco, c["alvo_id"], {c["campo"]: proposto}, autor, justificativa, True)
        else:
            atual = banco.con.execute("SELECT validacao FROM decisao WHERE id = ?", (c["alvo_id"],)).fetchone()
            revisar_decisoes(banco, [c["alvo_id"]], {"PENDENTE": REABRIR}.get(atual["validacao"], CONFERIR) if atual["validacao"] != "REJEITADO"
                             else REJEITAR, autor, justificativa, True, True, {c["campo"]: proposto})
    with banco.con:
        banco.con.execute("UPDATE conflito SET estado = ?, resolvido_por = ?, resolvido_em = ?, justificativa = ? WHERE id = ?",
                          ("ACEITO" if decisao == ACEITAR else "MANTIDO", autor, agora(), justificativa, c["id"]))
        banco.auditar(autor, f"CONFLITO_{decisao}", c["alvo_tipo"], c["alvo_id"],
                      {"campo": c["campo"], "valor": json.loads(c["valor_vigente"])}, {"campo": c["campo"], "proposta": proposto}, justificativa)
        if c["alvo_tipo"] == "decisao" and c["campo"] in ("vigencia", "presenca"):
            ato = banco.con.execute("SELECT ato_id FROM decisao WHERE id = ?", (c["alvo_id"],)).fetchone()
            if ato:
                banco._aplicar_resolucoes([ato[0]])
    return {"conflito": c["id"], "estado": "ACEITO" if decisao == ACEITAR else "MANTIDO"}


def revisar_ato(banco: Banco, ato_id: str, decisao: str, autor: str, justificativa: str, confirma_fonte: bool = False,
                confirma_vinculo: bool = False) -> dict:
    """Aplica a decisão a todas as decisões ainda PENDENTES do ato (resenha inteira)."""
    filtro = "validacao <> 'PENDENTE'" if decisao == REABRIR else "validacao = 'PENDENTE'"
    ids = [l["id"] for l in banco.con.execute(f"SELECT id FROM decisao WHERE ato_id = ? AND {filtro}", (ato_id,))]
    if not ids:
        raise Recusada("o ato não tem decisões nesse estado")
    return revisar_decisoes(banco, ids, decisao, autor, justificativa, confirma_fonte, confirma_vinculo)


def revisar_evento(banco: Banco, evento_id: str, decisao: str, autor: str, justificativa: str, ato_original_id: str | None = None,
                   confirma_fonte: bool = False) -> dict:
    autor, justificativa = _exigir(autor, justificativa)
    evento = banco.con.execute("SELECT * FROM evento WHERE id = ?", (evento_id,)).fetchone()
    if evento is None:
        raise Recusada("evento não encontrado")
    anterior = {"estado": evento["estado"], "ato_original_id": evento["ato_original_id"]}
    if decisao == VINCULAR:
        if not confirma_fonte:
            raise Recusada("para vincular é preciso declarar que os dois documentos oficiais foram consultados")
        alvo = ato_original_id or evento["ato_sugerido_id"]
        ato = banco.con.execute("SELECT * FROM ato WHERE id = ?", (alvo,)).fetchone() if alvo else None
        if ato is None or alvo == evento["ato_id"]:
            raise Recusada("informe o ato original (diferente do ato modificador) ao qual o evento se refere")
        # Etapa 05.3.3: o alvo precisa ser um ato ORIGINAL da mesma gerência, publicado até a data do evento.
        if ato["natureza"] != C.ORIGINAL or ato["gerencia"] != evento["gerencia"]:
            raise Recusada("o vínculo só pode apontar para um ato original da mesma gerência")
        if ato["data_publicacao"] and evento["data_publicacao"] and ato["data_publicacao"] > evento["data_publicacao"]:
            raise Recusada("o ato original não pode ser posterior ao evento que o altera")
        posterior = {"estado": "VALIDADO", "ato_original_id": alvo}
    elif decisao == REJEITAR:
        posterior = {"estado": "REJEITADO", "ato_original_id": None}
    elif decisao == REABRIR:
        posterior = {"estado": "SUGERIDO" if evento["ato_sugerido_id"] else "PENDENTE_VINCULACAO", "ato_original_id": None}
    else:
        raise Recusada("decisão inválida")
    with banco.con:
        banco.con.execute("UPDATE evento SET estado = ?, ato_original_id = ?, revisor = ?, revisado_em = ?, fundamento = ? WHERE id = ?",
                          (posterior["estado"], posterior["ato_original_id"], autor, agora(), justificativa, evento_id))
        banco.auditar(autor, decisao, "evento", evento_id, anterior, posterior, justificativa)
    return {"alterados": 1, "estado": posterior["estado"]}
