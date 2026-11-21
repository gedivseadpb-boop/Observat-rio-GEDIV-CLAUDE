"""Fontes oficiais do DOE/PB e leitura das suas listagens.

Cada fonte sabe apenas: onde fica a listagem de um mês, como reconhecer
os links de PDF nessa listagem e em quais endereços tentar o download.
A leitura é propositalmente tolerante à estrutura da página: considera
todos os links e filtra pelo formato do endereço.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from ..nucleo.rede import normalizar

_DATA = re.compile(r"(?<!\d)(\d{2})[-_.](\d{2})[-_.](20\d{2})(?!\d)")
_ORDEM = re.compile(r"-portal-(\d+)\.pdf$", re.I)


@dataclass(frozen=True)
class Item:
    fonte: str
    url: str
    data: date | None
    tipo: str  # normal | suplemento | extra
    ordem: int
    rotulo: str


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._fechar()
            self._href = dict(attrs).get("href")
            self._texto = []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            self._fechar()

    def _fechar(self):
        if self._href:
            self.links.append((self._href, " ".join("".join(self._texto).split())))
        self._href = None

    def close(self):
        super().close()
        self._fechar()


def links(html: str) -> list[tuple[str, str]]:
    leitor = _Links()
    leitor.feed(html)
    leitor.close()
    return leitor.links


def data_do_nome(nome: str) -> date | None:
    achado = _DATA.search(nome)
    if not achado:
        return None
    dia, mes, ano = (int(x) for x in achado.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def tipo_do_nome(nome: str) -> str:
    baixo = nome.lower()
    if "suplemento" in baixo:
        return "suplemento"
    if "extra" in baixo:
        return "extra"
    return "normal"


class AUniao:
    """Arquivo digital do DOE mantido pela A União (fonte principal)."""

    sigla = "auniao"
    MESES = ["", "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

    def __init__(self, base: str = "https://auniao.pb.gov.br", pastas_ano: dict[int, str] | None = None):
        self.base = base.rstrip("/")
        self.servidor = urllib.parse.urlsplit(self.base).netloc
        self.servidores = frozenset({self.servidor, "www." + self.servidor})
        # O nome da pasta do ano nem sempre é o próprio ano (2025 está publicado como "2025-1").
        self.pastas_ano = {2025: "2025-1", **(pastas_ano or {})}

    def url_mes(self, ano: int, mes: int) -> str:
        return f"{self.base}/servicos/doe/{self.pastas_ano.get(ano, str(ano))}/{self.MESES[mes]}"

    def url_recentes(self) -> str:
        """Listagem "Edições recentes" (12 por página, paginada por ?b_start:int=N). Estrutura conferida em 14/11/2026."""
        return f"{self.base}/doe/edicoes-recentes"

    def extrair(self, html: str, url_pagina: str) -> tuple[list[Item], list[str]]:
        itens: dict[str, Item] = {}
        paginas: list[str] = []
        caminho_pagina = urllib.parse.urlsplit(url_pagina).path.rstrip("/")
        for href, texto in links(html):
            absoluto = urllib.parse.urljoin(url_pagina, href)
            p = urllib.parse.urlsplit(absoluto)
            if p.netloc.lower() not in self.servidores:
                continue
            if "b_start" in p.query and p.path.rstrip("/") == caminho_pagina:
                pagina = normalizar(absoluto)
                if pagina not in paginas:
                    paginas.append(pagina)
                continue
            corte = p.path.lower().find(".pdf")
            if corte < 0 or "/servicos/doe/" not in p.path.lower():
                continue
            caminho = p.path[: corte + 4]  # descarta /view e /@@download/...
            canonica = normalizar(f"https://{self.servidor}{caminho}")
            nome = urllib.parse.unquote(caminho.rsplit("/", 1)[-1])
            ordem = _ORDEM.search(nome)
            itens.setdefault(canonica, Item(self.sigla, canonica, data_do_nome(nome), tipo_do_nome(nome),
                                            int(ordem.group(1)) if ordem else 0, texto or nome))
        return list(itens.values()), paginas

    def enderecos_download(self, url: str) -> list[str]:
        return [url, url + "/@@download/file"]


class CGE:
    """Consulta ao DOE mantida pela Controladoria Geral do Estado (fonte complementar)."""

    sigla = "cge"

    def __init__(self, base: str = "https://cge.pb.gov.br"):
        self.base = base.rstrip("/")
        self.servidor = urllib.parse.urlsplit(self.base).netloc
        self.servidores = frozenset({self.servidor})

    def url_mes(self, ano: int, mes: int) -> str:
        return f"{self.base}/gati/sap/sap26.asp?a={ano}&m={mes:02d}"

    def extrair(self, html: str, url_pagina: str) -> tuple[list[Item], list[str]]:
        itens: dict[str, Item] = {}
        for href, texto in links(html):
            absoluto = urllib.parse.urljoin(url_pagina, href.replace("\\", "/"))
            p = urllib.parse.urlsplit(absoluto)
            if p.netloc.lower() not in self.servidores:
                continue
            if not p.path.lower().endswith(".pdf") or "/doe/" not in p.path.lower():
                continue
            url = normalizar(f"https://{self.servidor}{p.path}")
            nome = urllib.parse.unquote(p.path.rsplit("/", 1)[-1])
            itens.setdefault(url, Item(self.sigla, url, data_do_nome(nome), tipo_do_nome(nome), 0, texto or nome))
        return list(itens.values()), []

    def enderecos_download(self, url: str) -> list[str]:
        return [url]


FONTES = {"auniao": AUniao, "cge": CGE}

# Padrão ÚNICO de fontes para coletar e medir cobertura quando o operador não escolhe: a A União, fonte principal.
# A CGE é complementar e entra quando pedida (--fonte cge). Todo relatório de cobertura declara as fontes
# consideradas e se elas são TODAS as configuradas — cobertura de uma fonte nunca é apresentada como geral.
PADRAO = ("auniao",)
CONFIGURADAS = tuple(sorted(FONTES))


def selecionar(siglas=None) -> list[str]:
    """As fontes escolhidas explicitamente pelo operador, ou o padrão único."""
    escolhidas = list(dict.fromkeys(siglas or PADRAO))
    desconhecidas = [s for s in escolhidas if s not in FONTES]
    if desconhecidas:
        raise ValueError(f"fonte(s) desconhecida(s): {desconhecidas}")
    return escolhidas


# --- validação do CONTEÚDO da listagem ------------------------------------------------------------------------
# HTTP 200, sozinho, não prova que a página é a listagem: pode ser manutenção, desafio anti-robô, erro ou um HTML
# novo que o leitor de links não reconhece. Sem itens, o mês só é dado como vazio diante de uma mensagem EXPLÍCITA
# de pasta vazia; em qualquer outro caso, a ausência de links é falha de descoberta, nunca ausência de publicação.
VALIDA, VAZIA_COMPROVADA = "VALIDA", "VAZIA_COMPROVADA"
MANUTENCAO, BLOQUEIO, ERRO_NA_PAGINA, FORMATO_DESCONHECIDO = "MANUTENCAO", "BLOQUEIO", "ERRO_NA_PAGINA", "FORMATO_DESCONHECIDO"
_BLOQUEIO = re.compile(r"captcha|cf-chl|cf_chl|just a moment|attention required|access denied|acesso negado|"
                       r"are you a (?:human|robot)|verifica[cç][aã]o de seguran[cç]a|request (?:was )?blocked|"
                       r"acesso bloqueado|too many requests|muitas requisi[cç][oõ]es", re.I)
_MANUTENCAO = re.compile(r"em manuten[cç][aã]o|under maintenance|maintenance mode|temporariamente indispon[ií]vel|"
                         r"service (?:temporarily )?unavailable|site em atualiza[cç][aã]o", re.I)
_ERRO = re.compile(r"p[aá]gina n[aã]o encontrada|page not found|404 not found|erro interno|internal server error|"
                   r"ocorreu um erro|an error (?:has )?occurred|error 5\d\d|exception", re.I)
_VAZIA = re.compile(r"n[aã]o h[aá] (?:itens|documentos|arquivos) nesta pasta|there are currently no items in this folder|"
                    r"esta pasta (?:est[aá] )?vazia|nenhum (?:item|documento|arquivo) (?:foi )?encontrado|"
                    r"nenhuma edi[cç][aã]o (?:foi )?(?:publicada|encontrada)", re.I)
_TAGS = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.I | re.S)


def classificar_listagem(html: str, itens: list[Item]) -> str:
    if itens:
        return VALIDA
    if _BLOQUEIO.search(html):              # o desafio costuma estar em scripts; procura no HTML inteiro
        return BLOQUEIO
    texto = " ".join(_TAGS.sub(" ", html).split())
    if _MANUTENCAO.search(texto):
        return MANUTENCAO
    if _ERRO.search(texto):
        return ERRO_NA_PAGINA
    if _VAZIA.search(texto):
        return VAZIA_COMPROVADA
    return FORMATO_DESCONHECIDO


def e_pagina_de_bloqueio(corpo: bytes) -> bool:
    """HTML de desafio/recusa recebido no lugar de um PDF."""
    return bool(_BLOQUEIO.search(corpo[:65536].decode("utf-8", "replace")))
