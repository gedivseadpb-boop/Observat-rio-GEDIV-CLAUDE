"""Testes de sincronização do gerador sintético canônico entre base local (SQLite + CLI) e pacote estático."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from observatorio.nucleo.banco import Banco
from observatorio.operacao import __main__ as cli_operacao
from observatorio.operacao import previa_sintetica, saida
from observatorio.painel import indicadores
from scripts import preparar_previa_github_pages as prep


class TestSincronizacaoSinteticoCanonico(unittest.TestCase):
    def test_01_paridade_exata_entre_banco_local_e_pacote_estatico(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-sync-sint-") as tmp:
            pasta_local = Path(tmp) / "dados-local"
            pasta_pages = Path(tmp) / "pages-public"

            # 1. Gera base SQLite local sintética pela fonte única canônica (sem snapshot ainda)
            res_local = previa_sintetica.criar_base_local_sintetica(pasta_local, publicar_snapshot=False)
            self.assertEqual(res_local["edicoes"], 6)

            # 2. Publica snapshot público usando a CLI oficial `publicar-snapshot-publico`
            buf = io.StringIO()
            with redirect_stdout(buf):
                cod = cli_operacao.main(["publicar-snapshot-publico", "--dados", str(pasta_local)])
            self.assertEqual(cod, saida.SUCESSO)
            cli_out = json.loads(buf.getvalue())
            self.assertEqual(cli_out["resultado"], "OK")

            # 3. Gera pacote estático do GitHub Pages a partir da mesma fonte canônica
            prep.construir_pacote(pasta_pages)
            dados_pages = json.loads((pasta_pages / "dados-sinteticos-publicos.json").read_text(encoding="utf-8"))

            # 4. Compara agregações gerenciais (banco local vs pacote estático)
            banco = Banco(pasta_local / "observatorio.sqlite3")
            try:
                p_ger = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.GERENCIA_PERFIL)
            finally:
                banco.fechar()

            self.assertEqual(p_ger["indicadores"], dados_pages["backend"]["indicadores"])
            res_local_nv = p_ger["series"]["resumo_nivel_vertical"]
            res_pages_nv = dados_pages["backend"]["series"]["resumo_nivel_vertical"]
            self.assertEqual(res_local_nv, res_pages_nv)

            # Distribuição exata de referência dos 42 registros verticais
            self.assertEqual(res_local_nv["total_vertical"], 42)
            self.assertEqual(res_local_nv["classificados"], 29)
            self.assertEqual(res_local_nv["indeferidos"], 7)
            self.assertEqual(res_local_nv["nao_determinados"], 2)
            self.assertEqual(res_local_nv["inconsistentes"], 2)
            self.assertEqual(res_local_nv["nao_aplica"], 2)
            self.assertEqual(res_local_nv["nao_identificados"], 13)
            self.assertEqual(
                res_local_nv["classificados"]
                + res_local_nv["indeferidos"]
                + res_local_nv["nao_determinados"]
                + res_local_nv["inconsistentes"]
                + res_local_nv["nao_aplica"],
                42,
            )

            # 5. Verifica preservação rigorosa da política de supressão (< 5) no snapshot público local
            snap_pub = indicadores.carregar_snapshot_publico(pasta_local / indicadores.ARQUIVO_SNAPSHOT_PUBLICO)
            self.assertIsNotNone(snap_pub)
            indicadores.validar_snapshot_publico(snap_pub)

            res_pub_nv = snap_pub["painel"]["series"]["resumo_nivel_vertical"]
            self.assertEqual(res_pub_nv["total_vertical"], 40)       # 42 -> faixa de 5
            self.assertEqual(res_pub_nv["classificados"], 25)        # 29 -> faixa de 5
            self.assertEqual(res_pub_nv["nao_identificados"], 10)    # 13 -> faixa de 5
            self.assertEqual(res_pub_nv["indeferidos"], 5)           # 7 -> faixa de 5
            # Categorias com contagem 2 (< 5) devem ser suprimidas (None)
            self.assertIsNone(res_pub_nv["nao_determinados"])
            self.assertIsNone(res_pub_nv["inconsistentes"])
            self.assertIsNone(res_pub_nv["nao_aplica"])

            sit_pub = {x["codigo"]: x for x in snap_pub["painel"]["series"]["por_situacao_nivel_vertical"]}
            self.assertEqual(sit_pub["INDEFERIDO"]["total"], 5)
            for cod_peq in ("E", "F", "NAO_DETERMINADO", "INCONSISTENTE", "NAO_APLICA"):
                self.assertIsNone(sit_pub[cod_peq]["total"], f"{cod_peq} (< 5) deveria estar suprimido")
                self.assertEqual(sit_pub[cod_peq]["transicoes"], [])

    def test_02_recusa_sobrescrever_banco_nao_sintetico(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-sync-guard-") as tmp:
            pasta = Path(tmp) / "dados-reais-simulados"
            pasta.mkdir()
            banco = Banco(pasta / "observatorio.sqlite3")
            try:
                banco.registrar_descoberta("auniao", "https://auniao.pb.gov.br/doe/edicao-real.pdf", "2026-10-01", "normal", 1, "Real")
            finally:
                banco.fechar()

            with self.assertRaises(ValueError):
                previa_sintetica.criar_base_local_sintetica(pasta, publicar_snapshot=True)


if __name__ == "__main__":
    unittest.main()
