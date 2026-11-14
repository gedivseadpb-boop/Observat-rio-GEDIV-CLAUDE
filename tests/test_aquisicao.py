"""Etapa 05 — aquisição de PDFs oficiais: descoberta, download robusto, integridade, cobertura e idempotência.

Todos os testes rodam contra um servidor HTTP local (127.0.0.1) com PDFs sintéticos: nenhum acesso à internet,
nenhum dado pessoal. A prova de download real fica na sonda (python -m observatorio.operacao sonda).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from observatorio.coleta import coletor, inventario
from observatorio.coleta.fontes import AUniao, CGE
from observatorio.coleta.transporte import Direto, ManifestoContingencia
from observatorio.nucleo import banco as B
from observatorio.nucleo import pdf, rede
from observatorio.nucleo.acervo import Acervo
from observatorio.operacao import aquisicao
from tests.apoio import FonteLocal, Servidor, pdf_sem_paginas, pdf_sintetico

FIXTURE = Path(__file__).parent / "fixtures" / "auniao_edicoes_recentes.html"
NOV = "/servicos/doe/2026/novembro"
OUT = "/servicos/doe/2026/outubro"


def rota_pdf(dia: int, mes: str = NOV, sufixo: str = "") -> str:
    numero = 11 if mes == NOV else 10
    return f"{mes}/diario-oficial-{dia:02d}-{numero}-2026-portal{sufixo}.pdf"


class TesteListagemReal(unittest.TestCase):
    """Estrutura real da listagem "Edições recentes" (observada em 14/11/2026)."""

    def setUp(self):
        self.itens, self.paginas = AUniao().extrair(FIXTURE.read_text(encoding="utf-8"),
                                                    "https://auniao.pb.gov.br/doe/edicoes-recentes")

    def test_doze_edicoes_com_url_canonica_sem_view(self):
        self.assertEqual(len(self.itens), 12)
        self.assertTrue(all(i.url.endswith(".pdf") and "/view" not in i.url for i in self.itens))
        self.assertEqual({i.data for i in self.itens if i.data.month == 10}, {date(2026, 10, d) for d in (28, 29, 31)})

    def test_sufixo_menos_um_e_segunda_ordem_da_mesma_data(self):
        doze = [i for i in self.itens if i.data == date(2026, 11, 12)][0]
        self.assertEqual((doze.ordem, doze.tipo), (1, "normal"))

    def test_paginacao_e_links_que_nao_sao_edicoes(self):
        self.assertEqual(len(self.paginas), 3)                     # 12, 24 e 996, sem repetir o "Próximo"
        self.assertTrue(all("b_start" in p for p in self.paginas))
        self.assertFalse([i for i in self.itens if "resolveuid" in i.url])

    def test_mudancas_de_html_toleradas(self):
        html = ('<A CLASS="x" HREF="/servicos/doe/2026/novembro/Diario-Oficial-03-11-2026-Portal.PDF/@@download/file">a</A>'
                '<a href="diario-oficial-02-11-2026-suplemento.pdf">b</a>'
                '<a href="https://outro.gov.br/servicos/doe/2026/novembro/diario-oficial-01-11-2026-portal.pdf">c</a>')
        itens, _ = AUniao().extrair(html, "https://auniao.pb.gov.br/servicos/doe/2026/novembro/")
        por_data = {i.data: i for i in itens}
        self.assertEqual(set(por_data), {date(2026, 11, 3), date(2026, 11, 2)})   # servidor estranho ignorado
        self.assertEqual(por_data[date(2026, 11, 2)].tipo, "suplemento")
        self.assertTrue(por_data[date(2026, 11, 3)].url.endswith(".PDF"))

    def test_pagina_sem_edicoes_nao_e_erro(self):
        itens, paginas = AUniao().extrair("<html><body><p>Manutenção</p></body></html>", "https://auniao.pb.gov.br/doe/edicoes-recentes")
        self.assertEqual((itens, paginas), ([], []))


class TesteVerificacaoDoPdf(unittest.TestCase):
    def test_pdf_integro_tem_paginas_contadas(self):
        dados = pdf_sintetico("x", paginas=3)
        laudo = pdf.verificar(dados, len(dados))
        self.assertEqual((laudo.valido, laudo.paginas, laudo.integridade), (True, 3, "ESTRUTURA_VERIFICADA"))
        self.assertEqual(laudo.sha256, hashlib.sha256(dados).hexdigest())

    def test_tamanho_divergente_do_anunciado(self):
        dados = pdf_sintetico("x")
        laudo = pdf.verificar(dados, len(dados) + 10)
        self.assertEqual((laudo.valido, laudo.motivo, laudo.truncado), (False, "TAMANHO_DIVERGENTE", True))

    def test_truncado_sem_fim_de_arquivo(self):
        dados = pdf_sintetico("x")
        laudo = pdf.verificar(dados[:-40])
        self.assertEqual((laudo.motivo, laudo.truncado, laudo.quarentena), ("SEM_FIM_DE_ARQUIVO", True, False))

    def test_eof_presente_mas_estrutura_ilegivel_vai_para_quarentena(self):
        laudo = pdf.verificar(pdf_sem_paginas("x"))
        self.assertFalse(laudo.valido)
        self.assertTrue(laudo.quarentena)
        self.assertEqual(laudo.integridade, "INCONCLUSIVA")
        self.assertIn("SEM_STARTXREF", laudo.alertas)

    def test_um_unico_eof_nao_basta(self):
        # Revisão incremental: o arquivo cortado logo após o primeiro %%EOF parece completo pelo marcador.
        base = pdf_sintetico("rev")
        completo = base + b"% revisao incremental\n" + b"y" * 2000 + b"\n%%EOF\n"
        cortado = completo[: len(base)]
        self.assertEqual(pdf.verificar(cortado, len(completo)).motivo, "TAMANHO_DIVERGENTE")  # Content-Length denuncia
        sem_anuncio = pdf.verificar(cortado)
        self.assertIn("SEM_CONTENT_LENGTH", sem_anuncio.alertas)  # sem Content-Length a limitação fica registrada

    def test_html_e_pdf_invalido(self):
        self.assertEqual(pdf.verificar(b"<!DOCTYPE html><html>erro</html>").motivo, "RECEBIDO_HTML_EM_VEZ_DE_PDF")
        self.assertEqual(pdf.verificar(b"GIF89a" + b"0" * 2000).motivo, "SEM_ASSINATURA_PDF")
        self.assertEqual(pdf.verificar(b"").motivo, "VAZIO")


class TesteRede(unittest.TestCase):
    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)
        self.esperas = []

    def obter(self, caminho, **extras):
        return rede.obter(self.s.base + caminho, self.s.politica(**extras), dormir=self.esperas.append)

    def categoria(self, caminho, **extras):
        with self.assertRaises(rede.ErroRede) as ctx:
            self.obter(caminho, **extras)
        return ctx.exception

    def test_200_com_menos_bytes_que_o_anunciado_e_truncado_e_repetido(self):
        dados = pdf_sintetico("t")
        self.s.rotas["/t.pdf"] = (200, "application/pdf", dados, {"cortar": len(dados) // 2})
        erro = self.categoria("/t.pdf", tentativas=3)
        self.assertEqual(erro.categoria, "TRUNCADO")
        self.assertEqual(self.s.acessos["/t.pdf"], 3)                  # transitório: tentativas limitadas

    def test_truncado_na_primeira_e_completo_na_segunda(self):
        dados = pdf_sintetico("t2")
        self.s.rotas["/t.pdf"] = lambda n: (200, "application/pdf", dados, {"cortar": 500} if n == 1 else {})
        resposta = self.obter("/t.pdf", tentativas=2)
        self.assertEqual((resposta.corpo, resposta.content_length, resposta.tentativas), (dados, len(dados), 2))

    def test_403_e_404_nao_sao_repetidos(self):
        self.s.rotas["/x"] = (403, "text/html", b"negado")
        self.assertTrue(self.categoria("/x", tentativas=3).recusa)
        self.s.rotas["/y"] = (404, "text/html", b"")
        self.assertEqual(self.categoria("/y", tentativas=3).categoria, "HTTP_404")
        self.assertEqual((self.s.acessos["/x"], self.s.acessos["/y"]), (1, 1))

    def test_429_registra_retry_after_e_para(self):
        self.s.rotas["/x"] = (429, "text/plain", b"", {"cabecalhos": {"Retry-After": "120"}})
        erro = self.categoria("/x", tentativas=3)
        self.assertEqual((erro.categoria, erro.retry_after, erro.recusa, self.s.acessos["/x"]), ("HTTP_429", 120.0, True, 1))

    def test_500_e_503_repetidos_com_espera_progressiva_e_retry_after_com_teto(self):
        self.s.rotas["/x"] = (500, "text/plain", b"")
        self.categoria("/x", tentativas=3, espera=1)
        self.assertEqual((self.s.acessos["/x"], self.esperas), (3, [1, 2]))
        self.esperas.clear()
        self.s.rotas["/y"] = (503, "text/plain", b"", {"cabecalhos": {"Retry-After": "999"}})
        self.categoria("/y", tentativas=2, espera=1, espera_maxima=30)
        self.assertEqual(self.esperas, [30])

    def test_tempo_esgotado(self):
        self.s.rotas["/lento"] = lambda n: (time.sleep(1.5), (200, "text/plain", b"ok"))[1]
        self.assertEqual(self.categoria("/lento", tentativas=1, tempo_limite=0.5).categoria, "TEMPO_ESGOTADO")

    def test_redirecionamento_para_destino_nao_autorizado(self):
        self.s.rotas["/r"] = (302, "text/plain", b"https://169.254.169.254/latest/meta-data")
        self.assertEqual(self.categoria("/r").categoria, "URL_NAO_PERMITIDA")
        self.s.rotas["/r2"] = (302, "text/plain", b"/destino")
        self.s.rotas["/destino"] = (200, "text/plain", b"ok")
        self.assertEqual(self.obter("/r2").redirecionamentos, [self.s.base + "/destino"])

    def test_recusa_do_proxy_do_executor_nao_e_atribuida_a_fonte(self):
        import os
        import urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class Proxy(BaseHTTPRequestHandler):
            def do_CONNECT(self):
                self.send_response(403)
                self.end_headers()

            def log_message(self, *args):
                pass

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        antigo = rede._ABRIDOR
        rede._ABRIDOR = urllib.request.build_opener(
            rede._SemRedirecionar, urllib.request.ProxyHandler({"https": f"http://127.0.0.1:{servidor.server_address[1]}"}))
        self.addCleanup(setattr, rede, "_ABRIDOR", antigo)
        politica = rede.Politica(servidores=frozenset({"auniao.pb.gov.br"}), tentativas=3, espera=0, tempo_limite=3)
        with self.assertRaises(rede.ErroRede) as ctx:
            rede.obter("https://auniao.pb.gov.br/doe/edicoes-recentes", politica)
        self.assertEqual((ctx.exception.categoria, ctx.exception.transitorio), ("PROXY_RECUSOU", False))

    def test_esquema_e_credenciais_na_url_recusados(self):
        politica = self.s.politica()
        for url in ("file:///etc/passwd", f"http://usuario@{self.s.endereco}/x", "http://10.0.0.1/x"):
            with self.assertRaises(rede.ErroRede) as ctx:
                rede.obter(url, politica)
            self.assertEqual(ctx.exception.categoria, "URL_NAO_PERMITIDA")


class Base(unittest.TestCase):
    hoje = date(2026, 11, 14)

    def setUp(self):
        self.s = Servidor()
        self.addCleanup(self.s.encerrar)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.banco = B.Banco(Path(self.tmp.name) / "b.sqlite3")
        self.addCleanup(self.banco.fechar)
        self.acervo = Acervo(Path(self.tmp.name) / "acervo")
        self.fonte = FonteLocal(AUniao(), self.s)
        self.pdfs = {}
        html = FIXTURE.read_text(encoding="utf-8").replace("https://auniao.pb.gov.br", "")
        self.s.rotas["/doe/edicoes-recentes"] = (200, "text/html", html.encode())
        self.s.rotas[NOV] = (200, "text/html", html.encode())         # listagem mensal com os mesmos links
        self.s.rotas[OUT] = (200, "text/html", html.encode())
        for dia in (4, 5, 6, 7, 10, 11, 13, 14):
            self.publicar(rota_pdf(dia), f"nov-{dia}")
        self.publicar(rota_pdf(12, sufixo="-1"), "nov-12-1")
        for dia in (28, 29, 31):
            self.publicar(rota_pdf(dia, OUT), f"out-{dia}")

    def publicar(self, caminho, marca, **opcoes):
        dados = pdf_sintetico(marca, paginas=2)
        self.pdfs[caminho] = dados
        self.s.rotas[caminho] = (200, "application/pdf", dados, opcoes) if opcoes else (200, "application/pdf", dados)

    def coletar(self, inicio, fim, **extras):
        return coletor.coletar_intervalo([self.fonte], self.banco, self.acervo, inicio, fim,
                                         politica=self.s.politica(), hoje=self.hoje, **extras)

    def arquivos_no_acervo(self):
        return sorted(p.name for p in Path(self.acervo.raiz).rglob("*.pdf"))


class TesteColetaPorPeriodo(Base):
    def test_coletar_dia_baixa_so_o_dia_com_procedencia_completa(self):
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"NOVO": 1})
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(pub["estado"], B.BAIXADA)
        self.assertEqual(pub["url"], f"{self.s.base}{rota_pdf(7)}")
        d = self.banco.downloads(pub["id"])[-1]
        dados = self.pdfs[rota_pdf(7)]
        self.assertEqual((d["sha256"], d["bytes"], d["content_length"], d["paginas"], d["integridade"], d["transporte"]),
                         (hashlib.sha256(dados).hexdigest(), len(dados), len(dados), 2, "ESTRUTURA_VERIFICADA", "direto"))
        self.assertEqual((d["status_http"], d["resultado"], d["versao_coletor"]), (200, "NOVO", coletor.VERSAO_COLETOR))
        self.assertEqual(self.banco.verificacao(pub["sha256"])["paginas"], 2)

    def test_intervalo_cruza_meses_e_respeita_limites(self):
        resumo = self.coletar(date(2026, 10, 29), date(2026, 11, 5))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"NOVO": 4})          # 29/10, 31/10, 04/11, 05/11
        self.assertEqual(len(resumo["fontes"]["auniao"]["varreduras"]), 2)

    def test_segunda_execucao_e_idempotente(self):
        self.coletar(date(2026, 11, 4), date(2026, 11, 7))
        antes = (self.arquivos_no_acervo(), len(self.banco.publicacoes()), len(self.banco.downloads()), len(self.banco.arquivos()))
        acessos_pdf = sum(n for c, n in self.s.acessos.items() if c.endswith(".pdf"))
        resumo = self.coletar(date(2026, 11, 4), date(2026, 11, 7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {})
        depois = (self.arquivos_no_acervo(), len(self.banco.publicacoes()), len(self.banco.downloads()), len(self.banco.arquivos()))
        self.assertEqual(antes, depois)
        self.assertEqual(sum(n for c, n in self.s.acessos.items() if c.endswith(".pdf")), acessos_pdf)  # nada rebaixado

    def test_fora_de_ordem_e_mesmo_conteudo_em_dois_enderecos(self):
        self.s.rotas[rota_pdf(5)] = (200, "application/pdf", self.pdfs[rota_pdf(4)])   # republicação idêntica
        self.coletar(date(2026, 11, 6), date(2026, 11, 7))
        self.coletar(date(2026, 11, 4), date(2026, 11, 5))
        r = {p["data_publicacao"]: p for p in self.banco.publicacoes() if p["estado"] == B.BAIXADA}
        self.assertEqual(r["2026-11-04"]["sha256"], r["2026-11-05"]["sha256"])
        self.assertEqual(len(self.arquivos_no_acervo()), 3)                              # 4=5, 6, 7
        self.assertEqual(self.banco.downloads(r["2026-11-05"]["id"])[-1]["resultado"], "DUPLICADO")

    def test_mesmo_identificador_com_hash_novo_preserva_versao_anterior(self):
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(self.coletar(date(2026, 11, 7), date(2026, 11, 7), reverificar=True)["fontes"]["auniao"]["downloads"],
                         {"IGUAL": 1})
        self.publicar(rota_pdf(7), "nov-7-substituida")
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7), reverificar=True)
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"ALTERADO": 1})
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(len(self.banco.versoes(pub["id"])), 2)
        self.assertEqual(len(self.arquivos_no_acervo()), 2)                              # nada apagado

    def test_truncado_com_http_200_nao_entra_e_e_recuperado_depois(self):
        dados = self.pdfs[rota_pdf(7)]
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", dados, {"cortar": len(dados) - 200})
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {B.FALHA_DOWNLOAD: 1})
        self.assertEqual(self.arquivos_no_acervo(), [])
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertIn("TRUNCADO", pub["ultimo_erro"])
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", dados)
        self.assertEqual(self.coletar(date(2026, 11, 7), date(2026, 11, 7))["fontes"]["auniao"]["downloads"], {"NOVO": 1})
        self.assertTrue(self.acervo.conferir(hashlib.sha256(dados).hexdigest()))

    def test_truncado_sem_content_length_e_detectado_pela_estrutura(self):
        dados = self.pdfs[rota_pdf(7)]
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", dados[:-300], {"anunciar": None})
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(pub["estado"], B.FALHA_DOWNLOAD)
        self.assertIn("SEM_FIM_DE_ARQUIVO", pub["ultimo_erro"])

    def test_estrutura_inconclusiva_fica_em_quarentena_fora_do_acervo(self):
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", pdf_sem_paginas("q"))
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {B.QUARENTENA: 1})
        self.assertEqual(self.arquivos_no_acervo(), [])
        self.assertEqual(len(list((Path(self.tmp.name) / "quarentena").glob("*.pdf"))), 1)
        self.assertEqual(self.coletar(date(2026, 11, 7), date(2026, 11, 7))["fontes"]["auniao"]["downloads"], {})  # não insiste
        dia = inventario.cobertura(self.banco, date(2026, 11, 7), date(2026, 11, 7), ["auniao"])[0]
        self.assertEqual(dia["situacao"], "QUARENTENA")

    def test_html_no_lugar_do_pdf_e_falha_no_meio(self):
        self.s.rotas[rota_pdf(7)] = (200, "text/html", b"<!DOCTYPE html><html>visualizar</html>")
        self.s.rotas[rota_pdf(7) + "/@@download/file"] = (500, "text/plain", b"")
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(pub["estado"], B.INVALIDA)
        self.assertEqual([d["resultado"] for d in self.banco.downloads(pub["id"])], ["REPROVADO", "ERRO_REDE"])

    def test_dry_run_nao_baixa_nada(self):
        resumo = self.coletar(date(2026, 11, 4), date(2026, 11, 7), simular=True)
        downloads = resumo["fontes"]["auniao"]["downloads"]
        self.assertEqual(downloads["SIMULADA"], 4)
        self.assertEqual([p["data"] for p in downloads["previstas"]], ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"])
        self.assertFalse([c for c in self.s.acessos if c.endswith(".pdf")])
        self.assertEqual((self.arquivos_no_acervo(), self.banco.downloads()), ([], []))

    def test_limite_e_tentativas_esgotadas(self):
        self.assertEqual(self.coletar(date(2026, 11, 4), date(2026, 11, 7), limite=1)["fontes"]["auniao"]["downloads"],
                         {"NOVO": 1, "ADIADA": 3})
        self.s.rotas[rota_pdf(13)] = (404, "text/plain", b"")
        for _ in range(5):
            self.coletar(date(2026, 11, 13), date(2026, 11, 13))
        self.assertEqual(self.coletar(date(2026, 11, 13), date(2026, 11, 13))["fontes"]["auniao"]["downloads"], {"ESGOTADA": 1})

    def test_intervalo_invalido_recusado(self):
        for inicio, fim in ((date(2026, 11, 7), date(2026, 11, 6)), (date(2026, 11, 7), date(2026, 11, 20)),
                            (date(2026, 1, 1), date(2026, 11, 12)), (date(2024, 12, 30), date(2025, 1, 2))):
            with self.assertRaises(coletor.IntervaloInvalido):
                self.coletar(inicio, fim)
        self.assertEqual(self.banco.publicacoes(), [])


class TesteCobertura(Base):
    def test_estados_distintos_do_dia(self):
        self.coletar(date(2026, 11, 4), date(2026, 11, 14))
        self.s.rotas[OUT] = (500, "text/plain", b"")
        self.s.rotas["/doe/edicoes-recentes"] = (500, "text/plain", b"")
        self.coletar(date(2026, 10, 25), date(2026, 10, 26))
        linhas = {l["data"]: l for l in inventario.cobertura(self.banco, date(2026, 9, 30), date(2026, 11, 14), ["auniao"])}
        self.assertEqual(linhas["2026-11-07"]["situacao"], "COMPLETO")
        self.assertEqual(linhas["2026-11-08"]["situacao"], "SEM_PUBLICACAO_LISTADA")     # domingo sem edição, mês lido
        self.assertEqual((linhas["2026-10-26"]["situacao"], linhas["2026-10-26"]["motivo"]), ("NAO_VERIFICADO", "FONTE_INDISPONIVEL"))
        self.assertEqual((linhas["2026-09-30"]["situacao"], linhas["2026-09-30"]["motivo"]), ("NAO_VERIFICADO", "NUNCA_LIDA"))

    def test_edicao_listada_e_ausente_do_acervo(self):
        self.coletar(date(2026, 11, 4), date(2026, 11, 7), simular=True)
        dia = inventario.cobertura(self.banco, date(2026, 11, 5), date(2026, 11, 5), ["auniao"])[0]
        self.assertEqual(dia["situacao"], "PENDENTE")

    def test_manifesto_sem_dados_pessoais_e_com_procedencia(self):
        self.coletar(date(2026, 11, 4), date(2026, 11, 7))
        m = inventario.manifesto(self.banco, date(2026, 11, 1), date(2026, 11, 7), ["auniao"])
        self.assertEqual(len(m["edicoes"]), 4)
        e = m["edicoes"][0]
        self.assertEqual(set(e), {"fonte", "url_oficial", "data", "tipo", "ordem", "estado", "sha256", "bytes", "paginas",
                                  "integridade", "versoes", "tentativas", "ultimo_erro", "coletado_em", "transporte",
                                  "versao_coletor"})
        self.assertEqual((e["integridade"], e["paginas"], e["transporte"]), ("ESTRUTURA_VERIFICADA", 2, "direto"))
        self.assertFalse([l for l in m["lacunas"] if l["situacao"] in ("COMPLETO", "SEM_PUBLICACAO_LISTADA")])
        json.dumps(m)                                                                    # serializável


class TesteTransporteESonda(Base):
    def test_contingencia_registra_procedencia_e_confere_hash(self):
        pasta = Path(self.tmp.name) / "contingencia"
        pasta.mkdir()
        dados = self.pdfs[rota_pdf(7)]
        (pasta / "a.pdf").write_bytes(dados)
        url = f"{self.s.base}{rota_pdf(7)}"
        (pasta / "m.json").write_text(json.dumps({url: {"arquivo": "a.pdf", "sha256": hashlib.sha256(dados).hexdigest()}}))
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7), transporte=ManifestoContingencia(pasta / "m.json"))
        self.assertEqual((resumo["transporte"], resumo["fontes"]["auniao"]["downloads"]), ("manifesto_contingencia", {"NOVO": 1}))
        self.assertFalse([c for c in self.s.acessos if c.endswith(".pdf")])               # nenhum download direto
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(self.banco.downloads(pub["id"])[-1]["transporte"], "manifesto_contingencia")
        (pasta / "m.json").write_text(json.dumps({url: {"arquivo": "a.pdf", "sha256": "0" * 64}}))
        with self.assertRaises(rede.ErroRede) as ctx:
            ManifestoContingencia(pasta / "m.json").obter(url, self.s.politica())
        self.assertEqual(ctx.exception.categoria, "CONTINGENCIA_DIVERGENTE")

    def test_sonda_descobre_baixa_em_pasta_vazia_e_verifica(self):
        r = aquisicao.sonda(fonte=self.fonte, politica=self.s.politica(),
                            hashes_conhecidos={f"{self.s.base}{rota_pdf(14)}": hashlib.sha256(self.pdfs[rota_pdf(14)]).hexdigest()})
        self.assertEqual(r["situacao"], "DOWNLOAD_INTEGRO")
        self.assertEqual(r["edicao"]["data"], "2026-11-14")
        self.assertEqual((r["edicao"]["paginas"], r["edicao"]["hash_historico"], r["edicao"]["gravado_e_reconferido"]),
                         (2, "IGUAL", True))
        t = r["tentativas"][0]
        self.assertEqual((t["status"], t["content_length"], t["integridade"]), (200, len(self.pdfs[rota_pdf(14)]), "ESTRUTURA_VERIFICADA"))
        self.assertNotIn("hostname", json.dumps(r["ambiente"]))

    def test_sonda_registra_bloqueio_sem_contornar(self):
        self.s.rotas["/doe/edicoes-recentes"] = (403, "text/html", b"negado")
        r = aquisicao.sonda(fonte=self.fonte, politica=self.s.politica())
        self.assertEqual((r["situacao"], r["listagem"]["erro"]), ("LISTAGEM_INACESSIVEL", "HTTP_403"))
        self.assertEqual(self.s.acessos["/doe/edicoes-recentes"], 1)

    def test_cge_sem_listagem_recente_continua_funcionando(self):
        self.assertFalse(hasattr(FonteLocal(CGE(), self.s), "url_recentes"))
        self.assertEqual(coletor.descobrir_recentes(FonteLocal(CGE(), self.s), self.banco, self.s.politica()),
                         {"fonte": "cge", "recentes": "NAO_OFERECIDA"})


if __name__ == "__main__":
    unittest.main()
