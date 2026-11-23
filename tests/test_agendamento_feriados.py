"""A coleta do DOE roda todos os dias (inclusive fins de semana e feriados) e datas ao operador seguem DD/MM/YYYY."""

from __future__ import annotations

import pathlib
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from observatorio.operacao import agendamento

TZ = timezone(timedelta(hours=-3))
DEPLOY_DIR = pathlib.Path(__file__).resolve().parents[1] / "deploy_autonomo"
ISO_DATA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _arquivo_feriados(tmp: str, conteudo: str) -> pathlib.Path:
    arq = pathlib.Path(tmp) / "feriados_oficiais.txt"
    arq.write_text(conteudo, encoding="utf-8")
    return arq


class TestAgendamentoDiario(unittest.TestCase):
    def test_todos_os_dias_do_ano_executam(self) -> None:
        d = date(2026, 1, 1)
        while d.year == 2026:
            for hora in (12,):
                dec = agendamento.avaliar_execucao(datetime(d.year, d.month, d.day, hora, 0, tzinfo=TZ))
                self.assertTrue(dec.executar, f"{d} às {hora}h deveria executar a coleta")
                self.assertEqual(dec.categoria, "DIARIA")
                self.assertEqual(dec.inicio_janela, d - timedelta(days=3))
                self.assertEqual(dec.fim_janela, d)
            d += timedelta(days=1)

    def test_feriado_em_fim_de_semana_executa(self) -> None:
        # 15/11/2026 (Proclamação da República) é domingo.
        with tempfile.TemporaryDirectory() as tmp:
            arq = _arquivo_feriados(tmp, "15/11/2026  Proclamação da República\n")
            dec = agendamento.avaliar_execucao(datetime(2026, 11, 15, 9, 0, tzinfo=TZ), feriados_arq=arq)
        self.assertTrue(dec.executar)
        self.assertEqual(dec.feriado, "Proclamação da República")
        self.assertIn("domingo", dec.motivo)
        self.assertIn("executada normalmente", dec.motivo)

    def test_feriado_em_dia_util_executa(self) -> None:
        # 20/11/2026 (Consciência Negra) é sexta-feira.
        with tempfile.TemporaryDirectory() as tmp:
            arq = _arquivo_feriados(tmp, "20/11/2026  Dia da Consciência Negra\n")
            dec = agendamento.avaliar_execucao(datetime(2026, 11, 20, 9, 0, tzinfo=TZ), feriados_arq=arq)
        self.assertTrue(dec.executar)
        self.assertEqual(dec.feriado, "Dia da Consciência Negra")

    def test_carregar_feriados_aceita_ddmmyyyy_e_iso(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arq = _arquivo_feriados(tmp, "# comentário\n25/12/2026 Natal\n2026-01-01 Confraternização\ninválida X\n")
            feriados = agendamento.carregar_feriados(arq)
        self.assertEqual(feriados, {date(2026, 12, 25): "Natal", date(2026, 1, 1): "Confraternização"})

    def test_motivos_exibem_datas_em_ddmmyyyy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arq = _arquivo_feriados(tmp, "25/12/2026 Natal\n")
            casos = [
                agendamento.avaliar_execucao(datetime(2026, 11, 24, 9, 0, tzinfo=TZ)),
                agendamento.avaliar_execucao(datetime(2026, 11, 28, 9, 0, tzinfo=TZ)),
                agendamento.avaliar_execucao(datetime(2026, 12, 25, 9, 0, tzinfo=TZ), feriados_arq=arq),
            ]
        self.assertIn("21/11/2026 a 24/11/2026", casos[0].motivo)
        self.assertIn("sábado, 28/11/2026", casos[1].motivo)
        self.assertIn("25/12/2026", casos[2].motivo)
        for dec in casos:
            self.assertIsNone(ISO_DATA.search(dec.motivo), dec.motivo)

    def test_rodar_diario_sem_bloqueio_de_calendario(self) -> None:
        sh = (DEPLOY_DIR / "rodar_diario.sh").read_text(encoding="utf-8")
        bloco = sh[sh.index("# 1. Calendário"):sh.index("# 2. Janela de recuperação")]
        self.assertNotIn("exit", bloco)
        self.assertIn("[INFO]", bloco)
        self.assertIn('DATA_HOJE_BR="$(date +%d/%m/%Y)"', sh)
        self.assertIn("$INICIO_JANELA_BR até $DATA_HOJE_BR", sh)
        self.assertIn("DIAS_RECUO=3", sh)

    def test_timer_dispara_todos_os_dias(self) -> None:
        timer = (DEPLOY_DIR / "gediv-diario.timer").read_text(encoding="utf-8")
        calendarios = re.findall(r"^OnCalendar=(.+)$", timer, re.MULTILINE)
        self.assertEqual(
            calendarios,
            ["*-*-* 12:00:00 America/Sao_Paulo"],
        )
        self.assertEqual(agendamento.JANELAS_HORARIO, ("12:00",))
        self.assertRegex(timer, r"(?m)^Persistent=false$")


if __name__ == "__main__":
    unittest.main()
