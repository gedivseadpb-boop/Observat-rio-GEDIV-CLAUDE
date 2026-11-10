"""Fluxo completo com PDFs SINTÉTICOS: PDF → acervo → leitura por colunas → classificação → revisão → API.
E regressões dos defeitos apontados na auditoria de 10/11/2026 (BUG-009 a BUG-017)."""
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.request
from datetime import date
from pathlib import Path

from observatorio.coleta import coletor, inventario, lotes
from observatorio.coleta.fontes import AUniao
from observatorio.nucleo import banco as B
from observatorio.nucleo import rede
from observatorio.nucleo.acervo import Acervo
from tests.apoio import FonteLocal, Servidor, pdf_sintetico

TEM_BIBLIOTECAS = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab (pip install -r requirements-dev.txt)")
class TesteFluxoCompleto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from observatorio.operacao import demonstracao
        cls._pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.pasta = Path(cls._pasta.name)
        cls.resumo = demonstracao.criar(cls.pasta, conferir=False)

    @classmethod
    def tearDownClass(cls):
        cls._pasta.cleanup()

    def banco(self):
        banco = B.Banco(self.pasta / "observatorio.sqlite3")
        self.addCleanup(banco.fechar)
        return banco

    def test_1_pdfs_sao_lidos_por_colunas_e_classificados(self):
        self.assertEqual(self.resumo["leitura"], {"LIDA": 3, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0})
        c = self.resumo["classificacao"]
        # 13 resenhas + 1 portaria; 56 linhas decisórias; 3 resenhas de outra gerência descartadas.
        self.assertEqual((c["arquivos"], c["atos"], c["decisoes"], c["eventos"], c["descartados"]), (3, 14, 56, 2, 3))
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM pagina WHERE colunas = 2").fetchone()[0], 2)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE validacao <> 'PENDENTE'").fetchone()[0], 0)
        # Nenhuma linha das colunas vizinhas (outra secretaria, outra gerência) foi atribuída à GEDIV.
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE processo LIKE 'SEE-%' OR processo LIKE 'SAD-PSE-2026/8%'").fetchone()[0], 0)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE servidor IS NULL OR matricula IS NULL").fetchone()[0], 0)

    def test_2_cada_resenha_tem_a_quantidade_esperada_de_decisoes(self):
        esperado = {"801/2026": 6, "802/2026": 8, "803/2026": 3, "804/2026": 3, "805/2026": 5, "811/2026": 4, "812/2026": 7,
                    "813/2026": 1, "814/2026": 4, "815/2026": 4, "821/2026": 3, "822/2026": 2}
        achado = dict(self.banco().con.execute(
            "SELECT a.numero, COUNT(d.id) FROM ato a JOIN decisao d ON d.ato_id = a.id WHERE a.natureza = 'ORIGINAL' GROUP BY a.numero"))
        self.assertEqual(achado, esperado)

    def test_3_repetir_o_fluxo_nao_duplica(self):
        from observatorio.operacao import demonstracao, fluxo
        demonstracao.criar(self.pasta, conferir=False)
        repetido = fluxo.executar(self.pasta)
        self.assertEqual((repetido["leitura"]["LIDA"], repetido["classificacao"]["arquivos"]), (0, 0))
        self.assertEqual(sum(repetido["situacao"]["decisoes"].values()), 56)

    def test_4_revisao_e_api_entregam_os_sete_indicadores(self):
        from observatorio.operacao import demonstracao
        from observatorio.web.servidor import criar_servidor
        demonstracao.criar(self.pasta, conferir=True)
        servidor = criar_servidor(self.pasta, "credencial-de-teste-0123456789", porta=0)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        with urllib.request.urlopen(f"http://127.0.0.1:{servidor.server_address[1]}/api/painel", timeout=5) as r:
            dados = json.loads(r.read())
        self.assertEqual(dados["indicadores"], {"processos": 45, "resenhas": 10, "decisoes": 45, "deferidos": 38, "indeferidos": 7,
                                                "refeitos": 1, "sem_efeito": 1})
        self.assertEqual((dados["apoio"]["decisoes_pendentes"], dados["linhas"]), (11, []))
        self.assertEqual({g["grupo"] for g in dados["series"]["por_grupo"]}, {"MAG", "SAUDE", "GAJ", "FAP", "AST", "TEC-ADM"})
        pedido = urllib.request.Request(f"http://127.0.0.1:{servidor.server_address[1]}/api/pdf/" +
                                        self.banco().con.execute("SELECT sha256 FROM arquivo").fetchone()[0],
                                        headers={"Authorization": "Bearer credencial-de-teste-0123456789"})
        with urllib.request.urlopen(pedido, timeout=5) as r:
            self.assertEqual(r.read(5), b"%PDF-")


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab")
class TesteFechamentoDaAuditoria(unittest.TestCase):
    """RISCO-013 (página mista texto + imagem), LIMITE-014 (PDF corrompido com marcadores válidos)
    e o relatório de validação com PDF oficial, que não pode conter dados pessoais."""

    def setUp(self):
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def pdf_misto(self, fracao_da_altura: float) -> bytes:
        """Cabeçalho em texto nativo e, abaixo, o corpo como IMAGEM (texto que o PDF não traz como texto)."""
        import io
        import pypdfium2
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
        from observatorio.operacao import sintetico as S
        corpo = S.diario(date(2026, 10, 2), 18685, [S.resenha_tempo(801, "30-09-2026", "LICENÇA ESPECIAL", 1, 12)])
        documento = pypdfium2.PdfDocument(corpo)
        imagem = documento[0].render(scale=200 / 72).to_pil()
        documento.close()
        memoria = io.BytesIO()
        c = canvas.Canvas(memoria, pagesize=A4)
        c.setFont("Helvetica", 10)
        c.drawString(40, A4[1] - 40, "DIÁRIO OFICIAL Nº 18.685 João Pessoa - Sexta-feira, 02 de Outubro de 2026 página de teste mista")
        c.drawImage(ImageReader(imagem), 0, 0, width=A4[0] * fracao_da_altura, height=A4[1] * fracao_da_altura)
        c.showPage()
        c.save()
        return memoria.getvalue()

    def ler(self, dados: bytes) -> dict:
        from observatorio.leitura import leitor
        caminho = self.pasta / "x.pdf"
        caminho.write_bytes(dados)
        return leitor.ler_arquivo(caminho)

    def test_risco013_pagina_mista_sem_ocr_fica_pendente_e_nao_e_dada_como_lida(self):
        from unittest import mock
        from observatorio.leitura import leitor
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            pagina = self.ler(self.pdf_misto(0.9))["paginas"][0]
        self.assertEqual((pagina["metodo"], pagina["qualidade"]), ("TEXTO", "TEXTO_PARCIAL"))
        self.assertIn("DIÁRIO OFICIAL", pagina["texto"])              # o texto nativo não é descartado

    def test_risco013_imagem_pequena_nao_torna_a_pagina_mista(self):
        from unittest import mock
        from observatorio.leitura import leitor
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            pagina = self.ler(self.pdf_misto(0.3))["paginas"][0]         # 9% da página: um brasão, por exemplo
        self.assertEqual(pagina["qualidade"], "OK")

    def test_risco013_pagina_mista_com_ocr_recupera_o_corpo_digitalizado(self):
        from observatorio.leitura import leitor
        if not leitor.ocr_disponivel()[0]:
            self.skipTest("Tesseract com português não instalado")
        pagina = self.ler(self.pdf_misto(0.9))["paginas"][0]
        self.assertEqual(pagina["metodo"], "OCR")
        self.assertGreater(pagina["palavras"], 60)
        self.assertIn("LICEN", pagina["texto"].upper())

    def test_risco013_pagina_mista_pendente_volta_a_fila_com_refazer(self):
        from unittest import mock
        from observatorio.leitura import leitor
        banco, acervo = B.Banco(self.pasta / "b.sqlite3"), Acervo(self.pasta / "acervo")
        self.addCleanup(banco.fechar)
        coletor.importar_manual(banco, acervo, self.pdf_misto(0.9), date(2026, 10, 2), "manual:misto", "misto.pdf")
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            self.assertEqual(leitor.processar(banco, acervo)["LIDA_COM_PENDENCIAS"], 1)
            self.assertEqual(leitor.processar(banco, acervo), {"LIDA": 0, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0})
            self.assertEqual(leitor.processar(banco, acervo, refazer_pendentes=True)["LIDA_COM_PENDENCIAS"], 1)

    def test_limite014_pdf_corrompido_com_marcadores_validos_nunca_e_dado_como_lido(self):
        from observatorio.gerencias.gediv import processo
        from observatorio.leitura import leitor
        from observatorio.nucleo import pdf
        from observatorio.operacao import sintetico as S
        bom = S.diario(date(2026, 10, 2), 18685, [S.resenha_tempo(801, "30-09-2026", "LICENÇA ESPECIAL", 1, 3)])
        meio = len(bom) // 2
        corrompido = bom[:200] + bytes(reversed(bom[200:meio])) + b"\x00" * 400 + bom[-60:]     # assinatura e %%EOF presentes
        self.assertTrue(pdf.examinar(corrompido).valido)                # os marcadores sozinhos não detectam o defeito
        banco, acervo = B.Banco(self.pasta / "b.sqlite3"), Acervo(self.pasta / "acervo")
        self.addCleanup(banco.fechar)
        coletor.importar_manual(banco, acervo, corrompido, date(2026, 10, 2), "manual:corrompido", "c.pdf")
        contagem = leitor.processar(banco, acervo)
        self.assertEqual((contagem["LIDA"], contagem["LIDA_COM_PENDENCIAS"], contagem["ERRO"]), (0, 0, 1))
        leitura = banco.leituras()[0]
        self.assertEqual(leitura["situacao"], "ERRO")
        self.assertTrue(leitura["erro"])
        self.assertEqual(processo.classificar_pendentes(banco)["arquivos"], 0)       # nada é classificado a partir dele
        from observatorio.painel import indicadores
        cobertura = indicadores.cobertura(banco)
        self.assertEqual((cobertura["edicoes_no_acervo"], cobertura["edicoes_lidas"], cobertura["edicoes_com_pendencia_de_leitura"]), (1, 0, 1))

    def test_relatorio_de_validacao_real_nao_contem_dados_pessoais_e_nada_e_conferido(self):
        from observatorio.operacao import sintetico as S
        from observatorio.operacao import validacao_real
        pdf_ = self.pasta / "diario-oficial-02-10-2026-portal.pdf"
        pdf_.write_bytes(S.diario(date(2026, 10, 2), 18685, [
            S.resenha_progressao(802, "30-09-2026", "HORIZONTAL", "Ocupacional de Apoio Judiciário GAJ-1700:", 10, 4, cargo="POLICIAL PENAL"),
            S.resenha_tempo(801, "30-09-2026", "ANOTAÇÃO DE TEMPO DE SERVIÇO / CONTRIBUIÇÃO", 1, 3)],
            (S.outros_atos(1), S.resenha_progressao(805, "01-10-2026", "VERTICAL", "TEC. ADM.", 40, 2, gediv=False))))
        amostra = self.pasta / "amostra.txt"
        r = validacao_real.executar(pdf_, date(2026, 10, 2), "https://auniao.pb.gov.br/servicos/doe/2026/outubro/diario-oficial-02-10-2026-portal.pdf",
                                    self.pasta / "dados", amostra)
        texto = json.dumps(r, ensure_ascii=False)
        for proibido in ("PESSOA FICTICIA", "SAD-PSE", "900010", "9000001"):
            self.assertNotIn(proibido, texto)
        self.assertEqual((r["resultado"], r["leitura"]["paginas"], r["leitura"]["por_metodo"]), ("FLUXO_EXECUTADO", 2, {"TEXTO": 2}))
        self.assertEqual([(a["numero"], a["decisoes"], a["vinculo_gediv"]) for a in r["gediv"]["atos"]],
                         [("802/2026", 4, "EXPRESSO"), ("801/2026", 3, "EXPRESSO"), ("805/2026", 2, "NAO_EXPRESSO")])
        self.assertEqual(r["gediv"]["por_validacao"], {"PENDENTE": 9})
        self.assertEqual(r["painel"]["indicadores_conferidos"]["decisoes"], 0)
        self.assertEqual(r["painel"]["indicadores_em_conferencia_preliminares"]["decisoes"], 9)
        self.assertEqual(r["comparacao_com_referencia"]["sha256_igual"], False)       # sintético: não é o arquivo oficial
        self.assertIn("PESSOA FICTICIA", amostra.read_text(encoding="utf-8"))          # a amostra privada serve à conferência
        self.assertEqual(r["gediv"]["atos_de_outras_unidades_descartados"], 1)


class TesteRegressoesDaAuditoria(unittest.TestCase):
    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco, self.acervo = B.Banco(self.pasta / "b.sqlite3"), Acervo(self.pasta / "acervo")
        self.addCleanup(lambda: self.banco.fechar())
        self.fonte = FonteLocal(AUniao(), self.s)
        self.base = "/servicos/doe/2026/janeiro"

    def listar(self, dias):
        html = "".join(f'<a href="{self.base}/diario-oficial-{d:02d}-01-2026-portal.pdf/view">x</a>' for d in dias)
        self.s.rotas[self.base] = (200, "text/html", html.encode())
        coletor.descobrir(self.fonte, self.banco, self.s.politica(), date(2026, 1, 1), date(2026, 1, 31))

    def acessos(self, trecho):
        return sum(n for rota, n in self.s.acessos.items() if trecho in rota)

    def test_bug009_resposta_429_nao_e_repetida_nem_tenta_endereco_alternativo(self):
        for dia in (5, 6, 7, 8):
            self.s.rotas[f"{self.base}/diario-oficial-{dia:02d}-01-2026-portal.pdf"] = (429, "text/plain", b"devagar")
        self.listar((5, 6, 7, 8))
        resumo = lotes.executar_lote(self.fonte, self.banco, self.acervo, lotes.PILOTO, politica=self.s.politica(tentativas=3),
                                     dormir=lambda s: None)
        self.assertEqual((resumo["estado"], resumo["tentados"]), ("INTERROMPIDO_RECUSA_DA_FONTE", 1))
        self.assertEqual(self.acessos("portal.pdf"), 1)                 # uma única requisição de download em todo o lote
        self.assertEqual(self.banco.itens_do_lote(resumo["lote"])[0]["erro"][:8], "HTTP_429")

    def test_bug009_erro_429_nao_e_transitorio(self):
        self.assertFalse(rede.ErroRede("HTTP_429").transitorio)
        self.assertTrue(rede.ErroRede("HTTP_429").recusa and rede.ErroRede("HTTP_403").recusa)
        self.assertTrue(rede.ErroRede("HTTP_503").transitorio)

    def test_bug010_piloto_de_tamanho_um_nao_quebra(self):
        for dia in (5, 6, 7):
            self.s.rotas[f"{self.base}/diario-oficial-{dia:02d}-01-2026-portal.pdf"] = (200, "application/pdf", pdf_sintetico(str(dia)))
        self.listar((5, 6, 7))
        selecao = lotes.selecionar_piloto(self.banco, "auniao", lotes.Parametros(tamanho=1))
        self.assertEqual(len(selecao), 1)
        resumo = lotes.executar_lote(self.fonte, self.banco, self.acervo, lotes.PILOTO, lotes.Parametros(tamanho=1, pausa=0),
                                     politica=self.s.politica(), dormir=lambda s: None)
        self.assertEqual((resumo["tentados"], resumo["aprovado"]), (1, False))     # um arquivo não aprova o piloto

    def test_bug011_listagem_alem_do_limite_fica_parcial_e_e_relida(self):
        original, coletor.MAX_PAGINAS = coletor.MAX_PAGINAS, 2
        self.addCleanup(setattr, coletor, "MAX_PAGINAS", original)
        for n in range(4):
            proxima = f'<a href="{self.base}?b_start:int={(n + 1) * 20}">mais</a>' if n < 3 else ""
            item = f'<a href="{self.base}/diario-oficial-{n + 5:02d}-01-2026-portal.pdf/view">x</a>'
            self.s.rotas[self.base + (f"?b_start:int={n * 20}" if n else "")] = (200, "text/html", (item + proxima).encode())
        resultado = coletor.descobrir_mes(self.fonte, self.banco, self.s.politica(), 2026, 1)
        self.assertIn("LISTAGEM_PARCIAL", resultado["erro"])
        self.assertIn("LISTAGEM_PARCIAL", self.banco.varreduras()[0]["erro"])
        self.assertEqual(len(self.banco.publicacoes()), 2)               # o que foi visto fica registrado
        dia = inventario.cobertura(self.banco, date(2026, 1, 20), date(2026, 1, 20), ["auniao"])[0]
        self.assertEqual(dia["situacao"], "NAO_VERIFICADO")              # mês parcial não prova ausência de publicação

    def test_bug012_robots_negado_nao_e_tratado_como_ausente(self):
        self.s.rotas["/robots.txt"] = (403, "text/plain", b"negado")
        self.assertEqual(rede.consultar_robots(self.s.base + self.base, self.s.politica())[0], "RECUSADO")
        self.s.rotas[f"{self.base}/diario-oficial-05-01-2026-portal.pdf"] = (200, "application/pdf", pdf_sintetico("5"))
        self.listar((5,))
        resumo = lotes.executar_lote(self.fonte, self.banco, self.acervo, lotes.PILOTO, politica=self.s.politica(), dormir=lambda s: None)
        self.assertEqual(resumo, {"executado": False, "motivo": "ROBOTS_RECUSADO_PELA_FONTE"})
        self.assertEqual(self.acessos("portal.pdf"), 0)
        del self.s.rotas["/robots.txt"]                                  # 404: sem restrições declaradas
        self.assertEqual(rede.consultar_robots(self.s.base + self.base, self.s.politica())[0], "AUSENTE")

    def _arquivo_lido(self):
        self.banco.registrar_descoberta("manual", "manual:x", "2026-01-07", "normal", 0, "x")
        self.banco.registrar_arquivo(self.banco.publicacao("manual", "manual:x")["id"], "a" * 64, 10, "a.pdf")
        pagina = {"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": "texto já lido", "qualidade": "OK", "palavras": 3}
        self.banco.registrar_leitura("a" * 64, "LIDA", "v1", [pagina], "1", "2026-01-07", None)

    def test_bug015_releitura_com_erro_preserva_o_texto_ja_lido(self):
        self._arquivo_lido()
        self.banco.registrar_leitura("a" * 64, "ERRO", "v2", [], None, None, "ValueError: falhou")
        leitura = self.banco.leituras()[0]
        self.assertEqual((leitura["situacao"], self.banco.paginas("a" * 64)[0]["texto"]), ("LIDA", "texto já lido"))
        self.assertIn("releitura falhou", leitura["erro"])

    def test_bug016_leitura_com_erro_ou_pendencia_volta_a_fila_quando_pedido(self):
        self.banco.registrar_descoberta("manual", "manual:y", "2026-01-07", "normal", 0, "y")
        self.banco.registrar_arquivo(self.banco.publicacao("manual", "manual:y")["id"], "b" * 64, 10, "b.pdf")
        self.banco.registrar_leitura("b" * 64, "ERRO", "v1", [], None, None, "falhou")
        self.assertEqual(len(self.banco.arquivos_sem_leitura("v1")), 0)
        self.assertEqual(len(self.banco.arquivos_sem_leitura("v1", refazer_pendentes=True)), 1)
        pendente = {"numero": 1, "metodo": "OCR", "colunas": 1, "texto": "", "qualidade": "OCR_INDISPONIVEL", "palavras": 0}
        self.banco.registrar_leitura("b" * 64, "LIDA_COM_PENDENCIAS", "v1", [pendente], None, None, None)
        self.assertEqual(len(self.banco.arquivos_sem_leitura("v1", refazer_pendentes=True)), 1)

    def test_bug017_pdf_manual_nao_torna_o_dia_completo(self):
        self._arquivo_lido()
        dia = inventario.cobertura(self.banco, date(2026, 1, 7), date(2026, 1, 7), ["auniao", "cge"])[0]
        self.assertEqual(dia["situacao"], "BAIXADO_SEM_VARREDURA_COMPLETA")
        for fonte in ("auniao", "cge"):
            self.banco.registrar_varredura(fonte, 2026, 1, 0, None)
        dia = inventario.cobertura(self.banco, date(2026, 1, 7), date(2026, 1, 7), ["auniao", "cge"])[0]
        self.assertEqual(dia["situacao"], "COMPLETO")


if __name__ == "__main__":
    unittest.main()
