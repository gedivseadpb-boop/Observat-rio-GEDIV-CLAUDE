"""Servidor HTTP do painel: API JSON + dashboard estático. Somente biblioteca padrão.

Perfis:
- público (sem credencial): apenas indicadores e séries AGREGADOS de registros conferidos. Nenhum
  nome, matrícula, processo, trecho de texto ou PDF é entregue;
- gerência (credencial no cabeçalho `Authorization: Bearer ...`): linhas individualizadas, fila de
  pendências, revisão, exportações e PDFs do acervo.

A autorização é verificada no servidor em todas as rotas. Duas formas de credencial da gerência:
- conta individual (usuário e senha, `observatorio.web.contas`): POST /api/login devolve um token de sessão;
  quem conferir, corrigir ou rejeitar fica registrado pelo NOME DA CONTA, não por um nome digitado;
- credencial técnica única (variável GEDIV_TOKEN_GERENCIA), mantida por compatibilidade.
O servidor escuta em 127.0.0.1 por padrão.

Painel de administração em outro endereço (por exemplo, a página estática /admin-painel no GitHub Pages): as
origens autorizadas são informadas em `origens_admin`; só elas recebem os cabeçalhos CORS. A página não contém
dados: tudo vem desta API, depois do login.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import NOME, __version__
from .contas import AcessoNegado, Contas
from ..gerencias.gediv import catalogo
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from ..painel import adaptador, documental, exportacao, indicadores
from ..revisao import servico

ESTATICO = Path(__file__).parent / "estatico"
UNIFICADO = Path(__file__).parent / "unificado"
MAX_CORPO = 64 * 1024
SEGURANCA = {
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; frame-src blob:; "
                               "base-uri 'none'; form-action 'none'",
}


COOKIE_SESSAO = "gediv_sessao"
MIN_TOKEN_TECNICO_LEGADO = 16
MIN_TOKEN_TECNICO_PRODUCAO = 32
_ACOES_RESTRITAS_AUDITORIA = frozenset({
    "RECEBER_LOTE_ADMIN",
    "PUBLICAR_SNAPSHOT_PUBLICO",
    "USO_TOKEN_TECNICO_LEGADO",
    "CRIAR_USUARIO",
    "ALTERAR_PAPEL",
    "DESATIVAR_USUARIO",
    "ATIVAR_USUARIO",
})


class Erro(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def _validar_origens_cors(origens_admin) -> frozenset[str]:
    """Valida estritamente a lista de origens CORS autorizadas (somente HTTPS explícito,
    sem curingas '*', sem 'null' e sem localhost/loopback).
    """
    validadas: set[str] = set()
    for bruta in (origens_admin or ()):
        if not bruta:
            continue
        o = str(bruta).strip().rstrip("/")
        if not o:
            continue
        if "*" in o or o.lower() == "null":
            raise ValueError("CORS não permite curinga '*' nem origem 'null'")
        u = urlsplit(o)
        host = (u.hostname or "").lower()
        if (
            u.scheme != "https"
            or not u.netloc
            or u.path
            or u.query
            or u.fragment
            or u.username
            or u.password
            or host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        ):
            raise ValueError(
                "Origem CORS de administração inválida: exija HTTPS explícito sem localhost, null ou curinga"
            )
        validadas.add(o)
    return frozenset(validadas)


def criar_manipulador(pasta_dados: Path, token_gerencia: str | None = None, origens_admin=()):
    caminho_banco, acervo = pasta_dados / "observatorio.sqlite3", Acervo(pasta_dados / "acervo")
    caminho_snapshot_publico = pasta_dados / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
    _cache_snapshot_publico: dict[str, object] = {"mtime_ns": None, "snap": None}
    contas = Contas(pasta_dados / "contas.sqlite3")
    origens = _validar_origens_cors(origens_admin)
    token_legado = (token_gerencia or "").strip()

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PainelGEDIV"
        sys_version = ""

        def log_message(self, *args):          # sem registro de endereços consultados (podem conter buscas por nome)
            pass

        # --- utilidades -------------------------------------------------
        def _token_bearer(self) -> str:
            cabecalho = self.headers.get("Authorization", "")
            return cabecalho[7:].strip() if cabecalho.startswith("Bearer ") else ""

        def _token_cookie(self) -> str:
            bruto = self.headers.get("Cookie", "")
            if not bruto:
                return ""
            try:
                c = SimpleCookie()
                c.load(bruto)
                morsel = c.get(COOKIE_SESSAO)
                return morsel.value.strip() if morsel else ""
            except Exception:
                return ""

        def _token(self) -> str:
            return self._token_bearer() or self._token_cookie()

        def _tem_credencial(self) -> bool:
            return bool("Authorization" in self.headers or self._token_cookie())

        def _usando_cookie_sessao(self) -> bool:
            return bool(not self._token_bearer() and self._token_cookie())

        def _usando_token_tecnico(self) -> bool:
            tok = self._token_bearer()
            return bool(token_legado) and bool(tok) and hmac.compare_digest(
                tok.encode("utf-8"), token_legado.encode("utf-8")
            )

        def _auditar_token_tecnico_se_usado(self, banco: Banco) -> None:
            if self._usando_token_tecnico() and not getattr(self, "_token_tecnico_auditado", False):
                self._token_tecnico_auditado = True
                fp = hashlib.sha256(self._token_bearer().encode("utf-8")).hexdigest()[:12]
                with banco.con:
                    banco.auditar(
                        "gerencia (credencial_tecnica_legada)",
                        "USO_TOKEN_TECNICO_LEGADO",
                        "credencial_tecnica",
                        urlsplit(self.path).path,
                        None,
                        {"metodo": self.command, "token_sha256_prefix": fp},
                        "Acesso autenticado via credencial técnica legada",
                    )

        def _verificar_origem_post(self, exigir_cabecalho: bool) -> None:
            sec_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            host_req = (self.headers.get("Host") or "").strip()
            if exigir_cabecalho and sec_site and sec_site != "same-origin":
                raise Erro(403, "pedido bloqueado por proteção CSRF")
            if "Origin" in self.headers:
                orig_req = (self.headers.get("Origin") or "").strip().rstrip("/")
                if not orig_req or orig_req.lower() == "null" or "*" in orig_req:
                    raise Erro(403, "origem inválida (proteção CSRF)")
                if orig_req not in origens and urlsplit(orig_req).netloc != host_req:
                    raise Erro(403, "origem não autorizada (proteção CSRF)")
                if not exigir_cabecalho and sec_site and sec_site != "same-origin" and orig_req not in origens:
                    raise Erro(403, "pedido bloqueado por proteção CSRF")
                return
            if not exigir_cabecalho:
                if sec_site and sec_site not in ("same-origin", "none"):
                    raise Erro(403, "pedido bloqueado por proteção CSRF")
                return
            if sec_site == "same-origin":
                return
            ref = (self.headers.get("Referer") or "").strip()
            if ref:
                u = urlsplit(ref)
                orig_ref = f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else ""
                if u.scheme in ("http", "https") and (orig_ref in origens or u.netloc == host_req):
                    return
                raise Erro(403, "referência de origem não autorizada (proteção CSRF)")
            raise Erro(403, "origem não verificável (proteção CSRF)")

        def _verificar_csrf_cookie(self) -> None:
            if not self._usando_cookie_sessao():
                return
            self._verificar_origem_post(exigir_cabecalho=True)

        def _cabecalho_cookie_sessao(self, valor: str, max_age: int) -> str:
            secure = (
                (self.headers.get("X-Forwarded-Proto") or "").strip().lower() == "https"
                or os.environ.get("GEDIV_COOKIE_SECURE") == "1"
            )
            partes = [
                f"{COOKIE_SESSAO}={valor}",
                "HttpOnly",
                "SameSite=Strict",
                "Path=/api",
                f"Max-Age={max_age}",
            ]
            if secure:
                partes.append("Secure")
            return "; ".join(partes)

        def _conta(self) -> dict | None:
            """Sessão de conta individual válida, ou None. Calculada uma vez por pedido."""
            if not hasattr(self, "_conta_cache"):
                token = self._token()
                self._conta_cache = contas.sessao(token) if token else None
            return self._conta_cache

        def _perfil(self) -> str:
            if self._usando_token_tecnico():
                return indicadores.GERENCIA_PERFIL
            token = self._token()
            if token and self._conta():
                return indicadores.GERENCIA_PERFIL
            return indicadores.PUBLICO

        def _papel(self) -> str:
            # Credencial técnica legada concede apenas perfil gerencial (NÃO substitui conta nominal admin).
            if self._usando_token_tecnico():
                return "gerencia"
            token = self._token()
            conta = self._conta() if token else None
            if conta:
                return str(conta.get("papel") or "gerencia")
            return "publico"

        def _ator(self) -> str:
            conta = self._conta()
            return f"{conta['nome']} ({conta['usuario']})" if conta else "gerencia (credencial)"

        def _origem_permitida(self) -> str | None:
            bruta = (self.headers.get("Origin") or "").strip()
            if not bruta or bruta.lower() == "null" or "*" in bruta:
                return None
            origem = bruta.rstrip("/")
            return origem if origem and origem in origens else None

        def _exigir_gerencia(self) -> None:
            if not self._tem_credencial():
                raise Erro(401, "credencial necessária")
            if self._usando_cookie_sessao() and not self._conta():
                raise Erro(401, "sessão inexistente ou expirada")
            if self._perfil() != indicadores.GERENCIA_PERFIL:
                raise Erro(403, "credencial inválida ou sem permissão")

        def _exigir_admin(self) -> None:
            if not self._tem_credencial():
                raise Erro(401, "credencial necessária")
            if self._usando_cookie_sessao() and not self._conta():
                raise Erro(401, "sessão inexistente ou expirada")
            if self._papel() != "admin":
                raise Erro(403, "permissão administrativa necessária")

        def _obter_snapshot_publico(self, banco: Banco) -> dict:
            """Devolve o snapshot público congelado e validado (`snapshot_publico.json`).
            Confirmações unitárias em `POST /api/revisao` não alteram este snapshot até nova publicação.
            Com `GEDIV_EXIGIR_SNAPSHOT_PUBLICO=1`, falha de forma fechada (503) se o arquivo estiver ausente."""
            if caminho_snapshot_publico.is_file():
                try:
                    mtime_ns = caminho_snapshot_publico.stat().st_mtime_ns
                    if _cache_snapshot_publico["snap"] is not None and _cache_snapshot_publico["mtime_ns"] == mtime_ns:
                        return _cache_snapshot_publico["snap"]  # type: ignore[return-value]
                    snap = indicadores.carregar_snapshot_publico(caminho_snapshot_publico)
                    if snap is not None:
                        _cache_snapshot_publico["mtime_ns"] = mtime_ns
                        _cache_snapshot_publico["snap"] = snap
                        return snap
                except Exception:
                    if _cache_snapshot_publico["snap"] is not None:
                        return _cache_snapshot_publico["snap"]  # type: ignore[return-value]
                    raise Erro(503, "snapshot público inválido ou indisponível")
            if _cache_snapshot_publico["snap"] is not None:
                return _cache_snapshot_publico["snap"]  # type: ignore[return-value]
            if os.environ.get("GEDIV_EXIGIR_SNAPSHOT_PUBLICO") == "1":
                raise Erro(503, "snapshot público ainda não publicado")
            try:
                snap = indicadores.publicar_snapshot_publico(banco, caminho_snapshot_publico)
                _cache_snapshot_publico["mtime_ns"] = caminho_snapshot_publico.stat().st_mtime_ns
                _cache_snapshot_publico["snap"] = snap
                return snap
            except OSError:
                raise Erro(503, "snapshot público indisponível para gravação")

        def _enviar(self, status: int, corpo: bytes, tipo: str, extras: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            cors = {}
            origem = self._origem_permitida()
            if origem and urlsplit(self.path).path.startswith("/api/"):
                cors = {"Access-Control-Allow-Origin": origem, "Vary": "Origin",
                        "Access-Control-Expose-Headers": "Content-Disposition"}
            for nome, valor in {**SEGURANCA, **cors, **(extras or {})}.items():
                self.send_header(nome, valor)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _json(self, dados, status: int = 200, extras: dict | None = None) -> None:
            self._enviar(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                         {"Cache-Control": "no-store", **(extras or {})})

        def _atender(self, acao) -> None:
            self.__dict__.pop("_conta_cache", None)          # a sessão é verificada de novo a cada pedido
            self.__dict__.pop("_token_tecnico_auditado", None)
            banco = None
            try:
                banco = Banco(caminho_banco)
                if self._usando_token_tecnico() and urlsplit(self.path).path.startswith("/api/"):
                    self._auditar_token_tecnico_se_usado(banco)
                acao(banco)
            except Erro as e:
                self._json({"erro": e.mensagem}, e.status)
            except servico.Recusada as e:
                self._json({"erro": str(e)}, 422)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # nunca devolver rastros internos
                self._json({"erro": "falha interna", "tipo": type(e).__name__}, 500)
            finally:
                if banco is not None:
                    banco.fechar()

        # --- rotas ------------------------------------------------------
        def do_GET(self):
            self._atender(self._get)

        do_HEAD = do_GET

        def do_POST(self):
            self._atender(self._post)

        def do_OPTIONS(self):
            # Pré-verificação CORS: só para a API e só para origens autorizadas do painel de administração.
            origem = self._origem_permitida()
            if not origem or not urlsplit(self.path).path.startswith("/api/"):
                return self._enviar(403, b"", "text/plain; charset=utf-8")
            self._enviar(204, b"", "text/plain; charset=utf-8", {
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "600"})

        def _get(self, banco: Banco) -> None:
            url = urlsplit(self.path)
            rota = url.path
            consulta = {k: (v[0] if len(v) == 1 else v) for k, v in parse_qs(url.query).items()}
            perfil = self._perfil()
            if rota in ("/", "/index.html", "/painel", "/painel/", "/painel/index.html"):
                return self._arquivo("index.html", UNIFICADO)
            if rota.startswith("/painel/"):
                return self._arquivo(rota[len("/painel/"):], UNIFICADO)
            if rota in ("/estatico", "/estatico/"):
                return self._arquivo("index.html", ESTATICO)
            if rota.startswith("/estatico/"):
                return self._arquivo(rota[len("/estatico/"):], ESTATICO)
            if rota == "/api/saude":
                return self._json({"sistema": NOME, "versao": __version__, "regras": catalogo.VERSAO_REGRAS, "perfil": perfil,
                                   "papel": self._papel(), "cobertura": indicadores.cobertura(banco)})
            if rota == "/api/sessao":
                conta = self._conta()
                if not conta:
                    raise Erro(401, "sessão inexistente ou expirada")
                return self._json(conta)
            if rota == "/api/catalogo":
                return self._json(catalogo.como_dicionario())
            if rota == "/api/painel":
                if perfil != indicadores.GERENCIA_PERFIL:
                    return self._json(self._obter_snapshot_publico(banco)["painel"])
                return self._json(indicadores.painel(banco, consulta, perfil, proteger_publico=False))
            if rota == "/api/data":
                if perfil != indicadores.GERENCIA_PERFIL:
                    return self._json(self._obter_snapshot_publico(banco)["data"])
                escopo_padrao = "pendente"
                p_resp = indicadores.painel(
                    banco,
                    {**consulta, "escopo": consulta.get("escopo") or escopo_padrao},
                    perfil,
                    proteger_publico=False,
                )
                # Carrega ambos os escopos (pendente e conferido) e rejeitados para o perfil autenticado
                p_pend = p_resp if p_resp["meta"]["escopo"] == "pendente" else indicadores.painel(banco, {"escopo": "pendente"}, perfil)
                p_conf = p_resp if p_resp["meta"]["escopo"] == "conferido" else indicadores.painel(banco, {"escopo": "conferido"}, perfil)
                todas_linhas = list(p_pend.get("linhas") or []) + list(p_conf.get("linhas") or [])
                p_combinado = {**p_resp, "linhas": todas_linhas}
                outras_resp = indicadores.outras_publicacoes(banco, perfil)
                rej_consulta = banco.con.execute(
                    "SELECT d.id, d.ato_id, d.sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, d.cargo, d.detalhe, "
                    "d.resultado, d.trecho, d.validacao, d.revisor, d.revisado_em, d.justificativa, a.numero AS resenha, a.sufixo, a.tipo, "
                    "a.data_publicacao AS data, a.data_expediente, a.vinculo, a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, "
                    "a.grupo_expressao, a.subcategoria, a.pendencias, a.chave_logica, "
                    "a.gerencia AS gerencia_painel, SUBSTR(a.texto,1,1200) AS texto_identificacao, l.numero_edicao, l.data_edicao, "
                    "0 AS conflito_aberto "
                    "FROM decisao d JOIN ato a ON a.id = d.ato_id JOIN leitura l ON l.sha256 = d.sha256 "
                    "WHERE a.gerencia = 'GEDIV' AND d.validacao = 'REJEITADO'"
                ).fetchall()
                rej_linhas = []
                for r in rej_consulta:
                    lr = dict(r)
                    lr.update(documental.identificar(lr))
                    lr.pop("texto_identificacao", None)
                    lr["detalhe"] = json.loads(lr["detalhe"] or "{}")
                    lr["pendencias"] = json.loads(lr["pendencias"] or "[]")
                    url_of = banco.url_oficial(lr["sha256"])
                    lr["url_oficial"] = f"{url_of}#page={lr['pagina']}" if url_of else None
                    lr["pdf_no_acervo"] = f"/api/pdf/{lr['sha256']}#page={lr['pagina']}"
                    rej_linhas.append(lr)
                resp = adaptador.projetar_para_dashboard_2910(p_combinado, outras_resp, rej_linhas)
                conta = self._conta()
                resp["backend"]["papel"] = self._papel()
                resp["backend"]["ehAdmin"] = self._papel() == "admin"
                resp["backend"]["usuario"] = conta["usuario"] if conta else None
                resp["backend"]["nome"] = conta["nome"] if conta else None
                return self._json(resp)
            if rota == "/api/outras":
                self._exigir_gerencia()
                return self._json({"itens": indicadores.outras_publicacoes(banco, perfil)})
            if rota == "/api/exportar":
                self._exigir_gerencia()
                projecao = indicadores.painel(banco, consulta, perfil)
                nome = f"painel-gediv-{projecao['meta']['escopo']}-{date.today().isoformat()}"
                with banco.con:
                    banco.auditar(self._ator(), "EXPORTAR", "painel", consulta.get("formato", "xlsx"), None,
                                  {"filtros": projecao["meta"]["filtros"], "linhas": len(projecao["linhas"])}, None)
                if consulta.get("formato") == "csv":
                    return self._enviar(200, exportacao.csv(exportacao.linhas_decisoes(projecao)), "text/csv; charset=utf-8",
                                        {"Content-Disposition": f'attachment; filename="{nome}.csv"', "Cache-Control": "no-store"})
                return self._enviar(200, exportacao.planilha(projecao),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    {"Content-Disposition": f'attachment; filename="{nome}.xlsx"', "Cache-Control": "no-store"})
            achado = re.fullmatch(r"/api/ato/([0-9a-f]{20})", rota)
            if achado:
                self._exigir_gerencia()
                ato = banco.con.execute("SELECT * FROM ato WHERE id = ?", (achado.group(1),)).fetchone()
                if ato is None:
                    raise Erro(404, "ato não encontrado")
                decisoes = [dict(d) for d in banco.con.execute("SELECT * FROM decisao WHERE ato_id = ? ORDER BY rowid", (ato["id"],))]
                trilha = [dict(t) for d in decisoes for t in banco.trilha("decisao", d["id"], 20)]
                url_oficial = banco.url_oficial(ato["sha256"])
                ids_decisoes = [d["id"] for d in decisoes]
                conflitos = [dict(c) for c in banco.conflitos("ABERTO", "ato", [ato["id"]])] + \
                            [dict(c) for c in banco.conflitos("ABERTO", "decisao", ids_decisoes)]
                correcoes = [dict(c) for c in banco.correcoes("ato", ato["id"])] + \
                            [dict(c) for i in ids_decisoes for c in banco.correcoes("decisao", i)]
                return self._json({"conflitos": conflitos, "correcoes": correcoes,
                                   "ato": {**dict(ato), "pendencias": json.loads(ato["pendencias"] or "[]"),
                                           "url_oficial": f"{url_oficial}#page={ato['pagina']}" if url_oficial else None,
                                           "pdf_no_acervo": f"/api/pdf/{ato['sha256']}#page={ato['pagina']}"},
                                   "decisoes": decisoes, "trilha": sorted(trilha, key=lambda t: t["id"], reverse=True)})
            achado = re.fullmatch(r"/api/pdf/([0-9a-f]{64})", rota)
            if achado:
                self._exigir_gerencia()
                if banco.arquivo(achado.group(1)) is None or not acervo.conferir(achado.group(1)):
                    raise Erro(404, "arquivo ausente do acervo")
                return self._enviar(200, acervo.caminho(achado.group(1)).read_bytes(), "application/pdf",
                                    {"Cache-Control": "no-store", "Content-Disposition": "inline"})
            if rota == "/api/conflitos":
                self._exigir_gerencia()
                return self._json({"conflitos": [dict(c) for c in banco.conflitos("ABERTO")],
                                   "vinculos_orfaos": banco.vinculos_orfaos(),
                                   "classificacoes_desatualizadas": banco.classificacoes_desatualizadas("GEDIV", catalogo.VERSAO_REGRAS)})
            if rota == "/api/auditoria":
                self._exigir_gerencia()
                if self._usando_token_tecnico():
                    raise Erro(403, "consulta de auditoria exige conta nominal")
                if self._papel() == "admin":
                    return self._json({"escopo": "global", "trilha": [dict(t) for t in banco.trilha(limite=300)]})
                ator = self._ator()
                return self._json({
                    "escopo": "proprio",
                    "trilha": [
                        dict(t)
                        for t in banco.trilha(limite=300)
                        if t["autor"] == ator and t["acao"] not in _ACOES_RESTRITAS_AUDITORIA
                    ],
                })
            if rota == "/api/admin/usuarios":
                self._exigir_admin()
                return self._json({"usuarios": contas.listar()})
            raise Erro(404, "rota inexistente")

        def _corpo_json(self) -> dict:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise Erro(415, "envie JSON")
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise Erro(400, "tamanho inválido")
            if not 0 < tamanho <= MAX_CORPO:
                raise Erro(413, "corpo ausente ou grande demais")
            try:
                p = json.loads(self.rfile.read(tamanho))
                assert isinstance(p, dict)
            except Exception:
                raise Erro(400, "JSON inválido")
            return p

        def _post(self, banco: Banco) -> None:
            rota = urlsplit(self.path).path
            if rota == "/api/login":
                self._verificar_origem_post(exigir_cabecalho=False)
                p = self._corpo_json()
                try:
                    sessao = contas.entrar(str(p.get("usuario", ""))[:80], str(p.get("senha", ""))[:200])
                except AcessoNegado:
                    raise Erro(401, "usuário ou senha inválidos, ou acesso bloqueado temporariamente")
                with banco.con:
                    banco.auditar(f"{sessao['nome']} ({sessao['usuario']})", "ENTRAR", "sessao", sessao["usuario"], None, None, None)
                somente_cookie = bool(p.get("modo_cookie") is True) or (
                    os.environ.get("GEDIV_LOGIN_SOMENTE_COOKIE") == "1"
                    and self._origem_permitida() is None
                )
                resposta_login = (
                    {k: v for k, v in sessao.items() if k != "token"} | {"autenticacao": "cookie_httponly"}
                    if somente_cookie
                    else sessao
                )
                return self._json(
                    resposta_login,
                    extras={"Set-Cookie": self._cabecalho_cookie_sessao(sessao["token"], 28800)},
                )
            self._verificar_csrf_cookie()
            if rota == "/api/logout":
                if self._conta():
                    with banco.con:
                        banco.auditar(self._ator(), "SAIR", "sessao", self._conta()["usuario"], None, None, None)
                    contas.sair(self._token())
                return self._json({"encerrada": True}, extras={"Set-Cookie": self._cabecalho_cookie_sessao("", 0)})
            if rota == "/api/admin/lote":
                self._exigir_admin()
                p = self._corpo_json()
                itens = p.get("rows") if "rows" in p else (p.get("edicoes") if "edicoes" in p else p.get("lote"))
                if not isinstance(itens, list) or not itens or not all(isinstance(x, dict) for x in itens):
                    raise Erro(400, "lote inválido: informe lista não vazia em 'rows', 'edicoes' ou 'lote'")
                ids = [str(x.get("id") or "").strip() for x in itens if str(x.get("id") or "").strip()]
                dup = 0
                if ids:
                    existentes = {r[0] for r in banco.con.execute("SELECT id FROM decisao")}
                    dup = sum(1 for i in ids if i in existentes)
                origem = str(p.get("origem") or "manual")[:80]
                obs = str(p.get("observacao") or "Validação preliminar de lote administrativo (sem importação no banco)")[:200]
                with banco.con:
                    banco.auditar(self._ator(), "RECEBER_LOTE_ADMIN", "lote", origem, None,
                                  {"modo": "SOMENTE_VALIDACAO", "importado": False,
                                   "recebidos": len(itens), "ja_existentes": dup, "novos": len(itens) - dup}, obs)
                return self._json({"ok": True, "status": "VALIDADO", "importado": False,
                                   "modo": "SOMENTE_VALIDACAO", "recebidos": len(itens),
                                   "ja_existentes": dup, "novos": len(itens) - dup,
                                   "mensagem": "Registros validados preliminarmente e tentativa registrada em auditoria; nenhum registro foi importado ou incorporado ao banco principal (PENDENCIA_OPERACIONAL)."})
            if rota == "/api/admin/snapshot-publico":
                self._exigir_admin()
                snap = indicadores.publicar_snapshot_publico(banco, caminho_snapshot_publico)
                _cache_snapshot_publico["mtime_ns"] = caminho_snapshot_publico.stat().st_mtime_ns
                _cache_snapshot_publico["snap"] = snap
                with banco.con:
                    banco.auditar(
                        self._ator(),
                        "PUBLICAR_SNAPSHOT_PUBLICO",
                        "painel",
                        indicadores.ARQUIVO_SNAPSHOT_PUBLICO,
                        None,
                        {
                            "gerado_em": snap["gerado_em"],
                            "decisoes_faixa": snap["painel"]["indicadores"]["decisoes"],
                            "revision": snap["data"]["dashboard"]["revision"],
                        },
                        "Publicação controlada de snapshot público",
                    )
                return self._json({
                    "ok": True,
                    "gerado_em": snap["gerado_em"],
                    "indicadores": snap["painel"]["indicadores"],
                    "revision": snap["data"]["dashboard"]["revision"],
                })
            if rota != "/api/revisao":
                raise Erro(404, "rota inexistente")
            self._exigir_gerencia()
            p = self._corpo_json()
            # Com conta individual, o responsável é SEMPRE a pessoa logada (o nome enviado pelo navegador é ignorado).
            informado = str(p.get("responsavel", "")).strip()[:80]
            responsavel = self._ator() if self._conta() else (
                f"credencial_tecnica_legada: {informado}" if informado else ""
            )
            comuns = (str(p.get("decisao", "")), responsavel, str(p.get("justificativa", "")))
            alvo = p.get("alvo")
            if alvo == "ato":
                r = servico.revisar_ato(banco, str(p.get("id", "")), *comuns, bool(p.get("confirma_fonte")), bool(p.get("confirma_vinculo")))
            elif alvo == "decisao":
                ids = p.get("ids") if isinstance(p.get("ids"), list) else [p.get("id")]
                r = servico.revisar_decisoes(banco, [str(i) for i in ids if i], *comuns, bool(p.get("confirma_fonte")),
                                             bool(p.get("confirma_vinculo")), p.get("correcoes") if isinstance(p.get("correcoes"), dict) else None)
            elif alvo == "evento":
                r = servico.revisar_evento(banco, str(p.get("id", "")), *comuns, p.get("ato_original_id") or None, bool(p.get("confirma_fonte")))
            elif alvo == "ato_classificacao":
                r = servico.corrigir_ato(banco, str(p.get("id", "")), p.get("correcoes") if isinstance(p.get("correcoes"), dict) else {},
                                         comuns[1], comuns[2], bool(p.get("confirma_fonte")))
            elif alvo == "decisao_omitida":
                try:
                    pagina = int(p.get("pagina"))
                except (TypeError, ValueError):
                    raise Erro(400, "página inválida")
                r = servico.registrar_decisao_omitida(banco, str(p.get("id", "")), pagina, str(p.get("trecho", "")),
                                                      p.get("correcoes") if isinstance(p.get("correcoes"), dict) else {},
                                                      comuns[1], comuns[2], bool(p.get("confirma_fonte")))
            elif alvo == "conflito":
                try:
                    conflito = int(p.get("id"))
                except (TypeError, ValueError):
                    raise Erro(400, "conflito inválido")
                r = servico.resolver_conflito(banco, conflito, *comuns, bool(p.get("confirma_fonte")))
            else:
                raise Erro(400, "alvo inválido")
            self._json(r)

        def _arquivo(self, nome: str, base_dir: Path = ESTATICO) -> None:
            caminho = (base_dir / nome).resolve()
            if base_dir.resolve() not in caminho.parents or not caminho.is_file():
                raise Erro(404, "arquivo inexistente")
            tipo = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript", "text/javascript"):
                tipo += "; charset=utf-8"
            extras = {"Cache-Control": "no-cache"}
            if base_dir == UNIFICADO:
                extras["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob:; object-src 'none'; frame-src blob:; base-uri 'none'; form-action 'self'"
                )
            self._enviar(200, caminho.read_bytes(), tipo, extras)

    return Manipulador


def criar_servidor(pasta_dados: str | Path, token_gerencia: str | None = None, endereco: str = "127.0.0.1", porta: int = 8000,
                   origens_admin=(), *, exigir_token_32: bool = False) -> ThreadingHTTPServer:
    if token_gerencia is not None and token_gerencia != "":
        min_len = (
            MIN_TOKEN_TECNICO_PRODUCAO
            if (exigir_token_32 or os.environ.get("GEDIV_MODO_PRODUCAO") == "1")
            else MIN_TOKEN_TECNICO_LEGADO
        )
        if len(token_gerencia) < min_len:
            raise ValueError(f"a credencial da gerência precisa de pelo menos {min_len} caracteres")
    Banco(Path(pasta_dados) / "observatorio.sqlite3").fechar()        # cria ou atualiza o esquema antes de atender
    servidor = ThreadingHTTPServer((endereco, porta), criar_manipulador(Path(pasta_dados), token_gerencia or "", origens_admin))
    servidor.daemon_threads = True
    return servidor
