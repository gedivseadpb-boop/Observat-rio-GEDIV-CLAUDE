"""Regras definitivas da GEDIV (Etapa 02, PR-01): os 16 grupos, expressões sem grupo homologado e exclusões.
Todos os textos são SINTÉTICOS; pessoas e processos são fictícios."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv import exclusoes as EX
from observatorio.gerencias.gediv.classificador import NAO_EXPRESSO, classificar
from observatorio.nucleo import banco as B
from observatorio.painel import indicadores
from tests import textos_doe as T


def um(texto):
    return classificar([(1, texto)], "arquivo-de-teste")


CABECALHO_GEDIV = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {n}/2026\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS "
                   "EXPEDIENTE DO DIA : 03-11-2026\nGERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n")
CABECALHO_DEREH = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : {n}/2026 - DEREH/GS/SEAD\nDIRETORIA EXECUTIVA DE RECURSOS "
                   "HUMANOS EXPEDIENTE DO DIA : 03-11-2026\n")

LICENCA_SAUDE_GEDIV = ("GOVERNO DO ESTADO DA PARAÍBA Nº da Resenha: 931/2026\nSECRETARIA DE ESTADO DA ADMINISTRAÇÃO. 03/11/2026\n"
                       "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS / GERÊNCIA\nEXECUTIVA CONC. DE DIREITOS E VANTAGENS\n"
                       "O Diretor Executivo de Recursos Humanos, de acordo com Laudo da Perícia Médica Oficial, DEFERIU os seguintes pedidos:\n"
                       "Órgão/Secretaria Nome Matrícula Reg. Previd. Dias Data de Início Data Fim\n"
                       "TIPO DE LICENÇA => DOENÇA NÃO RELACIONADA AO TRABALHO\n"
                       "SEE - REGIONAL 01 PESSOA FICTICIA 9000051 RPPS 30 01/11/2026 30/11/2026\nPUBLIQUE-SE")
LICENCA_SAUDE_DEREH = (CABECALHO_DEREH.format(n=932) + "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS DEFERIU os pedidos de LICENÇA PARA "
                       "TRATAMENTO DE SAÚDE dos servidores abaixo:\nSAD-PSE-2026/90052 9000052 PESSOA FICTICIA SEE 30 DIAS\nPUBLIQUE-SE")
VACANCIA_DEREH = (CABECALHO_DEREH.format(n=933) + "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO resolve DECLARAR A VACÂNCIA dos cargos "
                  "abaixo, em virtude de posse em outro cargo inacumulável:\nSAD-PSE-2026/90053 9000053 PESSOA FICTICIA PROFESSOR\nPUBLIQUE-SE")
VACANCIA_GEDIV = (CABECALHO_GEDIV.format(n=934) + "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS resolve DECLARAR VAGO o cargo abaixo:\n"
                  "SAD-PSE-2026/90054 9000054 PESSOA FICTICIA AGENTE\nPUBLIQUE-SE")
OUTRA_GERENCIA = ("SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº : 935/2026\nDIRETORIA EXECUTIVA DE RECURSOS HUMANOS "
                  "EXPEDIENTE DO DIA : 03-11-2026\nGERÊNCIA EXECUTIVA DE PAGAMENTO DE PESSOAL\n"
                  "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS DEFERIU os pedidos de AUXÍLIO FUNERAL abaixo:\n"
                  "SAD-PSE-2026/90055 9000055 PESSOA FICTICIA SEE\nPUBLIQUE-SE")
OUTRA_GERENCIA_COM_TEMA = OUTRA_GERENCIA.replace("935", "936").replace("AUXÍLIO FUNERAL", "LICENÇA ESPECIAL")
PROGRESSAO_DEREH = (CABECALHO_DEREH.format(n=937) + "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO DEFERIU os Processos de PROGRESSÃO "
                    "FUNCIONAL HORIZONTAL do Grupo Ocupacional de Apoio Judiciário GAJ-1700:\n"
                    "SAD-PSE-2026/90056 900056-1 PESSOA FICTICIA POLICIAL PENAL I II\nPUBLIQUE-SE")
LICENCA_ESPECIAL_DEREH = (CABECALHO_DEREH.format(n=938) + "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS DEFERIU os processos de "
                          "LICENÇA ESPECIAL abaixo:\nSAD-PSE-2026/90057 9000057 PESSOA FICTICIA 90 01/02/1998 01/02/2003\nPUBLIQUE-SE")


class TesteGruposDefinitivos(unittest.TestCase):
    def test_os_dezesseis_codigos_na_ordem_definida(self):
        self.assertEqual([g.codigo for g in C.GRUPOS],
                         ["MAG", "SSA", "GAJ", "FAP", "AST", "ANS", "ESP", "DPS", "SFT", "OSPB", "GPC", "SEI", "SAT", "ACI", "PPGG", "INT"])
        self.assertNotIn("SAUDE", C.GRUPO_POR_CODIGO)
        self.assertNotIn("ESPECIAL", C.GRUPO_POR_CODIGO)
        self.assertNotIn("TEC-ADM", C.GRUPO_POR_CODIGO)

    def test_ssa_e_esp(self):
        for texto, esperado in {"DOS PROFISSIONAIS DO GRUPO SAUDE": "SSA", "DO GRUPO SSA-1200": "SSA",
                                "DO GRUPO OCUPACIONAL ESPECIAL": "ESP", "DO GRUPO ESP-800": "ESP"}.items():
            with self.subTest(texto=texto):
                self.assertEqual(C.identificar_grupo(texto)[0], esperado)

    def test_int_existe_provisorio_e_so_em_forma_inequivoca(self):
        self.assertEqual(C.GRUPO_POR_CODIGO["INT"].estado, C.PROVISORIA)
        self.assertEqual(C.identificar_grupo("DO GRUPO INT ABAIXO")[0], "INT")
        self.assertEqual(C.identificar_grupo("DO GRUPO INT-1500")[0], "INT")
        for texto in ("LICENCA PARA TRATAR DE INTERESSES PARTICULARES", "SERVIDOR INTERINO", "INT. NO DIA"):
            with self.subTest(texto=texto):
                self.assertIsNone(C.identificar_grupo(texto)[0])

    def test_tec_adm_nao_vira_ast_nem_grupo(self):
        self.assertEqual(C.identificar_grupo("DO GRUPO TEC. ADM."), (None, "TEC. ADM"))
        self.assertEqual(C.identificar_grupo("DO GRUPO TEC ADM"), (None, "TEC ADM"))
        # mesmo com AST no texto, a expressão sem homologação impede a atribuição automática
        self.assertEqual(C.identificar_grupo("GRUPO TEC. ADM. E AST")[0], None)
        self.assertEqual(C.identificar_grupo("DO GRUPO TECNICO ADMINISTRATIVO - AST -")[0], "AST")

    def test_stf_nao_e_presumido_sft(self):
        self.assertEqual(C.identificar_grupo("GRUPO STF - AUDITOR FISCAL TRIBUTARIO"), (None, "STF"))
        self.assertEqual(C.identificar_grupo("DOS AUDITORES FISCAIS TRIBUTARIOS")[0], "SFT")
        self.assertEqual(C.identificar_grupo("DOS PROFISSIONAIS DA FAZENDA")[0], "SFT")
        self.assertEqual(C.identificar_grupo("DO GRUPO SFT")[0], "SFT")

    def test_dicionario_publica_expressoes_sem_grupo(self):
        d = C.como_dicionario()
        self.assertEqual([g["codigo"] for g in d["grupos"]], list(C.CODIGOS_GRUPOS))
        self.assertEqual({e["expressao"] for e in d["expressoes_sem_grupo"]}, {"TEC. ADM", "STF"})


class TesteExclusoes(unittest.TestCase):
    def test_licenca_saude_com_gediv_no_cabecalho_fica_fora_do_escopo(self):
        r = um(LICENCA_SAUDE_GEDIV)
        self.assertEqual((r.atos, r.decisoes, r.outras), ([], [], []))
        self.assertEqual([(f.numero, f.motivo, f.vinculo) for f in r.fora_escopo], [("931/2026", EX.LICENCA_SAUDE, "EXPRESSO")])

    def test_licenca_saude_sob_a_dereh_fica_fora_do_escopo(self):
        r = um(LICENCA_SAUDE_DEREH)
        self.assertEqual((r.atos, r.outras), ([], []))
        self.assertEqual([(f.numero, f.motivo) for f in r.fora_escopo], [("932/2026", EX.LICENCA_SAUDE)])

    def test_vacancia_fica_fora_do_escopo_com_ou_sem_gediv(self):
        for texto, numero in ((VACANCIA_DEREH, "933/2026"), (VACANCIA_GEDIV, "934/2026")):
            with self.subTest(numero=numero):
                r = um(texto)
                self.assertEqual((r.atos, r.outras), ([], []))
                self.assertEqual([(f.numero, f.motivo) for f in r.fora_escopo], [(numero, EX.VACANCIA)])

    def test_outra_gerencia_da_sead_fica_registrada_fora_do_escopo(self):
        r = um(OUTRA_GERENCIA)
        self.assertEqual((r.atos, r.outras), ([], []))
        self.assertEqual([(f.numero, f.motivo) for f in r.fora_escopo], [("935/2026", EX.OUTRA_GERENCIA)])

    def test_outra_gerencia_com_tema_parecido_nao_entra_e_fica_registrada(self):
        r = um(OUTRA_GERENCIA_COM_TEMA)
        self.assertEqual((r.atos, r.decisoes, r.descartados), ([], [], 1))
        self.assertEqual([f.motivo for f in r.fora_escopo], [EX.OUTRA_GERENCIA])

    def test_dereh_no_cabecalho_nao_exclui_progressao(self):
        r = um(PROGRESSAO_DEREH)
        self.assertEqual(r.fora_escopo, [])
        self.assertEqual([(a.numero, a.eixo, a.modalidade, a.grupo, a.vinculo) for a in r.atos],
                         [("937/2026", C.PROGRESSAO, C.HORIZONTAL, "GAJ", NAO_EXPRESSO)])
        self.assertEqual(len(r.decisoes), 1)

    def test_dereh_no_cabecalho_nao_exclui_tempo_de_servico(self):
        r = um(LICENCA_ESPECIAL_DEREH)
        self.assertEqual(r.fora_escopo, [])
        self.assertEqual([(a.numero, a.subcategoria) for a in r.atos], [("938/2026", "TS-05")])

    def test_temas_dos_eixos_nunca_sao_excluidos(self):
        for texto in ("LICENCA ESPECIAL", "LICENCA PARA TRATAR DE INTERESSES PARTICULARES", "CONVERSAO DE LICENCA ESPECIAL",
                      "DESISTENCIA DA LICENCA", "PROGRESSAO FUNCIONAL VERTICAL"):
            with self.subTest(texto=texto):
                self.assertIsNone(EX.motivo_de_exclusao(texto))

    def test_atos_dos_eixos_seguem_classificados_ao_lado_de_um_excluido(self):
        r = classificar([(1, LICENCA_SAUDE_GEDIV), (2, T.ANOTACAO)], "x")
        self.assertEqual([a.subcategoria for a in r.atos], ["TS-01"])
        self.assertEqual([f.motivo for f in r.fora_escopo], [EX.LICENCA_SAUDE])

    def test_nenhum_terceiro_eixo(self):
        self.assertEqual(list(C.EIXOS), [C.PROGRESSAO, C.TEMPO])
        for texto in (LICENCA_SAUDE_GEDIV, VACANCIA_GEDIV, OUTRA_GERENCIA, PROGRESSAO_DEREH, T.ANOTACAO):
            for ato in um(texto).atos:
                self.assertIn(ato.eixo, (C.PROGRESSAO, C.TEMPO, None))


class TesteRegistroPrivadoDasExclusoes(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.banco = B.Banco(Path(self.pasta.name) / "b.sqlite3")
        self.addCleanup(self.banco.fechar)
        with self.banco.con:
            self.banco.con.execute("INSERT INTO arquivo VALUES ('sha-teste', 1, 'x', 'agora')")

    def gravar(self, *textos):
        r = classificar([(i, t) for i, t in enumerate(textos, start=1)], "sha-teste")
        return self.banco.gravar_classificacao("GEDIV", "sha-teste", C.VERSAO_REGRAS, "2026-11-04", r)

    def test_exclusoes_ficam_registradas_e_nao_duplicam_na_reclassificacao(self):
        resumo = self.gravar(LICENCA_SAUDE_GEDIV, VACANCIA_DEREH, T.ANOTACAO)
        self.assertEqual((resumo["fora_escopo"], resumo["atos"]), (2, 1))
        self.gravar(LICENCA_SAUDE_GEDIV, VACANCIA_DEREH, T.ANOTACAO)
        linhas = self.banco.con.execute("SELECT numero, motivo, versao_regras FROM fora_escopo ORDER BY numero").fetchall()
        self.assertEqual([tuple(l) for l in linhas], [("931/2026", EX.LICENCA_SAUDE, C.VERSAO_REGRAS),
                                                       ("933/2026", EX.VACANCIA, C.VERSAO_REGRAS)])
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM outra_publicacao").fetchone()[0], 0)

    def test_excluidos_nao_aparecem_em_outras_publicacoes_nem_nos_indicadores(self):
        self.gravar(LICENCA_SAUDE_GEDIV, VACANCIA_GEDIV)
        self.assertEqual(indicadores.outras_publicacoes(self.banco, indicadores.GERENCIA_PERFIL), [])
        painel = indicadores.painel(self.banco, {"escopo": "pendente"}, indicadores.GERENCIA_PERFIL)
        self.assertEqual(painel["indicadores"]["decisoes"], 0)

    def test_registro_privado_nao_guarda_linhas_de_servidores(self):
        self.gravar(LICENCA_SAUDE_GEDIV)
        colunas = [c[1] for c in self.banco.con.execute("PRAGMA table_info(fora_escopo)")]
        self.assertFalse({"servidor", "matricula", "trecho", "texto"} & set(colunas))
        valores = " ".join(str(v) for l in self.banco.con.execute("SELECT * FROM fora_escopo") for v in l)
        self.assertNotIn("PESSOA FICTICIA", valores)
        self.assertNotIn("9000051", valores)


class TesteMigracaoV5(unittest.TestCase):
    def test_banco_da_versao_4_ganha_a_tabela_sem_perder_dados(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "v4.sqlite3"
            con = sqlite3.connect(caminho)
            for script in (B._ESQUEMA, B._ESQUEMA_V2, B._ESQUEMA_V3, B._ESQUEMA_V4):
                con.executescript(script)
            con.execute("PRAGMA user_version = 4")
            con.execute("INSERT INTO arquivo VALUES ('sha-antigo', 1, 'x', 'agora')")
            con.commit()
            con.close()
            banco = B.Banco(caminho)
            try:
                self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], 5)
                self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0], 1)
                self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM fora_escopo").fetchone()[0], 0)
            finally:
                banco.fechar()


if __name__ == "__main__":
    unittest.main()
