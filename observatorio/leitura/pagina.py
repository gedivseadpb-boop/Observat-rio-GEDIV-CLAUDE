"""Reconstrução do texto de uma página a partir das palavras e de suas posições.

O Diário Oficial é diagramado em colunas. Ler a página "de um lado ao outro" mistura
atos de órgãos diferentes na mesma linha. Aqui a página é dividida em faixas:
- linhas de largura total (cabeçalho, títulos) são lidas como estão;
- trechos em colunas são lidos coluna por coluna, da esquerda para a direita.

Este módulo não depende de nenhuma biblioteca de PDF: recebe apenas palavras posicionadas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MIN_LINHAS_PARA_COLUNAS = 8


@dataclass(frozen=True)
class Palavra:
    x0: float
    x1: float
    topo: float
    texto: str


@dataclass(frozen=True)
class Divisor:
    x: float
    largura: float


def agrupar_linhas(palavras: list[Palavra], tolerancia: float = 3.0) -> list[list[Palavra]]:
    """Agrupa palavras de mesma altura em linhas físicas, de cima para baixo."""
    linhas: list[list[Palavra]] = []
    for palavra in sorted(palavras, key=lambda p: (p.topo, p.x0)):
        if linhas and abs(palavra.topo - linhas[-1][0].topo) <= tolerancia:
            linhas[-1].append(palavra)
        else:
            linhas.append([palavra])
    return [sorted(linha, key=lambda p: p.x0) for linha in linhas]


def encontrar_divisores(linhas: list[list[Palavra]], largura: float, fracao_cruzamento: float = 0.2,
                        largura_minima: float = 5.0) -> list[Divisor]:
    """Procura corredores verticais vazios (espaço entre colunas) na região central da página.

    Um corredor é uma faixa de x que quase nenhuma linha ocupa. Tolera-se que uma fração
    das linhas o atravesse, pois cabeçalhos e títulos ocupam a largura toda.
    """
    if len(linhas) < MIN_LINHAS_PARA_COLUNAS:
        return []
    ocupacao = [0] * (int(largura) + 2)
    for linha in linhas:
        cobertos = set()
        for palavra in linha:
            cobertos.update(range(max(0, int(palavra.x0)), min(len(ocupacao), int(palavra.x1) + 1)))
        for x in cobertos:
            ocupacao[x] += 1
    limite = fracao_cruzamento * len(linhas)
    divisores, inicio = [], None
    for x in range(int(largura * 0.2), int(largura * 0.8) + 1):
        livre = ocupacao[x] <= limite
        if livre and inicio is None:
            inicio = x
        elif not livre and inicio is not None:
            if x - inicio >= largura_minima:
                divisores.append(Divisor((inicio + x) / 2, x - inicio))
            inicio = None
    # exige texto em quantidade dos dois lados de cada corredor
    validos = []
    for d in divisores:
        esquerda = sum(any(p.x1 <= d.x for p in linha) for linha in linhas)
        direita = sum(any(p.x0 >= d.x for p in linha) for linha in linhas)
        if min(esquerda, direita) >= MIN_LINHAS_PARA_COLUNAS / 2:
            validos.append(d)
    if len(validos) > 1:
        # Vários corredores: os que ficam fora do centro costumam ser os vãos entre colunas de uma TABELA.
        # Havendo um corredor central (a divisão do jornal em duas colunas), só ele vale; assim as linhas
        # da tabela permanecem inteiras dentro da sua coluna (visto no DOE de 02/10/2026, p. 4).
        centrais = [d for d in validos if 0.4 * largura <= d.x <= 0.6 * largura]
        if centrais:
            validos = [min(centrais, key=lambda d: abs(d.x - largura / 2))]
    return validos


def _partes(linha: list[Palavra], divisores: list[Divisor]) -> list[list[Palavra]] | None:
    """Divide a linha nas colunas. Devolve None se a linha for de largura total."""
    partes: list[list[Palavra]] = [[] for _ in range(len(divisores) + 1)]
    for palavra in linha:
        if any(palavra.x0 < d.x < palavra.x1 for d in divisores):
            return None  # uma palavra sobre o corredor: a linha atravessa as colunas
        partes[sum(palavra.x0 >= d.x for d in divisores)].append(palavra)
    for indice, d in enumerate(divisores):
        antes, depois = partes[indice], partes[indice + 1]
        if antes and depois and depois[0].x0 - antes[-1].x1 < max(5.0, d.largura * 0.5):
            return None  # espaçamento normal entre palavras onde deveria haver corredor
    return partes


def ler_pagina(palavras: list[Palavra], largura: float) -> tuple[str, int]:
    """Devolve (texto na ordem de leitura, quantidade de colunas detectadas)."""
    linhas = agrupar_linhas(palavras)
    divisores = encontrar_divisores(linhas, largura)
    if not divisores:
        return "\n".join(" ".join(p.texto for p in linha) for linha in linhas), 1
    saida: list[str] = []
    faixa: list[list[str]] = [[] for _ in range(len(divisores) + 1)]

    def descarregar():
        for coluna in faixa:
            saida.extend(coluna)
            coluna.clear()

    for linha in linhas:
        partes = _partes(linha, divisores)
        if partes is None:
            descarregar()
            saida.append(" ".join(p.texto for p in linha))
        else:
            for indice, parte in enumerate(partes):
                if parte:
                    faixa[indice].append(" ".join(p.texto for p in parte))
    descarregar()
    return "\n".join(saida), len(divisores) + 1


_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
          "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
# Duas formas vistas: "DIÁRIO OFICIAL Nº 18.546" e, na capa real de 02/10/2026,
# "DIÁRIO OFICIAL / ESTADO DA PARAÍBA / Nº 18.684 João Pessoa - Sexta-feira, …".
_NUMERO = re.compile(r"DI[ÁA]RIO\s+OFI\s?CIAL\s+N[ºo°.]\s*(\d{1,3}(?:\.\d{3})?)"
                     r"|N[ºo°.]\s*(\d{1,3}\.\d{3})\s+Jo[ãa]o\s+Pessoa", re.I)
_DATA = re.compile(r"Jo[ãa]o\s+Pessoa\s*[-–—]?\s*[\w-]+,\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(20\d{2})", re.I)


def identificar_edicao(texto_primeira_pagina: str) -> tuple[str | None, str | None]:
    """Lê do cabeçalho o número da edição e a data (AAAA-MM-DD). None quando não encontrados."""
    numero = _NUMERO.search(texto_primeira_pagina)
    data = None
    achado = _DATA.search(texto_primeira_pagina)
    if achado and achado.group(2).lower() in _MESES:
        try:
            data = date(int(achado.group(3)), _MESES[achado.group(2).lower()], int(achado.group(1))).isoformat()
        except ValueError:
            data = None
    return ((numero.group(1) or numero.group(2)).replace(".", "") if numero else None), data
