"""Testes de homologação da Missão Final (Seções 5, 6, 7, 8, 10 e 11).

Comprova de forma reproduzível:
- Agendamento diário, inclusive sábados e domingos (12:00 America/Sao_Paulo);
- Feriado configurado é apenas informativo e nunca suspende a coleta do DOE;
- Recuperação de lacunas (recuo de 3 dias) e modo manual excepcional;
- Desacoplamento de repositórios obsoletos (`gediv-painel-redesign-preview`) em `rodar_diario.sh`;
- Proteção contra exclusão automática do banco reconciliado em `scripts/reconciliar_acervo_gediv.py`;
- Preservação de revisões humanas (`CONFERIDO`) após reimportação/releitura;
- Backup consistente SQLite (`src.backup` + `PRAGMA integrity_check` + SHA-256) e restauração íntegra.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import contextlib

from observatorio.nucleo.banco import Banco
from observatorio.operacao import agendamento
from observatorio.painel import adaptador, indicadores
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
    def test_01_agendamento_diario_inclusive_fim_de_semana(self) -> None:
        tz = timezone(timedelta(hours=-3))
        # 2026-11-23 (segunda-feira) a 2026-11-29 (domingo): todos os dias executam
        for dia in range(23, 30):
            dt = datetime(2026, 11, dia, 9, 0, tzinfo=tz)
            dec = agendamento.avaliar_execucao(dt)
            self.assertTrue(dec.executar, f"{dt.date()} deveria executar a coleta diária")
            self.assertEqual(dec.categoria, "DIARIA")
            self.assertEqual(dec.inicio_janela, dt.date() - timedelta(days=3))

            # Modo manual excepcional (separado do agendamento) é permitido quando acionado pelo operador
            dec_manual = agendamento.avaliar_execucao(dt, modo_manual=True)
            self.assertTrue(dec_manual.executar)
            self.assertEqual(dec_manual.categoria, "MANUAL_EXCEPCIONAL")

    def test_02_feriado_configurado_nao_suspende_coleta(self) -> None:
        tz = timezone(timedelta(hours=-3))
        dt_sexta = datetime(2026, 12, 25, 9, 0, tzinfo=tz)  # Sexta-feira
        # Sem arquivo de feriados validado, não presume feriado
        dec_sem_arq = agendamento.avaliar_execucao(dt_sexta, feriados_arq=None)
        self.assertTrue(dec_sem_arq.executar)
        self.assertIsNone(dec_sem_arq.feriado)

        with tempfile.TemporaryDirectory() as tmp:
            arq = pathlib.Path(tmp) / "feriados_oficiais.txt"
            arq.write_text("# Feriados validados\n2026-12-25  Natal (Decreto Estadual)\n", encoding="utf-8")
            dec_com_arq = agendamento.avaliar_execucao(dt_sexta, feriados_arq=arq)
            self.assertTrue(dec_com_arq.executar)
            self.assertEqual(dec_com_arq.categoria, "DIARIA")
            self.assertEqual(dec_com_arq.feriado, "Natal (Decreto Estadual)")
            self.assertIn("Natal", dec_com_arq.motivo)

    def test_03_timer_service_e_script_desacoplados_de_repo_obsoleto(self) -> None:
        timer_txt = (DEPLOY_DIR / "gediv-diario.timer").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^OnCalendar=(.+)$", timer_txt, re.MULTILINE), [
            "*-*-* 12:00:00 America/Sao_Paulo",
        ])
        self.assertNotIn("Mon..Fri", timer_txt)

        sh_txt = (DEPLOY_DIR / "rodar_diario.sh").read_text(encoding="utf-8")
        self.assertIn("flock -n 9", sh_txt)
        self.assertNotIn('DIA_SEMANA" -ge 6', sh_txt)
        self.assertIn("FERIADOS_ARQ", sh_txt)
        self.assertIn("America/Sao_Paulo", sh_txt)
        # Nenhuma linha executável pode apontar para o repositório obsoleto nem reconstruir o painel-publico antigo
        linhas_exec = [l for l in sh_txt.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertFalse(
            any("gediv-painel-redesign-preview" in l for l in linhas_exec),
            "rodar_diario.sh ainda possui referência executável a gediv-painel-redesign-preview!",
        )
        self.assertFalse(
            any("preparar_painel_publico.py" in l for l in linhas_exec),
            "rodar_diario.sh ainda executa scripts/preparar_painel_publico.py para construir o frontend antigo painel-publico!",
        )
        self.assertNotIn("SAIDA_PUBLICA", sh_txt, "Variável morta SAIDA_PUBLICA deve ter sido removida de rodar_diario.sh!")
        self.assertNotIn("object.__new__", sh_txt, "Passo [5/6] não deve instanciar Banco via object.__new__!")
        self.assertIn('export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"', sh_txt)
        self.assertIn("with Banco.somente_leitura(db) as banco_ro:", sh_txt)
        self.assertIn("cobertura_resumo.json", sh_txt)
        self.assertEqual(sh_txt.count('as_uri() + "?mode=ro"'), 2, "Passo [3/6] deve abrir os SQLites exclusivamente em ?mode=ro!")
        self.assertNotIn("with Banco(", sh_txt, "Passo [5/6] não deve abrir Banco() em modo leitura-escrita após o backup!")
        self.assertIn("indicadores.resumo_cobertura_edicoes(banco_ro)", sh_txt)
        self.assertIn("proteger_publico=True", sh_txt)
        idx_validacoes = sh_txt.index('if "TS-08" in cats or "ABONO_PERMANENCIA" not in cats:')
        idx_tmp_write = sh_txt.index('tmp.write_text(')
        idx_tmp_replace = sh_txt.index('tmp.replace(out)')
        self.assertLess(idx_validacoes, idx_tmp_write)
        self.assertLess(idx_tmp_write, idx_tmp_replace)
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

    def test_05_banco_somente_leitura_e_passo_5_rodar_diario(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_dir = pathlib.Path(tmp)
            ausente = tmp_dir / "nao_existe.sqlite3"
            with self.assertRaises(FileNotFoundError):
                Banco.somente_leitura(ausente)
            self.assertFalse(ausente.exists())

            db_path = tmp_dir / "observatorio.sqlite3"
            with Banco(db_path) as banco:
                adaptador.importar_snapshot_reconciliado(banco, _bootstrap_sintetico())
            sha_antes = hashlib.sha256(db_path.read_bytes()).hexdigest()

            with Banco.somente_leitura(db_path) as banco_ro:
                with self.assertRaises(sqlite3.OperationalError):
                    banco_ro.con.execute("CREATE TABLE tentativa_escrita (x INTEGER)")
                with self.assertRaises(sqlite3.OperationalError):
                    banco_ro.con.execute("DELETE FROM decisao")
                p_pub = indicadores.painel(banco_ro, {"escopo": "pendente"}, indicadores.PUBLICO)
                self.assertEqual(p_pub["meta"]["escopo"], "conferido")
                self.assertEqual(p_pub["linhas"], [])
            with self.assertRaises(sqlite3.ProgrammingError):
                banco_ro.con.execute("SELECT 1")
            self.assertEqual(hashlib.sha256(db_path.read_bytes()).hexdigest(), sha_antes)

            sh_txt = (DEPLOY_DIR / "rodar_diario.sh").read_text(encoding="utf-8")
            match = re.search(
                r'echo "\[5/6\][^\n]*\nCOBERTURA_RESUMO="\$DADOS_DIR/cobertura_resumo\.json"\n"\$PYTHON_BIN" - "\$DADOS_DIR/observatorio\.sqlite3" "\$COBERTURA_RESUMO" <<\'PY\'\n(.*?)\nPY',
                sh_txt,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match, "Bloco Python do passo [5/6] não encontrado em rodar_diario.sh")
            snippet = match.group(1)

            env = {**os.environ, "PYTHONSAFEPATH": "1", "PYTHONPATH": str(REPO_DIR)}
            out_json = tmp_dir / "cobertura_resumo.json"
            res_ok = subprocess.run(
                [sys.executable, "-c", snippet, str(db_path), str(out_json)],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_ok.returncode, 0, res_ok.stderr)
            self.assertTrue(out_json.is_file())
            self.assertFalse(out_json.with_name(out_json.name + ".tmp").exists())
            dados_resumo = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(set(dados_resumo.keys()), {"ausencia_tecnica_edicoes", "inconclusivas"})
            self.assertEqual(hashlib.sha256(db_path.read_bytes()).hexdigest(), sha_antes)

            res_ausente = subprocess.run(
                [sys.executable, "-c", snippet, str(ausente), str(tmp_dir / "ausente.json")],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(res_ausente.returncode, 0)
            self.assertFalse((tmp_dir / "ausente.json").exists())

            db_corrompido = tmp_dir / "corrompido.sqlite3"
            db_corrompido.write_bytes(b"nao e sqlite valido")
            res_corrompido = subprocess.run(
                [sys.executable, "-c", snippet, str(db_corrompido), str(tmp_dir / "corrompido.json")],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(res_corrompido.returncode, 0)
            self.assertFalse((tmp_dir / "corrompido.json").exists())

    def test_06_cobertura_abono_permanencia_e_units_linux(self) -> None:
        from observatorio.gerencias.gediv import catalogo as C

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = pathlib.Path(tmp) / "cobertura_abono.sqlite3"
            shas = [f"{i:064x}" for i in range(1, 7)]
            with Banco(db_path) as banco:
                with banco.con:
                    for i, sha in enumerate(shas, start=1):
                        banco.con.execute(
                            "INSERT INTO arquivo (sha256, tamanho, caminho, guardado_em) VALUES (?,?,?,?)",
                            (sha, 1024, f"acervo/{sha}.pdf", "2026-04-10T09:00:00Z"),
                        )
                        situacao = "ERRO" if i == 6 else "LIDA"
                        banco.con.execute(
                            "INSERT INTO leitura (sha256, situacao, versao_leitor, paginas, paginas_sem_texto, numero_edicao, data_edicao, concluida_em) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (sha, situacao, "1.0", 8, 0, f"20{i}", f"2026-04-0{i}", "2026-04-10T09:00:00Z"),
                        )
                    # Edição 1: PROGRESSAO; Edição 2: TEMPO_SERVICO
                    banco.con.execute(
                        "INSERT INTO ato (id, gerencia, sha256, tipo, numero, pagina, pagina_final, data_publicacao, vinculo, natureza, eixo, modalidade, grupo, resultado, texto, versao_regras) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("a" * 20, "GEDIV", shas[0], "RESENHA", "001/2026", 1, 1, "2026-04-01", "EXPRESSO", "ORIGINAL", "PROGRESSAO", "VERTICAL", "MAG", "DEFERIDO", "Resenha", C.VERSAO_REGRAS),
                    )
                    banco.con.execute(
                        "INSERT INTO ato (id, gerencia, sha256, tipo, numero, pagina, pagina_final, data_publicacao, vinculo, natureza, eixo, subcategoria, resultado, texto, versao_regras) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("b" * 20, "GEDIV", shas[1], "RESENHA", "002/2026", 2, 2, "2026-04-02", "EXPRESSO", "ORIGINAL", "TEMPO_SERVICO", "TS-01", "DEFERIDO", "Resenha", C.VERSAO_REGRAS),
                    )
                    # Edição 3: SOMENTE Abono de Permanência em outra_publicacao -> NÃO deve contar como ausência técnica
                    banco.con.execute(
                        "INSERT INTO outra_publicacao (id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        ("c" * 20, "GEDIV", shas[2], "PORTARIA", 5, "2026-04-03", "Portaria 55/2026 - Abono de Permanência", "EXPRESSO", "Concede Abono de Permanência."),
                    )
                    # Edição 4: SOMENTE distrator "Abono Natalino" -> DEVE contar como ausência técnica
                    banco.con.execute(
                        "INSERT INTO outra_publicacao (id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        ("d" * 20, "GEDIV", shas[3], "PORTARIA", 6, "2026-04-04", "Portaria 56/2026 - Abono Natalino", "EXPRESSO", "Dispõe sobre Abono Natalino."),
                    )
                    # Edição 5: leitura válida sem ato e sem Abono -> ausência técnica

            sha_antes = hashlib.sha256(db_path.read_bytes()).hexdigest()
            with Banco.somente_leitura(db_path) as banco_ro:
                res = indicadores.resumo_cobertura_edicoes(banco_ro)
            self.assertEqual(res, {"ausencia_tecnica_edicoes": 2, "inconclusivas": 1})
            self.assertEqual(hashlib.sha256(db_path.read_bytes()).hexdigest(), sha_antes)

        # Valida scripts LF e units systemd preparados para Linux
        for script_nome in ("rodar_diario.sh", "recuperar_edicoes_manual.sh", "verificar_ambiente_linux.sh"):
            arq = DEPLOY_DIR / script_nome
            self.assertTrue(arq.is_file(), f"Script ausente: {script_nome}")
            self.assertEqual(arq.read_bytes().count(b"\r\n"), 0, f"{script_nome} deve usar apenas LF")
        ver_linux = (DEPLOY_DIR / "verificar_ambiente_linux.sh").read_text(encoding="utf-8")
        self.assertIn("systemd-analyze verify", ver_linux)
        self.assertIn("PYTHONSAFEPATH=1", ver_linux)


if __name__ == "__main__":
    unittest.main()
