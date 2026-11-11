"""Decisões de revisão, com trilha de auditoria.

Regras:
- toda decisão exige responsável e justificativa;
- CONFERIR exige a declaração de que o PDF oficial foi conferido (`confirma_fonte`) e, quando o ato
  não expressa a GEDIV, a confirmação explícita do vínculo (`confirma_vinculo`);
- um evento de alteração só é vinculado a um ato original existente, por decisão humana;
- nada é apagado: cada mudança registra autor, momento, estado anterior e posterior, e pode ser reaberta.
"""
from __future__ import annotations

from ..nucleo.banco import Banco, agora

CONFERIR, REJEITAR, REABRIR, VINCULAR = "CONFERIR", "REJEITAR", "REABRIR", "VINCULAR"
_ESTADO = {CONFERIR: "CONFERIDO", REJEITAR: "REJEITADO", REABRIR: "PENDENTE"}
CAMPOS_CORRIGIVEIS = ("processo", "servidor", "matricula", "lotacao", "cargo", "resultado")


class Recusada(ValueError):
    """A decisão não atende às regras de revisão."""


def _exigir(autor: str, justificativa: str) -> tuple[str, str]:
    autor, justificativa = (autor or "").strip(), (justificativa or "").strip()
    if len(autor) < 3:
        raise Recusada("informe o responsável pela revisão")
    if len(justificativa) < 5:
        raise Recusada("informe a justificativa da decisão")
    return autor[:120], justificativa[:1000]


def revisar_decisoes(banco: Banco, ids, decisao: str, autor: str, justificativa: str, confirma_fonte: bool = False,
                     confirma_vinculo: bool = False, correcoes: dict | None = None) -> dict:
    if decisao not in _ESTADO:
        raise Recusada("decisão inválida")
    autor, justificativa = _exigir(autor, justificativa)
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise Recusada("nenhum registro informado")
    correcoes = {k: (str(v).strip() or None) for k, v in (correcoes or {}).items()}
    if set(correcoes) - set(CAMPOS_CORRIGIVEIS):
        raise Recusada("campo não corrigível: " + ", ".join(sorted(set(correcoes) - set(CAMPOS_CORRIGIVEIS))))
    if correcoes and len(ids) != 1:
        raise Recusada("correções de campos valem para um registro por vez")
    if correcoes.get("resultado") not in (None, "DEFERIDO", "INDEFERIDO", "NAO_INFORMADO"):
        raise Recusada("resultado inválido")
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
            anterior = {c: l[c] for c in ("validacao", *CAMPOS_CORRIGIVEIS)}
            posterior = {**anterior, **correcoes, "validacao": novo}
            banco.con.execute(
                "UPDATE decisao SET validacao = ?, revisor = ?, revisado_em = ?, justificativa = ?, processo = ?, servidor = ?, "
                "matricula = ?, lotacao = ?, cargo = ?, resultado = ? WHERE id = ?",
                (novo, autor, momento, justificativa, *(posterior[c] for c in CAMPOS_CORRIGIVEIS), l["id"]))
            banco.auditar(autor, decisao, "decisao", l["id"], anterior, posterior, justificativa)
    return {"alterados": len(linhas), "estado": novo}


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
        ato = banco.con.execute("SELECT id FROM ato WHERE id = ?", (alvo,)).fetchone() if alvo else None
        if ato is None or alvo == evento["ato_id"]:
            raise Recusada("informe o ato original (diferente do ato modificador) ao qual o evento se refere")
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
