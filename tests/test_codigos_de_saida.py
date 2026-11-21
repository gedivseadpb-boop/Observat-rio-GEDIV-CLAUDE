"""Códigos de saída dos comandos de operação (auditorias de 14/11/2026: `executar` saía com 0 mesmo com leitura em ERRO).

Um agendador (ex.: GitHub Actions) precisa distinguir: 0 sucesso integral, 1 falha (intervenção), 3 concluído com
pendências (retomável), 4 nada executado (faltam insumos). Diários SINTÉTICOS; pessoas fictícias.
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.gerencias.gediv import processo
from observatorio.leitura import leitor
from observatorio.operacao import fluxo, ouro, saida
from observatorio.operacao.__main__ import main

TEM_PDF = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))
RAIZ = Path(__file__).resolve().parents[1]


def rodar(*argumentos) -> tuple[int, dict]:
    texto = io.StringIO()
    with contextlib.redirect_stdout(texto):
        codigo = main(list(argumentos))
    return codigo, json.loads(texto.getvalue())


class TesteCombinacao(unittest.TestCase):
    def test_pior_resultado_prevalece(self):
        self.assertEqual(saida.pior(saida.SUCESSO, saida.CONCLUIDO_COM_PENDENCIAS), saida.CONCLUIDO_COM_PENDENCIAS)
        self.assertEqual(saida.pior(saida.CONCLUIDO_COM_PENDENCIAS, saida.FALHA, saida.NAO_EXECUTADO), saida.FALHA)
        self.assertEqual(saida.pior(), saida.SUCESSO)

    def test_avaliacao_sem_pdf(self):
        ok = {"LIDA": 1, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0}
        self.assertEqual(fluxo.avaliar([], ok, {"com_erro": 0}, 0, 0)["codigo"], saida.SUCESSO)
        self.assertEqual(fluxo.avaliar([], {**ok, "ERRO": 1}, {"com_erro": 0}, 1, 0)["codigo"], saida.FALHA)
        self.assertEqual(fluxo.avaliar([], ok, {"com_erro": 0}, 2, 0)["codigo"], saida.FALHA)               # erro anterior não refeito
        self.assertEqual(fluxo.avaliar([], ok, {"com_erro": 1}, 0, 1)["codigo"], saida.FALHA)
        self.assertEqual(fluxo.avaliar([{"aceito": False}], ok, {"com_erro": 0}, 0, 0)["codigo"], saida.FALHA)
        self.assertEqual(fluxo.avaliar([], {**ok, "LIDA_COM_PENDENCIAS": 1}, {"com_erro": 0}, 0, 0)["codigo"], saida.CONCLUIDO_COM_PENDENCIAS)
        self.assertEqual(fluxo.avaliar([], {**ok, "na_fila": 2}, {"com_erro": 0}, 0, 0)["codigo"], saida.CONCLUIDO_COM_PENDENCIAS)


class TesteValidacaoComDivergencia(unittest.TestCase):
    def test_conjunto_ouro(self):
        edicoes = lambda *s: {"edicoes": [{"situacao": x} for x in s]}
        self.assertEqual(ouro.codigo_de_saida(edicoes("CONFERE", "CONFERE")), saida.SUCESSO)
        self.assertEqual(ouro.codigo_de_saida(edicoes("CONFERE", "DIVERGE")), saida.FALHA)
        self.assertEqual(ouro.codigo_de_saida(edicoes("CONFERE", "PDF_AUSENTE")), saida.FALHA)        # parcial não é sucesso
        self.assertEqual(ouro.codigo_de_saida(edicoes("PDF_AUSENTE")), saida.NAO_EXECUTADO)
        self.assertEqual(ouro.codigo_de_saida(edicoes()), saida.NAO_EXECUTADO)                         # vazio não é sucesso

    def test_ouro_aceita_leitura_com_pendencias_e_recusa_falha(self):
        doc = {"data": "2026-11-07", "url": "https://exemplo.invalid/x.pdf"}
        with tempfile.TemporaryDirectory() as pasta:
            for codigo, esperado in ((saida.CONCLUIDO_COM_PENDENCIAS, None), (saida.FALHA, "ERRO_DE_EXECUCAO")):
                with self.subTest(codigo=codigo):
                    def falso(comando, **k):
                        Path(comando[comando.index("--saida") + 1]).write_text('{"resultado": "FLUXO_EXECUTADO"}', encoding="utf-8")
                        return subprocess.CompletedProcess(comando, codigo, "", "Traceback ... PESSOA FICTICIA")
                    with mock.patch.object(ouro.subprocess, "run", falso):
                        r = ouro._executar_edicao(doc, Path(pasta) / "x.pdf")
                    self.assertEqual(r.get("resultado"), esperado or "FLUXO_EXECUTADO")
                    self.assertNotIn("PESSOA FICTICIA", json.dumps(r))                 # saída de erro não vai ao relatório


class TesteArquivosNecessarios(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_origem_inexistente_ou_sem_pdf(self):
        codigo, r = rodar("executar", str(self.pasta / "nao-existe"), "--dados", str(self.pasta / "dados"))
        self.assertEqual((codigo, r["resultado"]["situacao"]), (saida.NAO_EXECUTADO, "NAO_EXECUTADO"))
        (self.pasta / "vazia").mkdir()
        self.assertEqual(rodar("executar", str(self.pasta / "vazia"), "--dados", str(self.pasta / "dados"))[0], saida.NAO_EXECUTADO)
        self.assertFalse((self.pasta / "dados").exists())                         # nada foi criado

    def test_validar_real_sem_o_arquivo(self):
        codigo, r = rodar("validar-real", str(self.pasta / "nao-existe.pdf"), "--data", "2026-11-07", "--dados", str(self.pasta / "d"))
        self.assertEqual((codigo, r["resultado"]), (saida.NAO_EXECUTADO, "ARQUIVO_AUSENTE"))

    def test_codigo_visto_pelo_agendador_no_processo_real(self):
        processo_real = subprocess.run([sys.executable, "-m", "observatorio.operacao", "executar", str(self.pasta / "nao-existe"),
                                        "--dados", str(self.pasta / "dados")], capture_output=True, cwd=RAIZ)
        self.assertEqual(processo_real.returncode, saida.NAO_EXECUTADO)


@unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab")
class TesteFluxo(unittest.TestCase):
    def setUp(self):
        from tests.test_leitura import pdf_duas_colunas
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.dados = str(self.pasta / "dados")
        self.pdf_limpo = self.pasta / "limpo.pdf"
        self.pdf_limpo.write_bytes(pdf_duas_colunas(paginas_extras=False))
        self.pdf_com_pendencia = self.pasta / "pendente.pdf"
        self.pdf_com_pendencia.write_bytes(pdf_duas_colunas())               # página gráfica sem texto: pendência

    def executar(self, origem=None, *extras):
        return rodar("executar", *([str(origem)] if origem else []), "--data", "2026-05-08", "--dados", self.dados, *extras)

    def test_processamento_integral_bem_sucedido(self):
        codigo, r = self.executar(self.pdf_limpo)
        self.assertEqual((codigo, r["resultado"]["situacao"], r["resultado"]["motivos"]), (saida.SUCESSO, "SUCESSO", []))
        self.assertEqual(r["leitura"]["LIDA"], 1)

    def test_leitura_com_pendencias_nao_e_sucesso_integral_nem_falha(self):
        codigo, r = self.executar(self.pdf_com_pendencia)
        self.assertEqual(codigo, saida.CONCLUIDO_COM_PENDENCIAS)
        self.assertEqual(r["resultado"]["retomada"]["comando"], fluxo.RETOMADA)
        self.assertEqual(r["leitura"]["LIDA_COM_PENDENCIAS"], 1)

    def test_falha_na_leitura_e_retomada(self):
        with mock.patch.object(leitor, "ler_arquivo", side_effect=RuntimeError("falha simulada")):
            codigo, r = self.executar(self.pdf_limpo)
        self.assertEqual((codigo, r["leitura"]["ERRO"]), (saida.FALHA, 1))
        # Nova execução sem retomar: o erro anterior continua visível (antes: saída 0, "nada a fazer").
        codigo, r = self.executar()
        self.assertEqual((codigo, r["leitura"]["ERRO"], r["resultado"]["retomada"]["leituras_com_erro"]), (saida.FALHA, 0, 1))
        self.assertIn("execuções anteriores", " ".join(r["resultado"]["motivos"]))
        # Retomada com o problema resolvido: relê, classifica e termina com sucesso.
        codigo, r = self.executar(None, "--refazer-pendentes")
        self.assertEqual((codigo, r["leitura"]["LIDA"], r["resultado"]["retomada"]["leituras_com_erro"]), (saida.SUCESSO, 1, 0))

    def test_falha_na_classificacao_nao_para_a_fila_e_e_retomada(self):
        from tests.test_leitura import pdf_duas_colunas
        lote = self.pasta / "lote"
        lote.mkdir()
        (lote / "a.pdf").write_bytes(self.pdf_limpo.read_bytes())
        (lote / "b.pdf").write_bytes(pdf_duas_colunas(paginas_extras=False, fonte=7.5))   # segundo arquivo, conteúdo diferente
        original = processo.classificar
        alvo = {}

        def classificar_falhando_no_primeiro(paginas, sha):
            alvo.setdefault("sha", sha)
            if sha == alvo["sha"]:
                raise ValueError("falha simulada na classificação")
            return original(paginas, sha)
        with mock.patch.object(processo, "classificar", classificar_falhando_no_primeiro):
            codigo, r = self.executar(lote)
        self.assertEqual((codigo, r["classificacao"]["com_erro"], r["classificacao"]["arquivos"]), (saida.FALHA, 1, 1))
        self.assertEqual(r["classificacao"]["erros"], [{"sha256": alvo["sha"][:12], "erro": "ValueError"}])
        self.assertEqual(r["situacao"]["na_fila"], 1)                         # continua na fila
        codigo, r = self.executar()                                           # retomada automática
        self.assertEqual((codigo, r["classificacao"]["arquivos"], r["situacao"]["na_fila"]), (saida.SUCESSO, 1, 0))

    def test_importacao_recusada(self):
        ruim = self.pasta / "corrompido.pdf"
        ruim.write_bytes(b"%PDF-1.4 cortado no meio")
        codigo, r = self.executar(ruim)
        self.assertEqual((codigo, r["importacao"][0]["aceito"]), (saida.FALHA, False))

    def test_validar_real_reflete_o_fluxo(self):
        codigo, r = rodar("validar-real", str(self.pdf_limpo), "--data", "2026-05-08", "--dados", str(self.pasta / "v1"))
        self.assertEqual((codigo, r["codigo_de_saida"], r["resultado"]), (saida.SUCESSO, saida.SUCESSO, "FLUXO_EXECUTADO"))
        ruim = self.pasta / "corrompido.pdf"
        ruim.write_bytes(b"%PDF-1.4 cortado no meio")
        codigo, r = rodar("validar-real", str(ruim), "--data", "2026-05-08", "--dados", str(self.pasta / "v2"))
        self.assertEqual((codigo, r["resultado"]), (saida.FALHA, "ARQUIVO_RECUSADO"))
        with mock.patch.object(leitor, "ler_arquivo", side_effect=RuntimeError("falha simulada")):
            codigo, r = rodar("validar-real", str(self.pdf_limpo), "--data", "2026-05-08", "--dados", str(self.pasta / "v3"))
        self.assertEqual((codigo, r["leitura"]["situacao"]), (saida.FALHA, "ERRO"))


if __name__ == "__main__":
    unittest.main()
