"""Banco → revisão → indicadores → exportação → API. Dados SINTÉTICOS.

Os cenários de aceitação vêm da Especificação V3 (seção 9): a contagem dos sete cartões, as datas
de cada indicador, a separação entre candidato e conferido e o bloqueio de dados individuais."""
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from observatorio.gerencias.gediv import processo
from observatorio.gerencias.gediv import catalogo as C
from observatorio.nucleo.banco import Banco
from observatorio.painel import exportacao, indicadores
from observatorio.revisao import servico
from observatorio.web.servidor import criar_servidor
from tests import textos_doe as T

REVISOR, JUST = "Revisora de Teste", "conferido no PDF sintético"
GER = indicadores.GERENCIA_PERFIL


def carregar(banco: Banco, marca: str, data: str, texto: str, url: str | None = None) -> str:
    """Registra um 'arquivo' já lido (sem PDF), como a leitura faria."""
    sha = (marca * 64)[:64]
    banco.registrar_descoberta("manual" if not url else "auniao", url or f"manual:{marca}", data, "normal", 0, marca)
    banco.registrar_arquivo(banco.publicacao("manual" if not url else "auniao", url or f"manual:{marca}")["id"], sha, 10, f"{marca}.pdf")
    banco.registrar_leitura(sha, "LIDA", "teste", [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": texto, "qualidade": "OK",
                                                    "palavras": len(texto.split())}], "1", data, None)
    return sha


class Base(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco = Banco(self.pasta / "observatorio.sqlite3")
        self.addCleanup(lambda: self.banco.fechar())

    def base_padrao(self):
        carregar(self.banco, "a", "2026-10-09", "\n".join([T.ANOTACAO, T.HORIZONTAL_GAJ, T.VERTICAL_SEM_GEDIV, T.INDEFERIDA_MAG, T.OUTRA_GERENCIA]),
                 "https://auniao.pb.gov.br/servicos/doe/2026/outubro/diario-oficial-09-10-2026-portal.pdf")
        carregar(self.banco, "b", "2026-10-15", "\n".join([T.PORTARIA_SEM_EFEITO, T.REPUBLICACAO, T.LICENCA_ESPECIAL]))
        return processo.classificar_pendentes(self.banco)

    def ato(self, numero, natureza="ORIGINAL"):
        return self.banco.con.execute("SELECT * FROM ato WHERE numero = ? AND natureza = ?", (numero, natureza)).fetchone()

    def conferir(self, numero, vinculo=False):
        return servico.revisar_ato(self.banco, self.ato(numero)["id"], servico.CONFERIR, REVISOR, JUST, True, vinculo)

    def painel(self, perfil=GER, **filtros):
        return indicadores.painel(self.banco, filtros, perfil)


class TesteCandidatosNaoSaoConferidos(Base):
    def test_tudo_nasce_pendente_e_os_indicadores_ficam_em_zero(self):
        resumo = self.base_padrao()
        self.assertEqual((resumo["decisoes"], resumo["descartados"]), (10, 1))
        p = self.painel()
        self.assertEqual(p["indicadores"], dict(processos=0, resenhas=0, decisoes=0, deferidos=0, indeferidos=0, refeitos=0, sem_efeito=0))
        self.assertEqual((p["apoio"]["decisoes_pendentes"], p["apoio"]["decisoes_conferidas"]), (10, 0))
        self.assertEqual(p["linhas"], [])

    def test_escopo_pendente_e_rotulado_preliminar_e_nao_calcula_refeitos(self):
        self.base_padrao()
        p = self.painel(escopo="pendente")
        self.assertTrue(p["meta"]["preliminar"])
        self.assertIn("preliminares", p["meta"]["rotulo"])
        self.assertEqual((p["indicadores"]["decisoes"], p["indicadores"]["refeitos"], p["indicadores"]["sem_efeito"]), (8, None, None))

    def test_perfil_publico_nunca_recebe_pendentes_nem_linhas_individuais(self):
        self.base_padrao()
        self.conferir("901/2026")
        p = self.painel(indicadores.PUBLICO, escopo="pendente", busca="PESSOA")
        self.assertEqual((p["meta"]["escopo"], p["meta"]["filtros"]["busca"], p["linhas"]), ("conferido", None, []))
        self.assertEqual(p["indicadores"]["decisoes"], 2)
        self.assertNotIn("PESSOA FICTICIA", json.dumps(p, ensure_ascii=False))
        self.assertNotIn("SAD-PSE", json.dumps(p, ensure_ascii=False))
        self.assertNotIn("900000", json.dumps(p, ensure_ascii=False))


class TesteRevisao(Base):
    def test_conferir_exige_responsavel_justificativa_e_declaracao_da_fonte(self):
        self.base_padrao()
        ato = self.ato("901/2026")["id"]
        for argumentos in (("", JUST, True), (REVISOR, "", True), (REVISOR, JUST, False)):
            with self.assertRaises(servico.Recusada):
                servico.revisar_ato(self.banco, ato, servico.CONFERIR, *argumentos)
        self.assertEqual(self.painel()["indicadores"]["decisoes"], 0)

    def test_ato_sem_gediv_expressa_exige_confirmacao_do_vinculo(self):
        self.base_padrao()
        with self.assertRaises(servico.Recusada):
            self.conferir("903/2026")
        self.conferir("903/2026", vinculo=True)
        self.assertEqual(self.painel()["indicadores"]["decisoes"], 1)

    def test_trilha_registra_autor_estado_anterior_e_posterior_e_permite_reabrir(self):
        self.base_padrao()
        self.conferir("901/2026")
        trilha = self.banco.trilha("decisao")
        self.assertEqual(len(trilha), 2)
        self.assertEqual((trilha[0]["autor"], trilha[0]["acao"], json.loads(trilha[0]["anterior"])["validacao"],
                          json.loads(trilha[0]["posterior"])["validacao"]), (REVISOR, "CONFERIR", "PENDENTE", "CONFERIDO"))
        servico.revisar_ato(self.banco, self.ato("901/2026")["id"], servico.REABRIR, REVISOR, "reabertura para nova conferência")
        self.assertEqual((self.painel()["indicadores"]["decisoes"], len(self.banco.trilha("decisao"))), (0, 4))

    def test_rejeitado_nao_conta_e_correcao_de_campo_fica_auditada(self):
        self.base_padrao()
        ids = [d["id"] for d in self.banco.con.execute("SELECT id FROM decisao WHERE ato_id = ? ORDER BY rowid", (self.ato("901/2026")["id"],))]
        servico.revisar_decisoes(self.banco, [ids[0]], servico.REJEITAR, REVISOR, "linha de outra unidade")
        servico.revisar_decisoes(self.banco, [ids[1]], servico.CONFERIR, REVISOR, JUST, True, correcoes={"resultado": "INDEFERIDO"})
        p = self.painel()
        self.assertEqual((p["indicadores"]["decisoes"], p["indicadores"]["indeferidos"], p["apoio"]["decisoes_rejeitadas"]), (1, 1, 1))
        with self.assertRaises(servico.Recusada):
            servico.revisar_decisoes(self.banco, [ids[1]], servico.CONFERIR, REVISOR, JUST, True, correcoes={"validacao": "X"})

    def test_reclassificar_preserva_o_que_ja_foi_revisado_e_nao_duplica(self):
        self.base_padrao()
        self.conferir("901/2026")
        antes = self.banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0]
        resumo = processo.classificar_pendentes(self.banco, refazer=True)
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], antes)
        self.assertEqual((resumo["preservadas_por_revisao"], self.painel()["indicadores"]["decisoes"]), (2, 2))
        self.assertEqual(self.banco.con.execute("SELECT revisor FROM decisao WHERE validacao = 'CONFERIDO'").fetchone()[0], REVISOR)


class TesteIndicadores(Base):
    def conferir_tudo(self):
        self.base_padrao()
        for numero in ("901/2026", "902/2026", "904/2026", "905/2026"):
            self.conferir(numero)
        self.conferir("903/2026", vinculo=True)

    def test_os_sete_cartoes_contam_unidades_diferentes(self):
        self.conferir_tudo()
        i = self.painel()["indicadores"]
        # 5 resenhas originais; 8 decisões; a 902 tem 3 linhas e 2 processos distintos -> 7 processos.
        self.assertEqual((i["resenhas"], i["decisoes"], i["processos"], i["deferidos"], i["indeferidos"]), (5, 8, 7, 7, 1))
        self.assertEqual((i["refeitos"], i["sem_efeito"]), (0, 0))      # eventos ainda sem vínculo validado

    def test_evento_so_conta_depois_de_vinculo_validado_e_pela_data_do_evento(self):
        self.conferir_tudo()
        eventos = {e["tipo"]: e for e in self.banco.con.execute("SELECT * FROM evento")}
        self.assertEqual({e["estado"] for e in eventos.values()}, {"SUGERIDO"})
        self.assertEqual(eventos[C.SEM_EFEITO]["ato_sugerido_id"], self.ato("904/2026")["id"])
        self.assertEqual(self.painel()["apoio"]["eventos_sem_vinculo"], 2)
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, eventos[C.SEM_EFEITO]["id"], servico.VINCULAR, REVISOR, JUST)      # sem declarar a fonte
        for e in eventos.values():
            servico.revisar_evento(self.banco, e["id"], servico.VINCULAR, REVISOR, JUST, None, True)
        i = self.painel()["indicadores"]
        self.assertEqual((i["refeitos"], i["sem_efeito"], i["decisoes"], i["processos"]), (1, 1, 8, 7))   # republicação não cria decisão
        # O ato original é de 09/10; o evento é de 15/10: entra em Refeitos de 15/10, não nos originais desse dia.
        dia15 = self.painel(inicio="2026-10-15", fim="2026-10-15")["indicadores"]
        self.assertEqual((dia15["refeitos"], dia15["sem_efeito"], dia15["decisoes"]), (1, 1, 1))
        dia09 = self.painel(inicio="2026-10-09", fim="2026-10-09")["indicadores"]
        self.assertEqual((dia09["refeitos"], dia09["sem_efeito"], dia09["decisoes"]), (0, 0, 7))

    def test_evento_sem_ato_original_identificavel_permanece_pendente(self):
        carregar(self.banco, "c", "2026-10-15", T.PORTARIA_SEM_EFEITO)       # a resenha 904 não está na base
        processo.classificar_pendentes(self.banco)
        evento = self.banco.con.execute("SELECT * FROM evento").fetchone()
        self.assertEqual((evento["estado"], evento["ato_sugerido_id"], evento["ato_original_id"]), ("PENDENTE_VINCULACAO", None, None))
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, evento["id"], servico.VINCULAR, REVISOR, JUST, None, True)
        p = self.painel()
        self.assertEqual((p["indicadores"]["sem_efeito"], p["apoio"]["eventos_sem_vinculo"]), (0, 1))

    def test_clique_no_cartao_restringe_a_tabela_ao_universo_do_indicador(self):
        self.conferir_tudo()
        p = self.painel(cartao="indeferidos")
        self.assertEqual(([l["resultado"] for l in p["linhas"]], [r["resenha"] for r in p["resenhas"]]), (["INDEFERIDO"], ["904/2026"]))
        self.assertEqual(p["indicadores"]["decisoes"], 8)                # os cartões não mudam com o clique

    def test_filtros_de_eixo_modalidade_grupo_e_subcategoria(self):
        self.conferir_tudo()
        self.assertEqual(self.painel(eixo="PROGRESSAO")["indicadores"]["decisoes"], 5)
        self.assertEqual(self.painel(eixo="TEMPO_SERVICO")["indicadores"]["decisoes"], 3)
        mag = self.painel(eixo="PROGRESSAO", modalidade="HORIZONTAL", grupo="MAG")
        self.assertEqual((mag["indicadores"]["decisoes"], {l["grupo"] for l in mag["linhas"]}), (1, {"MAG"}))
        self.assertEqual(self.painel(grupo="GAJ,TEC-ADM")["indicadores"]["decisoes"], 4)
        self.assertEqual(self.painel(subcategoria="TS-05")["indicadores"]["decisoes"], 1)
        self.assertEqual(self.painel(vinculo="NAO_EXPRESSO")["indicadores"]["decisoes"], 1)
        self.assertEqual(self.painel(busca="ficticia tres")["indicadores"]["decisoes"], 1)
        self.assertEqual(self.painel(eixo="INVENTADO", grupo="XYZ")["indicadores"]["decisoes"], 8)   # valores fora do dicionário são ignorados

    def test_series_mantem_dois_eixos_e_as_sete_subcategorias_visiveis(self):
        self.conferir_tudo()
        s = self.painel()["series"]
        self.assertEqual([(x["chave"], x["total"]) for x in s["por_assunto"]], [("VERTICAL", 1), ("HORIZONTAL", 4), ("TEMPO_SERVICO", 3)])
        self.assertEqual([x["codigo"] for x in s["por_subcategoria"]], [f"TS-0{i}" for i in range(1, 8)])
        self.assertEqual({x["codigo"]: x["situacao"] for x in s["por_subcategoria"] if not x["total"]}["TS-07"], "cobertura pendente")
        self.assertEqual({x["grupo"]: x["total"] for x in s["por_grupo"]}, {"MAG": 1, "GAJ": 3, "TEC-ADM": 1})
        self.assertEqual(sum(x["total"] for x in s["por_data"]), 8)

    def test_fonte_oficial_so_quando_conhecida(self):
        self.conferir_tudo()
        linhas = {l["resenha"]: l for l in self.painel()["linhas"]}
        self.assertEqual(linhas["901/2026"]["url_oficial"],
                         "https://auniao.pb.gov.br/servicos/doe/2026/outubro/diario-oficial-09-10-2026-portal.pdf#page=1")
        self.assertIsNone(linhas["905/2026"]["url_oficial"])           # importação manual: endereço não é inventado

    def test_outras_publicacoes(self):
        carregar(self.banco, "d", "2026-10-09", T.ABONO + "\n" + T.REPUBLICACAO)
        processo.classificar_pendentes(self.banco)
        tipos = sorted(o["tipo"] for o in indicadores.outras_publicacoes(self.banco, GER))
        self.assertEqual(tipos, ["REPUBLICADO_POR_INCORRECAO", "TEMA_FORA_DOS_EIXOS"])
        self.assertTrue(all("trecho" not in o for o in indicadores.outras_publicacoes(self.banco, indicadores.PUBLICO)))


class TesteExportacao(Base):
    def test_planilha_tem_as_abas_e_os_mesmos_totais_da_tela(self):
        self.base_padrao()
        self.conferir("901/2026")
        self.conferir("902/2026")
        p = self.painel()
        with zipfile.ZipFile(io.BytesIO(exportacao.planilha(p))) as z:
            pasta = z.read("xl/workbook.xml").decode()
            decisoes = z.read("xl/worksheets/sheet1.xml").decode()
        for aba in ("Decisoes", "Atos", "Eventos_de_Alteracao", "Indicadores", "Metadados"):
            self.assertIn(f'name="{aba}"', pasta)
        self.assertEqual(decisoes.count("<row "), p["indicadores"]["decisoes"] + 1)
        self.assertIn("PESSOA FICTICIA UM", decisoes)

    def test_planilha_abre_em_leitor_independente(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl não instalado")
        self.base_padrao()
        self.conferir("902/2026")
        livro = openpyxl.load_workbook(io.BytesIO(exportacao.planilha(self.painel())))
        self.assertEqual(livro.sheetnames, ["Decisoes", "Atos", "Eventos_de_Alteracao", "Indicadores", "Metadados"])
        self.assertEqual(livro["Decisoes"].max_row, 4)
        self.assertEqual(livro["Decisoes"]["A1"].value, "Data da publicação")

    def test_celulas_que_parecem_formulas_sao_neutralizadas(self):
        self.assertEqual(exportacao.seguro("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(exportacao.seguro("@x"), "'@x")
        self.assertEqual(exportacao.seguro("SAD-PSE-2026/1"), "SAD-PSE-2026/1")
        self.assertTrue(exportacao.csv([["a", "=1+1"]]).decode("utf-8").startswith("﻿"))
        self.assertIn("\"'=1+1\"", exportacao.csv([["a", "=1+1"]]).decode("utf-8"))


class TesteAPI(Base):
    TOKEN = "credencial-de-teste-0123456789"

    def setUp(self):
        super().setUp()
        self.base_padrao()
        self.conferir("901/2026")
        self.servidor = criar_servidor(self.pasta, self.TOKEN, porta=0)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def pedir(self, caminho, token=None, corpo=None):
        pedido = urllib.request.Request(self.url + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                        headers={"Content-Type": "application/json"} if corpo is not None else {})
        if token:
            pedido.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(pedido, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_pagina_e_arquivos_estaticos_com_cabecalhos_de_seguranca(self):
        status, cabecalhos, corpo = self.pedir("/")
        self.assertEqual(status, 200)
        self.assertIn("Observatório do Diário Oficial", corpo.decode())
        self.assertIn("default-src 'self'", cabecalhos["Content-Security-Policy"])
        self.assertEqual(self.pedir("/estatico/app.js")[0], 200)
        self.assertEqual(self.pedir("/estatico/../servidor.py")[0], 404)

    def test_publico_recebe_agregados_sem_dados_individuais(self):
        status, _, corpo = self.pedir("/api/painel?escopo=pendente")
        dados = json.loads(corpo)
        self.assertEqual((status, dados["meta"]["perfil"], dados["meta"]["escopo"], dados["linhas"]), (200, "publico", "conferido", []))
        self.assertEqual(dados["indicadores"]["decisoes"], 2)
        self.assertNotIn("PESSOA FICTICIA", corpo.decode())

    def test_rotas_restritas_exigem_credencial_valida(self):
        ato = self.ato("901/2026")
        for rota in ("/api/exportar", f"/api/ato/{ato['id']}", f"/api/pdf/{ato['sha256']}", "/api/auditoria"):
            with self.subTest(rota=rota):
                self.assertEqual(self.pedir(rota)[0], 401)
                self.assertEqual(self.pedir(rota, "credencial-errada-0123456789")[0], 403)
        self.assertEqual(self.pedir("/api/revisao", corpo={"alvo": "ato"})[0], 401)

    def test_gerencia_ve_linhas_detalhe_do_ato_e_exporta(self):
        dados = json.loads(self.pedir("/api/painel", self.TOKEN)[2])
        self.assertEqual((dados["meta"]["perfil"], len(dados["linhas"])), ("gerencia", 2))
        status, _, corpo = self.pedir(f"/api/ato/{self.ato('901/2026')['id']}", self.TOKEN)
        self.assertEqual((status, len(json.loads(corpo)["decisoes"])), (200, 2))
        status, cabecalhos, corpo = self.pedir("/api/exportar?formato=xlsx", self.TOKEN)
        self.assertEqual((status, corpo[:2]), (200, b"PK"))
        self.assertIn(".xlsx", cabecalhos["Content-Disposition"])
        status, _, corpo = self.pedir("/api/exportar?formato=csv", self.TOKEN)
        self.assertEqual((status, len(corpo.decode("utf-8").strip().split("\r\n"))), (200, 3))
        self.assertEqual(self.banco.trilha("painel")[0]["acao"], "EXPORTAR")          # exportação fica na trilha

    def test_revisao_pela_api_atualiza_os_indicadores(self):
        corpo = {"alvo": "ato", "id": self.ato("902/2026")["id"], "decisao": "CONFERIR", "responsavel": REVISOR, "justificativa": JUST}
        status, _, resposta = self.pedir("/api/revisao", self.TOKEN, corpo)
        self.assertEqual(status, 422)                                   # faltou declarar a consulta à fonte
        self.assertIn("PDF oficial", json.loads(resposta)["erro"])
        status, _, resposta = self.pedir("/api/revisao", self.TOKEN, {**corpo, "confirma_fonte": True})
        self.assertEqual((status, json.loads(resposta)), (200, {"alterados": 3, "estado": "CONFERIDO"}))
        self.assertEqual(json.loads(self.pedir("/api/painel")[2])["indicadores"]["decisoes"], 5)

    def test_catalogo_saude_outras_e_rota_inexistente(self):
        catalogo = json.loads(self.pedir("/api/catalogo")[2])
        self.assertEqual((len(catalogo["eixos"]), len(catalogo["grupos"]), len(catalogo["subcategorias"])), (2, 16, 7))
        self.assertEqual(json.loads(self.pedir("/api/saude")[2])["cobertura"]["completa"], False)
        self.assertEqual(self.pedir("/api/outras")[0], 200)
        self.assertEqual(self.pedir("/api/nada")[0], 404)

    def test_credencial_curta_e_recusada_na_inicializacao(self):
        with self.assertRaises(ValueError):
            criar_servidor(self.pasta, "curta", porta=0)


if __name__ == "__main__":
    unittest.main()
