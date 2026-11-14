"""Integração 05.1: a coleta verificável (Etapa 05) entrega à leitura e à classificação (Etapas 03–04).

Servidor HTTP local e Diários SINTÉTICOS (pessoas e processos fictícios); nenhum acesso à internet.
"""
from __future__ import annotations

import hashlib
import importlib.util
import unittest
from datetime import date

from observatorio.gerencias.gediv import processo
from observatorio.leitura import leitor
from observatorio.nucleo import banco as B
from observatorio.revisao import servico
from tests.apoio import pdf_sem_paginas
from tests.test_aquisicao import Base, rota_pdf

TEM_PDF = all(importlib.util.find_spec(m) for m in ("pdfplumber", "reportlab"))


def diario_gediv(dia: int, quantidade: int = 3, inicio: int = 70) -> bytes:
    from observatorio.operacao import sintetico as S
    return S.diario(date(2026, 11, dia), 18700 + dia, [S.resenha_tempo(960 + dia, f"{dia - 1:02d}-11-2026", "LICENÇA ESPECIAL",
                                                                         inicio, quantidade)])


@unittest.skipUnless(TEM_PDF, "requer pdfplumber e reportlab")
class TesteColetaLeituraClassificacao(Base):
    def publicar_gediv(self, dia, **k):
        dados = diario_gediv(dia, **k)
        self.pdfs[rota_pdf(dia)] = dados
        self.s.rotas[rota_pdf(dia)] = (200, "application/pdf", dados)
        return dados

    def ler_e_classificar(self):
        return leitor.processar(self.banco, self.acervo), processo.classificar_pendentes(self.banco)

    def test_coleta_entrega_a_leitura_e_a_classificacao_com_manifesto_coerente(self):
        dados = self.publicar_gediv(7)
        sha = hashlib.sha256(dados).hexdigest()
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"NOVO": 1})
        leitura, classificacao = self.ler_e_classificar()
        self.assertEqual(leitura["LIDA"] + leitura["LIDA_COM_PENDENCIAS"], 1)
        atos = self.banco.con.execute("SELECT numero, subcategoria FROM ato WHERE sha256 = ?", (sha,)).fetchall()
        self.assertEqual([tuple(a) for a in atos], [("967/2026", "TS-05")])
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM decisao WHERE sha256 = ?", (sha,)).fetchone()[0], 3)
        # manifesto de download, verificação estrutural, acervo e leitura falam do MESMO arquivo
        download = [d for d in self.banco.downloads() if d["sha256"] == sha]
        self.assertEqual(len(download), 1)
        self.assertEqual(download[0]["bytes"], len(dados))
        self.assertEqual(self.banco.verificacao(sha)["integridade"], "ESTRUTURA_VERIFICADA")
        self.assertEqual(self.banco.con.execute("SELECT data_edicao FROM leitura WHERE sha256 = ?", (sha,)).fetchone()[0], "2026-11-07")

    def test_arquivo_em_quarentena_nunca_chega_a_leitura(self):
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", pdf_sem_paginas("q"))
        self.assertEqual(self.coletar(date(2026, 11, 7), date(2026, 11, 7))["fontes"]["auniao"]["downloads"], {B.QUARENTENA: 1})
        leitura, _ = self.ler_e_classificar()
        self.assertEqual(sum(leitura[k] for k in ("LIDA", "LIDA_COM_PENDENCIAS", "ERRO")), 0)
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM leitura").fetchone()[0], 0)
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0], 0)

    def test_truncado_com_200_nao_e_lido_e_a_versao_completa_e(self):
        dados = self.publicar_gediv(7)
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", dados, {"cortar": len(dados) - 200})
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.assertEqual(self.ler_e_classificar()[0]["LIDA"] + self.ler_e_classificar()[0]["LIDA_COM_PENDENCIAS"], 0)
        self.s.rotas[rota_pdf(7)] = (200, "application/pdf", dados)
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.ler_e_classificar()
        lidos = [r[0] for r in self.banco.con.execute("SELECT sha256 FROM leitura")]
        self.assertEqual(lidos, [hashlib.sha256(dados).hexdigest()])

    def test_pdf_alterado_e_reclassificado_e_a_revisao_humana_e_preservada(self):
        original = self.publicar_gediv(7)
        self.coletar(date(2026, 11, 7), date(2026, 11, 7))
        self.ler_e_classificar()
        sha_original = hashlib.sha256(original).hexdigest()
        ids = [r[0] for r in self.banco.con.execute("SELECT id FROM decisao WHERE sha256 = ?", (sha_original,))]
        servico.revisar_decisoes(self.banco, ids[:1], servico.CONFERIR, "revisora de teste", "conferido no PDF oficial",
                                 confirma_fonte=True, confirma_vinculo=True)
        # O portal troca legitimamente o arquivo no mesmo endereço (republicação com uma linha a mais).
        alterado = self.publicar_gediv(7, quantidade=4)
        resumo = self.coletar(date(2026, 11, 7), date(2026, 11, 7), reverificar=True)
        self.assertEqual(resumo["fontes"]["auniao"]["downloads"], {"ALTERADO": 1})
        self.ler_e_classificar()
        sha_novo = hashlib.sha256(alterado).hexdigest()
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM decisao WHERE sha256 = ?", (sha_novo,)).fetchone()[0], 4)
        revisada = self.banco.con.execute("SELECT validacao, revisor FROM decisao WHERE id = ?", (ids[0],)).fetchone()
        self.assertEqual(tuple(revisada), ("CONFERIDO", "revisora de teste"))        # revisão humana intacta
        pub = [p for p in self.banco.publicacoes() if p["data_publicacao"] == "2026-11-07"][0]
        self.assertEqual(len(self.banco.versoes(pub["id"])), 2)                       # as duas versões preservadas
        # reclassificar o arquivo original (nova versão de regras) também não toca a revisão
        processo.classificar_pendentes(self.banco, refazer=True)
        self.assertEqual(self.banco.con.execute("SELECT validacao FROM decisao WHERE id = ?", (ids[0],)).fetchone()[0], "CONFERIDO")

    def test_coleta_leitura_e_classificacao_repetidas_nao_duplicam(self):
        self.publicar_gediv(7)
        for _ in range(2):
            self.coletar(date(2026, 11, 7), date(2026, 11, 7))
            self.ler_e_classificar()
        contar = lambda t: self.banco.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        self.assertEqual((contar("arquivo"), contar("leitura"), contar("ato"), contar("decisao")), (1, 1, 1, 3))
        self.assertEqual(len([d for d in self.banco.downloads() if d["resultado"] == "NOVO"]), 1)


if __name__ == "__main__":
    unittest.main()
