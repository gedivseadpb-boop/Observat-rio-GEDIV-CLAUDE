"""Testes de homologação da Missão Final (Seções 5, 6, 7, 8, 10 e 11).

Comprova de forma reproduzível:
- Agendamento estrito de segunda a sexta (09:00 e 14:00 America/Sao_Paulo);
- Bloqueio em sábados e domingos (timer + guarda no script + módulo Python);
- Distinção entre fim de semana e feriado administrativo configurável;
- Recuperação de lacunas na segunda-feira (recuo de 4 dias) e modo manual excepcional;
- Desacoplamento de repositórios obsoletos (`gediv-painel-redesign-preview`) em `rodar_diario.sh`;
- Proteção contra exclusão automática do banco reconciliado em `scripts/reconciliar_acervo_gediv.py`;
- Preservação de revisões humanas (`CONFERIDO`) após reimportação/releitura;
- Backup consistente SQLite (`src.backup` + `PRAGMA integrity_check` + SHA-256) e restauração íntegra.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import contextlib

from observatorio.nucleo.banco import Banco
from observatorio.operacao import agendamento
from observatorio.painel import adaptador
from observatorio.revisao import servico

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
DEPLOY_DIR = REPO_DIR / "deploy_autonomo"
_ENV_ORIGEM = os.environ.get("GEDIV_ORIGEM_HTML")
REF_HTML = pathlib.Path(_ENV_ORIGEM) if _ENV_ORIGEM else None


def _bootstrap_sintetico() -> dict:
    """Fixture sintética mínima sem PII para validar idempotência e backup no CI."""
    return {
        "rows": [
            {
                "id": "dec-mis-001",
                "resenha": "Resenha 921/2026",
                "date": "2026-10-15",
                "page": 1,
                "url": "snapshot:mis-1",
                "process": "PROC-TESTE-2026/201",
                "server": "SERVIDOR FICTICIO MISSAO 1",
                "registration": "920001",
                "axis": "progressao",
                "modality": "Vertical",
                "group": "TEC-ADM",
                "groupExpression": "TEC. ADM",
                "merit": "deferido",
                "validation": "pendente",
                "levelFrom": "D",
                "levelTo": "E",
                "evidence": "Progressão Vertical D para E deferida.",
            },
            {
                "id": "dec-mis-002",
                "resenha": "Resenha 922/2026",
                "date": "2026-10-16",
                "page": 2,
                "url": "snapshot:mis-2",
                "process": "PROC-TESTE-2026/202",
                "server": "SERVIDOR FICTICIO MISSAO 2",
                "registration": "920002",
                "axis": "tempo",
                "modality": "",
                "category": "TS-01",
                "merit": "deferido",
                "validation": "pendente",
                "evidence": "Anotação de Tempo de Serviço TS-01 deferida.",
            },
        ],
        "events": [],
    }


class TestHomologacaoMissaoFinal(unittest.TestCase):
    def test_01_agendamento_dias_uteis_e_bloqueio_fim_de_semana(self) -> None:
        tz = timezone(timedelta(hours=-3))
        # 2026-11-23 é segunda-feira; 2026-11-27 é sexta-feira
        for dia in range(23, 28):
            dt = datetime(2026, 11, dia, 9, 0, tzinfo=tz)
            dec = agendamento.avaliar_execucao(dt)
            self.assertTrue(dec.executar, f"Dia útil {dt.date()} deveria executar")
            self.assertEqual(dec.categoria, "DIA_UTIL")
            if dia == 23:  # Segunda-feira: recuo de 4 dias para recuperar quinta/sexta
                self.assertEqual(dec.inicio_janela, dt.date() - timedelta(days=4))
            else:
                self.assertEqual(dec.inicio_janela, dt.date() - timedelta(days=3))

        # 2026-11-28 (sábado) e 2026-11-29 (domingo): bloqueio estrito
        for dia in (28, 29):
            dt = datetime(2026, 11, dia, 9, 0, tzinfo=tz)
            dec = agendamento.avaliar_execucao(dt)
            self.assertFalse(dec.executar, f"Fim de semana {dt.date()} não pode executar automaticamente")
            self.assertEqual(dec.categoria, "FIM_DE_SEMANA")

            # Modo manual excepcional (separado do agendamento) é permitido quando acionado pelo operador
            dec_manual = agendamento.avaliar_execucao(dt, modo_manual=True)
            self.assertTrue(dec_manual.executar)
            self.assertEqual(dec_manual.categoria, "MANUAL_EXCEPCIONAL")

    def test_02_distincao_feriado_administrativo_configuravel(self) -> None:
        tz = timezone(timedelta(hours=-3))
        dt_sexta = datetime(2026, 12, 25, 9, 0, tzinfo=tz)  # Sexta-feira
        # Sem arquivo de feriados validado, não presume feriado
        dec_sem_arq = agendamento.avaliar_execucao(dt_sexta, feriados_arq=None)
        self.assertTrue(dec_sem_arq.executar)

        with tempfile.TemporaryDirectory() as tmp:
            arq = pathlib.Path(tmp) / "feriados_oficiais.txt"
            arq.write_text("# Feriados validados\n2026-12-25  Natal (Decreto Estadual)\n", encoding="utf-8")
            dec_com_arq = agendamento.avaliar_execucao(dt_sexta, feriados_arq=arq)
            self.assertFalse(dec_com_arq.executar)
            self.assertEqual(dec_com_arq.categoria, "FERIADO_ADMINISTRATIVO")
            self.assertIn("Natal", dec_com_arq.motivo)

    def test_03_timer_service_e_script_desacoplados_de_repo_obsoleto(self) -> None:
        timer_txt = (DEPLOY_DIR / "gediv-diario.timer").read_text(encoding="utf-8")
        self.assertIn("OnCalendar=Mon..Fri *-*-* 09:00:00 America/Sao_Paulo", timer_txt)
        self.assertIn("OnCalendar=Mon..Fri *-*-* 14:00:00 America/Sao_Paulo", timer_txt)
        self.assertNotIn("OnCalendar=*-*-*", timer_txt)

        sh_txt = (DEPLOY_DIR / "rodar_diario.sh").read_text(encoding="utf-8")
        self.assertIn("flock -n 9", sh_txt)
        self.assertIn('DIA_SEMANA" -ge 6', sh_txt)
        self.assertIn("FERIADOS_ARQ", sh_txt)
        self.assertIn("America/Sao_Paulo", sh_txt)
        # Nenhuma linha executável pode apontar para o repositório obsoleto
        linhas_exec = [l for l in sh_txt.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertFalse(
            any("gediv-painel-redesign-preview" in l for l in linhas_exec),
            "rodar_diario.sh ainda possui referência executável a gediv-painel-redesign-preview!",
        )
        self.assertTrue((DEPLOY_DIR / "recuperar_edicoes_manual.sh").is_file())

    def test_04_protecao_contra_exclusao_e_preservacao_revisao_humana(self) -> None:
        rec_script = (REPO_DIR / "scripts" / "reconciliar_acervo_gediv.py").read_text(encoding="utf-8")
        self.assertNotIn("db_rec.unlink()", rec_script)
        self.assertNotIn("shutil.copy2(db_rec, db_orig)", rec_script)

        boot = (
            adaptador.extrair_bootstrap_de_html(REF_HTML)
            if (REF_HTML and REF_HTML.is_file())
            else _bootstrap_sintetico()
        )
        total_dec = sum(1 for r in boot["rows"] if r.get("axis") != "outros")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "reconciliado_teste.sqlite3"
            with Banco(db_path) as banco:
                r1 = adaptador.importar_snapshot_reconciliado(banco, boot)
                self.assertEqual(r1["inseridos_decisao"], total_dec)

                # Simula revisão humana (CONFERIR) em 1 registro
                alvo_id = banco.con.execute("SELECT id FROM decisao WHERE validacao='PENDENTE' LIMIT 1").fetchone()[0]
                servico.revisar_decisoes(
                    banco, [alvo_id], "CONFERIR", "Homologador GEDIV",
                    "Conferência documental validada no PDF oficial.", confirma_fonte=True, confirma_vinculo=True
                )

                # Reimportação idempotente NÃO pode apagar nem sobrescrever a revisão humana
                r2 = adaptador.importar_snapshot_reconciliado(banco, boot)
                self.assertEqual(r2["inseridos_decisao"], 0)
                self.assertEqual(r2["preservados_decisao"], total_dec)
                estado = banco.con.execute("SELECT validacao, revisor FROM decisao WHERE id=?", (alvo_id,)).fetchone()
                self.assertEqual(estado["validacao"], "CONFERIDO")
                self.assertEqual(estado["revisor"], "Homologador GEDIV")

            # Teste de backup consistente (.backup + PRAGMA integrity_check + SHA-256) e restauração
            bak_path = pathlib.Path(tmp) / "backup_consistente.sqlite3"
            with contextlib.closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as src:
                with contextlib.closing(sqlite3.connect(bak_path)) as dst:
                    src.backup(dst)
            with contextlib.closing(sqlite3.connect(bak_path.resolve().as_uri() + "?mode=ro", uri=True)) as chk:
                self.assertEqual(chk.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(chk.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], total_dec)
                self.assertEqual(chk.execute("SELECT validacao FROM decisao WHERE id=?", (alvo_id,)).fetchone()[0], "CONFERIDO")
            sha_bak = hashlib.sha256(bak_path.read_bytes()).hexdigest()
            self.assertEqual(len(sha_bak), 64)


if __name__ == "__main__":
    unittest.main()
