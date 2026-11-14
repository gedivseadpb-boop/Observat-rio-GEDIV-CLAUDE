"""Etapa 04 — PDFs difíceis do DOE-PB. Documentos e textos SINTÉTICOS (pessoas e processos fictícios),
reproduzindo a FORMA dos casos reais encontrados nas edições de 02/10 a 12/11/2026."""
import importlib.util
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv import classificador as K
from observatorio.gerencias.gediv.classificador import classificar
from observatorio.nucleo import banco as B

TEM_PDF = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))
TEM_OCR = False
if TEM_PDF:
    from observatorio.leitura import leitor
    TEM_OCR = leitor.ocr_disponivel()[0]


def um(texto):
    return classificar([(1, texto)], "arquivo-de-teste")


GPC = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº: 971/2026 /DEREH/GS\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS "
       "EXPEDIENTE DO DIA: 05-11-2026\nO SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos dos Profissionais do Grupo "
       "Ocupacional de Polícia Civil – GPC 600 de PROGRESSÃO FUNCIONAL HORIZONTAL abaixo relacionados:\n"
       "Nº do Documento Matrícula Nome Cargo Niv. Ant. Atual\n"
       "SDS-OFI-2026-90826 9000071 PESSOA FICTICIA UM Investigador de Polícia Civil NÍVEL 2 NÍVEL3\n"
       "SDS-OFI-2026-90826 9000072 PESSOA FICTICIA DOIS Necrotomista Policial NÍVEL 1 NÍVEL 2\n"
       "SDS-OFI-2026-90826 9000073 PESSOA FICTICIA TRES Delegado de Polícia NÍVEL 3 NÍVEL 4\nPUBLIQUE-SE")


class TesteDocumentoComHifenENivelNumerado(unittest.TestCase):
    def test_oficio_com_hifen_e_niveis_numerados(self):
        r = um(GPC)
        self.assertEqual([(a.numero, a.grupo, a.modalidade) for a in r.atos], [("971/2026", "GPC", C.HORIZONTAL)])
        self.assertEqual([d.processo for d in r.decisoes], ["SDS-OFI-2026-90826"] * 3)      # como publicado, com hífen
        self.assertEqual(len({d.id for d in r.decisoes}), 3)                                  # o mesmo ofício, 3 decisões
        self.assertEqual([(d.servidor, d.cargo) for d in r.decisoes],
                         [("PESSOA FICTICIA UM", "INVESTIGADOR DE POLICIA CIVIL"), ("PESSOA FICTICIA DOIS", "NECROTOMISTA POLICIAL"),
                          ("PESSOA FICTICIA TRES", "DELEGADO DE POLICIA")])
        self.assertEqual([(d.detalhe["nivel_anterior"], d.detalhe["nivel_atual"]) for d in r.decisoes],
                         [("NIVEL 2", "NIVEL 3"), ("NIVEL 1", "NIVEL 2"), ("NIVEL 3", "NIVEL 4")])

    def test_barra_continua_aceita_e_preservada(self):
        self.assertEqual(K._processo(K.PAT_PROCESSO.search("SAD-PSE-2026/90001")), "SAD-PSE-2026/90001")
        self.assertEqual(K._processo(K.PAT_PROCESSO.search("SDS-OFI-2026-90826")), "SDS-OFI-2026-90826")
        self.assertIsNone(K.PAT_PROCESSO.search("LEI 2026-90826"))


class TesteClasseENivelComoPublicados(unittest.TestCase):
    def ev(self, cauda, modalidade):
        return K._evolucao(cauda, C.PROGRESSAO, modalidade, None)[1]

    def test_classe_e_nivel_em_campos_distintos(self):
        self.assertEqual(self.ev("TECNICO A B", C.VERTICAL), {"classe_anterior": "A", "classe_posterior": "B"})
        self.assertEqual(self.ev("TECNICO III IV", C.HORIZONTAL), {"nivel_anterior": "III", "nivel_atual": "IV"})

    def test_saltos_sao_mantidos_e_sinalizados(self):
        for cauda, modalidade, campos in (("TECNICO A E", C.VERTICAL, ("A", "E")), ("PENAL III VII", C.HORIZONTAL, ("III", "VII")),
                                          ("PENAL II V", C.HORIZONTAL, ("II", "V"))):
            with self.subTest(cauda=cauda):
                d = self.ev(cauda, modalidade)
                self.assertEqual(tuple(v for k, v in d.items() if k != "observacoes"), campos)     # nada é "corrigido"
                self.assertIn("salto", d["observacoes"][0])

    def test_regressao_e_valor_fora_da_faixa_sao_mantidos_e_sinalizados(self):
        d = self.ev("TECNICO C B", C.VERTICAL)
        self.assertEqual((d["classe_anterior"], d["classe_posterior"]), ("C", "B"))
        self.assertIn("sem avanço", d["observacoes"][0])
        d = self.ev("TECNICO A G", C.VERTICAL)
        self.assertEqual((d["classe_anterior"], d["classe_posterior"]), ("A", "G"))
        self.assertIn("fora da faixa", d["observacoes"][0])

    def test_formato_trocado_nao_e_convertido(self):
        d = self.ev("TECNICO III IV", C.VERTICAL)
        self.assertNotIn("classe_anterior", d)
        self.assertEqual(d["evolucao_lida"], "III IV")
        d = self.ev("TECNICO A B", C.HORIZONTAL)
        self.assertNotIn("nivel_anterior", d)
        self.assertEqual(d["evolucao_lida"], "A B")


PORTARIA_SEM_EFEITO = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS\n"
                       "Portaria nº 908/2026- DEREH João Pessoa, 09 de novembro de 2026\nO DIRETOR EXECUTIVO DE RECURSOS HUMANOS "
                       "R E S O L V E tornar sem efeito o ato que concedeu a Licença Especial, através do processo Nº 900.071-5, "
                       "publicado no D.O.E. edição do dia 28/07/1999, à servidora PESSOA FICTICIA, matrícula nº 9000071.\nPUBLIQUE-SE")


class TesteReferenciaAoAtoOriginal(unittest.TestCase):
    def test_publicacao_e_processo_antigo_citados_sao_guardados_como_publicados(self):
        r = um(PORTARIA_SEM_EFEITO)
        self.assertEqual(len(r.eventos), 1)
        e = r.eventos[0]
        self.assertEqual((e.tipo, e.publicacoes_citadas, e.resenhas_citadas), (C.SEM_EFEITO, ["1999-07-28"], []))
        self.assertIn("900.071-5", e.processos_citados)
        self.assertNotIn("9000071", " ".join(e.processos_citados))       # a matrícula não vira processo

    def test_original_anterior_a_base_recebe_fundamento_e_continua_pendente(self):
        from observatorio.gerencias.gediv import processo
        with tempfile.TemporaryDirectory() as pasta:
            banco = B.Banco(Path(pasta) / "b.sqlite3")
            try:
                with banco.con:
                    banco.con.execute("INSERT INTO arquivo VALUES ('sha', 1, 'x', 'agora')")
                banco.gravar_classificacao("GEDIV", "sha", C.VERSAO_REGRAS, "2026-11-10", um(PORTARIA_SEM_EFEITO))
                processo.sugerir_vinculos(banco)
                ev = banco.con.execute("SELECT estado, fundamento, publicacoes_citadas FROM evento").fetchone()
                self.assertEqual(ev["estado"], "PENDENTE_VINCULACAO")
                self.assertIn("28/07/1999", ev["fundamento"])
                self.assertIn("antes do início da base", ev["fundamento"])
            finally:
                banco.fechar()

    def test_migracao_v5_para_v6_preserva_eventos(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "v5.sqlite3"
            con = sqlite3.connect(caminho)
            for script in (B._ESQUEMA, B._ESQUEMA_V2, B._ESQUEMA_V3, B._ESQUEMA_V4, B._ESQUEMA_V5):
                con.executescript(script)
            con.execute("PRAGMA user_version = 5")
            con.execute("INSERT INTO arquivo VALUES ('sha', 1, 'x', 'agora')")
            con.execute("INSERT INTO evento (id, gerencia, sha256, tipo, pagina, vinculo, texto) VALUES ('e1','GEDIV','sha','RETIFICACAO',1,'EXPRESSO','t')")
            con.commit()
            con.close()
            banco = B.Banco(caminho)
            try:
                self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
                self.assertEqual(banco.con.execute("SELECT id, publicacoes_citadas FROM evento").fetchone()[:], ("e1", None))
            finally:
                banco.fechar()


def _pdf(desenhar) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4)
    desenhar(c, A4)
    c.showPage()
    c.save()
    return memoria.getvalue()


@unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab")
class TesteToleranciaProporcional(unittest.TestCase):
    def test_tabela_de_corpo_pequeno_separa_palavras_e_mantem_a_palavra_inteira(self):
        import pdfplumber
        from reportlab.pdfbase.pdfmetrics import stringWidth

        def desenhar(c, tamanho):
            c.setFont("Helvetica", 4.3)
            for linha in range(4):
                x, y = 40, tamanho[1] - 80 - 8 * linha
                for palavra in ("JOSY", "ALMEIDA", "MARIANO", "TECNICO", "ADMINISTRATIVO"):
                    c.drawString(x, y, palavra)
                    x += stringWidth(palavra, "Helvetica", 4.3) + 0.87       # vão real medido no DOE de 05/11/2026
        with pdfplumber.open(io.BytesIO(_pdf(desenhar))) as d:
            fixa = [w["text"] for w in d.pages[0].extract_words(x_tolerance=1.5)][:5]
            proporcional = [w["text"] for w in d.pages[0].extract_words(x_tolerance_ratio=leitor.TOLERANCIA_X_PROPORCIONAL)][:5]
        self.assertIn("JOSYALMEIDA", "".join(fixa).replace(" ", "")[:20])
        self.assertEqual(proporcional, ["JOSY", "ALMEIDA", "MARIANO", "TECNICO", "ADMINISTRATIVO"])


@unittest.skipUnless(TEM_PDF and TEM_OCR, "requer pdfplumber, reportlab e Tesseract com português")
class TesteOcrDeTabelaPelaGrade(unittest.TestCase):
    LINHAS = [("Nº do Documento", "Matrícula", "Nome", "Cargo", "Niv. Ant.", "Atual")] + [
        ("SDS-OFI-2026-90826", f"900007{i}", f"PESSOA FICTICIA {n}", "Investigador de Polícia Civil", "NÍVEL 2", "NÍVEL 3")
        for i, n in enumerate(("ALFA", "BETA", "GAMA", "DELTA"), start=1)]
    COLUNAS = (40, 115, 160, 300, 430, 475, 520)

    def pdf_tabela(self):
        def desenhar(c, tamanho):
            topo = tamanho[1] - 100
            c.setLineWidth(1.6)                                         # grade grossa, como no DOE
            for i in range(len(self.LINHAS) + 1):
                c.line(self.COLUNAS[0], topo - 16 * i, self.COLUNAS[-1], topo - 16 * i)
            for x in self.COLUNAS:
                c.line(x, topo, x, topo - 16 * len(self.LINHAS))
            c.setFont("Helvetica", 7)
            for i, linha in enumerate(self.LINHAS):
                for x, texto in zip(self.COLUNAS, linha):
                    c.drawString(x + 3, topo - 16 * i - 11, texto)
        return _pdf(desenhar)

    def palavras_ilegiveis(self, pagina, legiveis=0):
        """Simula a fonte sem mapeamento: as palavras das células de dados viram "(cid:N)"."""
        brutas = pagina.extract_words(x_tolerance_ratio=leitor.TOLERANCIA_X_PROPORCIONAL)
        cabecalho = min(w["top"] for w in brutas)
        for w in brutas:
            if w["top"] > cabecalho + 3:
                w["text"] = "(cid:12)" * 5
        return brutas

    def test_cada_linha_da_tabela_sai_inteira_e_na_ordem_das_colunas(self):
        import pdfplumber
        from observatorio.leitura import pagina as PG
        from observatorio.leitura import tabela_ocr
        with pdfplumber.open(io.BytesIO(self.pdf_tabela())) as d:
            p = d.pages[0]
            brutas = self.palavras_ilegiveis(p)
            bloco = leitor._blocos_ilegiveis(brutas, float(p.width), float(p.height))[0]
            palavras, confiancas, area = tabela_ocr.ler_tabela(p, bloco, brutas, lambda t: "(cid:" in t)
        linhas = PG.ler_pagina(palavras, float(p.width))[0].split("\n")
        dados = [l for l in linhas if l.startswith("SDS")]
        self.assertEqual(len(dados), 4)
        for linha, nome in zip(dados, ("ALFA", "BETA", "GAMA", "DELTA")):
            with self.subTest(nome=nome):
                self.assertRegex(linha, rf"^SDS-OFI-2026-90826 900007\d PESSOA FICTICIA {nome} Investigador de Pol[ií]cia Civil N[IÍ]VEL ?2 N[IÍ]VEL ?3$")
        self.assertGreater(sum(confiancas) / len(confiancas), 75)

    def test_grade_maior_que_o_trecho_ilegivel_nao_e_usada(self):
        import pdfplumber
        from observatorio.leitura import tabela_ocr
        with pdfplumber.open(io.BytesIO(self.pdf_tabela())) as d:
            p = d.pages[0]
            brutas = p.extract_words(x_tolerance_ratio=leitor.TOLERANCIA_X_PROPORCIONAL)
            alvo = [w for w in brutas if w["text"] == "ALFA"][0]
            alvo["text"] = "(cid:12)" * 12                              # só UMA célula ilegível numa tabela legível
            bloco = (alvo["x0"], alvo["top"], alvo["x1"], alvo["bottom"])
            self.assertIsNone(tabela_ocr.ler_tabela(p, bloco, brutas, lambda t: "(cid:" in t))


@unittest.skipUnless(TEM_PDF and TEM_OCR, "requer pdfplumber, reportlab e Tesseract com português")
class TesteCaracteresSobrepostos(unittest.TestCase):
    def test_vale_o_que_esta_impresso_visivel(self):
        import pdfplumber

        def desenhar(c, tamanho):
            c.setFont("Helvetica", 9)
            c.drawString(40, tamanho[1] - 80, "TECNICO ADMINISTRATIVO")
            c.setFillColorRGB(1, 1, 1)                                   # letra original, encoberta
            c.drawString(200, tamanho[1] - 80, "A")
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Courier-Bold", 9)                                 # correção impressa por cima, outra fonte
            c.drawString(200, tamanho[1] - 80, "D")
            c.setFont("Helvetica", 9)
            c.drawString(230, tamanho[1] - 80, "E")
        with pdfplumber.open(io.BytesIO(_pdf(desenhar))) as d:
            p = d.pages[0]
            brutas = p.extract_words(x_tolerance_ratio=leitor.TOLERANCIA_X_PROPORCIONAL)
            sobreposta = [w for w in brutas if w["x0"] >= 199 and w["x1"] <= 210][0]
            sobreposta["text"] = "A(cid:39)"                             # como sai do PDF real (fonte sem mapeamento)
            self.assertEqual(leitor._ler_sobreposicoes(p, brutas), 1)
        self.assertEqual(sobreposta["text"], "D")


class TesteCorpusPorCampo(unittest.TestCase):
    """Medição por campo: comparação (sempre) e execução real (só com os PDFs e o esperado privado)."""

    def test_comparacao_conta_acertos_por_campo_e_linhas_inteiras(self):
        from observatorio.operacao import corpus
        esperadas = [{"processo": "SAD-PSE-2026/90001", "matricula": "9000001", "servidor": "PESSOA FICTICIA UM", "cargo": "PROFESSOR",
                      "evolucao_anterior": "A", "evolucao_posterior": "B"},
                     {"processo": "SAD-PSE-2026/90002", "matricula": "9000002", "servidor": "PESSOA FICTICIA DOIS", "cargo": "PROFESSOR",
                      "evolucao_anterior": None, "evolucao_posterior": None}]
        obtidas = [{"processo": "SAD-PSE-2026/90002", "matricula": "9000002", "servidor": "PESSOA FICTICIADOIS", "cargo": "Professor",
                    "evolucao_anterior": None, "evolucao_posterior": None},
                   {"processo": "SAD-PSE-2026/90001", "matricula": "9000001", "servidor": "Pessoa Fictícia Um", "cargo": "PROFESSOR",
                    "evolucao_anterior": "A", "evolucao_posterior": "E"}]
        r = corpus.comparar(esperadas, obtidas)
        self.assertEqual((r["linhas_encontradas"], r["linhas_inteiramente_corretas"]), (2, 0))
        self.assertEqual(r["por_campo"]["servidor"], {"acertos": 1, "total": 2})          # maiúsculas/acentos não contam como erro
        self.assertEqual(r["por_campo"]["evolucao_posterior"], {"acertos": 0, "total": 1})  # campos ausentes no esperado não contam

    def test_manifesto_publico_sem_dados_pessoais(self):
        import json
        import re
        from observatorio.operacao import corpus
        dados = json.loads(corpus.MANIFESTO.read_text(encoding="utf-8"))
        for caso in dados["casos"]:
            caso.pop("bytes", None)                                    # tamanho do arquivo não é dado pessoal
        texto = json.dumps(dados, ensure_ascii=False)
        self.assertIsNone(re.search(r"SAD-PSE-2026/\d+|SDS-OFI-\d{4}-\d+|\b\d{6}-\d\b|\b\d{7}\b|\"(?:servidor|matricula|processo)\"", texto))
        casos = json.loads(texto)["casos"]
        self.assertEqual({c["conjunto"] for c in casos}, {"desenvolvimento", "validacao_cega"})
        self.assertTrue(all(len(c["sha256"]) == 64 and c["pagina_pdf"] for c in casos))

    @unittest.skipUnless(__import__("os").environ.get("GEDIV_PDFS_OURO") and __import__("os").environ.get("GEDIV_CORPUS_PRIVADO"),
                         "informe GEDIV_PDFS_OURO e GEDIV_CORPUS_PRIVADO")
    def test_corpus_real_por_campo(self):
        import os
        from observatorio.operacao import corpus
        r = corpus.executar(os.environ["GEDIV_PDFS_OURO"], os.environ["GEDIV_CORPUS_PRIVADO"])
        # Antes: percorria os conjuntos devolvidos — um resultado vazio passava sem avaliar nada.
        self.assertEqual(r["situacao"], corpus.APROVADO, r["motivo"])
        self.assertEqual(set(r["conjuntos"]), {"desenvolvimento", "validacao_cega"})
        for conjunto, dados in r["conjuntos"].items():
            with self.subTest(conjunto=conjunto):
                self.assertEqual(dados["por_situacao"], {corpus.CONFERE: len(dados["casos"])})
                self.assertEqual(dados["total"]["linhas_pareadas"], dados["total"]["linhas_esperadas"])
                self.assertEqual(dados["total"]["precisao_todos_os_campos"], 100.0)


if __name__ == "__main__":
    unittest.main()
