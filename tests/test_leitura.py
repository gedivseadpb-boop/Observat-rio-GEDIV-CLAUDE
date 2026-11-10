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
        self.assertEqual(identificar_edicao("João Pessoa Sexta-feira, 08 de Maio de 2026 R$ 2,55\nDIÁRIO OFICIAL Nº 18.585"), ("18585", "2026-05-08"))
        self.assertEqual(identificar_edicao("texto qualquer sem cabeçalho"), (None, None))
        self.assertEqual(identificar_edicao("João Pessoa - Segunda-feira, 31 de Fevereiro de 2026"), (None, None))


TEM_OCR = False
if TEM_BIBLIOTECAS:
    from observatorio.leitura import leitor as _leitor
    TEM_OCR = _leitor.ocr_disponivel()[0]


def pdf_duas_colunas(paginas_extras: bool = True, fonte: float = 7) -> bytes:
    """Documento SINTÉTICO, com nomes e processos fictícios. Não reproduz nenhum Diário real."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4)
    largura, altura = A4
    c.setFont("Helvetica", fonte)
    c.drawString(40, altura - 40, "João Pessoa - Sexta-feira, 08 de Maio de 2026 R$ 2,55")
    c.drawString(40, altura - 55, "ESTADO DA PARAÍBA DIÁRIO OFICIAL Nº 18.585 - documento sintético de teste, sem valor oficial algum")
    for i in range(30):
        y = altura - 90 - i * 12
        c.drawString(40, y, f"E{i:02d} servidor fictício Fulano de Tal SAD-PRC-2026/{i:05d} deferido")
        c.drawString(310, y, f"D{i:02d} servidora fictícia Beltrana de Tal SES-PRC-2026/{i:05d} indeferido")
    c.showPage()
    if paginas_extras:
        c.rect(100, 100, 300, 300, fill=1)   # conteúdo gráfico sem texto algum
        c.showPage()
        c.showPage()                          # página em branco
    c.save()
    return memoria.getvalue()


def pdf_digitalizado() -> bytes:
    """Simula uma edição digitalizada: a página de duas colunas vira uma imagem, sem texto nativo."""
    import pypdfium2
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    documento = pypdfium2.PdfDocument(pdf_duas_colunas(paginas_extras=False, fonte=8))
    pagina = documento[0]
    imagem = pagina.render(scale=300 / 72).to_pil()
    pagina.close()
    documento.close()
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4)
    c.drawImage(ImageReader(imagem), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()
    return memoria.getvalue()


class BaseLeitor(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco, self.acervo = Banco(":memory:"), Acervo(self.pasta / "acervo")
        self.addCleanup(self.banco.fechar)

    def guardar(self, dados, url="u1", data="2026-05-08", fonte="manual"):
        sha, _ = self.acervo.guardar(dados)
        self.banco.registrar_descoberta(fonte, url, data, "normal", 0, "x")
        self.banco.registrar_arquivo(self.banco.publicacao(fonte, url)["id"], sha, len(dados), self.acervo.caminho_relativo(sha))
        return sha


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab (pip install -r requirements-dev.txt)")
class TesteLeitorComPdf(BaseLeitor):
    def setUp(self):
        super().setUp()
        self.dados = pdf_duas_colunas()

    def test_le_colunas_cabecalho_e_classifica_cada_pagina(self):
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados)
        self.assertEqual(leitor.processar(self.banco, self.acervo), {"LIDA": 0, "LIDA_COM_PENDENCIAS": 1, "ERRO": 0, "na_fila": 0})
        leitura = self.banco.leituras()[0]
        self.assertEqual((leitura["paginas"], leitura["numero_edicao"], leitura["data_edicao"], leitura["inconsistencias"]),
                         (3, "18585", "2026-05-08", "[]"))
        p1, p2, p3 = self.banco.paginas(sha)
        self.assertEqual((p1["metodo"], p1["colunas"], p1["qualidade"]), ("TEXTO", 2, "OK"))
        self.assertIn(p2["qualidade"], ("ILEGIVEL", "OCR_INDISPONIVEL"))   # conteúdo gráfico sem texto reconhecível
        self.assertEqual((p3["metodo"], p3["qualidade"]), ("NENHUM", "VAZIA"))
        self.assertEqual(leitura["paginas_com_pendencia"], 1)
        linhas = p1["texto"].split("\n")
        marcas = [l[:3] for l in linhas if l[:1] in "ED" and l[1:3].isdigit()]
        self.assertEqual(marcas, [f"E{i:02d}" for i in range(30)] + [f"D{i:02d}" for i in range(30)])
        self.assertFalse(any("Fulano" in l and "Beltrana" in l for l in linhas))     # colunas não se misturam
        self.assertIn("SAD-PRC-2026/00007 deferido", p1["texto"])

    def test_rastreabilidade_da_pagina_ate_a_origem(self):
        import hashlib
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados, "https://exemplo.invalid/a.pdf", fonte="auniao")
        self.guardar(self.dados, "https://exemplo.invalid/b.pdf", fonte="cge")           # mesmo conteúdo, outra fonte
        leitor.processar(self.banco, self.acervo)
        self.assertEqual(len(self.banco.leituras()), 1)                                  # um arquivo, uma leitura
        self.assertEqual([(o["fonte"], o["url"]) for o in self.banco.origens(sha)],
                         [("auniao", "https://exemplo.invalid/a.pdf"), ("cge", "https://exemplo.invalid/b.pdf")])
        p1 = self.banco.paginas(sha)[0]
        self.assertEqual(p1["texto_sha256"], hashlib.sha256(p1["texto"].encode()).hexdigest())
        self.assertEqual(p1["palavras"], len(p1["texto"].split()))                       # nenhuma palavra perdida na reordenação
        self.assertEqual(hashlib.sha256(self.acervo.ler(sha)).hexdigest(), sha)

    def test_data_do_cabecalho_diferente_da_origem_e_apontada(self):
        from observatorio.leitura import leitor
        self.guardar(pdf_duas_colunas(paginas_extras=False), data="2026-05-09")
        self.assertEqual(leitor.processar(self.banco, self.acervo)["LIDA_COM_PENDENCIAS"], 1)
        self.assertIn("DATA_DIVERGENTE: cabeçalho 2026-05-08, origem 2026-05-09", self.banco.leituras()[0]["inconsistencias"])

    def test_documento_integro_e_coerente_fica_lido_sem_pendencias(self):
        from observatorio.leitura import leitor
        self.guardar(pdf_duas_colunas(paginas_extras=False))
        self.assertEqual(leitor.processar(self.banco, self.acervo), {"LIDA": 1, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0})

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
        self.assertEqual((contagem["ERRO"], contagem["LIDA_COM_PENDENCIAS"]), (1, 1))
        self.assertTrue([l for l in self.banco.leituras() if l["situacao"] == "ERRO"][0]["erro"])

    def test_arquivo_adulterado_no_acervo_nao_e_lido(self):
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados)
        self.acervo.caminho(sha).write_bytes(b"adulterado")
        self.assertEqual(leitor.processar(self.banco, self.acervo)["ERRO"], 1)
        self.assertEqual(self.banco.paginas(sha), [])

    def test_sem_tesseract_a_pagina_fica_marcada_e_nao_e_dada_como_lida(self):
        from unittest import mock
        from observatorio.leitura import leitor
        sha = self.guardar(self.dados)
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            leitor.processar(self.banco, self.acervo)
        self.assertEqual(self.banco.paginas(sha)[1]["qualidade"], "OCR_INDISPONIVEL")
        self.assertEqual(self.banco.leituras()[0]["situacao"], "LIDA_COM_PENDENCIAS")

    def test_relatorio_de_validacao_nao_contem_texto_das_publicacoes(self):
        import json
        from observatorio.leitura import leitor, validacao
        sha = self.guardar(pdf_duas_colunas(paginas_extras=False), "https://exemplo.invalid/a.pdf", fonte="auniao")
        leitor.processar(self.banco, self.acervo)
        referencias = [{"data": "2026-05-08", "sha256": sha, "paginas": 1, "bytes": 1, "numero_edicao": "18585", "fonte_da_referencia": "teste"}]
        r = validacao.relatorio(self.banco, self.acervo, referencias)
        item = r["arquivos"][0]
        self.assertEqual(r["sistema"], "Painel de Publicações DOE-PB GEDIV")
        self.assertEqual((item["integridade_do_acervo"], item["edicao"], item["paginas"]["por_colunas"]),
                         (True, {"numero": "18585", "data": "2026-05-08"}, {"2": 1}))
        self.assertEqual(item["referencia"]["conferidos"], {"sha256": True, "bytes": False, "paginas": True, "numero_edicao": True})
        self.assertFalse(item["referencia"]["tudo_confere"])
        self.assertGreaterEqual(item["leitura_independente"]["cobertura_minima"], 0.95)
        texto = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("Fulano", texto)
        self.assertNotIn("PRC-2026", texto)


@unittest.skipUnless(TEM_OCR, "requer o programa Tesseract com o idioma português")
class TesteOcr(BaseLeitor):
    def test_pagina_digitalizada_e_lida_por_ocr_respeitando_as_colunas(self):
        from observatorio.leitura import leitor
        sha = self.guardar(pdf_digitalizado())
        leitor.processar(self.banco, self.acervo)
        pagina = self.banco.paginas(sha)[0]
        self.assertEqual((pagina["metodo"], pagina["colunas"]), ("OCR", 2))
        self.assertIn(pagina["qualidade"], ("OK", "BAIXA_CONFIANCA"))
        self.assertGreater(pagina["confianca"], 50)
        linhas = pagina["texto"].split("\n")
        self.assertFalse(any("Fulano" in l and "Beltrana" in l for l in linhas))
        self.assertGreaterEqual(sum("Fulano" in l for l in linhas), 27)                  # ao menos 90% das 30 linhas
        self.assertGreaterEqual(sum("Beltrana" in l for l in linhas), 27)
        ultima_esquerda = max(i for i, l in enumerate(linhas) if "Fulano" in l)
        primeira_direita = min(i for i, l in enumerate(linhas) if "Beltrana" in l)
        self.assertLess(ultima_esquerda, primeira_direita)
        self.assertIn("fictício", pagina["texto"])                                       # acentuação do português
        self.assertEqual(self.banco.leituras()[0]["data_edicao"], "2026-05-08")


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab")
class TesteFluxoManualCompleto(unittest.TestCase):
    def test_pdf_importado_percorre_integridade_leitura_e_validacao(self):
        import contextlib
        import json
        from observatorio.coleta.__main__ import main as coleta
        from observatorio.leitura.__main__ import main as leitura
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "entrada"
            entrada.mkdir()
            (entrada / "diario-oficial-08-05-2026-portal.pdf").write_bytes(pdf_duas_colunas(paginas_extras=False))
            (entrada / "diario-oficial-09-05-2026-portal.pdf").write_bytes(b"isto nao e um pdf" * 100)
            (entrada / "sem-data.pdf").write_bytes(pdf_duas_colunas(paginas_extras=False) + b"\n%x\n")
            dados = str(Path(pasta) / "dados")

            def rodar(funcao, *argumentos):
                with contextlib.redirect_stdout(io.StringIO()) as saida:
                    codigo = funcao([*argumentos, "--dados", dados])
                return codigo, saida.getvalue()

            codigo, saida = rodar(coleta, "importar", str(entrada))
            resultados = {r["arquivo"]: r for r in json.loads(saida)}
            self.assertEqual(codigo, 2)                                                 # houve recusas
            self.assertTrue(resultados["diario-oficial-08-05-2026-portal.pdf"]["aceito"])
            self.assertEqual(resultados["diario-oficial-09-05-2026-portal.pdf"]["motivo"], "SEM_ASSINATURA_PDF")
            self.assertEqual(resultados["sem-data.pdf"]["motivo"], "DATA_NAO_INFORMADA_NEM_NO_NOME")
            self.assertEqual(rodar(coleta, "conferir")[0], 0)
            self.assertEqual(rodar(leitura, "processar")[0], 0)
            _, saida = rodar(leitura, "validar")
            item = json.loads(saida)["arquivos"][0]
            self.assertEqual((item["origens"][0]["fonte"], item["origens"][0]["data"], item["edicao"]["data"], item["situacao"]),
                             ("manual", "2026-05-08", "2026-05-08", "LIDA"))
            _, saida = rodar(coleta, "progresso")
            progresso = json.loads(saida)
            self.assertEqual(progresso["sistema"], "Painel de Publicações DOE-PB GEDIV")
            self.assertEqual(progresso["cobertura"]["situacao"], "PARCIAL")              # importação manual não é acervo completo
            self.assertEqual(progresso["fontes"]["auniao"]["situacao"], "NAO_TESTADA")
            codigo, saida = rodar(leitura, "pagina", item["sha256"][:10], "1")
            self.assertIn("2 coluna(s)", saida)


class TesteNomeDoSistema(unittest.TestCase):
    def test_nome_oficial_exato(self):
        import observatorio
        raiz = Path(__file__).resolve().parents[1]
        self.assertEqual(observatorio.NOME, "Painel de Publicações DOE-PB GEDIV")
        self.assertEqual((raiz / "README.md").read_text(encoding="utf-8").splitlines()[0], "# Painel de Publicações DOE-PB GEDIV")
        for modulo in ("coleta", "leitura", "sonda"):
            texto = (raiz / "observatorio" / modulo / "__main__.py").read_text(encoding="utf-8")
            self.assertIn("Painel de Publicações DOE-PB GEDIV", texto.split("\n")[0])


if __name__ == "__main__":
    unittest.main()
