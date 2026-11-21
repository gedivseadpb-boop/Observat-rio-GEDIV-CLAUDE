"""Etapa 05.3.2 — integridade da coleta, cobertura e retomada (auditorias Codex, Gemini/Antigravity e GPT Work).

Tudo contra o servidor HTTP local, com listagens e PDFs SINTÉTICOS: nenhum acesso à internet, nenhum dado pessoal.
A data da varredura é ajustada no banco para simular "quando" a fonte foi lida, sem depender do relógio.
"""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from observatorio.coleta import coletor, inventario, lotes
from observatorio.coleta import fontes as F
from observatorio.coleta.fontes import CGE
from observatorio.nucleo import banco as B
from observatorio.nucleo import pdf, rede
from observatorio.nucleo.acervo import ErroAcervo
from tests import test_aquisicao as TA
from tests.apoio import FonteLocal, pdf_sem_paginas, pdf_sintetico

NOV = TA.NOV
D = lambda dia, mes=11: date(2026, mes, dia)


def artigo(caminho: str) -> str:
    return f'<article class="entry"><a href="{caminho}/view" class="summary url">{caminho.rsplit("/", 1)[-1]}</a></article>'


class Base(TA.Base):
    def listagem(self, *extras: str, rota: str = NOV) -> None:
        """Listagem mensal = fixture real + artigos extras (suplementos, edições sem data...)."""
        html = TA.FIXTURE.read_text(encoding="utf-8").replace("https://auniao.pb.gov.br", "")
        self.s.rotas[rota] = (200, "text/html", (html + "".join(artigo(e) for e in extras)).encode())

    def lida_em(self, quando: date, fonte: str = "auniao") -> None:
        """Simula a data da última varredura (os testes rodam em qualquer data real)."""
        with self.banco.con:
            self.banco.con.execute("UPDATE varredura SET realizada_em = ? WHERE fonte = ?", (f"{quando.isoformat()}T12:00:00+00:00", fonte))

    def dias(self, inicio, fim, fontes=("auniao",)):
        return {l["data"]: l for l in inventario.cobertura(self.banco, inicio, fim, list(fontes), self.acervo)}

    def pub(self, dia, mes=11, sufixo=""):
        return self.banco.publicacao("auniao", self.s.base + TA.rota_pdf(dia, NOV if mes == 11 else TA.OUT, sufixo))


# --------------------------------------------------------------------------------------------- Correção 1
class TesteCoberturaExigeEvidencia(Base):
    def test_mes_corrente_varrido_em_parte_nao_certifica_dias_posteriores_nem_recentes(self):
        self.coletar(D(4), D(7))
        self.lida_em(D(8))                                 # a listagem de novembro foi lida em 08/11
        d = self.dias(D(4), D(9))
        self.assertEqual((d["2026-11-04"]["situacao"], d["2026-11-05"]["situacao"]), ("COMPLETO", "COMPLETO"))
        # 06 e 07: ainda dentro da janela de suplementos quando a listagem foi lida.
        self.assertEqual((d["2026-11-07"]["situacao"], d["2026-11-07"]["motivo"]),
                         ("BAIXADO_SEM_VARREDURA_COMPLETA", "AGUARDANDO_JANELA_DE_SUPLEMENTOS"))
        # 08 (dia da leitura) e 09 (depois dela): sem edição listada, mas nada certifica — NÃO é "sem publicação".
        for dia in ("2026-11-08", "2026-11-09"):
            self.assertEqual((d[dia]["situacao"], d[dia]["motivo"]), ("NAO_VERIFICADO", "VARREDURA_ANTERIOR_AO_DIA"))

    def test_dia_futuro_nunca_e_verificado(self):
        self.coletar(D(4), D(7))
        futuro = date.today() + timedelta(days=10)
        linha = inventario.cobertura(self.banco, futuro, futuro, ["auniao"], self.acervo)[0]
        self.assertEqual(linha["situacao"], "NAO_VERIFICADO")

    def test_dia_sem_publicacao_comprovado_e_nao_verificado(self):
        self.coletar(D(1), D(14))
        self.lida_em(D(30))
        self.assertEqual(self.dias(D(8), D(8))["2026-11-08"]["situacao"], "SEM_PUBLICACAO_LISTADA")
        outubro = self.dias(D(30, 10), D(30, 10))["2026-10-30"]                     # outubro não foi varrido
        self.assertEqual((outubro["situacao"], outubro["motivo"]), ("NAO_VERIFICADO", "NUNCA_LIDA"))

    def test_mes_historico_integralmente_varrido(self):
        self.coletar(D(28, 10), D(31, 10))
        self.lida_em(D(14))
        d = self.dias(D(28, 10), D(31, 10))
        self.assertEqual([d[x]["situacao"] for x in sorted(d)], ["COMPLETO", "COMPLETO", "SEM_PUBLICACAO_LISTADA", "COMPLETO"])

    def test_suplemento_publicado_tarde_impede_completo_ate_ser_baixado(self):
        self.coletar(D(10), D(12))
        self.lida_em(D(16))
        self.assertEqual(self.dias(D(12), D(12))["2026-11-12"]["situacao"], "COMPLETO")
        # Um suplemento de 12/11 aparece depois: a nova leitura o lista e o dia deixa de estar completo.
        supl = NOV + "/diario-oficial-12-11-2026-suplemento.pdf"
        self.listagem(supl)
        self.s.rotas[supl] = (500, "text/plain", b"")
        self.coletar(D(10), D(12))
        self.lida_em(D(20))
        dia = self.dias(D(12), D(12))["2026-11-12"]
        self.assertEqual((dia["situacao"], dia["listadas"], dia["suplementos_ou_extras"]), ("PARCIAL", 2, 2))
        self.publicar(supl, "supl-12")
        self.coletar(D(10), D(12))
        self.lida_em(D(20))
        self.assertEqual(self.dias(D(12), D(12))["2026-11-12"]["situacao"], "COMPLETO")

    def test_principal_presente_e_suplemento_ausente(self):
        supl = NOV + "/diario-oficial-07-11-2026-suplemento.pdf"
        self.listagem(supl)
        self.s.rotas[supl] = (404, "text/plain", b"")
        self.coletar(D(7), D(7))
        self.lida_em(D(14))
        dia = self.dias(D(7), D(7))["2026-11-07"]
        self.assertEqual((dia["situacao"], dia["listadas"], dia["baixadas"]), ("PARCIAL", 2, 1))

    def test_uma_fonte_verificada_e_outra_nao(self):
        self.coletar(D(4), D(7))
        self.lida_em(D(14))
        d = self.dias(D(4), D(8), ("auniao", "cge"))
        self.assertEqual((d["2026-11-04"]["situacao"], d["2026-11-04"]["fontes_verificadas"], d["2026-11-04"]["fontes_sem_evidencia"]),
                         ("BAIXADO_SEM_VARREDURA_COMPLETA", ["auniao"], {"cge": "NUNCA_LIDA"}))
        self.assertEqual(d["2026-11-08"]["situacao"], "NAO_VERIFICADO")
        so_auniao = inventario.manifesto(self.banco, D(4), D(8), ["auniao"], self.acervo)["escopo"]
        self.assertEqual((so_auniao["todas_as_fontes"], so_auniao["fontes_nao_consideradas"]), (False, ["cge"]))
        self.assertTrue(so_auniao["aviso"])
        self.assertTrue(inventario.manifesto(self.banco, D(4), D(8), ["auniao", "cge"], self.acervo)["escopo"]["todas_as_fontes"])

    def test_completo_exige_arquivo_presente_integro_e_verificado(self):
        self.coletar(D(4), D(7))
        self.lida_em(D(14))
        pub = self.pub(7)
        self.acervo.caminho(pub["sha256"]).unlink()                     # arquivo sumiu do acervo
        dia = self.dias(D(7), D(7))["2026-11-07"]
        self.assertEqual((dia["situacao"], dia["motivo"]), ("INTEGRIDADE_NAO_CONFIRMADA", "ARQUIVO_AUSENTE_NO_ACERVO"))
        pub5 = self.pub(5)
        with self.banco.con:
            self.banco.con.execute("DELETE FROM verificacao_arquivo WHERE sha256 = ?", (pub5["sha256"],))
        dia = self.dias(D(5), D(5))["2026-11-05"]
        self.assertEqual((dia["situacao"], dia["motivo"]), ("INTEGRIDADE_NAO_CONFIRMADA", "SEM_VERIFICACAO_ESTRUTURAL"))

    def test_varredura_interrompida_nao_certifica_nada(self):
        original = rede.obter

        def queda(url, politica, *a, **k):
            if url.endswith(NOV):
                raise KeyboardInterrupt
            return original(url, politica, *a, **k)
        with mock.patch.object(coletor.rede, "obter", queda), self.assertRaises(KeyboardInterrupt):
            self.coletar(D(4), D(7))
        d = self.dias(D(4), D(8))
        self.assertEqual((d["2026-11-08"]["situacao"], d["2026-11-08"]["motivo"]), ("NAO_VERIFICADO", "NUNCA_LIDA"))
        self.assertNotIn("COMPLETO", {l["situacao"] for l in d.values()})
        self.coletar(D(4), D(7))                                        # retomada normal
        self.lida_em(D(14))
        self.assertEqual(self.dias(D(4), D(4))["2026-11-04"]["situacao"], "COMPLETO")

    def test_paginacao_incompleta(self):
        html = TA.FIXTURE.read_text(encoding="utf-8").replace("https://auniao.pb.gov.br", "")
        segunda = NOV + "?b_start:int=12"
        self.s.rotas[NOV] = (200, "text/html", (html + f'<a href="{segunda}">2</a>').encode())
        self.s.rotas[segunda] = (503, "text/html", b"<p>Service Unavailable</p>")
        resumo = self.coletar(D(4), D(7))
        self.assertTrue(resumo["fontes"]["auniao"]["varreduras"][0]["erro"].startswith("HTTP_503"))
        dia = self.dias(D(8), D(8))["2026-11-08"]
        self.assertEqual((dia["situacao"], dia["motivo"]), ("NAO_VERIFICADO", "FONTE_INDISPONIVEL"))
        self.s.rotas[segunda] = (200, "text/html", b"<html><body><p>Nada aqui</p></body></html>")
        self.coletar(D(4), D(7))                                        # 2ª página sem itens e sem aviso de pasta vazia
        dia = self.dias(D(8), D(8))["2026-11-08"]
        self.assertEqual((dia["situacao"], dia["motivo"]), ("NAO_VERIFICADO", "LISTAGEM_INVALIDA"))

    def test_comando_cobertura_sai_com_pendencias_quando_ha_lacunas(self):
        from observatorio.operacao.__main__ import main
        self.coletar(D(4), D(7))
        self.lida_em(D(8))                                              # 08 e 09 sem evidência; 06–07 na janela
        with mock.patch("observatorio.operacao.aquisicao.abrir", lambda dados: (self.banco, self.acervo)), \
                mock.patch.object(self.banco, "fechar", lambda: None), contextlib.redirect_stdout(io.StringIO()) as saida:
            codigo = main(["cobertura", "--inicio", "2026-11-04", "--fim", "2026-11-09"])
        self.assertEqual(codigo, 3)
        self.assertFalse(json.loads(saida.getvalue())["escopo"]["todas_as_fontes"])


# --------------------------------------------------------------------------------------------- Correção 2
class TesteListagensInesperadas(Base):
    CASOS = {
        "MANUTENCAO": "<html><body><h1>Site em manutenção</h1><p>Voltamos em breve.</p></body></html>",
        "BLOQUEIO": "<html><head><title>Just a moment...</title><script>window._cf_chl_opt={}</script></head></html>",
        "ERRO_NA_PAGINA": "<html><body><h1>Ocorreu um erro</h1><p>Tente novamente.</p></body></html>",
        "FORMATO_DESCONHECIDO": "<html><body><div class='novo-layout'>Diário Oficial</div></body></html>",
    }

    def test_resposta_200_que_nao_e_listagem_nunca_vira_mes_vazio(self):
        for estado, html in self.CASOS.items():
            with self.subTest(estado=estado):
                self.setUp()
                self.s.rotas[NOV] = (200, "text/html", html.encode())
                self.s.rotas["/doe/edicoes-recentes"] = (200, "text/html", b"<html><body>sem itens</body></html>")
                resumo = self.coletar(D(4), D(7))
                varredura = [v for v in self.banco.varreduras() if (v["ano"], v["mes"]) == (2026, 11)][0]
                self.assertEqual(varredura["erro"].split(":")[0], "LISTAGEM_INVALIDA")
                self.assertIn(estado, varredura["erro"])
                dia = self.dias(D(8), D(8))["2026-11-08"]
                self.assertEqual((dia["situacao"], dia["motivo"]), ("NAO_VERIFICADO", "LISTAGEM_INVALIDA"))
                self.assertTrue(coletor.houve_pendencia(resumo))

    def test_bloqueio_na_listagem_suspende_a_fonte(self):
        self.s.rotas[NOV] = (200, "text/html", self.CASOS["BLOQUEIO"].encode())
        resumo = self.coletar(D(4), D(7))
        self.assertTrue(resumo["fontes"]["auniao"]["suspensa"].startswith("BLOQUEIO_RECONHECIDO"))
        self.assertEqual(sum(n for c, n in self.s.acessos.items() if c.endswith(".pdf")), 0)   # nenhum download depois

    def test_mes_legitimamente_vazio(self):
        self.s.rotas[NOV] = (200, "text/html", b"<html><body><p>N\xc3\xa3o h\xc3\xa1 itens nesta pasta.</p></body></html>")
        self.coletar(D(4), D(7), usar_recentes=False)
        self.lida_em(D(14))
        self.assertEqual(self.dias(D(8), D(8))["2026-11-08"]["situacao"], "SEM_PUBLICACAO_LISTADA")

    def test_edicao_sem_data_fica_rastreavel_e_impede_certificar_o_mes(self):
        sem_data = NOV + "/diario-oficial-edicao-especial.pdf"
        self.listagem(sem_data)
        resumo = self.coletar(D(4), D(7))
        self.assertTrue(resumo["fontes"]["auniao"]["varreduras"][0]["erro"].startswith("DATA_NAO_IDENTIFICADA"))
        registrada = self.banco.publicacao("auniao", self.s.base + sem_data)
        self.assertIsNotNone(registrada)
        self.assertIsNone(registrada["data_publicacao"])                    # nenhuma data inventada
        self.lida_em(D(14))
        d = self.dias(D(4), D(8))
        self.assertEqual((d["2026-11-08"]["situacao"], d["2026-11-08"]["motivo"]), ("NAO_VERIFICADO", "DATA_NAO_IDENTIFICADA"))
        self.assertEqual(d["2026-11-04"]["situacao"], "BAIXADO_SEM_VARREDURA_COMPLETA")
        m = inventario.manifesto(self.banco, D(4), D(8), ["auniao"], self.acervo)
        self.assertEqual([e["url_oficial"] for e in m["sem_data_identificada"]], [self.s.base + sem_data])

    def test_fonte_temporariamente_indisponivel(self):
        self.s.rotas[NOV] = (503, "text/html", b"")
        self.coletar(D(4), D(7))
        dia = self.dias(D(8), D(8))["2026-11-08"]
        self.assertEqual((dia["situacao"], dia["motivo"]), ("NAO_VERIFICADO", "FONTE_INDISPONIVEL"))

    def test_classificador(self):
        item = F.Item("auniao", "u", D(7), "normal", 0, "x")
        self.assertEqual(F.classificar_listagem("<html>qualquer</html>", [item]), F.VALIDA)
        self.assertEqual(F.classificar_listagem("<p>There are currently no items in this folder.</p>", []), F.VAZIA_COMPROVADA)
        self.assertEqual(F.classificar_listagem("<p>Error 502</p>", []), F.ERRO_NA_PAGINA)


# --------------------------------------------------------------------------------------------- Correção 3
class TesteIntegridadeDoPdf(Base):
    def importar(self, dados, dia=7, url="manual:x"):
        return coletor.importar_manual(self.banco, self.acervo, dados, D(dia), url, "x.pdf")

    def test_resposta_206_parcial_nao_e_download_integral(self):
        dados = self.pdfs[TA.rota_pdf(7)]
        self.s.rotas[TA.rota_pdf(7)] = (206, "application/pdf", dados[:1500],
                                        {"cabecalhos": {"Content-Range": f"bytes 0-1499/{len(dados)}"}})
        self.s.rotas[TA.rota_pdf(7) + "/@@download/file"] = (404, "text/plain", b"")
        self.coletar(D(7), D(7))
        pub = self.pub(7)
        self.assertNotEqual(pub["estado"], B.BAIXADA)
        self.assertIn("RESPOSTA_PARCIAL", self.banco.downloads(pub["id"])[0]["erro"])
        self.assertEqual(self.arquivos_no_acervo(), [])

    def test_206_que_cobre_o_arquivo_inteiro_e_aceito(self):
        dados = self.pdfs[TA.rota_pdf(7)]
        self.s.rotas[TA.rota_pdf(7)] = (206, "application/pdf", dados,
                                        {"cabecalhos": {"Content-Range": f"bytes 0-{len(dados) - 1}/{len(dados)}"}})
        self.coletar(D(7), D(7))
        self.assertEqual(self.pub(7)["estado"], B.BAIXADA)

    def test_importacao_manual_aplica_a_mesma_verificacao_da_coleta(self):
        bom = pdf_sintetico("manual-bom", paginas=2)
        for nome, dados, quarentena in (("sem páginas", pdf_sem_paginas("m"), True), ("truncado", bom[: len(bom) // 2], False),
                                        ("html", b"<!doctype html><html>erro</html>", False)):
            with self.subTest(nome):
                r = self.importar(dados, url=f"manual:{nome}")
                self.assertEqual((r["aceito"], r["quarentena"]), (False, quarentena))
                self.assertEqual(pdf.verificar(dados, len(dados)).valido, False)       # a coleta também recusa
        self.assertEqual(self.banco.arquivos(), [])
        r = self.importar(bom)
        self.assertEqual((r["aceito"], r["resultado"], r["paginas"]), (True, "NOVO", 2))
        pub = self.banco.publicacao("manual", "manual:x")
        self.assertEqual(self.banco.verificacao(pub["sha256"])["integridade"], "ESTRUTURA_VERIFICADA")
        self.assertEqual(self.banco.downloads(pub["id"])[-1]["transporte"], "importacao_manual")
        self.assertEqual(self.importar(bom)["resultado"], "IGUAL")                     # reimportação

    def test_content_length_divergente(self):
        dados = self.pdfs[TA.rota_pdf(7)]
        self.s.rotas[TA.rota_pdf(7)] = (200, "application/pdf", dados, {"anunciar": len(dados) + 50, "cortar": len(dados)})
        self.s.rotas[TA.rota_pdf(7) + "/@@download/file"] = (404, "text/plain", b"")
        self.coletar(D(7), D(7))
        self.assertNotEqual(self.pub(7)["estado"], B.BAIXADA)

    def test_assinatura_valida_e_estrutura_invalida(self):
        self.s.rotas[TA.rota_pdf(7)] = (200, "application/pdf", pdf_sem_paginas("x"))
        self.coletar(D(7), D(7))
        self.assertEqual(self.pub(7)["estado"], B.QUARENTENA)
        self.assertEqual(self.arquivos_no_acervo(), [])

    def test_mesmo_endereco_com_pdf_diferente_preserva_versoes(self):
        self.coletar(D(7), D(7))
        self.publicar(TA.rota_pdf(7), "republicado")
        self.coletar(D(7), D(7), reverificar=True)
        pub = self.pub(7)
        self.assertEqual(len(self.banco.versoes(pub["id"])), 2)
        m = inventario.manifesto(self.banco, D(7), D(7), ["auniao"], self.acervo)
        self.assertEqual(m["edicoes"][0]["relacao"], "SUBSTITUIDO_NO_MESMO_ENDERECO")

    def test_falha_ao_gravar_no_acervo_e_registrada_e_a_coleta_continua(self):
        original = self.acervo.guardar

        def guardar(dados):
            if dados == self.pdfs[TA.rota_pdf(5)]:
                raise ErroAcervo("arquivo existente corrompido")
            return original(dados)
        with mock.patch.object(self.acervo, "guardar", guardar):
            resumo = self.coletar(D(4), D(7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"].get(B.FALHA_DOWNLOAD), 1)
        self.assertEqual(self.pub(5)["estado"], B.FALHA_DOWNLOAD)
        self.assertIn("FALHA_ACERVO", self.pub(5)["ultimo_erro"])
        self.assertEqual(self.pub(7)["estado"], B.BAIXADA)                              # as outras seguiram

    def test_reverificacao_malsucedida_nao_substitui_a_versao_valida(self):
        self.coletar(D(7), D(7))
        valido = self.pub(7)["sha256"]
        self.s.rotas[TA.rota_pdf(7)] = (200, "application/pdf", b"%PDF-1.4 truncado")
        self.s.rotas[TA.rota_pdf(7) + "/@@download/file"] = (404, "text/plain", b"")
        self.coletar(D(7), D(7), reverificar=True)
        pub = self.pub(7)
        self.assertEqual((pub["estado"], pub["sha256"]), (B.BAIXADA, valido))
        self.assertTrue(pub["ultimo_erro"])
        self.assertTrue(self.acervo.conferir(valido))


# --------------------------------------------------------------------------------------------- Correção 4
class TesteInterrupcoesEntreGravacoes(Base):
    def coletar_com_queda(self, alvo, objeto, nome):
        original = getattr(objeto, nome)

        def com_queda(*a, **k):
            raise KeyboardInterrupt(f"queda simulada em {alvo}")
        with mock.patch.object(objeto, nome, com_queda), self.assertRaises(KeyboardInterrupt):
            self.coletar(D(7), D(7))
        return original

    def depois_da_retomada(self, downloads_integros=1):
        self.coletar(D(7), D(7))
        pub = self.pub(7)
        self.assertEqual(pub["estado"], B.BAIXADA)
        self.assertEqual(self.banco.verificacao(pub["sha256"])["integridade"], "ESTRUTURA_VERIFICADA")
        self.assertTrue(self.acervo.conferir(pub["sha256"]))
        self.assertEqual(len([d for d in self.banco.downloads(pub["id"]) if d["resultado"] in ("NOVO", "IGUAL")]),
                         downloads_integros)

    def test_queda_durante_o_download_e_apos_receber_os_bytes(self):
        for alvo, objeto, nome in (("download", coletor.Direto, "obter"), ("verificação", coletor.pdf, "verificar")):
            with self.subTest(alvo):
                self.setUp()
                self.coletar_com_queda(alvo, objeto, nome)
                self.assertEqual(self.pub(7)["estado"], B.DESCOBERTA)                 # pendente, nunca "baixada"
                self.depois_da_retomada()

    def test_queda_apos_salvar_o_arquivo_e_antes_de_registrar(self):
        self.coletar_com_queda("registro", B.Banco, "registrar_obtencao")
        self.assertEqual(self.pub(7)["estado"], B.DESCOBERTA)
        self.assertEqual(len(self.arquivos_no_acervo()), 1)                             # arquivo órfão, não apagado
        self.assertEqual(coletor.reconciliar(self.banco, self.acervo)["arquivos_sem_registro"], 1)
        self.depois_da_retomada()
        self.assertEqual(self.banco.downloads(self.pub(7)["id"])[-1]["resultado"], "NOVO")   # não "DUPLICADO"

    def test_queda_antes_de_confirmar_a_transacao_desfaz_tudo(self):
        with self.banco.con:
            self.banco.con.execute("CREATE TRIGGER queda BEFORE INSERT ON download WHEN NEW.resultado IN ('NOVO','IGUAL','ALTERADO','DUPLICADO') "
                                   "BEGIN SELECT RAISE(ABORT, 'queda simulada antes do COMMIT'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.coletar(D(7), D(7))
        pub = self.pub(7)
        self.assertEqual((pub["estado"], pub["sha256"]), (B.DESCOBERTA, None))             # nada pela metade
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM verificacao_arquivo").fetchone()[0], 0)
        self.assertEqual(self.banco.versoes(pub["id"]), [])
        with self.banco.con:
            self.banco.con.execute("DROP TRIGGER queda")
        self.depois_da_retomada()

    def test_queda_depois_da_confirmacao_e_antes_de_encerrar(self):
        with mock.patch.object(self.banco, "concluir_execucao", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.coletar(D(7), D(7))
        pub = self.pub(7)
        self.assertEqual(pub["estado"], B.BAIXADA)
        self.assertIsNotNone(self.banco.verificacao(pub["sha256"]))
        acessos = dict(self.s.acessos)
        self.coletar(D(7), D(7))
        self.assertEqual(self.s.acessos.get(TA.rota_pdf(7)), acessos.get(TA.rota_pdf(7)))     # não baixa de novo

    def test_registro_no_banco_com_arquivo_ausente_volta_a_fila(self):
        self.coletar(D(7), D(7))
        self.acervo.caminho(self.pub(7)["sha256"]).unlink()
        r = coletor.reconciliar(self.banco, self.acervo)
        self.assertEqual(r["reobter"], 1)
        pub = self.pub(7)
        self.assertEqual(pub["estado"], B.FALHA_DOWNLOAD)
        self.assertIn("ARQUIVO_AUSENTE_NO_ACERVO", pub["ultimo_erro"])
        self.assertTrue(self.banco.trilha("publicacao", str(pub["id"])))              # visível e auditado
        self.depois_da_retomada(downloads_integros=2)                                  # o original (NOVO) e o refeito (IGUAL)

    def test_arquivo_no_acervo_com_registro_incompleto(self):
        self.coletar(D(7), D(7))
        sha = self.pub(7)["sha256"]
        with self.banco.con:                                                            # como o código antigo deixava
            self.banco.con.execute("DELETE FROM verificacao_arquivo")
        self.assertEqual(coletor.reconciliar(self.banco, self.acervo)["verificados_agora"], 1)
        self.assertEqual(self.banco.verificacao(sha)["integridade"], "ESTRUTURA_VERIFICADA")
        # Bytes alterados no disco (mesmo tamanho): a verificação reprova e a publicação volta à fila.
        caminho = self.acervo.caminho(sha)
        dados = bytearray(caminho.read_bytes())
        dados[200:260] = b"\x00" * 60
        caminho.write_bytes(bytes(dados))
        with self.banco.con:
            self.banco.con.execute("DELETE FROM verificacao_arquivo")
        self.assertEqual(coletor.reconciliar(self.banco, self.acervo)["reobter"], 1)
        self.assertEqual(self.pub(7)["estado"], B.FALHA_DOWNLOAD)

    def test_arquivos_temporarios_de_gravacao_interrompida_sao_removidos(self):
        parcial = Path(self.acervo.raiz) / "ab" / "tmpqueda.parcial"
        parcial.parent.mkdir(parents=True, exist_ok=True)
        parcial.write_bytes(b"%PDF-1.4 metade")
        self.assertEqual(coletor.reconciliar(self.banco, self.acervo)["parciais_removidos"], 1)
        self.assertFalse(parcial.exists())


# --------------------------------------------------------------------------------------------- Correção 5
class TesteTentativasEsgotadas(Base):
    def falhar(self, vezes):
        self.s.rotas[TA.rota_pdf(7)] = (500, "text/plain", b"")
        self.s.rotas[TA.rota_pdf(7) + "/@@download/file"] = (500, "text/plain", b"")
        for _ in range(vezes):
            self.coletar(D(7), D(7))

    def test_cinco_falhas_esgotam_sem_sumir_da_cobertura(self):
        self.falhar(5)
        pub = self.pub(7)
        self.assertEqual((pub["estado"], pub["tentativas"]), (B.FALHA_DOWNLOAD, 5))
        acessos = dict(self.s.acessos)
        resumo = self.coletar(D(7), D(7), reverificar=True)                            # nem reverificar insiste
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"ESGOTADA": 1})
        self.assertEqual(self.s.acessos.get(TA.rota_pdf(7)), acessos.get(TA.rota_pdf(7)))
        self.lida_em(D(14))
        dia = self.dias(D(7), D(7))["2026-11-07"]
        self.assertEqual((dia["situacao"], dia["motivo"], dia["esgotadas"]), ("PENDENTE", "TENTATIVAS_ESGOTADAS", 1))
        e = inventario.manifesto(self.banco, D(7), D(7), ["auniao"], self.acervo)["edicoes"][0]
        self.assertTrue(e["esgotada"])
        self.assertTrue(e["ultima_tentativa_em"] and e["ultimo_erro"])

    def test_reabertura_autorizada_e_auditada_retoma_o_download(self):
        self.falhar(5)
        with self.assertRaises(ValueError):
            coletor.reabrir_esgotadas(self.banco, "auniao", D(1), D(14), "", "sem responsável")
        r = coletor.reabrir_esgotadas(self.banco, "auniao", D(1), D(14), "operadora de teste", "fonte voltou a responder")
        self.assertEqual((r["esgotadas"], r["reabertas"]), (1, 1))
        self.assertEqual(self.banco.trilha("publicacao", str(self.pub(7)["id"]))[0]["acao"], "REABRIR_TENTATIVAS")
        self.publicar(TA.rota_pdf(7), "nov-7")
        self.s.rotas.pop(TA.rota_pdf(7) + "/@@download/file", None)
        self.coletar(D(7), D(7))
        self.assertEqual(self.pub(7)["estado"], B.BAIXADA)

    def test_falha_apos_reabertura_volta_a_contar(self):
        self.falhar(5)
        coletor.reabrir_esgotadas(self.banco, "auniao", D(1), D(14), "operadora de teste", "nova tentativa autorizada")
        self.falhar(1)
        self.assertEqual(self.pub(7)["tentativas"], 1)
        self.assertEqual(self.banco.esgotadas("auniao"), [])

    def test_item_ja_concluido_nao_e_baixado_de_novo(self):
        self.coletar(D(4), D(7))
        acessos = dict(self.s.acessos)
        self.coletar(D(4), D(7))
        self.assertEqual({k: v for k, v in self.s.acessos.items() if k.endswith(".pdf")},
                         {k: v for k, v in acessos.items() if k.endswith(".pdf")})

    def test_comando_reabrir_exige_responsavel_e_justificativa(self):
        from observatorio.operacao.__main__ import main
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["reabrir", "--fonte", "auniao", "--inicio", "2026-11-01", "--fim", "2026-11-14"])


# --------------------------------------------------------------------------------------------- Correção 6
class TesteRecusaDaFonte(Base):
    def pdfs_pedidos(self):
        return sum(n for c, n in self.s.acessos.items() if ".pdf" in c)

    def test_429_na_primeira_requisicao_nenhuma_outra_e_enviada(self):
        self.s.rotas["/doe/edicoes-recentes"] = (429, "text/plain", b"", {"cabecalhos": {"Retry-After": "7200"}})
        resumo = self.coletar(D(4), D(7))
        self.assertEqual((self.s.acessos.get(NOV, 0), self.pdfs_pedidos()), (0, 0))
        self.assertIn("HTTP_429", resumo["fontes"]["auniao"]["suspensa"])
        vigente = self.banco.suspensao_vigente("auniao")
        ate = datetime.fromisoformat(vigente["ate"])
        self.assertGreater(ate - datetime.now(timezone.utc), timedelta(seconds=7000))     # Retry-After respeitado
        antes = sum(self.s.acessos.values())
        self.coletar(D(4), D(7))                                                        # execução seguinte
        self.assertEqual(sum(self.s.acessos.values()), antes)                          # nenhuma requisição

    def test_403_no_primeiro_download_interrompe_os_seguintes(self):
        self.s.rotas[TA.rota_pdf(4)] = (403, "text/plain", b"negado")
        resumo = self.coletar(D(4), D(7))
        self.assertEqual(self.pdfs_pedidos(), 1)
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"].get("SUSPENSA"), 3)
        self.assertEqual(self.pub(5)["tentativas"], 0)                                 # não conta como falha da edição

    def test_robots_proibe_ou_recusa(self):
        for nome, rota in (("proíbe", (200, "text/plain", b"User-agent: *\nDisallow: /\n")), ("recusa", (403, "text/plain", b""))):
            with self.subTest(nome):
                self.setUp()
                self.s.rotas["/robots.txt"] = rota
                resumo = self.coletar(D(4), D(7))
                self.assertTrue(resumo["fontes"]["auniao"]["suspensa"])
                self.assertEqual(set(self.s.acessos), {"/robots.txt"})

    def test_fonte_recusada_nao_afeta_fonte_independente(self):
        cge = FonteLocal(CGE(), self.s)
        self.s.rotas["/gati/sap/sap26.asp?a=2026&m=11"] = (200, "text/html", "<p>Não há itens nesta pasta.</p>".encode())
        self.s.rotas["/doe/edicoes-recentes"] = (429, "text/plain", b"")
        resumo = coletor.coletar_intervalo([self.fonte, cge], self.banco, self.acervo, D(4), D(7), politica=self.s.politica(),
                                           hoje=self.hoje)
        self.assertTrue(resumo["fontes"]["auniao"]["suspensa"])
        self.assertIsNone(resumo["fontes"]["cge"]["suspensa"])
        self.assertEqual(self.s.acessos.get("/gati/sap/sap26.asp?a=2026&m=11"), 1)

    def test_retomada_apos_liberacao_ou_prazo(self):
        self.s.rotas["/doe/edicoes-recentes"] = (429, "text/plain", b"")
        self.coletar(D(4), D(7))
        self.s.rotas["/doe/edicoes-recentes"] = (200, "text/html", self.s.rotas[NOV][2])
        with self.assertRaises(ValueError):
            self.banco.liberar_fonte("auniao", "operadora", "")
        self.assertTrue(self.banco.liberar_fonte("auniao", "operadora de teste", "limite da fonte normalizado"))
        self.assertEqual(self.coletar(D(4), D(7))["fontes"]["auniao"]["downloads"].get("NOVO"), 4)
        # Prazo vencido também encerra a suspensão.
        self.banco.suspender_fonte("auniao", "HTTP_429", "teste", "2000-01-01T00:00:00+00:00")
        self.assertIsNone(self.banco.suspensao_vigente("auniao"))

    def test_mesma_politica_no_lote_na_descoberta_e_no_intervalo(self):
        self.s.rotas[TA.rota_pdf(4)] = (403, "text/plain", b"negado")
        self.coletar(D(4), D(7))                                                        # suspensa pelo intervalo
        antes = sum(self.s.acessos.values())
        self.assertEqual(lotes.executar_lote(self.fonte, self.banco, self.acervo, lotes.PILOTO, politica=self.s.politica(),
                                             dormir=lambda s: None)["motivo"], "FONTE_SUSPENSA")
        resultado = coletor.descobrir(self.fonte, self.banco, self.s.politica(), D(1, 10), D(14), refazer=True)
        self.assertTrue(all("FONTE_SUSPENSA" in r["erro"] for r in resultado))
        self.assertEqual(sum(self.s.acessos.values()), antes)


# --------------------------------------------------------------------------------------------- Correção 7
class TesteFontesESuplementos(Base):
    def test_padrao_unico_de_fontes_e_escolha_explicita_preservada(self):
        self.assertEqual(F.selecionar(), ["auniao"])
        self.assertEqual(F.selecionar(["cge"]), ["cge"])
        with self.assertRaises(ValueError):
            F.selecionar(["outra"])
        from observatorio.coleta import __main__ as coleta_cli
        from observatorio.operacao import __main__ as operacao_cli
        for modulo in (coleta_cli, operacao_cli):
            self.assertIn("selecionar", modulo.__dict__ if modulo is coleta_cli else open(modulo.__file__, encoding="utf-8").read())

    def test_principal_dois_suplementos_e_extra_sao_documentos_distintos(self):
        extras = [NOV + "/diario-oficial-07-11-2026-suplemento.pdf", NOV + "/diario-oficial-07-11-2026-suplemento-1.pdf",
                  NOV + "/diario-oficial-07-11-2026-extra.pdf"]
        self.listagem(*extras)
        for i, e in enumerate(extras):
            self.publicar(e, f"doc-{i}")
        self.coletar(D(7), D(7))
        self.lida_em(D(14))
        dia = self.dias(D(7), D(7))["2026-11-07"]
        self.assertEqual((dia["situacao"], dia["listadas"], dia["arquivos_distintos"], dia["suplementos_ou_extras"]),
                         ("COMPLETO", 4, 4, 3))
        relacoes = {e["relacao"] for e in inventario.manifesto(self.banco, D(7), D(7), ["auniao"], self.acervo)["edicoes"]}
        self.assertEqual(relacoes, {"DOCUMENTO_DISTINTO"})

    def test_mesmo_documento_em_duas_urls(self):
        copia = NOV + "/diario-oficial-07-11-2026-portal-copia.pdf"
        self.listagem(copia)
        self.s.rotas[copia] = (200, "application/pdf", self.pdfs[TA.rota_pdf(7)])
        self.coletar(D(7), D(7))
        self.lida_em(D(14))
        dia = self.dias(D(7), D(7))["2026-11-07"]
        self.assertEqual((dia["situacao"], dia["listadas"], dia["arquivos_distintos"]), ("COMPLETO", 2, 1))
        relacoes = [e["relacao"] for e in inventario.manifesto(self.banco, D(7), D(7), ["auniao"], self.acervo)["edicoes"]]
        self.assertEqual(relacoes, ["MESMO_CONTEUDO_DE_OUTRA_URL"] * 2)
        self.assertEqual(sorted(d["resultado"] for d in self.banco.downloads() if d["resultado"] in ("NOVO", "DUPLICADO")),
                         ["DUPLICADO", "NOVO"])
