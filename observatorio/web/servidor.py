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

import hmac
import json
import mimetypes
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import NOME, __version__
from .contas import AcessoNegado, Contas
from ..gerencias.gediv import catalogo
from ..nucleo.acervo import Acervo
from ..nucleo.banco import Banco
from ..painel import exportacao, indicadores
from ..revisao import servico

ESTATICO = Path(__file__).parent / "estatico"
MAX_CORPO = 64 * 1024
SEGURANCA = {
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; frame-src blob:; "
                               "base-uri 'none'; form-action 'none'",
}


class Erro(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def criar_manipulador(pasta_dados: Path, token_gerencia: str, origens_admin=()):
    caminho_banco, acervo = pasta_dados / "observatorio.sqlite3", Acervo(pasta_dados / "acervo")
    contas = Contas(pasta_dados / "contas.sqlite3")
    origens = frozenset(o.rstrip("/") for o in origens_admin if o)

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PainelGEDIV"
        sys_version = ""

        def log_message(self, *args):          # sem registro de endereços consultados (podem conter buscas por nome)
            pass

        # --- utilidades -------------------------------------------------
        def _token(self) -> str:
            cabecalho = self.headers.get("Authorization", "")
            return cabecalho[7:].strip() if cabecalho.startswith("Bearer ") else ""

        def _conta(self) -> dict | None:
            """Sessão de conta individual válida, ou None. Calculada uma vez por pedido."""
            if not hasattr(self, "_conta_cache"):
                token = self._token()
                self._conta_cache = contas.sessao(token) if token else None
            return self._conta_cache

        def _perfil(self) -> str:
            token = self._token()
            if token and hmac.compare_digest(token.encode(), token_gerencia.encode()):
                return indicadores.GERENCIA_PERFIL
            if token and self._conta():
                return indicadores.GERENCIA_PERFIL
            return indicadores.PUBLICO

        def _ator(self) -> str:
            conta = self._conta()
            return f"{conta['nome']} ({conta['usuario']})" if conta else "gerencia (credencial)"

        def _origem_permitida(self) -> str | None:
            origem = (self.headers.get("Origin") or "").rstrip("/")
            return origem if origem and origem in origens else None

        def _exigir_gerencia(self) -> None:
            if "Authorization" not in self.headers:
                raise Erro(401, "credencial necessária")
            if self._perfil() != indicadores.GERENCIA_PERFIL:
                raise Erro(403, "credencial inválida ou sem permissão")

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

        def _json(self, dados, status: int = 200) -> None:
            self._enviar(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                         {"Cache-Control": "no-store"})

        def _atender(self, acao) -> None:
            self.__dict__.pop("_conta_cache", None)          # a sessão é verificada de novo a cada pedido
            banco = None
            try:
                banco = Banco(caminho_banco)
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
            if rota in ("/", "/index.html"):
                return self._arquivo("index.html")
            if rota.startswith("/estatico/"):
                return self._arquivo(rota[len("/estatico/"):])
            if rota == "/api/saude":
                return self._json({"sistema": NOME, "versao": __version__, "regras": catalogo.VERSAO_REGRAS, "perfil": perfil,
                                   "cobertura": indicadores.cobertura(banco)})
            if rota == "/api/sessao":
                conta = self._conta()
                if not conta:
                    raise Erro(401, "sessão inexistente ou expirada")
                return self._json(conta)
            if rota == "/api/catalogo":
                return self._json(catalogo.como_dicionario())
            if rota == "/api/painel":
                return self._json(indicadores.painel(banco, consulta, perfil))
            if rota == "/api/outras":
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
                return self._json({"trilha": [dict(t) for t in banco.trilha(limite=300)]})
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
                p = self._corpo_json()
                try:
                    sessao = contas.entrar(str(p.get("usuario", ""))[:80], str(p.get("senha", ""))[:200])
                except AcessoNegado:
                    raise Erro(401, "usuário ou senha inválidos, ou acesso bloqueado temporariamente")
                with banco.con:
                    banco.auditar(f"{sessao['nome']} ({sessao['usuario']})", "ENTRAR", "sessao", sessao["usuario"], None, None, None)
                return self._json(sessao)
            if rota == "/api/logout":
                if self._conta():
                    with banco.con:
                        banco.auditar(self._ator(), "SAIR", "sessao", self._conta()["usuario"], None, None, None)
                    contas.sair(self._token())
                return self._json({"encerrada": True})
            if rota != "/api/revisao":
                raise Erro(404, "rota inexistente")
            self._exigir_gerencia()
            p = self._corpo_json()
            # Com conta individual, o responsável é SEMPRE a pessoa logada (o nome enviado pelo navegador é ignorado).
            responsavel = self._ator() if self._conta() else str(p.get("responsavel", ""))
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

        def _arquivo(self, nome: str) -> None:
            caminho = (ESTATICO / nome).resolve()
            if ESTATICO.resolve() not in caminho.parents or not caminho.is_file():
                raise Erro(404, "arquivo inexistente")
            tipo = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript", "text/javascript"):
                tipo += "; charset=utf-8"
            self._enviar(200, caminho.read_bytes(), tipo, {"Cache-Control": "no-cache"})

    return Manipulador


def criar_servidor(pasta_dados: str | Path, token_gerencia: str, endereco: str = "127.0.0.1", porta: int = 8000,
                   origens_admin=()) -> ThreadingHTTPServer:
    if len(token_gerencia) < 16:
        raise ValueError("a credencial da gerência precisa de pelo menos 16 caracteres")
    Banco(Path(pasta_dados) / "observatorio.sqlite3").fechar()        # cria ou atualiza o esquema antes de atender
    servidor = ThreadingHTTPServer((endereco, porta), criar_manipulador(Path(pasta_dados), token_gerencia, origens_admin))
    servidor.daemon_threads = True
    return servidor
