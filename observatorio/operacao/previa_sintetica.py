"""Gerador canônico único da base 100% sintética de homologação do Painel Unificado GEDIV.

Centraliza as 6 edições sintéticas de referência (Jun–Nov/2026, processos `SAD-PSE-2099/*`,
matrículas `950.xxx-x`, nomes `SERVIDOR FICTICIO ...`) para eliminar divergências entre:
- a prévia pública estática publicada no GitHub Pages (`scripts/preparar_previa_github_pages.py`);
- a base SQLite local de homologação com backend (`python -m observatorio.web --dados ...`).

Reconciliação de referência nas decisões conferidas:
- 42 Progressões Verticais: 29 A–F + 7 indeferidas (sem nível) + 2 deferidas sem nível +
  2 inconsistências A–F + 2 estrutura A–F não se aplica;
- 29 Progressões Horizontais;
- 25 decisões de Tempo de Serviço (TS-01 a TS-07 + subcategoria pendente).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..gerencias.gediv import processo
from ..nucleo.banco import Banco
from ..painel import indicadores
from ..revisao import servico

REVISOR_SINT = "Equipe Demonstração Sintética"
JUST_SINT = "Registro exclusivamente sintético para demonstração e homologação"

REFERENCIA_VERTICAL = {
    "total_vertical": 42,
    "classificados": 29,
    "indeferidos": 7,
    "nao_determinados": 2,
    "inconsistentes": 2,
    "nao_aplica": 2,
    "nao_identificados": 13,
}


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
        "sintetico_canonico",
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


def popular_banco_sintetico_canonico(banco: Banco) -> dict:
    """Popula um banco SQLite vazio com as 6 edições sintéticas canônicas, classifica e aplica
    conferências/eventos de referência para homologação consistente."""
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

    # Edição 5 — Out/2026 (eventos modificadores + 3 resenhas verticais sem nível A–F por motivo)
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
        _resenha_tempo("506/2026", "ABONO DE PERMANENCIA", "DEFERIU", [
            (512, 118, "PROFESSOR DE EDUCACAO BASICA", "SEE"),
            (513, 119, "TECNICO ADMINISTRATIVO", "SEAD"),
            (514, 120, "ENFERMEIRO", "SES"),
        ]),
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
        _resenha_tempo("608/2026", "ABONO DE PERMANENCIA", "DEFERIU", [
            (617, 121, "ANALISTA DE APOIO JUDICIARIO", "PGE"),
            (618, 122, "AUDITOR FISCAL TRIBUTARIO ESTADUAL", "SEFAZ"),
            (619, 123, "AGENTE ADMINISTRATIVO", "SEAD"),
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
        "501/2026", "502/2026", "503/2026", "504/2026", "505/2026", "506/2026",
        "601/2026", "602/2026", "603/2026", "608/2026",
    }
    ato_por_num: dict[str, str] = {}
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

    p_conf = indicadores.painel(banco, {"escopo": "conferido"}, indicadores.GERENCIA_PERFIL, proteger_publico=False)
    res_nv = (p_conf.get("series") or {}).get("resumo_nivel_vertical") or {}
    for chave, esperado in REFERENCIA_VERTICAL.items():
        atual = res_nv.get(chave)
        assert atual == esperado, f"Divergência na referência sintética ({chave}): {atual} != {esperado}"
    return {
        "edicoes": 6,
        "indicadores": p_conf.get("indicadores") or {},
        "resumo_nivel_vertical": res_nv,
    }


def _verificar_banco_somente_sintetico(caminho_banco: Path) -> None:
    """Recusa sobrescrever qualquer SQLite existente que contenha publicações não sintéticas."""
    if not caminho_banco.is_file():
        return
    banco = Banco(caminho_banco)
    try:
        nao_sint = banco.con.execute(
            "SELECT COUNT(*) FROM publicacao "
            "WHERE NOT ((fonte = 'manual' AND url LIKE 'manual:sintetico-%') "
            "OR url LIKE '%/previa-sintetica/%-sintetico.pdf')"
        ).fetchone()[0]
        if nao_sint > 0:
            raise ValueError(
                f"Recusado: {caminho_banco} contém {nao_sint} publicação(ões) não sintética(s). "
                "Use uma pasta dedicada exclusivamente à homologação sintética."
            )
    finally:
        banco.fechar()


def criar_base_local_sintetica(
    pasta_dados: Path | str,
    *,
    publicar_snapshot: bool = True,
) -> dict:
    """Cria ou recria com segurança uma base SQLite local 100% sintética alinhada ao conjunto
    canônico de referência (preservando `contas.sqlite3` caso já exista na pasta)."""
    pasta = Path(pasta_dados)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_banco = pasta / "observatorio.sqlite3"
    _verificar_banco_somente_sintetico(caminho_banco)

    for sufixo in ("", "-wal", "-shm"):
        arq = Path(str(caminho_banco) + sufixo)
        if arq.exists():
            arq.unlink()
    acervo_dir = pasta / "acervo"
    if acervo_dir.exists() and acervo_dir.is_dir():
        shutil.rmtree(acervo_dir)

    banco = Banco(caminho_banco)
    try:
        resumo = popular_banco_sintetico_canonico(banco)
        snap_info = None
        if publicar_snapshot:
            destino_snap = pasta / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
            snap = indicadores.publicar_snapshot_publico(banco, destino_snap)
            snap_info = {
                "arquivo": str(destino_snap),
                "gerado_em": snap.get("gerado_em"),
                "indicadores_publicos": (snap.get("painel") or {}).get("indicadores"),
                "resumo_nivel_vertical_publico": ((snap.get("painel") or {}).get("series") or {}).get("resumo_nivel_vertical"),
            }
        return {
            "pasta": str(pasta),
            "banco": str(caminho_banco),
            **resumo,
            "snapshot_publico": snap_info,
        }
    finally:
        banco.fechar()
