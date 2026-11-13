"""OCR de TABELA guiado pela geometria vetorial do PDF.

Problema real (DOE 07/11/2026, p. 7, resenhas 579 e 580): a tabela inteira está em fonte sem mapeamento de
caracteres. O texto nativo sai como "(cid:N)" e o OCR do bloco inteiro, prejudicado pelas linhas grossas da
grade, devolve só a primeira e a última coluna (matrícula, nome, cargo e nível anterior se perdem).

Solução: o próprio PDF desenha a grade da tabela. As bordas das células (linhas e retângulos vetoriais) dão as
colunas e as linhas. Cada COLUNA é recortada por dentro das bordas (sem as linhas verticais) e lida pelo
Tesseract; cada palavra reconhecida vai para a célula cuja faixa vertical a contém. Cada LINHA da tabela vira
uma única palavra posicionada (células na ordem das colunas, largura da linha inteira), de modo que a
reconstrução da página (`pagina.ler_pagina`) devolve uma linha de texto por linha da tabela e os vãos entre
células nunca são tomados por corredores entre colunas da página.

Não conhece regras de gerência. Sem tabela vetorial reconhecível no bloco, devolve None e o chamador usa o
OCR do bloco inteiro (comportamento anterior).
"""
from __future__ import annotations

from .pagina import Palavra

RESOLUCAO = 400          # pontos por polegada no recorte de cada coluna
RECUO_BORDA = 1.5        # pt recuados de cada borda vertical, para a linha da grade não entrar no recorte
MIN_LINHAS, MIN_COLUNAS = 2, 2
# Salvaguardas medidas no conjunto-ouro (12/11/2026). Em 02/10/2026, p. 5, a "tabela" encontrada era a grade de
# diagramação da coluna: 1,81 vez a área do bloco ilegível e só 62% de células ilegíveis — usá-la apagou resenhas
# legíveis. Nas tabelas reais da Polícia Civil (07/11/2026, p. 7): 1,1 vez e 95%. Limite calibrado com apenas esses
# dois casos reais (mais um sintético com cabeçalho alto, 1,31): rever quando houver mais exemplos.
MARGEM_BUSCA = 24.0      # pt acima do bloco ilegível em que a tabela é procurada (o cabeçalho das colunas costuma ser legível)
MAX_AREA_TABELA_SOBRE_BLOCO = 1.3
MIN_FRACAO_CELULAS_ILEGIVEIS = 0.8


def _tabela_que_cobre(pagina, bloco: tuple[float, float, float, float]):
    """A MENOR tabela vetorial que contém a maior parte do bloco ilegível.

    A busca é feita numa FAIXA horizontal da página (largura inteira; altura do bloco mais uma margem):
    - largura inteira, porque o bloco ilegível pode ser só parte das colunas da tabela;
    - altura limitada, porque, na página inteira, as linhas da tabela se juntam à moldura da resenha e ao
      cabeçalho legível acima dela (07/11/2026, p. 7), e esse texto legível seria descartado.
    A menor, porque a moldura da página e grades de diagramação também são reconhecidas como tabelas."""
    x0, topo, x1, base = bloco
    regiao = pagina.crop((0.0, max(0.0, topo - MARGEM_BUSCA), float(pagina.width), min(float(pagina.height), base + 4)))
    melhor = None
    for tabela in regiao.find_tables():
        tx0, ttop, tx1, tbase = tabela.bbox
        sobreposicao = max(0.0, min(tx1, x1) - max(tx0, x0)) * max(0.0, min(tbase, base) - max(ttop, topo))
        area_bloco = max(1.0, (x1 - x0) * (base - topo))
        if sobreposicao / area_bloco >= 0.5 and len(tabela.rows) >= MIN_LINHAS:
            area = (tx1 - tx0) * (tbase - ttop)
            if melhor is None or area < melhor[0]:
                melhor = (area, tabela)
    return melhor[1] if melhor else None


def _tabela_e_do_bloco(tabela, bloco, palavras_nativas, ilegivel) -> bool:
    """A tabela é a do trecho ilegível, e não uma grade de diagramação que também envolve texto legível?

    A primeira linha da tabela (cabeçalho das colunas, legível por natureza) não entra na contagem de células e
    entra na área considerada ilegível; assim tabelas curtas não são recusadas por causa do próprio cabeçalho."""
    tx0, ttop, tx1, tbase = tabela.bbox
    dentro = lambda w, c: c[0] <= (w["x0"] + w["x1"]) / 2 <= c[2] and c[1] <= (w["top"] + w["bottom"]) / 2 <= c[3]
    ilegiveis_na_tabela = [w for w in palavras_nativas if ilegivel(w["text"]) and dentro(w, tabela.bbox)]
    if not ilegiveis_na_tabela:
        return False
    primeira = [c for c in tabela.rows[0].cells if c]
    topo_area = min([min(c[1] for c in primeira)] + [w["top"] for w in ilegiveis_na_tabela]) if primeira else \
        min(w["top"] for w in ilegiveis_na_tabela)
    area_ilegivel = ((max(w["x1"] for w in ilegiveis_na_tabela) - min(w["x0"] for w in ilegiveis_na_tabela))
                     * (max(w["bottom"] for w in ilegiveis_na_tabela) - topo_area))
    if (tx1 - tx0) * (tbase - ttop) > MAX_AREA_TABELA_SOBRE_BLOCO * max(1.0, area_ilegivel):
        return False
    ilegiveis = legiveis = 0
    for c in (c for linha in tabela.rows[1:] for c in linha.cells if c):
        palavras = [w for w in palavras_nativas if dentro(w, c)]
        if any(ilegivel(w["text"]) for w in palavras):
            ilegiveis += 1
        elif palavras:
            legiveis += 1
    return ilegiveis >= MIN_FRACAO_CELULAS_ILEGIVEIS * max(1, ilegiveis + legiveis)


def ler_tabela(pagina, bloco: tuple[float, float, float, float], palavras_nativas=(), ilegivel=lambda t: "(cid:" in t
               ) -> tuple[list[Palavra], list[float], tuple] | None:
    """(palavras — uma por linha da tabela —, confianças do OCR, área coberta pela tabela) ou None se não houver
    tabela vetorial no bloco. A área coberta substitui todo o texto nativo que estiver dentro dela."""
    import pytesseract

    tabela = _tabela_que_cobre(pagina, bloco)
    if tabela is None or not _tabela_e_do_bloco(tabela, bloco, palavras_nativas, ilegivel):
        return None
    celulas = [c for linha in tabela.rows for c in linha.cells if c]
    bordas_x = sorted({round(c[0], 1) for c in celulas} | {round(c[2], 1) for c in celulas})
    faixas_y = sorted({(round(c[1], 1), round(c[3], 1)) for c in celulas})
    if len(bordas_x) - 1 < MIN_COLUNAS or len(faixas_y) < MIN_LINHAS:
        return None
    textos: dict[tuple[int, int], list[str]] = {}
    confiancas: list[float] = []
    escala = 72.0 / RESOLUCAO
    topo_tabela, base_tabela = tabela.bbox[1], tabela.bbox[3]
    for coluna, (a, z) in enumerate(zip(bordas_x, bordas_x[1:])):
        if z - a < 2 * RECUO_BORDA + 2:
            continue
        recorte = pagina.crop((a + RECUO_BORDA, topo_tabela, z - RECUO_BORDA, base_tabela))
        imagem = recorte.to_image(resolution=RESOLUCAO).original
        dados = pytesseract.image_to_data(imagem, lang="por", config="--psm 6", output_type=pytesseract.Output.DICT)
        for texto, conf, y, h, n_bloco, n_par, n_linha, n_palavra in zip(
                dados["text"], dados["conf"], dados["top"], dados["height"], dados["block_num"], dados["par_num"],
                dados["line_num"], dados["word_num"]):
            if not texto.strip() or float(conf) < 0:
                continue
            centro = topo_tabela + (y + h / 2) * escala
            linha = next((i for i, (t, b) in enumerate(faixas_y) if t - 1 <= centro <= b + 1), None)
            if linha is None:
                continue
            textos.setdefault((linha, coluna), []).append(texto.strip())
            confiancas.append(float(conf))
    # Uma palavra por LINHA da tabela, com as células na ordem das colunas e a largura da linha inteira: os vãos
    # entre células não podem parecer corredores entre colunas da página (o que partiria a tabela ao meio).
    palavras = []
    for linha in sorted({l for l, _ in textos}):
        celulas = [" ".join(textos[(linha, c)]) for c in range(len(bordas_x) - 1) if (linha, c) in textos]
        t, b = faixas_y[linha]
        palavras.append(Palavra(bordas_x[0] + RECUO_BORDA, bordas_x[-1] - RECUO_BORDA, (t + b) / 2, " ".join(celulas)))
    return (palavras, confiancas, tuple(tabela.bbox)) if palavras else None
