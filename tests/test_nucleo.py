import tempfile
import unittest
from pathlib import Path

from observatorio.nucleo import pdf, rede
from observatorio.nucleo.acervo import Acervo, ErroAcervo
from observatorio.nucleo.banco import Banco
from tests.apoio import Servidor, pdf_sintetico


class TestePdf(unittest.TestCase):
    def test_pdf_integro_e_aceito(self):
        laudo = pdf.examinar(pdf_sintetico("a"))
        self.assertTrue(laudo.valido)
        self.assertEqual(len(laudo.sha256), 64)

    def test_motivos_de_recusa(self):
        bom = pdf_sintetico("a")
        casos = {
            b"": "VAZIO",
            b"<!DOCTYPE html><html><body>erro</body></html>" + b" " * 2000: "RECEBIDO_HTML_EM_VEZ_DE_PDF",
            b"qualquer coisa" * 200: "SEM_ASSINATURA_PDF",
            b"%PDF-1.4\n%%EOF": "MUITO_PEQUENO",
            bom[:-30]: "SEM_FIM_DE_ARQUIVO",
        }
        for dados, motivo in casos.items():
            self.assertEqual(pdf.examinar(dados).motivo, motivo)


class TesteAcervo(unittest.TestCase):
    def test_guarda_uma_vez_e_confere(self):
        with tempfile.TemporaryDirectory() as pasta:
            acervo = Acervo(pasta)
            sha, gravou = acervo.guardar(pdf_sintetico("a"))
            self.assertTrue(gravou)
            self.assertEqual(acervo.guardar(pdf_sintetico("a")), (sha, False))
            self.assertEqual(acervo.ler(sha), pdf_sintetico("a"))
            self.assertTrue(acervo.conferir(sha))
            self.assertEqual(len(list(Path(pasta).rglob("*.pdf"))), 1)
            self.assertEqual(list(Path(pasta).rglob("*.parcial")), [])

    def test_detecta_arquivo_adulterado(self):
        with tempfile.TemporaryDirectory() as pasta:
            acervo = Acervo(pasta)
            sha, _ = acervo.guardar(pdf_sintetico("a"))
            acervo.caminho(sha).write_bytes(b"adulterado")
            self.assertFalse(acervo.conferir(sha))
            with self.assertRaises(ErroAcervo):
                acervo.guardar(pdf_sintetico("a"))


class TesteBanco(unittest.TestCase):
    def test_descoberta_nao_duplica(self):
        banco = Banco(":memory:")
        self.assertTrue(banco.registrar_descoberta("auniao", "u1", "2026-01-07", "normal", 0, "x"))
        self.assertFalse(banco.registrar_descoberta("auniao", "u1", "2026-01-07", "normal", 0, "x"))
        self.assertEqual(len(banco.publicacoes()), 1)

    def test_conteudo_alterado_preserva_versao_anterior(self):
        banco = Banco(":memory:")
        banco.registrar_descoberta("auniao", "u1", "2026-01-07", "normal", 0, "x")
        pid = banco.publicacao("auniao", "u1")["id"]
        self.assertEqual(banco.registrar_arquivo(pid, "a" * 64, 10, "aa/a.pdf"), "NOVO")
        self.assertEqual(banco.registrar_arquivo(pid, "a" * 64, 10, "aa/a.pdf"), "IGUAL")
        self.assertEqual(banco.registrar_arquivo(pid, "b" * 64, 11, "bb/b.pdf"), "ALTERADO")
        self.assertEqual([v["sha256"][0] for v in banco.versoes(pid)], ["a", "b"])
        self.assertEqual(len(banco.arquivos()), 2)

    def test_banco_persiste_em_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "sub" / "b.sqlite3"
            banco = Banco(caminho)
            banco.registrar_descoberta("cge", "u", None, "normal", 0, "x")
            banco.fechar()
            self.assertEqual(len(Banco(caminho).publicacoes()), 1)


class TesteRede(unittest.TestCase):
    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)

    def test_normaliza_espacos_e_acentos(self):
        self.assertEqual(rede.normalizar("https://CGE.pb.gov.br/a/01-Janeiro/Diario Oficial.pdf"),
                         "https://cge.pb.gov.br/a/01-Janeiro/Diario%20Oficial.pdf")
        self.assertEqual(rede.normalizar("https://x/Di%C3%A1rio.pdf"), "https://x/Di%C3%A1rio.pdf")
        self.assertEqual(rede.normalizar("https://x/Diário.pdf"), "https://x/Di%C3%A1rio.pdf")

    def test_recusa_servidor_e_esquema_fora_da_lista(self):
        p = rede.Politica(servidores=frozenset({"auniao.pb.gov.br"}))
        for url in ("http://auniao.pb.gov.br/x", "https://exemplo.com/x", "https://auniao.pb.gov.br@exemplo.com/x",
                    "https://usuario:senha@auniao.pb.gov.br/x", "file:///etc/passwd"):
            with self.assertRaises(rede.ErroRede) as erro:
                rede.obter(url, p)
            self.assertEqual(erro.exception.categoria, "URL_NAO_PERMITIDA")

    def test_segue_redirecionamento_interno_e_bloqueia_externo(self):
        self.s.rotas["/a"] = (302, "text/plain", b"/b")
        self.s.rotas["/b"] = (200, "text/plain", b"ok")
        self.s.rotas["/fora"] = (302, "text/plain", b"http://exemplo.invalid/x")
        r = rede.obter(self.s.base + "/a", self.s.politica())
        self.assertEqual((r.corpo, len(r.redirecionamentos)), (b"ok", 1))
        with self.assertRaises(rede.ErroRede) as erro:
            rede.obter(self.s.base + "/fora", self.s.politica())
        self.assertEqual(erro.exception.categoria, "URL_NAO_PERMITIDA")

    def test_repete_falha_transitoria_e_nao_repete_404(self):
        self.s.rotas["/instavel"] = lambda n: (503, "text/plain", b"") if n == 1 else (200, "text/plain", b"ok")
        self.assertEqual(rede.obter(self.s.base + "/instavel", self.s.politica()).corpo, b"ok")
        with self.assertRaises(rede.ErroRede) as erro:
            rede.obter(self.s.base + "/nao-existe", self.s.politica())
        self.assertEqual(erro.exception.categoria, "HTTP_404")
        self.assertEqual(self.s.acessos["/nao-existe"], 1)

    def test_limite_de_tamanho(self):
        self.s.rotas["/grande"] = (200, "application/pdf", b"x" * 5000)
        with self.assertRaises(rede.ErroRede) as erro:
            rede.obter(self.s.base + "/grande", self.s.politica(max_bytes=1000))
        self.assertEqual(erro.exception.categoria, "TAMANHO_EXCEDIDO")

    def test_conexao_recusada_e_classificada(self):
        politica = rede.Politica(servidores=frozenset({"127.0.0.1:9"}), esquemas=frozenset({"http"}),
                                 tempo_limite=1, tentativas=1)
        with self.assertRaises(rede.ErroRede) as erro:
            rede.obter("http://127.0.0.1:9/x", politica)
        self.assertIn(erro.exception.categoria, ("CONEXAO", "TEMPO_ESGOTADO"))

    def test_robots(self):
        self.assertEqual(rede.consultar_robots(self.s.base + "/x", self.s.politica())[0], "AUSENTE")
        self.s.rotas["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /privado\n")
        situacao, regras = rede.consultar_robots(self.s.base + "/x", self.s.politica())
        self.assertEqual(situacao, "LIDO")
        self.assertTrue(regras.can_fetch(rede.AGENTE, self.s.base + "/servicos/doe/2026"))
        self.assertFalse(regras.can_fetch(rede.AGENTE, self.s.base + "/privado/x"))


if __name__ == "__main__":
    unittest.main()
