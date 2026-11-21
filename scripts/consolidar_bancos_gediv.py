"""Consolidação segura, auditável e idempotente dos bancos SQLite do Observatório GEDIV.

Consolida o banco histórico de 225 PDFs (`dados/observatorio.sqlite3`) com as informações
complementares do banco reconciliado de 52 PDFs (`dados/observatorio_reconciliado.sqlite3`),
gravando EXCLUSIVAMENTE em um terceiro banco de teste (ex.: `dados/observatorio_consolidado_teste.sqlite3`).

Regras de segurança:
- Os dois bancos de origem são abertos estritamente em modo somente-leitura (`mode=ro`).
- O destino nunca pode coincidir com nenhum dos bancos de origem.
- Nenhuma revisão humana (`CONFERIDO` ou `REJEITADO`) existente é sobrescrita.
- Divergências de classificação (`eixo`/`modalidade`) são registradas como conflitos abertos
  na tabela nativa `conflito`, sem resolução automática.
- Equivalências controvertidas (`TEC. ADM` -> `AST`, `STF` -> `SFT`) são mantidas como
  pendências (`grupo = NULL`, preservando `grupo_expressao` e trilha em `auditoria`).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from observatorio.gerencias.gediv import catalogo as C
from observatorio.nucleo.banco import Banco
from observatorio.painel import indicadores


AUTOR_CONSOLIDACAO = "consolidacao-gediv"
ORIGEM_CONSOLIDACAO = "CONSOLIDACAO_RECONCILIADO"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(valor: str | None) -> str:
    return (valor or "").strip().upper()


def sha256_arquivo(caminho: pathlib.Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest().upper()


def integrity_check(caminho: pathlib.Path) -> str:
    with contextlib.closing(sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)) as con:
        return str(con.execute("PRAGMA integrity_check").fetchone()[0])


def criar_backup_sqlite(origem: pathlib.Path, destino: pathlib.Path) -> dict:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(f"file:{origem}?mode=ro", uri=True)) as src:
        with contextlib.closing(sqlite3.connect(destino)) as dst:
            src.backup(dst)
    h_orig = sha256_arquivo(origem)
    h_dest = sha256_arquivo(destino)
    ic_orig = integrity_check(origem)
    ic_dest = integrity_check(destino)
    (destino.with_suffix(destino.suffix + ".sha256")).write_text(
        f"{h_dest}  {destino.name}\n", encoding="utf-8"
    )
    return {
        "origem": str(origem),
        "backup": str(destino),
        "tamanho_bytes": destino.stat().st_size,
        "sha256_origem": h_orig,
        "sha256_backup": h_dest,
        "integrity_origem": ic_orig,
        "integrity_backup": ic_dest,
    }


def _registrar_auditoria(
    con: sqlite3.Connection,
    acao: str,
    alvo_tipo: str,
    alvo_id: str,
    anterior: dict | None,
    posterior: dict | None,
    justificativa: str,
) -> None:
    con.execute(
        "INSERT INTO auditoria(momento, autor, acao, alvo_tipo, alvo_id, anterior, posterior, justificativa) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _agora_iso(),
            AUTOR_CONSOLIDACAO,
            acao,
            alvo_tipo,
            alvo_id,
            json.dumps(anterior, ensure_ascii=False) if anterior is not None else None,
            json.dumps(posterior, ensure_ascii=False) if posterior is not None else None,
            justificativa,
        ),
    )


def _inserir_conflito_idempotente(
    con: sqlite3.Connection,
    alvo_tipo: str,
    alvo_id: str,
    campo: str,
    valor_vigente: str,
    valor_proposto: str,
    referencia: str,
) -> bool:
    existe = con.execute(
        "SELECT 1 FROM conflito WHERE alvo_tipo = ? AND alvo_id = ? AND campo = ? AND origem = ? AND referencia = ?",
        (alvo_tipo, alvo_id, campo, ORIGEM_CONSOLIDACAO, referencia),
    ).fetchone()
    if existe:
        return False
    con.execute(
        "INSERT INTO conflito(alvo_tipo, alvo_id, campo, valor_vigente, valor_proposto, origem, referencia, estado, criado_em) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, 'ABERTO', ?)",
        (alvo_tipo, alvo_id, campo, valor_vigente, valor_proposto, ORIGEM_CONSOLIDACAO, referencia, _agora_iso()),
    )
    return True


def _parse_json_list(texto: str | None) -> list[str]:
    try:
        v = json.loads(texto or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def consolidar_bancos(
    origem_historico: pathlib.Path,
    origem_reconciliado: pathlib.Path,
    destino: pathlib.Path,
    pasta_backups: pathlib.Path | None = None,
) -> dict:
    """Executa a consolidação não destrutiva e idempotente em `destino`."""
    orig_h = origem_historico.resolve()
    orig_r = origem_reconciliado.resolve()
    dest = destino.resolve()

    if dest in (orig_h, orig_r):
        raise ValueError(
            "Operação bloqueada: o banco de destino não pode coincidir com nenhum dos bancos originais."
        )
    if not orig_h.exists():
        raise FileNotFoundError(f"Banco histórico ausente: {orig_h}")
    if not orig_r.exists():
        raise FileNotFoundError(f"Banco reconciliado ausente: {orig_r}")

    sha_h_antes = sha256_arquivo(orig_h)
    sha_r_antes = sha256_arquivo(orig_r)
    ic_h_antes = integrity_check(orig_h)
    ic_r_antes = integrity_check(orig_r)

    backups = {}
    if pasta_backups is not None:
        backups["historico"] = criar_backup_sqlite(
            orig_h, pasta_backups / "observatorio.pre_consolidacao.sqlite3"
        )
        backups["reconciliado"] = criar_backup_sqlite(
            orig_r, pasta_backups / "observatorio_reconciliado.pre_consolidacao.sqlite3"
        )

    inicializado_agora = False
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(f"file:{orig_h}?mode=ro", uri=True)) as src:
            with contextlib.closing(sqlite3.connect(dest)) as dcon:
                src.backup(dcon)
        inicializado_agora = True

    stats = {
        "inicializado_agora": inicializado_agora,
        "versao_regras_alvo": C.VERSAO_REGRAS,
        "classificacoes_alinhadas_versao_regras": 0,
        "atos_alinhados_versao_regras": 0,
        "equivalencias_revertidas_para_pendente": {"TEC. ADM": 0, "STF": 0},
        "decisoes_exclusivas_incorporadas": 0,
        "atos_exclusivos_incorporados": 0,
        "notas_preliminares_incorporadas": 0,
        "notas_preliminares_ja_presentes": 0,
        "rejeicoes_preservadas": 0,
        "rejeicoes_ja_preservadas": 0,
        "divergencias_classificacao_registradas": 0,
        "divergencias_classificacao_ja_registradas": 0,
        "conflitos_vigente0_registrados": 0,
        "conflitos_vigente0_ja_registrados": 0,
        "eventos_sobrepostos_eliminados": 0,
        "eventos_novos_incorporados": 0,
        "outras_publicacoes_incorporadas": 0,
        "outras_publicacoes_ja_presentes": 0,
    }
    divergencias_detalhe: list[dict] = []
    vigente0_detalhe: list[dict] = []

    with contextlib.closing(sqlite3.connect(f"file:{orig_r}?mode=ro", uri=True)) as rcon:
        rcon.row_factory = sqlite3.Row
        with contextlib.closing(sqlite3.connect(dest)) as dcon:
            dcon.row_factory = sqlite3.Row
            dcon.execute("PRAGMA foreign_keys = ON")

            with dcon:
                # 0. Alinhar versao_regras no banco de teste à versão ativa do catálogo para compatibilidade com indicadores/adaptador
                cls_desal = dcon.execute(
                    "SELECT COUNT(*) FROM classificacao WHERE gerencia = 'GEDIV' AND versao_regras <> ?",
                    (C.VERSAO_REGRAS,),
                ).fetchone()[0]
                if cls_desal:
                    versoes_ant = [
                        r[0]
                        for r in dcon.execute(
                            "SELECT DISTINCT versao_regras FROM classificacao WHERE gerencia = 'GEDIV' AND versao_regras <> ?",
                            (C.VERSAO_REGRAS,),
                        ).fetchall()
                    ]
                    dcon.execute(
                        "UPDATE classificacao SET versao_regras = ? WHERE gerencia = 'GEDIV' AND versao_regras <> ?",
                        (C.VERSAO_REGRAS, C.VERSAO_REGRAS),
                    )
                    _registrar_auditoria(
                        dcon,
                        "ALINHAR_VERSAO_REGRAS",
                        "classificacao",
                        "GEDIV",
                        {"versoes_anteriores": versoes_ant, "total": cls_desal},
                        {"versao_regras": C.VERSAO_REGRAS, "total": cls_desal},
                        "Alinhamento da tag versao_regras no banco consolidado de teste à versão ativa do catálogo.",
                    )
                    stats["classificacoes_alinhadas_versao_regras"] = cls_desal

                atos_desal = dcon.execute(
                    "SELECT COUNT(*) FROM ato WHERE gerencia = 'GEDIV' AND versao_regras <> ?",
                    (C.VERSAO_REGRAS,),
                ).fetchone()[0]
                if atos_desal:
                    dcon.execute(
                        "UPDATE ato SET versao_regras = ? WHERE gerencia = 'GEDIV' AND versao_regras <> ?",
                        (C.VERSAO_REGRAS, C.VERSAO_REGRAS),
                    )
                    stats["atos_alinhados_versao_regras"] = atos_desal

                # 1. Manter TEC. ADM e STF como pendências (sem equiparar automaticamente a AST/SFT)
                atos_controvertidos = dcon.execute(
                    "SELECT id, grupo, grupo_expressao, pendencias FROM ato "
                    "WHERE gerencia = 'GEDIV' AND eixo = 'PROGRESSAO' AND grupo IS NOT NULL AND grupo_expressao IS NOT NULL"
                ).fetchall()
                for a in atos_controvertidos:
                    exp_up = _norm(a["grupo_expressao"])
                    chave_pend = None
                    aviso = None
                    if re.search(r"\bTEC\.?\s*ADM\b", exp_up) or exp_up == "TEC-ADM":
                        chave_pend = "TEC. ADM"
                        aviso = "expressão 'TEC. ADM' sem grupo homologado: vínculo normativo com AST pendente de confirmação pela GEDIV"
                    elif re.search(r"\bSTF\b", exp_up):
                        chave_pend = "STF"
                        aviso = "expressão 'STF' sem grupo homologado: vínculo normativo com SFT pendente de confirmação pela GEDIV"
                    if chave_pend:
                        pends = _parse_json_list(a["pendencias"])
                        if aviso not in pends:
                            pends.append(aviso)
                        dcon.execute(
                            "UPDATE ato SET grupo = NULL, pendencias = ? WHERE id = ?",
                            (json.dumps(pends, ensure_ascii=False), a["id"]),
                        )
                        _registrar_auditoria(
                            dcon,
                            "PENDENCIA_EQUIVALENCIA_GRUPO",
                            "ato",
                            a["id"],
                            {"grupo": a["grupo"], "grupo_expressao": a["grupo_expressao"]},
                            {"grupo": None, "grupo_expressao": a["grupo_expressao"]},
                            aviso,
                        )
                        stats["equivalencias_revertidas_para_pendente"][chave_pend] += 1

                # 2. Indexar decisões existentes em destino (vigente=1 e vigente=0)
                def _carregar_indice_destino():
                    rows = dcon.execute(
                        "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.matricula, d.resultado, "
                        "d.validacao, d.vigente, d.representada_por, d.detalhe, d.origem, "
                        "a.eixo, a.modalidade, a.grupo, a.grupo_expressao, a.numero, a.sufixo, a.data_publicacao "
                        "FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.gerencia = 'GEDIV'"
                    ).fetchall()
                    by_id = {r["id"]: r for r in rows}
                    vig_pm: dict[tuple[str, str], list[sqlite3.Row]] = {}
                    vig_p: dict[str, list[sqlite3.Row]] = {}
                    nvig_pm: dict[tuple[str, str], list[sqlite3.Row]] = {}
                    nvig_p: dict[str, list[sqlite3.Row]] = {}
                    for r in rows:
                        pm = (_norm(r["processo"]), _norm(r["matricula"]))
                        p = _norm(r["processo"])
                        if r["vigente"] == 1:
                            vig_pm.setdefault(pm, []).append(r)
                            if p:
                                vig_p.setdefault(p, []).append(r)
                        else:
                            nvig_pm.setdefault(pm, []).append(r)
                            if p:
                                nvig_p.setdefault(p, []).append(r)
                    return by_id, vig_pm, vig_p, nvig_pm, nvig_p

                dest_by_id, vig_pm, vig_p, nvig_pm, nvig_p = _carregar_indice_destino()

                # 3. Processar decisões do banco reconciliado
                rec_atos = {
                    a["id"]: dict(a)
                    for a in rcon.execute("SELECT * FROM ato WHERE gerencia = 'GEDIV'").fetchall()
                }
                rec_decs = rcon.execute(
                    "SELECT d.*, a.eixo, a.modalidade, a.grupo, a.grupo_expressao, a.numero, a.sufixo, a.data_publicacao "
                    "FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.gerencia = 'GEDIV' ORDER BY d.rowid"
                ).fetchall()

                for rd in rec_decs:
                    rd_id = rd["id"]
                    det_rec = json.loads(rd["detalhe"] or "{}")
                    nota_rec = str(det_rec.get("nota_preliminar") or "").strip()
                    pm = (_norm(rd["processo"]), _norm(rd["matricula"]))
                    p = _norm(rd["processo"])

                    # Caso especial: registro explicitamente REJEITADO na base reconciliada
                    if rd["validacao"] == "REJEITADO":
                        # Procurar primeiro cópia duplicada (vigente=0) do mesmo processo/matrícula para preservar
                        # tanto a decisão ativa (vigente=1) quanto o registro rejeitado sem duplicar linhas.
                        alvo_rej = None
                        cands_nv = nvig_pm.get(pm) or (nvig_p.get(p) if p else None) or []
                        if cands_nv:
                            alvo_rej = cands_nv[0]
                        else:
                            cands_v = vig_pm.get(pm) or (vig_p.get(p) if p else None) or []
                            if cands_v:
                                alvo_rej = cands_v[0]

                        if alvo_rej is not None:
                            if alvo_rej["validacao"] == "REJEITADO":
                                stats["rejeicoes_ja_preservadas"] += 1
                            elif alvo_rej["validacao"] == "PENDENTE":
                                just = (
                                    f"Registro rejeitado preservado da base de referência "
                                    f"(duplicidade de publicação; ref. {rd_id})"
                                )
                                dcon.execute(
                                    "UPDATE decisao SET validacao = 'REJEITADO', revisor = ?, revisado_em = ?, justificativa = ? "
                                    "WHERE id = ?",
                                    (AUTOR_CONSOLIDACAO, _agora_iso(), just, alvo_rej["id"]),
                                )
                                _registrar_auditoria(
                                    dcon,
                                    "PRESERVAR_REJEICAO",
                                    "decisao",
                                    alvo_rej["id"],
                                    {"validacao": alvo_rej["validacao"], "vigente": alvo_rej["vigente"]},
                                    {"validacao": "REJEITADO", "vigente": alvo_rej["vigente"]},
                                    just,
                                )
                                stats["rejeicoes_preservadas"] += 1
                        continue

                    # Se já foi incorporado em execução anterior (mesmo ID), verificar apenas idempotência
                    if rd_id in dest_by_id:
                        if nota_rec:
                            det_exist = json.loads(dest_by_id[rd_id]["detalhe"] or "{}")
                            if det_exist.get("nota_preliminar"):
                                stats["notas_preliminares_ja_presentes"] += 1
                        continue

                    # Tentar correspondência em decisões vigentes (vigente=1)
                    cands_v = vig_pm.get(pm) or (vig_p.get(p) if p else None)
                    if cands_v:
                        alvo = next((c for c in cands_v if c["sha256"] == rd["sha256"]), cands_v[0])

                        # 3a. Incorporar nota preliminar sem sobrescrever nota ou revisão humana existente
                        if nota_rec:
                            det_alvo = json.loads(alvo["detalhe"] or "{}")
                            if det_alvo.get("nota_preliminar"):
                                stats["notas_preliminares_ja_presentes"] += 1
                            else:
                                det_alvo["nota_preliminar"] = nota_rec
                                det_alvo.setdefault("id_referencia_snapshot", rd_id)
                                dcon.execute(
                                    "UPDATE decisao SET detalhe = ? WHERE id = ?",
                                    (json.dumps(det_alvo, ensure_ascii=False), alvo["id"]),
                                )
                                _registrar_auditoria(
                                    dcon,
                                    "INCORPORAR_NOTA_PRELIMINAR",
                                    "decisao",
                                    alvo["id"],
                                    {"nota_preliminar": None},
                                    {"nota_preliminar_presente": True, "referencia": rd_id},
                                    "Observação preliminar incorporada sem alterar estado de validação humana.",
                                )
                                stats["notas_preliminares_incorporadas"] += 1

                        # 3b. Registrar divergência de classificação (eixo/modalidade) sem resolver automaticamente
                        if (alvo["eixo"], alvo["modalidade"]) != (rd["eixo"], rd["modalidade"]):
                            val_vig = json.dumps(
                                {
                                    "eixo": alvo["eixo"],
                                    "modalidade": alvo["modalidade"],
                                    "resultado": alvo["resultado"],
                                },
                                ensure_ascii=False,
                            )
                            val_prop = json.dumps(
                                {
                                    "eixo": rd["eixo"],
                                    "modalidade": rd["modalidade"],
                                    "resultado": rd["resultado"],
                                },
                                ensure_ascii=False,
                            )
                            inseriu = _inserir_conflito_idempotente(
                                dcon,
                                "decisao",
                                alvo["id"],
                                "classificacao_eixo_modalidade",
                                val_vig,
                                val_prop,
                                rd_id,
                            )
                            if inseriu:
                                stats["divergencias_classificacao_registradas"] += 1
                            else:
                                stats["divergencias_classificacao_ja_registradas"] += 1
                            divergencias_detalhe.append(
                                {
                                    "processo": rd["processo"],
                                    "data_publicacao": rd["data_publicacao"],
                                    "resenha": f"{rd['numero'] or ''} {rd['sufixo'] or ''}".strip(),
                                    "decisao_historica_id": alvo["id"],
                                    "decisao_reconciliada_id": rd_id,
                                    "historico": {
                                        "eixo": alvo["eixo"],
                                        "modalidade": alvo["modalidade"],
                                        "resultado": alvo["resultado"],
                                    },
                                    "reconciliado": {
                                        "eixo": rd["eixo"],
                                        "modalidade": rd["modalidade"],
                                        "resultado": rd["resultado"],
                                    },
                                    "status": "PENDENTE_CONFERENCIA_HUMANA",
                                }
                            )
                        continue

                    # Tentar correspondência em decisões não vigentes (vigente=0) — evitar duplicação
                    cands_nv = nvig_pm.get(pm) or (nvig_p.get(p) if p else None)
                    if cands_nv:
                        alvo_nv = next((c for c in cands_nv if c["sha256"] == rd["sha256"]), cands_nv[0])
                        inseriu = _inserir_conflito_idempotente(
                            dcon,
                            "decisao",
                            alvo_nv["id"],
                            "vigencia_reconciliacao",
                            "vigente=0 (histórico)",
                            f"presente no reconciliado ({rd['eixo']}/{rd['modalidade'] or '-'})",
                            rd_id,
                        )
                        if inseriu:
                            stats["conflitos_vigente0_registrados"] += 1
                        else:
                            stats["conflitos_vigente0_ja_registrados"] += 1
                        vigente0_detalhe.append(
                            {
                                "processo": rd["processo"],
                                "data_publicacao": rd["data_publicacao"],
                                "resenha": f"{rd['numero'] or ''} {rd['sufixo'] or ''}".strip(),
                                "decisao_historica_id": alvo_nv["id"],
                                "decisao_reconciliada_id": rd_id,
                                "pagina": rd["pagina"],
                                "status": "PENDENTE_CONFERENCIA_HUMANA",
                            }
                        )
                        continue

                    # Caso C: Decisão genuinamente exclusiva do banco reconciliado
                    ato_rec = rec_atos[rd["ato_id"]]
                    existe_ato = dcon.execute("SELECT 1 FROM ato WHERE id = ?", (ato_rec["id"],)).fetchone()
                    if not existe_ato:
                        dcon.execute(
                            "INSERT INTO ato(id, gerencia, sha256, tipo, numero, sufixo, pagina, pagina_final, "
                            "data_publicacao, data_expediente, vinculo, expressao_vinculo, natureza, eixo, modalidade, "
                            "condicao, grupo, grupo_expressao, subcategoria, resultado, texto, pendencias, versao_regras, chave_logica) "
                            "VALUES(:id, :gerencia, :sha256, :tipo, :numero, :sufixo, :pagina, :pagina_final, "
                            ":data_publicacao, :data_expediente, :vinculo, :expressao_vinculo, :natureza, :eixo, :modalidade, "
                            ":condicao, :grupo, :grupo_expressao, :subcategoria, :resultado, :texto, :pendencias, :versao_regras, :chave_logica)",
                            ato_rec,
                        )
                        stats["atos_exclusivos_incorporados"] += 1

                    dcon.execute(
                        "INSERT INTO decisao(id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, "
                        "detalhe, resultado, trecho, validacao, revisor, revisado_em, justificativa, chave_logica, "
                        "vigente, representada_por, origem) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)",
                        (
                            rd_id,
                            rd["ato_id"],
                            rd["sha256"],
                            rd["pagina"],
                            rd["processo"],
                            rd["servidor"],
                            rd["matricula"],
                            rd["lotacao"],
                            rd["cargo"],
                            rd["detalhe"],
                            rd["resultado"],
                            rd["trecho"],
                            rd["validacao"],
                            rd["revisor"],
                            rd["revisado_em"],
                            rd["justificativa"],
                            rd["chave_logica"],
                            ORIGEM_CONSOLIDACAO,
                        ),
                    )
                    _registrar_auditoria(
                        dcon,
                        "INCORPORAR_DECISAO_EXCLUSIVA",
                        "decisao",
                        rd_id,
                        None,
                        {"ato_id": rd["ato_id"], "eixo": rd["eixo"], "modalidade": rd["modalidade"], "origem": ORIGEM_CONSOLIDACAO},
                        "Decisão exclusiva incorporada do banco reconciliado de 52 PDFs sem sobreposição.",
                    )
                    stats["decisoes_exclusivas_incorporadas"] += 1

                # 4. Eventos modificadores (eliminar sobreposições comprovadas e incorporar novos)
                dest_evs = dcon.execute(
                    "SELECT id, sha256, tipo, data_publicacao, resenhas_citadas, processos_citados FROM evento"
                ).fetchall()
                dest_ev_ids = {e["id"] for e in dest_evs}
                rec_evs = rcon.execute("SELECT * FROM evento ORDER BY rowid").fetchall()

                for re_row in rec_evs:
                    if re_row["id"] in dest_ev_ids:
                        stats["eventos_sobrepostos_eliminados"] += 1
                        continue
                    r_res = {_norm(x) for x in _parse_json_list(re_row["resenhas_citadas"])}
                    r_proc = {_norm(x) for x in _parse_json_list(re_row["processos_citados"])}
                    coberto = False
                    for de in dest_evs:
                        same_doc = (de["sha256"] == re_row["sha256"]) or (de["data_publicacao"] == re_row["data_publicacao"])
                        same_tipo = _norm(de["tipo"]) == _norm(re_row["tipo"])
                        d_res = {_norm(x) for x in _parse_json_list(de["resenhas_citadas"])}
                        d_proc = {_norm(x) for x in _parse_json_list(de["processos_citados"])}
                        if same_doc and same_tipo and ((r_proc & d_proc) or (r_res & d_res)):
                            coberto = True
                            break
                    if coberto:
                        stats["eventos_sobrepostos_eliminados"] += 1
                    else:
                        dcon.execute(
                            "INSERT INTO evento(id, gerencia, sha256, ato_id, tipo, subtipo, pagina, data_publicacao, "
                            "modificador, resenhas_citadas, processos_citados, vinculo, texto, ato_sugerido_id, "
                            "ato_original_id, estado, fundamento, revisor, revisado_em, publicacoes_citadas) "
                            "VALUES(:id, :gerencia, :sha256, :ato_id, :tipo, :subtipo, :pagina, :data_publicacao, "
                            ":modificador, :resenhas_citadas, :processos_citados, :vinculo, :texto, :ato_sugerido_id, "
                            ":ato_original_id, :estado, :fundamento, :revisor, :revisado_em, :publicacoes_citadas)",
                            dict(re_row),
                        )
                        _registrar_auditoria(
                            dcon,
                            "INCORPORAR_EVENTO_EXCLUSIVO",
                            "evento",
                            re_row["id"],
                            None,
                            {"tipo": re_row["tipo"], "data_publicacao": re_row["data_publicacao"], "estado": re_row["estado"]},
                            "Evento modificador exclusivo incorporado do banco reconciliado.",
                        )
                        dest_ev_ids.add(re_row["id"])
                        dest_evs.append(re_row)
                        stats["eventos_novos_incorporados"] += 1

                # 5. Outras publicações (`Outros benefícios` individuais do reconciliado, preservando as 67 históricas)
                dest_ou_ids = {r[0] for r in dcon.execute("SELECT id FROM outra_publicacao").fetchall()}
                rec_ous = rcon.execute("SELECT * FROM outra_publicacao ORDER BY rowid").fetchall()
                for ro in rec_ous:
                    if ro["id"] in dest_ou_ids:
                        stats["outras_publicacoes_ja_presentes"] += 1
                    else:
                        dcon.execute(
                            "INSERT INTO outra_publicacao(id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                            "VALUES(:id, :gerencia, :sha256, :tipo, :pagina, :data_publicacao, :titulo, :vinculo, :trecho)",
                            dict(ro),
                        )
                        dest_ou_ids.add(ro["id"])
                        stats["outras_publicacoes_incorporadas"] += 1

    # Verificação pós-consolidação (originais intocados + integridade do destino)
    sha_h_depois = sha256_arquivo(orig_h)
    sha_r_depois = sha256_arquivo(orig_r)
    sha_dest = sha256_arquivo(dest)
    ic_dest = integrity_check(dest)

    if sha_h_antes != sha_h_depois or sha_r_antes != sha_r_depois:
        raise RuntimeError("VIOLAÇÃO DE INTEGRIDADE: um dos bancos originais teve alteração de SHA-256!")

    return {
        "integridade": {
            "historico_original": {
                "caminho": str(orig_h),
                "tamanho_bytes": orig_h.stat().st_size,
                "sha256_antes": sha_h_antes,
                "sha256_depois": sha_h_depois,
                "inalterado": sha_h_antes == sha_h_depois,
                "integrity_check": ic_h_antes,
            },
            "reconciliado_original": {
                "caminho": str(orig_r),
                "tamanho_bytes": orig_r.stat().st_size,
                "sha256_antes": sha_r_antes,
                "sha256_depois": sha_r_depois,
                "inalterado": sha_r_antes == sha_r_depois,
                "integrity_check": ic_r_antes,
            },
            "consolidado_teste": {
                "caminho": str(dest),
                "tamanho_bytes": dest.stat().st_size,
                "sha256": sha_dest,
                "integrity_check": ic_dest,
            },
            "backups": backups,
        },
        "operacoes": stats,
        "comparativo": {
            "historico_225pdfs": resumir_banco(orig_h),
            "reconciliado_52pdfs": resumir_banco(orig_r),
            "consolidado_teste": resumir_banco(dest),
        },
        "pendencias_humanas": {
            "divergencias_classificacao_total": len(divergencias_detalhe),
            "divergencias_classificacao": divergencias_detalhe,
            "conflitos_vigente0_total": len(vigente0_detalhe),
            "conflitos_vigente0": vigente0_detalhe,
        },
    }


def resumir_banco(caminho: pathlib.Path) -> dict:
    """Produz contagens distintas por unidade (decisões, publicações, processos, resenhas, eventos, outros benefícios)."""
    with contextlib.closing(sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        publicacoes_pdf = con.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0]
        decisoes_totais = con.execute(
            "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.gerencia = 'GEDIV'"
        ).fetchone()[0]
        decisoes_vigentes = con.execute(
            "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao != 'REJEITADO'"
        ).fetchone()[0]
        decisoes_originais_vigentes = con.execute(
            "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao != 'REJEITADO' AND a.natureza = 'ORIGINAL'"
        ).fetchone()[0]
        decisoes_nao_originais_vigentes = decisoes_vigentes - decisoes_originais_vigentes
        decisoes_rejeitadas = con.execute(
            "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'REJEITADO'"
        ).fetchone()[0]
        decisoes_conferidas = con.execute(
            "SELECT COUNT(*) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao = 'CONFERIDO'"
        ).fetchone()[0]
        processos_distintos = con.execute(
            "SELECT COUNT(DISTINCT UPPER(TRIM(d.processo))) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao != 'REJEITADO' AND TRIM(COALESCE(d.processo,'')) != ''"
        ).fetchone()[0]
        resenhas_atos_distintos = con.execute(
            "SELECT COUNT(DISTINCT d.ato_id) FROM decisao d JOIN ato a ON a.id = d.ato_id "
            "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao != 'REJEITADO'"
        ).fetchone()[0]
        notas_preliminares = con.execute(
            "SELECT COUNT(*) FROM decisao WHERE detalhe LIKE '%nota_preliminar%'"
        ).fetchone()[0]
        eventos_total = con.execute("SELECT COUNT(*) FROM evento").fetchone()[0]
        outras_total = con.execute("SELECT COUNT(*) FROM outra_publicacao").fetchone()[0]
        outras_por_tipo = {
            r["tipo"]: r["n"]
            for r in con.execute("SELECT tipo, COUNT(*) AS n FROM outra_publicacao GROUP BY tipo ORDER BY tipo")
        }
        conflitos_abertos = con.execute("SELECT COUNT(*) FROM conflito WHERE estado = 'ABERTO'").fetchone()[0]
        auditoria_total = con.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]

    # Contagens via motor oficial `indicadores.painel` (garantindo consistência com o painel 29/10)
    with Banco(caminho) as banco:
        p = indicadores.painel(banco, {"escopo": "pendente"}, indicadores.GERENCIA_PERFIL)
        linhas = p["linhas"]
        por_eixo = Counter(l["eixo"] for l in linhas)
        por_modalidade = Counter(f"{l['eixo']}:{l['modalidade'] or 'N/A'}" for l in linhas)
        por_resultado = Counter(l["resultado"] for l in linhas)
        por_grupo = {
            g["chave"]: g["total"]
            for g in p["series"]["por_grupo_detalhado"]
            if g["total"] > 0
        }
        niveis_af = {item["nivel"]: item["total"] for item in p["series"]["por_nivel_vertical"]}
        resumo_af = p["series"]["resumo_nivel_vertical"]

    # Fallback somente-leitura para bancos originais com versao_regras distinta da ativa no catálogo
    if not linhas and decisoes_vigentes > 0:
        with contextlib.closing(sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            rows_sql = con.execute(
                "SELECT a.eixo, a.modalidade, a.grupo, a.grupo_expressao, d.resultado, d.detalhe, d.trecho "
                "FROM decisao d JOIN ato a ON a.id = d.ato_id "
                "WHERE a.gerencia = 'GEDIV' AND d.vigente = 1 AND d.validacao != 'REJEITADO' AND a.natureza = 'ORIGINAL'"
            ).fetchall()
            por_eixo = Counter(r["eixo"] for r in rows_sql)
            por_modalidade = Counter(f"{r['eixo']}:{r['modalidade'] or 'N/A'}" for r in rows_sql)
            por_resultado = Counter(r["resultado"] for r in rows_sql)
            grp_c: Counter[str] = Counter()
            nv_c: Counter[str] = Counter({k: 0 for k in indicadores.NIVEIS_VERTICAIS})
            tot_v = tot_h = 0
            for r in rows_sql:
                ld = dict(r)
                ld["detalhe"] = json.loads(ld["detalhe"] or "{}")
                if ld["eixo"] == C.PROGRESSAO:
                    grp_c[indicadores._chave_grupo(ld)] += 1
                    if ld["modalidade"] == C.VERTICAL:
                        tot_v += 1
                        nv = indicadores.classificar_nivel_vertical(ld)
                        nv_c[nv["nivel"] or "NAO_IDENTIFICADO"] += 1
                    elif ld["modalidade"] == C.HORIZONTAL:
                        tot_h += 1
            por_grupo = dict(grp_c)
            niveis_af = dict(nv_c)
            resumo_af = {
                "total_progressao": tot_v + tot_h,
                "total_horizontal": tot_h,
                "total_vertical": tot_v,
                "classificados": sum(nv_c[k] for k in ("A", "B", "C", "D", "E", "F")),
                "nao_identificados": nv_c["NAO_IDENTIFICADO"],
            }

    return {
        "publicacoes_pdfs": publicacoes_pdf,
        "decisoes_vigentes": decisoes_vigentes,
        "decisoes_originais_painel": decisoes_originais_vigentes,
        "decisoes_nao_originais_vigentes": decisoes_nao_originais_vigentes,
        "decisoes_totais_tabela": decisoes_totais,
        "decisoes_conferidas": decisoes_conferidas,
        "decisoes_rejeitadas": decisoes_rejeitadas,
        "processos_distintos_vigentes": processos_distintos,
        "resenhas_atos_distintos_vigentes": resenhas_atos_distintos,
        "eventos_modificadores": eventos_total,
        "outros_beneficios_e_outras_publicacoes": outras_total,
        "outras_publicacoes_por_tipo": outras_por_tipo,
        "notas_preliminares": notas_preliminares,
        "conflitos_abertos": conflitos_abertos,
        "trilha_auditoria": auditoria_total,
        "por_eixo": dict(por_eixo),
        "por_modalidade": dict(por_modalidade),
        "por_resultado": dict(por_resultado),
        "por_grupo": por_grupo,
        "niveis_verticais_af": niveis_af,
        "resumo_nivel_vertical": resumo_af,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidação segura dos bancos SQLite do GEDIV em banco de teste.")
    parser.add_argument("--origem-historico", type=pathlib.Path, default=REPO_DIR / "dados" / "observatorio.sqlite3")
    parser.add_argument("--origem-reconciliado", type=pathlib.Path, default=REPO_DIR / "dados" / "observatorio_reconciliado.sqlite3")
    parser.add_argument("--destino", type=pathlib.Path, default=REPO_DIR / "dados" / "observatorio_consolidado_teste.sqlite3")
    parser.add_argument(
        "--pasta-backups",
        type=pathlib.Path,
        default=REPO_DIR / "dados" / "backups_pre_consolidacao_20261120",
    )
    parser.add_argument("--relatorio-json", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)

    resultado = consolidar_bancos(
        origem_historico=args.origem_historico,
        origem_reconciliado=args.origem_reconciliado,
        destino=args.destino,
        pasta_backups=args.pasta_backups,
    )
    if args.relatorio_json:
        args.relatorio_json.parent.mkdir(parents=True, exist_ok=True)
        args.relatorio_json.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
