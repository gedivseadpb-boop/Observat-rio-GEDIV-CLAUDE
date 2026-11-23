"""Gera e valida o pacote estático 100% sintético do Painel Unificado GEDIV para GitHub Pages.

- Usa o painel real `observatorio/web/unificado/index.html` (Delicadeza Visual · 240 cores HEX).
- Gera base SQLite temporária descartável com dados 100% SINTÉTICOS (ano 2099, matrículas 950.xxx-x,
  nomes fictícios) sem tocar nos bancos originais e sem depender das rotas Python `/api/*`.
- Desabilita de forma clara e honesta funções que exigem backend (login gerencial real, conferência,
  auditoria, conflitos e alterações), sem simular segurança por senha em JavaScript.
- Valida o artefato gerado contra vazamento de PII, credenciais, arquivos não autorizados e cores novas.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from observatorio.gerencias.gediv import processo  # noqa: E402
from observatorio.nucleo.banco import Banco  # noqa: E402
from observatorio.painel import adaptador, indicadores  # noqa: E402
from observatorio.revisao import servico  # noqa: E402

HTML_ORIGEM = RAIZ / "observatorio" / "web" / "unificado" / "index.html"
PALETA_JSON = RAIZ / "observatorio" / "web" / "unificado" / "paleta-aprovada.json"
REVISOR_SINT = "Equipe Demonstração Sintética"
JUST_SINT = "Registro exclusivamente sintético para demonstração pública estática"


def _mat(n: int) -> str:
    base = 950000 + n
    dv = (base % 9) + 1
    s = f"{base:06d}"
    return f"{s[:3]}.{s[3:]}-{dv}"


def _proc(n: int) -> str:
    return f"SAD-PSE-2099/{n:05d}"


def _nome(n: int) -> str:
    prefixos = [
        "ALFA", "BETA", "GAMA", "DELTA", "EPSILON", "ZETA", "ETA", "TETA", "IOTA", "KAPA",
        "LAMBDA", "SIGMA", "OMEGA", "PRIMA", "NOVA", "SOLAR", "LUNAR", "ASTRAL", "VERDE", "AZUL",
    ]
    sobrenomes = ["SILVA", "COSTA", "PEREIRA", "OLIVEIRA", "SANTOS", "LIMA", "SOUZA", "ALMEIDA", "ROCHA", "DIAS"]
    return f"SERVIDOR FICTICIO {prefixos[n % len(prefixos)]} {prefixos[(n // len(prefixos)) % len(prefixos)]} {sobrenomes[n % len(sobrenomes)]}"


def _carregar_edicao(banco: Banco, tag: str, data_iso: str, blocos: list[str], num_doe: str) -> str:
    texto = "\n\n".join(blocos)
    sha = f"{tag:0<64}"[:64]
    url = f"manual:sintetico-{data_iso}"
    banco.registrar_descoberta("manual", url, data_iso, "normal", int(num_doe), f"DOE sintético {data_iso}")
    pub = banco.publicacao("manual", url)
    banco.registrar_arquivo(pub["id"], sha, len(texto.encode("utf-8")), f"doe_sintetico_{data_iso}.pdf")
    banco.registrar_leitura(
        sha,
        "LIDA",
        "sintetico_pages",
        [{
            "numero": 1,
            "metodo": "TEXTO",
            "colunas": 1,
            "texto": texto,
            "qualidade": "OK",
            "palavras": len(texto.split()),
        }],
        num_doe,
        data_iso,
        None,
    )
    return sha


def _resenha_prog(
    num: str,
    modalidade: str,
    grupo_txt: str,
    resultado_header: str,
    linhas: list[tuple[int, int, str, str, str]],
    *,
    com_classe: bool = False,
) -> str:
    cab = (
        "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
        f"RESENHA Nº {num} - SEAD/GEDIV\n"
        "O SECRETARIO DE ESTADO DA ADMINISTRACAO, no uso de suas atribuicoes, "
        f"{resultado_header} os pedidos de PROGRESSAO {modalidade.upper()} do grupo {grupo_txt} "
        "dos servidores abaixo relacionados:\n"
        "PROCESSO MATRICULA NOME CARGO LOTACAO" + (" CLASSE" if com_classe else "")
    )
    corpo = [
        f"{_proc(p_idx)} {_mat(s_idx)} {_nome(s_idx)} {cargo} {lotacao}" + (f" {cl}" if com_classe and cl else "")
        for p_idx, s_idx, cargo, lotacao, cl in linhas
    ]
    return cab + "\n" + "\n".join(corpo) + "\nPUBLIQUE-SE."


def _resenha_tempo(num: str, assunto_txt: str, resultado_header: str, linhas: list[tuple[int, int, str, str]]) -> str:
    cab = (
        "SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD\n"
        f"RESENHA Nº {num} - SEAD/GEDIV\n"
        f"O SECRETARIO DE ESTADO DA ADMINISTRACAO {resultado_header} os processos de {assunto_txt}:\n"
        "PROCESSO MATRICULA NOME CARGO LOTACAO"
    )
    corpo = [f"{_proc(p_idx)} {_mat(s_idx)} {_nome(s_idx)} {cargo} {lotacao}" for p_idx, s_idx, cargo, lotacao in linhas]
    return cab + "\n" + "\n".join(corpo) + "\nPUBLIQUE-SE."


def _bloco_outra(titulo: str, corpo: str) -> str:
    return f"SECRETARIA DE ESTADO DA ADMINISTRACAO - SEAD / GEDIV\n{titulo}\n{corpo}\nPUBLIQUE-SE."


def gerar_dados_sinteticos_publicos() -> dict:
    """Constrói um payload JSON 100% sintético para demonstração estática (sem backend e sem dados reais)."""
    with tempfile.TemporaryDirectory(prefix="gediv-pages-sint-") as tmp:
        banco = Banco(Path(tmp) / "sintetico.sqlite3")
        try:
            # Edição 1 — Jun/2026
            _carregar_edicao(banco, "a1", "2026-06-18", [
                _resenha_prog("101/2026", "VERTICAL", "MAG", "DEFERIU", [
                    (101, 1, "PROFESSOR DE EDUCACAO BASICA", "SEE", "A B"),
                    (102, 2, "PROFESSOR DE EDUCACAO BASICA", "SEE", "B C"),
                    (103, 3, "PROFESSOR DE EDUCACAO BASICA", "SEE", "C D"),
                    (104, 4, "PROFESSOR DE EDUCACAO BASICA", "SEE", "D E"),
                    (105, 5, "PROFESSOR DE EDUCACAO BASICA", "SEE", "E F"),
                    (106, 6, "PROFESSOR DE EDUCACAO BASICA", "SEE", "B C"),
                ], com_classe=True),
                _resenha_prog("102/2026", "VERTICAL", "TEC. ADM", "DEFERIU", [
                    (107, 7, "TECNICO ADMINISTRATIVO", "SEAD", "A B"),
                    (108, 8, "TECNICO ADMINISTRATIVO", "SEAD", "B C"),
                    (109, 9, "TECNICO ADMINISTRATIVO", "SEAD", "C D"),
                    (110, 10, "TECNICO ADMINISTRATIVO", "SEAD", "D E"),
                    (111, 11, "TECNICO ADMINISTRATIVO", "SEAD", "B C"),
                ], com_classe=True),
                _resenha_prog("103/2026", "HORIZONTAL", "GAJ", "DEFERIU", [
                    (112, 12, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (113, 13, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (114, 14, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (115, 15, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (116, 16, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                ]),
                _resenha_tempo("104/2026", "ANOTACAO DE TEMPO DE SERVICO/CONTRIBUICAO", "DEFERIU", [
                    (117, 17, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (118, 18, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (119, 19, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (120, 20, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (121, 21, "AGENTE ADMINISTRATIVO", "SEAD"),
                ]),
                _bloco_outra(
                    "PORTARIA Nº 041/2026 - ABONO DE PERMANENCIA - SEAD/GEDIV",
                    f"CONCEDER ABONO DE PERMANENCIA ao servidor {_nome(91)}, matricula {_mat(91)}, processo {_proc(901)}.",
                ),
            ], "18001")

            # Edição 2 — Jul/2026
            _carregar_edicao(banco, "b2", "2026-07-22", [
                _resenha_prog("201/2026", "VERTICAL", "STF", "DEFERIU", [
                    (201, 22, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ", "A B"),
                    (202, 23, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ", "B C"),
                    (203, 24, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ", "C D"),
                    (204, 25, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ", "D E"),
                    (205, 26, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ", "E F"),
                ], com_classe=True),
                _resenha_prog("202/2026", "VERTICAL", "SSA", "DEFERIU", [
                    (206, 27, "ENFERMEIRO", "SES", "A B"),
                    (207, 28, "ENFERMEIRO", "SES", "B C"),
                    (208, 29, "MEDICO", "SES", "C D"),
                    (209, 30, "FARMACEUTICO", "SES", "D E"),
                    (210, 31, "FISIOTERAPEUTA", "SES", "B C"),
                ], com_classe=True),
                _resenha_prog("203/2026", "HORIZONTAL", "MAG", "DEFERIU", [
                    (211, 32, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                    (212, 33, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                    (213, 34, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                    (214, 35, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                    (215, 36, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                ]),
                _resenha_tempo("204/2026", "LICENCA ESPECIAL", "DEFERIU", [
                    (216, 37, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (217, 38, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (218, 39, "TECNICO ADMINISTRATIVO", "SEAD"),
                    (219, 40, "ENFERMEIRO", "SES"),
                    (220, 41, "AGENTE ADMINISTRATIVO", "SEAD"),
                ]),
                _bloco_outra(
                    "PORTARIA Nº 072/2026 - ABONO DE PERMANENCIA - SEAD/GEDIV",
                    f"CONCEDER ABONO DE PERMANENCIA ao servidor {_nome(92)}, matricula {_mat(92)}, processo {_proc(902)}.",
                ),
            ], "18025")

            # Edição 3 — Ago/2026
            _carregar_edicao(banco, "c3", "2026-08-19", [
                _resenha_prog("301/2026", "VERTICAL", "FAP", "INDEFERIU", [
                    (301, 42, "FISCAL AGROPECUARIO", "SEDAP", ""),
                    (302, 43, "FISCAL AGROPECUARIO", "SEDAP", ""),
                    (303, 44, "FISCAL AGROPECUARIO", "SEDAP", ""),
                    (304, 45, "FISCAL AGROPECUARIO", "SEDAP", ""),
                    (305, 46, "FISCAL AGROPECUARIO", "SEDAP", ""),
                ]),
                _resenha_prog("302/2026", "HORIZONTAL", "GPC", "DEFERIU", [
                    (306, 47, "AGENTE DE INVESTIGACAO", "SEDS", ""),
                    (307, 48, "AGENTE DE INVESTIGACAO", "SEDS", ""),
                    (308, 49, "ESCRIVAO DE POLICIA", "SEDS", ""),
                    (309, 50, "PERITO CRIMINAL", "SEDS", ""),
                    (310, 51, "AGENTE DE INVESTIGACAO", "SEDS", ""),
                ]),
                _resenha_tempo("303/2026", "CONVERSAO DE FERIAS EM TEMPO DE SERVICO", "DEFERIU", [
                    (311, 52, "TECNICO ADMINISTRATIVO", "SEAD"),
                    (312, 53, "TECNICO ADMINISTRATIVO", "SEAD"),
                    (313, 54, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (314, 55, "ANALISTA DE SISTEMAS", "SEAD"),
                    (315, 56, "ENFERMEIRO", "SES"),
                ]),
                _resenha_tempo("304/2026", "DESAVERBACAO DE TEMPO DE SERVICO", "INDEFERIU", [
                    (316, 57, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (317, 58, "TECNICO ADMINISTRATIVO", "SEAD"),
                ]),
                _resenha_tempo("305/2026", "LICENCA PARA TRATAR DE INTERESSES PARTICULARES", "INDEFERIU", [
                    (318, 59, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (319, 60, "TECNICO ADMINISTRATIVO", "SEAD"),
                ]),
                _resenha_tempo("306/2026", "DESISTENCIA DE LICENCA PARA TRATAR DE INTERESSES PARTICULARES", "DEFERIU", [
                    (320, 61, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (321, 62, "ENFERMEIRO", "SES"),
                ]),
                _resenha_tempo("307/2026", "CONVERSAO DE LICENCA ESPECIAL EM TEMPO DE SERVICO", "DEFERIU", [
                    (322, 63, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (323, 64, "TECNICO ADMINISTRATIVO", "SEAD"),
                ]),
                _bloco_outra(
                    "PORTARIA Nº 108/2026 - ABONO DE PERMANENCIA - SEAD/GEDIV",
                    f"CONCEDER ABONO DE PERMANENCIA ao servidor {_nome(93)}, matricula {_mat(93)}, processo {_proc(903)}.",
                ),
            ], "18052")

            # Edição 4 — Set/2026
            _carregar_edicao(banco, "d4", "2026-09-24", [
                _resenha_prog("401/2026", "HORIZONTAL", "TEC. ADM", "DEFERIU", [
                    (401, 65, "TECNICO ADMINISTRATIVO", "SEAD", ""),
                    (402, 66, "TECNICO ADMINISTRATIVO", "SEAD", ""),
                    (403, 67, "TECNICO ADMINISTRATIVO", "SEAD", ""),
                    (404, 68, "TECNICO ADMINISTRATIVO", "SEAD", ""),
                    (405, 69, "TECNICO ADMINISTRATIVO", "SEAD", ""),
                ]),
                _resenha_prog("402/2026", "HORIZONTAL", "SSA", "INDEFERIU", [
                    (406, 70, "ENFERMEIRO", "SES", ""),
                    (407, 71, "ENFERMEIRO", "SES", ""),
                    (408, 72, "TECNICO DE ENFERMAGEM", "SES", ""),
                    (409, 73, "MEDICO", "SES", ""),
                    (410, 74, "FARMACEUTICO", "SES", ""),
                ]),
                _resenha_prog("403/2026", "VERTICAL", "MAG", "DEFERIU", [
                    (490, 75, "PROFESSOR DE EDUCACAO BASICA", "SEE", "A B"),
                    (490, 76, "PROFESSOR DE EDUCACAO BASICA", "SEE", "B C"),
                    (490, 77, "PROFESSOR DE EDUCACAO BASICA", "SEE", "C D"),
                    (490, 78, "PROFESSOR DE EDUCACAO BASICA", "SEE", "D E"),
                ], com_classe=True),
                _resenha_tempo("404/2026", "TEMPO DE SERVICO", "DEFERIU", [
                    (411, 79, "TECNICO ADMINISTRATIVO", "SEAD"),
                    (412, 80, "AGENTE ADMINISTRATIVO", "SEAD"),
                ]),
                _resenha_prog("405/2026", "VERTICAL", "TEC. ADM", "DEFERIU", [
                    (413, 81, "ENGENHEIRO CIVIL", "SEINFRA", "B C"),
                    (414, 82, "ADVOGADO", "SEAD", "C D"),
                ], com_classe=True),
                _bloco_outra(
                    "PORTARIA Nº 149/2026 - ABONO DE PERMANENCIA - SEAD/GEDIV",
                    f"CONCEDER ABONO DE PERMANENCIA ao servidor {_nome(94)}, matricula {_mat(94)}, processo {_proc(904)}.",
                ),
            ], "18080")

            # Edição 5 — Out/2026 (eventos modificadores)
            _carregar_edicao(banco, "e5", "2026-10-21", [
                _resenha_prog("101/2026", "VERTICAL", "MAG", "DEFERIU", [
                    (101, 1, "PROFESSOR DE EDUCACAO BASICA", "SEE", "A B"),
                    (102, 2, "PROFESSOR DE EDUCACAO BASICA", "SEE", "B C"),
                    (103, 3, "PROFESSOR DE EDUCACAO BASICA", "SEE", "C D"),
                    (104, 4, "PROFESSOR DE EDUCACAO BASICA", "SEE", "D E"),
                    (105, 5, "PROFESSOR DE EDUCACAO BASICA", "SEE", "E F"),
                    (106, 6, "PROFESSOR DE EDUCACAO BASICA", "SEE", "B C"),
                ], com_classe=True).replace("PUBLIQUE-SE.", "REPUBLICADA POR INCORRECAO\nPUBLIQUE-SE."),
                (
                    "Portaria nº 205/2026- DEREH Joao Pessoa, 20 de outubro de 2026\n"
                    "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, tendo em vista os relatorios da "
                    "GERENCIA EXECUTIVA DE CONCESSAO DE DIREITOS E VANTAGENS - SEAD/GEDIV,\n"
                    "R E S O L V E retificar a PROGRESSAO FUNCIONAL VERTICAL, grupo SSA, objeto do "
                    f"Processo nº {_proc(209)}, resenha 202/2026, publicado no D.O.E. de 22/07/2026, "
                    f"do servidor {_nome(30)}, matricula nº {_mat(30)}.\nPUBLIQUE-SE."
                ),
                (
                    "Portaria nº 210/2026- DEREH Joao Pessoa, 20 de outubro de 2026\n"
                    "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, tendo em vista os relatorios da "
                    "GERENCIA EXECUTIVA DE CONCESSAO DE DIREITOS E VANTAGENS - SEAD/GEDIV,\n"
                    "R E S O L V E tornar sem efeito o DEFERIMENTO DE PROGRESSAO FUNCIONAL VERTICAL, grupo MAG, "
                    f"objeto do Processo nº {_proc(490)}, resenha 403/2026, publicado no D.O.E. de 24/09/2026, "
                    f"exclusivamente em relacao aos servidores {_nome(75)}, matricula nº {_mat(75)}, "
                    f"e {_nome(76)}, matricula nº {_mat(76)}.\nPUBLIQUE-SE."
                ),
                (
                    "Portaria nº 215/2026- DEREH Joao Pessoa, 20 de outubro de 2026\n"
                    "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, tendo em vista os relatorios da "
                    "GERENCIA EXECUTIVA DE CONCESSAO DE DIREITOS E VANTAGENS - SEAD/GEDIV,\n"
                    "R E S O L V E tornar sem efeito a PROGRESSAO FUNCIONAL HORIZONTAL, "
                    "objeto do Processo nº SAD-PSE-2099/00001, resenha 012/2025, publicado no D.O.E. de 14/03/2025.\n"
                    "PUBLIQUE-SE."
                ),
                _resenha_prog("501/2026", "VERTICAL", "MAG", "DEFERIU", [
                    (501, 83, "PROFESSOR DE EDUCACAO BASICA", "SEE", "C D"),
                    (502, 84, "PROFESSOR DE EDUCACAO BASICA", "SEE", "D E"),
                    (503, 85, "PROFESSOR DE EDUCACAO BASICA", "SEE", "E F"),
                ], com_classe=True),
                _resenha_prog("502/2026", "HORIZONTAL", "GAJ", "DEFERIU", [
                    (504, 86, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (505, 87, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                ]),
                # Exemplos 100% sintéticos das situações sem nível A–F efetivado (separadas por motivo)
                _resenha_prog("503/2026", "VERTICAL", "ANS", "DEFERIU", [
                    (506, 112, "ANALISTA DE NIVEL SUPERIOR", "SEAD", ""),
                    (507, 113, "ANALISTA DE NIVEL SUPERIOR", "SEAD", ""),
                ], com_classe=False),
                _resenha_prog("504/2026", "VERTICAL", "MAG", "DEFERIU", [
                    (508, 114, "PROFESSOR DE EDUCACAO BASICA", "SEE", "D B"),
                    (509, 115, "PROFESSOR DE EDUCACAO BASICA", "SEE", "C C"),
                ], com_classe=True),
                _resenha_prog("505/2026", "VERTICAL", "GPC", "DEFERIU", [
                    (510, 116, "AGENTE DE INVESTIGACAO", "SEDS", "II III"),
                    (511, 117, "ESCRIVAO DE POLICIA", "SEDS", "III IV"),
                ], com_classe=True),
                _bloco_outra(
                    "INSTRUCAO NORMATIVA Nº 004/2026 - SEAD/GEDIV",
                    "Estabelece orientacoes sinteticas de padronizacao documental para fluxos de progressao e tempo de servico.",
                ),
            ], "18105")

            # Edição 6 — Nov/2026
            _carregar_edicao(banco, "f6", "2026-11-22", [
                _resenha_prog("601/2026", "VERTICAL", "AST", "DEFERIU", [
                    (601, 95, "TECNICO ADMINISTRATIVO", "SEAD", "A B"),
                    (602, 96, "TECNICO ADMINISTRATIVO", "SEAD", "B C"),
                    (603, 97, "TECNICO ADMINISTRATIVO", "SEAD", "C D"),
                ], com_classe=True),
                _resenha_prog("602/2026", "HORIZONTAL", "MAG", "DEFERIU", [
                    (604, 98, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                    (605, 99, "PROFESSOR DE EDUCACAO BASICA", "SEE", ""),
                ]),
                _resenha_tempo("603/2026", "ANOTACAO DE TEMPO DE SERVICO/CONTRIBUICAO", "DEFERIU", [
                    (606, 100, "AGENTE ADMINISTRATIVO", "SEAD"),
                    (607, 101, "TECNICO ADMINISTRATIVO", "SEAD"),
                ]),
                _resenha_prog("604/2026", "VERTICAL", "SSA", "DEFERIU", [
                    (608, 102, "ENFERMEIRO", "SES", "B C"),
                    (609, 103, "MEDICO", "SES", "C D"),
                    (610, 104, "FISIOTERAPEUTA", "SES", "D E"),
                ], com_classe=True),
                _resenha_prog("605/2026", "HORIZONTAL", "GAJ", "INDEFERIU", [
                    (611, 105, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                    (612, 106, "ANALISTA DE APOIO JUDICIARIO", "PGE", ""),
                ]),
                _resenha_tempo("606/2026", "LICENCA ESPECIAL", "DEFERIU", [
                    (613, 107, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
                    (614, 108, "TECNICO ADMINISTRATIVO", "SEAD"),
                ]),
                _resenha_prog("607/2026", "HORIZONTAL", "FAP", "DEFERIU", [
                    (615, 109, "FISCAL AGROPECUARIO", "SEDAP", ""),
                    (616, 110, "FISCAL AGROPECUARIO", "SEDAP", ""),
                ]),
                (
                    "Portaria nº 299/2026- DEREH Joao Pessoa, 17 de novembro de 2026\n"
                    "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, tendo em vista os relatorios da "
                    "GERENCIA EXECUTIVA DE CONCESSAO DE DIREITOS E VANTAGENS - SEAD/GEDIV,\n"
                    "R E S O L V E retificar a PROGRESSAO FUNCIONAL VERTICAL, grupo SSA, resenha 604/2026, "
                    "aguardando analise documental da GEDIV.\nPUBLIQUE-SE."
                ),
                _bloco_outra(
                    "PORTARIA Nº 288/2026 - ABONO DE PERMANENCIA - SEAD/GEDIV",
                    f"CONCEDER ABONO DE PERMANENCIA ao servidor {_nome(111)}, matricula {_mat(111)}, processo {_proc(905)}.",
                ),
            ], "18130")

            resumo_cls = processo.classificar_pendentes(banco)
            assert resumo_cls["com_erro"] == 0, f"Erro na classificação sintética: {resumo_cls}"

            conferir_nums = {
                "101/2026", "102/2026", "103/2026", "104/2026",
                "201/2026", "202/2026", "203/2026", "204/2026",
                "301/2026", "302/2026", "303/2026", "304/2026", "305/2026", "306/2026", "307/2026",
                "401/2026", "402/2026", "403/2026", "404/2026", "405/2026",
                "501/2026", "502/2026", "503/2026", "504/2026", "505/2026", "601/2026", "602/2026", "603/2026",
            }
            ato_por_num = {}
            for a in banco.con.execute("SELECT id, numero, natureza, vinculo FROM ato"):
                if a["natureza"] != "ORIGINAL":
                    continue
                ato_por_num[a["numero"]] = a["id"]
                if a["numero"] in conferir_nums:
                    servico.revisar_ato(
                        banco, a["id"], servico.CONFERIR, REVISOR_SINT, JUST_SINT,
                        confirma_fonte=True, confirma_vinculo=(a["vinculo"] != "EXPRESSO"),
                    )
                elif a["numero"] == "607/2026":
                    servico.revisar_ato(
                        banco, a["id"], servico.REJEITAR, REVISOR_SINT,
                        "Ato sintético rejeitado para demonstração da visão de rejeitados",
                    )

            d_misto = banco.con.execute(
                "SELECT id FROM decisao WHERE ato_id = ? AND matricula = ?",
                (ato_por_num["403/2026"], _mat(78)),
            ).fetchone()
            if d_misto:
                servico.revisar_decisoes(
                    banco, [d_misto["id"]], servico.CONFERIR, REVISOR_SINT,
                    "Ajuste sintético de processo coletivo misto",
                    confirma_fonte=True, correcoes={"resultado": "INDEFERIDO"},
                )

            for ev in banco.con.execute("SELECT * FROM evento ORDER BY data_publicacao, rowid"):
                res_cit = json.loads(ev["resenhas_citadas"] or "[]")
                if "101/2026" in res_cit and ev["tipo"] == "REPUBLICACAO":
                    servico.revisar_evento(
                        banco, ev["id"], servico.VINCULAR, REVISOR_SINT, JUST_SINT,
                        ato_original_id=ato_por_num["101/2026"], confirma_fonte=True,
                    )
                elif "202/2026" in res_cit and ev["tipo"] == "RETIFICACAO":
                    d_ret = banco.con.execute(
                        "SELECT id FROM decisao WHERE ato_id = ? AND matricula = ?",
                        (ato_por_num["202/2026"], _mat(30)),
                    ).fetchone()
                    servico.revisar_evento(
                        banco, ev["id"], servico.VINCULAR, REVISOR_SINT, JUST_SINT,
                        ato_original_id=ato_por_num["202/2026"], confirma_fonte=True,
                        decisoes_ids=[d_ret["id"]] if d_ret else None, resultado_novo="INDEFERIDO",
                    )
                elif "403/2026" in res_cit and ev["tipo"] == "TORNADO_SEM_EFEITO":
                    ds_se = banco.con.execute(
                        "SELECT id FROM decisao WHERE ato_id = ? AND matricula IN (?, ?)",
                        (ato_por_num["403/2026"], _mat(75), _mat(76)),
                    ).fetchall()
                    servico.revisar_evento(
                        banco, ev["id"], servico.VINCULAR, REVISOR_SINT, JUST_SINT,
                        ato_original_id=ato_por_num["403/2026"], confirma_fonte=True,
                        decisoes_ids=[r["id"] for r in ds_se],
                    )
                elif "12/2025" in res_cit or "012/2025" in res_cit:
                    servico.revisar_evento(
                        banco, ev["id"], servico.EXTERNO, REVISOR_SINT,
                        "Ato sintético anterior ao recorte contabilizado", confirma_fonte=True,
                    )

            # Projetar os dados sintéticos (conferidos + pendentes + rejeitados + eventos + outras publicações)
            perfil = indicadores.GERENCIA_PERFIL
            p_conf = indicadores.painel(banco, {"escopo": "conferido"}, perfil, proteger_publico=False)
            p_pend = indicadores.painel(banco, {"escopo": "pendente"}, perfil, proteger_publico=False)
            outras = indicadores.outras_publicacoes(banco, perfil)
            rej_rows = []
            for r in banco.con.execute(
                "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, "
                "d.cargo, d.detalhe, d.resultado, d.trecho, d.validacao, d.revisor, d.revisado_em, d.justificativa, "
                "a.numero AS resenha, a.sufixo, a.tipo, a.data_publicacao AS data, a.data_expediente, a.vinculo, "
                "a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, a.grupo_expressao, a.subcategoria, "
                "a.pendencias, a.chave_logica, a.gerencia AS gerencia_painel, "
                "SUBSTR(a.texto,1,1200) AS texto_identificacao, l.numero_edicao, l.data_edicao, 0 AS conflito_aberto "
                "FROM decisao d JOIN ato a ON a.id = d.ato_id JOIN leitura l ON l.sha256 = d.sha256 "
                "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'REJEITADO'"
            ).fetchall():
                lr = dict(r)
                lr.pop("texto_identificacao", None)
                lr["detalhe"] = json.loads(lr["detalhe"] or "{}")
                lr["pendencias"] = json.loads(lr["pendencias"] or "[]")
                lr["url_oficial"] = None
                lr["pdf_no_acervo"] = None
                rej_rows.append(lr)
            combinado = {
                **p_conf,
                "linhas": list(p_pend.get("linhas") or []) + list(p_conf.get("linhas") or []),
                "indicadores_conferido": p_conf.get("indicadores") or {},
                "eventos_detalhados_conferido": (p_conf.get("series") or {}).get("eventos_detalhados") or {},
            }
            snap = adaptador.projetar_para_dashboard_2910(combinado, outras, rej_rows)

            # Sanitização explícita para demonstração estática pública (ZERO credenciais, ZERO /api/pdf, ZERO campos internos)
            for row in snap["rows"] + snap.get("otherPublications", []):
                row["url"] = ""
                row["urlOficial"] = ""
                row["pdfNoAcervo"] = ""
                row["preliminaryReview"] = ""
                row.pop("revisor", None)
                row.pop("revisadoEm", None)
                row.pop("justificativa", None)
            for ev in snap.get("events", []):
                ev["url"] = ""
                ev["pdfNoAcervo"] = ""

            snap["backend"] = {
                "perfil": "demonstracao_estatica",
                "autenticado": False,
                "ehAdmin": False,
                "modoDemonstracaoEstatica": True,
                "versaoRegras": snap["backend"].get("versaoRegras"),
                "incompatibilidadeVersaoRegras": False,
                "versaoRegrasDiagnostico": {"compativel": True, "incompativel": False},
                "indicadores": p_conf.get("indicadores") or {},
                "apoio": {
                    "eventos_de_alteracao": p_conf["apoio"].get("eventos_de_alteracao"),
                    "eventos_sem_vinculo": p_conf["apoio"].get("eventos_sem_vinculo"),
                    "eventos_fora_do_acervo": p_conf["apoio"].get("eventos_fora_do_acervo"),
                    "decisoes_conferidas": p_conf["apoio"].get("decisoes_conferidas"),
                    "decisoes_pendentes": p_conf["apoio"].get("decisoes_pendentes"),
                    "decisoes_rejeitadas": p_conf["apoio"].get("decisoes_rejeitadas"),
                },
                "series": p_conf.get("series") or {},
                "resenhas": [],
            }
            snap["meta"]["version"] = "Painel Diário Oficial | GEDIV · Demonstração Estática (Dados Sintéticos)"
            snap["meta"]["coverage"] = (
                "Demonstração pública gratuita no GitHub Pages com 6 edições 100% sintéticas (Jun–Nov/2026). "
                "Nenhum dado real de servidor público."
            )
            snap["meta"]["automation"] = "Prévia estática somente leitura no GitHub Pages · sem rotas /api/*."
            snap["meta"]["personal"] = (
                "Demonstração estática com dados exclusivamente sintéticos. "
                "Login gerencial verdadeiro, conferência documental, auditoria e alterações de registros exigem servidor backend."
            )
            snap["dashboard"]["defaultScope"] = "conferido"
            return snap
        finally:
            banco.fechar()


def adaptar_html_estatico(html_orig: str) -> str:
    """Adapta `observatorio/web/unificado/index.html` para operar estaticamente no GitHub Pages.

    Preserva todas as 7 abas, cartões, gráficos, calendário, filtros, navegação e as 240 cores HEX (0 cores novas).
    Desabilita claramente funções que exigem backend (sem simular login/senha no JavaScript).
    """
    html = html_orig

    # 1. Favicon inline neutro (evita 404 de /favicon.ico no console do navegador)
    html = html.replace(
        '<meta name="color-scheme" content="light">',
        '<meta name="color-scheme" content="light"><link rel="icon" href="data:,">',
        1,
    )

    # 2. Carregamento estático direto de ./dados-sinteticos-publicos.json (zero chamadas /api/*)
    old_ready = """window.GEDIV_READY=(async()=>{
 let d=window.GEDIV_BOOTSTRAP;
 if(location.protocol!=='file:'&&!location.hostname.endsWith('github.io')){
  try{d=await window.GEDIV_FETCH_DATA();}catch(err){console.warn('Usando esqueleto inicial:',err);}
 }
 window.GEDIV_DATA=d;
 return d;
})();"""
    new_ready = """window.GEDIV_STATIC_DEMO=true;
window.GEDIV_FETCH_DATA=async()=>{
 const r=await fetch('./dados-sinteticos-publicos.json',{cache:'no-store',headers:{Accept:'application/json'}});
 if(!r.ok)throw new Error('HTTP '+r.status);
 return window.GEDIV_MODEL.acceptSnapshot(await r.json());
};
window.GEDIV_READY=(async()=>{
 let d=window.GEDIV_BOOTSTRAP;
 try{d=await window.GEDIV_FETCH_DATA();}catch(err){console.warn('Falha ao carregar dados sintéticos estáticos:',err);}
 window.GEDIV_DATA=d;
 return d;
})();"""
    assert old_ready in html, "Bloco window.GEDIV_READY esperado não encontrado"
    html = html.replace(old_ready, new_ready, 1)

    # 3. Forçar isStaticHost()=true no pacote estático e definir aviso honesto para funções que exigem backend
    old_static_host = "const isStaticHost=()=>location.hostname.endsWith('github.io')||location.protocol==='file:';"
    new_static_host = (
        "const isStaticHost=()=>true;\n"
        "const isStaticDemo=()=>!!(window.GEDIV_STATIC_DEMO||data.backend?.modoDemonstracaoEstatica);"
    )
    assert old_static_host in html, "isStaticHost esperado não encontrado"
    html = html.replace(old_static_host, new_static_host, 1)

    # 4. Em isPublicAgg(): no modo demonstração estática sintética, as rows sintéticas estão disponíveis para os controles
    old_pub_agg = """function isPublicAgg(){
 return !data.backend?.autenticado&&!(data.rows||[]).length&&!!(data.backend?.indicadores&&data.backend?.series);
}"""
    assert old_pub_agg in html  # já retorna false quando data.rows tem registros sintéticos

    # 5. Desabilitar de forma clara e honesta login falso, revisão, conflitos, auditoria e lotes (sem senha em JS)
    old_open_login = """ function openLoginModal(){
  $('#loginStatus').textContent='';$('#loginStatus').classList.remove('is-error');$('#loginDialog').showModal();
 }"""
    new_open_login = """ function openStaticBackendNotice(acao){
  const titulo=acao?`${acao} — recurso exclusivo com backend`:'Demonstração estática no GitHub Pages';
  const body=`<div class="reconcile-note" style="margin-top:0"><b>Prévia pública gratuita com dados 100% sintéticos (somente leitura).</b></div>
  <p>Esta publicação estática no <b>GitHub Pages</b> permite navegar livremente pelas <b>7 abas</b>, cartões, gráficos, calendário, filtros, tabela ampliada e exportações sobre uma base fictícia descartável.</p>
  <p><b>Funções desabilitadas nesta demonstração (exigem servidor backend Python/SQLite):</b></p>
  <ul><li><b>Login gerencial verdadeiro</b> (contas nominais e cookie <code>HttpOnly</code> — não há senha simulada em JavaScript);</li>
  <li><b>Conferência documental e alterações de registros</b> (<code>POST /api/revisao</code>);</li>
  <li><b>Resolução de conflitos (D2)</b> e <b>trilha de auditoria institucional (D3)</b>;</li>
  <li><b>Recebimento administrativo de lotes</b> e leitura de PDFs privados.</li></ul>`;
  openDialog(titulo,body);
 }
 function openLoginModal(){
  openStaticBackendNotice('Acesso gerencial');
 }"""
    assert old_open_login in html, "openLoginModal esperado não encontrado"
    html = html.replace(old_open_login, new_open_login, 1)

    # 6. Impedir abertura de modais de backend (revisão, conflitos, auditoria, lote) e exportação via /api
    for old_guard, new_guard in (
        (
            "function openReviewModal(targetType,items){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "function openReviewModal(targetType,items){\n if(isStaticDemo()){openStaticBackendNotice('Conferência documental');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            "async function openConflictsDialog(){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "async function openConflictsDialog(){\n if(isStaticDemo()){openStaticBackendNotice('Conflitos de reconciliação');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            "async function openAuditDialog(){\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
            "async function openAuditDialog(){\n if(isStaticDemo()){openStaticBackendNotice('Trilha de auditoria');return;}\n if(!data.backend?.autenticado){$('#loginDialog').showModal();return;}",
        ),
        (
            " $('#showPending').addEventListener('click',()=>{if(!data.backend?.autenticado){openLoginModal();return;}if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});",
            " $('#showPending').addEventListener('click',()=>{if(!isStaticDemo()&&!data.backend?.autenticado){openLoginModal();return;}if(S.validation!=='pendente'){S.validation='pendente';S.card='';S.page=0;S.selected='';commitHistory();render();}openFullTableModal();});",
        ),
    ):
        assert old_guard in html, f"Guarda esperada não encontrada: {old_guard[:60]}"
        html = html.replace(old_guard, new_guard, 1)

    # 7. Permitir exportação local CSV/XLSX dos dados 100% SINTÉTICOS no modo estático (sem /api/exportar)
    old_exp_csv = """function exportCsv(){
 if(!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 const localFallback=()=>{exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8','GEDIV-decisoes-filtradas.csv');toast('Lista filtrada gerada.');};
 if(!isStaticHost()){serverAuditedExport('csv',localFallback);return;}
 localFallback();
}"""
    new_exp_csv = """function exportCsv(){
 if(!isStaticDemo()&&!data.backend?.autenticado){toast('Lista individual (.csv) disponível apenas após login gerencial.');return;}
 const fname=isStaticDemo()?'GEDIV-demonstracao-sintetica.csv':'GEDIV-decisoes-filtradas.csv';
 exp.download(exp.csv(decisionRows()),'text/csv;charset=utf-8',fname);
 toast(isStaticDemo()?'CSV da demonstração sintética gerado.':'Lista filtrada gerada.');
}"""
    assert old_exp_csv in html, "exportCsv esperado não encontrado"
    html = html.replace(old_exp_csv, new_exp_csv, 1)

    old_exp_xlsx_guard = """ if(!isAuth){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }"""
    new_exp_xlsx_guard = """ if(!isAuth&&!isStaticDemo()){
  exp.download(exp.xlsx({'Resumo':summary}),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','GEDIV-resumo-publico.xlsx');
  toast('Resumo agregado gerado (dados individuais protegidos).');return;
 }"""
    assert old_exp_xlsx_guard in html, "exportXlsx guard esperado não encontrado"
    html = html.replace(old_exp_xlsx_guard, new_exp_xlsx_guard, 1)

    # 8. Em renderMeta(): exibir rótulo honesto de Demonstração Estática Sintética, manter seletor de escopo sintético visível e desabilitar ações de backend
    old_rm_chrome = """ const dDot=$('#delicateDot'),dLbl=$('#delicateAcctLabel'),dTag=$('#delicateRoleTag');
 if(dDot)dDot.classList.toggle('is-pub',!isAuth);
 if(dLbl)dLbl.textContent=isAuth?(usr?.nome||(isAdm?'Admin GEDIV':'Gerência GEDIV')):'Acesso gerencial';
 if(dTag)dTag.textContent=isAuth?(isAdm?'Admin':'Gerência'):'Público';
 const mu=$('#delicateMenuUser'),mm=$('#delicateMenuMeta'),la=$('#delicateLoginAct'),lo=$('#delicateLogoutAct'),ba=$('#delicateBatchAct'),ca=$('#delicateConflictsAct'),aa=$('#delicateAuditAct');
 if(mu)mu.textContent=isAuth?(usr?`${usr.nome} (${usr.usuario})`:'Sessão autenticada'):'Visitante (Público)';
 if(mm)mm.textContent=isAuth?`${Number(meta.edicoes)||0} edições · perfil ${isAdm?'Administração':'Gerência'}`:'Apenas indicadores agregados';
 if(la)la.hidden=isAuth;if(lo)lo.hidden=!isAuth;if(ba)ba.hidden=!isAdm;if(ca)ca.hidden=!isAuth;if(aa)aa.hidden=!isAuth;
 const totalBase=isAuth?data.rows.length:(pending+confCnt+rej);
 $('#receivedTotal').textContent=totalBase+' registros na base';
 $('#receivedMetaPill').textContent=`${pending} em conferência${rej?' · '+rej+(rej===1?' rejeitado':' rejeitados'):''}`;
 $('#receivedValidation').textContent=pending+' em conferência · '+confCnt+' conferidos · '+rej+' rejeitados';
 $('#validationScope').innerHTML=`<option value="pendente">Em conferência (${pending})</option><option value="conferido">Conferidos (${confCnt})</option>${isAuth?`<option value="rejeitado">Rejeitados (${rej})</option>`:''}`;
 $('#validationScope').value=S.validation;
 const proxyScope=$('#delicateScopeProxy');
 if(proxyScope){proxyScope.hidden=!isAuth;if(isAuth){proxyScope.innerHTML=$('#validationScope').innerHTML;proxyScope.value=S.validation;}}
 const expHead=$('#exportScopeHead');
 if(expHead){const mRec=typeof model==='function'?model():{original:[]};expHead.textContent=isAuth?`Recorte: ${views[S.view]?.[1]||'Visão'} · ${mRec.original.length} registro(s)`:'Modo público: apenas indicadores agregados';}
 const bt=$('#bannerTitle'),bx=$('#bannerText'),edC=Number(meta.edicoes)||0,scopeLbl=S.validation==='pendente'?'conferência pendente':S.validation==='rejeitado'?'registros rejeitados':'conferência registrada';
 if(bt)bt.textContent=edC?`Cobertura parcial (${edC} ${edC===1?'edição':'edições'}) · ${scopeLbl}`:'Cobertura em atualização';
 if(bx)bx.textContent=isAuth?'Registros extraídos sujeitos a conferência documental.':'Dados públicos agregados (sujeitos a conferência); registros individuais protegidos.';"""
    new_rm_chrome = """ const dDot=$('#delicateDot'),dLbl=$('#delicateAcctLabel'),dTag=$('#delicateRoleTag');
 if(dDot)dDot.classList.toggle('is-pub',true);
 if(dLbl)dLbl.textContent='Demonstração estática';
 if(dTag)dTag.textContent='Sintético';
 const mu=$('#delicateMenuUser'),mm=$('#delicateMenuMeta'),la=$('#delicateLoginAct'),lo=$('#delicateLogoutAct'),ba=$('#delicateBatchAct'),ca=$('#delicateConflictsAct'),aa=$('#delicateAuditAct');
 if(mu)mu.textContent='Demonstração estática (Somente leitura)';
 if(mm)mm.textContent='GitHub Pages · dados 100% sintéticos';
 if(la)la.hidden=true;if(lo)lo.hidden=true;if(ba)ba.hidden=true;if(ca)ca.hidden=true;if(aa)aa.hidden=true;
 const pendDemo=data.rows.filter(r=>r.validation==='pendente').length,confDemo=data.rows.filter(r=>r.validation==='conferido').length,rejDemo=data.rows.filter(r=>r.validation==='rejeitado').length;
 $('#receivedTotal').textContent=data.rows.length+' registros sintéticos na demonstração';
 $('#receivedMetaPill').textContent=`${pendDemo} em conferência · ${rejDemo} rejeitados`;
 $('#receivedValidation').textContent=`${pendDemo} em conferência · ${confDemo} conferidos · ${rejDemo} rejeitados`;
 $('#validationScope').innerHTML=`<option value="conferido">Conferidos (${confDemo})</option><option value="pendente">Em conferência (${pendDemo})</option><option value="rejeitado">Rejeitados (${rejDemo})</option>`;
 $('#validationScope').value=S.validation;
 const proxyScope=$('#delicateScopeProxy');
 if(proxyScope){proxyScope.hidden=false;proxyScope.innerHTML=$('#validationScope').innerHTML;proxyScope.value=S.validation;}
 const expHead=$('#exportScopeHead');
 if(expHead){const mRec=typeof model==='function'?model():{original:[]};expHead.textContent=`Demonstração sintética · ${views[S.view]?.[1]||'Visão'} (${mRec.original.length})`;}
 const bt=$('#bannerTitle'),bx=$('#bannerText'),edC=Number(meta.edicoes)||0,scopeLbl=S.validation==='pendente'?'fila pendente (sintética)':S.validation==='rejeitado'?'rejeitados (sintéticos)':'conferidos (sintéticos)';
 if(bt)bt.textContent=`Demonstração estática no GitHub Pages (${edC} edições · 100% sintético) · ${scopeLbl}`;
 if(bx)bx.textContent='Prévia pública gratuita somente leitura. Login gerencial, conferência documental, auditoria e alterações exigem backend.';"""
    assert old_rm_chrome in html, "Bloco renderMeta chrome esperado não encontrado"
    html = html.replace(old_rm_chrome, new_rm_chrome, 1)

    # 9. Sincronizar exportScopeHead também em sync()
    html = html.replace(
        "$('#exportScopeHead').textContent=isA?`Recorte: ${views[S.view]?.[1]||'Visão'} · ${mE.original.length} registro(s)`:'Modo público: apenas indicadores agregados';",
        "$('#exportScopeHead').textContent=`Demonstração sintética · ${views[S.view]?.[1]||'Visão'} (${mE.original.length})`;",
        1,
    )

    # 10. Garantir preservação estrita da paleta (240 cores HEX, 0 cores novas)
    orig_colors = {c.lower() for c in json.loads(PALETA_JSON.read_text(encoding="utf-8"))["cores_hex"]}
    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    new_colors = {c.lower() for c in hex_re.findall(html)}
    added = new_colors - orig_colors
    assert not added, f"Cores novas detectadas na prévia estática: {added}"
    return html


def validar_pacote_estatico(pasta: Path) -> None:
    """Validação fechada do artefato público antes de qualquer publicação no GitHub Pages."""
    arquivos = sorted(p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file())
    permitidos = {".nojekyll", "dados-sinteticos-publicos.json", "index.html"}
    assert set(arquivos) == permitidos, f"Arquivos fora da lista autorizada: {arquivos}"

    html = (pasta / "index.html").read_text(encoding="utf-8")
    dados_txt = (pasta / "dados-sinteticos-publicos.json").read_text(encoding="utf-8")
    dados = json.loads(dados_txt)

    # Proibições absolutas de privacidade e segurança
    for rotulo, texto in (("index.html", html), ("dados-sinteticos-publicos.json", dados_txt)):
        assert not re.search(r"SAD-PSE-202\d/\d+", texto), f"Processo real (202x) detectado em {rotulo}"
        assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", texto), f"CPF detectado em {rotulo}"
        assert not re.search(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|PreviaGediv2026!|previa\.gediv)", texto), f"Segredo/credencial em {rotulo}"
        assert not re.search(r"C:[\\/]+Users[\\/]+", texto, re.I), f"Caminho local Windows em {rotulo}"

    assert not re.search(r"/api/pdf/", dados_txt), "Rota /api/pdf/ encontrada no JSON público!"
    assert dados["backend"]["autenticado"] is False, "JSON estático nunca pode vir marcado como autenticado!"
    assert dados["backend"]["ehAdmin"] is False, "JSON estático nunca pode ter ehAdmin=True!"
    assert dados["backend"]["modoDemonstracaoEstatica"] is True
    assert len(dados["rows"]) > 0, "JSON sintético sem registros!"
    for r in dados["rows"]:
        assert str(r.get("process") or "").startswith("SAD-PSE-2099/"), f"Processo não sintético: {r.get('process')}"
        assert str(r.get("registration") or "").startswith("950."), f"Matrícula não sintética: {r.get('registration')}"
        assert "FICTICIO" in str(r.get("server") or "").upper(), f"Nome não sintético: {r.get('server')}"

    assert html.count("\r\n") == 0, "CRLF detectado em index.html"
    assert "./dados-sinteticos-publicos.json" in html
    assert "openStaticBackendNotice" in html

    # Garantir reconciliação matemática exata das 5 situações de Progressão Vertical A–F
    res_nv = (dados.get("backend") or {}).get("series", {}).get("resumo_nivel_vertical") or {}
    assert res_nv.get("total_vertical", 0) > 0, "Sem progressões verticais na demonstração sintética"
    for campo_sit in ("classificados", "indeferidos", "nao_determinados", "inconsistentes", "nao_aplica"):
        assert res_nv.get(campo_sit, 0) > 0, f"Situação vertical ausente na prévia sintética: {campo_sit}"
    soma_5 = (
        res_nv["classificados"]
        + res_nv["indeferidos"]
        + res_nv["nao_determinados"]
        + res_nv["inconsistentes"]
        + res_nv["nao_aplica"]
    )
    assert soma_5 == res_nv["total_vertical"], f"Partição vertical divergente: {soma_5} != {res_nv['total_vertical']}"
    assert (
        res_nv["indeferidos"] + res_nv["nao_determinados"] + res_nv["inconsistentes"] + res_nv["nao_aplica"]
        == res_nv["nao_identificados"]
    ), "Soma das 4 categorias sem nível diverge de nao_identificados"


def construir_pacote(saida: Path) -> Path:
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True, exist_ok=True)
    snap = gerar_dados_sinteticos_publicos()
    html = adaptar_html_estatico(HTML_ORIGEM.read_text(encoding="utf-8"))
    (saida / ".nojekyll").write_text("", encoding="utf-8", newline="\n")
    (saida / "index.html").write_text(html, encoding="utf-8", newline="\n")
    (saida / "dados-sinteticos-publicos.json").write_text(
        json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validar_pacote_estatico(saida)
    print(f"Pacote estático validado com sucesso em: {saida}")
    print(f"  index.html: {(saida / 'index.html').stat().st_size:,} bytes (240 cores HEX, 0 cores novas)")
    print(f"  dados-sinteticos-publicos.json: {(saida / 'dados-sinteticos-publicos.json').stat().st_size:,} bytes "
          f"({len(snap['rows'])} linhas sintéticas, {len(snap['events'])} eventos, {len(snap['otherPublications'])} outras)")
    return saida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, required=True, help="Diretório de saída do pacote estático público")
    args = ap.parse_args(argv)
    construir_pacote(args.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
