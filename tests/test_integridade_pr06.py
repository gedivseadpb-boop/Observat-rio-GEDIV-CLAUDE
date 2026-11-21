"""Regressões de integridade PR06. Dados e documentos inteiramente sintéticos."""
import io
import json
import csv
import threading
import urllib.request
import zipfile
from datetime import date
from unittest import mock

from observatorio.coleta import coletor, inventario
from observatorio.gerencias.gediv import catalogo as C, processo
from observatorio.leitura import leitor
from observatorio.nucleo import banco as B
from observatorio.nucleo.acervo import Acervo
from observatorio.operacao import fluxo, saida
from observatorio.painel import indicadores, exportacao
from observatorio.revisao import servico
from observatorio.web.servidor import criar_servidor
from tests import test_painel as TP, textos_doe as T
from tests.apoio import pdf_sintetico
from tests.test_leitura_banco_revisao import pag


class TesteRevisoes(TP.Base):
    def setUp(self):
        super().setUp()
        self.sha = TP.carregar(self.banco, 'a', '2026-10-09', T.HORIZONTAL_GAJ)
        processo.classificar_pendentes(self.banco)
        self.d = self.banco.con.execute('SELECT * FROM decisao ORDER BY rowid').fetchone()

    def revisao(self, acao, campo, valor):
        servico.revisar_decisoes(self.banco, [self.d['id']], acao, TP.REVISOR, TP.JUST, True, True, {campo: valor})

    def test_d01_correcao_pendente_sobrevive_reclassificacao_divergente(self):
        self.revisao(servico.REABRIR, 'cargo', 'CARGO REVISTO')
        novo = processo.classificar([(1, T.HORIZONTAL_GAJ)], self.sha)
        next(d for d in novo.decisoes if d.id == self.d['id']).cargo = 'CARGO DIVERGENTE'
        for _ in range(2):
            self.banco.gravar_classificacao('GEDIV', self.sha, C.VERSAO_REGRAS, '2026-10-09', novo)
        d = self.banco.con.execute('SELECT * FROM decisao WHERE id = ?', (self.d['id'],)).fetchone()
        self.assertEqual((d['validacao'], d['cargo']), ('PENDENTE', 'CARGO REVISTO'))
        conflitos = self.banco.conflitos(alvo_tipo='decisao', alvo_ids=[self.d['id']])
        self.assertEqual(len([c for c in conflitos if c['campo'] == 'cargo']), 1)
        self.assertEqual(len(self.banco.correcoes('decisao', self.d['id'])), 1)
        self.assertEqual(len(self.banco.trilha('decisao', self.d['id'])), 1)

    def test_d01_conferida_rejeitada_e_reaberta_preservam_correcao(self):
        self.revisao(servico.CONFERIR, 'cargo', 'CARGO REVISTO')
        novo = processo.classificar([(1, T.HORIZONTAL_GAJ)], self.sha)
        next(d for d in novo.decisoes if d.id == self.d['id']).cargo = 'CARGO DIVERGENTE'
        for acao, estado in ((None, 'CONFERIDO'), (servico.REJEITAR, 'REJEITADO'), (servico.REABRIR, 'PENDENTE')):
            if acao:
                servico.revisar_decisoes(self.banco, [self.d['id']], acao, TP.REVISOR, TP.JUST)
            self.banco.gravar_classificacao('GEDIV', self.sha, C.VERSAO_REGRAS, '2026-10-09', novo)
            d = self.banco.con.execute('SELECT validacao, cargo FROM decisao WHERE id = ?', (self.d['id'],)).fetchone()
            self.assertEqual(tuple(d), (estado, 'CARGO REVISTO'))
            self.assertEqual(len([c for c in self.banco.conflitos() if c['alvo_id'] == self.d['id'] and c['campo'] == 'cargo']), 1)

    def test_d02_nulo_vazio_ausente_e_literal(self):
        self.revisao(servico.REABRIR, 'cargo', None)
        d = self.banco.con.execute('SELECT * FROM decisao WHERE id = ?', (self.d['id'],)).fetchone()
        self.assertIsNone(d['cargo'])
        self.assertEqual(json.loads(self.banco.correcoes('decisao', d['id'])[-1]['valor_corrigido']), None)
        self.revisao(servico.REABRIR, 'cargo', 'None')
        self.assertEqual(self.banco.con.execute('SELECT cargo FROM decisao WHERE id = ?', (d['id'],)).fetchone()[0], 'None')
        self.revisao(servico.REABRIR, 'cargo', '')
        self.assertIsNone(self.banco.con.execute('SELECT cargo FROM decisao WHERE id = ?', (d['id'],)).fetchone()[0])
        servico.revisar_decisoes(self.banco, [d['id']], servico.REABRIR, TP.REVISOR, TP.JUST)
        self.assertIsNone(self.banco.con.execute('SELECT cargo FROM decisao WHERE id = ?', (d['id'],)).fetchone()[0])
        ato = self.banco.con.execute('SELECT * FROM ato WHERE id = ?', (d['ato_id'],)).fetchone()
        servico.corrigir_ato(self.banco, ato['id'], {'eixo': C.TEMPO, 'grupo': None, 'modalidade': None,
                                                  'condicao': None, 'subcategoria': 'TS-01'}, TP.REVISOR, TP.JUST, True)
        self.assertIsNone(self.banco.con.execute('SELECT grupo FROM ato WHERE id = ?', (ato['id'],)).fetchone()[0])

    def test_d02_api_exportacao_e_auditoria_preservam_null(self):
        self.revisao(servico.CONFERIR, 'cargo', 'VALOR ANTIGO SINTETICO')
        token = 'credencial-sintetica-de-teste-12345'
        servidor = criar_servidor(self.pasta, token, porta=0)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        url = f'http://127.0.0.1:{servidor.server_address[1]}'
        corpo = {'alvo': 'decisao', 'id': self.d['id'], 'decisao': 'CONFERIR', 'responsavel': TP.REVISOR,
                 'justificativa': TP.JUST, 'confirma_fonte': True, 'confirma_vinculo': True, 'correcoes': {'cargo': None}}
        req = urllib.request.Request(url + '/api/revisao', data=json.dumps(corpo).encode(),
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as resposta:
            self.assertEqual(resposta.status, 200)
        def get(caminho, credencial=False):
            req = urllib.request.Request(url + caminho, headers={'Authorization': 'Bearer ' + token} if credencial else {})
            with urllib.request.urlopen(req, timeout=5) as resposta:
                return resposta.read()
        privado = json.loads(get('/api/painel', True))
        self.assertIsNone(next(l for l in privado['linhas'] if l['id'] == self.d['id'])['cargo'])
        publico = get('/api/painel').decode()
        self.assertNotIn('VALOR ANTIGO SINTETICO', publico)
        linhas = list(csv.reader(io.StringIO(get('/api/exportar?formato=csv', True).decode('utf-8-sig')), delimiter=';'))
        cargo, ident = linhas[0].index('Cargo'), linhas[0].index('ID da decisão')
        self.assertEqual(next(l for l in linhas[1:] if l[ident] == self.d['id'])[cargo], '')
        historico = self.banco.correcoes('decisao', self.d['id'])
        self.assertEqual(json.loads(historico[-1]['valor_corrigido']), None)
        self.assertEqual(json.loads(historico[-1]['valor_anterior']), 'VALOR ANTIGO SINTETICO')

    def test_d05_classificacao_obsoleta_nao_e_contada_silenciosamente(self):
        servico.revisar_decisoes(self.banco, [self.d['id']], servico.CONFERIR, TP.REVISOR, TP.JUST, True, True)
        self.assertEqual(indicadores.painel(self.banco)['indicadores']['decisoes'], 1)
        self.banco.registrar_leitura(self.sha, 'LIDA', 'v2', [pag(1, T.HORIZONTAL_GAJ + '\nTEXTO ADICIONAL')], '1', '2026-10-09', None)
        painel = indicadores.painel(self.banco)
        self.assertEqual(painel['indicadores']['decisoes'], 0)
        self.assertGreater(painel['apoio']['classificacoes_desatualizadas'], 0)
        self.assertEqual(self.banco.con.execute('SELECT validacao FROM decisao WHERE id = ?', (self.d['id'],)).fetchone()[0], 'CONFERIDO')
        processo.classificar_pendentes(self.banco)
        self.assertEqual(indicadores.painel(self.banco)['indicadores']['decisoes'], 1)

    def test_d05_vinculo_de_classificacao_ausente_nao_e_inventado_na_reabertura(self):
        servico.revisar_decisoes(self.banco, [self.d['id']], servico.CONFERIR, TP.REVISOR, TP.JUST, True, True)
        with self.banco.con:
            self.banco.con.execute('UPDATE classificacao SET revisao_leitura = NULL WHERE sha256 = ?', (self.sha,))
        outro = B.Banco(self.pasta / 'observatorio.sqlite3')
        try:
            self.assertIsNone(outro.con.execute('SELECT revisao_leitura FROM classificacao WHERE sha256 = ?', (self.sha,)).fetchone()[0])
            self.assertEqual(indicadores.painel(outro)['indicadores']['decisoes'], 0)
            self.assertEqual(len(outro.arquivos_sem_classificacao('GEDIV', C.VERSAO_REGRAS)), 1)
        finally:
            outro.fechar()

    def test_d05_regras_obsoletas_e_conflito_visiveis_no_painel_e_na_planilha(self):
        servico.revisar_decisoes(self.banco, [self.d['id']], servico.CONFERIR, TP.REVISOR, TP.JUST, True, True)
        with self.banco.con:
            self.banco._conflito('decisao', self.d['id'], 'cargo', self.d['cargo'], 'DIVERGENTE', 'TESTE')
        publico = indicadores.painel(self.banco)
        self.assertEqual(publico['indicadores']['decisoes'], 1)
        self.assertEqual(publico['apoio']['decisoes_conferidas_com_conflito'], 1)
        self.assertTrue(publico['resenhas'][0]['conflito_aberto'])
        privado = indicadores.painel(self.banco, perfil=indicadores.GERENCIA_PERFIL)
        self.assertTrue(privado['linhas'][0]['conflito_aberto'])
        linhas = exportacao.linhas_decisoes(privado)
        coluna_conflito = linhas[0].index('Conflito aberto')
        self.assertEqual(coluna_conflito, 26)  # Posição histórica, antes das colunas documentais.
        self.assertEqual(linhas[1][coluna_conflito], 'SIM')
        with zipfile.ZipFile(io.BytesIO(exportacao.planilha(privado))) as z:
            self.assertIn('conflito aberto', z.read('xl/worksheets/sheet5.xml').decode())
        conflito = self.banco.conflitos()[0]
        servico.resolver_conflito(self.banco, conflito['id'], servico.MANTER, TP.REVISOR, TP.JUST)
        self.assertEqual(indicadores.painel(self.banco)['apoio']['decisoes_conferidas_com_conflito'], 0)
        with self.banco.con:
            self.banco.con.execute("UPDATE classificacao SET versao_regras = 'REGRAS_ANTIGAS' WHERE sha256 = ?", (self.sha,))
        publico = indicadores.painel(self.banco)
        self.assertEqual(publico['indicadores']['decisoes'], 0)
        self.assertEqual(publico['apoio']['classificacoes_desatualizadas'], 1)
        self.assertIn('desatualizada', publico['meta']['cobertura']['parecer'])
        processo.classificar_pendentes(self.banco)
        self.assertEqual(indicadores.painel(self.banco)['indicadores']['decisoes'], 1)

    def test_d07_inconsistencia_nova_na_leitura_neutra_tem_retomada(self):
        self.banco.registrar_leitura(self.sha, 'LIDA_COM_PENDENCIAS', leitor.VERSAO,
                                    [pag(1, T.HORIZONTAL_GAJ)], '1', '2026-10-09', None, ['DATA_DIVERGENTE'])
        atual = self.banco.con.execute('SELECT * FROM leitura WHERE sha256=?', (self.sha,)).fetchone()
        self.assertEqual(atual['situacao'], 'LIDA_COM_PENDENCIAS')
        self.assertIn(self.sha, [a['sha256'] for a in self.banco.arquivos_sem_leitura(leitor.VERSAO, True)])
        self.assertIn('DATA_DIVERGENTE', atual['inconsistencias'])
        self.banco.registrar_leitura(self.sha, 'LIDA', leitor.VERSAO, [pag(1, T.HORIZONTAL_GAJ)], '1', '2026-10-09', None, [])
        self.assertEqual(self.banco.con.execute('SELECT situacao FROM leitura WHERE sha256=?', (self.sha,)).fetchone()[0], 'LIDA')
        self.assertNotIn(self.sha, [a['sha256'] for a in self.banco.arquivos_sem_leitura(leitor.VERSAO, True)])

    def test_d04_pendencia_persistida_nao_vira_sucesso(self):
        with self.banco.con:
            self.banco.con.execute("UPDATE leitura SET situacao='LIDA_COM_PENDENCIAS', paginas_com_pendencia=1, versao_leitor=? WHERE sha256=?", (leitor.VERSAO, self.sha))
        r = fluxo.executar(self.pasta)
        self.assertEqual(r['leitura']['na_fila'], 0)
        self.assertEqual(r['resultado']['codigo'], saida.CONCLUIDO_COM_PENDENCIAS)
        self.assertEqual(r['escopo']['fontes_e_periodos_da_base'][0]['fonte'], 'manual')

    def test_d04_conflito_aberto_e_resolvido_muda_status(self):
        with self.banco.con:
            self.banco.con.execute('UPDATE leitura SET versao_leitor = ? WHERE sha256 = ?', (leitor.VERSAO, self.sha))
            self.banco._conflito('decisao', self.d['id'], 'cargo', self.d['cargo'], 'DIVERGENTE', 'TESTE')
        self.assertEqual(fluxo.executar(self.pasta)['resultado']['codigo'], saida.CONCLUIDO_COM_PENDENCIAS)
        conflito = self.banco.conflitos()[0]
        servico.resolver_conflito(self.banco, conflito['id'], servico.MANTER, TP.REVISOR, TP.JUST)
        self.assertEqual(fluxo.executar(self.pasta)['resultado']['codigo'], saida.SUCESSO)


class TesteAcervo(TP.Base):
    def test_d03_mesmo_tamanho_divergente_nao_e_completo(self):
        acervo = Acervo(self.pasta / 'acervo')
        dados = pdf_sintetico('UM')
        outro = pdf_sintetico('DO')
        self.assertEqual(len(dados), len(outro))
        r = coletor.importar_manual(self.banco, acervo, dados, date(2026, 10, 9), 'manual:um', 'um.pdf')
        self.assertTrue(r['aceito'])
        self.banco.registrar_varredura('manual', 2026, 10, 1, None)
        def cobertura():
            return inventario.cobertura(self.banco, date(2026, 10, 9), date(2026, 10, 9), ['manual'], acervo)[0]
        self.assertEqual(cobertura()['situacao'], 'COMPLETO')
        acervo.caminho(r['sha256']).write_bytes(outro)
        self.assertNotEqual(cobertura()['situacao'], 'COMPLETO')
        self.assertEqual(coletor.reconciliar(self.banco, acervo)['reobter'], 1)
        self.assertNotEqual(cobertura()['situacao'], 'COMPLETO')
        self.assertTrue(self.banco.trilha('publicacao'))
        # Preserva os bytes divergentes fora do acervo endereçado por hash e restaura o original.
        quarentena = self.pasta / 'substituicao-sintetica.pdf'
        acervo.caminho(r['sha256']).rename(quarentena)
        self.assertEqual(quarentena.read_bytes(), outro)
        restaurado = coletor.importar_manual(self.banco, acervo, dados, date(2026, 10, 9), 'manual:um', 'um.pdf')
        self.assertTrue(restaurado['aceito'])
        self.assertEqual(cobertura()['situacao'], 'COMPLETO')
        nova = coletor.importar_manual(self.banco, acervo, outro, date(2026, 10, 9), 'manual:um', 'um.pdf')
        self.assertTrue(nova['aceito'])
        pub = self.banco.publicacao('manual', 'manual:um')
        self.assertEqual(len(self.banco.versoes(pub['id'])), 2)
        self.assertTrue(acervo.conferir(r['sha256']))
        self.assertTrue(acervo.conferir(nova['sha256']))

    def test_d03_arquivo_ausente_nao_e_completo(self):
        acervo = Acervo(self.pasta / 'acervo')
        r = coletor.importar_manual(self.banco, acervo, pdf_sintetico('AUSENTE'), date(2026, 10, 9), 'manual:x', 'x.pdf')
        self.banco.registrar_varredura('manual', 2026, 10, 1, None)
        acervo.caminho(r['sha256']).unlink()
        linha = inventario.cobertura(self.banco, date(2026, 10, 9), date(2026, 10, 9), ['manual'], acervo)[0]
        self.assertNotEqual(linha['situacao'], 'COMPLETO')
        self.assertEqual(coletor.reconciliar(self.banco, acervo)['reobter'], 1)
