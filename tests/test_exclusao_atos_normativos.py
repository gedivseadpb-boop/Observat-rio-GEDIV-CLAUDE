"""Regra obrigatória do Observatório GEDIV (decisão humana de 23/11/2026): atos normativos são excluídos dos
resultados, de "Outras publicações" e dos indicadores, preservando os atos individuais e concretos (resenhas e
portarias) — inclusive os que citam leis. A identificação é pelo tipo do ato no cabeçalho, nunca por palavra no corpo.
Dados fictícios; só a forma é a real."""
from __future__ import annotations

import unittest

from observatorio.gerencias.gediv import exclusoes as EX
from observatorio.gerencias.gediv.classificador import classificar

RESENHA = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {numero}/2026 - DEREH/GS/SEAD\n"
           "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS EXPEDIENTE DO DIA : 01-11-2026\n"
           "GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS E VANTAGENS\n"
           "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo MAG,\n"
           "nos termos da\n"
           "LEI Nº 7.419, DE 15 DE OUTUBRO DE 2003, que dispõe sobre o Plano de Cargos dos servidores públicos do Magistério\n"
           "Processo Matricula Nome Cargo Classe P/Classe\n"
           "SAD-PSE-2026/9{numero}1 9{numero}11-1 PESSOA FICTICIA {numero} PROFESSOR A B\n"
           "PUBLIQUE-SE")

PORTARIA_INDIVIDUAL = ("DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nPORTARIA Nº 044/2026-DEREH\n"
                       "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS RESOLVE conceder ao servidor PESSOA FICTICIA PORTARIA,\n"
                       "matrícula 900044-4, nos termos da Lei nº 58/2003, o benefício requerido.\nPUBLIQUE-SE")
PORTARIA_GERAL = ("DIRETORIA EXECUTIVA DE RECURSOS HUMANOS\nPORTARIA Nº 045/2026-DEREH\n"
                  "Estabelece normas e procedimentos para o requerimento de progressão funcional dos servidores.\n"
                  "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS RESOLVE:\nArt. 1º Os pedidos serão protocolados.\nPUBLIQUE-SE")

NORMATIVOS = {
    "LEI": "LEI Nº 14.999, DE 5 DE OUTUBRO DE 2026\nAltera o Plano de Cargos, Carreira e Remuneração dos servidores públicos.",
    "LEI_COMPLEMENTAR": "LEI COMPLEMENTAR Nº 201, DE 5 DE OUTUBRO DE 2026\nDispõe sobre o regime dos servidores públicos civis.",
    "DECRETO": "DECRETO Nº 45.001, DE 6 DE OUTUBRO DE 2026\nRegulamenta a progressão funcional dos servidores públicos.",
    "MEDIDA_PROVISORIA": "MEDIDA PROVISÓRIA Nº 360, DE 7 DE OUTUBRO DE 2026\nAltera o PCCR dos servidores do Grupo AST.",
    "ATO_NORMATIVO": "ATO NORMATIVO Nº 12/2026\nSECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nDispõe sobre procedimentos da DEREH.",
    "INSTRUCAO_NORMATIVA": "INSTRUÇÃO NORMATIVA Nº 3/2026 - SEAD\nOrienta a contagem de tempo de serviço dos servidores públicos.",
    "RESOLUCAO_NORMATIVA": "RESOLUÇÃO NORMATIVA Nº 8/2026\nDispõe sobre o abono de permanência dos servidores públicos.",
    "PORTARIA_NORMATIVA": "PORTARIA NORMATIVA Nº 5/2026 - SEAD\nEstabelece critérios de progressão funcional dos servidores.",
}


def um(*textos):
    return classificar([(i + 1, t) for i, t in enumerate(textos)], "arquivo-de-teste")


class TesteExclusaoDeAtosNormativos(unittest.TestCase):
    def test_cada_tipo_normativo_e_excluido_pelo_cabecalho(self):
        for tipo, texto in NORMATIVOS.items():
            with self.subTest(tipo=tipo):
                r = um(texto)
                self.assertEqual((r.atos, r.decisoes, r.outras, r.eventos), ([], [], [], []))
                self.assertEqual([(f.tipo, f.motivo) for f in r.fora_escopo], [(tipo, EX.ATO_NORMATIVO)])

    def test_normativo_sem_relacao_com_pessoal_nao_gera_registro_nem_resultado(self):
        r = um("LEI Nº 15.000, DE 5 DE OUTUBRO DE 2026\nDenomina rodovia estadual.")
        self.assertEqual((r.atos, r.outras, r.fora_escopo), ([], [], []))

    def test_resenha_que_cita_lei_e_preservada(self):
        r = um(RESENHA.format(numero=940))
        self.assertEqual([a.numero for a in r.atos], ["940/2026"])
        self.assertEqual([d.processo for d in r.decisoes], ["SAD-PSE-2026/99401"])
        self.assertEqual(r.fora_escopo, [])          # "LEI Nº 7.419" dentro da resenha é citação

    def test_portaria_individual_que_cita_lei_e_preservada_sem_marca(self):
        r = um(PORTARIA_INDIVIDUAL)
        self.assertEqual([(o.tipo, o.titulo) for o in r.outras], [("PORTARIA", "Portaria nº 44/2026 -DEREH")])
        self.assertEqual(r.fora_escopo, [])

    def test_portaria_de_redacao_normativa_vai_para_revisao_humana(self):
        r = um(PORTARIA_GERAL)
        self.assertEqual(len(r.outras), 1)
        self.assertIn("possível ato normativo; exige revisão humana", r.outras[0].titulo)
        self.assertEqual((r.atos, r.decisoes, r.fora_escopo), ([], [], []))

    def test_edicao_mista_exclui_normativos_e_preserva_individuais(self):
        r = um(RESENHA.format(numero=941), NORMATIVOS["LEI"], PORTARIA_INDIVIDUAL, NORMATIVOS["DECRETO"],
               RESENHA.format(numero=942))
        self.assertEqual([a.numero for a in r.atos], ["941/2026", "942/2026"])
        self.assertEqual(len(r.decisoes), 2)
        self.assertEqual([o.tipo for o in r.outras], ["PORTARIA"])
        self.assertEqual(sorted(f.tipo for f in r.fora_escopo), ["DECRETO", "LEI"])
        self.assertFalse({"ATO_NORMATIVO", "ALTERACAO_LEI"} & {o.tipo for o in r.outras})

    def test_registros_sao_estaveis_entre_execucoes(self):
        a, b = um(NORMATIVOS["LEI"], NORMATIVOS["DECRETO"]), um(NORMATIVOS["LEI"], NORMATIVOS["DECRETO"])
        self.assertEqual([f.id for f in a.fora_escopo], [f.id for f in b.fora_escopo])
        self.assertEqual(len({f.id for f in a.fora_escopo}), 2)


if __name__ == "__main__":
    unittest.main()
