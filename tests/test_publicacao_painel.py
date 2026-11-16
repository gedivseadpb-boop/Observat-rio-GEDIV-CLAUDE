"""Contratos públicos usando exclusivamente bancos e pessoas fictícias."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C
from observatorio.painel.publicacao import main, metrica, projetar


class TestePublicacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.seq = 0

    def banco(self, grupos, *, estado="PENDENTE", edicao="99991", mes="2026-03", versao=None,
              conflito=False):
        self.seq += 1
        p = self.raiz / f"fonte{self.seq}.sqlite3"
        with closing(sqlite3.connect(p)) as con, con:
            con.executescript('''
                CREATE TABLE leitura(sha256 TEXT,numero_edicao TEXT,data_edicao TEXT,situacao TEXT,
                                     revisao TEXT,paginas INTEGER);
                CREATE TABLE classificacao(sha256 TEXT,gerencia TEXT,versao_regras TEXT,revisao_leitura TEXT);
                CREATE TABLE ato(id TEXT,chave_logica TEXT,sha256 TEXT,gerencia TEXT,eixo TEXT,
                    modalidade TEXT,grupo TEXT,subcategoria TEXT,natureza TEXT,data_publicacao TEXT);
                CREATE TABLE decisao(id TEXT,ato_id TEXT,sha256 TEXT,chave_logica TEXT,validacao TEXT,vigente INTEGER,
                    servidor TEXT,matricula TEXT,processo TEXT,revisor TEXT);
                CREATE TABLE conflito(estado TEXT,alvo_tipo TEXT,alvo_id TEXT);
            ''')
            con.execute("INSERT INTO leitura VALUES('pdf-ficticio',?,?, 'LIDA','r1',12)", (edicao, mes + "-12"))
            con.execute("INSERT INTO classificacao VALUES('pdf-ficticio','GEDIV',?,'r1')", (versao or C.VERSAO_REGRAS,))
            for indice, (grupo, qtd) in enumerate(grupos):
                aid = f"ato-ficticio-{indice}"
                eixo = C.TEMPO if grupo.startswith("TS-") else C.PROGRESSAO
                con.execute("INSERT INTO ato VALUES(?,?,'pdf-ficticio','GEDIV',?,?,?,?, 'ORIGINAL',?)",
                            (aid, aid, eixo, "HORIZONTAL" if eixo == C.PROGRESSAO else None,
                             grupo if eixo == C.PROGRESSAO else None, grupo if eixo == C.TEMPO else None, mes + "-12"))
                for j in range(qtd):
                    did = f"decisao-ficticia-{indice}-{j}"
                    con.execute("INSERT INTO decisao VALUES(?,?,'pdf-ficticio','chave-logica-repetida',?,1,?,?,?,?)",
                                (did, aid, estado, "PESSOA FICTICIA SIGILOSA", str(99880000 + indice * 100 + j), "FIC-PSE-2099/123456", "REVISOR FICTICIO"))
                    if conflito and indice == 0 and j == 0:
                        con.execute("INSERT INTO conflito VALUES('ABERTO','decisao',?)", (did,))
        return p

    def test_leitura_fecha_as_conexoes_sem_depender_do_coletor(self):
        p = self.banco([("MAG", 6)])
        conectar = sqlite3.connect
        abertas = []
        def rastrear(*args, **kwargs):
            con = conectar(*args, **kwargs)
            abertas.append(con)
            return con
        with patch("observatorio.painel.publicacao.sqlite3.connect", side_effect=rastrear):
            projetar([p])
        self.assertTrue(abertas)
        for con in abertas:
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")

    def test_faixas_nao_sao_contagens_exatas(self):
        self.assertEqual(metrica(0)["valor"], 0)
        for valor in [1, 4, 5, 9, 10, 213]:
            m = metrica(valor)
            self.assertIsNone(m["valor"])
            self.assertLessEqual(m["minimo"], valor)
            self.assertGreaterEqual(m["maximo"], valor)
            self.assertEqual(m["maximo"] - m["minimo"], 4)
        self.assertEqual(metrica(1)["rotulo"], "0–4")

    def test_allowlist_e_supressao_do_recorte_pequeno(self):
        p = self.banco([("MAG", 7), ("AST", 4)])
        d = projetar([p])
        self.assertEqual(len(d["celulas"]), 1)
        self.assertEqual(d["celulas"][0]["grupo"], "MAG")
        self.assertEqual(d["celulas"][0]["decisoes"]["rotulo"], "5–9")
        self.assertEqual(d["celulas"][0]["atos"]["rotulo"], "0–4")
        self.assertEqual(d["resumo"]["provisorios"]["rotulo"], "10–14")
        self.assertEqual(d["resumo"]["conferidos"]["valor"], 0)
        texto = json.dumps(d, ensure_ascii=False)
        for proibido in ["PESSOA FICTICIA", "99887766", "FIC-PSE", "REVISOR FICTICIO", "pdf-ficticio", "ato-ficticio", "decisao-ficticia", str(p)]:
            self.assertNotIn(proibido, texto)
        self.assertNotIn("suprimidas", texto)
        self.assertEqual(len(d["catalogo"]["grupos"]), 16)
        self.assertEqual(len(d["catalogo"]["subcategorias"]), 7)

    def test_deduplica_edicao_nao_soma_bancos(self):
        antigo = self.banco([("MAG", 6)])
        novo = self.banco([("MAG", 11)])
        d = projetar([antigo, novo])
        self.assertEqual(d["cobertura"]["edicoes"], 1)
        self.assertEqual(d["cobertura"]["paginas"], 12)
        self.assertEqual(d["resumo"]["provisorios"]["rotulo"], "10–14")
        # Chave lógica repetida dentro do banco não elimina decisões vigentes distintas.
        self.assertEqual(d["celulas"][0]["decisoes"]["rotulo"], "10–14")

    def test_fonte_revisada_prevalece_e_fontes_permanecem_intactas(self):
        revisada = self.banco([("MAG", 6)], estado="CONFERIDO")
        bruta = self.banco([("MAG", 11)])
        hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [revisada, bruta]}
        d = projetar([revisada, bruta])
        self.assertEqual(d["resumo"]["conferidos"]["rotulo"], "5–9")
        self.assertEqual(d["resumo"]["provisorios"]["valor"], 0)
        self.assertEqual(d["celulas"][0]["situacao"], "conferido")
        self.assertEqual(hashes, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes})

    def test_conflito_e_classificacao_desatualizada_nao_viram_conferidos(self):
        com_conflito = self.banco([("MAG", 5)], estado="CONFERIDO", conflito=True)
        d = projetar([com_conflito])
        self.assertEqual(d["celulas"], [])
        self.assertEqual(d["resumo"]["conferidos"]["rotulo"], "0–4")
        velha = self.banco([("MAG", 8)], versao="regra-incompativel")
        d = projetar([velha])
        self.assertEqual(d["resumo"]["conferidos"]["valor"], 0)
        self.assertEqual(d["resumo"]["provisorios"]["valor"], 0)

    def test_mes_grupo_assunto_sem_criar_eixo(self):
        a = self.banco([("MAG", 5)], edicao="99991", mes="2026-03")
        b = self.banco([("TS-01", 6)], edicao="99992", mes="2026-04")
        d = projetar([a, b])
        self.assertEqual({x["periodo"] for x in d["celulas"]}, {"2026-03", "2026-04"})
        self.assertEqual({x["eixo"] for x in d["celulas"]}, {C.PROGRESSAO, C.TEMPO})
        self.assertEqual(d["celulas"][1]["subcategoria"], "TS-01")
        self.assertIsNone(d["celulas"][1]["grupo"])

    def test_nenhuma_fonte_sem_inventar_dados(self):
        d = projetar([])
        self.assertEqual(d["cobertura"]["edicoes"], 0)
        self.assertIsNone(d["cobertura"]["primeira_publicacao"])
        self.assertFalse(d["cobertura"]["historico_completo"])
        self.assertEqual(d["celulas"], [])

    def test_cli_cobertura_nao_repasse_livre_nem_sobrescreve_banco(self):
        p = self.banco([("MAG", 6)])
        c = self.raiz / "cobertura.json"
        c.write_text(json.dumps({"ausencia_tecnica_edicoes": 5, "inconclusivas": 1, "observacao": "SEGREDO FICTICIO"}))
        saida = self.raiz / "snapshot.json"
        self.assertEqual(main(["--banco", str(p), "--cobertura", str(c), "--saida", str(saida)]), 0)
        d = json.loads(saida.read_text())
        self.assertEqual(d["cobertura"]["inconclusivas"], 1)
        self.assertNotIn("SEGREDO", saida.read_text())
        with self.assertRaises(SystemExit):
            main(["--banco", str(p), "--saida", str(p)])

    def test_varias_decisoes_da_mesma_pessoa_nao_liberam_celula(self):
        p = self.banco([("MAG", 8)])
        with closing(sqlite3.connect(p)) as con, con:
            con.execute("UPDATE decisao SET matricula=\"99887766\"")
        d = projetar([p])
        self.assertEqual(d["celulas"], [])

    def test_resumo_tempo_publicavel_sem_expor_subcategorias_pequenas(self):
        p = self.banco([("TS-01", 3), ("TS-03", 3)])
        d = projetar([p])
        self.assertEqual(d["celulas"], [])
        resumo = d["resumo_eixos"][C.TEMPO]
        self.assertEqual(resumo["provisorios"]["rotulo"], "5–9")
        self.assertEqual(resumo["conferidos"]["valor"], 0)
        self.assertEqual(set(resumo), {"conferidos", "provisorios", "atos", "publicacoes_pendentes"})
        self.assertNotIn(C.PROGRESSAO, d["resumo_eixos"])

    def test_resumo_eixo_poucas_pessoas_nao_e_divulgado(self):
        p = self.banco([("TS-01", 4)])
        d = projetar([p])
        self.assertNotIn(C.TEMPO, d["resumo_eixos"])
        # Muitas decisões de uma única pessoa também não liberam o total do eixo.
        p = self.banco([("TS-01", 8)])
        with closing(sqlite3.connect(p)) as con, con:
            con.execute("UPDATE decisao SET matricula='99887766'")
        self.assertNotIn(C.TEMPO, projetar([p])["resumo_eixos"])

    def test_materias_excluidas_nunca_entram_nos_indicadores(self):
        p = self.banco([("MAG", 6), ("AST", 9)])
        with closing(sqlite3.connect(p)) as con, con:
            con.execute("UPDATE ato SET eixo='LICENCA_SAUDE' WHERE grupo='AST'")
        d = projetar([p])
        self.assertEqual(d["resumo"]["provisorios"]["rotulo"], "5–9")
        self.assertEqual(len(d["celulas"]), 1)


if __name__ == "__main__":
    unittest.main()
