"""Testes da CLI oficial `python -m observatorio.operacao publicar-snapshot-publico`."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from observatorio.operacao import __main__ as cli_operacao
from observatorio.operacao import demonstracao, saida
from observatorio.painel import indicadores


class TestCliPublicarSnapshotPublico(unittest.TestCase):
    def test_01_banco_ausente_falha_fechada_sem_criar_sqlite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-cli-snap-ausente-") as tmp:
            pasta = Path(tmp) / "vazia"
            pasta.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                codigo = cli_operacao.main(["publicar-snapshot-publico", "--dados", str(pasta)])
            self.assertEqual(codigo, saida.NAO_EXECUTADO)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["resultado"], "BANCO_AUSENTE")
            self.assertFalse((pasta / "observatorio.sqlite3").exists())
            self.assertFalse((pasta / indicadores.ARQUIVO_SNAPSHOT_PUBLICO).exists())

    def test_02_publicacao_valida_idempotente_e_sem_pii_no_stdout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-cli-snap-ok-") as tmp:
            pasta = Path(tmp) / "dados-demo"
            demonstracao.criar(str(pasta))

            # 1ª execução: grava no caminho padrão da pasta de dados
            buf1 = io.StringIO()
            with redirect_stdout(buf1):
                cod1 = cli_operacao.main(["publicar-snapshot-publico", "--dados", str(pasta)])
            self.assertEqual(cod1, saida.SUCESSO)
            texto1 = buf1.getvalue()
            res1 = json.loads(texto1)
            self.assertEqual(res1["resultado"], "OK")
            arq_padrao = pasta / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
            self.assertTrue(arq_padrao.is_file())
            snap = indicadores.carregar_snapshot_publico(arq_padrao)
            self.assertIsNotNone(snap)
            self.assertIn("por_situacao_nivel_vertical", snap["painel"]["series"])

            # Garante ausência de PII ou referências individuais no stdout
            self.assertNotIn("SAD-PSE-", texto1)
            self.assertNotIn("pdf_sha256", texto1)
            self.assertNotIn("#page=", texto1)

            # 2ª execução com --saida customizado (idempotente)
            arq_custom = Path(tmp) / "custom" / "snapshot_custom.json"
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                cod2 = cli_operacao.main([
                    "publicar-snapshot-publico",
                    "--dados", str(pasta),
                    "--saida", str(arq_custom),
                ])
            self.assertEqual(cod2, saida.SUCESSO)
            self.assertTrue(arq_custom.is_file())
            self.assertIsNotNone(indicadores.carregar_snapshot_publico(arq_custom))


if __name__ == "__main__":
    unittest.main()
