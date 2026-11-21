"""Requisições HTTP restritas às fontes oficiais.

Regras aplicadas a toda requisição:
- somente esquemas e servidores previamente autorizados (inclusive após redirecionamento);
- redirecionamentos seguidos manualmente e limitados;
- limite de tamanho da resposta;
- novas tentativas apenas para falhas transitórias (tempo esgotado, conexão, transferência
  truncada e 5xx), com espera progressiva limitada e respeito ao Retry-After;
- HTTP 429 e 403 não são repetidos: são recusas da fonte;
- uma resposta com menos bytes que o Content-Length anunciado é TRUNCADO, mesmo com HTTP 200;
- HTTP 206 (conteúdo parcial) nunca é tratado como arquivo inteiro: o coletor não pede intervalos, e uma resposta 206
  só é aceita se o Content-Range cobrir o arquivo todo (bytes 0-N/N+1) e os bytes recebidos fecharem com ele.
  Outros 2xx que não 200 são recusados;
- cada falha recebe uma categoria, para que o diagnóstico não dependa de texto livre.

A validação TLS é sempre a padrão do Python; não há opção para desativá-la.
"""
from __future__ import annotations

import http.client
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field

AGENTE = "ObservatorioGEDIV/0.1 (+https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE)"
_SEGUROS = "/%@:+,;=~!$&'()*-._"


class ErroRede(Exception):
    def __init__(self, categoria: str, mensagem: str = "", retry_after: float | None = None):
        super().__init__(f"{categoria}: {mensagem}" if mensagem else categoria)
        self.categoria = categoria
        self.retry_after = retry_after

    @property
    def transitorio(self) -> bool:
        # HTTP 429 NÃO é repetido: é um pedido da fonte para parar. Quem decide o que fazer é o lote, que se encerra.
        return self.categoria in {"TEMPO_ESGOTADO", "CONEXAO", "TRUNCADO", "RESPOSTA_PARCIAL"} or self.categoria.startswith("HTTP_5")

    @property
    def recusa(self) -> bool:
        """A fonte recusou o acesso (403/429): não insistir nem tentar endereços alternativos."""
        return self.categoria in {"HTTP_403", "HTTP_429"}


@dataclass(frozen=True)
class Politica:
    servidores: frozenset[str]
    esquemas: frozenset[str] = frozenset({"https"})
    tempo_limite: float = 30.0
    max_bytes: int = 80 * 1024 * 1024
    tentativas: int = 3
    espera: float = 3.0          # base da espera progressiva: espera, 2×espera, 4×espera...
    espera_maxima: float = 60.0  # teto da espera entre tentativas, inclusive quando o Retry-After pede mais
    pausa: float = 1.0  # cortesia entre requisições à mesma fonte
    max_redirecionamentos: int = 5
    agente: str = AGENTE


@dataclass
class Resposta:
    url_final: str
    status: int
    tipo_conteudo: str
    corpo: bytes
    redirecionamentos: list[str] = field(default_factory=list)
    content_length: int | None = None
    segundos: float | None = None
    tentativas: int = 1


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar)


def normalizar(url: str) -> str:
    """Codifica espaços e acentos do caminho sem alterar o que já está codificado."""
    p = urllib.parse.urlsplit(url.strip())
    caminho = urllib.parse.quote(p.path, safe=_SEGUROS)
    consulta = urllib.parse.quote(p.query, safe=_SEGUROS + "?")
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), caminho, consulta, ""))


def validar(url: str, politica: Politica) -> None:
    p = urllib.parse.urlsplit(url)
    if p.scheme not in politica.esquemas:
        raise ErroRede("URL_NAO_PERMITIDA", f"esquema {p.scheme!r}")
    if "@" in p.netloc or p.netloc.lower() not in politica.servidores:
        raise ErroRede("URL_NAO_PERMITIDA", f"servidor {p.netloc!r}")


def _retry_after(valor: str | None) -> float | None:
    if not valor:
        return None
    try:
        return max(0.0, float(valor.strip()))
    except ValueError:
        return None  # data HTTP: não interpretada; a espera progressiva padrão é usada


def _tamanho_anunciado(valor: str | None) -> int | None:
    try:
        return int(valor) if valor is not None and int(valor) >= 0 else None
    except ValueError:
        return None


_FAIXA = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.I)


def _faixa_completa(content_range: str | None, recebidos: int) -> bool:
    """Content-Range de uma resposta 206 que cobre o arquivo INTEIRO e coincide com os bytes recebidos."""
    achado = _FAIXA.fullmatch((content_range or "").strip())
    if not achado:
        return False
    primeiro, ultimo, total = (int(x) for x in achado.groups())
    return primeiro == 0 and ultimo + 1 == total == recebidos


def _uma_requisicao(url: str, politica: Politica) -> Resposta:
    redirecionamentos: list[str] = []
    atual = normalizar(url)
    for _ in range(politica.max_redirecionamentos + 1):
        validar(atual, politica)
        pedido = urllib.request.Request(atual, headers={"User-Agent": politica.agente, "Accept": "*/*"})
        inicio = time.monotonic()
        try:
            with _ABRIDOR.open(pedido, timeout=politica.tempo_limite) as r:
                anunciado = _tamanho_anunciado(r.headers.get("Content-Length"))
                if anunciado is not None and anunciado > politica.max_bytes:
                    raise ErroRede("TAMANHO_EXCEDIDO", f"{anunciado} bytes anunciados")
                blocos, total = [], 0
                while bloco := r.read(65536):
                    total += len(bloco)
                    if total > politica.max_bytes:
                        raise ErroRede("TAMANHO_EXCEDIDO", f"mais de {politica.max_bytes} bytes")
                    blocos.append(bloco)
                if anunciado is not None and total != anunciado:
                    raise ErroRede("TRUNCADO", f"{atual} ({total} de {anunciado} bytes)")
                if r.status == 206 and not _faixa_completa(r.headers.get("Content-Range"), total):
                    raise ErroRede("RESPOSTA_PARCIAL", f"{atual} (HTTP 206, {r.headers.get('Content-Range') or 'sem Content-Range'})")
                if r.status not in (200, 206):
                    raise ErroRede(f"HTTP_{r.status}", f"{atual} (resposta sem o conteúdo esperado)")
                return Resposta(atual, r.status, r.headers.get("Content-Type", ""), b"".join(blocos), redirecionamentos,
                                anunciado, round(time.monotonic() - inicio, 3))
        except http.client.IncompleteRead as e:
            raise ErroRede("TRUNCADO", f"{atual} ({len(e.partial)} bytes antes da interrupção)") from None
        except urllib.error.HTTPError as e:
            destino = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
            espera = _retry_after(e.headers.get("Retry-After")) if e.code in (429, 503) else None
            e.close()
            if not destino:
                raise ErroRede(f"HTTP_{e.code}", atual, retry_after=espera) from None
            atual = normalizar(urllib.parse.urljoin(atual, destino))
            redirecionamentos.append(atual)
        except (socket.timeout, TimeoutError):
            raise ErroRede("TEMPO_ESGOTADO", atual) from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise ErroRede("TEMPO_ESGOTADO", atual) from None
            if "tunnel connection failed" in str(e.reason).lower():
                # Quem recusou foi o proxy do executor, não a fonte: não é evidência sobre o portal oficial.
                raise ErroRede("PROXY_RECUSOU", f"{atual} ({e.reason})") from None
            raise ErroRede("CONEXAO", f"{atual} ({e.reason})") from None
        except (ConnectionError, OSError) as e:
            if "tunnel connection failed" in str(e).lower():
                raise ErroRede("PROXY_RECUSOU", f"{atual} ({e})") from None
            raise ErroRede("CONEXAO", f"{atual} ({e})") from None
    raise ErroRede("REDIRECIONAMENTOS", f"mais de {politica.max_redirecionamentos}")


def espera_entre_tentativas(politica: Politica, tentativa: int, erro: ErroRede) -> float:
    """Espera progressiva (espera × 2^(n-1)); o Retry-After da fonte prevalece se for maior. Sempre com teto."""
    progressiva = politica.espera * (2 ** (tentativa - 1))
    pedida = erro.retry_after or 0.0
    return min(max(progressiva, pedida), politica.espera_maxima)


def obter(url: str, politica: Politica, dormir=time.sleep) -> Resposta:
    ultimo: ErroRede | None = None
    for tentativa in range(1, politica.tentativas + 1):
        try:
            resposta = _uma_requisicao(url, politica)
            resposta.tentativas = tentativa
            return resposta
        except ErroRede as e:
            ultimo = e
            if not e.transitorio or tentativa == politica.tentativas:
                break
            dormir(espera_entre_tentativas(politica, tentativa, e))
    assert ultimo is not None
    raise ultimo


def texto(resposta: Resposta) -> str:
    for codificacao in ("utf-8", "latin-1"):
        try:
            return resposta.corpo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return resposta.corpo.decode("utf-8", "replace")


def consultar_robots(url_base: str, politica: Politica) -> tuple[str, urllib.robotparser.RobotFileParser | None]:
    """Lê o robots.txt do servidor. Devolve (situação, regras).

    Situações: LIDO, AUSENTE (404/410: sem restrições declaradas), RECUSADO (403/429 ou outro 4xx:
    a fonte negou a consulta, o que não autoriza presumir ausência de restrições), NAO_E_ROBOTS
    (o servidor devolveu uma página HTML no lugar do arquivo) ou INACESSIVEL.
    """
    p = urllib.parse.urlsplit(url_base)
    endereco = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        resposta = obter(endereco, politica)
    except ErroRede as e:
        if e.categoria in ("HTTP_404", "HTTP_410"):
            return "AUSENTE", None
        if e.categoria.startswith("HTTP_4"):
            return "RECUSADO", None
        return "INACESSIVEL", None
    conteudo = texto(resposta)
    if conteudo.lstrip().startswith("<"):
        return "NAO_E_ROBOTS", None
    regras = urllib.robotparser.RobotFileParser()
    regras.parse(conteudo.splitlines())
    return "LIDO", regras
