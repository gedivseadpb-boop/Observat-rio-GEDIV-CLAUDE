"""Validador do corpus: só aprova quando o contrato inteiro foi avaliado e confere (auditorias de 14/11/2026).

Antes: caso sem esperado era pulado, PDF ausente ficava fora do total, um esperado vazio "passava", extras e
duplicatas não contavam, o pareamento caía para a posição e o código de saída do subprocesso era ignorado.
Tudo SINTÉTICO: PDFs falsos (só bytes para o SHA-256), leitura simulada, pessoas fictícias.
"""
import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.operacao import corpus, saida
from observatorio.operacao.__main__ import main


def linha(n, **k):
    return {"processo": f"SAD-PSE-2026/9{n:04d}", "matricula": f"90{n:05d}", "servidor": f"PESSOA FICTICIA {n}", "cargo": "PROFESSOR",
            "evolucao_anterior": "A", "evolucao_posterior": "B", **k}


class Base(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self.pdfs = self.raiz / "pdfs"
        self.pdfs.mkdir()
        self.casos, self.privado, self.extraido = [], {}, {}
        self.codigo_da_leitura, self.chamadas = saida.SUCESSO, 0

    def caso(self, conjunto, dia, resenha, esperadas, extraidas=None, com_pdf=True):
        conteudo = f"%PDF-sintetico {dia} {resenha}".encode()
        sha = hashlib.sha256(conteudo).hexdigest()
        if com_pdf:
            (self.pdfs / f"diario-{dia}.pdf").write_bytes(conteudo)
        data = f"2026-11-{dia:02d}"
        self.casos.append({"conjunto": conjunto, "data": data, "resenha": resenha, "sha256": sha, "url": f"https://exemplo.invalid/{dia}.pdf"})
        if esperadas is not None:
            self.privado.setdefault(conjunto, {})[f"{dia:02d}-11|{resenha}"] = esperadas
        self.extraido.setdefault(sha, {})[resenha] = esperadas if extraidas is None else extraidas

    def rodar(self, arquivo, caso, dados):
        """Simula `validar-real`: grava o banco com as linhas 'extraídas' e devolve o código de saída configurado."""
        self.chamadas += 1
        if self.codigo_da_leitura not in (saida.SUCESSO, saida.CONCLUIDO_COM_PENDENCIAS):
            return self.codigo_da_leitura
        dados.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(dados / "observatorio.sqlite3")) as con:
            con.execute("CREATE TABLE ato (id TEXT, numero TEXT)")
            con.execute("CREATE TABLE decisao (id INTEGER PRIMARY KEY, ato_id TEXT, processo, matricula, servidor, cargo, detalhe)")
            for resenha, linhas in self.extraido[caso["sha256"]].items():
                con.execute("INSERT INTO ato VALUES (?, ?)", (resenha, resenha))
                for l in linhas or []:
                    con.execute("INSERT INTO decisao (ato_id, processo, matricula, servidor, cargo, detalhe) VALUES (?, ?, ?, ?, ?, ?)",
                                (resenha, l["processo"], l["matricula"], l["servidor"], l["cargo"],
                                 json.dumps({"classe_anterior": l["evolucao_anterior"], "classe_posterior": l["evolucao_posterior"]})))
            con.commit()
        return self.codigo_da_leitura

    def executar(self, privado="padrao"):
        manifesto = self.raiz / "manifesto.json"
        manifesto.write_text(json.dumps({"casos": self.casos}), encoding="utf-8")
        arquivo = self.raiz / "esperado-privado.json"
        if privado == "padrao":
            arquivo.write_text(json.dumps(self.privado), encoding="utf-8")
        elif privado is not None:
            arquivo.write_text(privado, encoding="utf-8")
        return corpus.executar(self.pdfs, arquivo, manifesto, rodar=self.rodar)

    def unico(self, r):
        (conjunto,) = r["conjuntos"].values()
        return conjunto["casos"]


class TesteContrato(Base):
    def test_corpus_legitimo_integralmente_correto_e_aprovado(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1), linha(2), linha(3)])
        self.caso("validacao_cega", 11, "584/2026", [linha(4)])
        r = self.executar()
        self.assertEqual((r["situacao"], r["aprovado"], r["codigo_de_saida"]), (corpus.APROVADO, True, saida.SUCESSO))
        self.assertEqual({c: d["por_situacao"] for c, d in r["conjuntos"].items()},
                         {"desenvolvimento": {"CONFERE": 1}, "validacao_cega": {"CONFERE": 1}})
        self.assertEqual(r["conjuntos"]["desenvolvimento"]["total"]["precisao_todos_os_campos"], 100.0)

    def test_registros_fora_de_ordem_conferem(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1), linha(2), linha(3)], [linha(3), linha(1), linha(2)])
        self.assertEqual(self.executar()["situacao"], corpus.APROVADO)

    def test_conjunto_vazio_nunca_e_aprovado(self):
        self.caso("desenvolvimento", 7, "579/2026", None)
        for privado in ("{}", '{"desenvolvimento": {}}'):
            with self.subTest(privado=privado):
                r = self.executar(privado)
                self.assertEqual((r["situacao"], r["codigo_de_saida"]), (corpus.INDISPONIVEL, saida.NAO_EXECUTADO))
                self.assertEqual(self.unico(r)[0]["situacao"], corpus.ESPERADO_AUSENTE)
        r = self.executar('{"desenvolvimento": {"07-11|579/2026": []}}')
        self.assertEqual((r["situacao"], self.unico(r)[0]["situacao"]), (corpus.INDISPONIVEL, corpus.ESPERADO_VAZIO))

    def test_manifesto_sem_casos_e_esperado_privado_ausente_ou_ilegivel(self):
        self.assertEqual(self.executar()["situacao"], corpus.INDISPONIVEL)                      # manifesto vazio
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        for privado in (None, "isto não é JSON", "[]"):
            with self.subTest(privado=privado):
                self.assertEqual(self.executar(privado)["situacao"], corpus.INDISPONIVEL)
        self.assertEqual(self.chamadas, 0)                                                    # nada foi "avaliado"

    def test_pdf_esperado_ausente_nao_some_da_avaliacao(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        self.caso("desenvolvimento", 11, "584/2026", [linha(2)], com_pdf=False)
        r = self.executar()
        self.assertEqual((r["situacao"], r["aprovado"], r["codigo_de_saida"]), (corpus.PARCIAL, False, saida.FALHA))
        self.assertEqual(self.unico(r)[1]["situacao"], corpus.PDF_AUSENTE)
        (pasta_vazia := self.raiz / "vazia").mkdir()
        self.pdfs = pasta_vazia
        self.assertEqual(self.executar()["situacao"], corpus.INDISPONIVEL)                    # nenhum PDF: nada avaliado
        self.pdfs = self.raiz / "nao-existe"
        self.assertEqual(self.executar()["situacao"], corpus.INDISPONIVEL)

    def test_esperado_para_caso_fora_do_manifesto_impede_aprovacao(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        self.privado["desenvolvimento"]["30-11|999/2026"] = [linha(9)]
        r = self.executar()
        self.assertEqual(r["situacao"], corpus.PARCIAL)
        self.assertIn(corpus.CASO_NAO_CONTRATADO, r["conjuntos"]["desenvolvimento"]["por_situacao"])


class TesteComparacao(Base):
    def avaliar(self, esperadas, extraidas):
        self.caso("desenvolvimento", 7, "579/2026", esperadas, extraidas)
        r = self.executar()
        return r, self.unico(r)[0]

    def test_um_caso_esperado_nao_encontrado(self):
        r, c = self.avaliar([linha(1), linha(2)], [linha(1)])
        self.assertEqual((r["situacao"], r["codigo_de_saida"], c["situacao"], c["ausentes"]), (corpus.REPROVADO, saida.FALHA, corpus.DIVERGENTE, 1))

    def test_registro_adicional(self):
        r, c = self.avaliar([linha(1)], [linha(1), linha(2)])
        self.assertEqual((r["situacao"], c["extras"], c["linhas_inteiramente_corretas"]), (corpus.REPROVADO, 1, 1))

    def test_registro_extraido_sem_matricula_conta_como_extra(self):
        r, c = self.avaliar([linha(1)], [linha(1), linha(2, matricula=None)])
        self.assertEqual((r["situacao"], c["extras"]), (corpus.REPROVADO, 1))

    def test_registro_duplicado(self):
        r, c = self.avaliar([linha(1), linha(2)], [linha(1), linha(2), linha(2)])
        self.assertEqual((r["situacao"], c["duplicadas"], c["linhas_pareadas"]), (corpus.REPROVADO, 1, 1))     # a duplicada não vale

    def test_correspondencia_ambigua(self):
        for esperadas in ([linha(1), linha(2, matricula=linha(1)["matricula"])], [linha(1, matricula=None)]):
            with self.subTest(esperadas=len(esperadas)):
                self.setUp()
                r, c = self.avaliar(esperadas, [linha(1)])
                self.assertEqual(r["situacao"], corpus.REPROVADO)
                self.assertEqual(c["ambiguas"], len(esperadas))

    def test_sem_pareamento_por_posicao(self):
        # Antes: sem matrícula correspondente, a linha esperada era comparada com a da mesma posição.
        r, c = self.avaliar([linha(1)], [linha(2, processo=linha(1)["processo"])])
        self.assertEqual((c["ausentes"], c["extras"], c["linhas_pareadas"]), (1, 1, 0))

    def test_divergencia_de_um_campo(self):
        r, c = self.avaliar([linha(1), linha(2)], [linha(1), linha(2, evolucao_posterior="E")])
        self.assertEqual((r["situacao"], c["campos_divergentes"], c["linhas_inteiramente_corretas"]), (corpus.REPROVADO, 1, 1))
        self.assertEqual(c["por_campo"]["evolucao_posterior"], {"acertos": 1, "total": 2})

    def test_maiusculas_e_acentos_nao_sao_divergencia(self):
        r, _ = self.avaliar([linha(1, servidor="PESSOA FICTÍCIA UM")], [linha(1, servidor="Pessoa Ficticia Um")])
        self.assertEqual(r["situacao"], corpus.APROVADO)


class TesteFalhaDeExecucao(Base):
    def test_subprocesso_com_codigo_de_falha(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        for codigo in (saida.FALHA, saida.NAO_EXECUTADO, -9):
            with self.subTest(codigo=codigo):
                self.codigo_da_leitura = codigo
                r = self.executar()
                self.assertEqual((r["situacao"], r["codigo_de_saida"]), (corpus.REPROVADO, saida.FALHA))
                self.assertEqual(self.unico(r)[0]["situacao"], corpus.FALHA_EXECUCAO)

    def test_leitura_com_pendencias_ainda_e_avaliada(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        self.codigo_da_leitura = saida.CONCLUIDO_COM_PENDENCIAS          # PDFs reais costumam ter pendências de página
        self.assertEqual(self.executar()["situacao"], corpus.APROVADO)

    def test_sucesso_sem_banco_nao_vira_zero_linhas(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])
        self.rodar = lambda arquivo, caso, dados: saida.SUCESSO             # "sucesso" sem produzir nada
        r = self.executar()
        self.assertEqual((r["situacao"], self.unico(r)[0]["situacao"]), (corpus.REPROVADO, corpus.FALHA_EXECUCAO))

    def test_programa_que_nao_inicia(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)])

        def nao_inicia(arquivo, caso, dados):
            raise OSError("executável ausente")
        self.rodar = nao_inicia
        self.assertEqual(self.executar()["situacao"], corpus.REPROVADO)


class TesteCasoDeEvento(Base):
    """Caso cujo esperado é um evento público (ex.: "tornado sem efeito" de ato anterior à base): avaliado pelo evento
    extraído na página — antes era pulado em silêncio por não ter linhas no arquivo privado."""
    ESPERADO = {"evento": "TORNADO_SEM_EFEITO", "subcategoria": "TS-05", "publicacoes_citadas": ["1999-07-28"], "resenhas_citadas": []}

    def caso_evento(self, eventos):
        conteudo = b"%PDF-sintetico evento"
        sha = hashlib.sha256(conteudo).hexdigest()
        (self.pdfs / "diario-10.pdf").write_bytes(conteudo)
        self.casos.append({"conjunto": "desenvolvimento", "data": "2026-11-10", "resenha": "Portaria 8/2026", "sha256": sha,
                           "url": "https://exemplo.invalid/10.pdf", "pagina_pdf": 2, "esperado_publico": self.ESPERADO})

        def rodar(arquivo, caso, dados):
            self.chamadas += 1
            dados.mkdir(parents=True, exist_ok=True)
            with contextlib.closing(sqlite3.connect(dados / "observatorio.sqlite3")) as con:
                con.execute("CREATE TABLE ato (id TEXT, numero TEXT, subcategoria TEXT)")
                con.execute("CREATE TABLE decisao (id INTEGER PRIMARY KEY, ato_id TEXT, processo, matricula, servidor, cargo, detalhe)")
                con.execute("CREATE TABLE evento (tipo TEXT, pagina INTEGER, publicacoes_citadas TEXT, resenhas_citadas TEXT, ato_id TEXT)")
                con.execute("INSERT INTO ato VALUES ('p8', '8/2026', 'TS-05')")
                for e in eventos:
                    con.execute("INSERT INTO evento VALUES (?, ?, ?, ?, 'p8')", (e.get("tipo", "TORNADO_SEM_EFEITO"), e.get("pagina", 2),
                                json.dumps(e.get("publicacoes_citadas", ["1999-07-28"])), "[]"))
                con.commit()
            return saida.SUCESSO
        self.rodar = rodar

    def test_evento_esperado_confere_sem_arquivo_privado_de_linhas(self):
        self.caso_evento([{}])
        r = self.executar("{}")
        self.assertEqual((r["situacao"], self.unico(r)[0]["situacao"]), (corpus.APROVADO, corpus.CONFERE))

    def test_evento_divergente_ausente_ou_duplicado(self):
        for eventos, nome in (([{"publicacoes_citadas": ["1999-07-29"]}], "campo"), ([{"pagina": 3}], "ausente"),
                              ([{"tipo": "RETIFICACAO"}], "outro tipo"), ([{}, {}], "duplicado")):
            with self.subTest(nome):
                self.setUp()
                self.caso_evento(eventos)
                r = self.executar("{}")
                self.assertEqual((r["situacao"], self.unico(r)[0]["situacao"]), (corpus.REPROVADO, corpus.DIVERGENTE))


class TesteLinhaDeComando(Base):
    def test_codigo_de_saida_e_relatorio_sem_dados_pessoais(self):
        self.caso("desenvolvimento", 7, "579/2026", [linha(1)], [linha(1, cargo="OUTRO")])
        manifesto = self.raiz / "manifesto.json"
        manifesto.write_text(json.dumps({"casos": self.casos}), encoding="utf-8")
        privado = self.raiz / "esperado.json"
        privado.write_text(json.dumps(self.privado), encoding="utf-8")
        relatorio = self.raiz / "relatorio.json"
        with mock.patch.object(corpus, "MANIFESTO", manifesto), \
                mock.patch.object(corpus, "_rodar_validar_real", self.rodar), \
                mock.patch.object(corpus.executar, "__defaults__", (manifesto, self.rodar)), \
                contextlib.redirect_stdout(io.StringIO()):
            codigo = main(["corpus", "--pdfs", str(self.pdfs), "--esperado-privado", str(privado), "--saida", str(relatorio)])
            sem_privado = main(["corpus", "--pdfs", str(self.pdfs), "--esperado-privado", str(self.raiz / "nao-existe.json")])
        self.assertEqual((codigo, sem_privado), (saida.FALHA, saida.NAO_EXECUTADO))
        texto = relatorio.read_text(encoding="utf-8")
        for valor in ("PESSOA FICTICIA", "9000001", "SAD-PSE-2026/9", "OUTRO", "PROFESSOR"):
            self.assertNotIn(valor, texto)


if __name__ == "__main__":
    unittest.main()
