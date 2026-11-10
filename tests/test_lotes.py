import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from observatorio.coleta import coletor, lotes
from observatorio.coleta.fontes import CGE, AUniao
from observatorio.nucleo import banco as B
from observatorio.nucleo.acervo import Acervo
from tests.apoio import FonteLocal, Servidor, pdf_sintetico

DIAS = [(m, d) for m in (1, 2) for d in range(2, 14)]  # 24 edições sintéticas em dois meses
NOMES_MES = {1: "janeiro", 2: "fevereiro"}


def rota_pdf(mes, dia):
    return f"/servicos/doe/2026/{NOMES_MES[mes]}/diario-oficial-{dia:02d}-{mes:02d}-2026-portal.pdf"


class Base(unittest.TestCase):
    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.banco, self.acervo = B.Banco(self.pasta / "b.sqlite3"), Acervo(self.pasta / "acervo")
        self.addCleanup(lambda: self.banco.fechar())
        self.auniao, self.cge = FonteLocal(AUniao(), self.s), FonteLocal(CGE(), self.s)
        for mes in (1, 2):
            html = "".join(f'<a href="{rota_pdf(m, d)}/view">x</a>' for m, d in DIAS if m == mes)
            self.s.rotas[f"/servicos/doe/2026/{NOMES_MES[mes]}"] = (200, "text/html", html.encode())
        for mes, dia in DIAS:
            self.s.rotas[rota_pdf(mes, dia)] = (200, "application/pdf", pdf_sintetico(f"{mes}-{dia}"))
        cge = "".join(f'<a href="/gati/Uploads/doe/2026/01-Janeiro/{d:02d}-Diario Oficial {d:02d}-01-2026 TOTAL.pdf">x</a>'
                      for m, d in DIAS if m == 1)
        self.s.rotas["/gati/sap/sap26.asp?a=2026&m=01"] = (200, "text/html", cge.encode())
        self.s.rotas["/gati/sap/sap26.asp?a=2026&m=02"] = (200, "text/html", b"<html></html>")
        for m, d in DIAS:
            if m == 1:  # na CGE, o mesmo conteúdo da A União
                self.s.rotas[f"/gati/Uploads/doe/2026/01-Janeiro/{d:02d}-Diario%20Oficial%20{d:02d}-01-2026%20TOTAL.pdf"] = (
                    200, "application/pdf", pdf_sintetico(f"1-{d}"))
        self.pausas = []
        for fonte in (self.auniao, self.cge):
            coletor.descobrir(fonte, self.banco, self.s.politica(servidores=frozenset(fonte.servidores)),
                              date(2026, 1, 1), date(2026, 2, 28))

    def lote(self, tipo, fonte=None, **extras):
        return lotes.executar_lote(fonte or self.auniao, self.banco, self.acervo, tipo, politica=self.s.politica(),
                                   dormir=self.pausas.append, **extras)

    def aprovar_pilotos(self):
        for fonte in (self.auniao, self.cge):
            self.assertTrue(self.lote(lotes.PILOTO, fonte)["aprovado"])


class TestePiloto(Base):
    def test_piloto_usa_cinco_datas_diferentes_espalhadas_e_pausa_entre_downloads(self):
        resumo = self.lote(lotes.PILOTO)
        self.assertEqual((resumo["estado"], resumo["aprovado"], resumo["resultados"]), ("CONCLUIDO", True, {"NOVO": 5}))
        itens = self.banco.itens_do_lote(resumo["lote"])
        datas = [self.banco.con.execute("SELECT data_publicacao FROM publicacao WHERE id = ?", (i["publicacao_id"],)).fetchone()[0]
                 for i in itens]
        self.assertEqual(len(set(datas)), 5)
        self.assertEqual((datas[0], datas[-1]), ("2026-01-02", "2026-02-13"))
        self.assertEqual(self.pausas, [10.0] * 4)
        self.assertTrue(all(i["sha256"] and i["tamanho"] and i["segundos"] is not None for i in itens))

    def test_piloto_com_falha_nao_e_aprovado_e_nao_libera_a_carga(self):
        self.s.rotas[rota_pdf(1, 2)] = (404, "text/plain", b"")
        self.s.rotas[rota_pdf(1, 2) + "/@@download/file"] = (404, "text/plain", b"")
        resumo = self.lote(lotes.PILOTO)
        self.assertFalse(resumo["aprovado"])
        self.assertEqual(resumo["resultados"], {"FALHA_DOWNLOAD": 1, "NOVO": 4})
        self.assertFalse(self.banco.piloto_aprovado("auniao"))

    def test_piloto_com_menos_de_tres_edicoes_nao_aprova(self):
        with self.banco.con:
            self.banco.con.execute("DELETE FROM publicacao WHERE fonte = 'auniao' AND data_publicacao > '2026-01-03'")
        resumo = self.lote(lotes.PILOTO)
        self.assertEqual((resumo["selecionados"], resumo["aprovado"]), (2, False))


class TesteTravaDaCargaHistorica(Base):
    def test_sem_piloto_o_lote_historico_e_recusado_sem_tocar_na_fonte(self):
        acessos = dict(self.s.acessos)
        resumo = self.lote(lotes.HISTORICO, fontes_exigidas=["auniao", "cge"])
        self.assertEqual(resumo, {"executado": False, "motivo": "PILOTO_NAO_APROVADO", "fontes_sem_piloto": ["auniao", "cge"]})
        self.assertEqual(self.s.acessos, acessos)
        self.assertEqual(self.banco.lotes(), [])

    def test_piloto_em_uma_so_fonte_nao_basta(self):
        self.lote(lotes.PILOTO)
        resumo = self.lote(lotes.HISTORICO, fontes_exigidas=["auniao", "cge"])
        self.assertEqual(resumo["fontes_sem_piloto"], ["cge"])


class TesteLotesHistoricos(Base):
    def setUp(self):
        super().setUp()
        self.aprovar_pilotos()
        self.pausas.clear()

    def test_lote_de_dez_em_ordem_cronologica_sem_misturar_meses(self):
        r1 = self.lote(lotes.HISTORICO)
        self.assertEqual((r1["mes"], r1["tentados"], r1["estado"]), ("2026-01", 10, "CONCLUIDO"))
        r2 = self.lote(lotes.HISTORICO)   # janeiro: 12 edições, 2 baixadas no piloto e 10 no primeiro lote
        self.assertEqual(r2["mes"], "2026-02")
        self.assertEqual(self.pausas[:9], [8.0] * 9)

    def test_carga_completa_nao_repete_downloads_e_termina_em_nada_pendente(self):
        resumos = lotes.executar_sequencia(self.auniao, self.banco, self.acervo, 10, 60, politica=self.s.politica(),
                                           dormir=self.pausas.append)
        self.assertEqual(resumos[-1], {"executado": False, "motivo": "NADA_PENDENTE"})
        self.assertIn(60, self.pausas)
        pdfs = {k: v for k, v in self.s.acessos.items() if k.startswith("/servicos") and k.endswith(".pdf")}
        self.assertEqual(len(pdfs), 24)
        self.assertEqual(set(pdfs.values()), {1})            # cada PDF foi pedido uma única vez
        self.assertEqual(len(self.banco.publicacoes("auniao", (B.BAIXADA,))), 24)
        self.assertTrue(all(self.acervo.conferir(a["sha256"]) for a in self.banco.arquivos()))

    def test_conteudo_ja_existente_e_contado_como_duplicado(self):
        lotes.executar_sequencia(self.auniao, self.banco, self.acervo, 10, 0, politica=self.s.politica(), dormir=self.pausas.append)
        resumo = self.lote(lotes.HISTORICO, self.cge)
        self.assertEqual(resumo["resultados"], {"DUPLICADO": 7})   # 5 das 12 já tinham vindo no piloto da CGE
        linha = [dict(l) for l in self.banco.progresso() if l["mes"] == "2026-01" and l["fonte"] == "cge"][0]
        self.assertEqual((linha["listadas"], linha["verificadas"], linha["duplicadas"]), (12, 12, 12))
        self.assertEqual(len(self.banco.arquivos()), 24)     # nenhum arquivo a mais por causa da segunda fonte

    def test_falhas_seguidas_encerram_o_lote_e_o_seguinte_retoma(self):
        guardadas = {}
        for dia in range(2, 14):
            for sufixo in ("", "/@@download/file"):
                guardadas[rota_pdf(2, dia) + sufixo] = self.s.rotas.get(rota_pdf(2, dia) + sufixo)
                self.s.rotas[rota_pdf(2, dia) + sufixo] = (503, "text/plain", b"")
        lotes.executar_sequencia(self.auniao, self.banco, self.acervo, 5, 0, politica=self.s.politica(), dormir=self.pausas.append)
        ultimo = self.banco.lotes("auniao")[-1]
        self.assertEqual(ultimo["estado"], "INTERROMPIDO_POR_FALHAS")
        self.assertEqual(len(self.banco.itens_do_lote(ultimo["id"])), 3)   # parou na terceira falha seguida
        self.assertIn("continuam pendentes", ultimo["observacao"])
        for rota, valor in guardadas.items():
            if valor is None:
                self.s.rotas.pop(rota, None)
            else:
                self.s.rotas[rota] = valor
        resumos = lotes.executar_sequencia(self.auniao, self.banco, self.acervo, 5, 0, politica=self.s.politica(), dormir=self.pausas.append)
        self.assertEqual(resumos[-1]["motivo"], "NADA_PENDENTE")
        self.assertEqual(len(self.banco.publicacoes("auniao", (B.BAIXADA,))), 24)

    def test_recusa_da_fonte_encerra_na_primeira_ocorrencia(self):
        for codigo, esperado in ((403, "INTERROMPIDO_RECUSA_DA_FONTE"), (429, "INTERROMPIDO_RECUSA_DA_FONTE")):
            pendente = self.banco.pendentes("auniao", 5)[0]
            rota = pendente["url"].replace(self.s.base, "")
            original = self.s.rotas[rota]
            self.s.rotas[rota] = (codigo, "text/plain", b"")
            self.s.rotas[rota + "/@@download/file"] = (codigo, "text/plain", b"")
            resumo = self.lote(lotes.HISTORICO)
            self.assertEqual((resumo["estado"], resumo["tentados"]), (esperado, 1))
            self.s.rotas[rota] = original

    def test_pagina_de_verificacao_no_lugar_do_pdf_encerra_sem_insistir(self):
        pendente = self.banco.pendentes("auniao", 5)[0]
        rota = pendente["url"].replace(self.s.base, "")
        desafio = (200, "text/html", b"<html><script src='/TSPD/x'></script>Please enable JavaScript</html>" + b" " * 2000)
        self.s.rotas[rota] = desafio
        self.s.rotas[rota + "/@@download/file"] = desafio
        resumo = self.lote(lotes.HISTORICO)
        self.assertEqual((resumo["estado"], resumo["tentados"]), ("INTERROMPIDO_PROTECAO_DA_FONTE", 1))
        self.assertEqual(self.s.acessos[rota], 1)

    def test_interrupcao_pelo_operador_preserva_o_que_ja_foi_feito(self):
        def interromper(_):
            if len(self.pausas) == 3:
                raise KeyboardInterrupt
            self.pausas.append(_)
        resumo = lotes.executar_lote(self.auniao, self.banco, self.acervo, lotes.HISTORICO, politica=self.s.politica(), dormir=interromper)
        self.assertEqual((resumo["estado"], resumo["tentados"]), ("INTERROMPIDO_PELO_OPERADOR", 4))
        self.assertEqual(sum(resumo["resultados"].values()), 4)
        self.assertLessEqual(set(resumo["resultados"]), lotes.SUCESSOS)
        antes = len(self.banco.publicacoes("auniao", (B.BAIXADA,)))
        proximo = self.lote(lotes.HISTORICO)
        self.assertEqual(len(self.banco.publicacoes("auniao", (B.BAIXADA,))), antes + proximo["tentados"])

    def test_queda_do_programa_no_meio_do_lote_e_retomada_do_banco_em_disco(self):
        class Queda(Exception):
            pass
        def cair(_):
            if len(self.pausas) == 2:
                raise Queda
            self.pausas.append(_)
        with self.assertRaises(Queda):
            lotes.executar_lote(self.auniao, self.banco, self.acervo, lotes.HISTORICO, politica=self.s.politica(), dormir=cair)
        self.banco.fechar()                                   # simula o encerramento do processo
        self.banco = B.Banco(self.pasta / "b.sqlite3")
        aberto = self.banco.lotes("auniao")[-1]
        self.assertIsNone(aberto["concluido_em"])
        self.assertEqual(len(self.banco.itens_do_lote(aberto["id"])), 3)   # itens gravados um a um
        acessos = dict(self.s.acessos)
        resumos = lotes.executar_sequencia(self.auniao, self.banco, self.acervo, 10, 0, politica=self.s.politica(), dormir=lambda _: None)
        self.assertEqual(self.banco.lote(aberto["id"])["estado"], "INTERROMPIDO_EXECUCAO")
        self.assertEqual(resumos[-1]["motivo"], "NADA_PENDENTE")
        self.assertEqual(len(self.banco.publicacoes("auniao", (B.BAIXADA,))), 24)
        ja_baixados = [k for k, v in acessos.items() if k.endswith(".pdf") and k.startswith("/servicos")]
        self.assertTrue(all(self.s.acessos[k] == acessos[k] for k in ja_baixados))   # nada foi baixado de novo

    def test_robots_restritivo_impede_o_lote(self):
        self.s.rotas["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /\n")
        self.assertEqual(self.lote(lotes.HISTORICO), {"executado": False, "motivo": "ROBOTS_RESTRINGE_A_COLETA"})


class TesteDescobertaRetomavel(Base):
    def test_meses_ja_varridos_sao_pulados_exceto_os_dois_ultimos(self):
        politica = self.s.politica()
        r = coletor.descobrir(self.auniao, self.banco, politica, date(2026, 1, 1), date(2026, 4, 30))
        self.assertEqual(["erro" in x for x in r], [False, False, True, True])   # março e abril não existem no servidor
        acessos = dict(self.s.acessos)
        r = coletor.descobrir(self.auniao, self.banco, politica, date(2026, 1, 1), date(2026, 4, 30))
        self.assertEqual([x.get("pulado") for x in r[:2]], ["já varrido", "já varrido"])
        self.assertEqual(self.s.acessos["/servicos/doe/2026/janeiro"], acessos["/servicos/doe/2026/janeiro"])
        self.assertGreater(self.s.acessos["/servicos/doe/2026/abril"], acessos["/servicos/doe/2026/abril"])


class TesteMigracaoDoBanco(unittest.TestCase):
    def test_banco_da_versao_1_e_atualizado_sem_perder_dados(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "v1.sqlite3"
            con = sqlite3.connect(caminho)
            con.executescript(B._ESQUEMA)
            con.execute("PRAGMA user_version = 1")
            con.execute("INSERT INTO publicacao (fonte, url, tipo, estado, descoberta_em, atualizada_em) "
                        "VALUES ('auniao', 'u', 'normal', 'DESCOBERTA', 'x', 'x')")
            con.commit()
            con.close()
            banco = B.Banco(caminho)
            self.assertEqual(len(banco.publicacoes()), 1)
            self.assertEqual(banco.lotes(), [])
            self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
            banco.fechar()


if __name__ == "__main__":
    unittest.main()
