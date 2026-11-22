"""Contratos de apresentação e privacidade. Somente publicações/pessoas fictícias."""
import copy
import io
import json
import unittest
import zipfile
import xml.etree.ElementTree as ET

from observatorio.nucleo import banco as B
from observatorio.painel import documental as D, exportacao, indicadores
from tests import test_painel as TP, textos_doe as T

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def registro(**campos):
    return dict(gerencia_painel="GEDIV", tipo="RESENHA", resenha="9301/2099", pagina=4,
                sufixo=None, numero_edicao="99999", data_edicao="2099-03-02", sha256="a" * 64,
                texto_identificacao="SECRETARIA DE ESTADO DA ADMINISTRAÇÃO RESENHA Nº 9301/2099 "
                "DEREH/GS/SEAD GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS VANTAGENS "
                "O SECRETÁRIO DE ESTADO resolve DEFERIR os pedidos fictícios.") | campos


class Identificacao(unittest.TestCase):
    def test_cabecalho_expresso_sem_sufixo_persistido(self):
        entrada = registro()
        antes = copy.deepcopy(entrada)
        resultado = D.identificar(entrada)
        self.assertEqual(resultado["orgao_emitente"], "SEAD — Secretaria de Estado da Administração")
        self.assertEqual(resultado["unidade_emissora"], "DEREH / GEDIV")
        self.assertEqual(resultado["sufixo_documental"], "")
        self.assertIsNone(entrada["sufixo"])
        self.assertEqual(entrada, antes)
        self.assertIn("SEAD / DEREH / GEDIV — Resenha 9301/2099 — DOE 99999, 02/03/2099, p.4",
                      resultado["identificacao_documental"])

    def test_namespace_e_sufixo_nao_comprovam_emitente(self):
        r = D.identificar(registro(texto_identificacao="", sufixo="-DEREH/GS/SEAD"))
        self.assertEqual(r["gerencia_painel"], "GEDIV")
        self.assertEqual(r["orgao_emitente"], "EMITENTE_NAO_CONFIRMADO")
        self.assertEqual(r["unidade_emissora"], "")

    def test_mencao_no_corpo_nao_vira_cabecalho(self):
        r = D.identificar(registro(texto_identificacao="RESENHA Nº 9301/2099 O PRESIDENTE informa a "
                                  "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO e a GEDIV sobre assunto fictício."))
        self.assertEqual(r["orgao_emitente"], "EMITENTE_NAO_CONFIRMADO")
        self.assertEqual(r["unidade_emissora"], "")

    def test_emitente_externo_nao_e_transformado_em_sead(self):
        r = D.identificar(registro(texto_identificacao="RESENHA/PBPREV/GP/Nº 9301/2099 "
                                  "O PRESIDENTE da Paraíba Previdência resolve assunto fictício."))
        self.assertEqual(r["gerencia_painel"], "GEDIV")
        self.assertEqual(r["orgao_emitente"], "PBPREV — Paraíba Previdência")
        self.assertEqual(r["unidade_emissora"], "GP")

    def test_cabecalho_contraditorio_nao_escolhe_orgao(self):
        r = D.identificar(registro(texto_identificacao="SECRETARIA DE ESTADO DA ADMINISTRAÇÃO "
                                  "RESENHA/PBPREV/GP/Nº 9301/2099"))
        self.assertEqual(r["orgao_emitente"], "EMITENTE_NAO_CONFIRMADO")

    def test_duas_secretarias_no_cabecalho_ficam_nao_confirmadas(self):
        r = D.identificar(registro(texto_identificacao="SECRETARIA DE ESTADO DA ADMINISTRAÇÃO "
                                  "RESENHA Nº 9301/2099 SECRETARIA DE ESTADO DA SAÚDE"))
        self.assertEqual(r["orgao_emitente"], "EMITENTE_NAO_CONFIRMADO")
        self.assertEqual(r["unidade_emissora"], "")

    def test_nao_inventa_edicao_data_ou_sha(self):
        r = D.identificar(registro(numero_edicao=None, data_edicao=None, data="2099-03-02", sha256=None))
        self.assertEqual((r["numero_edicao"], r["data_edicao"], r["pdf_sha256"]), ("", "", ""))
        self.assertIn("edição não informada", r["identificacao_documental"])
        self.assertNotIn("02/03/2099", r["identificacao_documental"])

    def test_metadados_invalidos_nao_transportam_texto_livre(self):
        segredo = "MARCADOR PRIVADO PESSOA FICTICIA"
        r = D.identificar(registro(texto_identificacao=segredo, numero_edicao=segredo, data_edicao="2099-02-31",
                                  sha256=segredo, resenha=segredo, sufixo=segredo, tipo=segredo, pagina=segredo))
        self.assertNotIn(segredo, json.dumps(r))
        self.assertEqual(r["orgao_emitente"], "EMITENTE_NAO_CONFIRMADO")
        self.assertEqual(r["data_edicao"], "")


class Integracao(TP.Base):
    def preparar(self):
        TP.carregar(self.banco, "a", "2026-10-09", T.HORIZONTAL_GAJ)
        TP.processo.classificar_pendentes(self.banco)

    def test_projecao_documental_nao_grava_ou_muda_identidades(self):
        self.preparar()
        antes = {t: [tuple(r) for r in self.banco.con.execute("SELECT * FROM " + t)]
                 for t in ("ato", "decisao", "leitura", "classificacao", "auditoria")}
        p = self.painel(escopo="pendente")
        self.assertEqual(len(p["linhas"]), 3)
        for linha in p["linhas"]:
            self.assertEqual(linha["gerencia_painel"], "GEDIV")
            self.assertIn("SEAD", linha["orgao_emitente"])
            self.assertNotIn("texto_identificacao", linha)
            self.assertEqual(linha["pdf_sha256"], "a" * 64)
        for t, rows in antes.items():
            self.assertEqual([tuple(r) for r in self.banco.con.execute("SELECT * FROM " + t)], rows)
        self.assertEqual(self.banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)

    def test_colunas_historicas_e_tipos_preservados_antes_das_novas(self):
        self.preparar()
        p = self.painel(escopo="pendente")
        rows = exportacao.linhas_decisoes(p)
        historicas = ["Data da publicação", "Resenha", "Página", "Eixo", "Modalidade", "Condição", "Grupo", "Subcategoria",
                      "Processo", "Servidor", "Matrícula", "Lotação", "Cargo", "Classe/nível e demais dados", "Resultado",
                      "Natureza", "Vínculo GEDIV", "Validação", "Revisor", "Revisado em", "Refeito", "Tornado sem efeito",
                      "Fonte oficial", "Evidência (trecho)", "ID da decisão", "ID do ato", "Conflito aberto"]
        self.assertEqual(rows[0][:27], historicas)
        self.assertEqual(len(rows[0]), 36)
        self.assertEqual(rows[1][24], p["linhas"][0]["id"])
        self.assertEqual(rows[1][25], p["linhas"][0]["ato_id"])
        self.assertIsInstance(rows[1][2], int)
        self.assertEqual(rows[1][27], "GEDIV")
        self.assertIn("SEAD", rows[1][-1])
        with zipfile.ZipFile(io.BytesIO(exportacao.planilha(p))) as z:
            xml = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
        atos = xml.findall(".//s:row", NS)
        self.assertEqual(len(atos[0].findall("s:c", NS)), 24)
        self.assertEqual(atos[1].findall("s:c", NS)[7].findtext("s:v", namespaces=NS), "3")

    def test_perfil_publico_so_recebe_metadados_controlados(self):
        self.preparar()
        self.banco.con.execute("UPDATE ato SET texto=texto || ?", (" MARCADOR-PRIVADO-PESSOA-FICTICIA",))
        self.banco.con.commit()
        self.conferir("902/2026")
        p = self.painel(perfil=indicadores.PUBLICO)
        self.assertTrue(p["resenhas"])
        self.assertIn("orgao_emitente", p["resenhas"][0])
        self.assertNotIn("MARCADOR-PRIVADO", json.dumps(p))
        self.assertNotIn("PESSOA FICTICIA", json.dumps(p))
        self.assertEqual(p["linhas"], [])

    def test_documento_sem_ato_gediv_nao_e_falha_nem_ausencia_confirmada(self):
        TP.carregar(self.banco, "b", "2026-10-09", T.OUTRA_SECRETARIA)
        TP.processo.classificar_pendentes(self.banco)
        p = self.painel(escopo="pendente")
        self.assertEqual((p["linhas"], p["resenhas"]), ([], []))
        self.assertEqual(p["meta"]["cobertura"]["edicoes_lidas"], 1)
        self.assertFalse(p["meta"]["cobertura"]["completa"])
        self.assertEqual(p["meta"]["cobertura"]["edicoes_com_pendencia_de_leitura"], 0)

    def test_base_sem_edicao_nao_confirma_ausencia_de_publicacao(self):
        p = self.painel(escopo="pendente")
        self.assertEqual(p["meta"]["cobertura"]["edicoes_no_acervo"], 0)
        self.assertFalse(p["meta"]["cobertura"]["completa"])
        self.assertEqual(p["resenhas"], [])
