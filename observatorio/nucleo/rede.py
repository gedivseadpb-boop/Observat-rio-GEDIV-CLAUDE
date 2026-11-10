"""Requisições HTTP restritas às fontes oficiais.

Regras aplicadas a toda requisição:
- somente esquemas e servidores previamente autorizados (inclusive após redirecionamento);
- redirecionamentos seguidos manualmente e limitados;
- limite de tamanho da resposta;
- novas tentativas apenas para falhas transitórias (tempo esgotado, conexão, 429 e 5xx);
- cada falha recebe uma categoria, para que o diagnóstico não dependa de texto livre.
"""
from __future__ import annotations

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
    def __init__(self, categoria: str, mensagem: str = ""):
        super().__init__(f"{categoria}: {mensagem}" if mensagem else categoria)
        self.categoria = categoria

    @property
    def transitorio(self) -> bool:
        return self.categoria in {"TEMPO_ESGOTADO", "CONEXAO", "HTTP_429"} or self.categoria.startswith("HTTP_5")


@dataclass(frozen=True)
class Politica:
    servidores: frozenset[str]
    esquemas: frozenset[str] = frozenset({"https"})
    tempo_limite: float = 30.0
    max_bytes: int = 80 * 1024 * 1024
    tentativas: int = 3
    espera: float = 3.0
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


def _uma_requisicao(url: str, politica: Politica) -> Resposta:
    redirecionamentos: list[str] = []
    atual = normalizar(url)
    for _ in range(politica.max_redirecionamentos + 1):
        validar(atual, politica)
        pedido = urllib.request.Request(atual, headers={"User-Agent": politica.agente, "Accept": "*/*"})
        try:
            with _ABRIDOR.open(pedido, timeout=politica.tempo_limite) as r:
                blocos, total = [], 0
                while bloco := r.read(65536):
                    total += len(bloco)
                    if total > politica.max_bytes:
                        raise ErroRede("TAMANHO_EXCEDIDO", f"mais de {politica.max_bytes} bytes")
                    blocos.append(bloco)
                return Resposta(atual, r.status, r.headers.get("Content-Type", ""), b"".join(blocos), redirecionamentos)
        except urllib.error.HTTPError as e:
            destino = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
            e.close()
            if not destino:
                raise ErroRede(f"HTTP_{e.code}", atual) from None
            atual = normalizar(urllib.parse.urljoin(atual, destino))
            redirecionamentos.append(atual)
        except (socket.timeout, TimeoutError):
            raise ErroRede("TEMPO_ESGOTADO", atual) from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise ErroRede("TEMPO_ESGOTADO", atual) from None
            raise ErroRede("CONEXAO", f"{atual} ({e.reason})") from None
        except (ConnectionError, OSError) as e:
            raise ErroRede("CONEXAO", f"{atual} ({e})") from None
    raise ErroRede("REDIRECIONAMENTOS", f"mais de {politica.max_redirecionamentos}")


def obter(url: str, politica: Politica) -> Resposta:
    ultimo: ErroRede | None = None
    for tentativa in range(1, politica.tentativas + 1):
        try:
            return _uma_requisicao(url, politica)
        except ErroRede as e:
            ultimo = e
            if not e.transitorio or tentativa == politica.tentativas:
                break
            time.sleep(politica.espera * tentativa)
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

    Situações: LIDO, AUSENTE (4xx: sem restrições declaradas), NAO_E_ROBOTS
    (o servidor devolveu uma página HTML no lugar do arquivo) ou INACESSIVEL.
    """
    p = urllib.parse.urlsplit(url_base)
    endereco = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        resposta = obter(endereco, politica)
    except ErroRede as e:
        if e.categoria.startswith("HTTP_4"):
            return "AUSENTE", None
        return "INACESSIVEL", None
    conteudo = texto(resposta)
    if conteudo.lstrip().startswith("<"):
        return "NAO_E_ROBOTS", None
    regras = urllib.robotparser.RobotFileParser()
    regras.parse(conteudo.splitlines())
    return "LIDO", regras
