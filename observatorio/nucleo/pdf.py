"""Verificação estrutural de um PDF recebido.

Não interpreta o conteúdo: confirma que os bytes formam um PDF completo e calcula
a impressão digital (SHA-256) usada para integridade e duplicidade.

Nenhum indício isolado é suficiente. Um download pode chegar com HTTP 200 e ainda
assim truncado (caso real de 07/11/2026). Por isso as verificações são combinadas:

1. assinatura ``%PDF-`` no início e ausência de página HTML no lugar do PDF;
2. tamanho recebido igual ao ``Content-Length`` anunciado, quando houver;
3. marcador ``%%EOF`` no fim e ``startxref`` apontando para dentro do arquivo,
   para uma tabela ``xref`` ou um objeto (fluxo de referências);
4. leitura da estrutura com o pypdf: catálogo, árvore de páginas e contagem de páginas.

Resultados:
- ``valido=True`` e ``integridade="ESTRUTURA_VERIFICADA"``: pode seguir para o acervo;
- ``valido=False`` com motivo de transferência (``TAMANHO_DIVERGENTE``, ``SEM_FIM_DE_ARQUIVO``...):
  baixar de novo;
- ``valido=False`` e ``quarentena=True``: os bytes parecem completos, mas a estrutura não pôde
  ser confirmada. O arquivo é retido à parte para diagnóstico e não entra no acervo nem na leitura.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field

TAMANHO_MINIMO = 1024
_STARTXREF = re.compile(rb"startxref\s+(\d+)\s+%%EOF", re.S)

# Motivos que indicam transferência incompleta: a nova tentativa de download é o remédio.
TRANSFERENCIA = frozenset({"VAZIO", "MUITO_PEQUENO", "SEM_FIM_DE_ARQUIVO", "TAMANHO_DIVERGENTE"})


@dataclass(frozen=True)
class Laudo:
    valido: bool
    motivo: str | None
    tamanho: int
    sha256: str
    paginas: int | None = None
    integridade: str = "NAO_VERIFICADA"
    quarentena: bool = False
    alertas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def truncado(self) -> bool:
        return self.motivo in TRANSFERENCIA


def _minimo(dados: bytes, tamanho_minimo: int) -> str | None:
    if not dados:
        return "VAZIO"
    if b"%PDF-" not in dados[:1024]:
        inicio = dados[:512].lstrip().lower()
        if inicio.startswith((b"<!doctype", b"<html", b"<?xml")):
            return "RECEBIDO_HTML_EM_VEZ_DE_PDF"
        return "SEM_ASSINATURA_PDF"
    if len(dados) < tamanho_minimo:
        return "MUITO_PEQUENO"
    if b"%%EOF" not in dados[-4096:]:
        return "SEM_FIM_DE_ARQUIVO"  # download truncado
    return None


def examinar(dados: bytes, tamanho_minimo: int = TAMANHO_MINIMO) -> Laudo:
    """Verificação mínima (assinatura, tamanho e fim de arquivo). Mantida para a leitura e a importação."""
    motivo = _minimo(dados, tamanho_minimo)
    return Laudo(motivo is None, motivo, len(dados), hashlib.sha256(dados).hexdigest(),
                 integridade="MINIMA" if motivo is None else "REPROVADA")


def _startxref(dados: bytes) -> str | None:
    """Confere se o último ``startxref`` aponta para uma tabela xref ou um objeto dentro do arquivo."""
    achados = list(_STARTXREF.finditer(dados[-2048:]))
    if not achados:
        return "SEM_STARTXREF"
    deslocamento = int(achados[-1].group(1))
    if deslocamento <= 0 or deslocamento >= len(dados):
        return "STARTXREF_FORA_DO_ARQUIVO"
    alvo = dados[deslocamento:deslocamento + 32].lstrip()
    if not (alvo.startswith(b"xref") or re.match(rb"\d+\s+\d+\s+obj", alvo)):
        return "STARTXREF_INCONSISTENTE"
    return None


def _paginas(dados: bytes) -> tuple[int | None, str | None]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependência declarada em requirements.txt
        return None, "PYPDF_INDISPONIVEL"
    try:
        leitor = PdfReader(io.BytesIO(dados), strict=False)
        total = len(leitor.pages)
    except Exception as erro:  # qualquer falha estrutural vira diagnóstico, nunca exceção
        return None, f"ESTRUTURA_ILEGIVEL ({type(erro).__name__})"
    if total <= 0:
        return 0, "SEM_PAGINAS"
    return total, None


def verificar(dados: bytes, tamanho_esperado: int | None = None, tamanho_minimo: int = TAMANHO_MINIMO) -> Laudo:
    """Verificação completa usada na coleta (ver a docstring do módulo)."""
    sha = hashlib.sha256(dados).hexdigest()
    tamanho = len(dados)
    if tamanho_esperado is not None and tamanho != tamanho_esperado:
        return Laudo(False, "TAMANHO_DIVERGENTE", tamanho, sha, integridade="REPROVADA",
                     alertas=(f"recebidos {tamanho} de {tamanho_esperado} bytes anunciados",))
    motivo = _minimo(dados, tamanho_minimo)
    if motivo:
        return Laudo(False, motivo, tamanho, sha, integridade="REPROVADA")
    alertas = []
    if tamanho_esperado is None:
        alertas.append("SEM_CONTENT_LENGTH")
    problema_xref = _startxref(dados)
    paginas, problema = _paginas(dados)
    if problema_xref:
        alertas.append(problema_xref)
    if problema:
        # Os bytes têm início e fim de PDF, mas a estrutura não foi confirmada: quarentena, não descarte.
        return Laudo(False, problema, tamanho, sha, paginas=paginas, integridade="INCONCLUSIVA",
                     quarentena=True, alertas=tuple(alertas))
    return Laudo(True, None, tamanho, sha, paginas=paginas,
                 integridade="ESTRUTURA_VERIFICADA" if not problema_xref else "ESTRUTURA_VERIFICADA_COM_ALERTA",
                 alertas=tuple(alertas))
