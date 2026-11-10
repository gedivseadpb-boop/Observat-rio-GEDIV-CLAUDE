"""Guarda dos PDFs originais, endereçados pelo próprio conteúdo (SHA-256).

Um mesmo arquivo nunca é gravado duas vezes e um arquivo gravado nunca é
sobrescrito. A pasta do acervo fica fora do controle de versão.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ErroAcervo(Exception):
    pass


class Acervo:
    def __init__(self, raiz: str | Path):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    def caminho_relativo(self, sha256: str) -> str:
        return f"{sha256[:2]}/{sha256}.pdf"

    def caminho(self, sha256: str) -> Path:
        return self.raiz / self.caminho_relativo(sha256)

    def guardar(self, dados: bytes) -> tuple[str, bool]:
        """Grava os bytes. Devolve (sha256, gravou_agora)."""
        sha = hashlib.sha256(dados).hexdigest()
        destino = self.caminho(sha)
        if destino.exists():
            if not self.conferir(sha):
                raise ErroAcervo(f"arquivo existente corrompido: {sha}")
            return sha, False
        destino.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(dir=destino.parent, suffix=".parcial")
        try:
            with os.fdopen(descritor, "wb") as saida:
                saida.write(dados)
                saida.flush()
                os.fsync(saida.fileno())
            os.replace(temporario, destino)
        except BaseException:
            Path(temporario).unlink(missing_ok=True)
            raise
        return sha, True

    def ler(self, sha256: str) -> bytes:
        return self.caminho(sha256).read_bytes()

    def conferir(self, sha256: str) -> bool:
        """Recalcula o SHA-256 do arquivo guardado."""
        caminho = self.caminho(sha256)
        if not caminho.is_file():
            return False
        resumo = hashlib.sha256()
        with caminho.open("rb") as entrada:
            for bloco in iter(lambda: entrada.read(1 << 20), b""):
                resumo.update(bloco)
        return resumo.hexdigest() == sha256
