"""Correções de leitura do PR-02, com documentos SINTÉTICOS (pessoas e processos fictícios).

1. palavras coladas pela extração (tolerância horizontal entre letras);
2. letras espaçadas e palavras coladas no PREÂMBULO (assunto do ato);
3. cabeçalho da resenha separado da tabela (fim de uma coluna / início da outra);
4. liberação dos recursos de cada página;
5. conjunto-ouro: comparação do resultado com o esperado (e, se os PDFs oficiais estiverem disponíveis, execução real).
"""
import importlib.util
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv.classificador import classificar
from observatorio.operacao import ouro

TEM_BIBLIOTECAS = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))


def um(texto):
    return classificar([(1, texto)], "arquivo-de-teste")


CABECALHO = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {n}/2026\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS "
             "EXPEDIENTE DO DIA : 03-11-2026\nGERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n")


class TesteAssuntoComTextoReconstituido(unittest.TestCase):
    def test_palavras_coladas_no_assunto(self):
        r = um(CABECALHO.format(n=951) + "O Diretor Executivo de Recursos Humanos DEFERIU o(s) seguinte(s) processo(s) de "
               "LICENÇAPARATRATAR DE\nINTERESSES PARTICULARES pelo prazo de até 03 (três) anos.\nPROCESSO MATRICULA NOME LOTAÇÃO\n"
               "SAD-PSE-2026/90061 9000061 PESSOA FICTICIA SEC.EST.SAUDE\nPUBLIQUE-SE")
        self.assertEqual([(a.numero, a.subcategoria, a.resultado) for a in r.atos], [("951/2026", "TS-03", "DEFERIDO")])
        self.assertEqual(len(r.decisoes), 1)
        self.assertTrue(any("compacto" in p for p in r.atos[0].pendencias))      # o revisor sabe que o texto foi reconstituído

    def test_letras_espacadas_no_assunto_e_no_resultado(self):
        r = um(CABECALHO.format(n=952) + "O D I R E T O R E X E C U T I V O D E R E C U R S O S H U M A N O S , p o r d e le g a ç ã o, "
               "resolve INDEFERIR o s P r o c e s so s d e D E S A V E R B A Ç Ã O de Te m p o d e S er v iç o d o s s e rv i d o r e s a b a ix o :\n"
               "Lotacao Processo Matricula Nome Origem do tempo Data Inicio Data Final Total Dias\n"
               "SEC. EST. GOVERNO SAD-PSE-2026/90062 9000062 PESSOA FICTICIA Tempo Publico Estadual 01/06/1977 01/02/1978 246\nPUBLIQUE-SE")
        self.assertEqual([(a.numero, a.subcategoria, a.resultado) for a in r.atos], [("952/2026", "TS-02", "INDEFERIDO")])
        self.assertEqual(len(r.decisoes), 1)
        self.assertTrue(any("letras_reunidas" in p for p in r.atos[0].pendencias))

    def test_progressao_com_letras_espacadas(self):
        r = um(CABECALHO.format(n=953) + "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos de P R O G R E S S Ã O "
               "F U N C I O N A L V E R T I C A L do Grupo MAG:\nSAD-PSE-2026/90063 900063-0 PESSOA FICTICIA PROFESSOR A B\nPUBLIQUE-SE")
        self.assertEqual([(a.eixo, a.modalidade, a.grupo) for a in r.atos], [(C.PROGRESSAO, C.VERTICAL, "MAG")])

    def test_texto_normal_nao_ganha_pendencia_de_reconstituicao(self):
        r = um(CABECALHO.format(n=954) + "O Diretor DEFERIU os processos de LICENÇA PARA TRATAR DE INTERESSES PARTICULARES:\n"
               "SAD-PSE-2026/90064 9000064 PESSOA FICTICIA SEE\nPUBLIQUE-SE")
        self.assertEqual(r.atos[0].subcategoria, "TS-03")
        self.assertFalse(any("reconstituído" in p for p in r.atos[0].pendencias))

    def test_forma_compacta_nao_inventa_assunto(self):
        for assunto in ("AUXÍLIO FUNERAL", "FLEXIBILIZAÇÃO DE HORÁRIO", "CESSÃO DE SERVIDOR", "ABONO DE PERMANÊNCIA"):
            with self.subTest(assunto=assunto):
                r = um(CABECALHO.format(n=955) + f"O Diretor DEFERIU os processos de {assunto}:\n"
                       "SAD-PSE-2026/90065 9000065 PESSOA FICTICIA SEE\nPUBLIQUE-SE")
                self.assertEqual(r.atos, [])
                self.assertEqual(r.decisoes, [])

    def test_compactacao_preserva_os_padroes_das_sete_subcategorias(self):
        casos = {"ANOTACAODETEMPODESERVICO": "TS-01", "DESAVERBACAODETEMPO": "TS-02",
                 "LICENCAPARATRATARDEINTERESSESPARTICULARES": "TS-03", "DESISTENCIADALICENCAPARATRATAR": "TS-04",
                 "LICENCAESPECIAL": "TS-05", "CONVERSAODELICENCAESPECIALEMTEMPODESERVICO": "TS-06", "CONVERSAODEFERIAS": "TS-07"}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(C.identificar_subcategoria(texto, compacto=True), esperado)


@unittest.skipUnless(TEM_BIBLIOTECAS, "requer pdfplumber e reportlab")
class TesteLeituraDoPdf(unittest.TestCase):
    def pdf_com_espaco_estreito(self) -> bytes:
        """Palavras desenhadas uma a uma com 2,2 pt entre elas: estreito demais para a tolerância padrão (3 pt)."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
        memoria = io.BytesIO()
        c = canvas.Canvas(memoria, pagesize=A4)
        c.setFont("Helvetica", 7)
        y = A4[1] - 80
        for linha in range(4):
            x = 40
            for palavra in ("DEFERIU", "OS", "PROCESSOS", "DE", "LICENÇA", "PARA", "TRATAR", "DE", "INTERESSES", "PARTICULARES"):
                c.drawString(x, y, palavra)
                x += stringWidth(palavra, "Helvetica", 7) + 2.2
            y -= 12
        c.showPage()
        c.save()
        return memoria.getvalue()

    def gravar(self, dados: bytes) -> Path:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "teste.pdf"
        caminho.write_bytes(dados)
        return caminho

    def test_espaco_estreito_nao_cola_palavras(self):
        import pdfplumber
        from observatorio.leitura import leitor
        caminho = self.gravar(self.pdf_com_espaco_estreito())
        with pdfplumber.open(str(caminho)) as d:                      # o defeito existe com a tolerância padrão
            padrao = " ".join(w["text"] for w in d.pages[0].extract_words())
        self.assertIn("LICENÇAPARATRATAR", padrao)
        texto = leitor.ler_arquivo(caminho)["paginas"][0]["texto"]
        self.assertIn("LICENÇA PARA TRATAR DE INTERESSES PARTICULARES", texto)
        self.assertNotIn("LICENÇAPARA", texto)

    def test_cada_pagina_e_liberada_depois_de_lida(self):
        import pdfplumber.page
        from observatorio.leitura import leitor
        from tests.test_leitura import pdf_duas_colunas
        caminho = self.gravar(pdf_duas_colunas(paginas_extras=True))
        original = pdfplumber.page.Page.close
        fechadas = []

        def contar(pagina):
            fechadas.append(pagina.page_number)
            return original(pagina)

        with mock.patch.object(pdfplumber.page.Page, "close", contar):
            resultado = leitor.ler_arquivo(caminho)
        self.assertEqual(sorted(set(fechadas)), [p["numero"] for p in resultado["paginas"]])

    def test_cabecalho_no_fim_de_uma_coluna_e_tabela_no_inicio_da_outra(self):
        from observatorio.leitura import leitor
        from observatorio.operacao import sintetico as S
        resenha = S.resenha_tempo(961, "01-10-2026", "LICENÇA ESPECIAL", 70, 5)
        corte = next(i for i, l in enumerate(resenha) if "SAD-PSE-2026/" in l)
        coluna1 = S.outros_atos(3) + resenha[:corte]                  # cabeçalho e preâmbulo no pé da coluna 1
        coluna2 = resenha[corte:] + S.outros_atos(4)                  # tabela no topo da coluna 2
        caminho = self.gravar(S.diario(date(2026, 10, 2), 18684, [], colunas=(coluna1, coluna2)))
        paginas = leitor.ler_arquivo(caminho)["paginas"]
        r = classificar([(p["numero"], p["texto"]) for p in paginas], "x")
        self.assertEqual([(a.numero, a.subcategoria) for a in r.atos], [("961/2026", "TS-05")])
        self.assertEqual(len(r.decisoes), 5)


class TesteConjuntoOuro(unittest.TestCase):
    def relatorio(self, atos, decisoes, fora=()):
        return {"resultado": "FLUXO_EXECUTADO", "gediv": {
            "atos": [{"numero": n, "eixo": e, "modalidade": None, "subcategoria": s, "grupo": None, "resultado": r,
                      "vinculo_gediv": "EXPRESSO", "decisoes": d} for n, e, s, r, d in atos],
            "decisoes_extraidas": decisoes, "fora_escopo": [{"numero": n, "motivo": m} for n, m in fora]}}

    ESPERADO = {"atos": [{"numero": "540/2026", "eixo": "TEMPO_SERVICO", "classe": "TS-03", "grupo": None, "resultado": "DEFERIDO",
                          "vinculo": "EXPRESSO", "decisoes": 1}], "decisoes": 1, "fora_escopo_inclui": [["541/2026", "LICENCA_SAUDE"]]}

    def test_resultado_igual_ao_esperado_confere(self):
        r = self.relatorio([("540/2026", "TEMPO_SERVICO", "TS-03", "DEFERIDO", 1)], 1, [("541/2026", "LICENCA_SAUDE"), ("9/2026", "VACANCIA")])
        self.assertEqual(ouro.comparar(self.ESPERADO, r), [])

    def test_regressoes_sao_detectadas(self):
        casos = {
            "ato perdido": self.relatorio([], 0, [("541/2026", "LICENCA_SAUDE")]),
            "subcategoria trocada": self.relatorio([("540/2026", "TEMPO_SERVICO", "TS-05", "DEFERIDO", 1)], 1, [("541/2026", "LICENCA_SAUDE")]),
            "decisão a mais": self.relatorio([("540/2026", "TEMPO_SERVICO", "TS-03", "DEFERIDO", 2)], 2, [("541/2026", "LICENCA_SAUDE")]),
            "exclusão perdida": self.relatorio([("540/2026", "TEMPO_SERVICO", "TS-03", "DEFERIDO", 1)], 1, []),
            "ato inventado": self.relatorio([("540/2026", "TEMPO_SERVICO", "TS-03", "DEFERIDO", 1),
                                             ("541/2026", "TEMPO_SERVICO", "TS-05", "DEFERIDO", 0)], 1, [("541/2026", "LICENCA_SAUDE")]),
        }
        for nome, relatorio in casos.items():
            with self.subTest(caso=nome):
                self.assertTrue(ouro.comparar(self.ESPERADO, relatorio))

    def test_manifesto_nao_tem_dados_pessoais(self):
        import json
        import re
        texto = ouro.MANIFESTO_PADRAO.read_text(encoding="utf-8")
        dados = json.loads(texto)
        self.assertEqual(len(dados["documentos"]), 5)
        self.assertIsNone(re.search(r"[A-Z]{2,6}-(?:PSE|PRC|OFI)-\d{4}/\d+|\b\d{3}\.\d{3}-\d\b|\b\d{6,8}\b", texto))
        self.assertTrue(all(len(d["sha256"]) == 64 for d in dados["documentos"]))

    @unittest.skipUnless(os.environ.get("GEDIV_PDFS_OURO"), "informe a pasta dos PDFs oficiais em GEDIV_PDFS_OURO")
    def test_conjunto_ouro_com_os_pdfs_oficiais(self):
        resultado = ouro.executar(os.environ["GEDIV_PDFS_OURO"])
        problemas = {e["data"]: e.get("divergencias") or e["situacao"] for e in resultado["edicoes"] if e["situacao"] != "CONFERE"}
        self.assertEqual(problemas, {})


if __name__ == "__main__":
    unittest.main()
