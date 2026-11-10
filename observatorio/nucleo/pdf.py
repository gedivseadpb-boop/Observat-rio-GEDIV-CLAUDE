"""Verificação estrutural mínima de um PDF recebido.

Não interpreta o conteúdo: apenas confirma que os bytes são um PDF completo
e calcula a impressão digital (SHA-256) usada para integridade e duplicidade.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

TAMANHO_MINIMO = 1024


@dataclass(frozen=True)
class Laudo:
    valido: bool
    motivo: str | None
    tamanho: int
    sha256: str


def examinar(dados: bytes, tamanho_minimo: int = TAMANHO_MINIMO) -> Laudo:
    tamanho = len(dados)
    sha = hashlib.sha256(dados).hexdigest()
    motivo = None
    if tamanho == 0:
        motivo = "VAZIO"
    elif b"%PDF-" not in dados[:1024]:
        inicio = dados[:512].lstrip().lower()
        if inicio.startswith((b"<!doctype", b"<html", b"<?xml")):
            motivo = "RECEBIDO_HTML_EM_VEZ_DE_PDF"
        else:
            motivo = "SEM_ASSINATURA_PDF"
    elif tamanho < tamanho_minimo:
        motivo = "MUITO_PEQUENO"
    elif b"%%EOF" not in dados[-4096:]:
        motivo = "SEM_FIM_DE_ARQUIVO"  # download truncado
    return Laudo(motivo is None, motivo, tamanho, sha)
