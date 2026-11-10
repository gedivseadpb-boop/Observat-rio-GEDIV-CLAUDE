"""Base de DEMONSTRAÇÃO: três Diários sintéticos passam pelo fluxo real (acervo → leitura → classificação)
e parte dos registros é conferida por um revisor fictício, para o painel poder ser avaliado com números.

Nada aqui é publicação real: pessoas, matrículas, processos e resenhas são fictícios, e as origens
ficam registradas como `manual:DEMONSTRACAO-...`. Use sempre uma pasta de dados separada.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..coleta import coletor
from ..gerencias.gediv import processo
from ..leitura import leitor
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from ..revisao import servico
from . import sintetico as S

REVISOR = "Revisor de demonstração (fictício)"


def documentos() -> list[tuple[date, bytes]]:
    d1 = S.diario(date(2026, 10, 2), 18685, [
        S.resenha_tempo(801, "30-09-2026", "ANOTAÇÃO DE TEMPO DE SERVIÇO / CONTRIBUIÇÃO", 1, 6),
        S.resenha_progressao(802, "30-09-2026", "HORIZONTAL", "Ocupacional de Apoio Judiciário GAJ-1700:", 10, 8, cargo="POLICIAL PENAL"),
        S.resenha_progressao(803, "30-09-2026", "HORIZONTAL", "MAG abaixo relacionados:", 20, 3, deferir=False, cargo="PROFESSOR DE EDUCACAO BAS"),
    ], (S.outros_atos(1) + S.resenha_tempo(804, "01-10-2026", "LICENÇA ESPECIAL", 30, 3),
        S.resenha_progressao(805, "01-10-2026", "VERTICAL", "TEC. ADM.", 40, 5, gediv=False) + S.outros_atos(2)))
    d2 = S.diario(date(2026, 10, 9), 18690, [
        S.resenha_progressao(811, "07-10-2026", "VERTICAL", "FAP-1300", 50, 4, cargo="FISCAL ESTADUAL AGROPECUARIO"),
        S.resenha_progressao(812, "07-10-2026", "HORIZONTAL", "SAUDE abaixo relacionados:", 60, 7, cargo="TECNICO DE ENFERMAGEM"),
        S.resenha_tempo(813, "07-10-2026", "DESISTÊNCIA DE LICENÇA PARA TRATAR DE INTERESSES PARTICULARES", 70, 1),
        S.resenha_tempo(814, "07-10-2026", "ANOTAÇÃO DE TEMPO DE SERVIÇO / CONTRIBUIÇÃO", 80, 4, deferir=False),
    ], (S.outros_atos(3), S.resenha_progressao(815, "08-10-2026", "VERTICAL", "TECNICO ADMINISTRATIVO - AST -", 90, 4)))
    republicada = S.resenha_tempo(801, "30-09-2026", "ANOTAÇÃO DE TEMPO DE SERVIÇO / CONTRIBUIÇÃO", 1, 6)
    republicada.insert(-1, "REPUBLICADA POR INCORREÇÃO")
    d3 = S.diario(date(2026, 10, 15), 18693, [
        S.portaria_sem_efeito(77, 803, 21), republicada,
        S.resenha_progressao(821, "13-10-2026", "VERTICAL", "dos profissionais da Fazenda", 100, 3, cargo="AUDITOR FISCAL TRIBUTARIO EST"),
        S.resenha_tempo(822, "13-10-2026", "CONVERSÃO DE LICENÇA ESPECIAL EM TEMPO DE SERVIÇO", 110, 2),
    ], None)
    return [(date(2026, 10, 2), d1), (date(2026, 10, 9), d2), (date(2026, 10, 15), d3)]


def criar(pasta_dados: str | Path, conferir: bool = True) -> dict:
    pasta = Path(pasta_dados)
    banco, acervo = Banco(pasta / "observatorio.sqlite3"), Acervo(pasta / "acervo")
    try:
        for dia, pdf in documentos():
            nome = f"DEMONSTRACAO-diario-sintetico-{dia:%d-%m-%Y}.pdf"
            coletor.importar_manual(banco, acervo, pdf, dia, f"manual:{nome}", nome)
        resumo = {"leitura": leitor.processar(banco, acervo), "classificacao": processo.classificar_pendentes(banco)}
        if conferir:
            just = "Demonstração: conferência simulada sobre documento sintético"
            # Conferem-se os atos dos dois primeiros Diários; o terceiro fica na fila, como numa operação real.
            for ato in banco.con.execute("SELECT id, vinculo FROM ato WHERE natureza = 'ORIGINAL' AND tipo = 'RESENHA' "
                                         "AND data_publicacao < '2026-10-15' ORDER BY data_publicacao, pagina").fetchall():
                servico.revisar_ato(banco, ato["id"], servico.CONFERIR, REVISOR, just, True, ato["vinculo"] != "EXPRESSO")
            for evento in banco.con.execute("SELECT id FROM evento WHERE estado = 'SUGERIDO'").fetchall():
                servico.revisar_evento(banco, evento["id"], servico.VINCULAR, REVISOR, just, None, True)
        resumo["situacao"] = processo.situacao(banco)
        resumo["aviso"] = "Base de DEMONSTRAÇÃO com documentos sintéticos. Não contém publicações reais."
        return resumo
    finally:
        banco.fechar()
