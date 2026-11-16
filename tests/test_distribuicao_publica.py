"""Guardas do pacote estático, com dados inteiramente fictícios/vazios."""
import copy
import importlib.util
from pathlib import Path
import unittest

from observatorio.painel.publicacao import projetar

spec = importlib.util.spec_from_file_location('preparar_painel', Path(__file__).resolve().parents[1] / 'scripts' / 'preparar_painel_publico.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestePacotePublico(unittest.TestCase):
    def test_snapshot_vazio_real_nao_vira_exemplo(self):
        dados = projetar([])
        m.validar_snapshot(dados)
        self.assertEqual(dados['celulas'], [])
        self.assertEqual(dados['resumo']['conferidos']['valor'], 0)

    def test_recusa_campo_extra_e_texto_livre_em_metadados(self):
        for alterar in (lambda d: d.update(segredo='DADO FICTICIO'),
                        lambda d: d['cobertura'].update(observacao='DADO FICTICIO'),
                        lambda d: d['catalogo']['grupos'][0].update(nome='DADO FICTICIO')):
            dados=copy.deepcopy(projetar([]));alterar(dados)
            with self.assertRaises(ValueError):m.validar_snapshot(dados)

    def test_recusa_contagem_exata_positiva(self):
        dados=projetar([])
        dados['resumo']['provisorios']={'valor':9,'minimo':9,'maximo':9,'rotulo':'9','protegido':False}
        with self.assertRaises(ValueError):m.validar_snapshot(dados)

    def test_nunca_sobrescreve_banco_chamado_dados_json(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            alvo=Path(tmp)/'dados.json';alvo.write_bytes(b'FONTE PRIVADA FICTICIA')
            with self.assertRaises(ValueError):m.preparar(Path(tmp),[alvo])
            self.assertEqual(alvo.read_bytes(),b'FONTE PRIVADA FICTICIA')

    def test_multiplas_celulas_publicas_validas(self):
        dados=projetar([])
        for periodo in ('2026-10','2026-11'):
            dados['celulas'].append({'periodo':periodo,'eixo':'PROGRESSAO','modalidade':'HORIZONTAL','grupo':None,'subcategoria':None,'situacao':'provisorio',
                'atos':{'valor':None,'minimo':0,'maximo':4,'rotulo':'0–4','protegido':True},
                'decisoes':{'valor':None,'minimo':10,'maximo':14,'rotulo':'10–14','protegido':True}})
        m.validar_snapshot(dados)
