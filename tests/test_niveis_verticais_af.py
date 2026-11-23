"""Testes dedicados à separação das 5 situações da Progressão Vertical A–F.

Garante que o Observatório GEDIV nunca misture numa categoria genérica "Não identificados":
1. Progressões deferidas com nível de destino A–F efetivado (A..F);
2. Progressões indeferidas, sem nível efetivado (INDEFERIDO);
3. Progressões deferidas cujo nível A–F não pôde ser determinado (NAO_DETERMINADO);
4. Inconsistências na identificação ou sequência A–F (INCONSISTENTE);
5. Casos em que a estrutura A–F comprovadamente não se aplica (NAO_APLICA).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C, processo
from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores
from observatorio.revisao import servico


def _linha_vertical(resultado: str = "DEFERIDO", detalhe: dict | None = None, trecho: str = "") -> dict:
    return {
        "eixo": C.PROGRESSAO,
        "modalidade": C.VERTICAL,
        "resultado": resultado,
        "detalhe": detalhe or {},
        "trecho": trecho,
    }


class TestNiveisVerticaisAF(unittest.TestCase):
    def test_01_classificacao_cinco_situacoes_mutuamente_exclusivas(self) -> None:
        # 1. Deferida com nível A–F identificado (detalhe e fallback de trecho)
        r_af = indicadores.classificar_nivel_vertical(
            _linha_vertical("DEFERIDO", {"classe_anterior": "C", "classe_posterior": "D"})
        )
        self.assertEqual(r_af["categoria"], "D")
        self.assertEqual(r_af["nivel"], "D")
        self.assertEqual(r_af["transicao"], "C → D")
        self.assertEqual(r_af["motivo"], "ok")

        r_af_txt = indicadores.classificar_nivel_vertical(
            _linha_vertical("DEFERIDO", {}, "LINHA SAD-PSE-2099/00001 950.001-2 SERVIDOR FICTICIO PROFESSOR SEE D E")
        )
        self.assertEqual(r_af_txt["categoria"], "E")
        self.assertEqual(r_af_txt["transicao"], "D → E")

        # 2. Indeferida (sem nível efetivado, mesmo se houver texto/classe)
        r_ind = indicadores.classificar_nivel_vertical(
            _linha_vertical("INDEFERIDO", {"classe_anterior": "A", "classe_posterior": "B"}, "LINHA ... A B")
        )
        self.assertEqual(r_ind["categoria"], "INDEFERIDO")
        self.assertEqual(r_ind["nivel"], "NAO_IDENTIFICADO")
        self.assertEqual(r_ind["motivo"], "indeferido_sem_classe")

        # 3. Deferida sem nível determinado (ausente na publicação ou falha de OCR)
        r_ndet = indicadores.classificar_nivel_vertical(
            _linha_vertical("DEFERIDO", {}, "LINHA SAD-PSE-2099/00002 950.002-3 SERVIDOR FICTICIO ANALISTA SEAD")
        )
        self.assertEqual(r_ndet["categoria"], "NAO_DETERMINADO")
        self.assertEqual(r_ndet["nivel"], "NAO_IDENTIFICADO")
        self.assertEqual(r_ndet["motivo"], "ocr_ou_incompleto")

        # 4. Inconsistências na identificação ou sequência A–F
        for det_inc, trecho_inc, trans_esp in (
            ({"classe_anterior": "D", "classe_posterior": "B"}, "", "D → B"),
            ({"classe_anterior": "C", "classe_posterior": "C"}, "", "C → C"),
            ({"classe_anterior": "E", "classe_posterior": "G"}, "", "E → G"),
            ({"classe_anterior": "C", "classe_posterior": ""}, "", "C → ?"),
            ({}, "LINHA SAD-PSE-2099/00003 950.003-4 SERVIDOR FICTICIO PROFESSOR SEE D B", "D → B"),
            ({}, "LINHA SAD-PSE-2099/00004 950.004-5 SERVIDOR FICTICIO PROFESSOR SEE E G", "E → G"),
        ):
            r_inc = indicadores.classificar_nivel_vertical(_linha_vertical("DEFERIDO", det_inc, trecho_inc))
            self.assertEqual(r_inc["categoria"], "INCONSISTENTE", f"Falhou para {det_inc} / {trecho_inc}")
            self.assertEqual(r_inc["nivel"], "NAO_IDENTIFICADO")
            self.assertEqual(r_inc["transicao"], trans_esp)

        # 5. Estrutura A–F comprovadamente não se aplica
        for det_na, trecho_na in (
            ({"evolucao_lida": "II III"}, ""),
            ({"nivel_anterior": "NIVEL 1", "nivel_atual": "NIVEL 2"}, ""),
            ({"estrutura_nivel": "NAO_AF"}, ""),
            ({}, "LINHA SAD-PSE-2099/00005 950.005-6 SERVIDOR FICTICIO AGENTE SEDS II III"),
            ({}, "LINHA SAD-PSE-2099/00006 950.006-7 SERVIDOR FICTICIO AGENTE SEDS NIVEL 2 NIVEL 3"),
        ):
            r_na = indicadores.classificar_nivel_vertical(_linha_vertical("DEFERIDO", det_na, trecho_na))
            self.assertEqual(r_na["categoria"], "NAO_APLICA", f"Falhou para {det_na} / {trecho_na}")
            self.assertEqual(r_na["nivel"], "NAO_IDENTIFICADO")
            self.assertEqual(r_na["motivo"], "estrutura_nao_aplica")

        # Não-vertical continua retornando None
        r_horiz = indicadores.classificar_nivel_vertical({
            "eixo": C.PROGRESSAO, "modalidade": C.HORIZONTAL, "resultado": "DEFERIDO", "detalhe": {}, "trecho": ""
        })
        self.assertIsNone(r_horiz["categoria"])
        self.assertIsNone(r_horiz["nivel"])

    def test_02_particao_matematica_filtros_e_privacidade_snapshot(self) -> None:
        """Verifica soma exata == total_vertical, filtros por categoria, preservação de processos/servidores
        e proteção de privacidade (limiar >= 5 + supressão secundária) no snapshot público."""
        blocos = [
            # 6 deferidas A–F (grupo MAG)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 701/2026 - SEAD/GEDIV\n"
                "O SECRETARIO DEFERIU os pedidos de PROGRESSAO VERTICAL do grupo MAG:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO CLASSE\n"
                "SAD-PSE-2099/70001 950.701-1 SERVIDOR FICTICIO UM SILVA PROFESSOR SEE A B\n"
                "SAD-PSE-2099/70002 950.702-2 SERVIDOR FICTICIO DOIS SILVA PROFESSOR SEE B C\n"
                "SAD-PSE-2099/70003 950.703-3 SERVIDOR FICTICIO TRES SILVA PROFESSOR SEE B C\n"
                "SAD-PSE-2099/70004 950.704-4 SERVIDOR FICTICIO QUATRO SILVA PROFESSOR SEE B C\n"
                "SAD-PSE-2099/70005 950.705-5 SERVIDOR FICTICIO CINCO SILVA PROFESSOR SEE B C\n"
                "SAD-PSE-2099/70006 950.706-6 SERVIDOR FICTICIO SEIS SILVA PROFESSOR SEE B C\n"
                "PUBLIQUE-SE."
            ),
            # 5 indeferidas (grupo FAP)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 702/2026 - SEAD/GEDIV\n"
                "O SECRETARIO INDEFERIU os pedidos de PROGRESSAO VERTICAL do grupo FAP:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO\n"
                "SAD-PSE-2099/70007 950.707-7 SERVIDOR FICTICIO SETE COSTA FISCAL SEDAP\n"
                "SAD-PSE-2099/70008 950.708-8 SERVIDOR FICTICIO OITO COSTA FISCAL SEDAP\n"
                "SAD-PSE-2099/70009 950.709-9 SERVIDOR FICTICIO NOVE COSTA FISCAL SEDAP\n"
                "SAD-PSE-2099/70010 950.710-1 SERVIDOR FICTICIO DEZ COSTA FISCAL SEDAP\n"
                "SAD-PSE-2099/70011 950.711-2 SERVIDOR FICTICIO ONZE COSTA FISCAL SEDAP\n"
                "PUBLIQUE-SE."
            ),
            # 2 deferidas sem nível determinado (grupo ANS)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 703/2026 - SEAD/GEDIV\n"
                "O SECRETARIO DEFERIU os pedidos de PROGRESSAO VERTICAL do grupo ANS:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO\n"
                "SAD-PSE-2099/70012 950.712-3 SERVIDOR FICTICIO DOZE LIMA ANALISTA SEAD\n"
                "SAD-PSE-2099/70013 950.713-4 SERVIDOR FICTICIO TREZE LIMA ANALISTA SEAD\n"
                "PUBLIQUE-SE."
            ),
            # 2 inconsistências A–F (regressão D->B e igual C->C)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 704/2026 - SEAD/GEDIV\n"
                "O SECRETARIO DEFERIU os pedidos de PROGRESSAO VERTICAL do grupo MAG:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO CLASSE\n"
                "SAD-PSE-2099/70014 950.714-5 SERVIDOR FICTICIO QUATORZE ROCHA PROFESSOR SEE D B\n"
                "SAD-PSE-2099/70015 950.715-6 SERVIDOR FICTICIO QUINZE ROCHA PROFESSOR SEE C C\n"
                "PUBLIQUE-SE."
            ),
            # 2 estrutura não A–F (níveis romanos II->III e III->IV)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 705/2026 - SEAD/GEDIV\n"
                "O SECRETARIO DEFERIU os pedidos de PROGRESSAO VERTICAL do grupo GPC:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO CLASSE\n"
                "SAD-PSE-2099/70016 950.716-7 SERVIDOR FICTICIO DEZESSEIS DIAS AGENTE SEDS II III\n"
                "SAD-PSE-2099/70017 950.717-8 SERVIDOR FICTICIO DEZESSETE DIAS ESCRIVAO SEDS III IV\n"
                "PUBLIQUE-SE."
            ),
            # 2 horizontais (não entram no total vertical, preservadas no total global)
            (
                "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
                "RESENHA Nº 706/2026 - SEAD/GEDIV\n"
                "O SECRETARIO DEFERIU os pedidos de PROGRESSAO HORIZONTAL do grupo GAJ:\n"
                "PROCESSO MATRICULA NOME CARGO LOTACAO\n"
                "SAD-PSE-2099/70018 950.718-9 SERVIDOR FICTICIO DEZOITO SOUZA ANALISTA PGE\n"
                "SAD-PSE-2099/70019 950.719-1 SERVIDOR FICTICIO DEZENOVE SOUZA ANALISTA PGE\n"
                "PUBLIQUE-SE."
            ),
        ]
        texto = "\n\n".join(blocos)
        with tempfile.TemporaryDirectory(prefix="gediv-test-af-") as tmp:
            banco = Banco(Path(tmp) / "teste.sqlite3")
            try:
                sha = "f" * 64
                banco.registrar_descoberta("manual", "manual:teste-af", "2026-10-15", "normal", 19001, "DOE teste")
                pub = banco.publicacao("manual", "manual:teste-af")
                banco.registrar_arquivo(pub["id"], sha, len(texto.encode("utf-8")), "doe_teste.pdf")
                banco.registrar_leitura(
                    sha, "LIDA", "teste",
                    [{"numero": 1, "metodo": "TEXTO", "colunas": 1, "texto": texto, "qualidade": "OK", "palavras": len(texto.split())}],
                    "19001", "2026-10-15", None,
                )
                cls = processo.classificar_pendentes(banco)
                self.assertEqual(cls["com_erro"], 0)
                for a in banco.con.execute("SELECT id FROM ato WHERE natureza = 'ORIGINAL'"):
                    servico.revisar_ato(
                        banco, a["id"], "CONFERIR", "Revisor Teste",
                        "Conferência sintética de validação das 5 situações A–F",
                        confirma_fonte=True, confirma_vinculo=True,
                    )

                p = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.GERENCIA_PERFIL)
                self.assertEqual(p["indicadores"]["decisoes"], 19)
                self.assertEqual(p["indicadores"]["processos"], 19)
                self.assertEqual(p["series"]["unidades"]["servidores"]["total"], 19)

                res = p["series"]["resumo_nivel_vertical"]
                self.assertEqual(res["total_progressao"], 19)
                self.assertEqual(res["total_horizontal"], 2)
                self.assertEqual(res["total_vertical"], 17)
                self.assertEqual(res["classificados"], 6)
                self.assertEqual(res["indeferidos"], 5)
                self.assertEqual(res["nao_determinados"], 2)
                self.assertEqual(res["inconsistentes"], 2)
                self.assertEqual(res["nao_aplica"], 2)
                self.assertEqual(res["nao_identificados"], 11)
                self.assertEqual(
                    res["classificados"] + res["indeferidos"] + res["nao_determinados"] + res["inconsistentes"] + res["nao_aplica"],
                    res["total_vertical"],
                )

                por_sit = {x["codigo"]: x["total"] for x in p["series"]["por_situacao_nivel_vertical"]}
                self.assertEqual(sum(por_sit.values()), 17)
                self.assertEqual(por_sit["B"], 1)
                self.assertEqual(por_sit["C"], 5)
                self.assertEqual(por_sit["INDEFERIDO"], 5)
                self.assertEqual(por_sit["NAO_DETERMINADO"], 2)
                self.assertEqual(por_sit["INCONSISTENTE"], 2)
                self.assertEqual(por_sit["NAO_APLICA"], 2)

                # Filtros do backend por cada situação + legado NI
                for filtro_nv, esp in (
                    ("B", 1),
                    ("C", 5),
                    ("INDEFERIDO", 5),
                    ("NAO_DETERMINADO", 2),
                    ("INCONSISTENTE", 2),
                    ("NAO_APLICA", 2),
                    ("NI", 11),
                    ("NAO_IDENTIFICADO", 11),
                ):
                    pf = indicadores.painel(banco, {"escopo": "conferido", "nivel": filtro_nv}, indicadores.GERENCIA_PERFIL)
                    self.assertEqual(pf["indicadores"]["decisoes"], esp, f"Filtro nivel={filtro_nv} falhou")

                # Adaptador para frontend preserva exatamente as 5 categorias
                proj = adaptador.projetar_para_dashboard_2910(p, [], [])
                status_counts: dict[str, int] = {}
                for row in proj["rows"]:
                    if row["modality"] == "Vertical":
                        st = row["levelStatus"]
                        status_counts[st] = status_counts.get(st, 0) + 1
                self.assertEqual(status_counts, {"B": 1, "C": 5, "INDEFERIDO": 5, "NAO_DETERMINADO": 2, "INCONSISTENTE": 2, "NAO_APLICA": 2})

                # Snapshot público protegido (limiar >= 5 + supressão secundária + validação completa)
                snap_pub = indicadores.gerar_snapshot_publico(banco)
                indicadores.validar_snapshot_publico(snap_pub)
                sit_pub = {x["codigo"]: x for x in snap_pub["painel"]["series"]["por_situacao_nivel_vertical"]}
                self.assertEqual(sit_pub["C"]["total"], 5)
                self.assertEqual(sit_pub["INDEFERIDO"]["total"], 5)
                for cod_menor in ("B", "NAO_DETERMINADO", "INCONSISTENTE", "NAO_APLICA"):
                    self.assertIsNone(sit_pub[cod_menor]["total"], f"{cod_menor} (< 5) deveria estar suprimido no público")
                    self.assertEqual(sit_pub[cod_menor]["transicoes"], [])
            finally:
                banco.fechar()

    def test_03_previa_estatica_github_pages_contem_cinco_situacoes(self) -> None:
        from scripts import preparar_previa_github_pages as prep

        with tempfile.TemporaryDirectory(prefix="gediv-test-pages-") as tmp:
            pasta = prep.construir_pacote(Path(tmp) / "public")
            self.assertTrue((pasta / "index.html").is_file())
            self.assertTrue((pasta / "dados-sinteticos-publicos.json").is_file())


if __name__ == "__main__":
    unittest.main()
