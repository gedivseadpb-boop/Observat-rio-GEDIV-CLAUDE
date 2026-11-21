"""Referências documentais e limites de coluna; somente publicações/pessoas fictícias."""
import io
import json
import unittest
import zipfile
import xml.etree.ElementTree as ET

from observatorio.gerencias.gediv import classificador as K, processo
from observatorio.leitura import pagina as P
from observatorio.painel import exportacao, indicadores
from tests import test_painel as TP


def linha(x, y, texto):
    palavras = []
    for palavra in texto.split():
        largura = 3.5 * len(palavra)
        palavras.append(P.Palavra(x, x + largura, y, palavra))
        x += largura + 2
    return palavras


def paralelas(referencia=False, continuacao=False, titulo_inteiro=False):
    # O texto comum termina antes do título justificado. A faixa de baixa ocupação
    # inclui a borda da palavra longa do título, mas existe um corredor mais vazio.
    p = [P.Palavra(20, 55, 30, 'PORTARIA'), P.Palavra(60, 67, 30, 'Nº'),
         P.Palavra(250, 307, 30, '9301/2099-DEREH')]
    p += linha(330, 30, 'CONTINUAÇÃO' if continuacao else 'Nº da Resenha: 9302/2099')
    corpo = 'O Diretor resolve TORNAR SEM EFEITO a licença especial.'
    if referencia:
        corpo = 'RESOLVE: TORNAR SEM EFEITO a licença especial da Resenha nº 9300/2099.'
    esquerda = ['DIRETORIA EXECUTIVA DE RECURSOS HUMANOS', corpo,
                'Continua na próxima coluna.' if continuacao else 'PUBLIQUE-SE']
    esquerda += ['Texto complementar fictício desta coluna sem outro ato.'] * 12
    direita = (['Referência expressa: Resenha nº 9300/2099.', 'PUBLIQUE-SE'] if continuacao else
               ['SECRETARIA DE ESTADO DA ADMINISTRAÇÃO', 'DIRETORIA EXECUTIVA DE RECURSOS HUMANOS',
                'GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS',
                'De acordo com laudo da perícia médica, DEFERIU pedidos de LICENÇA SAÚDE.', 'PUBLIQUE-SE'])
    direita += ['Texto complementar fictício da outra coluna.'] * (15 - len(direita))
    for i, (a, b) in enumerate(zip(esquerda, direita)):
        p += linha(20, 42 + i * 12, a) + linha(330, 42 + i * 12, b)
    if titulo_inteiro:
        p += [P.Palavra(100, 500, 10, 'TÍTULO GERAL DA PÁGINA')]
    return p


def ler(palavras):
    return P.ler_pagina(palavras, 600)[0]


class ReferenciaEntreColunas(unittest.TestCase):
    def test_cabecalhos_paralelos_nao_sao_uma_linha(self):
        texto = ler(paralelas())
        self.assertFalse(any('PORTARIA' in l and '9302/2099' in l for l in texto.splitlines()))
        self.assertIn('Nº da Resenha: 9302/2099', texto.splitlines())

    def test_evento_nao_herda_cabecalho_medico_da_coluna_vizinha(self):
        r = K.classificar([(1, ler(paralelas()))], 'a' * 64)
        self.assertEqual(len(r.eventos), 1)
        self.assertEqual(r.eventos[0].resenhas_citadas, [])
        self.assertNotIn('9302/2099', r.eventos[0].texto)
        self.assertNotIn('laudo', r.atos[0].texto.lower())
        self.assertEqual([(x.numero, x.motivo) for x in r.fora_escopo], [('9302/2099', 'LICENCA_SAUDE')])

    def test_referencia_expressa_no_corpo_e_preservada(self):
        r = K.classificar([(1, ler(paralelas(referencia=True)))], 'a' * 64)
        self.assertEqual(r.eventos[0].resenhas_citadas, ['9300/2099'])
        self.assertNotIn('9302/2099', r.eventos[0].texto)

    def test_remissao_legitima_na_continuacao_da_coluna(self):
        r = K.classificar([(1, ler(paralelas(continuacao=True)))], 'a' * 64)
        self.assertEqual(len(r.eventos), 1)
        self.assertEqual(r.eventos[0].resenhas_citadas, ['9300/2099'])

    def test_titulo_real_de_largura_total_continua_inteiro(self):
        texto = ler(paralelas(titulo_inteiro=True))
        self.assertEqual(texto.splitlines()[0], 'TÍTULO GERAL DA PÁGINA')
        r = K.classificar([(1, texto)], 'a' * 64)
        self.assertEqual(r.eventos[0].resenhas_citadas, [])

    def test_marcas_esparsas_no_corredor_nao_fundem_cabecalhos(self):
        palavras = paralelas()
        palavras += [P.Palavra(215, 250, 42 + i * 12, 'complemento') for i in range(15)]
        palavras += [P.Palavra(x, x + 2, 150 + i * 12, '*') for i, x in enumerate([310, 316, 322, 328])]
        r = K.classificar([(1, ler(palavras))], 'a' * 64)
        self.assertEqual(r.eventos[0].resenhas_citadas, [])
        self.assertEqual(r.fora_escopo[0].numero, '9302/2099')

    def test_regra_independe_de_coordenadas_e_escala_fixas(self):
        for escala, margem in [(0.75, 0), (1, 8), (1.25, 15)]:
            with self.subTest(escala=escala, margem=margem):
                palavras = [P.Palavra(w.x0 * escala + margem, w.x1 * escala + margem, w.topo, w.texto)
                            for w in paralelas()]
                texto = P.ler_pagina(palavras, 600 * escala + 2 * margem)[0]
                self.assertEqual(K.classificar([(1, texto)], 'a' * 64).eventos[0].resenhas_citadas, [])

    def test_continuacao_de_tabela_em_outra_pagina_preserva_linhas(self):
        cab = ('SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nRESENHA Nº 9303/2099-DEREH/GS/SEAD\n'
               'GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n'
               'DEFERIU os processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo MAG\n')
        paginas = [(1, cab + 'SAD-PSE-2099/99001 999001-0 PESSOA FICTICIA UM PROFESSOR A B'),
                   (2, 'RESENHA Nº 9303/2099-DEREH/GS/SEAD (continuação)\n'
                       'SAD-PSE-2099/99002 999002-0 PESSOA FICTICIA DOIS PROFESSOR B C\nPUBLIQUE-SE')]
        r = K.classificar(paginas, 'b' * 64)
        self.assertEqual(len(r.atos), 1)
        self.assertEqual(r.atos[0].pagina_final, 2)
        self.assertEqual([d.processo for d in r.decisoes], ['SAD-PSE-2099/99001', 'SAD-PSE-2099/99002'])
        self.assertEqual([d.detalhe['classe_posterior'] for d in r.decisoes], ['B', 'C'])

    def test_remissao_expressa_em_outra_pagina_e_preservada(self):
        r = K.classificar([(1, 'PORTARIA Nº 9301/2099-DEREH\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS\n'
                               'TORNAR SEM EFEITO a licença especial. Continua na próxima página.'),
                           (2, 'Continuação da portaria. Referência expressa: Resenha nº 9300/2099.\nPUBLIQUE-SE')],
                          'c' * 64)
        self.assertEqual(r.eventos[0].resenhas_citadas, ['9300/2099'])

    def test_homonima_pbprev_nao_e_admitida_como_gediv(self):
        gediv = ('SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nRESENHA Nº 9304/2099-DEREH/GS/SEAD\n'
                 'GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n'
                 'DEFERIU os processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo MAG\n'
                 'SAD-PSE-2099/99003 999003-0 PESSOA FICTICIA TRES PROFESSOR A B\nPUBLIQUE-SE')
        pbprev = ('PARAÍBA PREVIDÊNCIA\nRESENHA/PBPREV/GP/Nº 09304/2099\n'
                  'O PRESIDENTE INDEFERIU a revisão de aposentadoria.\nPUBLIQUE-SE')
        r = K.classificar([(1, gediv), (2, pbprev)], 'd' * 64)
        self.assertEqual([(a.numero, a.pagina) for a in r.atos], [('9304/2099', 1)])
        self.assertEqual(len(r.decisoes), 1)


class PersistenciaEExportacao(TP.Base):
    def preparar(self):
        texto = ler(paralelas()) + ('\nSECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nRESENHA Nº 9303/2099-DEREH/GS/SEAD\n'
                 'GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n'
                 'DEFERIU os processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo MAG\n'
                 'SAD-PSE-2099/99004 999004-0 PESSOA FICTICIA QUATRO PROFESSOR A B\nPUBLIQUE-SE')
        TP.carregar(self.banco, 'a', '2099-03-02', texto)
        processo.classificar_pendentes(self.banco)

    def test_sem_referencia_inequivoca_evento_fica_pendente(self):
        self.preparar()
        e = self.banco.con.execute('SELECT * FROM evento').fetchone()
        self.assertEqual(json.loads(e['resenhas_citadas']), [])
        self.assertEqual(e['estado'], 'PENDENTE_VINCULACAO')
        self.assertIsNone(e['ato_original_id'])
        self.assertIsNone(e['ato_sugerido_id'])
        self.assertIsNone(e['revisor'])
        self.assertEqual(self.banco.con.execute('PRAGMA user_version').fetchone()[0], 8)

    def test_publico_exclui_pendentes_e_exportacao_nao_inventa_vinculo(self):
        self.preparar()
        publico = self.painel(perfil=indicadores.PUBLICO, escopo='pendente')
        self.assertEqual(publico['linhas'], [])
        self.assertEqual(publico['eventos'], [])
        self.assertEqual(publico['indicadores']['decisoes'], 0)
        privado = self.painel(escopo='pendente')
        self.assertEqual(len(privado['linhas']), 1)
        self.assertEqual(privado['linhas'][0]['validacao'], 'PENDENTE')
        self.assertEqual(privado['eventos'][0]['resenhas_citadas'], [])
        self.assertIsNone(privado['eventos'][0]['ato_original_id'])
        with zipfile.ZipFile(io.BytesIO(exportacao.planilha(privado))) as z:
            eventos = ET.fromstring(z.read('xl/worksheets/sheet3.xml'))
        texto = ' '.join(eventos.itertext())
        self.assertNotIn('9302/2099', texto)
        self.assertIn('PENDENTE_VINCULACAO', texto)
        csv = exportacao.csv(exportacao.linhas_decisoes(privado)).decode('utf-8-sig')
        self.assertNotIn('9302/2099', csv)
