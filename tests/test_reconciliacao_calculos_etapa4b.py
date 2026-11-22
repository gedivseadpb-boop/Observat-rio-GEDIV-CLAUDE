"""Regressões obrigatórias da Etapa 4B — Reconciliação de cálculos, unidades, grupos, eventos e paridade.

Todos os dados neste módulo são 100% SINTÉTICOS (nenhum dado real, nenhum PDF real, nenhuma escrita nos bancos originais).
Toda decomposição de categorias exige erro ZERO em relação ao total de referência, identificando os registros
responsáveis em caso de divergência.
"""
from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from observatorio.gerencias.gediv import catalogo as C, classificador as K, processo
from observatorio.nucleo import banco as B
from observatorio.painel import adaptador, indicadores
from observatorio.revisao import servico
from observatorio.web.servidor import criar_servidor
from tests import test_painel as TP

REV = "Revisora Fictícia GEDIV"
JUST = "Teste sintético de reconciliação Etapa 4B com fonte conferida"
GER = indicadores.GERENCIA_PERFIL


def _assert_particoes_exatas(tc: unittest.TestCase, p: dict, proj: dict | None = None) -> None:
    """Valida todas as partições matemáticas com tolerância ZERO, apontando exatamente os IDs divergentes."""
    linhas = p["linhas"]
    ind = p["indicadores"]
    uni = p["series"]["unidades"]
    total_linhas = len(linhas)

    # 1. Total de decisões == len(linhas) == D + I + NI
    d_ids = [l["id"] for l in linhas if l["resultado"] == "DEFERIDO"]
    i_ids = [l["id"] for l in linhas if l["resultado"] == "INDEFERIDO"]
    ni_ids = [l["id"] for l in linhas if l["resultado"] == "NAO_INFORMADO"]
    outros_res = [l["id"] for l in linhas if l["resultado"] not in ("DEFERIDO", "INDEFERIDO", "NAO_INFORMADO")]
    tc.assertEqual(outros_res, [], f"Resultados fora do domínio nos registros: {outros_res}")
    tc.assertEqual(
        ind["decisoes"], total_linhas,
        f"Divergência total decisões ({ind['decisoes']}) vs linhas ({total_linhas})",
    )
    soma_res = uni["decisoes"]["deferidos"] + uni["decisoes"]["indeferidos"] + uni["decisoes"]["nao_informado"]
    tc.assertEqual(
        soma_res, uni["decisoes"]["total"],
        f"Partição D+I+NI ({soma_res}) != total ({uni['decisoes']['total']}); "
        f"D={len(d_ids)}, I={len(i_ids)}, NI={len(ni_ids)}",
    )
    tc.assertEqual(uni["decisoes"]["deferidos"], len(d_ids))
    tc.assertEqual(uni["decisoes"]["indeferidos"], len(i_ids))
    tc.assertEqual(uni["decisoes"]["nao_informado"], len(ni_ids))

    # 2. Decomposição por eixo == total de decisões
    prog_ids = [l["id"] for l in linhas if l["eixo"] == C.PROGRESSAO]
    tempo_ids = [l["id"] for l in linhas if l["eixo"] == C.TEMPO]
    eixo_estranho = [l["id"] for l in linhas if l["eixo"] not in (C.PROGRESSAO, C.TEMPO)]
    tc.assertEqual(eixo_estranho, [], f"Linhas com eixo fora de PROGRESSAO/TEMPO_SERVICO: {eixo_estranho}")
    soma_assunto = sum(x["total"] for x in p["series"]["por_assunto"])
    tc.assertEqual(
        soma_assunto, total_linhas,
        f"Soma por_assunto ({soma_assunto}) != total ({total_linhas}); prog={len(prog_ids)}, tempo={len(tempo_ids)}",
    )

    # 3. Decomposição de Progressão por grupo == total de decisões de Progressão
    soma_grupo = sum(x["total"] for x in p["series"]["por_grupo"])
    tc.assertEqual(
        soma_grupo, len(prog_ids),
        f"Soma por_grupo ({soma_grupo}) != total Progressão ({len(prog_ids)}); ids={prog_ids}",
    )

    # 4. Decomposição de Tempo de Serviço por subcategoria + SEM_SUBCATEGORIA == total Tempo
    tempo_sem = p["series"]["tempo_sem_subcategoria"]
    tempo_sem_n = tempo_sem["total"] if isinstance(tempo_sem, dict) else int(tempo_sem)
    soma_sub = sum(x["total"] for x in p["series"]["por_subcategoria"]) + tempo_sem_n
    tc.assertEqual(
        soma_sub, len(tempo_ids),
        f"Soma subcategorias+sem_subcategoria ({soma_sub}) != total Tempo ({len(tempo_ids)}); ids={tempo_ids}",
    )

    # 5. Decomposição temporal (por_data) == total de decisões
    soma_data = sum(x["total"] for x in p["series"]["por_data"])
    tc.assertEqual(soma_data, total_linhas, f"Soma por_data ({soma_data}) != total ({total_linhas})")
    for mes in p["series"]["por_data"]:
        soma_mes = mes["vertical"] + mes["horizontal"] + mes["progressao_sem_modalidade"] + mes["tempo"]
        tc.assertEqual(soma_mes, mes["total"], f"Data {mes.get('data')} não fecha: {mes}")

    # 6. Partição exaustiva de processos (D + I + Misto + NI == total processos)
    up = uni["processos"]
    soma_proc = up["deferidos"] + up["indeferidos"] + up["mistos"] + up["nao_informado"]
    tc.assertEqual(
        soma_proc, up["total"],
        f"Partição de processos não fecha: {up} (delta={up['total'] - soma_proc})",
    )
    tc.assertEqual(ind["processos"], up["total"])

    # 7. Partição exaustiva de servidores (beneficiados + somente_indeferido + somente_nao_informado == total)
    us = uni["servidores"]
    soma_serv = us["beneficiados"] + us["somente_indeferido"] + us["somente_nao_informado"]
    tc.assertEqual(
        soma_serv, us["total"],
        f"Partição de servidores não fecha: {us} (delta={us['total'] - soma_serv})",
    )
    tc.assertEqual(us["beneficiados"], us["somente_deferido"] + us["misto_com_deferido"])
    tc.assertEqual(us["somente_indeferido"], us["apenas_indeferido"] + us["indeferido_e_nao_informado"])

    # 8. Paridade exata com o adaptador do painel unificado (cartões, gráficos, tabelas)
    if proj is not None:
        escopo = p["meta"].get("escopo") or "conferido"
        tc.assertEqual(len(proj["rows"]), total_linhas)
        visao = proj["dashboard"]["views"][escopo]
        m = visao["metrics"]
        s = visao["series"]
        tc.assertEqual(m["decisions"], uni["decisoes"]["total"])
        tc.assertEqual(m["deferidos"], uni["decisoes"]["deferidos"])
        tc.assertEqual(m["indeferidos"], uni["decisoes"]["indeferidos"])
        tc.assertEqual(m["naoInformado"], uni["decisoes"]["nao_informado"])
        tc.assertEqual(m["processes"], uni["processos"]["total"])
        tc.assertEqual(m["processesDeferidos"], uni["processos"]["deferidos"])
        tc.assertEqual(m["processesIndeferidos"], uni["processos"]["indeferidos"])
        tc.assertEqual(m["processesMistos"], uni["processos"]["mistos"])
        tc.assertEqual(m["processesNaoInformado"], uni["processos"]["nao_informado"])
        tc.assertEqual(m["servers"], uni["servidores"]["total"])
        tc.assertEqual(m["benefitedServers"], uni["servidores"]["beneficiados"])
        tc.assertEqual(m["serversOnlyIndeferido"], uni["servidores"]["somente_indeferido"])
        tc.assertEqual(m["serversOnlyNaoInformado"], uni["servidores"]["somente_nao_informado"])
        tc.assertEqual(m["rowsWithoutValidRegistration"], uni["servidores"]["linhas_sem_matricula_valida"])
        tc.assertEqual(m["pedidosIndividuais"], uni["pedidos_individuais"])
        tc.assertEqual(s["vertical"] + s["horizontal"] + s["progressaoSemModalidade"] + s["tempo"], total_linhas)
        tc.assertEqual(s["other"], 0)
        # Nenhuma linha de `outra_publicacao` pode contaminar `rows`
        contaminacao = [r["id"] for r in proj["rows"] if r.get("axis") not in ("progressao", "tempo")]
        tc.assertEqual(contaminacao, [], f"Contaminação de outra_publicacao em rows: {contaminacao}")


def _resenha_progressao(
    numero: str,
    linhas_proc: list[str],
    *,
    modalidade: str = "HORIZONTAL",
    grupo: str = "MAG",
    verbo: str = "DEFERIU",
    extra_cab: str = "",
) -> str:
    cab_mod = f"PROGRESSÃO FUNCIONAL {modalidade}" if modalidade else "PROGRESSÃO FUNCIONAL"
    grp_txt = f" do Grupo {grupo}" if grupo else ""
    return (
        f"SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
        f"RESENHA Nº : {numero} - DEREH/GS/SEAD\n"
        f"DIRETORIA EXECUTIVA DE RECURSOS HUMANOS EXPEDIENTE DO DIA : 05-10-2026\n"
        f"GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
        f"{extra_cab}"
        f"O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO {verbo} os processos de {cab_mod}{grp_txt}:\n"
        f"Processo Matricula Nome Cargo Classe P/Classe\n"
        + "\n".join(linhas_proc)
        + "\nPUBLIQUE-SE"
    )


def _portaria_sem_efeito(numero: str, resenha_citada: str, processos: list[str], data_orig: str = "09/10/2026") -> str:
    procs_txt = ", ".join(processos)
    return (
        f"SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
        f"PORTARIA Nº {numero} - GS/SEAD\n"
        f"GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
        f"O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO, usando de suas atribuições, "
        f"RESOLVE TORNAR SEM EFEITO a publicação da Resenha nº {resenha_citada}, "
        f"publicada no DOE de {data_orig}, exclusivamente quanto ao(s) processo(s) {procs_txt}, "
        f"referente à PROGRESSÃO FUNCIONAL.\n"
        f"PUBLIQUE-SE"
    )


class TesteReconciliacaoEtapa4B(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._dir.cleanup)
        self.banco = B.Banco(Path(self._dir.name) / "etapa4b_sintetico.sqlite3")
        self.addCleanup(self.banco.fechar)

    def carregar_e_classificar(self, marca: str, data: str, texto: str) -> str:
        sha = TP.carregar(self.banco, marca, data, texto)
        processo.classificar_pendentes(self.banco)
        return sha

    def conferir_todas_decisoes(self) -> None:
        ids = [r[0] for r in self.banco.con.execute("SELECT id FROM decisao WHERE validacao = 'PENDENTE'")]
        if ids:
            servico.revisar_decisoes(self.banco, ids, servico.CONFERIR, REV, JUST, True, True)

    def painel_e_proj(self, **filtros) -> tuple[dict, dict]:
        p = indicadores.painel(self.banco, filtros, GER)
        outras = indicadores.outras_publicacoes(self.banco, GER)
        proj = adaptador.projetar_para_dashboard_2910(p, outras_resp=outras)
        return p, proj

    # 1. Portaria que desconstitui 2 de 20 decisões
    def test_01_portaria_desconstitui_2_de_20_decisoes(self):
        linhas20 = [
            f"SAD-PSE-2099/{91001 + i} {910001 + i}-1 SERVIDOR FICTICIO {i:02d} PROFESSOR A B"
            for i in range(20)
        ]
        self.carregar_e_classificar("d01", "2026-10-09", _resenha_progressao("101/2099", linhas20))
        self.carregar_e_classificar(
            "d02", "2026-10-15",
            _portaria_sem_efeito("201/2099", "101/2099", ["SAD-PSE-2099/91003", "SAD-PSE-2099/91017"]),
        )
        self.conferir_todas_decisoes()

        # Regra 6: antes da confirmação do evento, efeito numérico ZERO
        p_antes, proj_antes = self.painel_e_proj()
        _assert_particoes_exatas(self, p_antes, proj_antes)
        self.assertEqual(p_antes["indicadores"]["decisoes"], 20)
        self.assertEqual(p_antes["indicadores"]["sem_efeito"], 0)
        self.assertEqual(p_antes["series"]["eventos_detalhados"]["decisoes_sem_efeito"], 0)

        ev = self.banco.con.execute("SELECT * FROM evento").fetchone()
        res = servico.revisar_evento(self.banco, ev["id"], servico.VINCULAR, REV, JUST, None, True)
        self.assertEqual(res["decisoes_vinculadas"], 2)

        # Regra 3: somente as 2 decisões atingidas deixam de contar; 18 permanecem ativas
        p_dep, proj_dep = self.painel_e_proj()
        _assert_particoes_exatas(self, p_dep, proj_dep)
        self.assertEqual(p_dep["indicadores"]["decisoes"], 18)
        self.assertEqual(p_dep["indicadores"]["deferidos"], 18)
        self.assertEqual(p_dep["indicadores"]["sem_efeito"], 1)
        self.assertEqual(p_dep["series"]["eventos_detalhados"]["sem_efeito_atos"], 1)
        self.assertEqual(p_dep["series"]["eventos_detalhados"]["decisoes_sem_efeito"], 2)
        self.assertEqual(proj_dep["dashboard"]["views"]["conferido"]["metrics"]["decisoesSemEfeito"], 2)
        self.assertEqual(proj_dep["dashboard"]["views"]["conferido"]["metrics"]["semEfeito"], 1)
        # Nenhuma decisão foi apagada da tabela histórica
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM decisao").fetchone()[0], 20)
        ativos_procs = {l["processo"] for l in p_dep["linhas"]}
        self.assertNotIn("SAD-PSE-2099/91003", ativos_procs)
        self.assertNotIn("SAD-PSE-2099/91017", ativos_procs)

    # 2. Indeferimento tornado sem efeito seguido de deferimento
    def test_02_indeferimento_sem_efeito_seguido_de_deferimento(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("102/2099", ["SAD-PSE-2099/95001 950001-1 PESSOA FICTICIA UM PROFESSOR A B"], verbo="INDEFERIU"),
        )
        self.carregar_e_classificar(
            "d02", "2026-10-12",
            _resenha_progressao("103/2099", ["SAD-PSE-2099/95001 950001-1 PESSOA FICTICIA UM PROFESSOR A B"], verbo="DEFERIU"),
        )
        self.carregar_e_classificar(
            "d03", "2026-10-15",
            _portaria_sem_efeito("202/2099", "102/2099", ["SAD-PSE-2099/95001"]),
        )
        self.conferir_todas_decisoes()

        p_antes, proj_antes = self.painel_e_proj()
        _assert_particoes_exatas(self, p_antes, proj_antes)
        self.assertEqual((p_antes["indicadores"]["decisoes"], p_antes["indicadores"]["deferidos"], p_antes["indicadores"]["indeferidos"]), (2, 1, 1))
        self.assertEqual(p_antes["series"]["unidades"]["processos"]["mistos"], 1)

        ev = self.banco.con.execute("SELECT * FROM evento").fetchone()
        servico.revisar_evento(self.banco, ev["id"], servico.VINCULAR, REV, JUST, None, True)

        # Regra 4: indeferimento desconstituído deixa de contar; processo deixa de ser misto e fica deferido
        p_dep, proj_dep = self.painel_e_proj()
        _assert_particoes_exatas(self, p_dep, proj_dep)
        self.assertEqual((p_dep["indicadores"]["decisoes"], p_dep["indicadores"]["deferidos"], p_dep["indicadores"]["indeferidos"]), (1, 1, 0))
        self.assertEqual(p_dep["series"]["unidades"]["processos"]["deferidos"], 1)
        self.assertEqual(p_dep["series"]["unidades"]["processos"]["mistos"], 0)
        self.assertEqual(p_dep["series"]["unidades"]["processos"]["indeferidos"], 0)
        self.assertEqual(p_dep["series"]["unidades"]["servidores"]["somente_deferido"], 1)
        self.assertEqual(p_dep["series"]["unidades"]["servidores"]["beneficiados"], 1)

    # 3. Republicação idêntica (+0 decisões novas, +1 em republicacoes_atos)
    def test_03_republicacao_identica_nao_duplica_decisoes(self):
        linhas = [
            "SAD-PSE-2099/93001 930001-1 SERVIDOR UM PROFESSOR A B",
            "SAD-PSE-2099/93002 930002-2 SERVIDOR DOIS PROFESSOR B C",
            "SAD-PSE-2099/93003 930003-3 SERVIDOR TRES PROFESSOR C D",
        ]
        orig_txt = _resenha_progressao("104/2099", linhas)
        repub_txt = orig_txt.replace("PUBLIQUE-SE", "REPUBLICADA POR INCORREÇÃO\nPUBLIQUE-SE")
        self.carregar_e_classificar("d01", "2026-10-09", orig_txt)
        self.carregar_e_classificar("d02", "2026-10-15", repub_txt)
        self.conferir_todas_decisoes()

        ev = self.banco.con.execute("SELECT * FROM evento WHERE tipo = 'REPUBLICACAO'").fetchone()
        self.assertIsNotNone(ev)
        servico.revisar_evento(self.banco, ev["id"], servico.VINCULAR, REV, JUST, None, True)

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["decisoes"], 3)
        self.assertEqual(p["indicadores"]["refeitos"], 1)
        self.assertEqual(p["series"]["eventos_detalhados"]["republicacoes_atos"], 1)
        self.assertEqual(p["series"]["eventos_detalhados"]["retificacoes_atos"], 0)
        self.assertEqual(proj["dashboard"]["views"]["conferido"]["metrics"]["republicacoes"], 1)
        self.assertEqual(proj["dashboard"]["views"]["conferido"]["metrics"]["retificacoes"], 0)
        self.assertEqual(len(proj["rows"]), 3)
        self.assertTrue(any(o["actType"] == "REPUBLICADO_POR_INCORRECAO" for o in proj["otherPublications"]))

    # 4. Retificação que modifica um resultado (preservando histórico original)
    def test_04_retificacao_modifica_resultado_e_preserva_historico(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao(
                "105/2099",
                [
                    "SAD-PSE-2099/94001 940001-1 SERVIDOR QUATRO UM PROFESSOR A B",
                    "SAD-PSE-2099/94002 940002-2 SERVIDOR QUATRO DOIS PROFESSOR B C",
                ],
                verbo="INDEFERIU",
            ),
        )
        retif_txt = (
            "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
            "PORTARIA Nº 205/2099 - GS/SEAD\n"
            "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
            "RETIFICAÇÃO da Resenha nº 105/2099, publicada no DOE de 09/10/2026, "
            "referente à PROGRESSÃO FUNCIONAL, quanto ao processo SAD-PSE-2099/94001: "
            "onde se lê INDEFERIDO, leia-se DEFERIDO.\nPUBLIQUE-SE"
        )
        self.carregar_e_classificar("d02", "2026-10-15", retif_txt)
        self.conferir_todas_decisoes()

        d_alvo = self.banco.con.execute("SELECT id FROM decisao WHERE processo = 'SAD-PSE-2099/94001'").fetchone()["id"]
        ato_orig = self.banco.con.execute("SELECT id FROM ato WHERE numero = '105/2099'").fetchone()["id"]
        ev = self.banco.con.execute("SELECT * FROM evento WHERE tipo = 'RETIFICACAO'").fetchone()
        self.assertIsNotNone(ev)

        servico.revisar_evento(
            self.banco, ev["id"], servico.VINCULAR, REV, JUST, ato_orig, True,
            decisoes_ids=[d_alvo], resultado_novo="DEFERIDO", campos_corrigidos={"cargo": "PROFESSOR RETIFICADO"},
        )

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual((p["indicadores"]["decisoes"], p["indicadores"]["deferidos"], p["indicadores"]["indeferidos"]), (2, 1, 1))
        self.assertEqual(p["series"]["eventos_detalhados"]["retificacoes_atos"], 1)
        self.assertEqual(p["series"]["eventos_detalhados"]["decisoes_retificadas"], 1)
        linha_ret = next(l for l in p["linhas"] if l["id"] == d_alvo)
        self.assertEqual(linha_ret["resultado"], "DEFERIDO")
        self.assertEqual(linha_ret["resultado_original"], "INDEFERIDO")
        self.assertEqual(linha_ret["cargo"], "PROFESSOR RETIFICADO")
        self.assertEqual(len(linha_ret["retificacoes_aplicadas"]), 1)
        # Histórico original preservado intacto na tabela `decisao`
        raw = self.banco.con.execute("SELECT resultado, cargo FROM decisao WHERE id = ?", (d_alvo,)).fetchone()
        self.assertEqual(raw["resultado"], "INDEFERIDO")
        self.assertEqual(raw["cargo"], "PROFESSOR")

        # Reabrir o evento remove o efeito calculado (Regra 6)
        servico.revisar_evento(self.banco, ev["id"], servico.REABRIR, REV, JUST)
        p_reab, proj_reab = self.painel_e_proj()
        _assert_particoes_exatas(self, p_reab, proj_reab)
        self.assertEqual((p_reab["indicadores"]["deferidos"], p_reab["indicadores"]["indeferidos"]), (0, 2))

    # 5. Processo coletivo com vários servidores sem matrícula disponível
    def test_05_processo_coletivo_com_servidores_sem_matricula(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("106/2099", ["SAD-PSE-2099/96001 960001-1 SERVIDOR COM MATRICULA UM PROFESSOR A B"]),
        )
        ato_id = self.banco.con.execute("SELECT id FROM ato WHERE numero = '106/2099'").fetchone()["id"]
        sha = self.banco.con.execute("SELECT sha256 FROM ato WHERE id = ?", (ato_id,)).fetchone()["sha256"]
        # Inserir mais 3 decisões no mesmo processo coletivo: 1 indeferida com matrícula, 2 sem matrícula (D e NI)
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_col_2', ?, ?, 1, 'SAD-PSE-2099/96001', 'SERVIDOR DOIS', '960002-2', 'PROFESSOR', '{}', 'INDEFERIDO', 't2', 'PENDENTE', 1, 'cl_col_2')",
                (ato_id, sha),
            )
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_col_3', ?, ?, 1, 'SAD-PSE-2099/96001', 'SERVIDOR SEM MAT A', NULL, 'PROFESSOR', '{}', 'DEFERIDO', 't3', 'PENDENTE', 1, 'cl_col_3')",
                (ato_id, sha),
            )
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_col_4', ?, ?, 1, 'SAD-PSE-2099/96001', 'SERVIDOR SEM MAT B', '', 'PROFESSOR', '{}', 'NAO_INFORMADO', 't4', 'PENDENTE', 1, 'cl_col_4')",
                (ato_id, sha),
            )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        uni = p["series"]["unidades"]
        self.assertEqual(uni["decisoes"], {"total": 4, "deferidos": 2, "indeferidos": 1, "nao_informado": 1})
        self.assertEqual(uni["pedidos_individuais"], 4)  # nunca elimina ou funde linhas sem matrícula
        self.assertEqual(uni["processos"]["total"], 1)
        self.assertEqual(uni["processos"]["coletivos"], 1)
        self.assertEqual(uni["processos"]["mistos"], 1)
        self.assertEqual(uni["processos"]["mistos_deferido_indeferido"], 1)
        self.assertEqual(uni["servidores"]["total"], 2)
        self.assertEqual(uni["servidores"]["linhas_sem_matricula_valida"], 2)

    # 6. Um servidor com dois pedidos autônomos + caso INDEFERIDO + NAO_INFORMADO (partição exata de servidores)
    def test_06_servidor_dois_pedidos_autonomos_e_particao_indeferido_com_nao_informado(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("107/2099", ["SAD-PSE-2099/97001 970001-1 SERVIDOR AUTONOMO PROFESSOR A B"], verbo="DEFERIU"),
        )
        self.carregar_e_classificar(
            "d02", "2026-10-12",
            _resenha_progressao(
                "108/2099",
                [
                    "SAD-PSE-2099/97002 970001-1 SERVIDOR AUTONOMO PROFESSOR B C",
                    "SAD-PSE-2099/97003 970002-2 SERVIDOR INDEF NI PROFESSOR A B",
                ],
                verbo="INDEFERIU",
            ),
        )
        # Adiciona segunda decisão NAO_INFORMADO para o servidor 970002-2 (reproduz exatamente o bug dos 2 servidores!)
        ato_id = self.banco.con.execute("SELECT id FROM ato WHERE numero = '108/2099'").fetchone()["id"]
        sha = self.banco.con.execute("SELECT sha256 FROM ato WHERE id = ?", (ato_id,)).fetchone()["sha256"]
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_ni_serv2', ?, ?, 1, 'SAD-PSE-2099/97004', 'SERVIDOR INDEF NI', '970002-2', 'PROFESSOR', '{}', 'NAO_INFORMADO', 't_ni', 'PENDENTE', 1, 'cl_ni_2')",
                (ato_id, sha),
            )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        us = p["series"]["unidades"]["servidores"]
        # Regra 5: indeferimento em pedido posterior não elimina concessão anterior válida do servidor 970001-1
        self.assertEqual(us["total"], 2)
        self.assertEqual(us["beneficiados"], 1)
        self.assertEqual(us["misto_com_deferido"], 1)
        # Servidor com INDEFERIDO + NAO_INFORMADO entra em somente_indeferido via indeferido_e_nao_informado (zero lacuna!)
        self.assertEqual(us["somente_indeferido"], 1)
        self.assertEqual(us["indeferido_e_nao_informado"], 1)
        self.assertEqual(us["somente_nao_informado"], 0)
        self.assertEqual(p["indicadores"]["decisoes"], 4)

    # 7. Duas grafias da mesma matrícula + matrículas inválidas nunca fundidas
    def test_07_duas_grafias_mesma_matricula_e_invalidas_nunca_fundidas(self):
        self.assertEqual(B.normalizar_matricula("987.654-3"), "9876543")
        self.assertEqual(B.normalizar_matricula("987654-3"), "9876543")
        self.assertEqual(B.normalizar_matricula("9876543"), "9876543")
        for inv in (None, "", "   ", "000000", "000000-0", "123", "1111111"):
            self.assertIsNone(B.normalizar_matricula(inv), f"Matrícula inválida {inv!r} não deveria normalizar")

        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("109/2099", ["SAD-PSE-2099/97101 987.654-3 SERVIDOR GRAFIA PROFESSOR A B"]),
        )
        ato_id = self.banco.con.execute("SELECT id FROM ato WHERE numero = '109/2099'").fetchone()["id"]
        sha = self.banco.con.execute("SELECT sha256 FROM ato WHERE id = ?", (ato_id,)).fetchone()["sha256"]
        with self.banco.con:
            for idx, (proc, mat) in enumerate([
                ("SAD-PSE-2099/97102", "987654-3"),
                ("SAD-PSE-2099/97103", "9876543"),
                ("SAD-PSE-2099/97104", ""),
                ("SAD-PSE-2099/97105", "000000"),
                ("SAD-PSE-2099/97106", "123"),
            ], start=2):
                self.banco.con.execute(
                    "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                    "VALUES (?, ?, ?, 1, ?, 'SERVIDOR TESTE', ?, 'PROFESSOR', '{}', 'DEFERIDO', 't', 'PENDENTE', 1, ?)",
                    (f"dec_mat_{idx}", ato_id, sha, proc, mat, f"cl_mat_{idx}"),
                )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["series"]["unidades"]["servidores"]["total"], 1)
        self.assertEqual(p["series"]["unidades"]["servidores"]["linhas_sem_matricula_valida"], 3)
        self.assertEqual(p["series"]["unidades"]["pedidos_individuais"], 6)
        # Valores originais preservados no banco e na projeção
        mats_orig = {l["matricula"] for l in p["linhas"]}
        self.assertTrue({"987.654-3", "987654-3", "9876543"}.issubset(mats_orig))

    # 8. Processos diferentes com números semelhantes (órgãos e séries distintos)
    def test_08_processos_diferentes_numeros_semelhantes_nao_colidem(self):
        chaves = [
            B.chave_processo("SAD-PSE-2099/90123"),
            B.chave_processo("SEE-PRC-2099/90123"),
            B.chave_processo("SDS-OFI-2099/90123"),
            B.chave_processo("90123/2099", orgao="SEC.EST.SAUDE", serie="RESENHA"),
            B.chave_processo("90123/2099", orgao="SEC.EST.EDUCACAO", serie="RESENHA"),
        ]
        self.assertEqual(len(set(chaves)), 5, f"Colisão indevida em chaves de processo: {chaves}")

        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao(
                "110/2099",
                [
                    "SAD-PSE-2099/90123 980001-1 SERVIDOR UM PROFESSOR A B",
                    "SEE-PRC-2099/90123 980002-2 SERVIDOR DOIS PROFESSOR A B",
                    "SDS-OFI-2099/90123 980003-3 SERVIDOR TRES PROFESSOR A B",
                ],
            ),
        )
        ato_id = self.banco.con.execute("SELECT id FROM ato WHERE numero = '110/2099'").fetchone()["id"]
        sha = self.banco.con.execute("SELECT sha256 FROM ato WHERE id = ?", (ato_id,)).fetchone()["sha256"]
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_p4', ?, ?, 1, '90123/2099', 'SERVIDOR QUATRO', '980004-4', 'SEC.EST.SAUDE', 'PROFESSOR', '{}', 'DEFERIDO', 't4', 'PENDENTE', 1, 'cl_p4')",
                (ato_id, sha),
            )
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_p5', ?, ?, 1, '90123/2099', 'SERVIDOR CINCO', '980005-5', 'SEC.EST.EDUCACAO', 'PROFESSOR', '{}', 'DEFERIDO', 't5', 'PENDENTE', 1, 'cl_p5')",
                (ato_id, sha),
            )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["processos"], 5)
        self.assertEqual(p["indicadores"]["decisoes"], 5)

    # 9. AST e SFT normalizados sem alterar total geral + fundamentos normativos + Q U E D E F E R I U
    def test_09_ast_sft_normativos_e_merito_espacado_sem_alterar_total_geral(self):
        # 9a. Expressões normativas e espaçadas (Resenhas 140/2026, 013/2026, Leis estaduais)
        self.assertEqual(C.avaliar_grupo("PROFISSIONAIS DA EDUCACAO LEI 7.419/03")[0], "MAG")
        self.assertEqual(C.avaliar_grupo("PROFISSIONAIS DA SAUDE LEI 7.376/03")[0], "SSA")
        self.assertEqual(C.avaliar_grupo("CONFORME LEI ESTADUAL 11.359/2019")[0], "GAJ")
        self.assertEqual(C.avaliar_grupo("PROFISSIONAIS DA CGE LEI 8.698/08")[0], "ACI")
        self.assertEqual(C.avaliar_grupo("CONFORME LEI 14.386/2026")[0], "AST")
        self.assertEqual(C.avaliar_grupo("CONFORME LEI 8.427/07")[0], "SFT")
        self.assertEqual(
            C.avaliar_grupo("G R U P O  O C U P A C I O N A L  D E  A P O I O  J U D I C I A R I O  G A J - 1 7 0 0")[0],
            "GAJ",
        )
        # 9b. Reconhecimento seguro de Q U E D E F E R I U + testes negativos rigorosos
        self.assertEqual(K._merito(C.normalizar("q u e D E F E R IU o s P ro c e s s o s")), "DEFERIDO")
        self.assertEqual(K._merito(C.normalizar("q u e  D E F E R I U  o s  p r o c e s s o s")), "DEFERIDO")
        self.assertEqual(K._merito(C.normalizar("q u e  I N D E F E R I U  o s  p r o c e s s o s")), "INDEFERIDO")
        self.assertEqual(K._merito(C.normalizar("N A O  D E F E R I U  o  p e d i d o")), "NAO_INFORMADO")
        self.assertEqual(K._merito(C.normalizar("S E M  D E F E R I M E N T O  d o  p e d i d o")), "NAO_INFORMADO")
        self.assertEqual(K._merito(C.normalizar("NAO DEFERIU O PEDIDO")), "NAO_INFORMADO")
        self.assertEqual(K._merito(C.normalizar("SEM DEFERIMENTO PREVIO")), "NAO_INFORMADO")
        for falso_pos in (
            "C O M  D E F E R E N C I A  A O  C A R G O",
            "Q U E  R E F E R I U  A O  P R O C E S S O",
            "Q U E  D I F E R I U  D A  N O R M A",
            "Q U E  C O N F E R I U  O S  D A D O S",
            "P R E F E R I U  O U T R A  O P C A O",
        ):
            with self.subTest(falso_positivo=falso_pos):
                self.assertEqual(K._merito(C.normalizar(falso_pos)), "NAO_INFORMADO")

        # 9c. Classificação integrada: AST compatível, SFT compatível, TEC. ADM incompatível e STF ambíguo
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("111/2099", ["SAD-PSE-2099/98101 981001-1 SERVIDOR AST TECNICO ADMINISTRATIVO A B"], grupo="TEC. ADM."),
        )
        self.carregar_e_classificar(
            "d02", "2026-10-09",
            _resenha_progressao("112/2099", ["SAD-PSE-2099/98102 981002-2 SERVIDOR SFT AUDITOR FISCAL TRIBUTARIO A B"], grupo="STF - AUDITOR FISCAL TRIBUTARIO"),
        )
        self.carregar_e_classificar(
            "d03", "2026-10-09",
            _resenha_progressao("113/2099", ["SAD-PSE-2099/98103 981003-3 SERVIDOR INCOMP PROFESSOR DE EDUCACAO BAS A B"], grupo="TEC. ADM."),
        )
        self.carregar_e_classificar(
            "d04", "2026-10-09",
            _resenha_progressao("114/2099", ["SAD-PSE-2099/98104 981004-4 SERVIDOR AMBIG TECNICO ADMINISTRATIVO A B"], grupo="STF"),
        )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["decisoes"], 4)  # total geral inalterado!
        por_grupo = {g["grupo"]: g["total"] for g in p["series"]["por_grupo"]}
        self.assertEqual(por_grupo, {"AST": 1, "SFT": 1, "NAO_INFORMADO": 2})
        # Denominação original preservada em `grupo_expressao`
        por_res = {r["numero"]: (r["grupo"], r["grupo_expressao"]) for r in self.banco.con.execute("SELECT numero, grupo, grupo_expressao FROM ato")}
        self.assertEqual(por_res["111/2099"], ("AST", "TEC. ADM"))
        self.assertEqual(por_res["112/2099"], ("SFT", "STF"))
        self.assertEqual(por_res["113/2099"], (None, "TEC. ADM"))
        self.assertEqual(por_res["114/2099"], (None, "STF"))

    # 10. Resultado não informado, Tempo sem subcategoria e zero contaminação por outra_publicacao
    def test_10_resultado_nao_informado_tempo_sem_subcategoria_e_sem_contaminacao(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao("115/2099", ["SAD-PSE-2099/98201 982001-1 SERVIDOR PROG PROFESSOR A B"], modalidade="VERTICAL"),
        )
        # Inserir ato Tempo de Serviço sem subcategoria + resultado NAO_INFORMADO + outra_publicacao (Abono)
        sha = self.banco.con.execute("SELECT sha256 FROM arquivo LIMIT 1").fetchone()[0]
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO ato (id, gerencia, sha256, data_publicacao, tipo, numero, pagina, pagina_final, vinculo, natureza, eixo, subcategoria, resultado, texto, versao_regras, chave_logica) "
                "VALUES ('ato_ts_sem', 'GEDIV', ?, '2026-10-09', 'RESENHA', '116/2099', 2, 2, 'EXPRESSO', 'ORIGINAL', 'TEMPO_SERVICO', NULL, 'NAO_INFORMADO', 't', ?, 'cl_ts_sem')",
                (sha, C.VERSAO_REGRAS),
            )
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_ts_sem', 'ato_ts_sem', ?, 2, 'SAD-PSE-2099/98202', 'SERVIDOR TS', '982002-2', 'AGENTE', '{}', 'NAO_INFORMADO', 't', 'PENDENTE', 1, 'cl_dec_ts_sem')",
                (sha,),
            )
            self.banco.con.execute(
                "INSERT INTO outra_publicacao (id, gerencia, sha256, data_publicacao, tipo, titulo, pagina, vinculo, trecho) "
                "VALUES ('out_abono_1', 'GEDIV', ?, '2026-10-09', 'TEMA_FORA_DOS_EIXOS', 'Abono de Permanência — EC 103/2019', 3, 'EXPRESSO', 'Abono de Permanência')",
                (sha,),
            )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["decisoes"], 2)  # Abono NÃO contamina total!
        self.assertEqual(p["series"]["unidades"]["decisoes"]["nao_informado"], 1)
        self.assertEqual(p["series"]["tempo_sem_subcategoria"]["total"], 1)
        self.assertEqual(len(proj["rows"]), 2)
        self.assertEqual(len(proj["otherPublications"]), 1)
        self.assertEqual(proj["otherPublications"][0]["category"], "ABONO_PERMANENCIA")
        # Filtro explícito por SEM_SUBCATEGORIA funciona e fecha com 1
        p_sem, proj_sem = self.painel_e_proj(subcategoria="SEM_SUBCATEGORIA")
        _assert_particoes_exatas(self, p_sem, proj_sem)
        self.assertEqual(p_sem["indicadores"]["decisoes"], 1)
        self.assertEqual(p_sem["linhas"][0]["id"], "dec_ts_sem")

    # 11. Incompatibilidade de versao_regras + colisão Resenha 353/2099 + evento sem fonte + governança NAO_HOMOLOGADO
    def test_11_versao_regras_incompativel_colisao_353_e_governanca(self):
        # 11a. Colisão Resenha 353/2099: Progressão GAJ (processos 99101) vs Republicação de Abono (EC 103/2019, processos 99901)
        self.carregar_e_classificar(
            "d01", "2026-08-05",
            _resenha_progressao("353/2099", ["SAD-PSE-2099/99101 991001-1 SERVIDOR GAJ POLICIAL PENAL A B"], grupo="GAJ-1700"),
        )
        abono_repub = (
            "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
            "RESENHA Nº : 353/2099 - DEREH/GS/SEAD\n"
            "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
            "O SECRETÁRIO DE ESTADO DEFERIU os processos de ABONO DE PERMANÊNCIA (EC 103/2019), "
            "publicada no DOE de 05/08/2026:\n"
            "SAD-PSE-2099/99901 999001-9 SERVIDOR ABONO\n"
            "REPUBLICADA POR INCORREÇÃO\nPUBLIQUE-SE"
        )
        self.carregar_e_classificar("d02", "2026-08-12", abono_repub)
        # Inserir também um evento sintético de republicação de Abono citando 353/2099 caso classificador o tenha classificado como outra_publicacao
        sha2 = self.banco.con.execute("SELECT sha256 FROM arquivo ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        with self.banco.con:
            self.banco.con.execute(
                "INSERT OR IGNORE INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                "VALUES ('ev_353_abono', 'GEDIV', ?, '2026-08-12', NULL, 'REPUBLICACAO', 1, 'EXPRESSO', "
                "'[\"353/2099\"]', '[\"SAD-PSE-2099/99901\"]', '[\"2026-08-05\"]', "
                "'REPUBLICACAO ABONO DE PERMANENCIA EC 103/2019 Resenha 353/2099', 'PENDENTE_VINCULACAO')",
                (sha2,),
            )
        processo.sugerir_vinculos(self.banco)
        ev353 = self.banco.con.execute("SELECT estado, ato_sugerido_id, ato_original_id FROM evento WHERE id = 'ev_353_abono'").fetchone()
        self.assertEqual(ev353["estado"], "PENDENTE_VINCULACAO")
        self.assertIsNone(ev353["ato_sugerido_id"])
        self.assertIsNone(ev353["ato_original_id"])

        # 11b. Governança (Seção 8): nunca converte pendentes em conferidos nem vaza PII,
        # e sinaliza candidato a duplicidade OCR (sem jamais apagar decisões)
        ato_gaj = self.banco.con.execute("SELECT id, sha256 FROM ato WHERE numero = '353/2099'").fetchone()
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                "VALUES ('dec_ocr_cand', ?, ?, 1, 'SAD-PSE-2099/99102', 'SERVIDOR GAJ', '991001-1', 'POLICIAL PENAL', '{}', 'DEFERIDO', 't_ocr', 'PENDENTE', 1, 'cl_ocr_cand')",
                (ato_gaj["id"], ato_gaj["sha256"]),
            )
        dups_ocr = self.banco.candidatos_duplicidade_ocr()
        self.assertEqual(len(dups_ocr), 1)
        self.assertEqual(dups_ocr[0]["motivo"], "divergencia_ocr_1_digito")
        triagem = servico.avaliar_triagem_governanca(self.banco)
        self.assertEqual(triagem["estado_homologacao"], "NAO_HOMOLOGADO")
        self.assertFalse(triagem["conversao_automatica_executada"])
        self.assertEqual(triagem["decisoes_conferidas"], 0)
        self.assertEqual(triagem["decisoes_pendentes"], 2)
        self.assertEqual(triagem["candidatos_duplicidade_ocr"], 1)
        self.assertEqual(triagem["duvidas_documentais_especificas"]["decisoes_com_duvida"], 2)
        triagem_txt = json.dumps(triagem, ensure_ascii=False)
        self.assertNotIn("SERVIDOR GAJ", triagem_txt)
        self.assertNotIn("991001-1", triagem_txt)

        # 11c. Incompatibilidade explícita de `versao_regras` (seguro por padrão no público, detalhado na gerência)
        with self.banco.con:
            self.banco.con.execute("UPDATE classificacao SET versao_regras = 'gediv-2026.11.19-1'")

        # Padrão sem informar perfil == PUBLICO (seguro por padrão: sem contagens exatas nem telemetria interna)
        diag_pub = indicadores.diagnostico_versao_regras(self.banco)
        self.assertTrue(diag_pub["incompativel"])
        self.assertFalse(diag_pub["compativel"])
        self.assertEqual(diag_pub["versao_codigo"], C.VERSAO_REGRAS)
        self.assertEqual(diag_pub["versoes_no_banco"], [])
        self.assertIsNone(diag_pub["decisoes_afetadas"])
        self.assertIsNone(diag_pub["edicoes_por_versao"])
        self.assertIsNone(diag_pub["edicoes_incompativeis"])
        self.assertIn("Incompatibilidade técnica de versão de regras", diag_pub["mensagem"])
        self.assertNotRegex(diag_pub["mensagem"], r"\d+\s+decis")

        # Perfil interno autorizado (GERENCIA_PERFIL) recebe diagnóstico técnico completo
        diag_ger = indicadores.diagnostico_versao_regras(self.banco, perfil=GER)
        self.assertTrue(diag_ger["incompativel"])
        self.assertEqual(diag_ger["versoes_no_banco"], ["gediv-2026.11.19-1"])
        self.assertEqual(diag_ger["decisoes_afetadas"], 2)
        self.assertIn("Incompatibilidade de versão de regras", diag_ger["mensagem"])

        p_inc = indicadores.painel(self.banco, {"escopo": "pendente"}, GER)
        cob_inc = p_inc["meta"]["cobertura"]
        self.assertTrue(p_inc["meta"]["incompatibilidade_versao_regras"])
        self.assertTrue(cob_inc["incompatibilidade_versao_regras"])
        self.assertEqual(cob_inc["versao_regras_diagnostico"]["decisoes_afetadas"], 2)
        self.assertIn("Incompatibilidade de versão de regras", cob_inc["parecer"])
        self.assertEqual(p_inc["indicadores"]["decisoes"], 0)

    # 12. Isolamento público (1 a 4 decisões pendentes em versão incompatível + supressão secundária de tempo_sem_subcategoria)
    def test_12_isolamento_publico_1_a_4_pendentes_e_supressao_tempo_sem_subcategoria(self):
        # 12a. Testar de 1 a 4 decisões pendentes sob versão incompatível em /api/saude, /api/painel, /api/data e snapshot_publico.json
        for qtd in (1, 2, 3, 4):
            with self.subTest(decisoes_pendentes=qtd):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta_tmp:
                    pasta = Path(pasta_tmp)
                    b_iso = B.Banco(pasta / "observatorio.sqlite3")
                    try:
                        linhas_q = [
                            f"SAD-PSE-2099/{98500 + i} {985000 + i}-1 SERVIDOR PEND {i} PROFESSOR A B"
                            for i in range(qtd)
                        ]
                        TP.carregar(b_iso, f"iso_{qtd}", "2026-10-09", _resenha_progressao(f"90{qtd}/2099", linhas_q))
                        processo.classificar_pendentes(b_iso)
                        with b_iso.con:
                            b_iso.con.execute("UPDATE classificacao SET versao_regras = 'gediv-2026.11.19-1'")

                        # Snapshot público gerado e validado
                        snap = indicadores.gerar_snapshot_publico(b_iso)
                        indicadores.validar_snapshot_publico(snap)
                        snap_txt = json.dumps(snap, ensure_ascii=False)
                        self.assertNotIn("decisões vigentes bloqueadas", snap_txt)
                        self.assertNotRegex(snap["painel"]["meta"]["cobertura"]["parecer"], r"\d+\s+decis")
                        self.assertNotRegex(snap["data"]["meta"]["coverage"], r"\d+\s+decis")
                        self.assertIsNone(snap["painel"]["meta"]["versao_regras_diagnostico"]["decisoes_afetadas"])
                        self.assertIsNone(snap["data"]["meta"]["versaoRegrasDiagnostico"]["decisoes_afetadas"])
                        self.assertEqual(snap["data"]["otherPublications"], [])
                        self.assertEqual(snap["data"]["otherPublicationsSummary"]["total"], 0)
                        for chave_priv in ("unidades", "eventos_detalhados", "outras_publicacoes_resumo"):
                            self.assertNotIn(chave_priv, snap["painel"]["series"])

                        # validar_snapshot_publico deve recusar qualquer adulteração que exponha contagem interna ou otherPublications
                        for mut_nome, mut_fn in (
                            ("decisoes_afetadas_vazada", lambda s: s["painel"]["meta"]["versao_regras_diagnostico"].__setitem__("decisoes_afetadas", qtd)),
                            ("otherPublications_nao_vazio", lambda s: s["data"]["otherPublications"].append({"id": "out_x"})),
                            ("series_unidades_exposto", lambda s: s["painel"]["series"].__setitem__("unidades", {})),
                        ):
                            adulterado = copy.deepcopy(snap)
                            mut_fn(adulterado)
                            with self.assertRaises(ValueError, msg=f"Deveria recusar adulteração: {mut_nome}"):
                                indicadores.validar_snapshot_publico(adulterado)
                    finally:
                        b_iso.fechar()

                    # Verificar HTTP real em /api/saude, /api/painel e /api/data (público vs autenticado)
                    tok = "credencial-sintetica-etapa4cbis-0123456789"
                    srv = criar_servidor(pasta, tok, porta=0)
                    threading.Thread(target=srv.serve_forever, daemon=True).start()
                    try:
                        base = f"http://127.0.0.1:{srv.server_address[1]}"
                        with urllib.request.urlopen(f"{base}/api/saude", timeout=5) as r:
                            saude_pub = json.loads(r.read())
                        self.assertTrue(saude_pub["cobertura"]["incompatibilidade_versao_regras"])
                        self.assertIsNone(saude_pub["cobertura"]["versao_regras_diagnostico"]["decisoes_afetadas"])
                        self.assertEqual(saude_pub["cobertura"]["versao_regras_diagnostico"]["versoes_no_banco"], [])
                        self.assertNotRegex(saude_pub["cobertura"]["parecer"], r"\d+\s+decis")

                        req_saude_ger = urllib.request.Request(f"{base}/api/saude", headers={"Authorization": f"Bearer {tok}"})
                        with urllib.request.urlopen(req_saude_ger, timeout=5) as r:
                            saude_ger = json.loads(r.read())
                        self.assertEqual(saude_ger["cobertura"]["versao_regras_diagnostico"]["decisoes_afetadas"], qtd)

                        with urllib.request.urlopen(f"{base}/api/painel", timeout=5) as r:
                            painel_pub = json.loads(r.read())
                        self.assertTrue(painel_pub["meta"]["incompatibilidade_versao_regras"])
                        self.assertIsNone(painel_pub["meta"]["versao_regras_diagnostico"]["decisoes_afetadas"])
                        self.assertEqual((painel_pub["linhas"], painel_pub["resenhas"], painel_pub["eventos"]), ([], [], []))

                        with urllib.request.urlopen(f"{base}/api/data", timeout=5) as r:
                            data_pub = json.loads(r.read())
                        self.assertTrue(data_pub["meta"]["incompatibilidadeVersaoRegras"])
                        self.assertIsNone(data_pub["meta"]["versaoRegrasDiagnostico"]["decisoes_afetadas"])
                        self.assertEqual((data_pub["rows"], data_pub["events"], data_pub["otherPublications"]), ([], [], []))
                    finally:
                        srv.shutdown()
                        srv.server_close()

        # 12b. Supressão secundária de `tempo_sem_subcategoria` (impedir reconstrução por subtração)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta_ts:
            b_ts = B.Banco(Path(pasta_ts) / "ts_supressao.sqlite3")
            try:
                sha_ts = TP.carregar(b_ts, "ts_sup", "2026-10-09", _resenha_progressao("910/2099", ["SAD-PSE-2099/98801 988001-1 SERVIDOR AUX PROFESSOR A B"]))
                processo.classificar_pendentes(b_ts)
                with b_ts.con:
                    # Remover decisão auxiliar de progressão e inserir 10 TS-01 + 3 Tempo sem subcategoria (conferidas)
                    b_ts.con.execute("DELETE FROM decisao")
                    b_ts.con.execute("DELETE FROM ato")
                    b_ts.con.execute(
                        "INSERT INTO ato (id, gerencia, sha256, data_publicacao, tipo, numero, pagina, pagina_final, vinculo, natureza, eixo, subcategoria, resultado, texto, versao_regras, chave_logica) "
                        "VALUES ('ato_ts01', 'GEDIV', ?, '2026-10-09', 'RESENHA', '911/2099', 1, 1, 'EXPRESSO', 'ORIGINAL', 'TEMPO_SERVICO', 'TS-01', 'DEFERIDO', 't', ?, 'cl_ts01')",
                        (sha_ts, C.VERSAO_REGRAS),
                    )
                    b_ts.con.execute(
                        "INSERT INTO ato (id, gerencia, sha256, data_publicacao, tipo, numero, pagina, pagina_final, vinculo, natureza, eixo, subcategoria, resultado, texto, versao_regras, chave_logica) "
                        "VALUES ('ato_ts_ni', 'GEDIV', ?, '2026-10-09', 'RESENHA', '912/2099', 2, 2, 'EXPRESSO', 'ORIGINAL', 'TEMPO_SERVICO', NULL, 'DEFERIDO', 't', ?, 'cl_ts_ni')",
                        (sha_ts, C.VERSAO_REGRAS),
                    )
                    for i in range(10):
                        b_ts.con.execute(
                            "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                            "VALUES (?, 'ato_ts01', ?, 1, ?, 'SERVIDOR TS01', ?, 'AGENTE', '{}', 'DEFERIDO', 't', 'CONFERIDO', 1, ?)",
                            (f"d_ts01_{i}", sha_ts, f"SAD-PSE-2099/{98901 + i}", f"{989001 + i}-1", f"cl_d_ts01_{i}"),
                        )
                    for j in range(3):
                        b_ts.con.execute(
                            "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, cargo, detalhe, resultado, trecho, validacao, vigente, chave_logica) "
                            "VALUES (?, 'ato_ts_ni', ?, 2, ?, 'SERVIDOR TSNI', ?, 'AGENTE', '{}', 'DEFERIDO', 't', 'CONFERIDO', 1, ?)",
                            (f"d_tsni_{j}", sha_ts, f"SAD-PSE-2099/{98951 + j}", f"{989501 + j}-2", f"cl_d_tsni_{j}"),
                        )
                snap_ts = indicadores.gerar_snapshot_publico(b_ts)
                indicadores.validar_snapshot_publico(snap_ts)
                ts_sem_pub = snap_ts["painel"]["series"]["tempo_sem_subcategoria"]
                ts01_pub = next(x for x in snap_ts["painel"]["series"]["por_subcategoria"] if x["codigo"] == "TS-01")
                # Com 3 decisões sem subcategoria (< 5, suprimidas), TS-01 (única outra positiva) TAMBÉM é suprimida secundariamente
                self.assertIsNone(ts_sem_pub["total"])
                self.assertIsNone(ts01_pub["total"])
                self.assertEqual(ts01_pub["situacao"], "suprimido por privacidade (< 5)")

                # E `validar_snapshot_publico` deve recusar caso TS-01 fosse deixado visível junto com tempo_sem_subcategoria suprimido
                adul_sub = copy.deepcopy(snap_ts)
                next(x for x in adul_sub["painel"]["series"]["por_subcategoria"] if x["codigo"] == "TS-01")["total"] = 10
                with self.assertRaises(ValueError):
                    indicadores.validar_snapshot_publico(adul_sub)
            finally:
                b_ts.fechar()

    # 13. Eventos em processos coletivos: exige identificação individual inequívoca (nunca vincula o coletivo inteiro)
    def test_13_evento_em_processo_coletivo_exige_identificacao_individual(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao(
                "120/2099",
                [
                    "SAD-PSE-2099/96100 961001-1 SERVIDOR COLETIVO ALFA PROFESSOR A B",
                    "SAD-PSE-2099/96100 961002-2 SERVIDOR COLETIVO BETA PROFESSOR B C",
                    "SAD-PSE-2099/96100 961003-3 SERVIDOR COLETIVO GAMA PROFESSOR C D",
                ],
            ),
        )
        # Portaria A (ambígua): cita apenas o processo coletivo sem matrícula nem servidor
        port_ambigua = _portaria_sem_efeito("220/2099", "120/2099", ["SAD-PSE-2099/96100"])
        self.carregar_e_classificar("d02", "2026-10-15", port_ambigua)
        self.conferir_todas_decisoes()

        ato_orig = self.banco.con.execute("SELECT id FROM ato WHERE numero = '120/2099'").fetchone()["id"]
        ev_amb = self.banco.con.execute("SELECT * FROM evento ORDER BY rowid DESC LIMIT 1").fetchone()
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, ev_amb["id"], servico.VINCULAR, REV, JUST, ato_orig, True)
        # Evento permanece pendente e nenhuma decisão do processo coletivo foi vinculada ou excluída
        self.assertNotEqual(self.banco.con.execute("SELECT estado FROM evento WHERE id = ?", (ev_amb["id"],)).fetchone()[0], "VALIDADO")
        self.assertEqual(self.banco.eventos_decisoes(ev_amb["id"]), [])
        p_amb, proj_amb = self.painel_e_proj()
        _assert_particoes_exatas(self, p_amb, proj_amb)
        self.assertEqual((p_amb["indicadores"]["decisoes"], p_amb["indicadores"]["sem_efeito"]), (3, 0))

        # Portaria B (contraditória): matrícula de ALFA + nome de BETA -> recusada por ambiguidade
        port_contr = (
            "Portaria nº 221/2099 - DEREH\n"
            "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
            "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO RESOLVE TORNAR SEM EFEITO a Resenha nº 120/2099, "
            "publicada no DOE de 09/10/2026, referente à PROGRESSÃO FUNCIONAL, processo SAD-PSE-2099/96100, "
            "servidor SERVIDOR COLETIVO BETA, matrícula 961001-1.\nPUBLIQUE-SE"
        )
        self.carregar_e_classificar("d03", "2026-10-16", port_contr)
        ev_contr = self.banco.con.execute("SELECT * FROM evento WHERE data_publicacao = '2026-10-16'").fetchone()
        self.assertIsNotNone(ev_contr)
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, ev_contr["id"], servico.VINCULAR, REV, JUST, ato_orig, True)

        # Portaria C (inequívoca): processo coletivo + matrícula 961002-2 (BETA) -> vincula EXCLUSIVAMENTE 1 de 3
        port_ok = (
            "Portaria nº 222/2099 - DEREH\n"
            "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
            "O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO RESOLVE TORNAR SEM EFEITO a Resenha nº 120/2099, "
            "publicada no DOE de 09/10/2026, referente à PROGRESSÃO FUNCIONAL, exclusivamente quanto ao "
            "processo SAD-PSE-2099/96100, servidor SERVIDOR COLETIVO BETA, matrícula 961002-2.\nPUBLIQUE-SE"
        )
        self.carregar_e_classificar("d04", "2026-10-17", port_ok)
        ev_ok = self.banco.con.execute("SELECT * FROM evento WHERE data_publicacao = '2026-10-17'").fetchone()
        self.assertIsNotNone(ev_ok)
        res_ok = servico.revisar_evento(self.banco, ev_ok["id"], servico.VINCULAR, REV, JUST, ato_orig, True)
        self.assertEqual(res_ok["decisoes_vinculadas"], 1)

        p_dep, proj_dep = self.painel_e_proj()
        _assert_particoes_exatas(self, p_dep, proj_dep)
        self.assertEqual((p_dep["indicadores"]["decisoes"], p_dep["indicadores"]["processos"], p_dep["indicadores"]["sem_efeito"]), (2, 1, 1))
        self.assertEqual(p_dep["series"]["eventos_detalhados"]["decisoes_sem_efeito"], 1)
        mats_ativas = {l["matricula"] for l in p_dep["linhas"]}
        self.assertEqual(mats_ativas, {"961001-1", "961003-3"})

    # 14. Eventos sem destinatário, tratamento separado (FORA_DO_ACERVO) e compatibilidade temática na validação manual
    def test_14_evento_sem_destinatario_externo_e_incompatibilidade_tematica_manual(self):
        self.carregar_e_classificar(
            "d01", "2026-08-05",
            _resenha_progressao("353/2099", ["SAD-PSE-2099/96201 962001-1 SERVIDOR GAJ UM POLICIAL PENAL A B"], grupo="GAJ-1700"),
        )
        ts_txt = (
            "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO\n"
            "RESENHA Nº : 354/2099 - DEREH/GS/SEAD\n"
            "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS\n"
            "O DIRETOR resolve DEFERIR os processos de ANOTAÇÃO DE TEMPO DE SERVIÇO / CONTRIBUIÇÃO:\n"
            "SEC.EST.EDUCACAO SAD-PSE-2099/96202 962002-2 SERVIDOR TEMPO UM 0 100 0 200\nPUBLIQUE-SE"
        )
        self.carregar_e_classificar("d02", "2026-08-05", ts_txt)
        self.conferir_todas_decisoes()

        ato_prog = self.banco.con.execute("SELECT id, sha256 FROM ato WHERE numero = '353/2099'").fetchone()
        ato_ts = self.banco.con.execute("SELECT id FROM ato WHERE numero = '354/2099'").fetchone()

        # 14a. Evento TORNADO_SEM_EFEITO sem processo/matrícula/decisoes_ids: proibido validar sobre o acervo
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                "VALUES ('ev_se_vazio', 'GEDIV', ?, '2026-08-12', NULL, 'TORNADO_SEM_EFEITO', 1, 'EXPRESSO', "
                "'[\"353/2099\"]', '[]', '[\"2026-08-05\"]', 'TORNAR SEM EFEITO PROGRESSAO FUNCIONAL Resenha 353/2099', 'PENDENTE_VINCULACAO')",
                (ato_prog["sha256"],),
            )
            # Evento de Tempo de Serviço tentando ser vinculado manualmente ao ato de Progressão
            self.banco.con.execute(
                "INSERT INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                "VALUES ('ev_tema_trocado', 'GEDIV', ?, '2026-08-12', NULL, 'TORNADO_SEM_EFEITO', 1, 'EXPRESSO', "
                "'[\"353/2099\"]', '[\"SAD-PSE-2099/96201\"]', '[\"2026-08-05\"]', "
                "'TORNAR SEM EFEITO LICENCA ESPECIAL Resenha 353/2099 SAD-PSE-2099/96201', 'PENDENTE_VINCULACAO')",
                (ato_prog["sha256"],),
            )
            # Evento de Abono de Permanência (EC 103/2019) tentando ser vinculado manualmente ao ato GAJ 353/2099
            self.banco.con.execute(
                "INSERT INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                "VALUES ('ev_abono_manual', 'GEDIV', ?, '2026-08-12', NULL, 'REPUBLICACAO', 1, 'EXPRESSO', "
                "'[\"353/2099\"]', '[\"SAD-PSE-2099/96201\"]', '[\"2026-08-05\"]', "
                "'REPUBLICACAO ABONO DE PERMANENCIA EC 103/2019 Resenha 353/2099', 'PENDENTE_VINCULACAO')",
                (ato_prog["sha256"],),
            )
            # Evento comprovadamente anterior ao início da base (1999-07-28)
            self.banco.con.execute(
                "INSERT INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                "VALUES ('ev_anterior_1999', 'GEDIV', ?, '2026-08-12', NULL, 'TORNADO_SEM_EFEITO', 1, 'EXPRESSO', "
                "'[]', '[]', '[\"1999-07-28\"]', 'TORNAR SEM EFEITO ato publicado no DOE de 28/07/1999', 'PENDENTE_VINCULACAO')",
                (ato_prog["sha256"],),
            )

        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, "ev_se_vazio", servico.VINCULAR, REV, JUST, ato_prog["id"], True)
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, "ev_tema_trocado", servico.VINCULAR, REV, JUST, ato_prog["id"], True)
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, "ev_abono_manual", servico.VINCULAR, REV, JUST, ato_prog["id"], True)
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, "ev_anterior_1999", servico.VINCULAR, REV, JUST, ato_ts["id"], True)

        # 14b. Tratamento separado para atos anteriores/externos via servico.EXTERNO -> estado FORA_DO_ACERVO
        with self.assertRaises(servico.Recusada):
            servico.revisar_evento(self.banco, "ev_anterior_1999", servico.EXTERNO, REV, JUST, None, False)
        r_ext = servico.revisar_evento(self.banco, "ev_anterior_1999", servico.EXTERNO, REV, JUST, None, True)
        self.assertEqual(r_ext, {"alterados": 1, "estado": "FORA_DO_ACERVO", "decisoes_vinculadas": 0})
        r_ext_ab = servico.revisar_evento(self.banco, "ev_abono_manual", servico.EXTERNO, REV, JUST, None, True)
        self.assertEqual(r_ext_ab["estado"], "FORA_DO_ACERVO")

        # 14c. Mesmo que um banco legado contenha evento TORNADO_SEM_EFEITO VALIDADO sem alcance decisório,
        # o cartão `sem_efeito` NÃO registra evento sem decisão atingida definida
        with self.banco.con:
            self.banco.con.execute(
                "UPDATE evento SET estado = 'VALIDADO', ato_original_id = ? WHERE id = 'ev_se_vazio'",
                (ato_prog["id"],),
            )
        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["sem_efeito"], 0)
        self.assertEqual(p["series"]["eventos_detalhados"]["sem_efeito_atos"], 0)
        self.assertEqual(p["series"]["eventos_detalhados"]["decisoes_sem_efeito"], 0)
        self.assertEqual(p["series"]["eventos_detalhados"]["eventos_fora_do_acervo"], 2)
        self.assertEqual(p["apoio"]["eventos_fora_do_acervo"], 2)
        self.assertEqual(indicadores.painel(self.banco, {"cartao": "sem_efeito"}, GER)["linhas"], [])
        self.assertEqual(sum(1 for e in proj["events"] if e["validation"] == "externo"), 2)
        # Snapshot público mantém isolamento integral (apoio.eventos_fora_do_acervo == None)
        snap = indicadores.gerar_snapshot_publico(self.banco)
        indicadores.validar_snapshot_publico(snap)
        self.assertIsNone(snap["painel"]["apoio"]["eventos_fora_do_acervo"])

    # 15. Grupos com cargos mistos, desconhecidos ou similares não comprovados (AST)
    def test_15_ast_com_cargos_mistos_desconhecidos_ou_nao_comprovados_sem_alterar_total(self):
        # 15a. Allowlist estrita em catalogo.avaliar_grupo:
        # Cargos desconhecidos (ENGENHEIRO CIVIL, ADVOGADO), similares não comprovados (ASSISTENTE/AUXILIAR ADMINISTRATIVO)
        # e combinações mistas NÃO podem virar AST automaticamente.
        for cargos_bloqueados in (
            ["TECNICO ADMINISTRATIVO", "PROFESSOR DE EDUCACAO BASICA"],
            ["ENGENHEIRO CIVIL"],
            ["ADVOGADO"],
            ["ASSISTENTE ADMINISTRATIVO"],
            ["AUXILIAR ADMINISTRATIVO"],
            ["TECNICO ADMINISTRATIVO", "ENGENHEIRO CIVIL"],
            ["TECNICO ADMINISTRATIVO", "ASSISTENTE ADMINISTRATIVO"],
        ):
            with self.subTest(cargos_bloqueados=cargos_bloqueados):
                grp, exp, pend = C.avaliar_grupo("DO GRUPO TEC. ADM.", cargos=cargos_bloqueados)
                self.assertIsNone(grp)
                self.assertEqual(exp, "TEC. ADM")
                self.assertTrue(pend)

        grp_puro, exp_puro, pend_puro = C.avaliar_grupo(
            "DO GRUPO TEC. ADM.",
            cargos=["TECNICO ADMINISTRATIVO", "TEC. ADM."],
        )
        self.assertEqual((grp_puro, exp_puro, pend_puro), ("AST", "TEC. ADM", None))

        # 15b. Classificação completa + painel: resenha mista/desconhecida/assistente fica sem grupo,
        # resenha pura de Técnico Administrativo vira AST, e o total geral permanece intacto (Delta = 0).
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao(
                "130/2099",
                [
                    "SAD-PSE-2099/96301 963001-1 SERVIDOR MISTO UM TECNICO ADMINISTRATIVO A B",
                    "SAD-PSE-2099/96302 963002-2 SERVIDOR MISTO DOIS PROFESSOR DE EDUCACAO BAS B C",
                ],
                grupo="TEC. ADM.",
            ),
        )
        self.carregar_e_classificar(
            "d02", "2026-10-09",
            _resenha_progressao(
                "131/2099",
                [
                    "SAD-PSE-2099/96303 963003-3 SERVIDOR PURO UM TECNICO ADMINISTRATIVO A B",
                    "SAD-PSE-2099/96304 963004-4 SERVIDOR PURO DOIS TECNICO ADMINISTRATIVO B C",
                ],
                grupo="TEC. ADM.",
            ),
        )
        self.carregar_e_classificar(
            "d03", "2026-10-09",
            _resenha_progressao(
                "132/2099",
                [
                    "SAD-PSE-2099/96305 963005-5 SERVIDOR ENG UM ENGENHEIRO CIVIL A B",
                    "SAD-PSE-2099/96306 963006-6 SERVIDOR ADV DOIS ADVOGADO B C",
                ],
                grupo="TEC. ADM.",
            ),
        )
        self.carregar_e_classificar(
            "d04", "2026-10-09",
            _resenha_progressao(
                "133/2099",
                [
                    "SAD-PSE-2099/96307 963007-7 SERVIDOR ASSIS UM ASSISTENTE ADMINISTRATIVO A B",
                    "SAD-PSE-2099/96308 963008-8 SERVIDOR AUX DOIS AUXILIAR ADMINISTRATIVO B C",
                ],
                grupo="TEC. ADM.",
            ),
        )
        self.conferir_todas_decisoes()

        p, proj = self.painel_e_proj()
        _assert_particoes_exatas(self, p, proj)
        self.assertEqual(p["indicadores"]["decisoes"], 8)  # contagem geral preservada (Delta = 0)
        por_grupo = {g["grupo"]: g["total"] for g in p["series"]["por_grupo"]}
        self.assertEqual(por_grupo, {"AST": 2, "NAO_INFORMADO": 6})
        atos_map = {
            r["numero"]: (r["grupo"], r["grupo_expressao"], json.loads(r["pendencias"] or "[]"))
            for r in self.banco.con.execute("SELECT numero, grupo, grupo_expressao, pendencias FROM ato")
        }
        for num_pendente in ("130/2099", "132/2099", "133/2099"):
            self.assertIsNone(atos_map[num_pendente][0], num_pendente)
            self.assertEqual(atos_map[num_pendente][1], "TEC. ADM", num_pendente)
            self.assertTrue(any("TEC. ADM" in x for x in atos_map[num_pendente][2]), num_pendente)
        self.assertEqual(atos_map["131/2099"][0], "AST")
        self.assertEqual(atos_map["131/2099"][1], "TEC. ADM")

    # 16. Processo de decisão única exige compatibilidade de toda matrícula e identificação individual citada
    def test_16_processo_decisao_unica_exige_confirmacao_de_matricula_e_identificacao(self):
        self.carregar_e_classificar(
            "d01", "2026-10-09",
            _resenha_progressao(
                "140/2099",
                [
                    "SAD-PSE-2099/96401 964001-1 SERVIDOR UNICO UM PROFESSOR A B",
                    "SAD-PSE-2099/96402 964002-2 SERVIDOR UNICO DOIS PROFESSOR B C",
                    "SAD-PSE-2099/96403 964003-3 SERVIDOR ORIGINAL UNICO PROFESSOR C D",
                    "SAD-PSE-2099/96404 964004-4 SERVIDOR UNICO QUATRO PROFESSOR A B",
                    "SAD-PSE-2099/96405 964005-5 SERVIDOR UNICO CINCO PROFESSOR B C",
                    "SAD-PSE-2099/96406 964006-6 SERVIDOR UNICO SEIS PROFESSOR C D",
                ],
            ),
        )
        ato = self.banco.con.execute("SELECT id, sha256 FROM ato WHERE numero = '140/2099'").fetchone()
        # Remover matrícula da decisão 96401 e nome da decisão 96404 para testar não confirmação
        with self.banco.con:
            self.banco.con.execute("UPDATE decisao SET matricula = NULL WHERE processo = 'SAD-PSE-2099/96401'")
            self.banco.con.execute("UPDATE decisao SET servidor = NULL WHERE processo = 'SAD-PSE-2099/96404'")
        self.conferir_todas_decisoes()

        # 16a. Decisão sem matrícula + portaria citando matrícula não confirmável -> recusado (permanece pendente)
        # 16b. Decisão com matrícula + portaria citando matrícula extra não confirmada -> recusado
        # 16c. Portaria citando nome individual divergente (sem matrícula) -> recusado
        # 16d. Decisão sem nome + portaria citando nome individual -> recusado
        # 16e. Portaria multi-processo com uma matrícula divergente -> recusado
        # 16f. Portaria multi-processo com TODAS as matrículas compatíveis -> vincula exatamente as 2 decisões
        casos_ev = [
            ("ev_u_sem_mat", '["SAD-PSE-2099/96401"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processo SAD-PSE-2099/96401, matrícula 964001-1"),
            ("ev_u_mat_extra", '["SAD-PSE-2099/96402"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processo SAD-PSE-2099/96402, matrículas 964002-2 e 964999-9"),
            ("ev_u_nome_div", '["SAD-PSE-2099/96403"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processo SAD-PSE-2099/96403, do servidor SERVIDOR DIVERGENTE OUTRO, lotado na SEAD"),
            ("ev_u_sem_nome", '["SAD-PSE-2099/96404"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processo SAD-PSE-2099/96404, do servidor SERVIDOR NAO CONFIRMADO, lotado na SEAD"),
            ("ev_u_multi_div", '["SAD-PSE-2099/96405", "SAD-PSE-2099/96406"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processos SAD-PSE-2099/96405 (matrícula 964005-5) e SAD-PSE-2099/96406 (matrícula 964888-8)"),
            ("ev_u_multi_ok", '["SAD-PSE-2099/96405", "SAD-PSE-2099/96406"]', "TORNAR SEM EFEITO PROGRESSAO FUNCIONAL processos SAD-PSE-2099/96405 (matrícula 964005-5) e SAD-PSE-2099/96406 (matrícula 964006-6)"),
        ]
        with self.banco.con:
            for eid, procs_j, txt_e in casos_ev:
                self.banco.con.execute(
                    "INSERT INTO evento (id, gerencia, sha256, data_publicacao, ato_id, tipo, pagina, vinculo, "
                    "resenhas_citadas, processos_citados, publicacoes_citadas, texto, estado) "
                    "VALUES (?, 'GEDIV', ?, '2026-10-15', NULL, 'TORNADO_SEM_EFEITO', 1, 'EXPRESSO', "
                    "'[\"140/2099\"]', ?, '[\"2026-10-09\"]', ?, 'PENDENTE_VINCULACAO')",
                    (eid, ato["sha256"], procs_j, txt_e),
                )

        for eid_rec in ("ev_u_sem_mat", "ev_u_mat_extra", "ev_u_nome_div", "ev_u_sem_nome", "ev_u_multi_div"):
            with self.subTest(evento_recusado=eid_rec):
                with self.assertRaises(servico.Recusada):
                    servico.revisar_evento(self.banco, eid_rec, servico.VINCULAR, REV, JUST, ato["id"], True)
                self.assertEqual(
                    self.banco.con.execute("SELECT estado FROM evento WHERE id = ?", (eid_rec,)).fetchone()[0],
                    "PENDENTE_VINCULACAO",
                )
                self.assertEqual(self.banco.eventos_decisoes(eid_rec), [])

        # Todas as 6 decisões continuam ativas enquanto nenhum evento incompatível foi aceito
        p_antes, proj_antes = self.painel_e_proj()
        _assert_particoes_exatas(self, p_antes, proj_antes)
        self.assertEqual((p_antes["indicadores"]["decisoes"], p_antes["indicadores"]["sem_efeito"]), (6, 0))

        # Evento multi-processo com TODAS as matrículas confirmadas vincula exatamente 2 decisões
        r_ok = servico.revisar_evento(self.banco, "ev_u_multi_ok", servico.VINCULAR, REV, JUST, ato["id"], True)
        self.assertEqual(r_ok["decisoes_vinculadas"], 2)
        p_dep, proj_dep = self.painel_e_proj()
        _assert_particoes_exatas(self, p_dep, proj_dep)
        self.assertEqual((p_dep["indicadores"]["decisoes"], p_dep["indicadores"]["sem_efeito"]), (4, 1))
        self.assertEqual(p_dep["series"]["eventos_detalhados"]["decisoes_sem_efeito"], 2)


if __name__ == "__main__":
    unittest.main()
