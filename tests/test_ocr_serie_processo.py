"""Regressão: o Tesseract (5.4, idioma por) lê a série "OFI" do processo como "OF1"/"OFl" em fonte pequena.
A correção vale só na posição da série do número de processo. Dados fictícios; não exige o Tesseract."""
from __future__ import annotations

import unittest
from unittest import mock

from observatorio.gerencias.gediv.classificador import PAT_PROCESSO
from observatorio.leitura import ocr


class TesteCorrecaoSerieProcesso(unittest.TestCase):
    def test_series_lidas_erradas_voltam_ao_padrao(self):
        casos = {
            "SDS-OF1-2026-90826": "SDS-OFI-2026-90826",
            "SDS-OFl-2026-90826": "SDS-OFI-2026-90826",
            "SDS-OF|-2026-90826": "SDS-OFI-2026-90826",
            "SDS-0FI-2026-90826": "SDS-OFI-2026-90826",
            "SAD-PS3-2026/93101": "SAD-PSE-2026/93101",
            "SAD-P5E-2026/93101": "SAD-PSE-2026/93101",
        }
        for lido, esperado in casos.items():
            with self.subTest(lido=lido):
                corrigido = ocr.corrigir_serie_processo(lido)
                self.assertEqual(corrigido, esperado)
                self.assertTrue(PAT_PROCESSO.search(corrigido))

    def test_texto_correto_e_outros_textos_ficam_intactos(self):
        for texto in ("SDS-OFI-2026-90826", "SAD-PSE-2026/93101", "SEE-PRC-2026/1234",
                      "OF1 ESTADUAL", "NIVEL 1", "PESSOA FICTICIA OF1", "SDS-OF1", "ABC-OF1-26-1", "", None):
            with self.subTest(texto=texto):
                self.assertEqual(ocr.corrigir_serie_processo(texto), texto)

    def test_linha_inteira_corrige_so_o_processo(self):
        linha = "SDS-OF1-2026-90826 9000071 PESSOA FICTICIA ALFA NIVEL 1 OF1"
        self.assertEqual(ocr.corrigir_serie_processo(linha),
                         "SDS-OFI-2026-90826 9000071 PESSOA FICTICIA ALFA NIVEL 1 OF1")

    def test_dados_e_texto_do_tesseract_passam_pela_correcao(self):
        bruto = {"text": ["SDS-OF1-2026-90826", "9000071", "", "ALFA"], "conf": [90, 91, -1, 92]}
        with mock.patch.object(ocr, "_chamar", return_value=bruto):
            self.assertEqual(ocr.dados(object())["text"], ["SDS-OFI-2026-90826", "9000071", "", "ALFA"])
        with mock.patch.object(ocr, "_chamar", return_value="SDS-OF1-2026-90826 ALFA\n"):
            self.assertEqual(ocr.texto(object()), "SDS-OFI-2026-90826 ALFA\n")


if __name__ == "__main__":
    unittest.main()
