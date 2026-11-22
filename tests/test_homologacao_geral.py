"""Etapa 05.3.5 — homologação geral: a cadeia inteira e os indicadores, com dados SINTÉTICOS.

Parte 1 (cadeia): PDF → validação → acervo → leitura → classificação → banco → revisão humana → API → indicadores →
exportação. Cada cenário usa um PDF gerado no próprio teste e confere os registros INTERMEDIÁRIOS, não só a contagem
final. Parte 2 (indicadores e revisão): o que o painel conta, o que fica na fila da gerência e o que o público vê.

Nenhum dado real: pessoas, matrículas e processos são fictícios (`observatorio.operacao.sintetico`).
"""
import importlib.util
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

from observatorio.gerencias.gediv import catalogo as C
from observatorio.gerencias.gediv import processo
from observatorio.nucleo import banco as B
from observatorio.nucleo.acervo import Acervo
from observatorio.painel import indicadores
from observatorio.revisao import servico
from observatorio.web.servidor import criar_servidor
from tests import test_leitura_banco_revisao as LB
from tests import test_painel as TP
from tests import textos_doe as T

TEM_PDF = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))
REV, JUST = TP.REVISOR, TP.JUST
GER, PUB = indicadores.GERENCIA_PERFIL, indicadores.PUBLICO
TOKEN = "credencial-de-homologacao-0123456789"
ZERO = dict(processos=0, resenhas=0, decisoes=0, deferidos=0, indeferidos=0, refeitos=0, sem_efeito=0)


def pedir(url, caminho, token=None, corpo=None):
    pedido = urllib.request.Request(url + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                    headers={"Content-Type": "application/json"} if corpo is not None else {})
    if token:
        pedido.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(pedido, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ====================================================================================================================
# Parte 1 — a cadeia completa, com PDFs sintéticos
# ====================================================================================================================
@unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab (pip install -r requirements-dev.txt)")
class Cadeia(unittest.TestCase):
    def setUp(self):
        from observatorio.operacao import fluxo, sintetico
        self.fluxo, self.S = fluxo, sintetico
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self.dados = self.raiz / "dados"
        self.entrada = self.raiz / "entrada"
        self.entrada.mkdir()

    def pdf(self, dia: date, edicao: int, blocos, pasta: str = "") -> Path:
        destino = self.entrada / pasta
        destino.mkdir(exist_ok=True)
        caminho = destino / f"diario-oficial-{dia.day:02d}-{dia.month:02d}-{dia.year}-portal.pdf"
        caminho.write_bytes(self.S.diario(dia, edicao, blocos))
        return caminho

    def executar(self, origem=None, **k):
        return self.fluxo.executar(self.dados, origem, **k)

    def banco(self):
        banco = B.Banco(self.dados / "observatorio.sqlite3")
        self.addCleanup(banco.fechar)
        return banco

    def edicao_padrao(self, dia=date(2026, 10, 8), edicao=18700, pasta=""):
        S = self.S
        return self.pdf(dia, edicao, [S.resenha_progressao(801, "07-10-2026", "VERTICAL", "GAJ-1700", 1, 3),
                                     S.resenha_tempo(802, "07-10-2026", "LICENÇA ESPECIAL", 10, 2)], pasta)

    def conferir_tudo(self, banco):
        for (ato,) in banco.con.execute("SELECT DISTINCT ato_id FROM decisao WHERE validacao = 'PENDENTE' AND vigente = 1").fetchall():
            servico.revisar_ato(banco, ato, servico.CONFERIR, REV, JUST, True, True)

    def painel(self, banco, perfil=GER, **filtros):
        return indicadores.painel(banco, filtros, perfil)


class TesteCadeiaDocumentoIntegro(Cadeia):
    def test_01_pdf_integro_cada_registro_aponta_para_a_sua_origem(self):
        arquivo = self.edicao_padrao()
        r = self.executar(arquivo)
        self.assertEqual((r["resultado"]["codigo"], r["resultado"]["situacao"]), (0, "SUCESSO"))
        sha = r["importacao"][0]["sha256"]
        banco = self.banco()
        # acervo: o arquivo guardado é o mesmo que entrou, identificado pelo SHA-256
        acervo = Acervo(self.dados / "acervo")
        self.assertTrue(acervo.conferir(sha))
        self.assertEqual(acervo.caminho(sha).read_bytes(), arquivo.read_bytes())
        # leitura: edição e data lidas do próprio documento; todas as páginas com qualidade registrada
        leitura = banco.con.execute("SELECT situacao, numero_edicao, data_edicao FROM leitura WHERE sha256 = ?", (sha,)).fetchone()
        self.assertEqual(tuple(leitura), ("LIDA", "18700", "2026-10-08"))
        self.assertEqual({q for (q,) in banco.con.execute("SELECT qualidade FROM pagina WHERE sha256 = ?", (sha,))}, {"OK"})
        # classificação: atos e decisões presos ao arquivo e à página; trecho literal presente no texto lido
        atos = banco.con.execute("SELECT numero, eixo, modalidade, grupo, subcategoria, sha256, pagina FROM ato ORDER BY numero").fetchall()
        self.assertEqual([tuple(a) for a in atos], [("801/2026", C.PROGRESSAO, C.VERTICAL, "GAJ", None, sha, 1),
                                                     ("802/2026", C.TEMPO, None, None, "TS-05", sha, 1)])
        texto = banco.con.execute("SELECT texto FROM pagina WHERE sha256 = ? AND numero = 1", (sha,)).fetchone()[0]
        decisoes = banco.con.execute("SELECT processo, matricula, servidor, sha256, pagina, validacao, vigente, origem FROM decisao ORDER BY rowid").fetchall()
        self.assertEqual(len(decisoes), 5)
        for d in decisoes:
            self.assertEqual((d["sha256"], d["pagina"], d["validacao"], d["vigente"]), (sha, 1, "PENDENTE", 1))
            self.assertIn(d["processo"], texto)
            self.assertIn(d["servidor"], texto)
        # nada conferido: os indicadores oficiais estão em zero e o público não recebe linha alguma
        self.assertEqual(self.painel(banco)["indicadores"], ZERO)
        self.assertEqual(self.painel(banco, PUB)["linhas"], [])

    def test_08_documento_sem_pertinencia_nao_cria_ato_nem_decisao(self):
        S = self.S
        arquivo = self.pdf(date(2026, 10, 9), 18701, [S.outros_atos(1), S.outros_atos(2)])
        r = self.executar(arquivo)
        self.assertEqual(r["resultado"]["codigo"], 0)
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM ato").fetchone()[0], 0)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], 0)
        self.assertEqual(r["classificacao"]["descartados"], 2)                     # reconhecidos e postos de lado, não ignorados
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM leitura WHERE situacao = 'LIDA'").fetchone()[0], 1)
        self.assertEqual(banco.arquivos_sem_classificacao(processo.GERENCIA, C.VERSAO_REGRAS), [])   # foi examinado

    def test_03_repetir_o_mesmo_pdf_nao_duplica_nada(self):
        arquivo = self.edicao_padrao()
        self.executar(arquivo)
        r = self.executar(arquivo)
        self.assertEqual(r["resultado"]["codigo"], 0)
        banco = self.banco()
        self.assertEqual(tuple(banco.con.execute("SELECT (SELECT COUNT(*) FROM arquivo), (SELECT COUNT(*) FROM ato), (SELECT COUNT(*) FROM decisao)").fetchone()),
                         (1, 2, 5))


class TesteCadeiaDocumentoComDefeito(Cadeia):
    def test_02_pdf_invalido_ou_incompleto_e_recusado_e_o_comando_falha(self):
        bom = self.edicao_padrao().read_bytes()
        casos = {"cortado no começo": bom[:900], "cortado no meio": bom[:len(bom) // 2] + b"\n" * 2000,
                 "não é PDF": b"<html><body>pagina de erro</body></html>" * 100}
        for nome, conteudo in casos.items():
            with self.subTest(caso=nome):
                arquivo = self.entrada / "diario-oficial-09-10-2026-portal.pdf"
                arquivo.write_bytes(conteudo)
                r = self.executar(arquivo)
                self.assertEqual((r["resultado"]["codigo"], r["resultado"]["situacao"]), (1, "FALHA"))
                self.assertFalse(r["importacao"][0]["aceito"])
                self.assertTrue(r["importacao"][0]["motivo"])
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0], 0)       # nada entrou no acervo
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], 0)

    def duas_paginas(self):
        S = self.S
        cheia = S.resenha_progressao(801, "07-10-2026", "VERTICAL", "GAJ-1700", 1, 70)             # ocupa a 1ª página inteira
        return self.pdf(date(2026, 10, 8), 18700, [cheia, S.resenha_tempo(802, "07-10-2026", "LICENÇA ESPECIAL", 100, 2)])

    def test_03_e_04_pagina_ilegivel_fica_pendente_e_a_releitura_recupera_sem_duplicar(self):
        from observatorio.leitura import leitor, ocr
        arquivo = self.duas_paginas()
        original = leitor._ler_uma_pagina

        def segunda_pagina_esgota(numero, pagina):
            if numero == 2:
                raise ocr.OcrEsgotado("limite de tempo de OCR por página atingido")
            return original(numero, pagina)
        with mock.patch.object(leitor, "_ler_uma_pagina", segunda_pagina_esgota):
            r = self.executar(arquivo)
        # página pendente: o comando NÃO sai como sucesso, a leitura não é "LIDA", e a pendência chega à classificação
        self.assertEqual((r["resultado"]["codigo"], r["resultado"]["situacao"]), (3, "CONCLUIDO_COM_PENDENCIAS"))
        self.assertIn("comando", r["resultado"]["retomada"])
        banco = self.banco()
        sha = r["importacao"][0]["sha256"]
        self.assertEqual(banco.con.execute("SELECT situacao FROM leitura WHERE sha256 = ?", (sha,)).fetchone()[0], "LIDA_COM_PENDENCIAS")
        self.assertEqual([q for (q,) in banco.con.execute("SELECT qualidade FROM pagina WHERE sha256 = ? ORDER BY numero", (sha,))],
                         ["OK", "OCR_ESGOTADO"])
        pendencias = json.loads(banco.con.execute("SELECT pendencias FROM classificacao WHERE sha256 = ?", (sha,)).fetchone()[0])
        self.assertTrue(any("páginas com leitura pendente" in p and "2" in p for p in pendencias))
        antes = banco.con.execute("SELECT COUNT(*) FROM decisao WHERE vigente = 1").fetchone()[0]
        banco.fechar()
        # retomada: a página é relida, a classificação é refeita e nada é contado duas vezes
        r = self.executar(refazer_pendentes=True)
        self.assertEqual(r["resultado"]["codigo"], 0)
        banco = self.banco()
        self.assertEqual([q for (q,) in banco.con.execute("SELECT qualidade FROM pagina WHERE sha256 = ? ORDER BY numero", (sha,))], ["OK", "OK"])
        depois = banco.con.execute("SELECT COUNT(*) FROM decisao WHERE vigente = 1").fetchone()[0]
        self.assertEqual(depois, 72)
        self.assertGreaterEqual(depois, antes)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM (SELECT chave_logica FROM decisao WHERE vigente = 1 GROUP BY chave_logica HAVING COUNT(*) > 1)").fetchone()[0], 0)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM tentativa_leitura WHERE sha256 = ?", (sha,)).fetchone()[0], 2)   # o histórico fica

    def test_13_e_15_falha_na_classificacao_nao_grava_pela_metade_e_e_retomada(self):
        arquivo = self.edicao_padrao()
        with mock.patch.object(processo, "classificar", side_effect=RuntimeError("falha simulada")):
            r = self.executar(arquivo)
        self.assertEqual((r["resultado"]["codigo"], r["classificacao"]["com_erro"]), (1, 1))
        self.assertEqual(r["classificacao"]["erros"][0]["erro"], "RuntimeError")       # só o tipo: a mensagem poderia ter dados
        self.assertEqual(r["resultado"]["retomada"]["fila_de_classificacao"], 1)
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM ato").fetchone()[0], 0)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM leitura WHERE situacao = 'LIDA'").fetchone()[0], 1)   # a leitura foi preservada
        banco.fechar()
        r = self.executar()                                                              # nova execução, sem informar o arquivo
        self.assertEqual((r["resultado"]["codigo"], r["classificacao"]["decisoes"]), (0, 5))

    def test_14_interrupcao_durante_a_persistencia_desfaz_tudo_e_a_fila_continua(self):
        arquivo = self.edicao_padrao()
        original = B.Banco._reconciliar_atos

        def cai_no_fim(banco, *a, **k):                                                  # atos e decisões já inseridos na transação
            raise sqlite3.OperationalError("disco cheio (simulado)")
        with mock.patch.object(B.Banco, "_reconciliar_atos", cai_no_fim):
            r = self.executar(arquivo)
        self.assertEqual(r["resultado"]["codigo"], 1)
        banco = self.banco()
        for tabela in ("ato", "decisao", "evento", "classificacao", "outra_publicacao"):
            self.assertEqual(banco.con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0], 0, tabela)
        self.assertEqual(len(banco.arquivos_sem_classificacao(processo.GERENCIA, C.VERSAO_REGRAS)), 1)
        self.assertEqual(banco.con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        banco.fechar()
        self.assertIs(B.Banco._reconciliar_atos, original)
        r = self.executar()
        self.assertEqual((r["resultado"]["codigo"], r["classificacao"]["atos"], r["classificacao"]["decisoes"]), (0, 2, 5))

    def test_15_erro_de_leitura_fica_registrado_bloqueia_o_sucesso_e_e_refeito(self):
        from observatorio.leitura import leitor
        arquivo = self.edicao_padrao()
        with mock.patch.object(leitor, "ler_arquivo", side_effect=ValueError("PDF ilegível (simulado)")):
            r = self.executar(arquivo)
        self.assertEqual((r["resultado"]["codigo"], r["leitura"]["ERRO"]), (1, 1))
        r = self.executar()                                                              # sem refazer: o erro antigo continua bloqueando
        self.assertEqual(r["resultado"]["codigo"], 1)
        self.assertTrue(any("execuções anteriores" in m for m in r["resultado"]["motivos"]))
        r = self.executar(refazer_pendentes=True)
        self.assertEqual((r["resultado"]["codigo"], r["classificacao"]["decisoes"]), (0, 5))


class TesteCadeiaVersoesERevisao(Cadeia):
    def test_06_nova_versao_tecnica_do_pdf_nao_conta_duas_vezes_e_preserva_as_duas(self):
        primeiro = self.edicao_padrao()
        self.executar(primeiro)
        outro = self.entrada / "republicado" / primeiro.name
        outro.parent.mkdir()
        outro.write_bytes(primeiro.read_bytes() + b"\n% gerado novamente pela imprensa oficial\n")
        r = self.executar(outro)
        self.assertEqual((r["resultado"]["codigo"], r["importacao"][0]["resultado"]), (0, "ALTERADO"))
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0], 2)        # as duas versões físicas ficam
        acervo = Acervo(self.dados / "acervo")
        self.assertTrue(all(acervo.conferir(s) for (s,) in banco.con.execute("SELECT sha256 FROM arquivo")))
        self.assertEqual(tuple(banco.con.execute("SELECT COUNT(*), SUM(vigente) FROM decisao").fetchone()), (10, 5))
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE vigente = 0 AND representada_por IS NULL").fetchone()[0], 0)
        self.conferir_tudo(banco)
        i = self.painel(banco)["indicadores"]
        self.assertEqual((i["decisoes"], i["resenhas"], i["processos"]), (5, 2, 5))

    def test_05_decisao_omitida_e_registrada_pela_gerencia_com_o_trecho_do_documento(self):
        S = self.S
        resenha = S.resenha_progressao(801, "07-10-2026", "VERTICAL", "GAJ-1700", 1, 3)
        # uma linha da tabela fora do formato: sem processo e sem matrícula reconhecíveis — o robô não a extrai
        resenha.insert(-1, "PROCESSO 9.999/26 PESSOA FICTICIA OMITIDA TECNICO ADMINISTRATIVO A B")
        r = self.executar(self.pdf(date(2026, 10, 8), 18700, [resenha]))
        self.assertEqual(r["classificacao"]["decisoes"], 3)
        banco = self.banco()
        ato = banco.con.execute("SELECT id FROM ato").fetchone()[0]
        with self.assertRaises(servico.Recusada):                                        # trecho que não está no documento: recusado
            servico.registrar_decisao_omitida(banco, ato, 1, "PROCESSO 1.111/26 PESSOA INVENTADA QUALQUER", {"processo": "1.111/26"}, REV, JUST, True)
        servico.registrar_decisao_omitida(banco, ato, 1, "PROCESSO 9.999/26 PESSOA FICTICIA OMITIDA TECNICO ADMINISTRATIVO A B",
                                          {"processo": "9.999/26", "servidor": "PESSOA FICTICIA OMITIDA", "resultado": "DEFERIDO"}, REV, JUST, True)
        nova = banco.con.execute("SELECT origem, validacao, revisor, sha256, pagina FROM decisao WHERE origem = 'MANUAL'").fetchone()
        self.assertEqual(tuple(nova)[:3], ("MANUAL", "CONFERIDO", REV))
        self.conferir_tudo(banco)
        self.assertEqual(self.painel(banco)["indicadores"]["decisoes"], 4)
        banco.fechar()
        self.executar()                                                                  # nova execução do robô: a decisão humana fica
        banco = self.banco()
        processo.classificar_pendentes(banco, refazer=True)
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM decisao WHERE origem = 'MANUAL' AND vigente = 1").fetchone()[0], 1)
        self.assertEqual(self.painel(banco)["indicadores"]["decisoes"], 4)

    def test_07_publicacao_modificadora_vira_evento_e_so_conta_depois_de_vinculada_pela_gerencia(self):
        S = self.S
        self.executar(self.pdf(date(2026, 10, 8), 18700, [S.resenha_progressao(804, "07-10-2026", "HORIZONTAL", "MAG", 40, 2, deferir=False)]))
        r = self.executar(self.pdf(date(2026, 10, 15), 18705, [S.portaria_sem_efeito(12, 804, 40)]))
        self.assertEqual((r["resultado"]["codigo"], r["classificacao"]["eventos"], r["classificacao"]["decisoes"]), (0, 1, 0))
        banco = self.banco()
        evento = banco.con.execute("SELECT * FROM evento").fetchone()
        self.assertIn(evento["estado"], ("PENDENTE_VINCULACAO", "SUGERIDO"))
        self.assertEqual((evento["tipo"], evento["ato_original_id"]), (C.SEM_EFEITO, None))
        self.assertIn("804/2026", evento["resenhas_citadas"])
        self.conferir_tudo(banco)
        self.assertEqual(self.painel(banco)["indicadores"]["sem_efeito"], 0)               # evento ainda não conferido: não conta
        original = banco.con.execute("SELECT id FROM ato WHERE numero = '804/2026'").fetchone()[0]
        with self.assertRaises(servico.Recusada):                                        # o evento não pode apontar para si mesmo
            servico.revisar_evento(banco, evento["id"], servico.VINCULAR, REV, JUST, evento["ato_id"], True)
        servico.revisar_evento(banco, evento["id"], servico.VINCULAR, REV, JUST, original, True)
        i = self.painel(banco)["indicadores"]
        self.assertEqual((i["sem_efeito"], i["decisoes"], i["indeferidos"]), (1, 2, 2))    # a decisão original não some nem duplica

    def test_09_10_11_validar_corrigir_e_rejeitar_pela_api_com_trilha_de_auditoria(self):
        self.executar(self.edicao_padrao())
        servidor = criar_servidor(self.dados, TOKEN, porta=0)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        url = f"http://127.0.0.1:{servidor.server_address[1]}"
        banco = self.banco()
        ids = [i for (i,) in banco.con.execute("SELECT d.id FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.numero = '801/2026' ORDER BY d.rowid")]
        comum = {"responsavel": REV, "justificativa": JUST, "confirma_fonte": True, "confirma_vinculo": True}
        # sem credencial ninguém revisa
        self.assertEqual(pedir(url, "/api/revisao", None, {"alvo": "decisao", "id": ids[0], "decisao": "CONFERIR", **comum})[0], 401)
        self.assertEqual(pedir(url, "/api/revisao", TOKEN, {"alvo": "decisao", "id": ids[0], "decisao": "CONFERIR", **comum})[0], 200)
        self.assertEqual(pedir(url, "/api/revisao", TOKEN, {"alvo": "decisao", "id": ids[1], "decisao": "CONFERIR", **comum,
                                                             "correcoes": {"cargo": "ANALISTA DE SISTEMAS"}})[0], 200)
        self.assertEqual(pedir(url, "/api/revisao", TOKEN, {"alvo": "decisao", "id": ids[2], "decisao": "REJEITAR", **comum})[0], 200)
        estados = dict(banco.con.execute("SELECT id, validacao FROM decisao WHERE id IN (?,?,?)", ids).fetchall())
        self.assertEqual([estados[i] for i in ids], ["CONFERIDO", "CONFERIDO", "REJEITADO"])
        self.assertEqual(banco.con.execute("SELECT cargo FROM decisao WHERE id = ?", (ids[1],)).fetchone()[0], "ANALISTA DE SISTEMAS")
        correcao = banco.con.execute("SELECT campo, valor_anterior, valor_corrigido, autor FROM correcao").fetchone()
        self.assertEqual((correcao[0], json.loads(correcao[1]), json.loads(correcao[2]), correcao[3]),
                         ("cargo", "TECNICO ADMINISTRATIVO", "ANALISTA DE SISTEMAS", f"credencial_tecnica_legada: {REV}"))
        self.assertEqual(banco.con.execute("SELECT COUNT(*) FROM auditoria WHERE alvo_tipo = 'decisao'").fetchone()[0], 3)
        # indicadores: só as conferidas; a rejeitada continua visível para a gerência, fora da contagem
        status, corpo = pedir(url, "/api/painel", TOKEN)
        painel = json.loads(corpo)
        self.assertEqual((painel["indicadores"]["decisoes"], painel["apoio"]["decisoes_rejeitadas"]), (2, 1))
        # público: nenhuma linha, nenhuma pequena contagem (<5), nenhum nome, nenhuma justificativa
        status, corpo = pedir(url, "/api/painel")
        publico = json.loads(corpo)
        self.assertEqual((status, publico["indicadores"]["decisoes"], publico["linhas"], publico["resenhas"]), (200, None, [], []))
        self.assertIsNone(publico["apoio"]["decisoes_pendentes"])
        for proibido in ("PESSOA FICTICIA", JUST, REV, "ANALISTA DE SISTEMAS"):
            self.assertNotIn(proibido, corpo.decode())
        self.assertEqual(pedir(url, "/api/auditoria")[0], 401)
        self.assertEqual(pedir(url, "/api/exportar?formato=xlsx")[0], 401)
        # exportação gerencial: planilha válida com as decisões conferidas
        status, planilha = pedir(url, "/api/exportar?formato=xlsx", TOKEN)
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(planilha)) as z:
            conteudo = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".xml"))
        self.assertIn("ANALISTA DE SISTEMAS", conteudo)

    def test_12_releitura_depois_da_homologacao_humana_nao_sobrescreve_e_abre_conflito(self):
        from observatorio.leitura import leitor
        self.executar(self.edicao_padrao())
        banco = self.banco()
        alvo = banco.con.execute("SELECT d.id, d.cargo, d.sha256 FROM decisao d JOIN ato a ON a.id = d.ato_id WHERE a.numero = '801/2026' ORDER BY d.rowid").fetchone()
        servico.revisar_decisoes(banco, [alvo["id"]], servico.CONFERIR, REV, JUST, True, True, {"cargo": "ANALISTA DE SISTEMAS"})
        self.conferir_tudo(banco)
        antes = self.painel(banco)["indicadores"]
        banco.fechar()
        # 1) nova versão do leitor, mesmo texto: nada muda para a gerência
        with mock.patch.object(leitor, "VERSAO", "9.9-teste"):
            r = self.executar()
        self.assertEqual(r["resultado"]["codigo"], 0)
        banco = self.banco()
        self.assertEqual(banco.con.execute("SELECT cargo, validacao FROM decisao WHERE id = ?", (alvo["id"],)).fetchone()[:], ("ANALISTA DE SISTEMAS", "CONFERIDO"))
        self.assertEqual(self.painel(banco)["indicadores"], antes)
        # 2) releitura com texto DIFERENTE para a mesma linha: o valor humano fica e a divergência vira conflito visível
        paginas = [dict(p) for p in banco.paginas(alvo["sha256"])]
        paginas[0]["texto"] = paginas[0]["texto"].replace("TECNICO ADMINISTRATIVO", "TECNICO DE NIVEL MEDIO", 1)
        banco.registrar_leitura(alvo["sha256"], "LIDA", "9.9-outra", paginas, "18700", "2026-10-08", None)
        resumo = processo.classificar_pendentes(banco)
        self.assertGreaterEqual(resumo["conflitos"], 1)
        self.assertEqual(banco.con.execute("SELECT cargo, validacao FROM decisao WHERE id = ?", (alvo["id"],)).fetchone()[:], ("ANALISTA DE SISTEMAS", "CONFERIDO"))
        conflito = banco.con.execute("SELECT campo, valor_vigente, valor_proposto, estado FROM conflito WHERE alvo_id = ?", (alvo["id"],)).fetchone()
        self.assertEqual((conflito[0], json.loads(conflito[1]), json.loads(conflito[2]), conflito[3]),
                         ("cargo", "ANALISTA DE SISTEMAS", "TECNICO DE NIVEL MEDIO", "ABERTO"))
        self.assertEqual(self.painel(banco)["indicadores"], antes)                       # indicadores intactos
        self.assertEqual(self.fluxo.avaliar([], {}, resumo, 0, 0)["codigo"], 3)          # e a execução sai com pendências


# ====================================================================================================================
# Parte 2 — indicadores e revisão humana (texto já lido; sem PDF)
# ====================================================================================================================
class TesteIndicadoresHomologacao(LB.Base):
    def carregar(self, marca, texto, data="2026-10-09"):
        sha = TP.carregar(self.banco, marca, data, texto)
        self.classificar()
        return sha

    def fila(self):
        """O que a gerência enxerga para revisar (escopo pendente), por processo."""
        return [l["processo"] for l in indicadores.painel(self.banco, {"escopo": "pendente"}, GER)["linhas"]]

    def test_01_uma_decisao_valida_e_contada_uma_vez(self):
        self.carregar("a", T.INDEFERIDA_MAG)
        self.conferir_tudo()
        i = indicadores.painel(self.banco, {}, GER)["indicadores"]
        self.assertEqual((i["decisoes"], i["processos"], i["resenhas"], i["indeferidos"], i["deferidos"]), (1, 1, 1, 1, 0))

    def test_02_duas_pessoas_no_mesmo_processo_sao_duas_decisoes_e_um_processo(self):
        self.carregar("a", T.HORIZONTAL_GAJ)                                # o processo 90004 aparece para duas pessoas
        self.conferir_tudo()
        i = indicadores.painel(self.banco, {}, GER)["indicadores"]
        self.assertEqual((i["decisoes"], i["processos"]), (3, 2))

    def test_03_mesmo_ato_em_duas_versoes_fisicas_conta_uma_vez(self):
        self.carregar("a", T.HORIZONTAL_GAJ)
        self.carregar("b", T.HORIZONTAL_GAJ)
        self.conferir_tudo()
        self.assertEqual(self.indicador(), 3)
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], 6)   # nada foi apagado

    def test_04_republicacao_verdadeira_e_evento_e_nao_decisao_nova(self):
        self.carregar("a", T.HORIZONTAL_GAJ, "2026-10-09")
        self.carregar("b", T.REPUBLICACAO, "2026-10-15")
        self.conferir_tudo()
        eventos = [tuple(e) for e in self.banco.con.execute("SELECT tipo, ato_original_id FROM evento")]
        self.assertEqual(eventos, [(C.REPUBLICACAO, None)])
        i = indicadores.painel(self.banco, {}, GER)["indicadores"]
        self.assertEqual(i["refeitos"], 0)                                   # só conta depois de conferida e vinculada

    def test_05_06_07_rejeitada_corrigida_e_reaberta(self):
        self.carregar("a", T.HORIZONTAL_GAJ)
        d = self.decisoes()
        servico.revisar_decisoes(self.banco, [d[0]["id"]], servico.REJEITAR, REV, JUST)
        servico.revisar_decisoes(self.banco, [d[1]["id"]], servico.CONFERIR, REV, JUST, True, True, {"resultado": "INDEFERIDO"})
        i = indicadores.painel(self.banco, {}, GER)
        self.assertEqual((i["indicadores"]["decisoes"], i["indicadores"]["indeferidos"], i["apoio"]["decisoes_rejeitadas"]), (1, 1, 1))
        # a rejeitada não some: continua consultável pela gerência
        self.assertEqual(self.banco.con.execute("SELECT validacao, revisor FROM decisao WHERE id = ?", (d[0]["id"],)).fetchone()[:], ("REJEITADO", REV))
        servico.revisar_decisoes(self.banco, [d[0]["id"], d[1]["id"]], servico.REABRIR, REV, JUST)
        i = indicadores.painel(self.banco, {}, GER)
        self.assertEqual((i["indicadores"]["decisoes"], i["apoio"]["decisoes_pendentes"]), (0, 3))
        self.assertEqual(self.banco.con.execute("SELECT resultado FROM decisao WHERE id = ?", (d[1]["id"],)).fetchone()[0], "INDEFERIDO")   # a correção fica
        self.assertEqual(len(self.fila()), 3)
        acoes = [a for (a,) in self.banco.con.execute("SELECT acao FROM auditoria WHERE alvo_tipo = 'decisao' ORDER BY id")]
        self.assertEqual(acoes.count("REABRIR"), 2)

    def test_08_identidade_ambigua_fica_fora_da_contagem_e_dentro_da_fila_com_conflito(self):
        # duas versões do mesmo ato; na segunda, uma linha SEM processo e SEM matrícula não pode ser casada com certeza
        self.carregar("a", T.HORIZONTAL_GAJ)
        outra = T.HORIZONTAL_GAJ.replace("SAD-PSE-2026/90003 900003-8 PESSOA FICTICIA TRES", "SAD-PSE-2026/90004 900009-9 PESSOA FICTICIA NOVE")
        self.carregar("b", outra)
        ambiguos = self.banco.con.execute("SELECT origem, estado FROM conflito WHERE alvo_tipo = 'decisao'").fetchall()
        self.assertTrue(ambiguos)
        self.assertTrue(all(c["estado"] == "ABERTO" for c in ambiguos))
        fora = self.banco.con.execute("SELECT COUNT(*) FROM decisao WHERE vigente = 0 AND representada_por IS NULL").fetchone()[0]
        self.assertEqual(fora, len(ambiguos))                                # cada decisão fora da contagem tem o seu conflito
        # visível e resolúvel pela gerência
        abertos = self.banco.conflitos()
        self.assertEqual(len(abertos), len(ambiguos))
        servico.resolver_conflito(self.banco, abertos[0]["id"], "ACEITAR", REV, JUST, True)
        self.assertEqual(len(self.banco.conflitos()), len(ambiguos) - 1)

    def test_09_decisao_sem_processo_aparece_na_fila_e_conta_como_decisao_nao_como_processo(self):
        texto = T.HORIZONTAL_GAJ.replace("SAD-PSE-2026/90004 900005-4", "900005-4")
        self.carregar("a", texto)
        d = self.decisoes()
        self.assertEqual([x["processo"] for x in d], ["SAD-PSE-2026/90003", "SAD-PSE-2026/90004", None])
        self.assertEqual(len(self.fila()), 3)                                # está na fila da gerência
        self.conferir_tudo()
        i = indicadores.painel(self.banco, {}, GER)["indicadores"]
        self.assertEqual((i["decisoes"], i["processos"]), (3, 2))            # o processo ausente não é inventado nem contado

    def test_10_grupo_nao_homologado_fica_sem_grupo_no_painel_e_na_exportacao(self):
        self.carregar("a", T.VERTICAL_SEM_GEDIV)                             # "Grupo TEC. ADM."
        self.conferir_tudo()
        p = indicadores.painel(self.banco, {}, GER)
        self.assertEqual([l["grupo"] for l in p["linhas"]], [None])
        self.assertEqual(indicadores.painel(self.banco, {"grupo": "AST"}, GER)["indicadores"]["decisoes"], 0)
        self.assertEqual(p["indicadores"]["decisoes"], 1)                    # conta no total; só não é atribuída a um grupo

    def test_11_conflito_apos_releitura_fica_visivel_ate_a_gerencia_decidir(self):
        sha = self.carregar("a", T.HORIZONTAL_GAJ)
        d = self.decisoes()[0]
        servico.revisar_decisoes(self.banco, [d["id"]], servico.CONFERIR, REV, JUST, True, True, {"cargo": "AGENTE PENITENCIARIO"})
        self.ler(sha, LB.pag(1, T.HORIZONTAL_GAJ.replace("PESSOA FICTICIA TRES POLICIAL PENAL", "PESSOA FICTICIA TRES INSPETOR PENAL")), versao="v2")
        self.classificar()
        self.assertEqual(self.banco.con.execute("SELECT cargo FROM decisao WHERE id = ?", (d["id"],)).fetchone()[0], "AGENTE PENITENCIARIO")
        aberto = self.banco.conflitos(alvo_tipo="decisao", alvo_ids=[d["id"]])
        self.assertEqual([(c["campo"], json.loads(c["valor_proposto"])) for c in aberto], [("cargo", "INSPETOR PENAL")])
        self.classificar(refazer=True)                                        # repetir não multiplica o conflito
        self.assertEqual(len(self.banco.conflitos(alvo_tipo="decisao", alvo_ids=[d["id"]])), 1)
        servico.resolver_conflito(self.banco, aberto[0]["id"], "MANTER", REV, JUST, True)
        self.assertEqual(self.banco.conflitos(alvo_tipo="decisao", alvo_ids=[d["id"]]), [])
        self.assertEqual(self.banco.con.execute("SELECT cargo FROM decisao WHERE id = ?", (d["id"],)).fetchone()[0], "AGENTE PENITENCIARIO")

    def test_12_evento_que_modifica_ato_anterior_so_conta_com_vinculo_confirmado(self):
        self.carregar("a", T.INDEFERIDA_MAG, "2026-10-09")
        self.carregar("b", T.PORTARIA_SEM_EFEITO, "2026-10-15")
        self.conferir_tudo()
        evento = self.banco.con.execute("SELECT id FROM evento").fetchone()[0]
        self.assertEqual(self.indicador("sem_efeito"), 0)
        with self.assertRaises(servico.Recusada):                            # sem declarar a consulta aos documentos, não se vincula
            servico.revisar_evento(self.banco, evento, servico.VINCULAR, REV, JUST, self.ato("904/2026")["id"], False)
        servico.revisar_evento(self.banco, evento, servico.VINCULAR, REV, JUST, self.ato("904/2026")["id"], True)
        self.assertEqual(self.indicador("sem_efeito"), 1)

    def test_13_historico_de_auditoria_guarda_quem_o_que_antes_e_depois(self):
        self.carregar("a", T.HORIZONTAL_GAJ)
        d = self.decisoes()[0]
        servico.revisar_decisoes(self.banco, [d["id"]], servico.CONFERIR, REV, JUST, True, True, {"servidor": "PESSOA FICTICIA TRES DA SILVA"})
        servico.corrigir_ato(self.banco, d["ato_id"], {"grupo": "MAG"}, REV, JUST, True)
        linhas = self.banco.con.execute("SELECT autor, acao, alvo_tipo, anterior, posterior, justificativa FROM auditoria ORDER BY id").fetchall()
        self.assertEqual([(l["acao"], l["alvo_tipo"]) for l in linhas], [("CONFERIR", "decisao"), ("CORRIGIR", "ato")])
        self.assertTrue(all(l["autor"] == REV and l["justificativa"] == JUST for l in linhas))
        self.assertIn("GAJ", linhas[1]["anterior"])
        self.assertIn("MAG", linhas[1]["posterior"])
        # A trilha só cresce: nenhum ponto do programa altera ou apaga um registro de auditoria ou de correção.
        # (O banco não tem trava contra alteração por fora do programa — risco residual registrado em docs/16.)
        import re
        fontes = "\n".join(c.read_text(encoding="utf-8") for c in Path(servico.__file__).parents[1].rglob("*.py"))
        self.assertEqual(re.findall(r"(?:UPDATE|DELETE\s+FROM)\s+(?:auditoria|correcao|tentativa_leitura)\b", fontes, re.I), [])

    def test_14_15_exportacao_gerencial_e_projecao_publica(self):
        from observatorio.painel import exportacao
        self.carregar("a", T.HORIZONTAL_GAJ)
        d = self.decisoes()[0]
        servico.revisar_decisoes(self.banco, [d["id"]], servico.CONFERIR, REV, "justificativa interna sigilosa", True, True)
        gerencia = indicadores.painel(self.banco, {}, GER)
        linhas = exportacao.linhas_decisoes(gerencia)
        self.assertEqual(len(linhas), 2)                                      # cabeçalho + a decisão conferida
        self.assertIn("PESSOA FICTICIA TRES", " ".join(map(str, linhas[1])))
        publico = indicadores.painel(self.banco, {}, PUB)
        texto = json.dumps(publico, ensure_ascii=False)
        self.assertEqual(publico["indicadores"]["decisoes"], 1)
        for proibido in ("PESSOA FICTICIA", "900003", "justificativa interna", REV, "SAD-PSE-2026/90003"):
            self.assertNotIn(proibido, texto)
        self.assertEqual(json.dumps(indicadores.outras_publicacoes(self.banco, PUB), ensure_ascii=False).count("PESSOA FICTICIA"), 0)

    def test_nenhuma_decisao_some_da_fila_por_estar_fora_dos_indicadores(self):
        """Invariante: toda decisão gravada está em exatamente uma destas situações — contada (conferida e vigente),
        na fila (pendente e vigente), rejeitada, representada por outra versão do mesmo ato, ou com conflito aberto."""
        self.carregar("a", "\n".join([T.ANOTACAO, T.HORIZONTAL_GAJ, T.VERTICAL_SEM_GEDIV, T.INDEFERIDA_MAG]))
        self.carregar("b", T.HORIZONTAL_GAJ.replace("SAD-PSE-2026/90003 900003-8 PESSOA FICTICIA TRES", "SAD-PSE-2026/90004 900009-9 PESSOA FICTICIA NOVE"))
        d = self.decisoes(vigente=1)
        servico.revisar_decisoes(self.banco, [d[0]["id"]], servico.REJEITAR, REV, JUST)
        servico.revisar_decisoes(self.banco, [d[1]["id"]], servico.CONFERIR, REV, JUST, True, True)
        com_conflito = {c["alvo_id"] for c in self.banco.conflitos(alvo_tipo="decisao")}
        sem_destino = [x["id"] for x in self.decisoes()
                       if not (x["vigente"] == 1 or x["representada_por"] is not None or x["id"] in com_conflito)]
        self.assertEqual(sem_destino, [])
        p = indicadores.painel(self.banco, {"escopo": "pendente"}, GER)
        vigentes_pendentes = sum(1 for x in self.decisoes(vigente=1) if x["validacao"] == "PENDENTE")
        self.assertEqual(p["apoio"]["decisoes_pendentes"], vigentes_pendentes)
        self.assertEqual(len(p["linhas"]), vigentes_pendentes)


if __name__ == "__main__":
    unittest.main()
