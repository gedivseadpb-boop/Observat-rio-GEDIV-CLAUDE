"""Gerador de Diários SINTÉTICOS para testes e demonstração.

Reproduz a FORMA das resenhas do DOE-PB (cabeçalhos, preâmbulos, tabelas, duas colunas), com
pessoas, matrículas e processos inteiramente fictícios. Não reproduz nenhuma publicação real.
Requer reportlab (dependência de desenvolvimento).
"""
from __future__ import annotations

import io

MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

_SEAD = "SECRETARIA DE ESTADO DA ADMINISTRAÇÃO"
_DEREH = "DIRETORIA EXECUTIVA DE RECURSOS HUMANOS"
_GEDIV = "GERÊNCIA EXECUTIVA DE CONCESSÃO DE DIREITOS E VANTAGENS"
_GEDIV_ABREV = "GERÊNCIA EXECUTIVA DE CONC. DE DIREITOS E VANTAGENS"


def pessoa(n: int) -> str:
    nomes = ["ALFA", "BETA", "GAMA", "DELTA", "EPSILON", "ZETA", "ETA", "TETA", "IOTA", "CAPA", "LAMBDA", "MI"]
    return f"PESSOA FICTICIA {nomes[n % len(nomes)]} {nomes[(n // len(nomes)) % len(nomes)]}"


def processo(n: int) -> str:
    return f"SAD-PSE-2026/9{n:04d}"


def resenha_progressao(numero: int, expediente: str, modalidade: str, grupo: str, inicio: int, quantidade: int, deferir: bool = True,
                       gediv: bool = True, cargo: str = "TECNICO ADMINISTRATIVO") -> list[str]:
    horizontal = modalidade == "HORIZONTAL"
    linhas = [f"{_SEAD} RESENHA Nº : {numero}/2026 {'/DEREH/GS' if horizontal else '- DEREH/GS/SEAD'}",
              f"{_DEREH} EXPEDIENTE DO DIA : {expediente}", _GEDIV_ABREV if gediv else "."]
    if deferir:
        linhas += ["O SECRETÁRIO DE ESTADO DA ADMINISTRAÇÃO, usando a atribuição que lhe confere o anexo V, da",
                   "Lei nº 13.099, de 14 de março de 2024, DEFERIU os Processos de PROGRESSÃO",
                   f"FUNCIONAL {modalidade} do Grupo {grupo}"]
    else:
        linhas += ["O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, por delegação de competência constante",
                   "na Portaria nº 2374/GS, datada de 18/07/88, resolve INDEFERIR os Processos de PROGRESSÃO",
                   f"FUNCIONAL {modalidade} do Grupo {grupo}"]
    linhas.append("Nº Processo Matricula Nome Cargo Niv. Ant. Atual" if horizontal else "Processo Matricula Nome Cargo Classe P/Classe")
    for i in range(inicio, inicio + quantidade):
        evolucao = (("I II", "II III", "III IV")[i % 3] if horizontal else ("A B", "B C", "C D")[i % 3]) if deferir else ""
        linhas.append(f"{processo(i)} 9{i:05d}-{i % 10} {pessoa(i)} {cargo} {evolucao}".strip())
    return linhas + ["PUBLIQUE-SE"]


def resenha_tempo(numero: int, expediente: str, tema: str, inicio: int, quantidade: int, deferir: bool = True) -> list[str]:
    verbo = "DEFERIR" if deferir else "INDEFERIR"
    linhas = [f"{_DEREH} RESENHA Nº : {numero}/2026", f"{_GEDIV} EXPEDIENTE DO DIA : {expediente}",
              "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, por delegação de competência que lhe foi outorgada",
              f"pela Portaria nº 2374/GS, datada de 18.07.88, resolve {verbo} os seguintes processos de {tema}:",
              "Lotacao Nº Processo Matricula Nome Privada Federal Estadual Municipal" if "ANOTA" in tema else
              "Lotacao Nº Processo Matricula Nome Dias Periodo Inicial Periodo Final"]
    for i in range(inicio, inicio + quantidade):
        cauda = f"0 {(i * 37) % 900} 0 {(i * 91) % 1200}" if "ANOTA" in tema else "90 01/02/1998 01/02/2003"
        linhas.append(f"SEC.EST.EDUCACAO {processo(i)} 9{i:06d} {pessoa(i)} {cauda}")
    return linhas + ["PUBLIQUE-SE"]


def portaria_sem_efeito(numero: int, resenha: int, n_processo: int) -> list[str]:
    return [f"Portaria nº {numero:03d}/2026- DEREH João Pessoa, 14 de outubro de 2026",
            "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS, por delegação de competência que lhe foi outorgada,",
            "R E S O L V E tornar sem efeito o INDEFERIMENTO DE PROGRESSÃO FUNCIONAL HORIZONTAL,",
            f"objeto do Processo nº {processo(n_processo)}, resenha {resenha}/2026, conforme relatório da",
            f"{_GEDIV}.", "PUBLIQUE-SE"]


def outros_atos(semente: int) -> list[str]:
    """Texto de OUTRAS unidades, para ocupar colunas e verificar que nada disso é atribuído à GEDIV."""
    return ["Secretaria de Estado da Educação", f"PORTARIA Nº {1200 + semente} João Pessoa, 08 de outubro de 2026",
            "O SECRETÁRIO DE ESTADO DA EDUCAÇÃO, no uso das atribuições legais, resolve designar",
            f"os servidores abaixo para compor comissão. Processo SEE-PRC-2026/5{semente:04d}", "PUBLIQUE-SE",
            f"{_SEAD} RESENHA Nº {700 + semente}/2026/GOCESP/DEREH/SEAD", f"{_DEREH} EXPEDIENTE DO DIA : 08-10-2026",
            "GERÊNCIA OPERACIONAL DE CESSÃO DE PESSOAL",
            "O DIRETOR EXECUTIVO DE RECURSOS HUMANOS resolve DEFERIR os processos de LICENÇA ESPECIAL:",
            f"SEC.EST.SAUDE SAD-PSE-2026/8{semente:04d} 8000{semente:03d} PESSOA FICTICIA DE OUTRA UNIDADE", "PUBLIQUE-SE"]


def diario(data, numero_edicao: int, blocos_largos: list[list[str]], colunas: tuple[list[str], list[str]] | None = None) -> bytes:
    """PDF com cabeçalho de edição; `blocos_largos` ocupam a largura toda; `colunas` formam uma página de duas colunas."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    largura, altura = A4
    memoria = io.BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4, invariant=1)
    cabecalho = f"João Pessoa - {DIAS[data.weekday()]}, {data.day:02d} de {MESES[data.month]} de {data.year}"

    def topo(pagina: int) -> float:
        c.setFont("Helvetica-Bold", 11)
        if pagina == 1:
            c.drawString(40, altura - 40, f"DIÁRIO OFICIAL Nº {numero_edicao // 1000}.{numero_edicao % 1000:03d}")
            c.setFont("Helvetica", 9)
            c.drawString(40, altura - 54, cabecalho)
            return altura - 80
        c.setFont("Helvetica", 8)
        c.drawString(40, altura - 36, f"{pagina} {cabecalho} Diário Oficial")
        return altura - 60

    pagina, y = 1, topo(1)
    for bloco in blocos_largos:
        for linha in bloco:
            if y < 50:
                c.showPage()
                pagina += 1
                y = topo(pagina)
            c.setFont("Helvetica", 7.5)
            c.drawString(40, y, linha)
            y -= 10.5
        y -= 8
    if colunas:
        c.showPage()
        pagina += 1
        y0 = topo(pagina)
        from reportlab.pdfbase.pdfmetrics import stringWidth
        for x, linhas in ((40, colunas[0]), (310, colunas[1])):
            y = y0
            for linha in linhas:
                # Como no Diário real, a linha que não cabe na coluna continua na linha de baixo.
                partes, atual = [], ""
                for palavra in linha.split():
                    if atual and stringWidth(f"{atual} {palavra}", "Helvetica", 6) > 245:
                        partes.append(atual)
                        atual = palavra
                    else:
                        atual = f"{atual} {palavra}".strip()
                for parte in partes + [atual]:
                    c.setFont("Helvetica", 6)
                    c.drawString(x, y, parte)
                    y -= 8.4
    c.showPage()
    c.save()
    return memoria.getvalue()
