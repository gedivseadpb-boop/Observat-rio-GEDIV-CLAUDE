"""Classificação GEDIV: dicionário, duas camadas de identificação e cenários de aceitação.
Todos os textos são SINTÉTICOS (tests/textos_doe.py); nenhum dado real é usado."""
import unittest

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv.classificador import EXPRESSO, NAO_EXPRESSO, classificar
from tests import textos_doe as T


def um(texto, **extras):
    return classificar([(1, texto)], "arquivo-de-teste", **extras)


class TesteCatalogo(unittest.TestCase):
    def test_exatamente_dois_eixos_duas_modalidades_e_sete_subcategorias(self):
        self.assertEqual(list(C.EIXOS), ["PROGRESSAO", "TEMPO_SERVICO"])
        self.assertEqual(list(C.MODALIDADES), ["HORIZONTAL", "VERTICAL"])
        self.assertEqual([s.codigo for s in C.SUBCATEGORIAS], [f"TS-0{i}" for i in range(1, 8)])
        self.assertEqual([s.nome for s in C.SUBCATEGORIAS], [
            "Anotação de Tempo de Serviço/Contribuição", "Desaverbação de Tempo de Serviço",
            "Licença para Tratar de Interesses Particulares", "Desistência de Licença de Interesse Particular",
            "Licença Especial", "Conversão de Licença Especial em Tempo de Serviço", "Conversão de Férias"])

    def test_os_dezesseis_grupos_do_documento_oficial_na_ordem_do_documento(self):
        self.assertEqual([g.codigo for g in C.GRUPOS], ["MAG", "SAUDE", "GAJ", "FAP", "AST", "TEC-ADM", "ANS", "ESPECIAL", "DPS",
                                                        "SFT", "OSPB", "GPC", "SEI", "SAT", "ACI", "PPGG"])
        self.assertTrue(all(g.estado in (C.CONFIRMADA, C.PROVISORIA) for g in C.GRUPOS))

    def test_expressoes_dos_grupos(self):
        casos = {"GRUPO OCUPACIONAL DE APOIO JUDICIARIO GAJ-1700:": "GAJ", "DO GRUPO FAP-1300": "FAP", "DO GRUPO TEC. ADM.": "TEC-ADM",
                 "DO GRUPO TECNICO ADMINISTRATIVO - AST -:": "AST", "DOS PROFISSIONAIS DO GRUPO SAUDE ABAIXO": "SAUDE",
                 "DOS PROFISSIONAIS DO GRUPO MAG. ABAIXO": "MAG", "DOS PROFISSINAIS DA FAZENDA": "SFT", "DO GRUPO ANS-900": "ANS",
                 "DO GRUPO ESPECIAL": "ESPECIAL", "DO GRUPO DPS-1600": "DPS", "DO GRUPO OSPB": "OSPB", "DO GRUPO GPC": "GPC",
                 "DO GRUPO SEI": "SEI", "DO GRUPO SAT": "SAT", "DO GRUPO ACI": "ACI", "DO GRUPO PPGG": "PPGG"}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(C.identificar_grupo(texto)[0], esperado)
        self.assertEqual(C.identificar_grupo("DO GRUPO DESCONHECIDO XYZ"), (None, None))      # nunca inventa grupo

    def test_as_sete_subcategorias_sao_reconhecidas_sem_confundir_casos_parecidos(self):
        casos = {"PROCESSOS DE ANOTACAO DE TEMPO DE SERVICO / CONTRIBUICAO": "TS-01", "DESAVERBACAO DE TEMPO DE SERVICO": "TS-02",
                 "LICENCA PARA TRATAR DE INTERESSES PARTICULARES": "TS-03",
                 "DESISTENCIA DE LICENCA PARA TRATAR DE INTERESSES PARTICULARES": "TS-04", "LICENCA ESPECIAL": "TS-05",
                 "CONVERSAO DE LICENCA ESPECIAL EM TEMPO DE SERVICO": "TS-06", "CONVERSAO DE FERIAS": "TS-07"}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(C.identificar_subcategoria(texto), esperado)
        self.assertIsNone(C.identificar_subcategoria("ABONO DE PERMANENCIA"))                 # não existe oitava categoria

    def test_condicao_e_normalizacao_da_ligadura(self):
        self.assertEqual(C.identificar_condicao("PROGRESSAO VERTICAL CONDICIONAL"), "CONDICIONAL")
        self.assertEqual(C.identificar_condicao("PROGRESSAO HORIZONTAL PLENA"), "PLENA")
        self.assertEqual(C.identificar_condicao("PROGRESSAO HORIZONTAL"), "NAO_INFORMADA")
        self.assertEqual(C.normalizar("Diário Ofi cial — Retifi cação"), "DIARIO OFICIAL — RETIFICACAO")


class TesteClassificador(unittest.TestCase):
    def test_resenha_de_anotacao_com_gediv_expressa(self):
        r = um(T.ANOTACAO)
        ato = r.atos[0]
        self.assertEqual((ato.numero, ato.vinculo, ato.eixo, ato.subcategoria, ato.resultado, ato.data_expediente, ato.natureza),
                         ("901/2026", EXPRESSO, C.TEMPO, "TS-01", "DEFERIDO", "2026-10-08", C.ORIGINAL))
        self.assertIsNone(ato.grupo)                                    # grupo nunca é atribuído ao Tempo de Serviço
        d = r.decisoes
        self.assertEqual([(x.processo, x.matricula, x.servidor, x.lotacao) for x in d],
                         [("SAD-PSE-2026/90001", "9000001", "PESSOA FICTICIA UM", "SEC.EST.EDUCACAO"),
                          ("SAD-PSE-2026/90002", "9000002", "PESSOA FICTICIA DOIS", "SEC.EST.SAUDE")])
        self.assertEqual(d[0].detalhe["dias_municipal"], 451)
        self.assertEqual(d[1].detalhe, {"dias_privada": 120, "dias_federal": 365, "dias_estadual": 0, "dias_municipal": 0})

    def test_progressao_horizontal_traz_grupo_e_niveis(self):
        r = um(T.HORIZONTAL_GAJ)
        ato = r.atos[0]
        self.assertEqual((ato.eixo, ato.modalidade, ato.grupo, ato.condicao), (C.PROGRESSAO, C.HORIZONTAL, "GAJ", "NAO_INFORMADA"))
        self.assertEqual(r.decisoes[0].detalhe, {"nivel_anterior": "I", "nivel_atual": "III"})
        self.assertEqual(r.decisoes[0].cargo, "POLICIAL PENAL")

    def test_resenha_com_tres_linhas_e_dois_processos_distintos(self):
        r = um(T.HORIZONTAL_GAJ)                                      # cenário de aceitação da Especificação V3
        self.assertEqual((len(r.atos), len(r.decisoes), len({d.processo for d in r.decisoes})), (1, 3, 2))
        self.assertEqual(len({d.id for d in r.decisoes}), 3)

    def test_progressao_vertical_traz_classe_anterior_e_posterior(self):
        r = um(T.VERTICAL_SEM_GEDIV)
        self.assertEqual(r.decisoes[0].detalhe, {"classe_anterior": "A", "classe_posterior": "F"})
        self.assertEqual((r.atos[0].modalidade, r.atos[0].grupo), (C.VERTICAL, "TEC-ADM"))

    def test_resenha_so_com_dereh_fica_com_vinculo_nao_expresso_e_sinalizada(self):
        ato = um(T.VERTICAL_SEM_GEDIV).atos[0]
        self.assertEqual(ato.vinculo, NAO_EXPRESSO)
        self.assertTrue(any("não expresso" in p for p in ato.pendencias))

    def test_resultado_indeferido_e_grupo_mag(self):
        r = um(T.INDEFERIDA_MAG)
        self.assertEqual((r.atos[0].resultado, r.atos[0].grupo, r.decisoes[0].resultado), ("INDEFERIDO", "MAG", "INDEFERIDO"))

    def test_licenca_especial_e_desistencia_nao_se_confundem(self):
        self.assertEqual(um(T.LICENCA_ESPECIAL).atos[0].subcategoria, "TS-05")
        self.assertEqual(um(T.LICENCA_ESPECIAL).decisoes[0].detalhe["dias"], 90)
        r = um(T.DESISTENCIA)
        self.assertEqual((r.atos[0].subcategoria, r.decisoes[0].lotacao), ("TS-04", "SEC.EST.EDUCACAO"))

    def test_ato_de_outra_gerencia_nao_e_atribuido_a_gediv(self):
        r = um(T.OUTRA_GERENCIA)
        self.assertEqual((r.atos, r.decisoes, r.descartados), ([], [], 1))

    def test_ato_de_outra_secretaria_e_ignorado(self):
        r = um(T.OUTRA_SECRETARIA)
        self.assertEqual((r.atos, r.decisoes, r.eventos, r.outras), ([], [], [], []))

    def test_tema_gediv_fora_dos_dois_eixos_nao_vira_decisao(self):
        r = um(T.ABONO)
        self.assertEqual((r.atos, r.decisoes), ([], []))
        self.assertEqual(r.outras[0].tipo, "TEMA_FORA_DOS_EIXOS")
        self.assertIn("Abono de Permanência", r.outras[0].titulo)

    def test_portaria_que_torna_sem_efeito_vira_evento_com_as_referencias(self):
        r = um(T.PORTARIA_SEM_EFEITO)
        e = r.eventos[0]
        self.assertEqual((e.tipo, e.resenhas_citadas, e.processos_citados), (C.SEM_EFEITO, ["904/2026"], ["SAD-PSE-2026/90007"]))
        self.assertEqual(r.decisoes, [])                               # evento não é decisão nova

    def test_republicacao_por_incorrecao_e_evento_e_nao_decisao_original(self):
        r = um(T.REPUBLICACAO)
        self.assertEqual((r.atos[0].natureza, r.eventos[0].tipo, r.eventos[0].subtipo), (C.REPUBLICACAO, C.REPUBLICACAO, "POR_INCORRECAO"))
        self.assertEqual(r.outras[0].tipo, "REPUBLICADO_POR_INCORRECAO")
        self.assertEqual(len(r.decisoes), 2)                           # guardadas com o ato republicado, fora dos totais originais

    def test_atos_vizinhos_nao_se_misturam(self):
        pagina = "\n".join([T.ANOTACAO, T.OUTRA_SECRETARIA, T.OUTRA_GERENCIA, T.INDEFERIDA_MAG])
        r = um(pagina)
        self.assertEqual([a.numero for a in r.atos], ["901/2026", "904/2026"])
        self.assertEqual([d.processo[-5:] for d in r.decisoes], ["90001", "90002", "90007"])
        self.assertEqual({d.resultado for d in r.decisoes if d.processo.endswith("90007")}, {"INDEFERIDO"})

    def test_ato_sem_publique_se_termina_no_cabecalho_de_outra_unidade(self):
        texto = (T.ANOTACAO.replace("\nPUBLIQUE-SE", "") + "\nSECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
                 "GERÊNCIA OPERACIONAL DE CESSÃO DE PESSOAL\nSEC.EST.SAUDE SAD-PSE-2026/80001 8000001 PESSOA DE OUTRA UNIDADE")
        r = um(texto)
        self.assertEqual(len(r.decisoes), 2)
        self.assertTrue(any("outra unidade" in p for p in r.atos[0].pendencias))

    def test_resenha_continua_na_pagina_seguinte_e_ignora_o_cabecalho_corrido(self):
        linhas = T.HORIZONTAL_GAJ.split("\n")
        r = classificar([(3, "\n".join(linhas[:8])), (4, T.CABECALHO_PAGINA.replace("Nº 18.690 ", "") + "\n" + "\n".join(linhas[8:]))], "x")
        self.assertEqual([d.pagina for d in r.decisoes], [3, 4, 4])
        self.assertTrue(any("continua até a página 4" in p for p in r.atos[0].pendencias))

    def test_cabecalho_de_resenha_quebrado_em_duas_linhas(self):
        r = um(T.ANOTACAO.replace("RESENHA Nº : 901/2026", "RESENHA Nº :\n901/2026"))
        self.assertEqual((r.atos[0].numero, len(r.decisoes)), ("901/2026", 2))

    def test_citacao_de_resenha_no_meio_do_texto_nao_abre_novo_ato(self):
        self.assertEqual(len(um(T.PORTARIA_SEM_EFEITO).atos), 1)

    def test_palavra_chave_sem_vinculo_institucional_nao_gera_registro(self):
        texto = "PREFEITURA MUNICIPAL DE EXEMPLO\nRESENHA Nº 5/2026\nDEFERIR a PROGRESSÃO FUNCIONAL HORIZONTAL\nSAD-PSE-2026/70001 7000001 PESSOA FICTICIA"
        r = um(texto)
        self.assertEqual((r.atos, r.decisoes), ([], []))

    def test_ids_sao_estaveis_entre_execucoes(self):
        a, b = um(T.HORIZONTAL_GAJ), um(T.HORIZONTAL_GAJ)
        self.assertEqual([d.id for d in a.decisoes], [d.id for d in b.decisoes])
        self.assertEqual(a.atos[0].id, b.atos[0].id)

    def test_processo_sem_matricula_ou_nome_fica_nao_informado(self):
        texto = T.LICENCA_ESPECIAL.replace("SEC.EST.SAUDE SAD-PSE-2026/90008 9000008 PESSOA FICTICIA OITO 90 01/02/1998 01/02/2003",
                                           "SAD-PSE-2026/90008")
        d = um(texto).decisoes[0]
        self.assertEqual((d.matricula, d.servidor), (None, None))

    def test_ato_normativo_e_alteracao_de_lei_entram_na_triagem_de_outras_publicacoes(self):
        texto = ("ATO NORMATIVO Nº 12/2026\nSECRETARIA DE ESTADO DA ADMINISTRAÇÃO\nDispõe sobre procedimentos da DEREH.\n"
                 "LEI Nº 14.999, DE 5 DE OUTUBRO DE 2026\nAltera o Plano de Cargos, Carreira e Remuneração dos servidores públicos.\n"
                 "LEI Nº 15.000, DE 5 DE OUTUBRO DE 2026\nDenomina rodovia estadual.")
        self.assertEqual(sorted(o.tipo for o in um(texto).outras), ["ALTERACAO_LEI", "ATO_NORMATIVO"])


class TesteFormatosVistosEmTextoReal(unittest.TestCase):
    """Formas encontradas ao rodar o classificador sobre trechos reais do histórico (ver docs/07).
    Os dados abaixo são fictícios; só a FORMA é a real."""

    VERTICAL = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : 910/2026 - DEREH/GS/SEAD\n"
                "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS EXPEDIENTE DO DIA : 01-10-2026\n"
                "GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS E VANTAGENS\n"
                "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos de PROGRESSÃO FUNCIONAL VERTICAL do Grupo {grupo}\n"
                "Processo Matricula Nome Cargo Classe P/Classe\n{linhas}\nPUBLIQUE-SE")

    def vertical(self, linhas, grupo="TEC. ADM."):
        return um(self.VERTICAL.format(grupo=grupo, linhas=linhas))

    def test_celula_quebrada_classes_na_primeira_linha_e_cargo_na_segunda(self):
        d = self.vertical("SAD-PSE-2026/90020 900020-1 PESSOA FICTICIA VINTE TECNICO A E\nADMINISTRATIVO").decisoes[0]
        self.assertEqual((d.servidor, d.detalhe["classe_anterior"], d.detalhe["classe_posterior"]), ("PESSOA FICTICIA VINTE", "A", "E"))
        self.assertIn("linha_quebrada", d.detalhe)                     # o revisor é avisado de que a linha continua

    def test_sobrenome_que_desceu_de_linha_apos_conectivo(self):
        d = self.vertical("SAD-PSE-2026/90021 900021-2 PESSOA FICTICIA DOS TECNICO D E\nEXEMPLOS ADMINISTRATIVO").decisoes[0]
        self.assertEqual(d.servidor, "PESSOA FICTICIA DOS EXEMPLOS")

    def test_classes_lidas_coladas_ficam_registradas_como_lidas(self):
        d = self.vertical("SAD-PSE-2026/90022 900022-3 PESSOA FICTICIA VINTE E DOIS FISCAL ESTADUAL AGROPECUARIO AC", "FAP-1300").decisoes[0]
        self.assertEqual((d.detalhe["classe_anterior"], d.detalhe["classe_posterior"]), ("A", "C"))
        self.assertIn("coladas", d.detalhe["observacao"])

    def test_caractere_invisivel_no_meio_da_palavra_nao_impede_a_classificacao(self):
        r = um(T.PORTARIA_SEM_EFEITO.replace("PROGRESSÃO FUNCIONAL", "PROGRESSÃO FUN\x02CIONAL").replace("competência", "com\x02petência"))
        self.assertEqual((len(r.eventos), r.eventos[0].tipo), (1, C.SEM_EFEITO))

    def test_variante_stf_auditor_fiscal_tributario_guarda_a_expressao_literal(self):
        ato = self.vertical("SAD-PSE-2026/90023 900023-4 PESSOA FICTICIA AUDITOR FISCAL TRIBUTARIO EST D E",
                            "STF - AUDITOR FISCAL TRIBUTARIO").atos[0]
        self.assertEqual((ato.grupo, ato.grupo_expressao), ("SFT", "STF"))

    def test_dias_com_separador_de_milhar_e_linha_seguida_de_nota_de_publicacao(self):
        texto = T.ANOTACAO.replace("PESSOA FICTICIA UM 0 0 0 451", "PESSOA FICTICIA UM 0 0 2.450 0\nPublicado no D.O.E. Edição do dia : 01/10/2026")
        d = um(texto).decisoes[0]
        self.assertEqual((d.servidor, d.detalhe["dias_estadual"]), ("PESSOA FICTICIA UM", 2450))

    def test_cabecalho_de_pagina_colado_ao_fim_da_linha_nao_entra_no_registro(self):
        d = self.vertical("SAD-PSE-2026/90024 900024-5 PESSOA FICTICIA TECNICO ADMINISTRATIVO A EDiário Ofi cial João Pessoa - Sábado, 10 de Outubro de 2026 3").decisoes[0]
        self.assertEqual((d.servidor, d.cargo, d.detalhe), ("PESSOA FICTICIA", "TECNICO ADMINISTRATIVO",
                                                            {"classe_anterior": "A", "classe_posterior": "E"}))


if __name__ == "__main__":
    unittest.main()
