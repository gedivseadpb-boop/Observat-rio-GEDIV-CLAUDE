import tempfile
import unittest
from datetime import date
from pathlib import Path

from observatorio.coleta import coletor, inventario
from observatorio.coleta.fontes import CGE, AUniao, data_do_nome, links, tipo_do_nome
from observatorio.nucleo import banco as B
from observatorio.nucleo.acervo import Acervo
from tests.apoio import FonteLocal, Servidor, pdf_sintetico

# Listagens sintéticas. Reproduzem os FORMATOS DE ENDEREÇO confirmados em 10/11/2026
# (não a estrutura real das páginas, que ainda não pôde ser lida diretamente).
LISTAGEM_AUNIAO = """
<html><body><nav><a href="/servicos/doe/2026">2026</a> <a href="https://exemplo.com/x.pdf">externo</a></nav>
<a href="https://auniao.pb.gov.br/servicos/doe/2026/janeiro/diario-oficial-07-01-2026-portal.pdf/view">Diário Oficial 07-01-2026 Portal.pdf</a>
<a href="/servicos/doe/2026/janeiro/diario-oficial-07-01-2026-portal.pdf/@@download/file/Di%C3%A1rio%20Oficial%2007-01-2026%20Portal.pdf">baixar</a>
<a href="https://www.auniao.pb.gov.br/servicos/doe/2026/janeiro/diario-oficial-08-01-2026-portal.pdf">Diário 08</a>
<a href="/servicos/doe/2026/janeiro/diario-oficial-08-01-2026-portal-1.pdf/view">Diário 08 (2)</a>
<a href="/servicos/doe/2026/janeiro/diario-oficial-09-01-2026-suplemento.pdf/view">Suplemento 09</a>
<a href="/servicos/doe/2026/janeiro?b_start:int=20">Próximo</a>
</body></html>"""
PAGINA_2 = '<a href="/servicos/doe/2026/janeiro/diario-oficial-10-01-2026-portal.pdf/view">Diário 10</a>'
LISTAGEM_CGE = """
<table><tr><td><a href="../Uploads/doe/2026/01-Janeiro/07-Diario Oficial 07-01-2026 TOTAL.pdf">07/01</a></td>
<td><a href="/gati/Uploads/doe/2026/01-Janeiro/08-Diario Oficial 08-01-2026 SUPLEMENTO.pdf">08/01 sup</a></td>
<td><a href="/gati/outros/manual.pdf">manual</a></td></tr></table>"""


class TesteLeituraDasListagens(unittest.TestCase):
    def test_links_e_nomes(self):
        self.assertEqual(links('<a href="a">x <b>y</b></a><a>sem</a><a href="b">z'), [("a", "x y"), ("b", "z")])
        self.assertEqual(data_do_nome("diario-oficial-07-01-2026-portal.pdf"), date(2026, 1, 7))
        self.assertIsNone(data_do_nome("diario-oficial-31-02-2026.pdf"))
        self.assertIsNone(data_do_nome("sem-data.pdf"))
        self.assertEqual(tipo_do_nome("Diario Oficial 08-01-2026 SUPLEMENTO.pdf"), "suplemento")

    def test_auniao_unifica_variantes_do_mesmo_documento(self):
        fonte = AUniao()
        itens, paginas = fonte.extrair(LISTAGEM_AUNIAO, fonte.url_mes(2026, 1))
        por_url = {i.url.rsplit("/", 1)[-1]: i for i in itens}
        self.assertEqual(sorted(por_url), ["diario-oficial-07-01-2026-portal.pdf", "diario-oficial-08-01-2026-portal-1.pdf",
                                           "diario-oficial-08-01-2026-portal.pdf", "diario-oficial-09-01-2026-suplemento.pdf"])
        self.assertTrue(all(i.url.startswith("https://auniao.pb.gov.br/servicos/doe/2026/janeiro/") for i in itens))
        self.assertEqual(por_url["diario-oficial-08-01-2026-portal-1.pdf"].ordem, 1)
        self.assertEqual(por_url["diario-oficial-08-01-2026-portal.pdf"].ordem, 0)
        self.assertEqual(por_url["diario-oficial-09-01-2026-suplemento.pdf"].tipo, "suplemento")
        self.assertEqual(paginas, ["https://auniao.pb.gov.br/servicos/doe/2026/janeiro?b_start:int=20"])

    def test_auniao_pasta_do_ano(self):
        self.assertEqual(AUniao().url_mes(2026, 3), "https://auniao.pb.gov.br/servicos/doe/2026/marco")
        self.assertEqual(AUniao().url_mes(2025, 11), "https://auniao.pb.gov.br/servicos/doe/2025-1/novembro")

    def test_cge_codifica_espacos_e_ignora_outros_pdfs(self):
        fonte = CGE()
        itens, _ = fonte.extrair(LISTAGEM_CGE, fonte.url_mes(2026, 1))
        self.assertEqual([i.url for i in itens], [
            "https://cge.pb.gov.br/gati/Uploads/doe/2026/01-Janeiro/07-Diario%20Oficial%2007-01-2026%20TOTAL.pdf",
            "https://cge.pb.gov.br/gati/Uploads/doe/2026/01-Janeiro/08-Diario%20Oficial%2008-01-2026%20SUPLEMENTO.pdf"])
        self.assertEqual([i.data for i in itens], [date(2026, 1, 7), date(2026, 1, 8)])
        self.assertEqual(itens[1].tipo, "suplemento")


class TesteColeta(unittest.TestCase):
    INICIO, FIM = date(2026, 1, 1), date(2026, 1, 31)

    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco, self.acervo = B.Banco(":memory:"), Acervo(self.pasta / "acervo")
        self.addCleanup(self.banco.fechar)
        self.auniao, self.cge = FonteLocal(AUniao(), self.s), FonteLocal(CGE(), self.s)
        j = "/servicos/doe/2026/janeiro"
        self.s.rotas.update({
            j: (200, "text/html", LISTAGEM_AUNIAO.encode()),
            j + "?b_start:int=20": (200, "text/html", PAGINA_2.encode()),
            j + "/diario-oficial-07-01-2026-portal.pdf": (200, "application/pdf", pdf_sintetico("07")),
            j + "/diario-oficial-08-01-2026-portal.pdf": (200, "application/pdf", pdf_sintetico("08")),
            j + "/diario-oficial-08-01-2026-portal-1.pdf": (200, "application/pdf", pdf_sintetico("08-1")),
            j + "/diario-oficial-09-01-2026-suplemento.pdf": (200, "application/pdf", pdf_sintetico("09s")),
            j + "/diario-oficial-10-01-2026-portal.pdf": (200, "application/pdf", pdf_sintetico("10")),
        })
        self.j = j

    def coletar(self, fontes=None, **extras):
        return coletor.coletar(fontes or [self.auniao], self.banco, self.acervo, self.INICIO, self.FIM,
                               politica=self.s.politica(), **extras)

    def test_coleta_completa_com_paginacao(self):
        resumo = self.coletar()
        parte = resumo["fontes"]["auniao"]
        self.assertEqual(parte["varreduras"][0]["listadas"], 5)
        self.assertEqual(parte["downloads"], {"NOVO": 5})
        self.assertEqual(len(self.banco.arquivos()), 5)
        self.assertTrue(all(self.acervo.conferir(a["sha256"]) for a in self.banco.arquivos()))
        self.assertFalse(coletor.houve_pendencia(resumo))

    def test_segunda_execucao_nao_baixa_nem_duplica(self):
        self.coletar()
        acessos = dict(self.s.acessos)
        resumo = self.coletar()
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {})
        self.assertEqual(resumo["fontes"]["auniao"]["varreduras"][0]["novas"], 0)
        pdfs = [k for k in self.s.acessos if k.endswith(".pdf")]
        self.assertTrue(all(self.s.acessos[k] == acessos[k] for k in pdfs))
        self.assertEqual(len(self.banco.publicacoes()), 5)

    def test_pagina_html_no_lugar_do_pdf_usa_endereco_alternativo(self):
        rota = self.j + "/diario-oficial-07-01-2026-portal.pdf"
        self.s.rotas[rota] = (200, "text/html", b"<html><body>visualizar</body></html>" + b" " * 2000)
        self.s.rotas[rota + "/@@download/file"] = (200, "application/pdf", pdf_sintetico("07"))
        self.assertEqual(self.coletar()["fontes"]["auniao"]["downloads"], {"NOVO": 5})

    def test_html_sem_alternativa_fica_invalida_e_nao_entra_no_acervo(self):
        rota = self.j + "/diario-oficial-07-01-2026-portal.pdf"
        self.s.rotas[rota] = (200, "text/html", b"<html><body>erro</body></html>" + b" " * 2000)
        resumo = self.coletar()
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"NOVO": 4, "INVALIDA": 1})
        linha = self.banco.publicacoes(estados=(B.INVALIDA,))[0]
        self.assertIn("RECEBIDO_HTML_EM_VEZ_DE_PDF", linha["ultimo_erro"])
        self.assertIsNone(linha["sha256"])
        self.assertEqual(len(self.banco.arquivos()), 4)
        self.assertTrue(coletor.houve_pendencia(resumo))

    def test_falha_de_download_e_recuperada_na_execucao_seguinte(self):
        rota = self.j + "/diario-oficial-10-01-2026-portal.pdf"
        bom = self.s.rotas[rota]
        self.s.rotas[rota] = (503, "text/plain", b"")
        self.assertEqual(self.coletar()["fontes"]["auniao"]["downloads"], {"NOVO": 4, "FALHA_DOWNLOAD": 1})
        self.s.rotas[rota] = bom
        self.assertEqual(self.coletar()["fontes"]["auniao"]["downloads"], {"NOVO": 1})
        self.assertEqual(len(self.banco.publicacoes(estados=(B.BAIXADA,))), 5)

    def test_tentativas_esgotadas_param_de_insistir(self):
        rota = self.j + "/diario-oficial-10-01-2026-portal.pdf"
        self.s.rotas[rota] = (404, "text/plain", b"")
        for _ in range(5):
            self.coletar()
        self.assertEqual(self.coletar()["fontes"]["auniao"]["downloads"], {"ESGOTADA": 1})

    def test_listagem_inacessivel_nao_vira_ausencia_de_publicacao(self):
        self.s.rotas[self.j] = (503, "text/plain", b"")
        resumo = self.coletar()
        self.assertIn("erro", resumo["fontes"]["auniao"]["varreduras"][0])
        self.assertTrue(coletor.houve_pendencia(resumo))
        linhas = inventario.cobertura(self.banco, self.INICIO, self.FIM, ["auniao"])
        self.assertEqual({l["situacao"] for l in linhas}, {"NAO_VERIFICADO"})

    def test_limite_por_execucao(self):
        resumo = self.coletar(limite=2)
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"NOVO": 2, "ADIADA": 3})
        self.assertTrue(coletor.houve_pendencia(resumo))

    def test_periodo_restringe_o_que_e_registrado(self):
        coletor.coletar([self.auniao], self.banco, self.acervo, date(2026, 1, 8), date(2026, 1, 9), politica=self.s.politica())
        self.assertEqual(sorted({p["data_publicacao"] for p in self.banco.publicacoes()}), ["2026-01-08", "2026-01-09"])

    def test_conteudo_trocado_no_mesmo_endereco_preserva_original(self):
        self.coletar()
        rota = self.j + "/diario-oficial-07-01-2026-portal.pdf"
        self.s.rotas[rota] = (200, "application/pdf", pdf_sintetico("07-republicado"))
        resumo = self.coletar(reverificar=True)
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"ALTERADO": 1, "IGUAL": 4})
        publicacao = self.banco.publicacao("auniao", self.s.base + rota)
        versoes = self.banco.versoes(publicacao["id"])
        self.assertEqual(len(versoes), 2)
        self.assertTrue(all(self.acervo.conferir(v["sha256"]) for v in versoes))

    def test_mesmo_arquivo_em_duas_fontes_e_um_unico_documento(self):
        self.s.rotas["/gati/sap/sap26.asp?a=2026&m=01"] = (200, "text/html", LISTAGEM_CGE.encode("latin-1"))
        self.s.rotas["/gati/Uploads/doe/2026/01-Janeiro/07-Diario%20Oficial%2007-01-2026%20TOTAL.pdf"] = (
            200, "application/pdf", pdf_sintetico("07"))
        self.s.rotas["/gati/Uploads/doe/2026/01-Janeiro/08-Diario%20Oficial%2008-01-2026%20SUPLEMENTO.pdf"] = (
            200, "application/pdf", pdf_sintetico("08-sup-cge"))
        self.coletar([self.auniao, self.cge])
        self.assertEqual(len(self.banco.publicacoes()), 7)
        self.assertEqual(len(self.banco.arquivos()), 6)
        linhas = {l["data"]: l for l in inventario.cobertura(self.banco, self.INICIO, self.FIM, ["auniao", "cge"])}
        self.assertEqual((linhas["2026-01-07"]["listadas"], linhas["2026-01-07"]["arquivos_distintos"]), (2, 1))
        self.assertEqual(linhas["2026-01-07"]["situacao"], "COMPLETO")
        self.assertTrue(linhas["2026-01-10"]["so_em_uma_fonte"])
        self.assertEqual(linhas["2026-01-11"]["situacao"], "SEM_PUBLICACAO_LISTADA")
        self.assertEqual(inventario.totais(list(linhas.values()))["dias"], 31)

    def test_robots_restritivo_interrompe_a_coleta_da_fonte(self):
        self.s.rotas["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /servicos/\n")
        resumo = self.coletar()
        self.assertEqual(resumo["fontes"]["auniao"]["robots"], "RESTRINGE_A_COLETA")
        self.assertEqual(self.banco.publicacoes(), [])
        self.assertTrue(coletor.houve_pendencia(resumo))

    def test_importacao_manual_valida_e_nao_duplica(self):
        dados = pdf_sintetico("07")
        r1 = coletor.importar_manual(self.banco, self.acervo, dados, date(2026, 1, 7), "manual:a.pdf", "a.pdf")
        r2 = coletor.importar_manual(self.banco, self.acervo, dados, date(2026, 1, 7), "manual:a.pdf", "a.pdf")
        self.assertEqual((r1["aceito"], r1["arquivo_novo"], r2["arquivo_novo"], r2["resultado"]), (True, True, False, "IGUAL"))
        recusa = coletor.importar_manual(self.banco, self.acervo, b"nao e pdf" * 300, date(2026, 1, 7), "manual:b", "b")
        self.assertEqual((recusa["aceito"], recusa["motivo"]), (False, "SEM_ASSINATURA_PDF"))
        self.assertEqual(len(self.banco.arquivos()), 1)

    def test_execucao_fica_registrada(self):
        self.coletar()
        ultima = self.banco.ultima_execucao()
        self.assertIsNotNone(ultima["concluida_em"])
        self.assertIn('"NOVO": 5', ultima["resumo"])


class TesteLinhaDeComando(unittest.TestCase):
    def test_importar_inventario_e_conferir(self):
        import contextlib
        import io
        from observatorio.coleta.__main__ import main
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "doe.pdf"
            origem.write_bytes(pdf_sintetico("cli"))
            dados = str(Path(pasta) / "dados")
            with contextlib.redirect_stdout(io.StringIO()) as saida:
                self.assertEqual(main(["importar", str(origem), "--data", "2026-01-07", "--dados", dados]), 0)
                self.assertEqual(main(["conferir", "--dados", dados]), 0)
                self.assertEqual(main(["inventario", "--inicio", "2026-01-07", "--fim", "2026-01-07", "--dados", dados]), 0)
            self.assertIn('"COMPLETO": 1', saida.getvalue())
            next((Path(dados) / "acervo").rglob("*.pdf")).write_bytes(b"x")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["conferir", "--dados", dados]), 3)


if __name__ == "__main__":
    unittest.main()
