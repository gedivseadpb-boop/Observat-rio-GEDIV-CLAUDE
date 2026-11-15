"""Etapa 05.3.5 — exame dos limites do leitor documentados na Etapa 05.3.4 (docs/15, seções 11 e 12).

Para cada limite: um teste que o reproduz e o comportamento exigido agora — corrigido, quando havia correção pontual
segura, ou SINALIZADO para revisão, quando não havia. Nenhuma limitação pode se esconder atrás de um arquivo dado
como "lido" sem ressalva. Dados sintéticos.
"""
import importlib.util
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from observatorio.gerencias.gediv.classificador import classificar
from observatorio.leitura import pagina as PG
from observatorio.leitura.pagina import Palavra
from tests import textos_doe as T
from tests.test_extracao_ocr_classificacao import CAB, VERTICAL, celula

TEM_PDF = importlib.util.find_spec("pdfplumber") is not None and importlib.util.find_spec("reportlab") is not None
TEM_PIL = importlib.util.find_spec("PIL") is not None
if TEM_PDF:
    from observatorio.leitura import leitor


def um(texto):
    return classificar([(1, texto)], "arquivo-de-teste")


# ====================================================================================================================
# 1. Título centrado logo abaixo da tabela
# ====================================================================================================================
class TesteTituloCentradoDepoisDaTabela(unittest.TestCase):
    COLUNAS = (40, 170, 330, 480)

    def linha(self, topo, *celulas):
        return [p for x, texto in zip(self.COLUNAS, celulas) if texto for p in celula(x, topo, texto)]

    def tabela(self):
        p = []
        for i in range(4):
            p += self.linha(100 + 9 * i, f"SAD-PSE-2026/9000{i}", f"PESSOA FICTICIA NUMERO {i} DA SILVA", "TECNICO", "A B")
        return p

    def test_titulo_centrado_dentro_da_coluna_do_nome_nao_e_absorvido(self):
        # DEFEITO (limite da 05.3.4): o título cabia na faixa da coluna NOME, a menos de 1,35 entrelinha, e era juntado à
        # última linha: o nome da última pessoa ganhava as palavras do título.
        # a célula do nome vai de 170 a 320 (centro 245); o título, de 190 a 267 (centro 228,5): cabe na coluna, mas não
        # se alinha à célula nem pela esquerda, nem pela direita, nem pelo centro
        p = self.tabela() + celula(190, 136, "RESENHA SEGUINTE")
        linhas = PG.ler_pagina(p, 595)[0].split("\n")
        self.assertEqual(linhas[-1], "RESENHA SEGUINTE")
        self.assertEqual(linhas[-2], "SAD-PSE-2026/90003 PESSOA FICTICIA NUMERO 3 DA SILVA TECNICO A B")
        self.assertEqual(len(linhas), 5)

    def test_continuacao_alinhada_a_celula_continua_sendo_juntada(self):
        p = self.tabela() + self.linha(136, "", "DOS SANTOS", "ADMINISTRATIVO")   # alinhada à esquerda das células
        linhas = PG.ler_pagina(p, 595)[0].split("\n")
        self.assertEqual(linhas[-1], "SAD-PSE-2026/90003 PESSOA FICTICIA NUMERO 3 DA SILVA DOS SANTOS TECNICO ADMINISTRATIVO A B")

    def test_continuacao_de_celula_centrada_continua_sendo_juntada(self):
        # coluna do cargo centrada: a continuação é mais curta e tem o mesmo centro da célula de cima
        p = []
        for i in range(4):
            p += self.linha(100 + 16 * i, f"SAD-PSE-2026/9000{i}", f"PESSOA FICTICIA NUMERO {i}", "", "A B")
            p += celula(330, 100 + 16 * i, "TECNICO ESPECIALIZADO")               # 330 … 437
        p += celula(363.5, 155, "EM SAUDE")                                       # centro igual ao da célula (383,5)
        linhas = PG.ler_pagina(p, 595)[0].split("\n")
        self.assertEqual(linhas[-1], "SAD-PSE-2026/90003 PESSOA FICTICIA NUMERO 3 TECNICO ESPECIALIZADO EM SAUDE A B")

    def test_no_meio_da_tabela_a_regra_de_alinhamento_nao_se_aplica(self):
        # Entre duas linhas da própria tabela o fragmento continua indo para a linha mais próxima, como na 05.3.4: em
        # tabela lida por OCR a posição das palavras é aproximada, e exigir alinhamento ali criaria ambiguidade falsa.
        p = []
        for i in range(4):
            p += self.linha(100 + 16 * i, f"SAD-PSE-2026/9000{i}", f"PESSOA FICTICIA NUMERO {i} DA SILVA", "TECNICO", "A B")
        p += celula(176, 107, "JUNIOR")                                           # 6 pt à direita do começo do nome
        leitura = PG.ler_pagina_detalhada(p, 595)
        self.assertEqual(leitura.linhas_ambiguas, 0)
        self.assertIn("SAD-PSE-2026/90000 PESSOA FICTICIA NUMERO 0 DA SILVA JUNIOR TECNICO A B", leitura.texto.split("\n"))


class TesteTracoDaGradeLidoComoCaractere(unittest.TestCase):
    """Achado na regressão com PDFs oficiais (resenha 570/2026, 07/11/2026): a borda vertical da célula do nome sai
    do PDF como o caractere "|"."""
    COLUNAS = (40, 150, 330, 480)

    def test_nome_e_cargo_sao_extraidos_apesar_do_traco(self):
        # DEFEITO: com "| NOME" o nome não era reconhecido e a decisão ficava sem nome e sem cargo (todas as linhas).
        r = um(VERTICAL.format(n=960, grupo="MAG") + "Processo Matricula Nome Cargo Classe P/Classe\n"
               "SAD-PSE-2026/90061 900061-1 | PESSOA FICTICIA SESSENTA E UM PROFESSOR DE EDUCACAO BAS A B\n"
               "SAD-PSE-2026/90062 900062-2 | PESSOA FICTICIA SESSENTA E DOIS | PROFESSOR DE EDUCACAO BAS | B C\nPUBLIQUE-SE")
        self.assertEqual([(d.servidor, d.cargo, d.detalhe.get("classe_posterior")) for d in r.decisoes],
                         [("PESSOA FICTICIA SESSENTA E UM", "PROFESSOR DE EDUCACAO BAS", "B"),
                          ("PESSOA FICTICIA SESSENTA E DOIS", "PROFESSOR DE EDUCACAO BAS", "C")])

    def test_cargo_com_a_primeira_letra_cortada_pelo_ocr_e_separado_do_nome_e_sinalizado(self):
        # DEFEITO (achado na regressão, mesma resenha): "ROFESSOR DE EDUCACAO BAS" não era reconhecido como cargo e ia
        # inteiro para o campo do nome.
        r = um(VERTICAL.format(n=961, grupo="MAG") + "Processo Matricula Nome Cargo Classe P/Classe\n"
               "SAD-PSE-2026/90063 900063-3 | PESSOA FICTICIA SESSENTA E TRES ROFESSOR DE EDUCACAO BAS A B\n"
               "SAD-PSE-2026/90064 900064-4 EDICARLOS FICTICIO DA SILVA ECNICO ADMINISTRATIVO B C\n"
               "SAD-PSE-2026/90065 900065-5 PESSOA FICTICIA SESSENTA E CINCO PROFESSOR DE EDUCACAO BAS C D\nPUBLIQUE-SE")
        d = r.decisoes
        self.assertEqual([(x.servidor, x.cargo) for x in d], [
            ("PESSOA FICTICIA SESSENTA E TRES", "ROFESSOR DE EDUCACAO BAS"),            # como lido: a letra não é reposta
            ("EDICARLOS FICTICIO DA SILVA", "ECNICO ADMINISTRATIVO"),                   # "EDIC…" no começo do nome não é cargo
            ("PESSOA FICTICIA SESSENTA E CINCO", "PROFESSOR DE EDUCACAO BAS")])
        self.assertTrue(any("primeira letra faltando" in p for p in d[0].detalhe["pendencias"]))
        self.assertTrue(any("primeira letra faltando" in p for p in d[1].detalhe["pendencias"]))
        self.assertNotIn("pendencias", d[2].detalhe)

    def test_nome_longo_sem_cargo_separado_e_sinalizado(self):
        r = um(VERTICAL.format(n=962, grupo="MAG") + "SAD-PSE-2026/90066 900066-6 PESSOA FICTICIA COM NOME MUITO COMPRIDO E UM XARGO ILEGIVEL QUALQUER A B\nPUBLIQUE-SE")
        self.assertIsNone(r.decisoes[0].cargo)
        self.assertTrue(any("nenhum cargo separado" in p for p in r.decisoes[0].detalhe["pendencias"]))

    def test_continuacao_do_nome_alinha_ao_texto_e_nao_ao_traco(self):
        p = []
        for i in range(4):
            topo = 100 + 16 * i
            p += celula(40, topo, f"SAD-PSE-2026/9000{i}") + [Palavra(150, 152, topo, "|")] + celula(156, topo, f"PESSOA FICTICIA NUMERO {i}")
            p += celula(330, topo, "PROFESSOR") + celula(480, topo, "A B")
        p += celula(156, 155, "JUNIOR")                                           # alinhado ao nome, não ao traço
        leitura = PG.ler_pagina_detalhada(p, 595)
        self.assertEqual(leitura.linhas_ambiguas, 0)
        self.assertEqual(leitura.texto.split("\n")[-1], "SAD-PSE-2026/90003 | PESSOA FICTICIA NUMERO 3 JUNIOR PROFESSOR A B")


class TesteNomeDaGerenciaLidoPorOcr(unittest.TestCase):
    def test_gediv_sem_a_conjuncao_continua_sendo_gediv_e_nao_outra_gerencia(self):
        # DEFEITO: "GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS VANTAGENS" (o OCR perdeu o "E") era tratada como OUTRA
        # gerência e o ato inteiro era excluído do escopo.
        texto = T.HORIZONTAL_GAJ.replace("DIREITOS E VANTAGENS", "DIREITOS VANTAGENS")
        r = um(texto)
        self.assertEqual((len(r.atos), len(r.decisoes), r.fora_escopo), (1, 3, []))
        self.assertEqual(r.atos[0].vinculo, "EXPRESSO")

    def test_outra_gerencia_continua_fora(self):
        r = um(T.OUTRA_GERENCIA)
        self.assertEqual((r.atos, r.decisoes), ([], []))


# ====================================================================================================================
# 2. Tabela pouco estruturada (nenhuma linha com três células)
# ====================================================================================================================
class TesteTabelaPoucoEstruturada(unittest.TestCase):
    def test_sem_geometria_suficiente_nada_e_associado_por_suposicao(self):
        # Só duas células por linha (processo+nome | cargo): a tabela não é reconhecida e o texto sai linha a linha,
        # exatamente como está no papel — nenhuma junção especulativa.
        p = []
        for i in range(3):
            p += celula(40, 100 + 20 * i, f"SAD-PSE-2026/9000{i} PESSOA FICTICIA {i}") + celula(330, 100 + 20 * i, "TECNICO")
            p += celula(330, 107 + 20 * i, "ADMINISTRATIVO")
        leitura = PG.ler_pagina_detalhada(p, 595)
        self.assertEqual((leitura.linhas_reconstruidas, leitura.linhas_ambiguas), (0, 0))
        self.assertEqual(len(leitura.texto.split("\n")), 6)

    def test_a_linha_solta_sinaliza_a_decisao_nos_dois_eixos(self):
        # DEFEITO: em Tempo de Serviço a linha de baixo era ignorada sem aviso (só a Progressão sinalizava).
        tempo = (CAB.format(n=950) + "O Diretor DEFERIU os processos de LICENÇA ESPECIAL:\n"
                 "SEC.EST.SAUDE SAD-PSE-2026/90051 9000051 PESSOA FICTICIA CINQUENTA E UM 90 01/02/1998 01/02/2003\n"
                 "DA SILVA SAURO\n"
                 "SEC.EST.SAUDE SAD-PSE-2026/90052 9000052 PESSOA FICTICIA CINQUENTA E DOIS 90 01/02/1998 01/02/2003\nPUBLIQUE-SE")
        r = um(tempo)
        self.assertEqual(len(r.decisoes), 2)                                       # nenhuma decisão a mais nem a menos
        self.assertIn("linha_quebrada", r.decisoes[0].detalhe)
        self.assertNotIn("linha_quebrada", r.decisoes[1].detalhe)
        self.assertEqual(r.decisoes[0].servidor, "PESSOA FICTICIA CINQUENTA E UM")  # nada colado por suposição
        progressao = um(VERTICAL.format(n=951, grupo="GAJ") + "SAD-PSE-2026/90053 900053-3 PESSOA FICTICIA TECNICO A B\n"
                        "ADMINISTRATIVO\nPUBLIQUE-SE")
        self.assertIn("linha_quebrada", progressao.decisoes[0].detalhe)

    def test_decisao_de_uma_linha_so_nao_e_sinalizada(self):
        self.assertTrue(all("linha_quebrada" not in d.detalhe for d in um(T.LICENCA_ESPECIAL).decisoes))


# ====================================================================================================================
# 3. OCR parcial em página que mistura texto nativo e imagem
# ====================================================================================================================
@unittest.skipUnless(TEM_PDF and TEM_PIL, "requer pdfplumber e Pillow")
class TesteOcrParcialEmPaginaMista(unittest.TestCase):
    def imagem(self, linhas):
        from PIL import Image, ImageDraw
        imagem = Image.new("L", (600, 300), 255)
        desenho = ImageDraw.Draw(imagem)
        for y in linhas:
            for x in range(30, 560, 12):
                desenho.rectangle((x, y, x + 7, y + 14), fill=0)
        return imagem

    def recorte(self, linhas):
        figura = self.imagem(linhas)

        class Imagem:
            original = figura

        class Recorte:
            def to_image(self, resolution):
                return Imagem
        return Recorte()

    def ocr_falso(self, lidas_na_primeira, relidas=()):
        """Simula o Tesseract: a 1ª chamada devolve as linhas `lidas_na_primeira`; as seguintes (releitura de uma faixa)
        devolvem uma palavra só se a faixa estiver em `relidas`."""
        chamadas = []

        def dados(imagem, config=""):
            chamadas.append(config)
            if len(chamadas) == 1:
                return {"text": ["texto"] * len(lidas_na_primeira), "conf": [95.0] * len(lidas_na_primeira),
                        "left": [30] * len(lidas_na_primeira), "top": list(lidas_na_primeira),
                        "width": [530] * len(lidas_na_primeira), "height": [14] * len(lidas_na_primeira)}
            achou = len(chamadas) - 2 in relidas
            return {"text": ["recuperada"] if achou else [""], "conf": [90.0] if achou else [-1], "left": [4], "top": [4], "width": [500], "height": [14]}
        return dados, chamadas

    def test_linha_que_o_ocr_do_trecho_nao_leu_e_relida_e_contada(self):
        # DEFEITO (limite da 05.3.4): a conferência de linhas não lidas só existia para páginas inteiras por OCR; um
        # trecho relido dentro de uma página nativa podia perder uma linha sem deixar sinal.
        dados, chamadas = self.ocr_falso([40, 120])                                # a linha do meio (y=80) não foi lida
        with mock.patch.object(leitor.ocr, "dados", dados):
            palavras, confiancas, sem_leitura = leitor._ocr_com_conferencia(self.recorte([40, 80, 120]), 300, (100.0, 200.0))
        self.assertEqual(sem_leitura, 1)
        self.assertEqual(chamadas[1], "--psm 7")                                   # tentou de novo só naquela faixa
        self.assertTrue(all(p.x0 >= 100.0 and p.topo >= 200.0 for p in palavras))  # posições na página, não no recorte

    def test_linha_recuperada_na_segunda_tentativa_nao_deixa_pendencia(self):
        dados, _ = self.ocr_falso([40, 120], relidas={0})
        with mock.patch.object(leitor.ocr, "dados", dados):
            palavras, _, sem_leitura = leitor._ocr_com_conferencia(self.recorte([40, 80, 120]), 300, (0.0, 0.0))
        self.assertEqual(sem_leitura, 0)
        self.assertIn("recuperada", [p.texto for p in palavras])

    def test_trecho_ilegivel_com_linha_perdida_deixa_a_pagina_pendente(self):
        sinais = "(cid:5)" * 12
        brutas = [{"x0": 20.0, "x1": 300.0, "top": 40.0 + 12 * i, "bottom": 46.0 + 12 * i, "text": sinais} for i in range(3)]
        brutas.append({"x0": 20.0, "x1": 80.0, "top": 500.0, "bottom": 508.0, "text": "Rodape"})
        proprio = self

        class Pagina:
            width, height = 595.0, 842.0

            def crop(self, caixa):
                return proprio.recorte([40, 80, 120])
        for lidas, esperado in (([40, 80, 120], "OK"), ([40, 120], "LEITURA_INCOMPLETA")):
            with self.subTest(lidas=lidas):
                dados, _ = self.ocr_falso(lidas)
                with mock.patch.object(leitor.ocr, "dados", dados), mock.patch.object(leitor.tabela_ocr, "ler_tabela", return_value=None):
                    leitor._blocos_ilegiveis.cache_clear() if hasattr(leitor._blocos_ilegiveis, "cache_clear") else None
                    pagina = leitor._reler_trechos_ilegiveis(1, Pagina(), brutas)
                self.assertEqual((pagina["metodo"], pagina["qualidade"]), ("TEXTO+OCR", esperado))
                self.assertIn("Rodape", pagina["texto"])                           # o texto nativo fica

    def test_tinta_sem_palavra_num_anuncio_nao_derruba_a_pagina_e_numa_tabela_digitalizada_sim(self):
        proprio = self

        class Pagina:
            width, height = 595.0, 842.0
            images = [{"x0": 40.0, "x1": 440.0, "top": 300.0, "bottom": 400.0}]

            def crop(self, caixa):
                return proprio.recorte([40, 80, 120])

        def ocr_da_regiao(quantas):
            def dados(imagem, config=""):
                if config:                                                          # releitura da faixa: nada
                    return {"text": [""], "conf": [-1], "left": [0], "top": [0], "width": [1], "height": [1]}
                return {"text": [f"palavra{i}" for i in range(quantas)], "conf": [92.0] * quantas, "left": [30 + 25 * (i % 20) for i in range(quantas)],
                        "top": [40 if i % 2 == 0 else 120 for i in range(quantas)], "width": [20] * quantas, "height": [14] * quantas}
            return dados
        with mock.patch.object(leitor.ocr, "dados", ocr_da_regiao(6)):              # anúncio: poucas palavras
            palavras, _, sem_leitura = leitor._ler_regioes_sem_texto(Pagina(), [])
        self.assertEqual((len(palavras), sem_leitura), (6, 0))
        with mock.patch.object(leitor.ocr, "dados", ocr_da_regiao(20)):             # região densa: é texto
            palavras, _, sem_leitura = leitor._ler_regioes_sem_texto(Pagina(), [])
        self.assertEqual((len(palavras), sem_leitura), (20, 1))


# ====================================================================================================================
# 4. Texto em contorno vetorial e imagem não examinada: sinalização
# ====================================================================================================================
class TesteContagemDeContornos(unittest.TestCase):
    def curva(self, x, topo, largura=4.0, altura=7.0):
        return {"x0": x, "x1": x + largura, "top": topo, "bottom": topo + altura}

    @unittest.skipUnless(TEM_PDF, "requer pdfplumber")
    def test_contornos_do_tamanho_de_letra_fora_de_palavras_sao_contados(self):
        letras = [self.curva(40 + 6 * i, 100) for i in range(50)]
        self.assertEqual(leitor.contornos_sem_texto(letras, []), 50)
        sob_palavra = [{"x0": 38.0, "x1": 345.0, "top": 98.0, "bottom": 109.0, "text": "x"}]
        self.assertEqual(leitor.contornos_sem_texto(letras, sob_palavra), 0)       # é o desenho da própria palavra
        self.assertEqual(leitor.contornos_sem_texto(letras[:20], []), 0)           # poucos: um ornamento
        grandes = [self.curva(40, 100, 200, 150) for _ in range(60)]               # brasão, moldura, mapa
        self.assertEqual(leitor.contornos_sem_texto(grandes, []), 0)

    @unittest.skipUnless(TEM_PDF, "requer pdfplumber")
    def test_regioes_de_contorno_sao_separadas_e_dizem_se_ha_texto_nativo_dentro(self):
        bloco_a = [self.curva(40 + 6 * i, 100 + 12 * linha) for linha in range(2) for i in range(30)]       # 40…220 × 100…119
        bloco_b = [self.curva(350 + 6 * i, 400) for i in range(60)]                                          # longe do primeiro
        solto = [self.curva(500, 700)]
        bloco_b += [self.curva(350 + 6 * i, 414) for i in range(60)]                                         # segunda linha
        palavra_dentro_de_b = [{"x0": 420.0, "x1": 440.0, "top": 409.7, "bottom": 410.3, "text": "x"}]       # entre as linhas
        regioes = leitor.regioes_de_contorno(bloco_a + bloco_b + solto, palavra_dentro_de_b)
        self.assertEqual([r[4] for r in regioes], [False, True])
        self.assertTrue(regioes[0][0] <= 40 and regioes[0][2] >= 220 and regioes[0][1] <= 100 and regioes[0][3] >= 119)
        self.assertGreaterEqual(regioes[1][0], 300)

    @unittest.skipUnless(TEM_PDF, "requer pdfplumber")
    def test_avisos_viram_inconsistencias_do_arquivo_com_as_paginas(self):
        paginas = [{"numero": 1, "avisos": []}, {"numero": 2, "avisos": [leitor.AVISO_CONTORNO]},
                   {"numero": 5, "avisos": [leitor.AVISO_CONTORNO, leitor.AVISO_IMAGEM]}, {"numero": 6}]
        self.assertEqual(leitor.avisos_do_arquivo(paginas),
                         ["IMAGEM_NAO_EXAMINADA: página(s) 5", "POSSIVEL_TEXTO_EM_CONTORNO: página(s) 2, 5"])


@unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab")
class TesteSinalizacaoNaCadeia(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)

    def pdf(self, desenhar) -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        memoria = io.BytesIO()
        c = canvas.Canvas(memoria, pagesize=A4)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, 800, "DIÁRIO OFICIAL Nº 18.700")
        c.setFont("Helvetica", 9)
        c.drawString(40, 786, "João Pessoa - Quinta-feira, 08 de Outubro de 2026")
        for i, linha in enumerate(T.LICENCA_ESPECIAL.split("\n")):
            c.drawString(40, 760 - 11 * i, linha[:120])
        desenhar(c)
        c.save()
        caminho = self.raiz / "diario-oficial-08-10-2026-portal.pdf"
        caminho.write_bytes(memoria.getvalue())
        return caminho

    def executar(self, arquivo):
        from observatorio.nucleo.banco import Banco
        from observatorio.operacao import fluxo
        r = fluxo.executar(self.raiz / "dados", arquivo)
        banco = Banco(self.raiz / "dados" / "observatorio.sqlite3")
        self.addCleanup(banco.fechar)
        return r, banco.con.execute("SELECT situacao, inconsistencias FROM leitura").fetchone()

    def test_texto_desenhado_como_contorno_deixa_o_arquivo_com_pendencia(self):
        # DEFEITO (limite da 05.3.4): um trecho desenhado letra a letra como curva não tinha caractere nem imagem; a
        # página saía "OK" e o arquivo "LIDA", sem nenhum sinal de que havia algo que não foi lido.
        contornos = self.contornos
        # Sem OCR (ou quando a região envolve texto nativo) não há leitura segura: o arquivo fica com pendência.
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            r, leitura = self.executar(self.pdf(contornos))
        self.assertEqual((r["resultado"]["codigo"], leitura["situacao"]), (3, "LIDA_COM_PENDENCIAS"))
        self.assertIn("POSSIVEL_TEXTO_EM_CONTORNO: página(s) 1", leitura["inconsistencias"])
        self.assertEqual(r["classificacao"]["decisoes"], 1)                        # o que foi lido segue adiante

    @staticmethod
    def contornos(c):
        if True:
            for linha in range(3):
                for i in range(40):
                    x, y = 60 + 9 * i, 300 - 14 * linha
                    letra = c.beginPath()                                           # um "A": contorno fechado, como um glifo
                    letra.moveTo(x, y)
                    letra.lineTo(x + 3, y + 8)
                    letra.curveTo(x + 4, y + 8, x + 5, y + 4, x + 6, y)
                    letra.close()
                    c.drawPath(letra, stroke=1, fill=0)

    def test_regiao_em_contorno_sem_texto_nativo_dentro_e_lida_por_ocr_so_ali(self):
        # Caso real (07/11/2026, p. 6): uma resenha inteira da GEDIV desenhada em contorno. Aqui os contornos são
        # sintéticos e o Tesseract é simulado (o que se confere é o caminho: a região certa vai ao OCR, as palavras
        # voltam para a posição certa da página e o aviso deixa de ser necessário).
        recortes = []
        original_crop = None

        def dados(imagem, config=""):
            recortes.append(imagem.size)
            if config:
                return {"text": [""], "conf": [-1], "left": [0], "top": [0], "width": [1], "height": [1]}
            palavras = ["SAD-PSE-2026/90061", "9000061", "PESSOA", "FICTICIA", "SESSENTA"]
            return {"text": palavras, "conf": [93.0] * 5, "left": [10 + 150 * i for i in range(5)], "top": [20] * 5,
                    "width": [140] * 5, "height": [30] * 5}
        import pdfplumber
        with pdfplumber.open(str(self.pdf(self.contornos))) as d:
            pagina = d.pages[0]
            regioes = leitor.regioes_de_contorno(pagina.curves, pagina.extract_words())
            self.assertEqual([r[4] for r in regioes], [False])                     # uma região, sem texto nativo dentro
            with mock.patch.object(leitor, "ocr_disponivel", return_value=(True, "simulado")), mock.patch.object(leitor.ocr, "dados", dados), \
                    mock.patch.object(leitor, "_ler_sobreposicoes", return_value=0):
                lida = leitor._ler_uma_pagina(1, pagina)
        self.assertEqual((lida["metodo"], lida["qualidade"], lida["avisos"]), ("TEXTO+OCR", "OK", []))
        self.assertIn("SAD-PSE-2026/90061 9000061 PESSOA FICTICIA SESSENTA", lida["texto"])
        self.assertIn("LICENÇA ESPECIAL", lida["texto"].upper())                   # o texto nativo fica
        self.assertLess(recortes[0][1], 600)                                       # foi ao OCR só a região, não a página

    def test_documento_sem_contornos_continua_lido_sem_ressalva(self):
        r, leitura = self.executar(self.pdf(lambda c: c.line(40, 300, 500, 300)))
        self.assertEqual((r["resultado"]["codigo"], leitura["situacao"]), (0, "LIDA"))

    @unittest.skipUnless(TEM_PIL, "requer Pillow")
    def test_sem_tesseract_a_imagem_pequena_nao_examinada_fica_visivel(self):
        # DEFEITO (limite da 05.3.4): sem OCR, imagem abaixo de 25% da página não era examinada e nada indicava isso.
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        figura = Image.new("RGB", (400, 100), "white")
        arquivo = self.pdf(lambda c: c.drawImage(ImageReader(figura), 40, 250, width=400, height=100))
        with mock.patch.object(leitor, "ocr_disponivel", return_value=(False, "simulado")):
            r, leitura = self.executar(arquivo)
        self.assertEqual((r["resultado"]["codigo"], leitura["situacao"]), (3, "LIDA_COM_PENDENCIAS"))
        self.assertIn("IMAGEM_NAO_EXAMINADA: página(s) 1", leitura["inconsistencias"])


if __name__ == "__main__":
    unittest.main()
