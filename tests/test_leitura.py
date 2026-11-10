import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from observatorio.leitura.pagina import Palavra, agrupar_linhas, encontrar_divisores, identificar_edicao, ler_pagina
from observatorio.nucleo.acervo import Acervo
from observatorio.nucleo.banco import Banco

TEM_BIBLIOTECAS = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))


def linha(x, topo, texto, passo=30.0):
    """Palavras em sequência a partir de x, cada uma com 25 pontos de largura."""
    return [Palavra(x + i * passo, x + i * passo + 25, topo, t) for i, t in enumerate(texto.split())]


def pagina_duas_colunas(linhas=12):
    palavras = linha(40, 30, "CABECALHO GERAL DA PAGINA QUE OCUPA TODA A LARGURA DISPONIVEL NO TOPO DO DIARIO")
    for i in range(linhas):
        topo = 60 + i * 12
        palavras += linha(40, topo, f"E{i:02d} texto da esquerda aqui")
        palavras += linha(310, topo, f"D{i:02d} texto da direita aqui")
    return palavras


class TestePaginaPura(unittest.TestCase):
    def test_agrupa_palavras_em_linhas(self):
        palavras = [Palavra(50, 70, 10.4, "b"), Palavra(10, 30, 10, "a"), Palavra(10, 30, 25, "c")]
        self.assertEqual([[p.texto for p in l] for l in agrupar_linhas(palavras)], [["a", "b"], ["c"]])

    def test_duas_colunas_sao_lidas_uma_de_cada_vez(self):
        texto, colunas = ler_pagina(pagina_duas_colunas(), 595)
        linhas = texto.split("\n")
        self.assertEqual(colunas, 2)
        self.assertTrue(linhas[0].startswith("CABECALHO GERAL"))
        self.assertEqual([l[:3] for l in linhas[1:]], [f"E{i:02d}" for i in range(12)] + [f"D{i:02d}" for i in range(12)])
        self.assertFalse(any("esquerda" in l and "direita" in l for l in linhas))

    def test_titulo_de_largura_total_no_meio_separa_as_faixas(self):
        palavras = pagina_duas_colunas()
        palavras = [p for p in palavras if abs(p.topo - (60 + 6 * 12)) > 1]          # remove a 7ª linha das colunas
        palavras += linha(40, 60 + 6 * 12, "SECRETARIA DE ESTADO DA ADMINISTRACAO TITULO QUE ATRAVESSA AS DUAS COLUNAS DA PAGINA INTEIRA")
        marcas = [l[:3] for l in ler_pagina(palavras, 595)[0].split("\n")]
        esperado = (["CAB"] + [f"E{i:02d}" for i in range(6)] + [f"D{i:02d}" for i in range(6)] + ["SEC"]
                    + [f"E{i:02d}" for i in range(7, 12)] + [f"D{i:02d}" for i in range(7, 12)])
        self.assertEqual(marcas, esperado)

    def test_pagina_de_uma_coluna_nao_e_dividida(self):
        palavras = []
        for i in range(15):
            palavras += linha(40, 30 + i * 12, f"L{i:02d} texto corrido que ocupa a largura inteira da pagina sem corredor central algum aqui")
        texto, colunas = ler_pagina(palavras, 595)
        self.assertEqual((colunas, len(texto.split("\n"))), (1, 15))

    def test_poucas_linhas_nao_bastam_para_declarar_colunas(self):
        self.assertEqual(encontrar_divisores(agrupar_linhas(pagina_duas_colunas(3)), 595), [])

    def test_coluna_com_linhas_so_de_um_lado(self):
        palavras = pagina_duas_colunas()
        palavras += linha(310, 60 + 12 * 12, "D12 linha apenas na direita")
        marcas = [l[:3] for l in ler_pagina(palavras, 595)[0].split("\n")]
        self.assertEqual(marcas[-1], "D12")
        self.assertEqual(marcas.index("D00"), 13)

    def test_cabecalho_da_edicao(self):
        # formatos observados no texto indexado de edições reais de 2026 (inclusive "Ofi cial")
        real = "João Pessoa - Sexta-feira, 08 de Maio de 2026 R$ 2,55\nESTADO DA PARAÍBA\nDIÁRIO OFICIAL\nNº 18.585\nATOS DO PODER LEGISLATIVO"
        self.assertEqual(identificar_edicao(real), ("18585", "2026-05-08"))
        self.assertEqual(identificar_edicao("João Pessoa - Sábado, 1 de Agosto de 2026\nDIÁRIO OFI CIAL\nNº 18.642"), ("18642", "2026-08-01"))
        self.assertEqual(identificar_edicao("João Pessoa - Terça-feira, 10 de Março de 2026\nDIÁRIO OFICIAL Nº 18.546"), ("18546", "2026-03-10"))
        self.assertEqual(identificar_edicao("texto qualquer sem cabeçalho"), (None, None))
        self.assertEqual(identificar_edicao("João Pessoa - Segunda-feira, 31 de Fevereiro de 2026"), (None, None))


def pdf_duas_colunas() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4)
    largura, altura = A4
    c.setFont("Helvetica", 7)
    c.drawString(40, altura - 40, "João Pessoa - Sexta-feira, 08 de Maio de 2026 R$ 2,55")
    c.drawString(40, altura - 55, "ESTADO DA PARAÍBA DIÁRIO OFICIAL Nº 18.585 - documento sintético de teste, sem valor oficial algum")
    for i in range(30):
        y = altura - 90 - i * 12
        c.drawString(40, y, f"E{i:02d} servidor fictício Fulano de Tal SAD-PRC-2026/{i:05d} deferido")
        c.drawString(310, y, f"D{i:02d} servidora fictícia Beltrana de Tal SES-PRC-2026/{i:05d} indeferido")
    c.showPage()
    c.rect(100, 100, 300, 300, fill=1)   # página sem texto, como uma página digitalizada
    c.showPage()
    c.save()
    return memoria.getvalue()


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab (pip install -r requirements-dev.txt)")
class TesteLeitorComPdf(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.banco, self.acervo = Banco(":memory:"), Acervo(Path(pasta.name) / "acervo")
        self.addCleanup(self.banco.fechar)
        self.dados = pdf_duas_colunas()

    def guardar(self, dados, url="u1"):
        sha, _ = self.acervo.guardar(dados)
        self.banco.registrar_descoberta("manual", url, "2026-05-08", "normal", 0, "x")
        self.banco.registrar_arquivo(self.banco.publicacao("manual", url)["id"], sha, len(dados), self.acervo.caminho_relativo(sha))
        return sha

    def test_le_colunas_cabecalho_e_marca_pagina_sem_texto(self):
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados)
        self.assertEqual(leitor.processar(self.banco, self.acervo), {"LIDA": 0, "LIDA_COM_PAGINAS_SEM_TEXTO": 1, "ERRO": 0, "na_fila": 0})
        leitura = self.banco.leituras()[0]
        self.assertEqual((leitura["paginas"], leitura["paginas_sem_texto"], leitura["numero_edicao"], leitura["data_edicao"]),
                         (2, 1, "18585", "2026-05-08"))
        p1, p2 = self.banco.paginas(sha)
        self.assertEqual((p1["metodo"], p1["colunas"], p2["metodo"]), ("TEXTO", 2, "SEM_TEXTO"))
        linhas = p1["texto"].split("\n")
        marcas = [l[:3] for l in linhas if l[:1] in "ED" and l[1:3].isdigit()]
        self.assertEqual(marcas, [f"E{i:02d}" for i in range(30)] + [f"D{i:02d}" for i in range(30)])
        self.assertFalse(any("Fulano" in l and "Beltrana" in l for l in linhas))     # colunas não se misturam
        self.assertIn("SAD-PRC-2026/00007 deferido", p1["texto"])

    def test_retomada_nao_rele_o_que_ja_foi_lido(self):
        from observatorio.leitura import leitor
        self.guardar(self.dados)
        leitor.processar(self.banco, self.acervo)
        momento = self.banco.leituras()[0]["concluida_em"]
        self.assertEqual(sum(v for k, v in leitor.processar(self.banco, self.acervo).items()), 0)
        self.assertEqual(self.banco.leituras()[0]["concluida_em"], momento)

    def test_limite_deixa_o_restante_na_fila(self):
        from observatorio.leitura import leitor
        self.guardar(self.dados)
        self.guardar(self.dados + b"\n% outra copia\n", "u2")
        self.assertEqual(leitor.processar(self.banco, self.acervo, limite=1)["na_fila"], 1)
        self.assertEqual(leitor.processar(self.banco, self.acervo)["na_fila"], 0)
        self.assertEqual(len(self.banco.leituras()), 2)

    def test_arquivo_ilegivel_vira_erro_e_nao_para_a_fila(self):
        from observatorio.leitura import leitor
        from tests.apoio import pdf_sintetico
        self.guardar(pdf_sintetico("estrutura minima, sem paginas"), "ruim")
        self.guardar(self.dados, "bom")
        contagem = leitor.processar(self.banco, self.acervo)
        self.assertEqual((contagem["ERRO"], contagem["LIDA_COM_PAGINAS_SEM_TEXTO"]), (1, 1))
        self.assertTrue([l for l in self.banco.leituras() if l["situacao"] == "ERRO"][0]["erro"])

    def test_arquivo_adulterado_no_acervo_nao_e_lido(self):
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados)
        self.acervo.caminho(sha).write_bytes(b"adulterado")
        self.assertEqual(leitor.processar(self.banco, self.acervo)["ERRO"], 1)
        self.assertEqual(self.banco.paginas(sha), [])


if __name__ == "__main__":
    unittest.main()
