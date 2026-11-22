"""PR09: somente identidades e valores fictícios; CI sem Paddle/pesos/downloads."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from observatorio.gerencias.gediv import paddle_complementar as P, processo
from observatorio.gerencias.gediv.paddle_worker import montar
from observatorio.nucleo import banco as B
from observatorio.painel import indicadores
from observatorio.revisao import servico
from tests import test_painel as TP, textos_doe as T


def decisao(**extras):
    d = dict(pagina=3, processo='SAD-PSE-2026/99001', matricula='990001-2', servidor='PESSOA FICTICIA',
             cargo='CARGO FICTICIO', detalhe='{}')
    d.update(extras)
    return d


def candidato(**extras):
    c = dict(pagina=3, processo='SAD-PSE-2026/99001', matricula='990001-2', nome='PESSOA FICTICIA',
             cargo='CARGO FICTICIO', classe_anterior='A', classe_posterior='B', confiancas=[.99]*4,
             geometria_segura=True, bbox_pdf=[30,40,300,60])
    c.update(extras)
    return c


class Avaliacao(unittest.TestCase):
    def test_par_totalmente_ausente(self):
        d = decisao(); a = copy.deepcopy(d)
        n,s,_,_ = P.avaliar(d,[candidato()])
        self.assertEqual((n['classe_anterior'],n['classe_posterior'],s),('A','B','RECUPERADO'))
        self.assertEqual(d,a)
        self.assertEqual(n['paddleocr']['modelos'], P.MODELOS)

    def test_classe_vazia_e_mesma_semantica_de_ausencia(self):
        n,s,_,_=P.avaliar(decisao(detalhe='{"classe_anterior":"","classe_posterior":" "}'),[candidato()])
        self.assertEqual(s,'RECUPERADO')

    def test_evolucao_regressiva_ou_igual_e_apenas_sinalizada(self):
        for a,b in [('B','A'),('A','A')]:
            n,s,m,_=P.avaliar(decisao(),[candidato(classe_anterior=a,classe_posterior=b)])
            self.assertNotIn('classe_anterior',n)
            self.assertEqual(m,'PADDLE_EVOLUCAO_INSEGURA')

    def test_par_parcial_nao_e_completado(self):
        n,s,_,_ = P.avaliar(decisao(detalhe='{"classe_anterior":"A"}'),[candidato()])
        self.assertNotIn('classe_posterior',n)
        self.assertEqual(s,'APENAS SINALIZADO')

    def test_classe_existente_conflitante_preservada(self):
        n,s,m,c = P.avaliar(decisao(detalhe='{"classe_anterior":"C","classe_posterior":"D"}'),[candidato()])
        self.assertEqual((n['classe_anterior'],n['classe_posterior']),('C','D'))
        self.assertEqual((s,m,len(c)),('APENAS SINALIZADO','PADDLE_DIVERGENCIA_CLASSES',2))

    def test_existente_igual_nao_recebe_origem_inventada(self):
        n,s,_,_ = P.avaliar(decisao(detalhe='{"classe_anterior":"A","classe_posterior":"B"}'),[candidato()])
        self.assertNotEqual(s,'RECUPERADO')

    def test_associacao_duplicada_e_ausente(self):
        for cs in ([],[candidato(),candidato()]):
            n,s,m,_ = P.avaliar(decisao(),cs)
            self.assertEqual(m,'PADDLE_ASSOCIACAO_AMBIGUA')
            self.assertNotIn('classe_anterior',n)

    def test_matricula_divergente_nao_preenche(self):
        for matricula in ('990002-3','990001-2X',''):
            n,s,m,_ = P.avaliar(decisao(),[candidato(matricula=matricula)])
            self.assertEqual(m,'PADDLE_IDENTIDADE_DIVERGENTE')
            self.assertNotIn('classe_anterior',n)

    def test_nome_e_cargo_divergentes_apenas_registrados(self):
        d=decisao();n,s,_,_=P.avaliar(d,[candidato(nome='OUTRA GRAFIA FICTICIA',cargo='OUTRO CARGO')])
        self.assertEqual(n['paddleocr']['diferencas'],['servidor','cargo'])
        self.assertEqual(d['servidor'],'PESSOA FICTICIA')
        self.assertNotIn('nome',n)

    def test_revisao_previa_inclusive_ausencia_voluntaria(self):
        n,s,m,c=P.avaliar(decisao(),[candidato()],True)
        self.assertNotIn('classe_anterior',n)
        self.assertEqual((m,len(c)),('PADDLE_REVISAO_PREVIA',2))

    def test_caracteres_invalidos_confianca_e_geometria(self):
        for extra in ({'classe_anterior':'G'},{'classe_anterior':'AB'},{'classe_posterior':''},
                      {'classe_anterior':'a'},{'confiancas':[.89]*4},{'confiancas':[float('nan')]*4},
                      {'confiancas':[.99]*3},{'geometria_segura':False},{'pagina':4}):
            n,s,_,_=P.avaliar(decisao(),[candidato(**extra)])
            self.assertNotIn('classe_anterior',n)

    def test_idempotencia_proveniencia(self):
        n,_,_,_=P.avaliar(decisao(),[candidato()])
        n2,s,_,_=P.avaliar(decisao(detalhe=json.dumps(n)),[candidato()])
        self.assertEqual(n,n2)
        self.assertEqual(s,'RECUPERADO')

    def test_geometria_rejeita_caixa_cruzando_celulas(self):
        xs=[0,10,20,30,40,50,60];ys=[0,10,20]
        pol=[[[42,12],[58,12],[58,18],[42,18]]]
        linhas,ruins=montar(['A B'],pol,[.99],xs,ys)
        self.assertIn(1,ruins)
        self.assertEqual(linhas[1][4],('',0))

    def test_hash_incorreto_e_pesos_ausentes(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(P.Indisponivel,'PESOS_AUSENTES'):P.modelos_conferidos(t)
            m=Path(t)/'modelo';m.mkdir();(m/'pesos').write_bytes(b'ficticio')
            with mock.patch.object(P,'MODELOS',{'modelo':{'pesos':'0'*64}}):
                with self.assertRaisesRegex(P.Indisponivel,'HASH_DIVERGENTE'):P.modelos_conferidos(t)

    def test_supervisor_timeout_termina_processo(self):
        proc=mock.Mock();proc.poll.side_effect=[None,None];proc.wait.return_value=0
        fake=mock.Mock();fake.Error=type('PsutilError',(Exception,),{});fake.Process.return_value.memory_info.return_value.rss=1
        fake.Process.return_value.children.return_value=[]
        with mock.patch.dict(P.os.environ,{'OMP_THREAD_LIMIT':'1'}),mock.patch.object(P,'modelos_conferidos'), mock.patch.dict(sys.modules,{'psutil':fake}), \
             mock.patch.object(P.subprocess,'Popen',return_value=proc) as abrir,mock.patch.object(P.time,'monotonic',side_effect=[0,200]):
            with self.assertRaisesRegex(P.Indisponivel,'TIMEOUT'):P.executar('ficticio.pdf',{},P.Config(Path('pesos')))
            self.assertEqual(abrir.call_args.kwargs['env']['OMP_THREAD_LIMIT'],'2')
        proc.kill.assert_called_once();proc.wait.assert_called_once()


    def test_supervisor_memoria_excessiva_termina_processo(self):
        proc=mock.Mock();proc.poll.side_effect=[None,None]
        fake=mock.Mock();fake.Error=type('PsutilError',(Exception,),{});fake.Process.return_value.memory_info.return_value.rss=5*1024**3
        fake.Process.return_value.children.return_value=[]
        with mock.patch.object(P,'modelos_conferidos'),mock.patch.dict(sys.modules,{'psutil':fake}), \
             mock.patch.object(P.subprocess,'Popen',return_value=proc):
            with self.assertRaisesRegex(P.Indisponivel,'MEMORIA'):P.executar('ficticio.pdf',{},P.Config(Path('pesos')))
        proc.kill.assert_called_once()


class Persistencia(TP.Base):
    def setUp(self):
        super().setUp()
        self.sha=TP.carregar(self.banco,'z','2026-10-09',T.VERTICAL_SEM_GEDIV.replace(' A F\n','\n'))
        processo.classificar_pendentes(self.banco)
        self.d=self.banco.con.execute('SELECT * FROM decisao').fetchone()
        self.acervo=mock.Mock();self.acervo.conferir.return_value=True
        self.acervo.caminho.return_value=Path('pdf-ficticio.pdf')
        self.config=P.Config(Path('pesos-nao-instalados'))
        self.c=candidato(pagina=self.d['pagina'],processo=self.d['processo'],matricula=self.d['matricula'])
        self.backend=mock.Mock(return_value={'regioes':1,'candidatos':[self.c]})

    def run_complement(self):
        return P.complementar(self.banco,self.acervo,self.config,backend=self.backend)

    def row(self):return self.banco.con.execute('SELECT * FROM decisao').fetchone()

    def test_grava_proveniencia_sem_homologar_idempotente_e_sem_alterar_indicadores(self):
        antes=indicadores.painel(self.banco)['indicadores']
        self.assertEqual(self.run_complement()['recuperados'],1)
        d=self.row();self.assertEqual(d['validacao'],'PENDENTE')
        self.assertEqual(json.loads(d['detalhe'])['paddleocr']['pdf_sha256'],self.sha)
        self.assertEqual(indicadores.painel(self.banco)['indicadores'],antes)
        count=self.banco.con.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0]
        self.run_complement()
        self.assertEqual(self.banco.con.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0],count)
        for campo in ['id','processo','matricula','servidor','cargo','resultado','origem','validacao']:
            self.assertEqual(d[campo],self.d[campo])
        self.assertEqual(self.banco.con.execute('PRAGMA user_version').fetchone()[0],B.VERSAO_ESQUEMA)

    def test_correcao_humana_nula_preservada_conflito_auditavel_idempotente(self):
        servico.revisar_decisoes(self.banco,[self.d['id']],servico.REABRIR,TP.REVISOR,TP.JUST,
                                True,True,{'classe_anterior':'A'})
        servico.revisar_decisoes(self.banco,[self.d['id']],servico.REABRIR,TP.REVISOR,TP.JUST,
                                True,True,{'classe_anterior':None})
        for _ in range(2):self.run_complement()
        self.assertIsNone(json.loads(self.row()['detalhe']).get('classe_anterior'))
        self.assertEqual(len(self.banco.correcoes('decisao',self.d['id'])),2)
        self.assertEqual(len(self.banco.conflitos(alvo_ids=[self.d['id']])),2)

    def test_falta_paddle_timeout_erro_e_memoria_preservam_baseline_e_pendencias(self):
        for erro in [P.Indisponivel('PADDLE_INDISPONIVEL'),P.Indisponivel('PADDLE_TIMEOUT'),
                     P.Indisponivel('PADDLE_LIMITE_MEMORIA'),RuntimeError('TEXTO PRIVADO FICTICIO')]:
            self.backend.side_effect=erro
            r=self.run_complement();self.assertEqual(r['falhas'],1)
            self.assertNotIn('classe_anterior',json.loads(self.row()['detalhe']))
            self.assertEqual(self.row()['validacao'],'PENDENTE')
            self.assertNotIn('TEXTO PRIVADO',json.dumps([dict(r) for r in self.banco.trilha()]))

    def test_pdf_adulterado_nao_chama_backend(self):
        self.acervo.conferir.return_value=False
        self.assertEqual(self.run_complement()['falhas'],1)
        self.backend.assert_not_called()

    def test_classificacao_obsoleta_nao_propoe(self):
        with self.banco.con:self.banco.con.execute('UPDATE classificacao SET revisao_leitura=NULL')
        self.run_complement();self.backend.assert_not_called()

    def test_releitura_durante_inferencia_invalida_proposta(self):
        def outro(*args):
            with self.banco.con:
                self.banco.con.execute('UPDATE leitura SET revisao=revisao+1')
                self.banco.con.execute('UPDATE classificacao SET revisao_leitura=revisao_leitura+1')
            return {'candidatos':[self.c]}
        self.backend.side_effect=outro
        self.run_complement()
        self.assertNotIn('classe_anterior',json.loads(self.row()['detalhe']))

    def test_reprocessar_pagina_insegura_nao_conta_mesma_recuperacao_novamente(self):
        self.run_complement()
        detalhe=json.loads(self.row()['detalhe']);detalhe['observacao']='observação sintética pendente'
        with self.banco.con:self.banco.con.execute('UPDATE decisao SET detalhe=?',(json.dumps(detalhe),))
        self.assertEqual(self.run_complement()['recuperados'],0)
        self.assertEqual(json.loads(self.row()['detalhe']),detalhe)

    def test_reclassificar_mesma_revisao_preserva_proposta_e_proveniencia(self):
        self.run_complement()
        detalhe=json.loads(self.row()['detalhe'])
        processo.classificar_pendentes(self.banco,refazer=True)
        self.assertEqual(json.loads(self.row()['detalhe']),detalhe)
        self.assertEqual(self.row()['validacao'],'PENDENTE')

    def test_nova_revisao_nao_reutiliza_proposta_antiga(self):
        self.run_complement()
        with self.banco.con:self.banco.con.execute('UPDATE leitura SET revisao=revisao+1')
        processo.classificar_pendentes(self.banco,refazer=True)
        self.assertNotIn('classe_anterior',json.loads(self.row()['detalhe']))

    def test_revisao_humana_conferida_nao_muda_indicadores_ou_campos(self):
        servico.revisar_decisoes(self.banco,[self.d['id']],servico.CONFERIR,TP.REVISOR,TP.JUST,True,True,
                                {'classe_anterior':'D','classe_posterior':'E'})
        before=indicadores.painel(self.banco)['indicadores']
        self.run_complement()
        det=json.loads(self.row()['detalhe'])
        self.assertEqual((det['classe_anterior'],det['classe_posterior']),('D','E'))
        self.assertEqual(self.row()['validacao'],'CONFERIDO')
        self.assertEqual(indicadores.painel(self.banco)['indicadores'],before)

    def test_contexto_documental_alterado_durante_inferencia_nao_preenche(self):
        def outro(*args):
            with self.banco.con:self.banco.con.execute("UPDATE ato SET modalidade='HORIZONTAL'")
            return {'candidatos':[self.c]}
        self.backend.side_effect=outro
        self.run_complement()
        self.assertNotIn('classe_anterior',json.loads(self.row()['detalhe']))

    def test_resposta_invalida_produz_fallback(self):
        self.backend.return_value={'candidatos':['resposta-ficticia-invalida']}
        self.assertEqual(self.run_complement()['falhas'],1)
        self.assertNotIn('classe_anterior',json.loads(self.row()['detalhe']))

    def test_d06_na_leitura_nao_e_removido(self):
        with self.banco.con:
            self.banco.con.execute('UPDATE leitura SET inconsistencias=?',(json.dumps(['POSSIVEL_TEXTO_EM_CONTORNO']),))
        self.run_complement()
        l=self.banco.leituras()[0]
        self.assertIn('POSSIVEL_TEXTO_EM_CONTORNO',l['inconsistencias'])


if __name__=='__main__':unittest.main()
