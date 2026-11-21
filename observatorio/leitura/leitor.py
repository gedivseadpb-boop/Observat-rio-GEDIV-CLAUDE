"""Leitura dos arquivos do acervo e gravação do texto por página no banco.

Para cada página:
1. tenta o texto nativo do PDF, reconstruído por colunas;
   1a. se um trecho usa fonte sem mapeamento de caracteres (o texto sai como "(cid:12)(cid:7)…"), só esse
       trecho é lido por OCR e recolocado no lugar — método TEXTO+OCR (visto no DOE de 02/10/2026, p. 5);
2. se não houver texto, aplica OCR em português (Tesseract) e reconstrói por colunas
   a partir da posição das palavras reconhecidas;
3. atribui uma qualidade, para que nada duvidoso siga adiante como se fosse confiável.

Qualidade da página:
    OK                 texto nativo íntegro, ou OCR com boa confiança;
    BAIXA_CONFIANCA    OCR com confiança média abaixo de 75;
    ILEGIVEL           OCR com confiança abaixo de 50, ou sem palavras reconhecidas em página com conteúdo gráfico;
    INCONSISTENTE      texto nativo com caracteres corrompidos em proporção relevante, sem OCR para recuperá-los;
    OCR_INDISPONIVEL   a página exige OCR e o Tesseract (com idioma português) não está instalado;
    TEXTO_PARCIAL      página MISTA: há texto nativo, mas também uma imagem grande cujo conteúdo não pôde ser lido
                       (sem OCR disponível); o texto nativo é guardado e a página fica pendente;
    VAZIA              página sem texto e sem conteúdo gráfico;
    LEITURA_INCOMPLETA (Etapa 05.3.4) o OCR deixou de ler linhas que têm tinta na imagem, mesmo depois de nova
                       tentativa só sobre elas: a página fica pendente, com o que foi lido guardado;
    OCR_ESGOTADO       o OCR estourou o tempo da chamada, da página ou do arquivo: fica o texto nativo, pendente.

Completude (Etapa 05.3.4), além do sinal "(cid:N)":
- fonte com mapeamento ERRADO de caracteres (o texto sai como letras, mas sem vogais ou cheio de sinais): as palavras
  dessa fonte são tratadas como ilegíveis e relidas por OCR, como as "(cid:N)";
- imagem sem nenhuma palavra por cima, mesmo pequena (uma tabela colada como figura): só a região é lida por OCR;
- página por OCR: faixas com tinta de texto e nenhuma palavra reconhecida são relidas uma a uma; as que continuarem
  sem leitura deixam a página como LEITURA_INCOMPLETA.

Cada arquivo é gravado em uma única transação: ou fica lido por inteiro, ou continua na
fila. Arquivos já lidos pela mesma versão do leitor são pulados; mudar a versão faz todos
voltarem à fila, sem apagar nada do acervo. Não conhece regras de nenhuma gerência.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from pathlib import Path

from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from . import ocr, tabela_ocr
from .pagina import Palavra, identificar_edicao, ler_pagina

VERSAO = "0.8"           # 0.4: cache liberado por página; 0.5: OCR de tabela pela grade vetorial;
                         # 0.6: tolerância proporcional ao corpo da letra; leitura de caracteres sobrepostos
                         # 0.7 (Etapa 05.3.4): linhas de tabela pela geometria, regiões da página, completude do OCR
                         # 0.8 (Etapa 05.3.5): alinhamento do fragmento à célula; conferência dos trechos relidos;
                         #      aviso de texto em contorno e de imagem não examinada
MIN_CARACTERES = 20       # abaixo disso a página é tratada como sem texto nativo
RESOLUCAO_OCR = 300       # pontos por polegada
RESOLUCAO_OCR_TRECHO = 400  # trechos com fonte ilegível costumam ser tabelas em corpo 4: mais resolução
MIN_SINAIS_ILEGIVEIS = 10   # sinais "(cid:N)" num bloco para justificar o OCR do trecho (uma linha inteira costuma vir como uma só "palavra")
CONFIANCA_BOA, CONFIANCA_MINIMA = 75.0, 50.0
FRACAO_IMAGEM_MISTA = 0.25  # imagens cobrindo esta fração da página, junto com texto nativo, indicam página mista
_CORROMPIDO = re.compile(r"\(cid:\d+\)|�")
# Distância horizontal máxima entre letras de uma mesma palavra, PROPORCIONAL ao corpo da letra. Uma tolerância
# fixa em pontos não serve às tabelas do DOE, que usam corpos de 4 a 8 pt: com 3 pt (padrão do pdfplumber) colava
# "LICENÇAPARATRATAR" (04/11/2026); com 1,5 pt ainda colava nomes em tabelas de corpo 4,3 pt (vão de 0,87 pt entre
# palavras, 05/11/2026). Medido em 513 páginas de 12 edições oficiais (12/11/2026): com 0,15 do corpo, 17 páginas
# ficam mais próximas da leitura independente (pypdfium2) que com 1,5 pt, e nenhuma piora.
TOLERANCIA_X_PROPORCIONAL = 0.15
# Caracteres de fontes diferentes desenhados no MESMO lugar (correção impressa por cima do texto original, DOE
# 05/11/2026, resenha 564: camada de texto "A", impresso visível "D" em fonte sem mapeamento). A palavra é relida por
# OCR do próprio recorte, que devolve o que está visível na publicação.
SOBREPOSICAO_MAX_PT = 0.6
RESOLUCAO_OCR_PALAVRA = 400


# --- Etapa 05.3.4: fontes com mapeamento errado, regiões sem texto e linhas não lidas ---------------------------
MIN_LETRAS_FONTE = 40          # letras de uma fonte na página para julgá-la
MAX_FRACAO_ESTRANHOS = 0.30    # sinais fora do alfabeto, dos algarismos e da pontuação comum
MIN_FRACAO_VOGAIS = 0.18       # em português as vogais passam de 40% das letras; abaixo disto o texto não é texto
_COMUNS = set(" .,;:!?()[]{}/\\-–—_'\"“”‘’ºª°%$&*+=<>@#|§")
_VOGAIS = set("AEIOUÁÀÂÃÉÊÍÓÔÕÚÜaeiouáàâãéêíóôõúü")
MIN_AREA_IMAGEM = 0.015        # fração da página a partir da qual uma imagem sem palavras por cima é lida por OCR
MIN_LADO_IMAGEM = (60.0, 12.0)  # largura e altura mínimas (pt): um traço ou um ícone não são texto
MIN_PALAVRAS_REGIAO = 3
MIN_PALAVRAS_REGIAO_DENSA = 15  # a partir daqui a região é texto corrido ou tabela, não um anúncio
LIMIAR_TINTA = 128             # tom de cinza abaixo do qual o ponto é tinta
MIN_TRACOS_LINHA = 6           # grupos de tinta separados numa faixa para ela parecer uma linha de texto (régua tem 1)


def fontes_suspeitas(caracteres) -> set[str]:
    """Fontes cujo texto extraído não é texto: mapeamento de caracteres errado, sem o sinal "(cid:N)"."""
    por_fonte: dict[str, list[str]] = {}
    for c in caracteres:
        if c.get("text") and not c["text"].isspace():
            por_fonte.setdefault(c.get("fontname") or "", []).append(c["text"])
    suspeitas = set()
    for fonte, sinais in por_fonte.items():
        texto = "".join(sinais)
        if _CORROMPIDO.search(texto):
            continue                                   # já tratado pelo sinal explícito
        # Ligaduras tipográficas ("ﬁ", "ﬂ") são letras: o DOE usa um subconjunto de fonte só com elas (06/10 e
        # 12/11/2026). Decompostas, voltam a "fi"/"fl" e não contam como sinal estranho.
        texto = unicodedata.normalize("NFKD", texto)
        letras = [c for c in texto if c.isalpha()]
        estranhos = sum(1 for c in texto if not (c.isalnum() and ord(c) < 0x250) and c not in _COMUNS
                        and not unicodedata.combining(c))
        if len(texto) >= MIN_LETRAS_FONTE and estranhos / len(texto) > MAX_FRACAO_ESTRANHOS:
            suspeitas.add(fonte)
        elif len(letras) >= MIN_LETRAS_FONTE and sum(c in _VOGAIS for c in letras) / len(letras) < MIN_FRACAO_VOGAIS:
            suspeitas.add(fonte)
    return suspeitas


def _marcar_fontes_suspeitas(pagina, brutas: list[dict]) -> int:
    """Palavras em fonte suspeita passam a carregar o sinal de ilegível ("(cid:0)" por caractere): daí em diante
    seguem o caminho já existente (OCR do trecho ou da tabela; sem OCR, página INCONSISTENTE). Devolve quantas."""
    suspeitas = fontes_suspeitas(pagina.chars)
    if not suspeitas:
        return 0
    ruins = [c for c in pagina.chars if (c.get("fontname") or "") in suspeitas and not c["text"].isspace()]
    marcadas = 0
    for w in brutas:
        dentro = sum(1 for c in ruins if w["x0"] - 0.5 <= (c["x0"] + c["x1"]) / 2 <= w["x1"] + 0.5
                     and w["top"] - 1 <= (c["top"] + c["bottom"]) / 2 <= w["bottom"] + 1)
        if dentro * 2 >= len(w["text"]):
            w["text"] = "(cid:0)" * max(1, len(w["text"]))
            marcadas += 1
    return marcadas


def _imagens_sem_texto(pagina, brutas: list[dict]) -> list[tuple[float, float, float, float]]:
    """Imagens de tamanho relevante sem nenhuma palavra nativa por cima: podem ser texto que o PDF não traz."""
    largura, altura = float(pagina.width), float(pagina.height)
    regioes = []
    for imagem in pagina.images:
        x0, x1 = max(0.0, float(imagem["x0"])), min(largura, float(imagem["x1"]))
        topo, base = max(0.0, float(imagem["top"])), min(altura, float(imagem["bottom"]))
        if x1 - x0 < MIN_LADO_IMAGEM[0] or base - topo < MIN_LADO_IMAGEM[1]:
            continue
        if (x1 - x0) * (base - topo) < MIN_AREA_IMAGEM * largura * altura:
            continue
        if any(x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and topo <= (w["top"] + w["bottom"]) / 2 <= base for w in brutas):
            continue
        regioes.append((x0, topo, x1, base))
    return regioes


def _ler_regioes_sem_texto(pagina, brutas: list[dict], regioes=None) -> tuple[list[Palavra], list[float], int]:
    """OCR só das imagens sem texto. Uma figura (brasão, foto) não devolve palavras e é ignorada.
    Numa figura com pouco texto (faixa de anúncio com logotipo) ficam só as palavras lidas com confiança: o ruído do
    desenho não entra no texto nem derruba a qualidade da página (12/11/2026, p. 55). Numa região DENSA de texto
    (tabela digitalizada) tudo é guardado, a confiança baixa deixa a página pendente e — Etapa 05.3.5 — as linhas com
    tinta que o OCR não leu são relidas e contadas: devolve também quantas continuaram sem leitura."""
    palavras, confiancas, sem_leitura = [], [], 0
    for regiao in (_imagens_sem_texto(pagina, brutas) if regioes is None else regioes):
        lidas, conf, faltam = _ocr_com_conferencia(pagina.crop(regiao), RESOLUCAO_OCR, (regiao[0], regiao[1]))
        com_texto = [(p, c) for p, c in zip(lidas, conf) if sum(ch.isalnum() for ch in p.texto) >= 2]
        boas = [(p, c) for p, c in com_texto if c >= CONFIANCA_MINIMA]
        if len(boas) < MIN_PALAVRAS_REGIAO:
            continue
        if len(com_texto) >= MIN_PALAVRAS_REGIAO_DENSA:
            sem_leitura += faltam                       # só em região de texto: num anúncio, tinta sem palavra é desenho
            if len(boas) < 0.6 * len(com_texto):
                boas = list(zip(lidas, conf))           # região de texto mal lida: fica tudo, e a página, pendente
        palavras += [p for p, _ in boas]
        confiancas += [c for _, c in boas]
    return palavras, confiancas, sem_leitura


# Etapa 05.3.5 — texto desenhado como CONTORNO vetorial (sem caracteres e sem imagem): o PDF traz cada letra como uma
# curva e a extração não devolve nada. Caso real: DOE de 07/11/2026, p. 6 — uma resenha inteira da GEDIV em contorno,
# que o robô nunca tinha lido; e 12/11/2026, p. 55 — uma página inteira de balanço de empresa.
# Tratamento: as curvas do tamanho de uma letra que não estão sob nenhuma palavra são agrupadas em regiões. Região sem
# nenhuma palavra nativa dentro é lida por OCR, como uma imagem sem texto. Região com palavras nativas não é relida
# para não duplicá-las. Toda região detectada mantém aviso: mesmo com confiança alta, ler algumas palavras não prova
# que todas foram reconhecidas.
MIN_CONTORNOS = 40             # curvas do tamanho de letra numa região; menos que isso é ornamento
CELULA_CONTORNO = 18.0         # pt da malha usada para agrupar curvas vizinhas
AVISO_CONTORNO = "POSSIVEL_TEXTO_EM_CONTORNO"
AVISO_IMAGEM = "IMAGEM_NAO_EXAMINADA"


def _contornos_livres(curvas, brutas: list[dict]) -> list[dict]:
    letras = [c for c in curvas if 2 <= c["bottom"] - c["top"] <= 22 and 0.5 <= c["x1"] - c["x0"] <= 30]
    if len(letras) < MIN_CONTORNOS:
        return []
    # índice das palavras por faixa vertical, para não comparar cada curva com cada palavra
    por_faixa: dict[int, list[dict]] = {}
    for w in brutas:
        for f in range(int((w["top"] - 2) // 20), int((w["bottom"] + 2) // 20) + 1):
            por_faixa.setdefault(f, []).append(w)
    livres = []
    for c in letras:
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        if not any(w["x0"] - 2 <= cx <= w["x1"] + 2 and w["top"] - 2 <= cy <= w["bottom"] + 2 for w in por_faixa.get(int(cy // 20), [])):
            livres.append(c)
    return livres


def contornos_sem_texto(curvas, brutas: list[dict]) -> int:
    """Quantas curvas do tamanho de uma letra (2–22 pt de altura, até 30 pt de largura) não estão sob nenhuma palavra."""
    return len(_contornos_livres(curvas, brutas))


def regioes_de_contorno(curvas, brutas: list[dict]) -> list[tuple[float, float, float, float, bool]]:
    """Regiões (x0, topo, x1, base, tem_palavra_nativa_dentro) formadas por MIN_CONTORNOS ou mais curvas vizinhas do
    tamanho de letra, fora de palavras. Vizinhas: em células adjacentes de uma malha de CELULA_CONTORNO pt."""
    livres = _contornos_livres(curvas, brutas)
    celulas: dict[tuple[int, int], list[dict]] = {}
    for c in livres:
        celulas.setdefault((int((c["x0"] + c["x1"]) / 2 // CELULA_CONTORNO), int((c["top"] + c["bottom"]) / 2 // CELULA_CONTORNO)), []).append(c)
    regioes, vistas = [], set()
    for inicio in celulas:
        if inicio in vistas:
            continue
        pilha, grupo = [inicio], []
        vistas.add(inicio)
        while pilha:
            i, j = pilha.pop()
            grupo += celulas[(i, j)]
            for vizinha in ((i + di, j + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)):
                if vizinha in celulas and vizinha not in vistas:
                    vistas.add(vizinha)
                    pilha.append(vizinha)
        if len(grupo) < MIN_CONTORNOS:
            continue
        x0, topo = min(c["x0"] for c in grupo) - 3, min(c["top"] for c in grupo) - 3
        x1, base = max(c["x1"] for c in grupo) + 3, max(c["bottom"] for c in grupo) + 3
        # palavra nativa LEGÍVEL dentro da região; uma palavra em fonte sem mapeamento ("(cid:N)") não conta: ela é
        # parte do que não foi lido e sai junto quando a região vai ao OCR
        dentro = any(x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and topo <= (w["top"] + w["bottom"]) / 2 <= base
                     and not _CORROMPIDO.search(w["text"]) for w in brutas)
        regioes.append((max(0.0, x0), max(0.0, topo), x1, base, dentro))
    return sorted(regioes, key=lambda r: (r[1], r[0]))


def _avisos(pagina, brutas: list[dict], contornos) -> list[str]:
    """O que a leitura NÃO examinou nesta página e pode esconder texto. Não muda a qualidade da página; vai para as
    inconsistências do arquivo, que fica "lido com pendências"."""
    avisos = []
    sem_ocr = not ocr_disponivel()[0]
    if contornos:
        avisos.append(AVISO_CONTORNO)                   # conferir mesmo quando o OCR leu parte da região
    if sem_ocr and _imagens_sem_texto(pagina, brutas):
        avisos.append(AVISO_IMAGEM)                     # sem Tesseract, a imagem pequena não pôde ser lida
    return avisos


def faixas_sem_leitura(imagem, caixas) -> list[tuple[int, int, int, int]]:
    """Regiões da imagem (x0, y0, x1, y1, em pontos da imagem) com tinta de TEXTO e nenhuma palavra reconhecida.
    `caixas`: (x0, y0, x1, y1) das palavras do OCR, na mesma escala. Não depende do Tesseract."""
    from PIL import Image
    cinza = imagem.convert("L").point(lambda v: 255 if v < LIMIAR_TINTA else 0)
    largura, altura = cinza.size
    por_linha = list(cinza.resize((1, altura), Image.BOX).getdata())
    faixas, inicio = [], None
    for y, valor in enumerate(por_linha + [0]):
        if valor > 0 and inicio is None:
            inicio = y
        elif valor == 0 and inicio is not None:
            faixas.append((inicio, y))
            inicio = None
    alturas = sorted(y1 - y0 for _, y0, _, y1 in caixas) if caixas else []
    tipica = alturas[len(alturas) // 2] if alturas else max(8, altura // 120)
    faltando = []
    for y0, y1 in faixas:
        if not 0.4 * tipica <= y1 - y0 <= 4 * tipica:
            continue                                   # régua fina, moldura ou figura alta: não é uma linha de texto
        por_coluna = list(cinza.crop((0, y0, largura, y1)).resize((largura, 1), Image.BOX).getdata())
        tracos, comeco = [], None
        for x, valor in enumerate(por_coluna + [0]):
            if valor > 0 and comeco is None:
                comeco = x
            elif valor == 0 and comeco is not None:
                tracos.append((comeco, x))
                comeco = None
        segmentos: list[list] = []
        for a, b in tracos:                            # traços próximos formam um segmento (uma linha numa coluna)
            if segmentos and a - segmentos[-1][1] < 0.03 * largura:
                segmentos[-1][1] = b
                segmentos[-1][2] += 1
            else:
                segmentos.append([a, b, 1])
        for a, b, n in segmentos:
            if n < MIN_TRACOS_LINHA:
                continue
            if not any(cx0 < b and cx1 > a and cy0 < y1 and cy1 > y0 for cx0, cy0, cx1, cy1 in caixas):
                faltando.append((a, y0, b, y1))
    return faltando


@functools.lru_cache(maxsize=1)
def ocr_disponivel() -> tuple[bool, str]:
    try:
        import pytesseract
        if "por" not in pytesseract.get_languages(config=""):
            return False, "idioma português (por) não instalado no Tesseract"
        return True, f"Tesseract {pytesseract.get_tesseract_version()}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]


def _ocr(pagina, resolucao: int = RESOLUCAO_OCR, origem: tuple[float, float] = (0.0, 0.0)) -> tuple[list[Palavra], float | None]:
    palavras, confiancas = _ocr_bruto(pagina, resolucao, origem)
    return palavras, (round(sum(confiancas) / len(confiancas), 1) if confiancas else None)


def _ocr_com_conferencia(pagina, resolucao: int, origem: tuple[float, float] = (0.0, 0.0)) -> tuple[list[Palavra], list[float], int]:
    """OCR de uma página ou de um recorte dela, com conferência de COMPLETUDE: faixas com tinta de texto e sem palavra
    reconhecida são relidas uma a uma (linha isolada, `--psm 7`). Devolve (palavras, confianças, linhas que continuaram
    sem leitura). `origem`: canto do recorte na página, em pontos."""
    imagem = pagina.to_image(resolution=resolucao).original
    dados = ocr.dados(imagem)
    escala = 72.0 / resolucao
    palavras, confiancas, caixas = [], [], []
    for texto, conf, x, y, w, h in zip(dados["text"], dados["conf"], dados["left"], dados["top"], dados["width"], dados["height"]):
        if texto.strip() and float(conf) >= 0:
            palavras.append(Palavra(origem[0] + x * escala, origem[0] + (x + w) * escala, origem[1] + (y + h / 2) * escala, texto.strip()))
            confiancas.append(float(conf))
            caixas.append((x, y, x + w, y + h))
    sem_leitura = 0
    for x0, y0, x1, y1 in faixas_sem_leitura(imagem, caixas):
        margem = 4
        recorte = imagem.crop((max(0, x0 - margem), max(0, y0 - margem), min(imagem.size[0], x1 + margem), min(imagem.size[1], y1 + margem)))
        relido = ocr.dados(recorte, config="--psm 7")
        achou = False
        for texto, conf, x, y, w, h in zip(relido["text"], relido["conf"], relido["left"], relido["top"], relido["width"], relido["height"]):
            if texto.strip() and float(conf) >= 0 and sum(c.isalnum() for c in texto) >= 1:
                gx, gy = max(0, x0 - margem) + x, max(0, y0 - margem) + y
                palavras.append(Palavra(origem[0] + gx * escala, origem[0] + (gx + w) * escala, origem[1] + (gy + h / 2) * escala, texto.strip()))
                confiancas.append(float(conf))
                achou = True
        sem_leitura += not achou
    return palavras, confiancas, sem_leitura


def _ocr_completo(pagina, resolucao: int = RESOLUCAO_OCR) -> tuple[list[Palavra], float | None, int]:
    """OCR da página inteira com conferência de completude: (palavras, confiança média, linhas sem leitura)."""
    palavras, confiancas, sem_leitura = _ocr_com_conferencia(pagina, resolucao)
    return palavras, (round(sum(confiancas) / len(confiancas), 1) if confiancas else None), sem_leitura


def _ocr_bruto(pagina, resolucao: int, origem: tuple[float, float]) -> tuple[list[Palavra], list[float]]:
    imagem = pagina.to_image(resolution=resolucao).original
    dados = ocr.dados(imagem)
    escala = 72.0 / resolucao
    palavras, confiancas = [], []
    for texto, conf, x, y, w, h in zip(dados["text"], dados["conf"], dados["left"], dados["top"], dados["width"],
                                       dados["height"]):
        if texto.strip() and float(conf) >= 0:
            # No OCR a caixa acompanha cada desenho de letra (um hífen é mais baixo que uma palavra);
            # usa-se o centro vertical para que sinais pequenos fiquem na mesma linha do texto.
            palavras.append(Palavra(origem[0] + x * escala, origem[0] + (x + w) * escala, origem[1] + (y + h / 2) * escala, texto.strip()))
            confiancas.append(float(conf))
    return palavras, confiancas


def _blocos_ilegiveis(brutas: list[dict], largura: float, altura: float) -> list[tuple[float, float, float, float]]:
    """Retângulos (x0, topo, x1, base) que envolvem as palavras em fonte sem mapeamento de caracteres.
    Palavras vizinhas na vertical e na mesma faixa horizontal formam um bloco; as linhas "normais" que ficam
    dentro dele (linhas de tabela na mesma fonte, que saem como letras trocadas) são relidas junto."""
    ruins = sorted((w for w in brutas if _CORROMPIDO.search(w["text"])), key=lambda w: w["top"])
    blocos: list[list[float]] = []
    contagem: list[int] = []
    for w in ruins:
        for i, b in enumerate(blocos):
            if w["top"] - b[3] <= 30 and w["x0"] <= b[2] + 20 and w["x1"] >= b[0] - 20:
                b[0], b[1], b[2], b[3] = min(b[0], w["x0"]), min(b[1], w["top"]), max(b[2], w["x1"]), max(b[3], w["bottom"])
                contagem[i] += len(_CORROMPIDO.findall(w["text"]))
                break
        else:
            blocos.append([w["x0"], w["top"], w["x1"], w["bottom"]])
            contagem.append(len(_CORROMPIDO.findall(w["text"])))
    fundiu = True
    while fundiu:                      # blocos que se tocam viram um só, para nenhum trecho ser lido duas vezes
        fundiu = False
        for i in range(len(blocos)):
            for j in range(i + 1, len(blocos)):
                a, b = blocos[i], blocos[j]
                if a[0] <= b[2] + 8 and b[0] <= a[2] + 8 and a[1] <= b[3] + 8 and b[1] <= a[3] + 8:
                    blocos[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    contagem[i] += contagem[j]
                    del blocos[j], contagem[j]
                    fundiu = True
                    break
            if fundiu:
                break
    return [(max(0.0, b[0] - 4), max(0.0, b[1] - 4), min(largura, b[2] + 4), min(altura, b[3] + 4))
            for b, n in zip(blocos, contagem) if n >= MIN_SINAIS_ILEGIVEIS]


def _reler_trechos_ilegiveis(numero: int, pagina, brutas: list[dict], regioes=()) -> dict | None:
    """Substitui por OCR somente os trechos em fonte ilegível. None quando não há o que reler.
    `regioes`: regiões de texto em contorno da mesma página, lidas na mesma passada (Etapa 05.3.5)."""
    largura, altura = float(pagina.width), float(pagina.height)
    blocos = _blocos_ilegiveis(brutas, largura, altura)
    if not blocos:
        return None
    dentro = lambda w, b: b[0] <= (w["x0"] + w["x1"]) / 2 <= b[2] and b[1] <= (w["top"] + w["bottom"]) / 2 <= b[3]
    lidas_por_bloco, confiancas, areas, sem_leitura = [], [], [], 0
    for b in blocos:
        centro = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        if any(a[0] <= centro[0] <= a[2] and a[1] <= centro[1] <= a[3] for a in areas):
            continue                                     # trecho já relido junto com a tabela a que pertence
        # Tabela com grade vetorial: OCR coluna a coluna, célula por célula (tabela_ocr). Sem grade: o bloco inteiro.
        tabela = tabela_ocr.ler_tabela(pagina, b, brutas, lambda t: bool(_CORROMPIDO.search(t)))
        if tabela:
            lidas, conf, area = tabela
        else:
            # Etapa 05.3.5: o trecho relido também é conferido — linha com tinta e sem palavra não passa em silêncio.
            lidas, conf, faltam = _ocr_com_conferencia(pagina.crop(b), RESOLUCAO_OCR_TRECHO, (b[0], b[1]))
            sem_leitura += faltam
            area = b
        lidas_por_bloco += lidas
        confiancas += conf
        areas.append(area)
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas
                if not any(dentro(w, a) for a in areas) and not _CORROMPIDO.search(w["text"])]
    palavras += lidas_por_bloco
    if not confiancas:
        return None
    if regioes:
        extras, confiancas_das_regioes, faltam = _ler_regioes_sem_texto(pagina, brutas, list(regioes))
        palavras += extras
        confiancas += confiancas_das_regioes
        sem_leitura += faltam
    confianca = round(sum(confiancas) / len(confiancas), 1)
    texto, colunas = ler_pagina(palavras, largura)
    qualidade = "LEITURA_INCOMPLETA" if sem_leitura else "OK" if confianca >= CONFIANCA_BOA else "BAIXA_CONFIANCA"
    return {"numero": numero, "metodo": "TEXTO+OCR", "colunas": colunas, "texto": texto, "palavras": len(palavras),
            "qualidade": qualidade, "confianca": confianca}


def _fracao_coberta_por_imagens(pagina) -> float:
    largura, altura = float(pagina.width), float(pagina.height)
    area = 0.0
    for imagem in pagina.images:
        x0, x1 = max(0.0, float(imagem["x0"])), min(largura, float(imagem["x1"]))
        topo, base = max(0.0, float(imagem["top"])), min(altura, float(imagem["bottom"]))
        area += max(0.0, x1 - x0) * max(0.0, base - topo)
    return min(1.0, area / (largura * altura)) if largura and altura else 0.0


def _classificar_ocr(numero, palavras, confianca, largura, sem_leitura: int = 0) -> dict:
    texto, colunas = ler_pagina(palavras, largura)
    if not palavras or confianca < CONFIANCA_MINIMA:
        qualidade = "ILEGIVEL"
    elif sem_leitura:
        qualidade = "LEITURA_INCOMPLETA"       # há linhas com tinta que o OCR não leu, nem na segunda tentativa
    elif confianca < CONFIANCA_BOA:
        qualidade = "BAIXA_CONFIANCA"
    else:
        qualidade = "OK"
    return {"numero": numero, "metodo": "OCR", "colunas": colunas if palavras else 0, "texto": texto,
            "palavras": len(palavras), "qualidade": qualidade, "confianca": confianca}


def _ler_sobreposicoes(pagina, brutas: list[dict]) -> int:
    """Relê por OCR as palavras em que dois caracteres diferentes ocupam a mesma posição e um deles está em fonte
    sem mapeamento. Altera `brutas` no lugar; devolve quantas palavras foram relidas."""
    relidas = 0
    for w in brutas:
        if not _CORROMPIDO.search(w["text"]):
            continue
        caracteres = sorted((c for c in pagina.chars if w["x0"] - 0.5 <= c["x0"] <= w["x1"] and w["top"] - 2 <= c["top"] <= w["bottom"]),
                            key=lambda c: c["x0"])
        if not any(b["x0"] - a["x0"] < SOBREPOSICAO_MAX_PT and a["text"] != b["text"] and a["fontname"] != b["fontname"]
                   for a, b in zip(caracteres, caracteres[1:])):
            continue
        caixa = (max(0.0, w["x0"] - 1.5), max(0.0, w["top"] - 1.5), min(float(pagina.width), w["x1"] + 1.5),
                 min(float(pagina.height), w["bottom"] + 1.5))
        imagem = pagina.crop(caixa).to_image(resolution=RESOLUCAO_OCR_PALAVRA).original
        lido = ocr.texto(imagem, config=f"--psm {10 if len(_CORROMPIDO.sub('x', w['text'])) <= 2 else 7}").strip()
        if lido and not _CORROMPIDO.search(lido):
            w["text"] = lido
            relidas += 1
    return relidas


def _reguas(pagina) -> list[tuple[float, float, float]]:
    """Segmentos horizontais da grade vetorial (y, x0, x1): linhas e retângulos finos. Delimitam linhas de tabela."""
    reguas = [(float(l["top"]), float(l["x0"]), float(l["x1"])) for l in pagina.lines if abs(l["top"] - l["bottom"]) < 1.5]
    for r in pagina.rects:
        if float(r["bottom"]) - float(r["top"]) < 1.5:
            reguas.append((float(r["top"]), float(r["x0"]), float(r["x1"])))
        elif float(r["x1"]) - float(r["x0"]) > 20:      # célula ou moldura: as bordas de cima e de baixo
            reguas += [(float(r["top"]), float(r["x0"]), float(r["x1"])), (float(r["bottom"]), float(r["x0"]), float(r["x1"]))]
    return reguas


def _ler_uma_pagina(numero: int, pagina) -> dict:
    largura = float(pagina.width)
    brutas = pagina.extract_words(x_tolerance_ratio=TOLERANCIA_X_PROPORCIONAL)
    _marcar_fontes_suspeitas(pagina, brutas)
    # Etapa 05.3.5: regiões de texto em contorno. As que não têm texto nativo legível dentro vão ao OCR; as palavras
    # ilegíveis ("(cid:N)") que estiverem dentro delas saem já aqui, para não desviarem a página para a releitura de
    # trecho ilegível (que leria só um pedaço — 07/11/2026, p. 6).
    contornos = regioes_de_contorno(pagina.curves, brutas)
    legiveis = [(x0, topo, min(largura, x1), min(float(pagina.height), base)) for x0, topo, x1, base, dentro in contornos if not dentro]
    if legiveis and ocr_disponivel()[0]:
        brutas = [w for w in brutas if not (_CORROMPIDO.search(w["text"]) and any(
            x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and topo <= (w["top"] + w["bottom"]) / 2 <= base for x0, topo, x1, base in legiveis))]
    sobrepostas = _ler_sobreposicoes(pagina, brutas) if ocr_disponivel()[0] else 0
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas]
    texto, colunas = ler_pagina(palavras, largura, _reguas(pagina))
    base = {"numero": numero, "confianca": None}
    if len(re.sub(r"\s", "", texto)) >= MIN_CARACTERES:
        corrompidos = len(_CORROMPIDO.findall(texto))
        qualidade = "INCONSISTENTE" if corrompidos > max(3, 0.02 * len(palavras)) or corrompidos >= MIN_SINAIS_ILEGIVEIS else "OK"
        avisos = _avisos(pagina, brutas, contornos)
        nativo = {**base, "metodo": "TEXTO+OCR" if sobrepostas else "TEXTO", "colunas": colunas, "texto": texto,
                  "palavras": len(palavras), "qualidade": qualidade, "avisos": avisos}
        if corrompidos and ocr_disponivel()[0]:
            relida = _reler_trechos_ilegiveis(numero, pagina, brutas, legiveis)
            if relida:
                return {**relida, "avisos": avisos}
        if _fracao_coberta_por_imagens(pagina) < FRACAO_IMAGEM_MISTA:
            if ocr_disponivel()[0] and (pagina.images or legiveis):
                # Imagem pequena sem palavras por cima (tabela colada como figura) e região de texto em contorno sem
                # texto nativo dentro: só a região é lida.
                extras, confiancas, sem_leitura = _ler_regioes_sem_texto(pagina, brutas, _imagens_sem_texto(pagina, brutas) + legiveis)
                if extras:
                    confianca = round(sum(confiancas) / len(confiancas), 1)
                    texto, colunas = ler_pagina(palavras + extras, largura, _reguas(pagina))
                    da_regiao = "LEITURA_INCOMPLETA" if sem_leitura else "OK" if confianca >= CONFIANCA_BOA else "BAIXA_CONFIANCA"
                    return {**nativo, "metodo": "TEXTO+OCR", "colunas": colunas, "texto": texto, "palavras": len(palavras) + len(extras),
                            "qualidade": qualidade if qualidade != "OK" else da_regiao, "confianca": confianca}
            return nativo
        # Página mista: cabeçalho em texto e corpo digitalizado, por exemplo. O texto nativo sozinho pode ser só uma parte.
        if not ocr_disponivel()[0]:
            return {**nativo, "qualidade": "TEXTO_PARCIAL" if qualidade == "OK" else qualidade}
        palavras_ocr, confianca, sem_leitura = _ocr_completo(pagina)
        if len(palavras_ocr) > 1.3 * len(palavras) + 15:      # a imagem tinha texto que o PDF não trazia: vale a página inteira por OCR
            return _classificar_ocr(numero, palavras_ocr, confianca, largura, sem_leitura)
        return nativo
    tem_conteudo = bool(pagina.images or pagina.rects or pagina.curves or pagina.lines)
    if not tem_conteudo:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "VAZIA"}
    if not ocr_disponivel()[0]:
        return {**base, "metodo": "NENHUM", "colunas": 0, "texto": "", "palavras": 0, "qualidade": "OCR_INDISPONIVEL"}
    palavras, confianca, sem_leitura = _ocr_completo(pagina)
    return _classificar_ocr(numero, palavras, confianca, largura, sem_leitura)


def _pagina_com_ocr_esgotado(numero: int, pagina) -> dict:
    """O OCR não respondeu a tempo: fica o texto nativo que houver, e a página vira pendência para nova tentativa
    (`processar(..., refazer_pendentes=True)`). O robô segue para a página seguinte em vez de travar."""
    brutas = pagina.extract_words(x_tolerance_ratio=TOLERANCIA_X_PROPORCIONAL)
    palavras = [Palavra(float(w["x0"]), float(w["x1"]), float(w["top"]), w["text"]) for w in brutas]
    texto, colunas = ler_pagina(palavras, float(pagina.width)) if palavras else ("", 0)
    return {"numero": numero, "metodo": "TEXTO" if palavras else "NENHUM", "colunas": colunas, "texto": texto,
            "palavras": len(palavras), "qualidade": "OCR_ESGOTADO", "confianca": None}


def ler_arquivo(caminho: str | Path) -> dict:
    import pdfplumber  # importado aqui para que a coleta funcione sem esta biblioteca

    paginas = []
    ocr.iniciar_arquivo()
    with pdfplumber.open(str(caminho)) as documento:
        for numero, pagina in enumerate(documento.pages, start=1):
            ocr.iniciar_pagina()
            try:
                try:
                    paginas.append(_ler_uma_pagina(numero, pagina))
                except ocr.OcrEsgotado:
                    paginas.append(_pagina_com_ocr_esgotado(numero, pagina))
            finally:
                # Sem isto o pdfplumber guarda caracteres, objetos e o mapa de texto de TODAS as páginas lidas
                # até o fim do arquivo (pico de 0,8–1,2 GB por edição medido em 12/11/2026).
                pagina.close()
    if not paginas:
        raise ValueError("o documento não tem páginas")
    numero_edicao, data_edicao = identificar_edicao(paginas[0]["texto"])
    return {"paginas": paginas, "numero_edicao": numero_edicao, "data_edicao": data_edicao}


def conferir_com_a_origem(resultado: dict, origens) -> list[str]:
    """Compara o que o documento diz de si mesmo com o que a origem informou."""
    achados = []
    if resultado["numero_edicao"] is None:
        achados.append("NUMERO_DA_EDICAO_NAO_IDENTIFICADO")
    if resultado["data_edicao"] is None:
        achados.append("DATA_DA_EDICAO_NAO_IDENTIFICADA")
    else:
        datas = sorted({o["data_publicacao"] for o in origens if o["data_publicacao"]})
        if datas and resultado["data_edicao"] not in datas:
            achados.append(f"DATA_DIVERGENTE: cabeçalho {resultado['data_edicao']}, origem {', '.join(datas)}")
    return achados


def avisos_do_arquivo(paginas: list[dict]) -> list[str]:
    """Avisos das páginas (texto em contorno, imagem não examinada) como inconsistências do arquivo, com as páginas."""
    por_aviso: dict[str, list[int]] = {}
    for p in paginas:
        for aviso in p.get("avisos") or []:
            por_aviso.setdefault(aviso, []).append(p["numero"])
    return [f"{aviso}: página(s) {', '.join(map(str, numeros))}" for aviso, numeros in sorted(por_aviso.items())]


def processar(banco: Banco, acervo: Acervo, limite: int | None = None, refazer_pendentes: bool = False) -> dict:
    """Lê os arquivos do acervo ainda não lidos por esta versão do leitor (de qualquer origem).
    Com `refazer_pendentes`, tenta de novo os que terminaram em erro ou com páginas pendentes."""
    contagem = {"LIDA": 0, "LIDA_COM_PENDENCIAS": 0, "ERRO": 0, "na_fila": 0}
    fila = banco.arquivos_sem_leitura(VERSAO, refazer_pendentes)
    for indice, arquivo in enumerate(fila):
        if limite is not None and indice >= limite:
            contagem["na_fila"] = len(fila) - indice
            break
        sha = arquivo["sha256"]
        try:
            if not acervo.conferir(sha):
                raise ValueError("arquivo ausente ou adulterado no acervo")
            resultado = ler_arquivo(acervo.caminho(sha))
        except Exception as e:  # um arquivo problemático não pode parar a fila
            banco.registrar_leitura(sha, "ERRO", VERSAO, [], None, None, f"{type(e).__name__}: {e}"[:300])
            contagem["ERRO"] += 1
            continue
        inconsistencias = conferir_com_a_origem(resultado, banco.origens(sha)) + avisos_do_arquivo(resultado["paginas"])
        pendencia = inconsistencias or any(p["qualidade"] not in ("OK", "VAZIA") for p in resultado["paginas"])
        situacao = "LIDA_COM_PENDENCIAS" if pendencia else "LIDA"
        comparacao = banco.registrar_leitura(sha, situacao, VERSAO, resultado["paginas"], resultado["numero_edicao"],
                                resultado["data_edicao"], None, inconsistencias)
        if comparacao == "PERDA_DE_CONTEUDO":
            # A tentativa perdeu páginas ou qualidade: a leitura válida anterior foi mantida (Etapa 05.3.3).
            contagem["RELEITURA_RECUSADA"] = contagem.get("RELEITURA_RECUSADA", 0) + 1
            continue
        contagem[situacao] += 1
    return contagem
