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


def _corredor_menos_ocupado(ocupacao, inicio, fim, largura_minima, centro, linhas):
    """Dentro da faixa tolerante, prefere um vão real a uma palavra pouco frequente.

    O ponto médio da faixa inteira pode cortar um título comprido e fazer duas
    publicações paralelas parecerem uma linha de largura total.
    """
    meio = (inicio + fim) / 2
    minimo = min(ocupacao[inicio:fim])
    if ocupacao[int(meio)] == minimo:
        return Divisor(meio, fim - inicio)
    ponto = min(range(inicio, fim), key=lambda x: (ocupacao[x], abs(x - centro)))
    # A largura tolerante também pode incluir palavras. Limita-a pelos vãos
    # observados; espaços comuns entre palavras não são prova de separação.
    limiar = max(largura_minima, limiar_de_celula(linhas))
    vaos = []
    for linha in linhas:
        esquerda = [p.x1 for p in linha if p.x1 <= ponto]
        direita = [p.x0 for p in linha if p.x0 >= ponto]
        if esquerda and direita and not any(p.x0 < ponto < p.x1 for p in linha):
            vao = min(direita) - max(esquerda)
            if vao >= limiar:
                vaos.append(vao)
    return Divisor(float(ponto), min(fim - inicio, min(vaos, default=fim - inicio)))


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
                divisores.append(_corredor_menos_ocupado(ocupacao, inicio, x, largura_minima, largura / 2, linhas))
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


# ---------------------------------------------------------------------------------------------------------------
# Etapa 05.3.4 — regiões da página e linhas de TABELA reconstruídas pela geometria.
#
# Defeito 1 (tabela de largura total numa página de duas colunas): a linha da tabela em que, por acaso, o vão entre
# duas células cai sobre o corredor central era dividida "em colunas" e as suas metades iam parar em pontos
# diferentes do texto; o cargo e a evolução se separavam da pessoa. Agora uma linha dividida que está ENTRE linhas
# de largura total da mesma tabela, com as células alinhadas às delas, é lida inteira (`_suavizar_regioes`).
#
# Defeito 2 (célula quebrada em duas linhas): nas tabelas do DOE a célula do nome ou do cargo quebra em duas linhas
# físicas e as demais células (processo, matrícula, classes) ficam centradas ou no alto. O texto saía linha física a
# linha física e a primeira metade do nome, quando ficava ACIMA da linha do processo, era atribuída à pessoa de cima.
# Agora cada fragmento (linha sem a primeira célula) é juntado, célula a célula, à linha-âncora mais próxima na
# vertical, sem atravessar régua horizontal da grade. Quando a geometria não decide (distâncias iguais e indícios
# contraditórios no mesmo trecho), o fragmento sai numa linha própria marcada com MARCA_AMBIGUA, que a
# classificação transforma em pendência — nunca é colado à pessoa por suposição.
# ---------------------------------------------------------------------------------------------------------------
MARCA_AMBIGUA = "[LINHA DE TABELA SEM ATRIBUICAO SEGURA]"
MIN_LINHAS_TABELA = 3            # linhas com 3+ células para reconhecer um trecho como tabela
MIN_CELULAS_TABELA = 3
TOLERANCIA_ALINHAMENTO = 2.5     # pt entre inícios de células consideradas alinhadas
FOLGA_DO_PASSO = 1.35            # um fragmento fica a, no máximo, este múltiplo da entrelinha típica da linha anterior
MAX_LINHAS_SUAVIZADAS = 3        # linhas divididas, entre linhas inteiras da mesma tabela, lidas como inteiras


@dataclass
class LeituraPagina:
    texto: str
    colunas: int
    linhas_ambiguas: int = 0      # fragmentos de tabela sem atribuição segura (marcados no texto)
    linhas_reconstruidas: int = 0  # fragmentos juntados à sua linha de tabela pela geometria
    regioes_suavizadas: int = 0   # linhas de tabela larga que deixaram de ser divididas pelo corredor


def _vaos(linha: list[Palavra]) -> list[float]:
    return [b.x0 - a.x1 for a, b in zip(linha, linha[1:])]


def limiar_de_celula(linhas: list[list[Palavra]]) -> float:
    """Vão mínimo entre CÉLULAS: bem maior que o espaço entre palavras (mediana dos vãos da página)."""
    vaos = sorted(v for linha in linhas for v in _vaos(linha) if v > 0)
    if not vaos:
        return 4.0
    # Numa página quase só de tabelas a mediana dos vãos já é um vão entre células; por isso o limite também é medido
    # pela largura típica de uma letra (o espaço entre palavras é uma fração dela). Vale o menor dos dois.
    letras = sorted((p.x1 - p.x0) / len(p.texto) for linha in linhas for p in linha if p.texto and p.x1 > p.x0)
    pela_letra = 2.2 * letras[len(letras) // 2] if letras else float("inf")
    return max(2.0, min(3.0 * vaos[len(vaos) // 2], pela_letra))


def _celulas(linha: list[Palavra], limiar: float) -> list[list[Palavra]]:
    celulas = [[linha[0]]] if linha else []
    for anterior, palavra in zip(linha, linha[1:]):
        if palavra.x0 - anterior.x1 >= limiar:
            celulas.append([palavra])
        else:
            celulas[-1].append(palavra)
    return celulas


def _alinhada(x: float, inicios: list[float]) -> bool:
    return any(abs(x - i) <= TOLERANCIA_ALINHAMENTO for i in inicios)


def _suavizar_regioes(linhas: list[list[Palavra]], partes: list, limiar: float) -> int:
    """Linhas divididas pelo corredor que pertencem a uma tabela de largura total passam a ser lidas inteiras.
    Exige: no máximo MAX_LINHAS_SUAVIZADAS linhas divididas seguidas, com linhas inteiras dos DOIS lados, e cada uma
    delas com a primeira célula e a célula à direita do corredor alinhadas a inícios de células das vizinhas."""
    mudadas, i = 0, 0
    while i < len(linhas):
        if partes[i] is None:
            i += 1
            continue
        j = i
        while j < len(linhas) and partes[j] is not None:
            j += 1
        if 0 < i and j < len(linhas) and j - i <= MAX_LINHAS_SUAVIZADAS:
            vizinhas = (linhas[i - 1], linhas[j])
            inicios = [[c[0].x0 for c in _celulas(v, limiar)] for v in vizinhas]
            if all(len(c) >= 2 for c in inicios) and all(
                    all(abs(linhas[k][0].x0 - v[0]) <= TOLERANCIA_ALINHAMENTO for v in inicios)
                    and all(any(_alinhada(p[0].x0, v) for v in inicios) for p in partes[k][1:] if p)
                    for k in range(i, j)):
                for k in range(i, j):
                    partes[k] = None
                mudadas += j - i
        i = j
    return mudadas


def _intervalos_de_colunas(linhas_tabela: list[list[list[Palavra]]]) -> list[tuple[float, float]]:
    """Faixas horizontais das colunas da tabela: a união das células das linhas completas."""
    faixas = sorted((c[0].x0, c[-1].x1) for celulas in linhas_tabela for c in celulas)
    unidas: list[list[float]] = []
    for x0, x1 in faixas:
        if unidas and x0 <= unidas[-1][1]:
            unidas[-1][1] = max(unidas[-1][1], x1)
        else:
            unidas.append([x0, x1])
    return [(a, b) for a, b in unidas]


def _coluna_de(celula: list[Palavra], faixas) -> int | None:
    """Coluna da célula: a ÚNICA faixa que ela toca. Uma continuação pode ser mais larga que as células das linhas
    completas (avança sobre o vão), mas nunca alcança a coluna vizinha; se tocar duas faixas, não é célula da tabela."""
    x0, x1 = celula[0].x0, celula[-1].x1
    tocadas = [i for i, (a, b) in enumerate(faixas) if x0 < b - TOLERANCIA_ALINHAMENTO and x1 > a + TOLERANCIA_ALINHAMENTO]
    return tocadas[0] if len(tocadas) == 1 else None


def _regua_entre(reguas, y1: float, y2: float, x0: float, x1: float) -> bool:
    baixo, alto = sorted((y1, y2))
    return any(baixo < y < alto and rx0 <= x1 and rx1 >= x0 for y, rx0, rx1 in reguas)


def reconstruir_tabelas(linhas: list[list[Palavra]], limiar: float, reguas=()) -> tuple[list[str], int, int]:
    """Texto das linhas de UM fluxo (uma coluna da página ou um trecho de largura total), com as linhas de tabela
    reconstruídas. Devolve (linhas de texto, fragmentos reconstruídos, fragmentos ambíguos)."""
    celulas = [_celulas(l, limiar) for l in linhas]
    saida: list[str] = []
    reconstruidas = ambiguas = 0
    passos = sorted(b[0].topo - a[0].topo for a, b in zip(linhas, linhas[1:]) if b[0].topo > a[0].topo)
    passo = passos[len(passos) // 2] if passos else 0.0
    i = 0
    while i < len(linhas):
        # um trecho de tabela começa numa linha com 3+ células e segue enquanto as células couberem nas colunas
        if len(celulas[i]) < MIN_CELULAS_TABELA:
            saida.append(" ".join(p.texto for p in linhas[i]))
            i += 1
            continue
        j = i
        completas = []
        while j < len(linhas) and (len(celulas[j]) >= MIN_CELULAS_TABELA or (
                completas and len(celulas[j]) >= 1 and linhas[j][0].topo - linhas[j - 1][0].topo <= FOLGA_DO_PASSO * passo)):
            if len(celulas[j]) >= MIN_CELULAS_TABELA:
                completas.append(celulas[j])
            j += 1
        # No fim do trecho, só continua na tabela o fragmento que cabe nas colunas e não é uma linha que recomeça na
        # margem (título, "Publique-se", parágrafo): essas nunca são absorvidas por uma linha de tabela.
        faixas = _intervalos_de_colunas(completas)
        for k in range(i, j):
            if len(celulas[k]) < MIN_CELULAS_TABELA and (any(_coluna_de(c, faixas) is None for c in celulas[k])
                                                         or {_coluna_de(c, faixas) for c in celulas[k]} == {0}):
                j = k                       # a tabela termina aqui
                break
        completas = [c for c in celulas[i:j] if len(c) >= MIN_CELULAS_TABELA]
        if j == i:                          # (não ocorre: a primeira linha do trecho é completa)
            j = i + 1
        if len(completas) < MIN_LINHAS_TABELA or len(faixas) < MIN_CELULAS_TABELA:
            for k in range(i, j):
                saida.append(" ".join(p.texto for p in linhas[k]))
            i = j
            continue
        texto, r, a = _linhas_da_tabela(linhas[i:j], celulas[i:j], faixas, reguas)
        saida += texto
        reconstruidas += r
        ambiguas += a
        i = j
    return saida, reconstruidas, ambiguas


_LETRAS_ESPACADAS = re.compile(r"(?<![A-ZÀ-Ý])[A-ZÀ-Ý] (?:[A-ZÀ-Ý]{1,2} ){2,}[A-ZÀ-Ý]+\b")


def _juntar_celulas(membros: list[int], colunas_de) -> str:
    """Uma linha de tabela a partir de várias linhas físicas: coluna a coluna, de cima para baixo em cada coluna."""
    partes = []
    for coluna in sorted({c for m in membros for c in colunas_de[m]}, key=lambda c: (c == -1, c)):
        for m in sorted(membros):
            pedaco = " ".join(p.texto for p in colunas_de[m].get(coluna, []))
            if pedaco:
                # Texto justificado letra a letra ("T E C N IC O" numa linha, "A D M IN IS TRATIVO" na de baixo): cada
                # pedaço é reunido ANTES de ser juntado, senão as duas palavras virariam uma só (05/11/2026, resenha 569).
                partes.append(_LETRAS_ESPACADAS.sub(lambda a: a.group(0).replace(" ", ""), pedaco) if len(membros) > 1 else pedaco)
    return " ".join(partes)


def _linhas_pela_grade(linhas, colunas_de, faixas, reguas) -> list[list[int]] | None:
    """Com grade vetorial (réguas horizontais que atravessam a maior parte da tabela), cada faixa entre duas réguas é
    UMA linha da tabela: a geometria decide, sem proximidade nem suposição. None quando não há grade."""
    x0, x1 = faixas[0][0], faixas[-1][1]
    topo0, topo1 = linhas[0][0].topo, linhas[-1][0].topo
    proprias = sorted(y for y, rx0, rx1 in reguas
                      if topo0 - 4 <= y <= topo1 + 12 and min(x1, rx1) - max(x0, rx0) >= 0.6 * (x1 - x0))
    if len([y for y in proprias if topo0 < y < topo1 + 1]) < 1:
        return None
    grupos: dict[int, list[int]] = {}
    for k, linha in enumerate(linhas):
        grupos.setdefault(sum(y <= linha[0].topo + 1 for y in proprias), []).append(k)
    # A grade só vale quando separa DE FATO as linhas: nenhuma faixa entre réguas pode conter duas linhas completas
    # (réguas que só contornam a tabela ou o cabeçalho não dizem onde termina cada linha — resenha 583, 11/11/2026).
    completa = lambda k: 0 in colunas_de[k] and len(colunas_de[k]) * 2 >= len(faixas)
    if any(sum(completa(k) for k in grupos[g]) > 1 for g in grupos if 0 < g < len(proprias)):
        return None
    saida = []
    for g in sorted(grupos):
        if g == 0 or g == len(proprias):       # acima da primeira régua ou abaixo da última: fora da grade
            saida += [[k] for k in grupos[g]]
        else:
            saida.append(grupos[g])
    return saida


def _fragmento_alinhado(fragmento: dict, ancora: dict, faixas) -> bool:
    for coluna, palavras in fragmento.items():
        if coluna == -1:
            return False
        x0, x1 = palavras[0].x0, palavras[-1].x1
        if coluna in ancora:
            # a célula pode começar por um traço da grade lido como caractere ("|"): a referência é a 1ª palavra de texto
            texto = [p for p in ancora[coluna] if any(c.isalnum() for c in p.texto)] or ancora[coluna]
            r0, r1 = texto[0].x0, texto[-1].x1
        else:
            r0, r1 = faixas[coluna]
        if min(abs(x0 - r0), abs(x1 - r1), abs((x0 + x1) / 2 - (r0 + r1) / 2)) > TOLERANCIA_ALINHAMENTO:
            return False
    return True


def _linhas_da_tabela(linhas, celulas, faixas, reguas) -> tuple[list[str], int, int]:
    colunas_de = []
    for cel in celulas:
        mapa: dict[int, list[Palavra]] = {}
        for c in cel:
            indice = _coluna_de(c, faixas)
            mapa.setdefault(indice if indice is not None else -1, []).extend(c)
        colunas_de.append(mapa)
    pela_grade = _linhas_pela_grade(linhas, colunas_de, faixas, reguas)
    if pela_grade is not None:
        return [_juntar_celulas(g, colunas_de) for g in pela_grade], sum(len(g) - 1 for g in pela_grade), 0
    # âncora: linha com a primeira coluna preenchida e pelo menos metade das colunas; o resto é fragmento
    ancoras = [k for k, m in enumerate(colunas_de) if 0 in m and len(m) * 2 >= len(faixas)]
    if not ancoras:
        return [" ".join(p.texto for p in l) for l in linhas], 0, 0
    topo = lambda k: linhas[k][0].topo
    extensao = lambda k: (linhas[k][0].x0, linhas[k][-1].x1)
    destino: dict[int, int | None] = {}
    empates = []
    indicios = {"acima": 0, "abaixo": 0}
    for k in range(len(linhas)):
        if k in ancoras:
            continue
        cima = max((a for a in ancoras if a < k), default=None)
        baixo = min((a for a in ancoras if a > k), default=None)
        x0, x1 = extensao(k)
        if cima is not None and _regua_entre(reguas, topo(k) - 0.01, topo(cima) + 0.01, x0, x1):
            cima = None
        if baixo is not None and _regua_entre(reguas, topo(k) + 0.01, topo(baixo) - 0.01, x0, x1):
            baixo = None
        if cima is None or baixo is None:
            destino[k] = cima if cima is not None else baixo
            if destino[k] is None:
                destino[k] = -1                     # nenhuma linha da tabela ao alcance: fica como está
            continue
        d_cima, d_baixo = topo(k) - topo(cima), topo(baixo) - topo(k)
        folga = 0.15 * min(d_cima, d_baixo)
        if d_cima + folga < d_baixo:
            destino[k] = cima
            indicios["acima"] += 1
        elif d_baixo + folga < d_cima:
            destino[k] = baixo
            indicios["abaixo"] += 1
        else:
            empates.append((k, cima, baixo))
    for k, cima, baixo in empates:
        if indicios["abaixo"] and not indicios["acima"]:
            destino[k] = baixo                      # células centradas: o fragmento pertence à linha seguinte
        elif indicios["acima"] and indicios["abaixo"]:
            destino[k] = None                       # indícios contraditórios: não se atribui
        else:
            destino[k] = cima                       # células alinhadas no alto (padrão do DOE): continua a de cima
    # Etapa 05.3.5 — DEPOIS da última linha da tabela, o fragmento só continua uma célula se estiver ALINHADO a ela
    # (pela esquerda, pela direita ou pelo centro). Um título centrado logo abaixo da tabela cabe na faixa de uma
    # coluna larga, mas não se alinha à célula da última linha: deixa de ser absorvido e sai como linha comum.
    # No MEIO da tabela a regra não se aplica: ali o fragmento está entre duas linhas da própria tabela, e em tabelas
    # lidas por OCR a posição das palavras é aproximada (resenha 570/2026, 07/11/2026) — exigir alinhamento marcaria
    # como ambíguas continuações legítimas.
    for k, a in list(destino.items()):
        if a is not None and a != -1 and k > ancoras[-1] and not _fragmento_alinhado(colunas_de[k], colunas_de[a], faixas):
            destino[k] = -1
    saida, reconstruidas, ambiguas = [], 0, 0
    pendentes = [k for k, d in destino.items() if d is None]
    anteriores = [k for k in range(len(linhas)) if k < ancoras[0] and destino.get(k) is None]
    for k in range(len(linhas)):
        if k in ancoras:
            membros = [k] + [f for f, d in destino.items() if d == k]
            saida.append(_juntar_celulas(membros, colunas_de))
            reconstruidas += len(membros) - 1
        elif destino.get(k) == -1:
            saida.append(" ".join(p.texto for p in linhas[k]))
        elif k in pendentes and k not in anteriores:
            saida.append(f"{MARCA_AMBIGUA} " + " ".join(p.texto for p in linhas[k]))
            ambiguas += 1
        elif k in anteriores:
            saida.append(" ".join(p.texto for p in linhas[k]))
    return saida, reconstruidas, ambiguas


def ler_pagina_detalhada(palavras: list[Palavra], largura: float, reguas=()) -> LeituraPagina:
    """Texto na ordem de leitura, com as regiões da página tratadas em separado. `reguas`: segmentos horizontais da
    grade vetorial (y, x0, x1), que delimitam linhas de tabela; opcional."""
    linhas = agrupar_linhas(palavras)
    limiar = limiar_de_celula(linhas)
    divisores = encontrar_divisores(linhas, largura)
    total = {"r": 0, "a": 0}

    def fluxo(bloco: list[list[Palavra]]) -> list[str]:
        texto, r, a = reconstruir_tabelas(bloco, limiar, reguas)
        total["r"] += r
        total["a"] += a
        return texto

    if not divisores:
        return LeituraPagina("\n".join(fluxo(linhas)), 1, total["a"], total["r"])
    partes = [_partes(linha, divisores) for linha in linhas]
    suavizadas = _suavizar_regioes(linhas, partes, limiar)
    saida: list[str] = []
    faixa: list[list[list[Palavra]]] = [[] for _ in range(len(divisores) + 1)]
    inteiras: list[list[Palavra]] = []

    def descarregar():
        for coluna in faixa:
            saida.extend(fluxo(coluna))
            coluna.clear()

    def descarregar_inteiras():
        saida.extend(fluxo(inteiras))
        inteiras.clear()

    for linha, parte in zip(linhas, partes):
        if parte is None:
            descarregar()
            inteiras.append(linha)
        else:
            descarregar_inteiras()
            for indice, pedaco in enumerate(parte):
                if pedaco:
                    faixa[indice].append(pedaco)
    descarregar()
    descarregar_inteiras()
    return LeituraPagina("\n".join(saida), len(divisores) + 1, total["a"], total["r"], suavizadas)


def ler_pagina(palavras: list[Palavra], largura: float, reguas=()) -> tuple[str, int]:
    """Devolve (texto na ordem de leitura, quantidade de colunas detectadas)."""
    leitura = ler_pagina_detalhada(palavras, largura, reguas)
    return leitura.texto, leitura.colunas


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
