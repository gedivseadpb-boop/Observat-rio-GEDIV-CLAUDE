"""Identificação de apresentação, sem modificar atos ou inferir emitente pela gerência.

Somente nomes institucionais controlados saem do cabeçalho lido. O texto do ato
(que pode conter dados pessoais) nunca é devolvido como evidência pública.
"""
from __future__ import annotations

from datetime import date
import re

from ..gerencias.gediv import catalogo as C
from ..gerencias.gediv.classificador import PAT_GEDIV

CAMPOS = ("gerencia_painel", "orgao_emitente", "unidade_emissora", "tipo_publicacao",
          "sufixo_documental", "numero_edicao", "data_edicao", "pdf_sha256", "identificacao_documental")
CABECALHO_EXPORTACAO = ["Painel/gerência", "Órgão emitente (cabeçalho lido)", "Unidade emissora (cabeçalho lido)",
                       "Tipo de publicação", "Sufixo institucional lido", "Edição DOE lida", "Data da edição lida",
                       "SHA-256 do PDF", "Identificação documental (conferir na fonte)"]

_DISPOSITIVO = re.compile(r"\b(?:O|A)\s+(?:SECRETARI[OA]|DIRETOR[A]?|PRESIDENTE)\b"
                         r"|\b(?:RESOLVE|DEFERIR|DEFERIU|INDEFERIR|INDEFERIU|USANDO)\b")
_SEAD = re.compile(r"^(?:GOVERNO DO ESTADO DA PARAIBA\s+)?SECRETARIA DE ESTADO DA ADMINISTRACAO\b")
_PBPREV = re.compile(r"^(?:PBPREV\b|PARAIBA PREVIDENCIA\b|RESENHA\s*/\s*PBPREV\s*/)")


def _instituicao(texto):
    cabecalho = re.sub(r"\s+", " ", C.normalizar(str(texto)[:1200])).strip()
    fim = _DISPOSITIVO.search(cabecalho)
    if fim:
        cabecalho = cabecalho[:fim.start()]
    sead, pbprev = bool(_SEAD.match(cabecalho)), bool(_PBPREV.match(cabecalho))
    # Cabeçalho contraditório: não escolher a entidade pela primeira menção.
    if (sead or pbprev) and re.search(r"\bSECRETARIA DE ESTADO D[AEO]S?\s+(?!ADMINISTRACAO\b)[A-Z]", cabecalho):
        return "EMITENTE_NAO_CONFIRMADO", "", "EMITENTE_NAO_CONFIRMADO"
    if sead and re.search(r"[-/]\s*PBPREV\b|PARAIBA PREVIDENCIA", cabecalho):
        return "EMITENTE_NAO_CONFIRMADO", "", "EMITENTE_NAO_CONFIRMADO"
    if pbprev and "SECRETARIA DE ESTADO DA ADMINISTRACAO" in cabecalho:
        return "EMITENTE_NAO_CONFIRMADO", "", "EMITENTE_NAO_CONFIRMADO"
    if sead:
        unidades = []
        if re.search(r"\bDEREH\b|DIRETORIA EXECUTIVA DE RECURSOS HUMANOS", cabecalho):
            unidades.append("DEREH")
        if PAT_GEDIV.search(cabecalho):
            unidades.append("GEDIV")
        return "SEAD — Secretaria de Estado da Administração", " / ".join(unidades), "SEAD"
    if pbprev:
        unidade = "GP" if re.search(r"/\s*GP\s*/", cabecalho) else ""
        return "PBPREV — Paraíba Previdência", unidade, "PBPREV"
    return "EMITENTE_NAO_CONFIRMADO", "", "EMITENTE_NAO_CONFIRMADO"


def identificar(registro: dict) -> dict:
    """Deriva só metadados visíveis; ausências continuam ausentes, inclusive sufixo."""
    orgao, unidade, sigla = _instituicao(registro.get("texto_identificacao") or "")
    tipo = registro.get("tipo") if registro.get("tipo") in ("RESENHA", "PORTARIA") else "PUBLICACAO"
    numero = str(registro.get("resenha") or "")
    if not re.fullmatch(r"\d{1,5}/20\d{2}", numero):
        numero = "s/ número"
    edicao = str(registro.get("numero_edicao") or "").strip().replace(".", "")
    if not re.fullmatch(r"\d{1,6}", edicao) or int(edicao) == 0:
        edicao = ""
    data = str(registro.get("data_edicao") or "")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            raise ValueError
        dia = date.fromisoformat(data)
    except ValueError:
        data, dia = "", None
    sha = str(registro.get("sha256") or "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
        sha = ""
    sufixo = str(registro.get("sufixo") or "")
    if not re.fullmatch(r"(?:[-/][A-Z]{2,10})+", sufixo):
        sufixo = ""
    pagina = registro.get("pagina")
    pagina = str(pagina) if isinstance(pagina, int) and not isinstance(pagina, bool) and pagina > 0 else "não informada"
    contexto = sigla + (" / " + unidade if unidade else "")
    publicacao = {"RESENHA": "Resenha", "PORTARIA": "Portaria", "PUBLICACAO": "Publicação"}[tipo]
    fonte = f"DOE {edicao}" if edicao else "DOE (edição não informada)"
    if dia:
        fonte += f", {dia.day:02d}/{dia.month:02d}/{dia.year}"
    return dict(zip(CAMPOS, ("GEDIV" if registro.get("gerencia_painel") == "GEDIV" else "",
                             orgao, unidade, tipo, sufixo, edicao, data, sha,
                             f"{contexto} — {publicacao} {numero} — {fonte}, p.{pagina}")))


def valores_exportacao(registro: dict) -> list:
    return [registro.get(campo, "") for campo in CAMPOS]
