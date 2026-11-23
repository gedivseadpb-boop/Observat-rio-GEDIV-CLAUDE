"""Testes completos do grupo Abono de Permanência no eixo Tempo de Serviço e do Resumo Comparativo Mensal."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C, processo
from observatorio.gerencias.gediv.classificador import classificar
from observatorio.nucleo.banco import Banco
from observatorio.operacao import previa_sintetica
from observatorio.painel import adaptador, exportacao, indicadores
from observatorio.revisao import servico
from scripts import preparar_previa_github_pages as prep


def _resenha(num: str, texto_assunto: str, linhas: list[str], *, deferir: bool = True) -> str:
    verbo = "DEFERIU" if deferir else "INDEFERIU"
    return (
        "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
        f"RESENHA Nº {num} - SEAD/GEDIV\n"
        f"O SECRETARIO DE ESTADO DA ADMINISTRACAO {verbo} os processos de {texto_assunto}:\n"
        "PROCESSO MATRICULA NOME CARGO LOTACAO\n"
        + "\n".join(linhas)
        + "\nPUBLIQUE-SE."
    )


def _carregar_conferir(banco: Banco, tag: str, data_iso: str, texto: str) -> None:
    sha = f"{tag:0<64}"[:64]
    url = f"manual:teste-abono-{tag}"
    banco.registrar_descoberta("manual", url, data_iso, "normal", 1, f"DOE teste {tag}")
    pub = banco.publicacao("manual", url)
    banco.registrar_arquivo(pub["id"], sha, len(texto.encode("utf-8")), f"doe_{tag}.pdf")
    banco.registrar_leitura(
        sha, "LIDA", "teste",
        [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": texto, "qualidade": "OK", "palavras": len(texto.split())}],
        "19000", data_iso, None,
    )
    res = processo.classificar_pendentes(banco)
    assert res["com_erro"] == 0
    for a in banco.con.execute("SELECT id, vinculo FROM ato WHERE natureza = 'ORIGINAL' AND sha256 = ?", (sha,)):
        servico.revisar_ato(
            banco, a["id"], servico.CONFERIR, "Revisor Teste",
            "Conferência sintética Abono de Permanência",
            confirma_fonte=True, confirma_vinculo=(a["vinculo"] != "EXPRESSO"),
        )


class TestAbonoPermanenciaEComparativoMensal(unittest.TestCase):
    def test_01_catalogo_e_classificacao_sem_confusao_com_outros_beneficios(self) -> None:
        codigos = [s.codigo for s in C.SUBCATEGORIAS]
        self.assertEqual(codigos, ["TS-01", "TS-02", "TS-03", "TS-04", "TS-05", "TS-06", "TS-07", "ABONO_PERMANENCIA"])
        self.assertNotIn("TS-08", codigos)
        self.assertEqual(C.SUBCATEGORIA_POR_CODIGO["ABONO_PERMANENCIA"].nome, "Abono de Permanência")

        # Classificação positiva (formas padrão, sem "DE" e compacta)
        for expr in ("ABONO DE PERMANÊNCIA", "ABONO PERMANENCIA", "ABONO DE PERMANENCIA (EC 103/2019)"):
            r = classificar([(1, _resenha("801/2026", expr, [
                "SAD-PSE-2099/80001 950.801-1 SERVIDOR FICTICIO ABONO UM PROFESSOR SEE",
            ]))], "sha-pos")
            self.assertEqual(len(r.atos), 1, f"Não classificou: {expr}")
            ato = r.atos[0]
            self.assertEqual(ato.eixo, C.TEMPO)
            self.assertEqual(ato.subcategoria, "ABONO_PERMANENCIA")
            self.assertIsNone(ato.modalidade)
            self.assertIsNone(ato.grupo)
            self.assertEqual(len(r.decisoes), 1)

        # Não confunde com outros abonos nem classifica como Progressão
        for outro in ("ABONO NATALINO", "ABONO PECUNIÁRIO", "ABONO SALARIAL", "ABONO FAMÍLIA"):
            r_out = classificar([(1, _resenha("802/2026", outro, [
                "SAD-PSE-2099/80002 950.802-2 SERVIDOR FICTICIO OUTRO PROFESSOR SEE",
            ]))], "sha-neg")
            self.assertEqual(r_out.atos, [], f"Classificou indevidamente: {outro}")
            self.assertEqual(r_out.decisoes, [])

    def test_02_zero_registros_comportamento_honesto_sem_inventar_dados(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-abono-zero-") as tmp:
            banco = Banco(Path(tmp) / "zero.sqlite3")
            try:
                _carregar_conferir(banco, "z1", "2026-09-10", _resenha("810/2026", "LICENCA ESPECIAL", [
                    "SAD-PSE-2099/81001 950.811-1 SERVIDOR FICTICIO ZERO UM PROFESSOR SEE",
                ]))
                p = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.GERENCIA_PERFIL)
                por_sub = {x["codigo"]: x for x in p["series"]["por_subcategoria"]}
                self.assertIn("ABONO_PERMANENCIA", por_sub)
                self.assertEqual(por_sub["ABONO_PERMANENCIA"]["total"], 0)
                self.assertEqual(por_sub["ABONO_PERMANENCIA"]["situacao"], "cobertura pendente")
                # Com apenas 1 mês de dados, comparativo mensal informa indisponibilidade honestamente
                cmp_m = p["series"]["comparativo_mensal"]
                self.assertFalse(cmp_m["disponivel"])
                self.assertEqual(cmp_m["motivo"], "menos_de_dois_meses")
            finally:
                banco.fechar()

    def test_03_indicadores_filtros_historico_exportacoes_e_privacidade(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-abono-full-") as tmp:
            banco = Banco(Path(tmp) / "abono.sqlite3")
            try:
                # Mês 1 (2026-09): 3 Abono + 5 TS-01 + 5 Progressão Vertical
                bloco_m1 = "\n\n".join([
                    _resenha("820/2026", "ABONO DE PERMANENCIA", [
                        f"SAD-PSE-2099/8200{i} 950.82{i}-{i} SERVIDOR FICTICIO ABONO M{i} PROFESSOR SEE"
                        for i in range(1, 4)
                    ]),
                    _resenha("821/2026", "ANOTACAO DE TEMPO DE SERVICO/CONTRIBUICAO", [
                        f"SAD-PSE-2099/8210{i} 950.83{i}-{i} SERVIDOR FICTICIO TS M{i} AGENTE SEAD"
                        for i in range(1, 6)
                    ]),
                    (
                        "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                        "RESENHA Nº 822/2026 - SEAD/GEDIV\n"
                        "O SECRETARIO DEFERIU os pedidos de PROGRESSAO VERTICAL do grupo MAG:\n"
                        "PROCESSO MATRICULA NOME CARGO LOTACAO CLASSE\n"
                        + "\n".join(
                            f"SAD-PSE-2099/8220{i} 950.84{i}-{i} SERVIDOR FICTICIO VERT M{i} PROFESSOR SEE A B"
                            for i in range(1, 6)
                        )
                        + "\nPUBLIQUE-SE."
                    ),
                ])
                # Mês 2 (2026-10): 3 Abono + 5 TS-05 (total Abono no período = 6 >= 5, mas 3 por mês < 5!)
                bloco_m2 = "\n\n".join([
                    _resenha("830/2026", "ABONO DE PERMANENCIA", [
                        f"SAD-PSE-2099/8300{i} 950.85{i}-{i} SERVIDOR FICTICIO ABONO N{i} ENFERMEIRO SES"
                        for i in range(1, 4)
                    ]),
                    _resenha("831/2026", "LICENCA ESPECIAL", [
                        f"SAD-PSE-2099/8310{i} 950.86{i}-{i} SERVIDOR FICTICIO LIC N{i} PROFESSOR SEE"
                        for i in range(1, 6)
                    ]),
                ])
                _carregar_conferir(banco, "m1", "2026-09-15", bloco_m1)
                _carregar_conferir(banco, "m2", "2026-10-15", bloco_m2)

                # 1. Totais e coerência matemática (sem dupla contagem)
                p = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.GERENCIA_PERFIL)
                self.assertEqual(p["indicadores"]["decisoes"], 21)
                por_ass = {x["chave"]: x["total"] for x in p["series"]["por_assunto"]}
                self.assertEqual(por_ass["VERTICAL"], 5)
                self.assertEqual(por_ass["HORIZONTAL"], 0)
                self.assertEqual(por_ass["TEMPO_SERVICO"], 16)  # 6 Abono + 5 TS-01 + 5 TS-05
                soma_subs = sum(x["total"] for x in p["series"]["por_subcategoria"]) + p["series"]["tempo_sem_subcategoria"]["total"]
                self.assertEqual(soma_subs, por_ass["TEMPO_SERVICO"])

                # 2. Filtro por subcategoria=ABONO_PERMANENCIA
                p_ab = indicadores.painel(banco, {"escopo": "conferido", "subcategoria": "ABONO_PERMANENCIA"}, indicadores.GERENCIA_PERFIL)
                self.assertEqual(p_ab["indicadores"]["decisoes"], 6)
                self.assertTrue(all(l["eixo"] == C.TEMPO and l["subcategoria"] == "ABONO_PERMANENCIA" for l in p_ab["linhas"]))

                # 3. Comparativo mensal (gerência)
                cm = p["series"]["comparativo_mensal"]
                self.assertTrue(cm["disponivel"])
                self.assertEqual((cm["mes_anterior"], cm["mes_atual"]), ("2026-09", "2026-10"))
                self.assertEqual(cm["resumo"]["anterior"], 13)
                self.assertEqual(cm["resumo"]["atual"], 8)
                self.assertEqual(cm["resumo"]["variacao_absoluta"], -5)
                gt = {g["codigo"]: g for g in cm["por_grupo_tempo"]}
                self.assertEqual(gt["ABONO_PERMANENCIA"]["anterior"], 3)
                self.assertEqual(gt["ABONO_PERMANENCIA"]["atual"], 3)
                self.assertEqual(gt["ABONO_PERMANENCIA"]["total_periodo"], 6)
                self.assertEqual(gt["ABONO_PERMANENCIA"]["participacao_tempo_pct"], 37.5)
                self.assertEqual(cm["abono_por_mes"], [{"mes": "2026-09", "total": 3}, {"mes": "2026-10", "total": 3}])

                # 4. Exportações CSV e XLSX incluem Abono de Permanência
                csv_bytes = exportacao.csv(exportacao.linhas_decisoes(p_ab))
                self.assertIn("ABONO_PERMANENCIA · Abono de Permanência", csv_bytes.decode("utf-8"))
                xlsx_bytes = exportacao.planilha(p_ab)
                with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
                    sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
                    self.assertIn("Abono de Permanência", sheet1)

                # 5. Snapshot público: Abono total=6 (>=5) visível como faixa 5; por mês (3 < 5) suprimido como None!
                snap_pub = indicadores.gerar_snapshot_publico(banco)
                indicadores.validar_snapshot_publico(snap_pub)
                sub_pub = {x["codigo"]: x for x in snap_pub["painel"]["series"]["por_subcategoria"]}
                self.assertEqual(sub_pub["ABONO_PERMANENCIA"]["total"], 5)
                cm_pub = snap_pub["painel"]["series"]["comparativo_mensal"]
                self.assertTrue(cm_pub["disponivel"])
                gt_pub = {g["codigo"]: g for g in cm_pub["por_grupo_tempo"]}
                self.assertIsNone(gt_pub["ABONO_PERMANENCIA"]["anterior"])
                self.assertIsNone(gt_pub["ABONO_PERMANENCIA"]["atual"])
                self.assertIsNone(gt_pub["ABONO_PERMANENCIA"]["variacao_absoluta"])
                self.assertIsNone(gt_pub["ABONO_PERMANENCIA"]["variacao_percentual"])
                self.assertEqual(gt_pub["ABONO_PERMANENCIA"]["total_periodo"], 5)
                self.assertTrue(all(x["total"] is None for x in cm_pub["abono_por_mes"]))
            finally:
                banco.fechar()

    def test_04_base_sintetica_canonica_inclui_abono_sem_alterar_42_verticais(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gediv-abono-sint-") as tmp:
            pasta_local = Path(tmp) / "local"
            pasta_pages = Path(tmp) / "pages"
            res = previa_sintetica.criar_base_local_sintetica(pasta_local, publicar_snapshot=True)
            # 42 Progressões Verticais de referência permanecem 100% intactas
            self.assertEqual(res["resumo_nivel_vertical"]["total_vertical"], 42)
            self.assertEqual(res["resumo_nivel_vertical"]["classificados"], 29)
            self.assertEqual(res["resumo_nivel_vertical"]["indeferidos"], 7)
            self.assertEqual(res["resumo_nivel_vertical"]["nao_determinados"], 2)
            self.assertEqual(res["resumo_nivel_vertical"]["inconsistentes"], 2)
            self.assertEqual(res["resumo_nivel_vertical"]["nao_aplica"], 2)

            prep.construir_pacote(pasta_pages)
            dados_pages = json.loads((pasta_pages / "dados-sinteticos-publicos.json").read_text(encoding="utf-8"))
            abono_rows = [
                r for r in dados_pages["rows"]
                if r["validation"] == "conferido" and r["axis"] == "tempo" and r["category"] == "ABONO_PERMANENCIA"
            ]
            self.assertEqual(len(abono_rows), 6)
            self.assertEqual(
                sorted({r["date"][:7] for r in abono_rows}),
                ["2026-10", "2026-11"],
            )
            # Snapshot público da base sintética canônica passa validação e expõe Abono >= 5 (faixa 5)
            snap_pub = indicadores.carregar_snapshot_publico(pasta_local / indicadores.ARQUIVO_SNAPSHOT_PUBLICO)
            self.assertIsNotNone(snap_pub)
            sub_pub = {x["codigo"]: x for x in snap_pub["painel"]["series"]["por_subcategoria"]}
            self.assertEqual(sub_pub["ABONO_PERMANENCIA"]["total"], 5)


if __name__ == "__main__":
    unittest.main()
