"""Script de simulação (dry-run) e reconciliação idempotente do acervo GEDIV."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from observatorio.nucleo.banco import Banco
from observatorio.painel import documental
from observatorio.painel.adaptador import (
    extrair_bootstrap_de_html,
    importar_snapshot_reconciliado,
    projetar_para_dashboard_2910,
    simular_reconciliacao,
)
from observatorio.painel.indicadores import GERENCIA_PERFIL, PUBLICO as PUBLICO_PERFIL, outras_publicacoes, painel


def executar(
    origem_html: pathlib.Path | None = None,
    pasta_pdfs: pathlib.Path | None = None,
    relatorio_extra: pathlib.Path | None = None,
) -> int:
    env_html = os.environ.get("GEDIV_ORIGEM_HTML")
    html_path = origem_html or (pathlib.Path(env_html) if env_html else None)
    if html_path is None or not html_path.is_file():
        raise FileNotFoundError(
            "Informe --origem-html <arquivo.html> ou defina a variável de ambiente GEDIV_ORIGEM_HTML."
        )
    env_pdfs = os.environ.get("GEDIV_ACERVO_PDFS")
    dir_pdfs = pasta_pdfs or (pathlib.Path(env_pdfs) if env_pdfs else (REPO_DIR / "dados" / "pdfs_2026"))
    env_rel = os.environ.get("GEDIV_RELATORIO_EXTRA")
    dir_extra = relatorio_extra or (pathlib.Path(env_rel) if env_rel else None)

    db_orig = REPO_DIR / "dados" / "observatorio.sqlite3"
    db_backup = REPO_DIR / "dados" / "observatorio.225pdfs.backup.sqlite3"

    if db_orig.exists() and not db_backup.exists():
        shutil.copy2(db_orig, db_backup)
        print("Backup 225-PDF DB criado:", db_backup)

    bootstrap = extrair_bootstrap_de_html(html_path)

    # 1. Dry-run contra o banco original de 225 PDFs
    with Banco(db_backup) as banco_orig:
        dry_run = simular_reconciliacao(
            bootstrap,
            banco_comparacao=banco_orig,
            pasta_pdfs=dir_pdfs,
        )

    destinos_dry = [REPO_DIR / "dados" / "relatorio_dry_run_reconciliacao.json"]
    if dir_extra is not None:
        destinos_dry.append(dir_extra / "relatorio_dry_run_reconciliacao.json")
    for p in destinos_dry:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dry_run, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Dry-run salvo:", json.dumps(dry_run["totais_snapshot"], ensure_ascii=False))
    print("Comparacao:", json.dumps(dry_run["correspondencia_banco"], ensure_ascii=False))
    print("Qualidade/PDFs:", json.dumps(dry_run["qualidade_e_documentos"], ensure_ascii=False))

    # 2. Banco reconciliado idempotente (PROTEÇÃO CONTRA EXCLUSÃO AUTOMÁTICA — Seção 7)
    # É proibido apagar o banco reconciliado para reconstruí-lo: caso já exista, cria-se
    # backup prévio verificável e executa-se a importação estritamente idempotente em modo
    # incremental, preservando integralmente revisões humanas (CONFERIDO/REJEITADO).
    db_rec = REPO_DIR / "dados" / "observatorio_reconciliado.sqlite3"
    if db_rec.exists():
        bak_rec = REPO_DIR / "dados" / "observatorio_reconciliado.pre_reexecucao.backup.sqlite3"
        shutil.copy2(db_rec, bak_rec)
        print("Proteção ativa: banco reconciliado preservado (não excluído); backup salvo em:", bak_rec)
    with Banco(db_rec) as banco_rec:
        run1 = importar_snapshot_reconciliado(
            banco_rec, bootstrap, pasta_pdfs=dir_pdfs
        )
        run2 = importar_snapshot_reconciliado(
            banco_rec, bootstrap, pasta_pdfs=dir_pdfs
        )

        p_ger = painel(banco_rec, {"escopo": "pendente"}, GERENCIA_PERFIL)
        p_pub = painel(banco_rec, {"escopo": "conferido"}, PUBLICO_PERFIL)
        outras_ger = outras_publicacoes(banco_rec, GERENCIA_PERFIL)
        rej_consulta = banco_rec.con.execute(
            "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, d.cargo, d.detalhe, "
            "d.resultado, d.trecho, d.validacao, d.revisor, d.revisado_em, d.justificativa, a.numero AS resenha, a.sufixo, a.tipo, "
            "a.data_publicacao AS data, a.data_expediente, a.vinculo, a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, "
            "a.grupo_expressao, a.subcategoria, a.pendencias, a.chave_logica, "
            "a.gerencia AS gerencia_painel, SUBSTR(a.texto,1,1200) AS texto_identificacao, l.numero_edicao, l.data_edicao, "
            "0 AS conflito_aberto "
            "FROM decisao d JOIN ato a ON a.id = d.ato_id JOIN leitura l ON l.sha256 = d.sha256 "
            "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'REJEITADO'"
        ).fetchall()
        rej_linhas = []
        for r in rej_consulta:
            lr = dict(r)
            lr.update(documental.identificar(lr))
            lr.pop("texto_identificacao", None)
            lr["detalhe"] = json.loads(lr["detalhe"] or "{}")
            lr["pendencias"] = json.loads(lr["pendencias"] or "[]")
            url_of = banco_rec.url_oficial(lr["sha256"])
            lr["url_oficial"] = f"{url_of}#page={lr['pagina']}" if url_of else None
            lr["pdf_no_acervo"] = f"/api/pdf/{lr['sha256']}#page={lr['pagina']}"
            rej_linhas.append(lr)

        proj_pub = projetar_para_dashboard_2910(p_pub, [], [])
        proj_ger = projetar_para_dashboard_2910(p_ger, outras_ger, rej_linhas)

    # IMPORTANTE (Etapa 3 da Homologação Pós-Integração):
    # O banco original de 225 PDFs (`dados/observatorio.sqlite3`) NÃO é substituído automaticamente
    # pelo banco reconciliado de 52 PDFs (`dados/observatorio_reconciliado.sqlite3`), pois o banco
    # de 225 PDFs contém 2.014 decisões de outras 93 edições que ainda não constam na amostra de 52 PDFs.
    # Ambos os bancos permanecem preservados separadamente em `dados/`.

    h_rec = hashlib.sha256(db_rec.read_bytes()).hexdigest().upper()
    print("Run 1:", json.dumps(run1, ensure_ascii=False))
    print("Run 2 (idempotente):", json.dumps(run2, ensure_ascii=False))
    print("Projecao publica (rows/events):", len(proj_pub["rows"]), len(proj_pub["events"]))
    print("Projecao gerencia (rows/events):", len(proj_ger["rows"]), len(proj_ger["events"]))
    print(
        "Gerencia status:",
        {
            "pendente": sum(1 for r in proj_ger["rows"] if r["validation"] == "pendente"),
            "rejeitado": sum(1 for r in proj_ger["rows"] if r["validation"] == "rejeitado"),
            "conferido": sum(1 for r in proj_ger["rows"] if r["validation"] == "conferido"),
            "notas": sum(1 for r in proj_ger["rows"] if r.get("preliminaryReview")),
        },
    )
    print(
        "Nivel vertical:",
        json.dumps(p_ger["series"]["por_nivel_vertical"], ensure_ascii=False),
        json.dumps(p_ger["series"]["resumo_nivel_vertical"], ensure_ascii=False),
    )
    print(
        "Grupos detalhados:",
        [(g["grupo"], g["total"]) for g in p_ger["series"]["por_grupo_detalhado"] if g["total"] > 0],
    )
    print("SHA-256 observatorio_reconciliado.sqlite3:", h_rec)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa simulação e reconciliação idempotente do acervo GEDIV.")
    parser.add_argument("--origem-html", type=pathlib.Path, default=None, help="HTML snapshot privado (ou GEDIV_ORIGEM_HTML).")
    parser.add_argument("--acervo-pdfs", type=pathlib.Path, default=None, help="Pasta local de PDFs (ou GEDIV_ACERVO_PDFS).")
    parser.add_argument("--relatorio-extra", type=pathlib.Path, default=None, help="Diretório adicional para gravar o dry-run JSON.")
    args = parser.parse_args(argv)
    return executar(args.origem_html, args.acervo_pdfs, args.relatorio_extra)


if __name__ == "__main__":
    raise SystemExit(main())
