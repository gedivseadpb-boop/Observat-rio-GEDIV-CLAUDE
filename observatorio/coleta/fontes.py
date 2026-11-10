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
