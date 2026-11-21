"""OCR com limite de tempo e uma thread por chamada (achado de 14/11/2026: seis leituras simultâneas travaram 24 min).

Diários SINTÉTICOS; nenhum PDF oficial."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from observatorio.leitura import ocr
from tests.test_leitura import TEM_BIBLIOTECAS, BaseLeitor, pdf_duas_colunas

TEM_OCR = bool(shutil.which("tesseract")) and bool(importlib.util.find_spec("pytesseract"))


class TesteLimites(unittest.TestCase):
    def _omp_no_processo_filho(self, ambiente):
        codigo = "import observatorio.leitura.ocr, os; print(os.environ['OMP_THREAD_LIMIT'])"
        env = {k: v for k, v in os.environ.items() if k != "OMP_THREAD_LIMIT"} | ambiente
        return subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, check=True).stdout.strip()

    def test_tesseract_usa_uma_thread_por_padrao(self):
        self.assertEqual(self._omp_no_processo_filho({}), "1")

    def test_valor_definido_pelo_operador_prevalece(self):
        self.assertEqual(self._omp_no_processo_filho({"OMP_THREAD_LIMIT": "4"}), "4")

    def test_tempo_maximo_configuravel_e_valor_invalido_volta_ao_padrao(self):
        for valor, esperado in (("30", 30.0), ("abc", ocr.TEMPO_MAXIMO_PADRAO), ("0", ocr.TEMPO_MAXIMO_PADRAO),
                                ("-5", ocr.TEMPO_MAXIMO_PADRAO)):
            with self.subTest(valor=valor), mock.patch.dict(os.environ, {"GEDIV_OCR_TEMPO_MAXIMO": valor}):
                self.assertEqual(ocr.tempo_maximo(), esperado)

    def test_estouro_vira_ocr_esgotado_e_outros_erros_seguem(self):
        def estoura(imagem, timeout, **k):
            raise RuntimeError("Tesseract process timeout")

        def quebra(imagem, timeout, **k):
            raise RuntimeError("outro problema")
        with self.assertRaises(ocr.OcrEsgotado):
            ocr._chamar(estoura, None)
        with self.assertRaises(RuntimeError) as erro:
            ocr._chamar(quebra, None)
        self.assertNotIsInstance(erro.exception, ocr.OcrEsgotado)

    def test_toda_chamada_leva_o_limite_de_tempo(self):
        recebido = {}

        def registra(imagem, timeout, **k):
            recebido["timeout"] = timeout
            return "ok"
        with mock.patch.dict(os.environ, {"GEDIV_OCR_TEMPO_MAXIMO": "7"}):
            ocr._chamar(registra, None)
        self.assertEqual(recebido["timeout"], 7.0)

    def test_nenhum_modulo_chama_o_tesseract_sem_passar_por_ocr(self):
        from pathlib import Path
        raiz = Path(ocr.__file__).resolve().parents[1]
        diretos = [str(p.relative_to(raiz)) for p in raiz.rglob("*.py")
                   if p.name != "ocr.py" and "pytesseract.image_to_" in p.read_text(encoding="utf-8")]
        self.assertEqual(diretos, [])

    @unittest.skipUnless(TEM_OCR, "requer o programa Tesseract")
    def test_estouro_real_do_tesseract(self):
        from PIL import Image, ImageDraw
        imagem = Image.new("L", (2400, 3200), 255)
        desenho = ImageDraw.Draw(imagem)
        for i in range(150):
            desenho.text((40, 20 + i * 21), "LINHA DE TEXTO SINTETICO PARA OCR " * 6, fill=0)
        with mock.patch.dict(os.environ, {"GEDIV_OCR_TEMPO_MAXIMO": "0.01"}), self.assertRaises(ocr.OcrEsgotado):
            ocr.dados(imagem)


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab")
class TesteFilaNaoTrava(BaseLeitor):
    def test_pagina_com_ocr_esgotado_vira_pendencia_e_e_refeita(self):
        from observatorio.leitura import leitor
        sha = self.guardar(pdf_duas_colunas(paginas_extras=False))
        original = leitor._ler_uma_pagina

        def esgota(numero, pagina):
            raise ocr.OcrEsgotado("OCR excedeu 120 s")
        with mock.patch.object(leitor, "_ler_uma_pagina", esgota):
            self.assertEqual(leitor.processar(self.banco, self.acervo),
                             {"LIDA": 0, "LIDA_COM_PENDENCIAS": 1, "ERRO": 0, "na_fila": 0})
        pagina = self.banco.paginas(sha)[0]
        self.assertEqual((pagina["qualidade"], pagina["metodo"]), ("OCR_ESGOTADO", "TEXTO"))
        self.assertIn("SAD-PRC-2026/00007 deferido", pagina["texto"])          # o texto nativo não se perde
        # Nova tentativa, com o OCR respondendo: a pendência desaparece.
        self.assertIs(leitor._ler_uma_pagina, original)
        self.assertEqual(leitor.processar(self.banco, self.acervo, refazer_pendentes=True),
                         {"LIDA": 1, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0})
        self.assertEqual(self.banco.paginas(sha)[0]["qualidade"], "OK")


if __name__ == "__main__":
    unittest.main()
