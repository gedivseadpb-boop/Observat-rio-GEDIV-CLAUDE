"""Testes automatizados da consolidação segura dos bancos SQLite do GEDIV."""
from __future__ import annotations

import contextlib
import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, documental, indicadores
from scripts.consolidar_bancos_gediv import (
    ORIGEM_CONSOLIDACAO,
    consolidar_bancos,
    integrity_check,
    resumir_banco,
    sha256_arquivo,
)

DB_HIST = REPO_DIR / "dados" / "observatorio.sqlite3"
DB_REC = REPO_DIR / "dados" / "observatorio_reconciliado.sqlite3"
DB_TESTE = REPO_DIR / "dados" / "observatorio_consolidado_teste.sqlite3"
DIR_BACKUPS = REPO_DIR / "dados" / "backups_pre_consolidacao_20261120"

SHA_HIST_ESPERADO = "CD80A1ADAA8B06A4871AE3A6DBF021CBD2D5C2BF912FF01267E2C85A3003D454"
SHA_REC_ESPERADO = "A3792C3040F24526C2513AE41A20B4665A006EA5CD61316A371C8F5EC727145A"


@unittest.skipUnless(
    DB_HIST.exists() and DB_REC.exists() and DB_TESTE.exists(),
    "Bancos locais privados indisponíveis neste ambiente.",
)
class TestConsolidacaoBancosGEDIV(unittest.TestCase):
    def test_01_originais_intocados_integridade_e_trava_seguranca(self):
        self.assertEqual(sha256_arquivo(DB_HIST), SHA_HIST_ESPERADO)
        self.assertEqual(sha256_arquivo(DB_REC), SHA_REC_ESPERADO)
        self.assertEqual(integrity_check(DB_HIST), "ok")
        self.assertEqual(integrity_check(DB_REC), "ok")
        self.assertEqual(integrity_check(DB_TESTE), "ok")

        bak_h = DIR_BACKUPS / "observatorio.pre_consolidacao.sqlite3"
        bak_r = DIR_BACKUPS / "observatorio_reconciliado.pre_consolidacao.sqlite3"
        self.assertTrue(bak_h.exists(), "Backup pré-consolidação do histórico ausente.")
        self.assertTrue(bak_r.exists(), "Backup pré-consolidação do reconciliado ausente.")
        self.assertEqual(integrity_check(bak_h), "ok")
        self.assertEqual(integrity_check(bak_r), "ok")

        # Trava de segurança: destino nunca pode coincidir com nenhum original
        with self.assertRaises(ValueError):
            consolidar_bancos(DB_HIST, DB_REC, DB_HIST, pasta_backups=None)
        with self.assertRaises(ValueError):
            consolidar_bancos(DB_HIST, DB_REC, DB_REC, pasta_backups=None)

    def test_02_idempotencia_e_preservacao_revisao_humana(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = pathlib.Path(tmp) / "teste_idempotencia.sqlite3"
            r1 = consolidar_bancos(DB_HIST, DB_REC, tmp_db, pasta_backups=None)

            self.assertEqual(r1["operacoes"]["decisoes_exclusivas_incorporadas"], 53)
            self.assertEqual(r1["operacoes"]["notas_preliminares_incorporadas"], 101)
            self.assertEqual(r1["operacoes"]["rejeicoes_preservadas"], 1)
            self.assertEqual(r1["operacoes"]["divergencias_classificacao_registradas"], 24)
            self.assertEqual(r1["operacoes"]["conflitos_vigente0_registrados"], 6)
            self.assertEqual(r1["operacoes"]["eventos_sobrepostos_eliminados"], 22)
            self.assertEqual(r1["operacoes"]["eventos_novos_incorporados"], 1)
            self.assertEqual(r1["operacoes"]["outras_publicacoes_incorporadas"], 80)
            self.assertGreater(r1["operacoes"]["equivalencias_revertidas_para_pendente"]["TEC. ADM"], 0)
            self.assertGreater(r1["operacoes"]["equivalencias_revertidas_para_pendente"]["STF"], 0)

            # Simular uma revisão humana CONFERIDO antes da 2ª execução para provar preservação
            with contextlib.closing(sqlite3.connect(tmp_db)) as con:
                alvo_id = con.execute(
                    "SELECT id FROM decisao WHERE vigente = 1 AND validacao = 'PENDENTE' LIMIT 1"
                ).fetchone()[0]
                con.execute(
                    "UPDATE decisao SET validacao = 'CONFERIDO', revisor = 'analista.teste', "
                    "justificativa = 'Conferido em teste' WHERE id = ?",
                    (alvo_id,),
                )
                con.commit()

            r2 = consolidar_bancos(DB_HIST, DB_REC, tmp_db, pasta_backups=None)
            self.assertFalse(r2["operacoes"]["inicializado_agora"])
            self.assertEqual(r2["operacoes"]["decisoes_exclusivas_incorporadas"], 0)
            self.assertEqual(r2["operacoes"]["notas_preliminares_incorporadas"], 0)
            self.assertEqual(r2["operacoes"]["notas_preliminares_ja_presentes"], 101)
            self.assertEqual(r2["operacoes"]["rejeicoes_preservadas"], 0)
            self.assertEqual(r2["operacoes"]["rejeicoes_ja_preservadas"], 1)
            self.assertEqual(r2["operacoes"]["divergencias_classificacao_registradas"], 0)
            self.assertEqual(r2["operacoes"]["divergencias_classificacao_ja_registradas"], 24)
            self.assertEqual(r2["operacoes"]["conflitos_vigente0_registrados"], 0)
            self.assertEqual(r2["operacoes"]["conflitos_vigente0_ja_registrados"], 6)
            self.assertEqual(r2["operacoes"]["eventos_novos_incorporados"], 0)
            self.assertEqual(r2["operacoes"]["outras_publicacoes_incorporadas"], 0)
            self.assertEqual(r2["operacoes"]["equivalencias_revertidas_para_pendente"], {"TEC. ADM": 0, "STF": 0})
            self.assertEqual(integrity_check(tmp_db), "ok")

            # Confirmar que a revisão humana CONFERIDO foi 100% preservada
            with contextlib.closing(sqlite3.connect(tmp_db)) as con:
                row = con.execute("SELECT validacao, revisor FROM decisao WHERE id = ?", (alvo_id,)).fetchone()
                self.assertEqual(row, ("CONFERIDO", "analista.teste"))

    def test_03_contagens_eixos_grupos_modalidades_resultados_e_af(self):
        resumo = resumir_banco(DB_TESTE)
        self.assertEqual(resumo["publicacoes_pdfs"], 225)
        self.assertEqual(resumo["decisoes_vigentes"], 3664)  # 3611 históricas + 53 exclusivas
        self.assertEqual(resumo["decisoes_rejeitadas"], 1)
        self.assertEqual(resumo["notas_preliminares"], 101)
        self.assertEqual(resumo["eventos_modificadores"], 22)  # 21 históricos + 1 novo
        self.assertEqual(resumo["outros_beneficios_e_outras_publicacoes"], 147)  # 67 + 80
        self.assertEqual(resumo["conflitos_abertos"], 104)  # 74 originais + 24 divergências + 6 vigente=0

        # Consistência matemática de eixos, modalidades, resultados e A–F (sobre decisões originais do painel)
        originais = resumo["decisoes_originais_painel"]
        self.assertEqual(originais + resumo["decisoes_nao_originais_vigentes"], 3664)
        self.assertEqual(sum(resumo["por_eixo"].values()), originais)
        self.assertEqual(sum(resumo["por_modalidade"].values()), originais)
        self.assertEqual(sum(resumo["por_resultado"].values()), originais)

        rv = resumo["resumo_nivel_vertical"]
        self.assertEqual(rv["total_horizontal"] + rv["total_vertical"], rv["total_progressao"])
        self.assertEqual(rv["classificados"] + rv["nao_identificados"], rv["total_vertical"])
        self.assertEqual(sum(resumo["niveis_verticais_af"].values()), rv["total_vertical"])

        # TEC. ADM e STF devem permanecer pendentes de confirmação normativa
        self.assertIn("PENDENTE:TEC. ADM", resumo["por_grupo"])
        self.assertIn("PENDENTE:STF", resumo["por_grupo"])
        self.assertGreaterEqual(resumo["por_grupo"]["PENDENTE:TEC. ADM"], 1580)
        self.assertGreaterEqual(resumo["por_grupo"]["PENDENTE:STF"], 11)

        # Divergências de classificação registradas sem resolução automática
        with contextlib.closing(sqlite3.connect(f"file:{DB_TESTE}?mode=ro", uri=True)) as con:
            n_div = con.execute(
                "SELECT COUNT(*) FROM conflito WHERE origem = ? AND campo = 'classificacao_eixo_modalidade' AND estado = 'ABERTO'",
                (ORIGEM_CONSOLIDACAO,),
            ).fetchone()[0]
            self.assertEqual(n_div, 24)

    def test_04_adaptador_painel_2910_e_privacidade(self):
        with Banco(DB_TESTE) as banco:
            # 1. Perfil Público: zero dados individuais
            p_pub = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.PUBLICO)
            proj_pub = adaptador.projetar_para_dashboard_2910(p_pub, [], [])
            self.assertEqual(len(proj_pub["rows"]), 0)
            self.assertEqual(len(proj_pub["events"]), 0)
            self.assertFalse(proj_pub["backend"]["autenticado"])

            outras_pub = indicadores.outras_publicacoes(banco, indicadores.PUBLICO)
            for item in outras_pub:
                self.assertNotIn("trecho", item)
                self.assertFalse(
                    re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", str(item.get("titulo") or "")),
                    "CPF detectado em título público de outra_publicacao!",
                )

            # 2. Perfil Gerência: consulta completa no contrato do painel 29/10
            p_ger = indicadores.painel(banco, {"escopo": "pendente"}, indicadores.GERENCIA_PERFIL)
            outras_ger = indicadores.outras_publicacoes(banco, indicadores.GERENCIA_PERFIL)
            rej_consulta = banco.con.execute(
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
                rej_linhas.append(lr)

            proj_ger = adaptador.projetar_para_dashboard_2910(p_ger, outras_ger, rej_linhas)
            self.assertTrue(proj_ger["backend"]["autenticado"])
            self.assertEqual(len(proj_ger["events"]), 22)
            self.assertEqual(sum(1 for r in proj_ger["rows"] if r["validation"] == "rejeitado"), 1)
            self.assertEqual(sum(1 for r in proj_ger["rows"] if r.get("preliminaryReview")), 101)

            # Abono de Permanência como modalidade de Tempo de Serviço (preserva TS-01..TS-07, SEM TS-08)
            cat_codes = [c[0] for c in proj_ger["categories"]]
            self.assertEqual(cat_codes[:7], [f"TS-0{i}" for i in range(1, 8)])
            self.assertNotIn("TS-08", cat_codes)
            self.assertIn("ABONO_PERMANENCIA", cat_codes)
            abono_rows = [r for r in proj_ger["rows"] if r["axis"] == "tempo" and r["category"] == "ABONO_PERMANENCIA"]
            self.assertEqual(len(abono_rows), 106)  # 80 individuais + 26 atos extras (8 sobrepostos eliminados)
            self.assertEqual(sum(1 for r in abono_rows if r["merit"] == "deferido"), 94)
            self.assertEqual(sum(1 for r in abono_rows if r["merit"] == "indeferido"), 12)
            tempo_pend = [r for r in proj_ger["rows"] if r["validation"] == "pendente" and r["axis"] == "tempo"]
            outros_pend = [r for r in proj_ger["rows"] if r["validation"] == "pendente" and r["axis"] == "outros"]
            self.assertEqual(len(tempo_pend), 394)  # 288 TS-01..TS-07 + 106 Abono de Permanência
            self.assertEqual(len(outros_pend), 33)  # 147 - 80 - 34 = 33 não-Abono

            # Consultas Por resenha e Por processo preservadas
            self.assertTrue(all(r.get("resenha_id") for r in proj_ger["rows"]))
            self.assertGreater(len({r["process"] for r in proj_ger["rows"] if r.get("process")}), 3300)
            grupos_chaves = [g[0] for g in proj_ger["groups"]]
            self.assertIn("PENDENTE:TEC. ADM", grupos_chaves)
            self.assertIn("PENDENTE:STF", grupos_chaves)


if __name__ == "__main__":
    unittest.main()
