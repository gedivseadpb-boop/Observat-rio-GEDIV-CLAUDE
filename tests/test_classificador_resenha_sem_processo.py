"""Regressão: resenha com assunto de um dos eixos e nenhum número de processo legível (ex.: tabela em fonte sem
mapeamento de caracteres, lida sem OCR — DOE de 07/11/2026) não pode interromper a classificação da edição inteira.
Dados fictícios; só a forma é a real."""
from __future__ import annotations

import unittest

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv.classificador import classificar

CABECALHO = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {numero}/2026 - DEREH/GS/SEAD\n"
             "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS EXPEDIENTE DO DIA : 01-11-2026\n"
             "GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS E VANTAGENS\n"
             "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo MAG\n")

# Tabela ilegível: o texto nativo só traz glifos sem mapeamento, nenhum processo nem matrícula.
SEM_PROCESSO = CABECALHO.format(numero=930) + (
    "Processo Matricula Nome Cargo Classe P/Classe\n"
    "(cid:12)(cid:15)(cid:3)(cid:44) (cid:9)(cid:21)(cid:7)\n"
    "(cid:17)(cid:4)(cid:33)(cid:5)(cid:28)(cid:31)\n"
    "PUBLIQUE-SE")

LEGIVEL = CABECALHO.format(numero=931) + (
    "Processo Matricula Nome Cargo Classe P/Classe\n"
    "SAD-PSE-2026/93101 931011-1 PESSOA FICTICIA LEGIVEL PROFESSOR A B\n"
    "PUBLIQUE-SE")


class TesteResenhaSemProcessoLegivel(unittest.TestCase):
    def test_resenha_sem_processo_nao_derruba_a_classificacao(self):
        r = classificar([(5, SEM_PROCESSO)], "arquivo-de-teste")
        self.assertEqual([a.numero for a in r.atos], ["930/2026"])
        ato = r.atos[0]
        self.assertEqual((ato.eixo, ato.modalidade), (C.PROGRESSAO, C.VERTICAL))
        self.assertEqual(r.decisoes, [])
        self.assertTrue(any("nenhum processo extraído" in p for p in ato.pendencias))

    def test_demais_publicacoes_da_edicao_continuam_extraidas(self):
        r = classificar([(5, SEM_PROCESSO), (6, LEGIVEL)], "arquivo-de-teste")
        self.assertEqual([a.numero for a in r.atos], ["930/2026", "931/2026"])
        self.assertEqual([(d.processo, d.matricula) for d in r.decisoes], [("SAD-PSE-2026/93101", "931011-1")])
        self.assertEqual(r.decisoes[0].ato_id, r.atos[1].id)

    def test_ordem_inversa_tambem_preserva_as_duas(self):
        r = classificar([(5, LEGIVEL), (6, SEM_PROCESSO)], "arquivo-de-teste")
        self.assertEqual([a.numero for a in r.atos], ["931/2026", "930/2026"])
        self.assertEqual(len(r.decisoes), 1)


if __name__ == "__main__":
    unittest.main()
