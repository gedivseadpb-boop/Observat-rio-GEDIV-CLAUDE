"""Etapa 05.3.4 — extração de PDFs difíceis, completude do OCR e classificação dos atos.

Cada teste descreve um DEFEITO da versão anterior (base 5442344) e o comportamento corrigido. Todos os dados são
SINTÉTICOS: nomes, matrículas e processos fictícios; nenhum PDF oficial é usado.

Grupos: A — geometria (tabelas e regiões da página); B — OCR e completude; C — continuidade entre páginas e colunas;
D — classificação (processo ausente, mérito por bloco, portarias, grupos e assuntos ambíguos); E — integração com o
banco e com a revisão da Etapa 05.3.3.
"""
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv import classificador as K
from observatorio.gerencias.gediv import processo as PROC
from observatorio.gerencias.gediv.classificador import classificar
from observatorio.leitura import ocr
from observatorio.leitura import pagina as PG
from observatorio.leitura.pagina import Palavra
from observatorio.nucleo.banco import Banco
from tests import textos_doe as T

TEM_PIL = importlib.util.find_spec("PIL") is not None
TEM_PDF = importlib.util.find_spec("pdfplumber") is not None and importlib.util.find_spec("reportlab") is not None
if TEM_PDF:
    from observatorio.leitura import leitor
    TEM_OCR = leitor.ocr_disponivel()[0]
else:
    TEM_OCR = False

CAB = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {n}/2026\n"
       "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS EXPEDIENTE DO DIA : 08-10-2026\n"
       "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n")
VERTICAL = CAB + "O Secretário DEFERIU os Processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo {grupo}:\n"


def um(texto):
    return classificar([(1, texto)], "arquivo-de-teste")


def celula(x, topo, texto, largura_letra=5.0):
    """Palavras de uma célula a partir de x, com espaço de 2 pt entre palavras."""
    palavras = []
    for parte in texto.split():
        palavras.append(Palavra(x, x + largura_letra * len(parte), topo, parte))
        x += largura_letra * len(parte) + 2
    return palavras


# ====================================================================================================================
# A — geometria
# ====================================================================================================================
class TesteLinhasDeTabelaPelaGeometria(unittest.TestCase):
    """Tabela: PROCESSO (x=40) | NOME (x=170) | CARGO (x=330) | CLASSES (x=480). Entrelinha 7 pt; 16 pt entre linhas."""

    COLUNAS = (40, 170, 330, 480)

    def linha(self, topo, *celulas):
        return [p for x, texto in zip(self.COLUNAS, celulas) if texto for p in celula(x, topo, texto)]

    def test_celulas_centradas_o_pedaco_de_cima_do_nome_fica_com_a_propria_pessoa(self):
        # DEFEITO: a 1ª metade do nome da pessoa DOIS, que fica ACIMA da linha do processo dela (célula centrada), era
        # lida como continuação da pessoa UM, e o cargo de UM recebia o começo do nome de DOIS.
        p = self.linha(100, "SAD-PSE-2026/90001", "PESSOA FICTICIA UM", "TECNICO ADMINISTRATIVO", "A B")
        p += self.linha(112.5, "", "PESSOA FICTICIA", "ANALISTA DE")                    # acima do processo de DOIS
        p += self.linha(116, "SAD-PSE-2026/90002", "", "", "C D")
        p += self.linha(119.5, "", "DOIS DA SILVA", "SISTEMAS")
        p += self.linha(135, "SAD-PSE-2026/90003", "PESSOA FICTICIA TRES", "AUXILIAR DE SERVICOS", "B C")
        p += self.linha(151, "SAD-PSE-2026/90004", "PESSOA FICTICIA QUATRO", "MOTORISTA", "D E")
        leitura = PG.ler_pagina_detalhada(p, 595)
        self.assertEqual(leitura.texto.split("\n"), [
            "SAD-PSE-2026/90001 PESSOA FICTICIA UM TECNICO ADMINISTRATIVO A B",
            "SAD-PSE-2026/90002 PESSOA FICTICIA DOIS DA SILVA ANALISTA DE SISTEMAS C D",
            "SAD-PSE-2026/90003 PESSOA FICTICIA TRES AUXILIAR DE SERVICOS B C",
            "SAD-PSE-2026/90004 PESSOA FICTICIA QUATRO MOTORISTA D E"])
        self.assertEqual((leitura.linhas_reconstruidas, leitura.linhas_ambiguas), (2, 0))
        r = um(VERTICAL.format(n=910, grupo="GAJ") + leitura.texto + "\nPUBLIQUE-SE")
        self.assertEqual([(d.servidor, d.cargo, d.detalhe.get("classe_anterior"), d.detalhe.get("classe_posterior")) for d in r.decisoes],
                         [("PESSOA FICTICIA UM", "TECNICO ADMINISTRATIVO", "A", "B"),
                          ("PESSOA FICTICIA DOIS DA SILVA", "ANALISTA DE SISTEMAS", "C", "D"),
                          ("PESSOA FICTICIA TRES", "AUXILIAR DE SERVICOS", "B", "C"),
                          ("PESSOA FICTICIA QUATRO", "MOTORISTA", "D", "E")])

    def test_celulas_no_alto_a_continuacao_fica_com_a_pessoa_de_cima(self):
        p = self.linha(100, "SAD-PSE-2026/90001", "PESSOA FICTICIA UM DOS", "TECNICO", "A B")
        p += self.linha(107, "", "SANTOS", "ADMINISTRATIVO")
        p += self.linha(123, "SAD-PSE-2026/90002", "PESSOA FICTICIA DOIS", "MOTORISTA", "C D")
        p += self.linha(139, "SAD-PSE-2026/90003", "PESSOA FICTICIA TRES", "AUXILIAR", "B C")
        linhas = PG.ler_pagina(p, 595)[0].split("\n")
        self.assertEqual(linhas[0], "SAD-PSE-2026/90001 PESSOA FICTICIA UM DOS SANTOS TECNICO ADMINISTRATIVO A B")
        self.assertEqual(len(linhas), 3)

    def test_geometria_indecisa_marca_a_linha_e_vira_pendencia_sem_colar_a_ninguem(self):
        # Indícios CONTRADITÓRIOS no mesmo trecho (um fragmento mais perto da linha de cima, outro da de baixo) e um
        # fragmento exatamente a meio caminho: não é atribuído; sai marcado e a decisão vizinha fica com pendência.
        p = self.linha(100, "SAD-PSE-2026/90001", "PESSOA FICTICIA UM", "TECNICO", "A B")
        p += self.linha(105, "", "DE SOUZA", "ADMINISTRATIVO")                  # claramente da linha de cima
        p += self.linha(120, "SAD-PSE-2026/90002", "PESSOA FICTICIA DOIS", "MOTORISTA", "C D")
        p += self.linha(130, "", "FRAGMENTO INCERTO", "")                       # a 10 pt de cada linha
        p += self.linha(140, "SAD-PSE-2026/90003", "PESSOA FICTICIA TRES", "AUXILIAR", "B C")
        p += self.linha(152, "", "DE LIMA", "")                                 # claramente da linha de baixo
        p += self.linha(160, "SAD-PSE-2026/90004", "PESSOA FICTICIA QUATRO", "AGENTE", "D E")
        leitura = PG.ler_pagina_detalhada(p, 595)
        self.assertEqual(leitura.linhas_ambiguas, 1)
        marcadas = [l for l in leitura.texto.split("\n") if l.startswith(PG.MARCA_AMBIGUA)]
        self.assertEqual(marcadas, [f"{PG.MARCA_AMBIGUA} FRAGMENTO INCERTO"])
        r = um(VERTICAL.format(n=911, grupo="GAJ") + leitura.texto + "\nPUBLIQUE-SE")
        por_processo = {d.processo[-5:]: d for d in r.decisoes}
        self.assertEqual(por_processo["90002"].servidor, "PESSOA FICTICIA DOIS")            # nada foi colado
        self.assertEqual(por_processo["90003"].servidor, "PESSOA FICTICIA TRES")
        for processo in ("90002", "90003"):
            self.assertTrue(any("sem atribuição segura" in x for x in por_processo[processo].detalhe["pendencias"]), processo)
        self.assertNotIn("pendencias", por_processo["90001"].detalhe)
        self.assertTrue(any("sem atribuição segura" in x for x in r.atos[0].pendencias))

    def test_grade_vetorial_define_a_linha_da_tabela(self):
        # Sem entrelinha que ajude (tudo a 8 pt), as réguas da grade dizem a que linha cada fragmento pertence.
        p = self.linha(100, "SAD-PSE-2026/90001", "PESSOA FICTICIA UM", "TECNICO", "A B")
        p += self.linha(108, "", "DE SOUZA", "ADMINISTRATIVO")
        p += self.linha(116, "", "PESSOA FICTICIA", "ANALISTA")
        p += self.linha(124, "SAD-PSE-2026/90002", "DOIS", "", "C D")
        p += self.linha(132, "SAD-PSE-2026/90003", "PESSOA FICTICIA TRES", "AUXILIAR", "B C")
        reguas = [(y, 38.0, 520.0) for y in (98.0, 114.5, 130.5, 140.0)]
        linhas = PG.ler_pagina(p, 595, reguas)[0].split("\n")
        self.assertEqual(linhas, ["SAD-PSE-2026/90001 PESSOA FICTICIA UM DE SOUZA TECNICO ADMINISTRATIVO A B",
                                  "SAD-PSE-2026/90002 PESSOA FICTICIA DOIS ANALISTA C D",
                                  "SAD-PSE-2026/90003 PESSOA FICTICIA TRES AUXILIAR B C"])

    def test_reguas_que_so_contornam_a_tabela_nao_fundem_as_linhas(self):
        # Achado na regressão com PDFs oficiais (11/11/2026, resenha 583): réguas só no contorno; cada linha continua uma.
        p = []
        for i in range(4):
            p += self.linha(100 + 12 * i, f"SAD-PSE-2026/9000{i}", f"PESSOA FICTICIA {i}", "TECNICO ADMINISTRATIVO", "A B")
        linhas = PG.ler_pagina(p, 595, [(98.0, 38.0, 520.0), (150.0, 38.0, 520.0)])[0].split("\n")
        self.assertEqual(len(linhas), 4)

    def test_titulo_e_publique_se_depois_da_tabela_nunca_sao_absorvidos(self):
        # Achado na regressão com PDFs oficiais: o cabeçalho da resenha seguinte, logo abaixo da tabela, não é fragmento.
        p = []
        for i in range(4):
            p += self.linha(100 + 9 * i, f"SAD-PSE-2026/9000{i}", f"PESSOA FICTICIA {i}", "TECNICO", "A B")
        p += celula(40, 136, "PUBLIQUE-SE")
        p += celula(170, 145, "RESENHA SEGUINTE")
        linhas = PG.ler_pagina(p, 595)[0].split("\n")
        self.assertEqual(linhas[-2:], ["PUBLIQUE-SE", "RESENHA SEGUINTE"])
        self.assertEqual(len(linhas), 6)


class TesteRegioesDaPagina(unittest.TestCase):
    def pagina(self):
        """Duas colunas de texto (corredor em x≈297), com uma tabela de LARGURA TOTAL no meio. Na 2ª linha da tabela o
        vão entre duas células cai sobre o corredor."""
        p = []
        for i in range(10):
            p += celula(40, 40 + 10 * i, f"E{i:02d} texto corrido da coluna esquerda") + celula(310, 40 + 10 * i, f"D{i:02d} texto corrido da coluna direita")
        p += celula(40, 150, "PROC-A") + celula(120, 150, "NOME A QUE ATRAVESSA O CORREDOR CENTRAL DA PAGINA") + celula(420, 150, "CARGO-A") + celula(520, 150, "A B")
        p += celula(40, 160, "PROC-B") + celula(120, 160, "NOME B CURTO") + celula(420, 160, "CARGO-B") + celula(520, 160, "C D")
        p += celula(40, 170, "PROC-C") + celula(120, 170, "NOME C QUE ATRAVESSA O CORREDOR CENTRAL DA PAGINA") + celula(420, 170, "CARGO-C") + celula(520, 170, "E F")
        for i in range(10):
            p += celula(40, 190 + 10 * i, f"F{i:02d} texto corrido da coluna esquerda") + celula(310, 190 + 10 * i, f"G{i:02d} texto corrido da coluna direita")
        return p

    def test_linha_de_tabela_larga_nao_e_partida_pelo_corredor(self):
        # DEFEITO: "PROC-B NOME B CURTO" ia para a coluna esquerda e "CARGO-B C D" para a direita, longe da pessoa.
        leitura = PG.ler_pagina_detalhada(self.pagina(), 595)
        linhas = leitura.texto.split("\n")
        self.assertEqual(leitura.colunas, 2)
        self.assertIn("PROC-B NOME B CURTO CARGO-B C D", linhas)
        self.assertEqual(leitura.regioes_suavizadas, 1)
        i = linhas.index("PROC-B NOME B CURTO CARGO-B C D")
        self.assertTrue(linhas[i - 1].startswith("PROC-A") and linhas[i + 1].startswith("PROC-C"))

    def test_ordem_de_leitura_das_regioes_e_preservada(self):
        marcas = [l[:3] for l in PG.ler_pagina(self.pagina(), 595)[0].split("\n")]
        esperado = ([f"E{i:02d}" for i in range(10)] + [f"D{i:02d}" for i in range(10)] + ["PRO"] * 3
                    + [f"F{i:02d}" for i in range(10)] + [f"G{i:02d}" for i in range(10)])
        self.assertEqual(marcas, esperado)

    def test_duas_linhas_de_texto_em_colunas_entre_titulos_continuam_em_colunas(self):
        # A regra só vale para linhas ALINHADAS às células das vizinhas: texto em colunas não é confundido com tabela.
        p = []
        for i in range(10):
            p += celula(40, 40 + 10 * i, f"E{i:02d} texto da esquerda") + celula(310, 40 + 10 * i, f"D{i:02d} texto da direita")
        p += celula(100, 150, "TITULO DE LARGURA TOTAL QUE ATRAVESSA O CORREDOR CENTRAL DA PAGINA INTEIRA")
        p += celula(40, 160, "X01 esquerda") + celula(310, 160, "Y01 direita")
        p += celula(40, 170, "X02 esquerda") + celula(310, 170, "Y02 direita")
        p += celula(100, 180, "OUTRO TITULO DE LARGURA TOTAL QUE ATRAVESSA O CORREDOR CENTRAL DA PAGINA")
        marcas = [l[:3] for l in PG.ler_pagina(p, 595)[0].split("\n")]
        self.assertEqual(marcas[20:], ["TIT", "X01", "X02", "Y01", "Y02", "OUT"])


# ====================================================================================================================
# B — OCR e completude
# ====================================================================================================================
class TesteFontesComMapeamentoErrado(unittest.TestCase):
    def caracteres(self, texto, fonte):
        return [{"text": c, "fontname": fonte, "x0": 10 + 5 * i, "x1": 14 + 5 * i, "top": 10, "bottom": 18} for i, c in enumerate(texto)]

    def test_fonte_sem_vogais_ou_cheia_de_sinais_e_suspeita_e_texto_normal_nao(self):
        # DEFEITO: só o sinal "(cid:N)" denunciava a fonte sem mapeamento; letras trocadas passavam como texto íntegro.
        normal = self.caracteres("SAD-PSE-2026/90001 900001-1 PESSOA FICTICIA UM TECNICO ADMINISTRATIVO A B", "Normal")
        trocada = self.caracteres("XTK-RXJ-7571/45556 HJXXTB KNHYNHNB ZR YJHSNHT BKRNSNXYWBYNDT", "Trocada")
        sinais = self.caracteres("¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿×÷ ¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½", "Sinais")
        siglas = self.caracteres("SAD PSE GS", "Curta")                                   # pouca letra: não se julga
        self.assertEqual(leitor_fontes(normal + trocada + sinais + siglas), {"Trocada", "Sinais"})

    @unittest.skipUnless(TEM_PDF, "requer pdfplumber")
    def test_palavras_da_fonte_suspeita_passam_a_ser_ilegiveis(self):
        class Pagina:
            chars = self.caracteres("XTKRXJ HJXXTB KNHYNHNB ZRYJHSNHT BKRNSNXYWBYNDT XTKRXJ HJXXTB", "Trocada")
        brutas = [{"text": "XTKRXJ", "x0": 10, "x1": 39, "top": 10, "bottom": 18},
                  {"text": "Diário", "x0": 400, "x1": 430, "top": 10, "bottom": 18}]
        self.assertEqual(leitor._marcar_fontes_suspeitas(Pagina, brutas), 1)
        self.assertTrue(leitor._CORROMPIDO.search(brutas[0]["text"]))
        self.assertEqual(brutas[1]["text"], "Diário")


def leitor_fontes(caracteres):
    from observatorio.leitura import leitor as L
    return L.fontes_suspeitas(caracteres)


@unittest.skipUnless(TEM_PIL and TEM_PDF, "requer Pillow e pdfplumber")
class TesteLinhasQueOcrNaoLeu(unittest.TestCase):
    def imagem(self, linhas):
        """Imagem 600x300 com 'linhas de texto' (sequências de tracinhos) e uma régua. linhas: [(y, x0, x1)]."""
        from PIL import Image, ImageDraw
        imagem = Image.new("L", (600, 300), 255)
        desenho = ImageDraw.Draw(imagem)
        for y, x0, x1 in linhas:
            for x in range(x0, x1, 12):
                desenho.rectangle((x, y, x + 7, y + 14), fill=0)
        desenho.line((20, 280, 580, 280), fill=0, width=2)                    # régua: tinta, mas não é texto
        return imagem

    def test_linha_com_tinta_e_sem_palavra_e_apontada(self):
        # DEFEITO: o OCR devolvia a página sem uma linha e ninguém percebia (confiança média alta nas demais).
        imagem = self.imagem([(40, 30, 560), (80, 30, 560), (120, 30, 560)])
        caixas = [(30, 40, 560, 54), (30, 120, 560, 134)]                     # o OCR "leu" a 1ª e a 3ª linhas
        self.assertEqual([(y0, y1) for _, y0, _, y1 in leitor.faixas_sem_leitura(imagem, caixas)], [(80, 95)])

    def test_linha_perdida_so_numa_coluna_e_apontada_e_regua_nao(self):
        imagem = self.imagem([(40, 30, 270), (40, 330, 560), (80, 30, 270), (80, 330, 560)])
        caixas = [(30, 40, 270, 54), (330, 40, 560, 54), (30, 80, 270, 94)]   # falta a linha de baixo da coluna direita
        faltando = leitor.faixas_sem_leitura(imagem, caixas)
        self.assertEqual(len(faltando), 1)
        self.assertGreaterEqual(faltando[0][0], 320)

    def test_pagina_inteira_lida_nao_tem_falta(self):
        imagem = self.imagem([(40, 30, 560), (80, 30, 560)])
        self.assertEqual(leitor.faixas_sem_leitura(imagem, [(30, 40, 560, 54), (30, 80, 560, 94)]), [])

    def test_linha_que_continua_sem_leitura_deixa_a_pagina_pendente(self):
        palavras = [Palavra(10, 60, 20, "texto"), Palavra(70, 120, 20, "lido")]
        self.assertEqual(leitor._classificar_ocr(1, palavras, 91.0, 595, sem_leitura=0)["qualidade"], "OK")
        pendente = leitor._classificar_ocr(1, palavras, 91.0, 595, sem_leitura=1)
        self.assertEqual(pendente["qualidade"], "LEITURA_INCOMPLETA")
        self.assertIn("texto lido", pendente["texto"])                        # o que foi lido é guardado


@unittest.skipUnless(TEM_PDF and TEM_OCR, "requer pdfplumber, reportlab e Tesseract com português")
class TesteRegiaoSemTextoEOcrCompleto(unittest.TestCase):
    def pdf(self, desenhar):
        from reportlab.pdfgen import canvas
        memoria = io.BytesIO()
        c = canvas.Canvas(memoria, pagesize=(595, 842))
        desenhar(c)
        c.save()
        return memoria.getvalue()

    def figura_com_texto(self, linhas, tamanho=(1200, 300)):
        from PIL import Image, ImageDraw, ImageFont
        imagem = Image.new("RGB", tamanho, "white")
        desenho = ImageDraw.Draw(imagem)
        try:
            fonte = ImageFont.truetype("DejaVuSans.ttf", 40)
        except OSError:
            self.skipTest("fonte DejaVuSans indisponível para desenhar a figura")
        for i, linha in enumerate(linhas):
            desenho.text((20, 20 + 70 * i), linha, fill="black", font=fonte)
        return imagem

    def test_tabela_colada_como_figura_pequena_e_lida_so_na_regiao(self):
        # DEFEITO: imagens abaixo de 25% da página nunca eram examinadas; o texto delas simplesmente não existia.
        from reportlab.lib.utils import ImageReader
        figura = self.figura_com_texto(["SAD-PSE-2026/90001 PESSOA FICTICIA UM", "SAD-PSE-2026/90002 PESSOA FICTICIA DOIS"])

        def desenhar(c):
            c.setFont("Helvetica", 10)
            for i in range(12):
                c.drawString(40, 800 - 14 * i, f"Linha {i:02d} de texto nativo do Diario Oficial, acima da figura.")
            c.drawImage(ImageReader(figura), 40, 480, width=400, height=100)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(self.pdf(desenhar))) as d:
            self.assertLess(leitor._fracao_coberta_por_imagens(d.pages[0]), leitor.FRACAO_IMAGEM_MISTA)
            pagina = leitor._ler_uma_pagina(1, d.pages[0])
        self.assertEqual(pagina["metodo"], "TEXTO+OCR")
        self.assertIn("Linha 00 de texto nativo", pagina["texto"])
        self.assertRegex(pagina["texto"], r"90001 PESSOA FICTICIA UM")
        self.assertRegex(pagina["texto"], r"90002 PESSOA FICTICIA DOIS")

    def test_figura_sem_texto_nao_muda_a_pagina(self):
        from PIL import Image, ImageDraw
        from reportlab.lib.utils import ImageReader
        figura = Image.new("RGB", (600, 300), "white")
        ImageDraw.Draw(figura).ellipse((150, 30, 450, 270), fill="navy")

        def desenhar(c):
            c.setFont("Helvetica", 10)
            for i in range(12):
                c.drawString(40, 800 - 14 * i, f"Linha {i:02d} de texto nativo do Diario Oficial.")
            c.drawImage(ImageReader(figura), 40, 480, width=300, height=150)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(self.pdf(desenhar))) as d:
            pagina = leitor._ler_uma_pagina(1, d.pages[0])
        self.assertEqual((pagina["metodo"], pagina["qualidade"]), ("TEXTO", "OK"))

    def test_pagina_digitalizada_e_lida_inteira_e_fica_ok(self):
        from reportlab.lib.utils import ImageReader
        figura = self.figura_com_texto([f"Linha {i} do documento digitalizado" for i in range(1, 9)], (1200, 620))
        import pdfplumber
        with pdfplumber.open(io.BytesIO(self.pdf(lambda c: c.drawImage(ImageReader(figura), 40, 400, width=500, height=258)))) as d:
            pagina = leitor._ler_uma_pagina(1, d.pages[0])
        self.assertEqual((pagina["metodo"], pagina["qualidade"]), ("OCR", "OK"))
        for i in range(1, 9):
            self.assertRegex(pagina["texto"], rf"Linha {i} do documento")


class TesteLimitesDoOcr(unittest.TestCase):
    def setUp(self):
        ocr.iniciar_arquivo()
        self.addCleanup(ocr.iniciar_arquivo)

    def test_limite_de_chamadas_por_pagina(self):
        # DEFEITO: só havia limite por CHAMADA; uma página com dezenas de trechos não tinha teto.
        with mock.patch.dict(os.environ, {"GEDIV_OCR_CHAMADAS_PAGINA": "2"}):
            for _ in range(2):
                self.assertEqual(ocr._chamar(lambda imagem, timeout: "ok", None), "ok")
            with self.assertRaises(ocr.OcrEsgotado):
                ocr._chamar(lambda imagem, timeout: "ok", None)
            ocr.iniciar_pagina()                                               # página seguinte: a conta recomeça
            self.assertEqual(ocr._chamar(lambda imagem, timeout: "ok", None), "ok")

    def test_limite_de_tempo_por_pagina_e_por_arquivo(self):
        with mock.patch.dict(os.environ, {"GEDIV_OCR_TEMPO_PAGINA": "10", "GEDIV_OCR_TEMPO_ARQUIVO": "25"}):
            ocr._uso["pagina"] = ocr._uso["arquivo"] = 10.0
            with self.assertRaisesRegex(ocr.OcrEsgotado, "por página"):
                ocr._chamar(lambda imagem, timeout: "ok", None)
            ocr.iniciar_pagina()
            ocr._uso["arquivo"] = 25.0                                         # outra página, arquivo já no teto
            with self.assertRaisesRegex(ocr.OcrEsgotado, "por arquivo"):
                ocr._chamar(lambda imagem, timeout: "ok", None)

    def test_a_chamada_recebe_so_o_tempo_que_resta(self):
        vistos = []
        with mock.patch.dict(os.environ, {"GEDIV_OCR_TEMPO_PAGINA": "50", "GEDIV_OCR_TEMPO_MAXIMO": "120"}):
            ocr._uso["pagina"] = 45.0
            ocr._chamar(lambda imagem, timeout: vistos.append(timeout), None)
        self.assertAlmostEqual(vistos[0], 5.0, places=3)

    @unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab")
    def test_estouro_vira_pagina_pendente_e_o_arquivo_segue(self):
        from reportlab.pdfgen import canvas
        memoria = io.BytesIO()
        c = canvas.Canvas(memoria, pagesize=(595, 842))
        for n in range(2):
            c.setFont("Helvetica", 10)
            for i in range(6):
                c.drawString(40, 800 - 14 * i, f"Pagina {n + 1}, linha {i} de texto nativo do Diario Oficial.")
            c.showPage()
        c.save()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "x.pdf"
            caminho.write_bytes(memoria.getvalue())
            original = leitor._ler_uma_pagina

            def estoura_na_primeira(numero, pagina):
                if numero == 1:
                    raise ocr.OcrEsgotado("limite de tempo de OCR por página atingido")
                return original(numero, pagina)
            with mock.patch.object(leitor, "_ler_uma_pagina", estoura_na_primeira):
                paginas = leitor.ler_arquivo(caminho)["paginas"]
        self.assertEqual([p["qualidade"] for p in paginas], ["OCR_ESGOTADO", "OK"])
        self.assertIn("Pagina 1, linha 0", paginas[0]["texto"])                # o texto nativo é guardado


# ====================================================================================================================
# C — continuidade entre páginas e colunas
# ====================================================================================================================
class TesteContinuidade(unittest.TestCase):
    def test_cabecalho_repetido_na_pagina_seguinte_e_o_mesmo_ato(self):
        # DEFEITO: "RESENHA Nº 902/2026 (continuação)" no alto da página seguinte abria um SEGUNDO ato com o mesmo número.
        linhas = T.HORIZONTAL_GAJ.split("\n")
        repetido = "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : 902/2026 /DEREH/GS (continuação)"
        r = classificar([(3, "\n".join(linhas[:8])), (4, repetido + "\n" + "\n".join(linhas[8:]))], "x")
        self.assertEqual([(a.numero, a.pagina, a.pagina_final) for a in r.atos], [("902/2026", 3, 4)])
        self.assertEqual([d.pagina for d in r.decisoes], [3, 4, 4])
        self.assertEqual(len({d.ato_id for d in r.decisoes}), 1)               # todas ligadas ao ato original
        self.assertFalse(any("continuidade duvidosa" in p for p in r.atos[0].pendencias))

    def test_mesmo_numero_depois_do_publique_se_continua_sendo_outro_ato(self):
        r = classificar([(3, T.HORIZONTAL_GAJ), (4, T.HORIZONTAL_GAJ)], "x")
        self.assertEqual(len(r.atos), 2)

    def test_republicacao_com_o_mesmo_numero_nao_e_continuacao(self):
        linhas = T.HORIZONTAL_GAJ.split("\n")
        r = classificar([(3, "\n".join(linhas[:9])), (4, linhas[0] + "\nREPUBLICADA POR INCORREÇÃO\n" + "\n".join(linhas[1:]))], "x")
        self.assertEqual(len(r.atos), 2)

    def test_linha_repetida_no_alto_da_pagina_seguinte_conta_uma_vez(self):
        # DEFEITO: a última linha da tabela, repetida no começo da página seguinte, virava duas decisões.
        linhas = T.HORIZONTAL_GAJ.split("\n")
        r = classificar([(3, "\n".join(linhas[:8])), (4, linhas[7] + "\n" + "\n".join(linhas[8:]))], "x")
        self.assertEqual([d.processo[-5:] for d in r.decisoes], ["90003", "90004", "90004"])
        self.assertTrue(any("repetida na continuação" in p for p in r.decisoes[0].detalhe["pendencias"]))

    def test_mesmo_processo_para_duas_pessoas_na_mesma_pagina_nao_e_duplicidade(self):
        r = um(T.HORIZONTAL_GAJ)
        self.assertEqual([(d.processo[-5:], d.matricula) for d in r.decisoes][1:], [("90004", "900004-6"), ("90004", "900005-4")])

    def test_continuidade_duvidosa_gera_pendencia_com_o_motivo(self):
        linhas = T.HORIZONTAL_GAJ.split("\n")
        # preâmbulo numa página e TODAS as linhas na seguinte: não há linha de processo na primeira página
        r = classificar([(3, "\n".join(linhas[:7])), (4, "\n".join(linhas[7:]))], "x")
        self.assertTrue(any("continuidade duvidosa (sem linhas de processo na página 3)" in p for p in r.atos[0].pendencias))
        self.assertEqual(len(r.decisoes), 3)                                   # as decisões são preservadas


# ====================================================================================================================
# D — classificação
# ====================================================================================================================
class TesteDecisaoSemProcesso(unittest.TestCase):
    TEXTO = VERTICAL.format(n=920, grupo="GAJ") + (
        "Processo Matricula Nome Cargo Classe P/Classe\n"
        "SAD-PSE-2026/90011 900011-1 PESSOA FICTICIA ONZE TECNICO ADMINISTRATIVO A B\n"
        "900012-2 PESSOA FICTICIA DOZE TECNICO ADMINISTRATIVO B C\n"
        "SAD-PSE-2O26/9OO13 900013-3 PESSOA FICTICIA TREZE AUXILIAR DE SERVICOS C D\n"
        "SAD-PSE-2026/90014 900014-4 PESSOA FICTICIA QUATORZE MOTORISTA D E\n"
        "PUBLIQUE-SE")

    def test_linha_sem_processo_e_preservada_sem_numero_presumido(self):
        # DEFEITO: só linhas com processo reconhecido viravam decisão; as demais eram coladas à pessoa de cima e sumiam.
        r = um(self.TEXTO)
        self.assertEqual([(d.processo, d.matricula, d.servidor) for d in r.decisoes], [
            ("SAD-PSE-2026/90011", "900011-1", "PESSOA FICTICIA ONZE"), (None, "900012-2", "PESSOA FICTICIA DOZE"),
            (None, "900013-3", "PESSOA FICTICIA TREZE"), ("SAD-PSE-2026/90014", "900014-4", "PESSOA FICTICIA QUATORZE")])
        self.assertEqual([d.cargo for d in r.decisoes][:2], ["TECNICO ADMINISTRATIVO", "TECNICO ADMINISTRATIVO"])   # nada colado em ONZE
        self.assertEqual([d.detalhe.get("classe_posterior") for d in r.decisoes], ["B", "C", "D", "E"])
        self.assertEqual(len({d.id for d in r.decisoes}), 4)

    def test_pendencia_na_decisao_e_no_ato_com_a_grafia_publicada(self):
        r = um(self.TEXTO)
        self.assertNotIn("pendencias", r.decisoes[0].detalhe)
        self.assertTrue(any("processo não reconhecido" in p for p in r.decisoes[1].detalhe["pendencias"]))
        self.assertTrue(any("grafia publicada: SAD-PSE-2O26/9OO13" in p for p in r.decisoes[2].detalhe["pendencias"]))
        self.assertTrue(any("2 decisão(ões) sem processo reconhecido" in p for p in r.atos[0].pendencias))

    def test_texto_do_preambulo_nunca_vira_decisao(self):
        texto = CAB.format(n=921) + ("O Diretor DEFERIU a ANOTAÇÃO DE TEMPO DE SERVIÇO requerida pelo servidor de matrícula\n"
                                     "900021-1 PESSOA FICTICIA VINTE E UM, conforme os processos:\n"
                                     "SEC.EST.SAUDE SAD-PSE-2026/90022 9000022 PESSOA FICTICIA VINTE E DOIS 0 0 0 100\nPUBLIQUE-SE")
        self.assertEqual([d.processo for d in um(texto).decisoes], ["SAD-PSE-2026/90022"])

    def test_decisao_sem_processo_e_gravada_e_fica_na_fila_de_revisao(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = Banco(Path(pasta) / "o.sqlite3")
            try:
                sha = "a" * 64
                banco.con.execute("INSERT INTO arquivo VALUES (?, 10, 'x', 'agora')", (sha,))
                banco.registrar_leitura(sha, "LIDA", "t", [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": self.TEXTO,
                                                               "palavras": 50, "qualidade": "OK"}], "18700", "2026-10-08", None)
                PROC.classificar_pendentes(banco)
                linhas = banco.con.execute("SELECT processo, matricula, validacao, vigente, chave_logica FROM decisao ORDER BY rowid").fetchall()
                self.assertEqual([l["processo"] for l in linhas], ["SAD-PSE-2026/90011", None, None, "SAD-PSE-2026/90014"])
                self.assertEqual({l["validacao"] for l in linhas}, {"PENDENTE"})                 # fila de revisão da 05.3.3
                self.assertTrue(linhas[1]["chave_logica"].endswith("|M:9000122"))                 # identidade pela matrícula
                self.assertEqual({l["vigente"] for l in linhas}, {1})
            finally:
                banco.fechar()


class TesteMeritoPorBloco(unittest.TestCase):
    MISTA = CAB.format(n=930) + (
        "O Diretor resolve DEFERIR e INDEFERIR os Processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo GAJ, conforme abaixo:\n"
        "DEFERIDOS:\n"
        "SAD-PSE-2026/90031 900031-1 PESSOA FICTICIA TRINTA E UM TECNICO ADMINISTRATIVO A B\n"
        "SAD-PSE-2026/90032 900032-2 PESSOA FICTICIA TRINTA E DOIS TECNICO ADMINISTRATIVO B C\n"
        "INDEFERIDOS:\n"
        "SAD-PSE-2026/90033 900033-3 PESSOA FICTICIA TRINTA E TRES MOTORISTA C D\n"
        "PUBLIQUE-SE")

    def test_cada_bloco_tem_o_seu_resultado(self):
        # DEFEITO: a linha logo acima de "INDEFERIDOS:" absorvia o título e virava INDEFERIDO; as demais, NAO_INFORMADO.
        r = um(self.MISTA)
        self.assertEqual([(d.processo[-5:], d.resultado) for d in r.decisoes],
                         [("90031", "DEFERIDO"), ("90032", "DEFERIDO"), ("90033", "INDEFERIDO")])
        self.assertEqual(r.atos[0].resultado, "NAO_INFORMADO")                 # o ato inteiro não é generalizado
        self.assertEqual(r.decisoes[0].detalhe["resultado_do_bloco"], "DEFERIDO")
        self.assertEqual(r.decisoes[1].cargo, "TECNICO ADMINISTRATIVO")        # o título não entrou no cargo

    def test_resultado_na_propria_linha_prevalece_sobre_o_bloco(self):
        texto = self.MISTA.replace("MOTORISTA C D", "MOTORISTA C D DEFERIDO")
        self.assertEqual(um(texto).decisoes[2].resultado, "DEFERIDO")

    def test_ato_misto_sem_indicacao_por_linha_nao_e_resolvido_e_vai_para_revisao(self):
        texto = self.MISTA.replace("DEFERIDOS:\n", "").replace("INDEFERIDOS:\n", "").replace("IN\n", "")
        r = um(texto)
        self.assertEqual({d.resultado for d in r.decisoes}, {"NAO_INFORMADO"})
        self.assertTrue(all(any("resultado misto" in p for p in d.detalhe["pendencias"]) for d in r.decisoes))
        self.assertTrue(any("resultado misto" in p for p in r.atos[0].pendencias))

    def test_ato_de_um_so_resultado_continua_como_antes(self):
        r = um(T.INDEFERIDA_MAG)
        self.assertEqual({d.resultado for d in r.decisoes}, {"INDEFERIDO"})
        self.assertNotIn("pendencias", r.decisoes[0].detalhe)


class TestePortarias(unittest.TestCase):
    CORPO = ("O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, no uso de suas atribuições, RESOLVE designar a servidora\n"
             "PESSOA FICTICIA QUARENTA, matrícula 900040-1, para compor a comissão de avaliação.\nPUBLIQUE-SE")

    def test_numero_na_linha_seguinte_e_unidade_na_linha_anterior(self):
        # DEFEITO: "PORTARIA Nº" numa linha e o número na seguinte não era reconhecida; e a GEDIV, no cabeçalho ACIMA
        # da portaria, ficava fora do ato (a portaria era descartada como "sem vínculo").
        texto = ("GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\nPORTARIA Nº\n041/2026-GEDIV\n" + self.CORPO)
        r = um(texto)
        self.assertEqual([(o.tipo, o.vinculo) for o in r.outras], [("PORTARIA", K.EXPRESSO)])
        self.assertIn("Portaria nº 41/2026", r.outras[0].titulo)
        self.assertIn("GEDIV", r.outras[0].titulo)                             # o sufixo é guardado

    def test_portaria_so_com_a_palavra_numa_linha(self):
        r = um("DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nGERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\nPORTARIA\nNº 042/2026\n" + self.CORPO)
        self.assertEqual([o.tipo for o in r.outras], ["PORTARIA"])

    def test_portaria_depois_do_nome_da_unidade_na_mesma_linha(self):
        r = um("GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS PORTARIA Nº 043/2026\n" + self.CORPO)
        self.assertEqual([o.titulo for o in r.outras], ["Portaria nº 43/2026"])

    def test_citacao_de_portaria_no_texto_nao_abre_ato(self):
        r = um(T.ANOTACAO)                                                     # "outorgada pela Portaria nº 2374/GS"
        self.assertEqual([o.tipo for o in r.outras], [])
        self.assertEqual(len(r.atos), 1)

    def test_portaria_so_da_dereh_tem_destino_com_vinculo_nao_expresso(self):
        # DEFEITO: portaria da DEREH sem a GEDIV expressa era descartada sem registro.
        r = um("DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nPORTARIA Nº 044/2026-DEREH\n" + self.CORPO)
        self.assertEqual([(o.tipo, o.vinculo) for o in r.outras], [("PORTARIA", K.NAO_EXPRESSO)])
        self.assertEqual((r.atos, r.decisoes), ([], []))

    def test_portaria_com_assunto_de_progressao_nao_vira_decisao(self):
        # DEFEITO: portaria da GEDIV que tratava de progressão não ia para lugar nenhum (nem decisão, nem "Outras").
        texto = ("GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\nPORTARIA Nº 045/2026-GEDIV\n"
                 "O DIRETOR RESOLVE estabelecer o calendário dos processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo GAJ:\n"
                 "SAD-PSE-2026/90045 900045-5 PESSOA FICTICIA QUARENTA E CINCO TECNICO ADMINISTRATIVO A B\nPUBLIQUE-SE")
        r = um(texto)
        self.assertEqual((r.atos, r.decisoes), ([], []))
        self.assertEqual([o.tipo for o in r.outras], ["PORTARIA"])
        self.assertIn("Progressão Funcional (indício; não convertida em decisão)", r.outras[0].titulo)

    def test_portaria_de_outra_secretaria_ou_gerencia_continua_fora(self):
        r = um("SECRETARIA DE ESTADO DA SAÚDE\nPORTARIA Nº 046/2026\nO SECRETÁRIO RESOLVE designar servidor.\nPUBLIQUE-SE")
        self.assertEqual(r.outras, [])
        r = um("DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nGERÊNCIA OPERACIONAL DE CESSÃO DE PESSOAL\nPORTARIA Nº 047/2026\n" + self.CORPO)
        self.assertEqual(r.outras, [])

    def test_portaria_tornada_sem_efeito_continua_evento(self):
        r = um(T.PORTARIA_SEM_EFEITO)
        self.assertEqual([e.tipo for e in r.eventos], [C.SEM_EFEITO])

    def test_portaria_e_gravada_em_outras_publicacoes(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = Banco(Path(pasta) / "o.sqlite3")
            try:
                sha = "b" * 64
                texto = "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nPORTARIA Nº 044/2026-DEREH\n" + self.CORPO
                banco.con.execute("INSERT INTO arquivo VALUES (?, 10, 'x', 'agora')", (sha,))
                banco.registrar_leitura(sha, "LIDA", "t", [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": texto,
                                                               "palavras": 50, "qualidade": "OK"}], "18700", "2026-10-08", None)
                PROC.classificar_pendentes(banco)
                self.assertEqual([tuple(l) for l in banco.con.execute("SELECT tipo, vinculo FROM outra_publicacao")], [("PORTARIA", "NAO_EXPRESSO")])
                self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], 0)
            finally:
                banco.fechar()


class TesteGruposEAssuntosAmbiguos(unittest.TestCase):
    def test_dois_grupos_no_mesmo_ato_nao_sao_resolvidos_pela_ordem(self):
        # DEFEITO: "GAJ ... e ... MAG" virava GAJ só porque o padrão de GAJ é avaliado antes do de MAG.
        for grupo, antes in (("GAJ-1700 e do Grupo MAG", "GAJ"), ("MAG e do Grupo de Apoio Judiciário", "GAJ"), ("FAP-1300 e SSA", "FAP")):
            with self.subTest(grupo=grupo):
                self.assertEqual(C.GRUPOS_AVALIACAO[[g.codigo for g in C.GRUPOS_AVALIACAO].index(antes)].codigo, antes)
                r = um(VERTICAL.format(n=940, grupo=grupo) + "SAD-PSE-2026/90041 900041-1 PESSOA FICTICIA TECNICO ADMINISTRATIVO A B\nPUBLIQUE-SE")
                ato = r.atos[0]
                self.assertIsNone(ato.grupo)
                self.assertIn(" | ", ato.grupo_expressao)                      # as expressões lidas ficam guardadas
                self.assertTrue(any("mais de um grupo do PCCR" in p for p in ato.pendencias))
                self.assertEqual(len(r.decisoes), 1)                           # a decisão é preservada

    def test_um_grupo_citado_duas_vezes_continua_sendo_um_grupo(self):
        codigo, expressao, pendencia = C.avaliar_grupo("GRUPO OCUPACIONAL DE APOIO JUDICIARIO GAJ-1700")
        self.assertEqual((codigo, pendencia), ("GAJ", None))

    def test_tec_adm_e_stf_nunca_sao_convertidos(self):
        for expressao, proibido in (("TEC. ADM.", "AST"), ("STF", "SFT"), ("TEC ADM", "AST")):
            with self.subTest(expressao=expressao):
                ato = um(VERTICAL.format(n=941, grupo=expressao) + "SAD-PSE-2026/90042 900042-2 PESSOA FICTICIA TECNICO ADMINISTRATIVO A B\nPUBLIQUE-SE").atos[0]
                self.assertIsNone(ato.grupo)
                self.assertNotEqual(ato.grupo, proibido)
                self.assertTrue(any("sem grupo homologado" in p for p in ato.pendencias))
        # mesmo ao lado da sigla homologada, a expressão não homologada impede a atribuição
        self.assertEqual(C.avaliar_grupo("GRUPO TEC. ADM E AST")[0], None)
        self.assertEqual(C.avaliar_grupo("SERVIDORES STF E SFT")[0], None)

    def tempo(self, assunto):
        return um(CAB.format(n=942) + f"O Diretor DEFERIU os processos de {assunto}:\n"
                  "SEC.EST.SAUDE SAD-PSE-2026/90043 9000043 PESSOA FICTICIA QUARENTA E TRES\nPUBLIQUE-SE")

    def test_ts04_exige_a_licenca_de_interesses_particulares(self):
        # DEFEITO: qualquer "desistência de licença" virava TS-04 (até a de licença especial).
        for assunto in ("DESISTÊNCIA DA LICENÇA PARA TRATAR DE INTERESSES PARTICULARES", "DESISTÊNCIA DE LICENÇA PARA TRATO DE INTERESSE PARTICULAR",
                        "DESISTÊNCIA DA LICENÇA SEM VENCIMENTOS PARA TRATAR DE INTERESSES PARTICULARES"):
            with self.subTest(assunto=assunto):
                self.assertEqual(self.tempo(assunto).atos[0].subcategoria, "TS-04")
        for assunto in ("DESISTÊNCIA DE LICENÇA ESPECIAL", "DESISTÊNCIA DA LICENÇA", "DESISTÊNCIA DE LICENÇA PRÊMIO"):
            with self.subTest(assunto=assunto):
                r = self.tempo(assunto)
                ato = r.atos[0]
                self.assertEqual((ato.eixo, ato.subcategoria), (C.TEMPO, None))          # nem TS-04, nem TS-05 por aproximação
                self.assertTrue(any("TS-04 exige" in p for p in ato.pendencias))
                self.assertEqual(len(r.decisoes), 1)

    def test_ts06_exige_a_conversao_em_tempo_de_servico(self):
        # DEFEITO: "conversão de licença especial em pecúnia" virava TS-06.
        for assunto in ("CONVERSÃO DE LICENÇA ESPECIAL EM TEMPO DE SERVIÇO", "CONVERSÃO DA LICENÇA ESPECIAL NÃO GOZADA EM TEMPO DE CONTRIBUIÇÃO",
                        "CONVERSÃO DE LICENÇA ESPECIAL PARA CONTAGEM EM DOBRO DE TEMPO DE SERVIÇO"):
            with self.subTest(assunto=assunto):
                self.assertEqual(self.tempo(assunto).atos[0].subcategoria, "TS-06")
        for assunto in ("CONVERSÃO DE LICENÇA ESPECIAL EM PECÚNIA", "CONVERSÃO DE LICENÇA ESPECIAL"):
            with self.subTest(assunto=assunto):
                ato = self.tempo(assunto).atos[0]
                self.assertEqual((ato.eixo, ato.subcategoria), (C.TEMPO, None))
                self.assertTrue(any("TS-06 exige" in p for p in ato.pendencias))

    def test_os_demais_assuntos_nao_mudaram(self):
        casos = {"ANOTAÇÃO DE TEMPO DE SERVIÇO": "TS-01", "DESAVERBAÇÃO DE TEMPO": "TS-02", "LICENÇA PARA TRATAR DE INTERESSES PARTICULARES": "TS-03",
                 "LICENÇA ESPECIAL": "TS-05", "CONVERSÃO DE FÉRIAS": "TS-07"}
        for assunto, esperado in casos.items():
            with self.subTest(assunto=assunto):
                ato = self.tempo(assunto).atos[0]
                self.assertEqual(ato.subcategoria, esperado)
                self.assertFalse(any("exige" in p for p in ato.pendencias))

    def test_assunto_sem_subcategoria_pode_ser_corrigido_pela_revisao_da_etapa_05_3_3(self):
        from observatorio.revisao import servico
        with tempfile.TemporaryDirectory() as pasta:
            banco = Banco(Path(pasta) / "o.sqlite3")
            try:
                sha = "c" * 64
                texto = CAB.format(n=943) + ("O Diretor DEFERIU os processos de DESISTÊNCIA DE LICENÇA:\n"
                                             "SEC.EST.SAUDE SAD-PSE-2026/90044 9000044 PESSOA FICTICIA QUARENTA E QUATRO\nPUBLIQUE-SE")
                banco.con.execute("INSERT INTO arquivo VALUES (?, 10, 'x', 'agora')", (sha,))
                banco.registrar_leitura(sha, "LIDA", "t", [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": texto,
                                                               "palavras": 50, "qualidade": "OK"}], "18700", "2026-10-08", None)
                PROC.classificar_pendentes(banco)
                ato = banco.con.execute("SELECT id, eixo, subcategoria FROM ato").fetchone()
                self.assertEqual((ato["eixo"], ato["subcategoria"]), (C.TEMPO, None))
                servico.corrigir_ato(banco, ato["id"], {"subcategoria": "TS-04"}, "Revisora de Teste", "conferido no PDF", confirma_fonte=True)
                self.assertEqual(banco.con.execute("SELECT subcategoria FROM ato").fetchone()[0], "TS-04")
                self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM correcao").fetchone()[0], 1)
            finally:
                banco.fechar()


if __name__ == "__main__":
    unittest.main()
