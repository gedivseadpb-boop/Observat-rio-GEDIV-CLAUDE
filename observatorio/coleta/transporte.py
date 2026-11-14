"""Contrato de transporte: COMO os bytes de uma publicação chegam ao coletor.

A aquisição de bytes fica separada da verificação, do acervo e da leitura. Todo transporte
devolve uma ``rede.Resposta`` e tem um ``nome`` que vai para o manifesto de downloads, para
que a procedência de cada arquivo fique explícita.

Transportes previstos:
- ``direto``: requisição HTTPS à fonte oficial, com a política de ``nucleo.rede``. É o único
  que comprova acesso automático à fonte.
- ``manifesto_contingencia``: arquivos obtidos por outro meio (por exemplo, baixados por uma
  pessoa no navegador) e listados num manifesto com a URL oficial e o SHA-256. Serve para não
  parar a leitura enquanto o acesso direto está bloqueado. NÃO comprova coleta automática e não
  deve virar rotina permanente.
- ``relay autorizado``: NÃO implementado. Só poderá existir com autorização documentada da
  fonte ou do órgão responsável, e nunca para contornar bloqueios ou proteções.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from ..nucleo import rede


class Transporte(Protocol):
    nome: str

    def obter(self, url: str, politica: rede.Politica) -> rede.Resposta: ...


class Direto:
    nome = "direto"

    def __init__(self, dormir=None):
        self._dormir = dormir

    def obter(self, url: str, politica: rede.Politica) -> rede.Resposta:
        if self._dormir is None:
            return rede.obter(url, politica)
        return rede.obter(url, politica, dormir=self._dormir)


class ManifestoContingencia:
    """Serve arquivos locais listados num manifesto JSON: ``{"URL_OFICIAL": {"arquivo": "nome.pdf", "sha256": "..."}}``.

    O arquivo só é entregue se o SHA-256 conferir com o manifesto; caso contrário, ``CONTINGENCIA_DIVERGENTE``.
    """

    nome = "manifesto_contingencia"

    def __init__(self, manifesto: str | Path):
        self.manifesto = Path(manifesto)
        self.itens = json.loads(self.manifesto.read_text(encoding="utf-8"))

    def obter(self, url: str, politica: rede.Politica) -> rede.Resposta:
        rede.validar(rede.normalizar(url), politica)       # a URL continua precisando ser de uma fonte autorizada
        item = self.itens.get(url) or self.itens.get(rede.normalizar(url))
        if not item:
            raise rede.ErroRede("CONTINGENCIA_SEM_ARQUIVO", url)
        dados = (self.manifesto.parent / item["arquivo"]).read_bytes()
        if hashlib.sha256(dados).hexdigest() != item.get("sha256"):
            raise rede.ErroRede("CONTINGENCIA_DIVERGENTE", url)
        return rede.Resposta(url, 200, "application/pdf", dados, [], len(dados), 0.0)
