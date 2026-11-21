"""PDF sintético: contornos vetoriais, cabeçalho nativo, sinal CID, grade e imagem.

Os contornos são gerados no teste a partir da fonte distribuída com o ReportLab. Nenhum
PDF ou dado real é necessário. Uma simulação torna reproduzível a perda parcial do OCR.
"""
import importlib.util
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from observatorio.leitura import leitor
from observatorio.leitura.pagina import Palavra

TEM_DEPS = all(importlib.util.find_spec(m) for m in ('reportlab', 'pdfplumber', 'fontTools', 'PIL'))


def pdf_sintetico():
    import reportlab
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from fontTools.ttLib import TTFont
    from fontTools.pens.reportLabPen import ReportLabPen
    from PIL import Image, ImageDraw, ImageFont
    fonte = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
    font = TTFont(str(fonte))
    glyphs, cmap, units = font.getGlyphSet(), font.getBestCmap(), font['head'].unitsPerEm
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=(595, 842), invariant=1)
    c.setFont('Helvetica', 10)
    for i in range(4):
        c.drawString(40, 810 - i * 14, f'CABECALHO NATIVO FICTICIO LINHA {i:02d} TEXTO SEGURO')
    linhas = ('PROGRESSAO FUNCIONAL PEDIDOS DEFERIDOS', 'PROCESSO FICTICIO E SERVIDOR DE TESTE',
              'REGISTRO SINTETICO PARA LEITURA OCR', 'OUTRA LINHA DE CONTORNOS VETORIAIS')
    for i, linha in enumerate(linhas):
        c.saveState()
        c.translate(40, 685 - i * 18)
        c.scale(14 / units, 14 / units)
        x = 0
        for ch in linha:
            nome = cmap[ord(ch)]
            path = c.beginPath()
            path.closePath = path.close
            pen = ReportLabPen(glyphs, path)
            c.saveState()
            c.translate(x, 0)
            glyphs[nome].draw(pen)
            c.drawPath(path, fill=1, stroke=0)
            c.restoreState()
            x += glyphs[nome].width
        c.restoreState()
    c.setFont('Helvetica', 10)
    c.drawString(45, 630, '(cid:45) (cid:46)')
    c.line(35, 590, 545, 590)
    c.line(35, 550, 545, 550)
    c.line(35, 550, 35, 590)
    c.line(545, 550, 545, 590)
    imagem = Image.new('RGB', (900, 250), 'white')
    ImageDraw.Draw(imagem).text((10, 50), 'IMAGEM SINTETICA OUTRA REGIAO', fill='black',
                               font=ImageFont.truetype(str(fonte), 44))
    c.drawImage(ImageReader(imagem), 50, 375, 360, 100)
    c.showPage()
    c.save()
    font.close()
    return memoria.getvalue()


@unittest.skipUnless(TEM_DEPS, 'requer bibliotecas de PDF e fonttools de teste')
class TesteContornos(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pdf = Path(temp.name) / 'sintetico.pdf'
        self.pdf.write_bytes(pdf_sintetico())

    def test_sem_tesseract_texto_nativo_e_aviso_sobre_regioes(self):
        with mock.patch.object(leitor, 'ocr_disponivel', return_value=(False, 'simulado')):
            pagina = leitor.ler_arquivo(self.pdf)['paginas'][0]
        self.assertIn('CABECALHO NATIVO', pagina['texto'])
        self.assertIn(leitor.AVISO_CONTORNO, pagina['avisos'])
        self.assertIn(leitor.AVISO_IMAGEM, pagina['avisos'])

    def test_ocr_parcial_sem_faixa_vazia_nao_pode_ser_silencioso(self):
        # O OCR retorna algumas palavras com confiança alta, mas perdeu o resto da região.
        # A média e a detecção por linha não demonstram que todas as palavras foram lidas.
        palavras = [Palavra(45, 100, 160, 'PROGRESSAO'), Palavra(110, 160, 160, 'FUNCIONAL'),
                    Palavra(165, 200, 160, 'PEDIDOS')]
        with mock.patch.object(leitor, 'ocr_disponivel', return_value=(True, 'simulado')), \
             mock.patch.object(leitor, '_ler_sobreposicoes', return_value=0), \
             mock.patch.object(leitor, '_ler_regioes_sem_texto', return_value=(palavras, [98.0] * 3, 0)):
            pagina = leitor.ler_arquivo(self.pdf)['paginas'][0]
        self.assertIn('CABECALHO NATIVO', pagina['texto'])
        self.assertIn('PROGRESSAO', pagina['texto'])
        self.assertIn(leitor.AVISO_CONTORNO, pagina['avisos'])

    def test_aviso_de_contorno_vira_pendencia_no_fluxo(self):
        from observatorio.nucleo.banco import Banco
        from observatorio.operacao import fluxo
        palavras = [Palavra(45, 100, 160, 'PROGRESSAO'), Palavra(110, 160, 160, 'FUNCIONAL'),
                    Palavra(165, 200, 160, 'PEDIDOS')]
        dados = self.pdf.parent / 'dados'
        with mock.patch.object(leitor, 'ocr_disponivel', return_value=(True, 'simulado')), \
             mock.patch.object(leitor, '_ler_sobreposicoes', return_value=0), \
             mock.patch.object(leitor, '_ler_regioes_sem_texto', return_value=(palavras, [98.0] * 3, 0)):
            resultado = fluxo.executar(dados, self.pdf, data=date(2026, 10, 9))
        self.assertEqual(resultado['resultado']['codigo'], 3)
        with Banco(dados / 'observatorio.sqlite3') as banco:
            leitura = banco.leituras()[0]
            self.assertEqual(leitura['situacao'], 'LIDA_COM_PENDENCIAS')
            self.assertIn(leitor.AVISO_CONTORNO, leitura['inconsistencias'])

    @unittest.skipUnless(leitor.ocr_disponivel()[0], 'requer Tesseract com português')
    def test_com_tesseract_processa_as_duas_regioes_ou_sinaliza(self):
        pagina = leitor.ler_arquivo(self.pdf)['paginas'][0]
        self.assertIn('CABECALHO NATIVO', pagina['texto'])
        self.assertIn('PROGRESSAO', pagina['texto'])
        self.assertTrue('IMAGEM SINTETICA' in pagina['texto'] or leitor.AVISO_IMAGEM in pagina['avisos'])
        self.assertTrue('OUTRA LINHA' in pagina['texto'] or leitor.AVISO_CONTORNO in pagina['avisos'])
