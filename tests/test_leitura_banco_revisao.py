"""Etapa 05.3.3 — leitura, reclassificação, reconciliação de versões, revisão humana e eventos.

Achados das auditorias sobre 964ce4d, confirmados no código antes da correção: releitura que falha gravava a versão nova
e saía da fila (A03); releitura parcial apagava páginas válidas; classificação antiga continuava válida após releitura
com texto diferente (A02); versões do mesmo PDF contavam a mesma decisão duas vezes (A06); só 6 campos eram corrigíveis
e a interface não enviava correção alguma (A13); o ato modificador de um evento revisado podia ser apagado (A15).
Dados SINTÉTICOS (pessoas e processos fictícios).
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv import processo
from observatorio.nucleo import banco as B
from observatorio.painel import exportacao, indicadores
from observatorio.revisao import servico
from tests import test_painel as TP
from tests import textos_doe as T

REV, JUST = TP.REVISOR, TP.JUST
GER = indicadores.GERENCIA_PERFIL


def pag(numero, texto, qualidade="OK", metodo="TEXTO"):
    return {"numero": numero, "metodo": metodo, "colunas": 1, "texto": texto, "qualidade": qualidade, "palavras": len(texto.split())}


HORIZONTAL_COM_EXTRA = T.HORIZONTAL_GAJ.replace(
    "PUBLIQUE-SE", "SAD-PSE-2026/90010 900010-2 PESSOA FICTICIA DEZ POLICIAL PENAL I II\nPUBLIQUE-SE")


class Base(TP.Base):
    def ler(self, sha, *paginas, versao="v1", situacao="LIDA", erro=None):
        return self.banco.registrar_leitura(sha, situacao, versao, list(paginas), "1", "2026-10-09", erro)

    def classificar(self, **k):
        return processo.classificar_pendentes(self.banco, **k)

    def decisoes(self, sha=None, **filtro):
        sql, par = "SELECT * FROM decisao WHERE 1=1", []
        if sha:
            sql += " AND sha256 = ?"
            par.append(sha)
        for k, v in filtro.items():
            sql += f" AND {k} = ?"
            par.append(v)
        return self.banco.con.execute(sql + " ORDER BY rowid", par).fetchall()

    def conferir_tudo(self):
        for a in self.banco.con.execute("SELECT DISTINCT ato_id FROM decisao WHERE validacao = 'PENDENTE' AND vigente = 1").fetchall():
            servico.revisar_ato(self.banco, a[0], servico.CONFERIR, REV, JUST, True, True)

    def indicador(self, nome="decisoes", perfil=GER):
        return indicadores.painel(self.banco, {}, perfil)["indicadores"][nome]


# ===================================================================================== A — revisões de leitura
class TesteUltimaLeituraValida(Base):
    def setUp(self):
        super().setUp()
        self.sha = TP.carregar(self.banco, "a", "2026-10-09", "pagina um")
        self.banco.registrar_leitura(self.sha, "LIDA", "v1", [pag(1, "pagina um"), pag(2, "pagina dois")], "1", "2026-10-09", None)

    def paginas(self):
        return [(p["numero"], p["texto"]) for p in self.banco.paginas(self.sha)]

    def test_tentativa_com_uma_pagina_nao_substitui_a_leitura_de_duas(self):
        self.assertEqual(self.ler(self.sha, pag(1, "pagina um"), versao="v2"), B.PERDA_DE_CONTEUDO)
        self.assertEqual(self.paginas(), [(1, "pagina um"), (2, "pagina dois")])
        leitura = self.banco.leituras()[0]
        self.assertEqual((leitura["situacao"], leitura["versao_leitor"], leitura["paginas"]), ("LIDA", "v1", 2))
        self.assertIn("perda de conteúdo", leitura["erro"])
        ultima = self.banco.tentativas_de_leitura(self.sha)[-1]
        self.assertEqual((ultima["versao_leitor"], ultima["aceita"], json.loads(ultima["detalhe"])["paginas_ausentes"]), ("v2", 0, [2]))

    def test_tentativa_com_erro_e_nova_versao_que_falha(self):
        self.assertEqual(self.ler(self.sha, versao="v2", situacao="ERRO", erro="ValueError: falhou"), B.FALHA_TECNICA)
        self.assertEqual(self.paginas(), [(1, "pagina um"), (2, "pagina dois")])
        self.assertEqual(self.banco.leituras()[0]["versao_leitor"], "v1")             # antes: gravava v2 e saía da fila
        # Não se repete sozinha a cada execução, mas não some: volta com --refazer-pendentes.
        self.assertEqual(self.banco.arquivos_sem_leitura("v2"), [])
        self.assertEqual([a["sha256"] for a in self.banco.arquivos_sem_leitura("v2", refazer_pendentes=True)], [self.sha])

    def test_melhora_de_pagina_e_aceita(self):
        sha = TP.carregar(self.banco, "b", "2026-10-09", "x")
        self.banco.registrar_leitura(sha, "LIDA_COM_PENDENCIAS", "v1", [pag(1, "um"), pag(2, "d0is", "BAIXA_CONFIANCA")], "1", None, None)
        self.assertEqual(self.ler(sha, pag(1, "um"), pag(2, "dois"), versao="v2"), B.MELHORA)
        self.assertEqual([p["qualidade"] for p in self.banco.paginas(sha)], ["OK", "OK"])

    def test_pagina_que_piora_e_recusada(self):
        self.assertEqual(self.ler(self.sha, pag(1, "pagina um"), pag(2, "pag1na d0is", "BAIXA_CONFIANCA"), versao="v2"),
                         B.PERDA_DE_CONTEUDO)
        self.assertEqual(self.banco.paginas(self.sha)[1]["qualidade"], "OK")

    def test_leitura_valida_com_pagina_pendente_e_repeticao_idempotente(self):
        sha = "c" * 64                                                    # arquivo ainda sem nenhuma leitura
        self.banco.registrar_descoberta("manual", "manual:c", "2026-10-09", "normal", 0, "c")
        self.banco.registrar_arquivo(self.banco.publicacao("manual", "manual:c")["id"], sha, 10, "c.pdf")
        paginas = [pag(1, "um"), pag(2, "", "OCR_INDISPONIVEL", "NENHUM")]
        self.assertEqual(self.banco.registrar_leitura(sha, "LIDA_COM_PENDENCIAS", "v1", paginas, "1", None, None), B.PRIMEIRA)
        revisao = self.banco.con.execute("SELECT revisao FROM leitura WHERE sha256 = ?", (sha,)).fetchone()[0]
        for versao in ("v1", "v2"):                                   # mesma leitura de novo; só a versão do leitor muda
            self.assertEqual(self.banco.registrar_leitura(sha, "LIDA_COM_PENDENCIAS", versao, paginas, "1", None, None), B.NEUTRA)
        leitura = self.banco.con.execute("SELECT revisao, versao_leitor FROM leitura WHERE sha256 = ?", (sha,)).fetchone()
        self.assertEqual(tuple(leitura), (revisao, "v2"))
        self.assertEqual(len(self.banco.paginas(sha)), 2)

    def test_interrupcao_durante_a_gravacao_e_reinicio(self):
        tentativas = len(self.banco.tentativas_de_leitura(self.sha))
        with self.banco.con:
            self.banco.con.execute("CREATE TRIGGER queda BEFORE INSERT ON pagina BEGIN SELECT RAISE(ABORT, 'queda simulada'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ler(self.sha, pag(1, "pagina um revista"), pag(2, "pagina dois"), versao="v2")
        self.assertEqual(self.paginas(), [(1, "pagina um"), (2, "pagina dois")])       # nada pela metade
        self.assertEqual(len(self.banco.tentativas_de_leitura(self.sha)), tentativas)   # a tentativa também foi desfeita
        with self.banco.con:
            self.banco.con.execute("DROP TRIGGER queda")
        self.assertEqual(self.ler(self.sha, pag(1, "pagina um revista"), pag(2, "pagina dois"), versao="v2"), B.MUDANCA)
        self.assertEqual(self.paginas()[0], (1, "pagina um revista"))


# ===================================================================================== B — reclassificação
class TesteReclassificacao(Base):
    def setUp(self):
        super().setUp()
        self.sha = TP.carregar(self.banco, "a", "2026-10-09", T.HORIZONTAL_GAJ)
        self.classificar()

    def reler(self, texto, versao="v2"):
        return self.ler(self.sha, pag(1, texto), versao=versao)

    def test_releitura_com_texto_diferente_volta_a_fila_e_recupera_a_decisao(self):
        self.assertEqual(len(self.decisoes(self.sha)), 3)
        self.assertEqual(self.reler(HORIZONTAL_COM_EXTRA), B.MUDANCA)
        self.assertEqual([r[0] for r in self.banco.arquivos_sem_classificacao("GEDIV", C.VERSAO_REGRAS)], [self.sha])   # antes: []
        self.assertEqual(self.banco.classificacoes_desatualizadas("GEDIV"), 1)
        self.classificar()
        self.assertEqual(len(self.decisoes(self.sha)), 4)
        self.assertEqual(self.banco.classificacoes_desatualizadas("GEDIV"), 0)

    def test_mesma_leitura_ou_so_versao_do_leitor_nao_reclassifica(self):
        self.assertEqual(self.reler(T.HORIZONTAL_GAJ, "v1"), B.NEUTRA)
        self.assertEqual(self.reler(T.HORIZONTAL_GAJ, "v2"), B.NEUTRA)
        self.assertEqual(self.banco.arquivos_sem_classificacao("GEDIV", C.VERSAO_REGRAS), [])

    def test_mudanca_das_regras_reclassifica(self):
        self.assertEqual(len(self.banco.arquivos_sem_classificacao("GEDIV", "regras-novas")), 1)

    def test_revisoes_humanas_sobrevivem_sem_duplicar(self):
        d1, d2, d3 = self.decisoes(self.sha)
        servico.revisar_decisoes(self.banco, [d1["id"]], servico.CONFERIR, REV, JUST, True, True)
        servico.revisar_decisoes(self.banco, [d2["id"]], servico.CONFERIR, REV, JUST, True, True, {"servidor": "PESSOA FICTICIA QUATRO CORRIGIDA"})
        servico.revisar_decisoes(self.banco, [d3["id"]], servico.REJEITAR, REV, JUST)
        self.reler(HORIZONTAL_COM_EXTRA)
        self.classificar()
        estado = {d["processo"] + d["matricula"]: (d["validacao"], d["servidor"]) for d in self.decisoes(self.sha)}
        self.assertEqual(len(self.decisoes(self.sha)), 4)                                   # 3 revisadas + 1 nova, sem cópia
        self.assertEqual(estado["SAD-PSE-2026/90004900004-6"], ("CONFERIDO", "PESSOA FICTICIA QUATRO CORRIGIDA"))
        self.assertEqual(estado["SAD-PSE-2026/90004900005-4"][0], "REJEITADO")
        self.assertEqual(estado["SAD-PSE-2026/90010900010-2"][0], "PENDENTE")
        self.assertEqual(self.banco.conflitos(), [])                                          # extração igual: nada a decidir
        self.classificar(refazer=True)                                                        # repetição idempotente
        self.assertEqual(len(self.decisoes(self.sha)), 4)
        self.assertEqual(len(self.banco.trilha("decisao", d2["id"])), 1)

    def test_falha_entre_reclassificacao_e_gravacao_e_retomada(self):
        antes = [d["id"] for d in self.decisoes(self.sha)]
        self.reler(HORIZONTAL_COM_EXTRA)
        with self.banco.con:
            self.banco.con.execute("CREATE TRIGGER queda BEFORE INSERT ON classificacao BEGIN SELECT RAISE(ABORT, 'queda'); END")
        resumo = self.classificar()
        self.assertEqual(resumo["com_erro"], 1)
        self.assertEqual([d["id"] for d in self.decisoes(self.sha)], antes)                   # classificação anterior intacta
        with self.banco.con:
            self.banco.con.execute("DROP TRIGGER queda")
        self.classificar()
        self.assertEqual(len(self.decisoes(self.sha)), 4)


# ===================================================================================== C — versões e identidade lógica
class TesteVersoesDoMesmoAto(Base):
    def versao(self, marca, texto, data="2026-10-09"):
        sha = TP.carregar(self.banco, marca, data, texto)
        self.classificar()
        return sha

    def test_duas_versoes_conferidas_nao_dobram_os_indicadores(self):
        self.versao("a", T.HORIZONTAL_GAJ)
        self.conferir_tudo()
        self.assertEqual(self.indicador(), 3)
        self.versao("b", T.HORIZONTAL_GAJ)                       # outro PDF (metadados diferentes), mesmos atos
        self.conferir_tudo()
        self.assertEqual(self.indicador(), 3)                    # antes: 6
        self.assertEqual(self.indicador("resenhas"), 1)
        self.assertEqual(len(self.decisoes(vigente=0)), 3)       # as cópias ficam guardadas, fora da contagem
        self.assertEqual(self.indicador("decisoes", indicadores.PUBLICO), 3)

    def test_versao_com_decisao_adicional_e_decisao_conferida_antes(self):
        self.versao("a", T.HORIZONTAL_GAJ)
        self.conferir_tudo()
        self.versao("b", HORIZONTAL_COM_EXTRA)
        nova = self.decisoes(processo="SAD-PSE-2026/90010")
        self.assertEqual([(d["validacao"], d["vigente"]) for d in nova], [("PENDENTE", 1)])     # acréscimo vai à conferência
        self.conferir_tudo()
        self.assertEqual(self.indicador(), 4)

    def test_processo_corrigido_na_nova_versao_vira_conflito_e_nao_duplica(self):
        self.versao("a", T.HORIZONTAL_GAJ)
        self.conferir_tudo()
        self.versao("b", T.HORIZONTAL_GAJ.replace("SAD-PSE-2026/90003", "SAD-PSE-2026/90033"))
        self.conferir_tudo()
        self.assertEqual(self.indicador(), 3)
        conflito = [c for c in self.banco.conflitos() if c["campo"] == "processo"]
        self.assertEqual([(json.loads(c["valor_vigente"]), json.loads(c["valor_proposto"])) for c in conflito],
                         [("SAD-PSE-2026/90003", "SAD-PSE-2026/90033")])

    def test_decisao_deslocada_para_outra_pagina(self):
        sha = TP.carregar(self.banco, "a", "2026-10-09", T.HORIZONTAL_GAJ)
        self.classificar()
        self.conferir_tudo()
        self.ler(sha, pag(1, "Página anterior sem atos da GEDIV"), pag(2, T.HORIZONTAL_GAJ), versao="v2")
        self.classificar()
        self.assertEqual(self.indicador(), 3)
        self.assertEqual(len(self.decisoes(sha, vigente=1)), 3)

    def test_mesmo_documento_em_duas_urls_e_reprocessamento(self):
        sha = TP.carregar(self.banco, "a", "2026-10-09", T.HORIZONTAL_GAJ)
        self.banco.registrar_descoberta("auniao", "https://auniao.pb.gov.br/x.pdf", "2026-10-09", "normal", 0, "x")
        self.banco.registrar_arquivo(self.banco.publicacao("auniao", "https://auniao.pb.gov.br/x.pdf")["id"], sha, 10, "x")
        for _ in range(3):
            self.classificar(refazer=True)
        self.assertEqual(len(self.decisoes()), 3)
        self.assertEqual(self.banco.conflitos(), [])

    def test_republicacao_legitima_nao_e_fundida_com_o_original(self):
        self.versao("a", "\n".join([T.ANOTACAO, T.HORIZONTAL_GAJ, T.VERTICAL_SEM_GEDIV, T.INDEFERIDA_MAG]))
        self.versao("b", "\n".join([T.PORTARIA_SEM_EFEITO, T.REPUBLICACAO, T.LICENCA_ESPECIAL]), "2026-10-15")
        chaves = {a["chave_logica"] for a in self.banco.con.execute("SELECT chave_logica FROM ato WHERE chave_logica IS NOT NULL")}
        naturezas = {k.split("|")[-1] for k in chaves}
        self.assertTrue({"ORIGINAL"} < naturezas)                                              # republicação com chave própria
        self.assertEqual(len(self.decisoes(vigente=0)), 0)

    def test_correspondencia_ambigua_entre_pessoas_fica_para_a_gerencia(self):
        self.versao("a", T.HORIZONTAL_GAJ)
        self.conferir_tudo()
        self.versao("b", T.HORIZONTAL_GAJ.replace("900003-8", "900099-9"))                      # mesmo processo, outra matrícula
        ambigua = [c for c in self.banco.conflitos() if c["origem"] == "CORRESPONDENCIA_AMBIGUA"]
        self.assertEqual(len(ambigua), 1)
        alvo = ambigua[0]["alvo_id"]
        self.assertEqual(self.decisoes(id=alvo)[0]["vigente"], 0)                              # nunca herda a revisão
        self.assertEqual(self.indicador(), 3)
        servico.resolver_conflito(self.banco, ambigua[0]["id"], servico.ACEITAR, REV, "são decisões distintas no PDF", True)
        self.assertEqual(self.decisoes(id=alvo)[0]["vigente"], 1)
        servico.revisar_decisoes(self.banco, [alvo], servico.CONFERIR, REV, JUST, True, True)
        self.assertEqual(self.indicador(), 4)


# ===================================================================================== D — revisão humana
class TesteCorrecoesGerenciais(Base):
    def setUp(self):
        super().setUp()
        self.sha = TP.carregar(self.banco, "a", "2026-10-09", "\n".join([T.HORIZONTAL_GAJ, T.VERTICAL_SEM_GEDIV, T.LICENCA_ESPECIAL]))
        self.classificar()
        self.ato = lambda n: self.banco.con.execute("SELECT * FROM ato WHERE numero = ?", (n,)).fetchone()

    def test_correcao_de_classe_nivel_e_resultado_com_historico(self):
        vertical = self.decisoes(ato_id=self.ato("903/2026")["id"])[0]
        servico.revisar_decisoes(self.banco, [vertical["id"]], servico.CONFERIR, REV, "classe conferida no PDF", True, True,
                                 {"classe_posterior": "B", "resultado": "DEFERIDO"})
        detalhe = json.loads(self.decisoes(id=vertical["id"])[0]["detalhe"])
        self.assertEqual((detalhe["classe_anterior"], detalhe["classe_posterior"]), ("A", "B"))
        horizontal = self.decisoes(ato_id=self.ato("902/2026")["id"])[0]
        servico.revisar_decisoes(self.banco, [horizontal["id"]], servico.REABRIR, REV, "nível conferido no PDF", True, True,
                                 {"nivel_atual": "nível 4"})
        self.assertEqual(json.loads(self.decisoes(id=horizontal["id"])[0]["detalhe"])["nivel_atual"], "NIVEL 4")
        c = self.banco.correcoes("decisao", vertical["id"])
        self.assertEqual([(x["campo"], json.loads(x["valor_extraido"]), json.loads(x["valor_corrigido"]), x["autor"]) for x in c],
                         [("classe_posterior", "F", "B", REV)])

    def test_valores_fora_do_dominio_sao_recusados(self):
        d = self.decisoes()[0]
        for correcao in ({"classe_posterior": "G"}, {"nivel_atual": "quinto"}, {"resultado": "TALVEZ"}, {"campo_livre": "x"}):
            with self.subTest(correcao=correcao), self.assertRaises(servico.Recusada):
                servico.revisar_decisoes(self.banco, [d["id"]], servico.REABRIR, REV, JUST, True, True, correcao)
        ato = self.ato("902/2026")["id"]
        for correcao in ({"eixo": "TERCEIRO_EIXO"}, {"grupo": "XYZ"}, {"subcategoria": "TS-01"}, {"modalidade": "DIAGONAL"}):
            with self.subTest(correcao=correcao), self.assertRaises(servico.Recusada):
                servico.corrigir_ato(self.banco, ato, correcao, REV, JUST, True)
        with self.assertRaises(servico.Recusada):
            servico.corrigir_ato(self.banco, ato, {"grupo": "AST"}, REV, JUST, False)                 # sem declarar a fonte

    def test_correcao_de_grupo_modalidade_e_assunto_reflete_no_painel_e_na_exportacao(self):
        vertical = self.ato("903/2026")["id"]
        servico.corrigir_ato(self.banco, vertical, {"grupo": "SFT"}, REV, "grupo conferido com a GEDIV", True)
        servico.corrigir_ato(self.banco, self.ato("902/2026")["id"], {"modalidade": "VERTICAL"}, REV, "modalidade conferida", True)
        servico.corrigir_ato(self.banco, self.ato("905/2026")["id"], {"subcategoria": "TS-06"}, REV, "assunto conferido", True)
        self.conferir_tudo()
        p = indicadores.painel(self.banco, {"grupo": "SFT"}, GER)
        self.assertEqual({l["resenha"] for l in p["linhas"]}, {"903/2026"})
        series = indicadores.painel(self.banco, {}, GER)["series"]
        self.assertEqual({s["codigo"]: s["total"] for s in series["por_subcategoria"]}["TS-06"], 1)
        self.assertIn(b"SFT", exportacao.csv(exportacao.linhas_decisoes(indicadores.painel(self.banco, {}, GER))))
        self.assertEqual(len(self.banco.correcoes("ato", vertical)), 1)

    def test_releitura_posterior_nao_perde_a_correcao_e_divergencia_vira_conflito(self):
        vertical = self.ato("903/2026")["id"]
        servico.corrigir_ato(self.banco, vertical, {"grupo": "SFT"}, REV, "grupo conferido com a GEDIV", True)
        self.conferir_tudo()
        self.classificar(refazer=True)
        self.assertEqual(self.ato("903/2026")["grupo"], "SFT")                                       # correção preservada
        self.assertEqual(self.banco.conflitos(), [])                                               # extração igual à original
        # A nova extração muda a classe da decisão já conferida: proposta, não sobrescrita.
        self.ler(self.sha, pag(1, "\n".join([T.HORIZONTAL_GAJ, T.VERTICAL_SEM_GEDIV.replace(" A F\n", " A C\n"), T.LICENCA_ESPECIAL])), versao="v2")
        self.classificar()
        d = self.decisoes(ato_id=vertical)[0]
        self.assertEqual(json.loads(d["detalhe"])["classe_posterior"], "F")
        conflito = [c for c in self.banco.conflitos() if c["campo"] == "classe_posterior"][0]
        self.assertEqual((json.loads(conflito["valor_vigente"]), json.loads(conflito["valor_proposto"])), ("F", "C"))
        servico.resolver_conflito(self.banco, conflito["id"], servico.ACEITAR, REV, "classe C confirmada no PDF", True)
        self.assertEqual(json.loads(self.decisoes(ato_id=vertical)[0]["detalhe"])["classe_posterior"], "C")
        self.assertEqual(self.decisoes(ato_id=vertical)[0]["validacao"], "CONFERIDO")
        self.classificar(refazer=True)
        self.assertEqual([c["estado"] for c in self.banco.conflitos(None)], ["ACEITO"])            # não é reproposto

    def test_metadados_do_ato_nao_ficam_congelados(self):
        self.conferir_tudo()
        self.ler(self.sha, pag(1, "\n".join([T.HORIZONTAL_GAJ.replace("07-10-2026", "05-10-2026"), T.VERTICAL_SEM_GEDIV, T.LICENCA_ESPECIAL])),
                 versao="v2")
        self.classificar()
        self.assertEqual(self.ato("902/2026")["data_expediente"], "2026-10-05")                       # antes: congelado

    def test_revisao_nao_passa_para_outra_pessoa_e_conflitos_simultaneos(self):
        d = [x for x in self.decisoes() if x["processo"] == "SAD-PSE-2026/90003"][0]
        servico.revisar_decisoes(self.banco, [d["id"]], servico.CONFERIR, REV, JUST, True, True)
        # Mesmo processo e posição, outra pessoa e outro cargo na releitura.
        texto = T.HORIZONTAL_GAJ.replace("900003-8 PESSOA FICTICIA TRES POLICIAL PENAL", "900077-7 PESSOA FICTICIA SETENTA AGENTE")
        self.ler(self.sha, pag(1, "\n".join([texto, T.VERTICAL_SEM_GEDIV, T.LICENCA_ESPECIAL])), versao="v2")
        self.classificar()
        atual = self.decisoes(id=d["id"])[0]
        self.assertEqual((atual["matricula"], atual["servidor"], atual["validacao"]), ("900003-8", "PESSOA FICTICIA TRES", "CONFERIDO"))
        campos = sorted(c["campo"] for c in self.banco.conflitos() if c["alvo_id"] == d["id"])
        self.assertEqual(campos, ["cargo", "matricula", "servidor"])
        self.assertTrue(self.banco.trilha("decisao", d["id"]))

    def test_registro_controlado_de_decisao_omitida(self):
        ato = self.ato("902/2026")
        trecho = "SAD-PSE-2026/90004 900004-6 PESSOA FICTICIA QUATRO TECNICO DE ENFERMAGEM III IV"
        with self.assertRaises(servico.Recusada):                                          # trecho que não está no PDF
            servico.registrar_decisao_omitida(self.banco, ato["id"], 1, "texto que não existe no documento", {"processo": "X"}, REV, JUST, True)
        with self.assertRaises(servico.Recusada):                                          # valor que não está no trecho
            servico.registrar_decisao_omitida(self.banco, ato["id"], 1, trecho, {"processo": "SAD-PSE-2026/99999"}, REV, JUST, True)
        # Como a decisão já existe extraída, o registro manual da mesma pessoa não pode duplicá-la.
        r = servico.registrar_decisao_omitida(self.banco, ato["id"], 1, trecho,
                                              {"processo": "SAD-PSE-2026/90004", "matricula": "900004-6", "nivel_anterior": "III",
                                               "nivel_atual": "IV", "resultado": "DEFERIDO"}, REV, "omitida na extração", True)
        with self.assertRaises(servico.Recusada):
            servico.registrar_decisao_omitida(self.banco, ato["id"], 1, trecho, {"processo": "SAD-PSE-2026/90004", "matricula": "900004-6",
                                                                               "nivel_anterior": "III", "nivel_atual": "IV",
                                                                               "resultado": "DEFERIDO"}, REV, "omitida na extração", True)
        manual = self.decisoes(id=r["id"])[0]
        self.assertEqual((manual["origem"], manual["validacao"]), ("MANUAL", "CONFERIDO"))
        self.assertEqual(self.banco.trilha("decisao", r["id"])[0]["acao"], "REGISTRAR_OMITIDA")


class TesteAPIGerencial(TP.Base):
    TOKEN, pedir = TP.TesteAPI.TOKEN, TP.TesteAPI.pedir

    def setUp(self):
        super().setUp()
        self.base_padrao()
        self.servidor = TP.criar_servidor(self.pasta, self.TOKEN, porta=0)
        TP.threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def test_correcao_pela_api_exige_credencial_e_aparece_no_detalhe(self):
        ato = self.ato("903/2026")
        corpo = {"alvo": "ato_classificacao", "id": ato["id"], "responsavel": REV, "justificativa": "grupo conferido",
                 "confirma_fonte": True, "correcoes": {"grupo": "SFT"}}
        self.assertEqual(self.pedir("/api/revisao", corpo=corpo)[0], 401)
        self.assertEqual(self.pedir("/api/revisao", "credencial-errada-0123456789", corpo)[0], 403)
        self.assertEqual(self.pedir("/api/revisao", self.TOKEN, {**corpo, "correcoes": {"grupo": "XYZ"}})[0], 422)
        status, _, resposta = self.pedir("/api/revisao", self.TOKEN, corpo)
        self.assertEqual(status, 200, resposta)
        detalhe = json.loads(self.pedir(f"/api/ato/{ato['id']}", self.TOKEN)[2])
        self.assertEqual((detalhe["ato"]["grupo"], detalhe["correcoes"][0]["campo"]), ("SFT", "grupo"))
        self.assertEqual(self.pedir("/api/conflitos")[0], 401)
        self.assertEqual(json.loads(self.pedir("/api/conflitos", self.TOKEN)[2])["vinculos_orfaos"], [])
        publico = self.pedir("/api/painel")[2].decode()
        self.assertNotIn("grupo conferido", publico)                                 # justificativa continua privada


# ===================================================================================== E — eventos e vínculos
class TesteEventos(Base):
    def setUp(self):
        super().setUp()
        self.base_padrao()
        self.eventos = {e["tipo"]: e for e in self.banco.con.execute("SELECT * FROM evento")}

    def test_vinculo_valido_e_alvo_inadequado(self):
        e = self.eventos[C.SEM_EFEITO]
        republicacao = self.banco.con.execute("SELECT id FROM ato WHERE natureza <> 'ORIGINAL'").fetchone()
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, e["id"], servico.VINCULAR, REV, JUST, republicacao[0], True)
        servico.revisar_evento(self.banco, e["id"], servico.VINCULAR, REV, JUST, None, True)
        self.assertEqual(self.banco.vinculos_orfaos(), [])

    def test_ato_modificador_de_evento_revisado_nao_some_na_reclassificacao(self):
        e = self.eventos[C.SEM_EFEITO]
        servico.revisar_evento(self.banco, e["id"], servico.VINCULAR, REV, JUST, None, True)
        sha = e["sha256"]
        # A releitura deixa de trazer a portaria (o ato modificador): antes, o ato era apagado e o evento ficava órfão.
        self.ler(sha, pag(1, "\n".join([T.REPUBLICACAO, T.LICENCA_ESPECIAL])), versao="v2")
        self.classificar()
        self.assertIsNotNone(self.banco.con.execute("SELECT 1 FROM ato WHERE id = ?", (e["ato_id"],)).fetchone())
        self.assertEqual(self.banco.con.execute("SELECT estado FROM evento WHERE id = ?", (e["id"],)).fetchone()[0], "VALIDADO")
        self.assertEqual(self.banco.vinculos_orfaos(), [])
        self.ler(sha, pag(1, "\n".join([T.PORTARIA_SEM_EFEITO, T.REPUBLICACAO, T.LICENCA_ESPECIAL])), versao="v3")
        self.classificar()                                                                  # releitura que recupera o ato
        self.assertEqual(self.banco.vinculos_orfaos(), [])

    def test_evento_reaberto_e_vinculo_orfao_historico(self):
        e = self.eventos[C.SEM_EFEITO]
        servico.revisar_evento(self.banco, e["id"], servico.VINCULAR, REV, JUST, None, True)
        servico.revisar_evento(self.banco, e["id"], servico.REABRIR, REV, JUST)
        self.assertEqual(self.banco.con.execute("SELECT estado FROM evento WHERE id = ?", (e["id"],)).fetchone()[0], "SUGERIDO")
        with self.banco.con:                                                                # banco histórico com referência perdida
            self.banco.con.execute("UPDATE evento SET ato_original_id = 'inexistente0000000000' WHERE id = ?", (e["id"],))
        self.assertEqual([(o["evento"], o["problema"]) for o in self.banco.vinculos_orfaos()], [(e["id"], "ATO_INEXISTENTE")])


# ===================================================================================== F — migração v8
class TesteMigracaoV8(unittest.TestCase):
    def test_banco_v7_com_dados_ganha_revisoes_e_identidades_sem_reclassificar(self):
        from tests.test_migracoes import _criar_ate, _executar
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "b.sqlite3"
        _criar_ate(caminho, 7)
        _executar(caminho,
                  "INSERT INTO arquivo VALUES ('s1', 10, 'x', 'agora')",
                  "INSERT INTO leitura (sha256, situacao, versao_leitor, paginas, concluida_em) VALUES ('s1', 'LIDA', 'v1', 1, 'agora')",
                  "INSERT INTO pagina (sha256, numero, metodo, colunas, texto) VALUES ('s1', 1, 'TEXTO', 1, 'texto')",
                  "INSERT INTO classificacao VALUES ('s1', 'GEDIV', 'r1', 1, 1, 0, 0, '[]', 'agora')",
                  "INSERT INTO ato (id, gerencia, sha256, tipo, numero, pagina, pagina_final, vinculo, natureza, resultado, texto, versao_regras) "
                  "VALUES ('a1', 'GEDIV', 's1', 'RESENHA', '901/2026', 1, 1, 'EXPRESSO', 'ORIGINAL', 'DEFERIDO', 't', 'r1')",
                  "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, resultado, trecho, validacao) "
                  "VALUES ('d1', 'a1', 's1', 1, 'SAD-PSE-2026/1', 'DEFERIDO', 't', 'CONFERIDO')",
                  "INSERT INTO evento (id, gerencia, sha256, ato_id, tipo, pagina, vinculo, texto, ato_original_id, estado) "
                  "VALUES ('e1', 'GEDIV', 's1', 'a1', 'SEM_EFEITO', 1, 'EXPRESSO', 't', 'a1', 'VALIDADO')")
        with B.Banco(caminho) as banco:
            self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
            self.assertIsNotNone(banco.con.execute("SELECT revisao FROM leitura").fetchone()[0])
            self.assertEqual(banco.arquivos_sem_classificacao("GEDIV", "r1"), [])                     # não reclassifica tudo
            d = banco.con.execute("SELECT chave_logica, vigente, validacao FROM decisao").fetchone()
            self.assertEqual((d["vigente"], d["validacao"]), (1, "CONFERIDO"))
            self.assertTrue(d["chave_logica"].endswith("|P:SADPSE20261"))
            self.assertEqual(banco.con.execute("SELECT estado FROM evento").fetchone()[0], "VALIDADO")
            self.assertTrue(Path(f"{caminho}.antes-v{B.VERSAO_ESQUEMA}.bak").exists())
        with B.Banco(caminho) as banco:                                                           # reabertura idempotente
            self.assertEqual(B.estruturas_pendentes(banco.con), {})


if __name__ == "__main__":
    unittest.main()
