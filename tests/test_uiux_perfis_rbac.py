"""Testes automatizados de RBAC (Público / Gerência GEDIV / Administração) e revisão UI/UX."""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador
from observatorio.web.contas import Contas
from observatorio.web.servidor import criar_servidor

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
_ENV_ORIGEM = os.environ.get("GEDIV_ORIGEM_HTML")
REF_HTML = pathlib.Path(_ENV_ORIGEM) if _ENV_ORIGEM else None
UNIFICADO_HTML = REPO_DIR / "observatorio" / "web" / "unificado" / "index.html"
PALETA_JSON = REPO_DIR / "observatorio" / "web" / "unificado" / "paleta-aprovada.json"


def _bootstrap_sintetico() -> dict:
    """Fixture sintética mínima sem dados pessoais para execução portátil no CI."""
    return {
        "rows": [
            {
                "id": "dec-rbac-001",
                "resenha": "Resenha 901/2026",
                "date": "2026-10-15",
                "page": 1,
                "url": "snapshot:rbac-1",
                "process": "PROC-TESTE-2026/001",
                "server": "SERVIDOR FICTICIO ALPHA",
                "registration": "900001",
                "axis": "progressao",
                "modality": "Vertical",
                "group": "TEC-ADM",
                "groupExpression": "TEC. ADM",
                "merit": "deferido",
                "validation": "pendente",
                "levelFrom": "D",
                "levelTo": "E",
                "preliminaryReview": "Conferência sintética inicial",
                "evidence": "Progressão Vertical D para E deferida.",
            },
            {
                "id": "dec-rbac-002",
                "resenha": "Resenha 902/2026",
                "date": "2026-10-16",
                "page": 2,
                "url": "snapshot:rbac-2",
                "process": "PROC-TESTE-2026/002",
                "server": "SERVIDOR FICTICIO BETA",
                "registration": "900002",
                "axis": "tempo",
                "modality": "",
                "category": "TS-01",
                "merit": "indeferido",
                "validation": "pendente",
                "evidence": "Anotação de Tempo de Serviço TS-01 indeferida.",
            },
            {
                "id": "dec-rbac-003",
                "resenha": "Resenha 903/2026",
                "date": "2026-10-17",
                "page": 3,
                "url": "snapshot:rbac-3",
                "process": "PROC-TESTE-2026/003",
                "server": "SERVIDOR FICTICIO GAMA",
                "registration": "900003",
                "axis": "progressao",
                "modality": "Horizontal",
                "group": "SAUDE",
                "groupExpression": "SAUDE",
                "merit": "deferido",
                "validation": "rejeitado",
                "evidence": "Registro rejeitado de teste.",
            },
        ],
        "events": [],
    }


def _req(url: str, token: str | None = None, payload: dict | None = None, method: str | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class TestUiUxPerfisRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if REF_HTML and REF_HTML.is_file():
            cls.bootstrap = adaptador.extrair_bootstrap_de_html(REF_HTML)
        else:
            cls.bootstrap = _bootstrap_sintetico()

    def test_01_contas_papeis_e_migracao_retrocompativel(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = pathlib.Path(tmp) / "contas_legado.sqlite3"
            # Simula esquema antigo sem a coluna `papel`
            with contextlib.closing(sqlite3.connect(db)) as con:
                con.executescript(
                    """
                    CREATE TABLE usuario (
                        usuario TEXT PRIMARY KEY, nome TEXT NOT NULL, sal BLOB NOT NULL,
                        senha_hash BLOB NOT NULL, ativo INTEGER NOT NULL DEFAULT 1,
                        falhas INTEGER NOT NULL DEFAULT 0, bloqueado_ate TEXT,
                        criado_em TEXT NOT NULL, ultimo_acesso TEXT
                    );
                    CREATE TABLE sessao (
                        token_hash TEXT PRIMARY KEY, usuario TEXT NOT NULL REFERENCES usuario(usuario),
                        criada_em TEXT NOT NULL, expira_em TEXT NOT NULL
                    );
                    """
                )
                con.commit()

            contas = Contas(db)
            contas.criar("ana.gerente", "Ana Gerente", "SenhaForte#2026")
            contas.criar("carlos.admin", "Carlos Admin", "AdminForte#2026", papel="admin")

            with self.assertRaises(ValueError):
                contas.criar("ruivo", "Ruivo Teste", "SenhaForte#2026", papel="super")

            s_ger = contas.entrar("ana.gerente", "SenhaForte#2026")
            s_adm = contas.entrar("carlos.admin", "AdminForte#2026")
            self.assertEqual(s_ger["papel"], "gerencia")
            self.assertEqual(s_adm["papel"], "admin")
            self.assertEqual(contas.sessao(s_ger["token"])["papel"], "gerencia")
            self.assertEqual(contas.sessao(s_adm["token"])["papel"], "admin")

            # Troca de papel encerra sessões existentes do usuário
            contas.definir_papel("ana.gerente", "admin")
            self.assertIsNone(contas.sessao(s_ger["token"]))
            self.assertEqual(contas.entrar("ana.gerente", "SenhaForte#2026")["papel"], "admin")

    def test_02_permissoes_3_perfis_no_servidor(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            pasta = pathlib.Path(tmp)
            with Banco(pasta / "observatorio.sqlite3") as banco:
                adaptador.importar_snapshot_reconciliado(banco, self.bootstrap)

            contas = Contas(pasta / "contas.sqlite3")
            contas.criar("ger.gediv", "Analista Gerencia", "SenhaGer#2026", papel="gerencia")
            contas.criar("adm.gediv", "Gestor Admin", "SenhaAdm#2026", papel="admin")

            srv = criar_servidor(pasta, "token-admin-tecnico-2026", "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                # 1. Perfil Público
                st, pub = _req(f"{base}/api/data")
                self.assertEqual(st, 200)
                self.assertEqual(pub["rows"], [])
                self.assertFalse(pub["backend"]["autenticado"])
                self.assertEqual(pub["backend"]["papel"], "publico")
                self.assertFalse(pub["backend"]["ehAdmin"])
                self.assertEqual(_req(f"{base}/api/admin/usuarios")[0], 401)
                self.assertEqual(_req(f"{base}/api/admin/lote", payload={"rows": [{"id": "x"}]})[0], 401)
                self.assertEqual(_req(f"{base}/api/revisao", payload={"alvo": "decisao"})[0], 401)

                # 2. Perfil Gerência (NÃO possui privilégios de administração)
                st_l, s_ger = _req(f"{base}/api/login", payload={"usuario": "ger.gediv", "senha": "SenhaGer#2026"})
                self.assertEqual((st_l, s_ger["papel"]), (200, "gerencia"))
                tok_ger = s_ger["token"]
                st_d, d_ger = _req(f"{base}/api/data", token=tok_ger)
                self.assertEqual(st_d, 200)
                self.assertTrue(d_ger["backend"]["autenticado"])
                self.assertEqual(d_ger["backend"]["papel"], "gerencia")
                self.assertFalse(d_ger["backend"]["ehAdmin"])
                self.assertEqual(len(d_ger["rows"]), len(self.bootstrap["rows"]))
                self.assertEqual(_req(f"{base}/api/auditoria", token=tok_ger)[0], 200)
                self.assertEqual(_req(f"{base}/api/admin/usuarios", token=tok_ger)[0], 403)
                self.assertEqual(_req(f"{base}/api/admin/lote", token=tok_ger, payload={"rows": [{"id": "x"}]})[0], 403)

                # 3. Perfil Administração
                st_a, s_adm = _req(f"{base}/api/login", payload={"usuario": "adm.gediv", "senha": "SenhaAdm#2026"})
                self.assertEqual((st_a, s_adm["papel"]), (200, "admin"))
                tok_adm = s_adm["token"]
                st_da, d_adm = _req(f"{base}/api/data", token=tok_adm)
                self.assertEqual(st_da, 200)
                self.assertEqual(d_adm["backend"]["papel"], "admin")
                self.assertTrue(d_adm["backend"]["ehAdmin"])
                st_u, u_resp = _req(f"{base}/api/admin/usuarios", token=tok_adm)
                self.assertEqual(st_u, 200)
                self.assertEqual({u["usuario"]: u["papel"] for u in u_resp["usuarios"]},
                                 {"adm.gediv": "admin", "ger.gediv": "gerencia"})

                # Validação de payload no lote admin + prevenção de duplicidade + auditoria (SOMENTE VALIDAÇÃO, sem alterar banco)
                self.assertEqual(_req(f"{base}/api/admin/lote", token=tok_adm, payload={"rows": []})[0], 400)
                total_antes = len(d_adm["rows"])
                amostra_id = d_adm["rows"][0]["id"]
                st_ok, l_resp = _req(
                    f"{base}/api/admin/lote",
                    token=tok_adm,
                    payload={"origem": "teste-admin", "rows": [{"id": amostra_id}, {"id": "novo-reg-999"}]},
                )
                self.assertEqual(st_ok, 200)
                self.assertEqual(l_resp["status"], "VALIDADO")
                self.assertFalse(l_resp["importado"])
                self.assertEqual(l_resp["modo"], "SOMENTE_VALIDACAO")
                self.assertEqual(l_resp["recebidos"], 2)
                self.assertEqual(l_resp["ja_existentes"], 1)
                self.assertEqual(l_resp["novos"], 1)
                self.assertIn("nenhum registro foi importado", l_resp["mensagem"].lower())

                # Comprovar que a rota NÃO alterou nem importou o registro novo no banco principal
                _, d_apos = _req(f"{base}/api/data", token=tok_adm)
                self.assertEqual(len(d_apos["rows"]), total_antes)
                self.assertNotIn("novo-reg-999", {r["id"] for r in d_apos["rows"]})

                st_aud, aud = _req(f"{base}/api/auditoria", token=tok_adm)
                self.assertEqual(st_aud, 200)
                self.assertIn(
                    ("RECEBER_LOTE_ADMIN", "Gestor Admin (adm.gediv)", "teste-admin"),
                    [(t["acao"], t["autor"], t["alvo_id"]) for t in aud["trilha"]],
                )
            finally:
                srv.shutdown()
                srv.server_close()

    def test_03_html_unificado_delicadeza_paleta_privacidade_e_abono(self) -> None:
        html = UNIFICADO_HTML.read_text(encoding="utf-8")
        hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
        cores_orig = {c.lower() for c in json.loads(PALETA_JSON.read_text(encoding="utf-8"))["cores_hex"]}
        cores_unif = {c.lower() for c in hex_re.findall(html)}
        self.assertEqual(cores_unif - cores_orig, set())
        self.assertIn('window.GEDIV_BOOTSTRAP={"rows":[],"events":[', html)
        self.assertNotRegex(html, r"SAD-PSE-202\d/\d+")
        self.assertNotRegex(html, r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
        self.assertNotRegex(html, r'"server"\s*:\s*"[A-ZÀ-Ú]{3,}')
        self.assertIn("Exportar visualização", html)
        self.assertIn("delicateAcctBtn", html)
        self.assertIn("Empilhadas (Mês)", html)
        self.assertIn("Validar lote (sem importar)", html)
        self.assertIn("NÃO são incorporados ao banco principal", html)
        self.assertNotIn("Receber e atualizar", html)
        self.assertNotIn("TS-08", html)

    def test_04_reprodutibilidade_frontend_em_ambiente_limpo_e_ausencia_de_pii(self) -> None:
        """Passo 2.2: reconstrói o painel unificado a partir do modelo base sanitizado versionado,
        sem qualquer arquivo externo ou variável GEDIV_ORIGEM_HTML, validando ausência de dados
        pessoais/caminhos/segredos e igualdade byte a byte com o artefato versionado.
        """
        from scripts import construir_painel_unificado as builder

        modelo_path = builder.MODELO_BASE_PADRAO
        self.assertTrue(modelo_path.is_file(), "modelo-base-sanitizado.html ausente do repositório.")

        padroes_proibidos = [
            ("processo administrativo real", r"SAD-PSE-202\d/\d+"),
            ("CPF", r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
            ("e-mail pessoal", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
            ("token ou chave privada", r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|BEGIN [A-Z ]*PRIVATE KEY)"),
            ("senha de homologação", r"Gediv(?:Homolog|Admin)\d{4}[!]"),
            ("URL privada chatgpt.site", r"[A-Za-z0-9.-]*\.chatgpt\.site"),
            ("caminho local Windows", r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+"),
            ("caminho pessoal Linux", r"/home/(?!\[)[A-Za-z0-9._-]+"),
            ("nome serializado em JS", r'"server"\s*:\s*"[A-ZÀ-Ú]{3,}'),
            ("matrícula serializada em JS", r'"registration"\s*:\s*"\d+'),
            ("processo serializado em JS", r'"process"\s*:\s*"SAD-'),
        ]

        for rotulo_arq, caminho_arq in (("modelo-base-sanitizado.html", modelo_path), ("unificado/index.html", UNIFICADO_HTML)):
            conteudo = caminho_arq.read_text(encoding="utf-8")
            self.assertIn('window.GEDIV_BOOTSTRAP={"rows":[],"events":[', conteudo, f"Bootstrap não vazio em {rotulo_arq}")
            for nome_regra, regex in padroes_proibidos:
                self.assertNotRegex(conteudo, re.compile(regex, re.I), f"Violação ({nome_regra}) em {rotulo_arq}")

        # Reconstruir em diretório temporário isolado sem GEDIV_ORIGEM_HTML
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saida_limpa = pathlib.Path(tmp) / "index_reconstruido.html"
            env_antigo = os.environ.pop("GEDIV_ORIGEM_HTML", None)
            try:
                builder.construir(origem_html=None, destino_html=saida_limpa)
            finally:
                if env_antigo is not None:
                    os.environ["GEDIV_ORIGEM_HTML"] = env_antigo

            self.assertTrue(saida_limpa.is_file())
            bytes_reconstruido = saida_limpa.read_bytes()
            bytes_versionado = UNIFICADO_HTML.read_bytes()
            self.assertEqual(
                bytes_reconstruido,
                bytes_versionado,
                "Build limpo a partir de modelo-base-sanitizado.html divergiu de observatorio/web/unificado/index.html!",
            )

            html_limpo = bytes_reconstruido.decode("utf-8")
            # Verificar estrutura, 7 abas, modalidades A–F / Horizontal / TS-01..TS-07 / Abono (sem TS-08),
            # consultas Por resenha / Por processo, alternância Quantidade / % e 3 perfis RBAC
            for marcador in (
                'data-view="geral"',
                'data-view="vertical"',
                'data-view="horizontal"',
                'data-view="tempo"',
                'data-view="outras"',
                'data-view="hoje"',
                'data-view="historico"',
                'id="byResenha"',
                'id="byProcess"',
                'id="resenhaProcessesCard"',
                'id="selectedProcCard"',
                'id="docModal"',
                'id="reviewDialog"',
                'id="conflictsDialog"',
                'id="auditDialog"',
                'id="batchDialog"',
                'id="revCorrCargo"',
                'id="revCorrLotacao"',
                'id="revActClassBox"',
                'data-unit="qty"',
                'data-unit="pct"',
                'TS-01',
                'TS-07',
                'ABONO_PERMANENCIA',
                'Abono de Permanência',
                'PENDENTE:TEC. ADM',
                'PENDENTE:STF',
                'parseVerticalLevel',
                'delicateAcctBtn',
                'delicateConflictsAct',
                'delicateAuditAct',
                'delicateBatchAct',
                'delicateScopeProxy',
                'serverAuditedExport',
                'setSession',
                'handleAuthExpiry',
                'Exportar visualização',
                'Empilhadas (Mês)',
                'Linhas (Mês)',
            ):
                self.assertIn(marcador, html_limpo, f"Funcionalidade/estrutura ausente após rebuild: {marcador}")
            self.assertNotIn("TS-08", html_limpo)

    def test_05_seguranca_administrativa_token_legado_cors_sessao_e_rbac(self) -> None:
        """Passo 2.3: valida desabilitação padrão do token técnico legado, mínimo de 32 caracteres em
        modo produção, ausência de escalonamento para admin, registro auditável sem expor o segredo,
        rejeição de origens CORS inseguras ('*', 'null', 'localhost', HTTP) e proteção de cookie/CSRF.
        """
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            pasta = pathlib.Path(tmp)
            with Banco(pasta / "observatorio.sqlite3") as banco:
                adaptador.importar_snapshot_reconciliado(banco, _bootstrap_sintetico())

            # 1. Validação estrita de origens CORS na inicialização
            for origem_invalida in (
                ["*"],
                ["null"],
                ["http://gediv.example.gov.br"],
                ["https://localhost:8000"],
                ["https://127.0.0.1:8000"],
                ["https://gediv.example.gov.br/caminho"],
            ):
                with self.subTest(origem_invalida=origem_invalida):
                    with self.assertRaises(ValueError):
                        criar_servidor(pasta, None, "127.0.0.1", 0, origens_admin=origem_invalida)

            # 2. Exigência de 32+ caracteres para token técnico em modo produção
            with self.assertRaises(ValueError):
                criar_servidor(pasta, "token-curto-de-20-ch", "127.0.0.1", 0, exigir_token_32=True)

            # 3. Servidor sem token técnico legado (desabilitado por padrão)
            srv_sem_tok = criar_servidor(pasta, None, "127.0.0.1", 0)
            threading.Thread(target=srv_sem_tok.serve_forever, daemon=True).start()
            base_sem = f"http://127.0.0.1:{srv_sem_tok.server_address[1]}"
            try:
                self.assertEqual(_req(f"{base_sem}/api/conflitos", token="qualquer-token-01234567890123456789")[0], 403)
            finally:
                srv_sem_tok.shutdown()
                srv_sem_tok.server_close()

            # 4. Servidor com token técnico forte (>= 32 chars) e origem HTTPS explícita
            token_forte = "token-tecnico-forte-com-mais-de-32-caracteres-2026"
            origem_ok = "https://painel.sead.pb.gov.br"
            contas = Contas(pasta / "contas.sqlite3")
            contas.criar("analista.ger", "Analista Gerencia", "SenhaGer#2026", papel="gerencia")
            srv = criar_servidor(pasta, token_forte, "127.0.0.1", 0, origens_admin=[origem_ok], exigir_token_32=True)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                # Token técnico acessa rota gerencial, mas NÃO possui papel 'admin' (não faz bypass de RBAC) e não consulta /api/auditoria
                self.assertEqual(_req(f"{base}/api/conflitos", token=token_forte)[0], 200)
                self.assertEqual(_req(f"{base}/api/auditoria", token=token_forte)[0], 403)
                self.assertEqual(_req(f"{base}/api/admin/usuarios", token=token_forte)[0], 403)
                self.assertEqual(_req(f"{base}/api/admin/lote", token=token_forte, payload={"rows": [{"id": "x"}]})[0], 403)

                # Conta admin nominal enxerga trilha global (inclusive USO_TOKEN_TECNICO_LEGADO sem expor o segredo)
                Contas(pasta / "contas.sqlite3").criar("admin.rbac", "Admin RBAC", "AdminForte#2026", papel="admin")
                st_adm_l, s_adm_l = _req(f"{base}/api/login", payload={"usuario": "admin.rbac", "senha": "AdminForte#2026"})
                self.assertEqual(st_adm_l, 200)
                st_aud, aud = _req(f"{base}/api/auditoria", token=s_adm_l["token"])
                self.assertEqual(st_aud, 200)
                texto_aud = json.dumps(aud, ensure_ascii=False)
                self.assertNotIn(token_forte, texto_aud)
                self.assertIn("USO_TOKEN_TECNICO_LEGADO", [t["acao"] for t in aud["trilha"]])

                # Cookie HttpOnly emitido no login + proteção CSRF em pedidos POST via cookie
                req_login = Request(
                    f"{base}/api/login",
                    data=json.dumps({"usuario": "analista.ger", "senha": "SenhaGer#2026"}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Forwarded-Proto": "https"},
                    method="POST",
                )
                with urlopen(req_login, timeout=10) as r_log:
                    set_cookie = r_log.headers.get("Set-Cookie") or ""
                    dados_log = json.loads(r_log.read().decode("utf-8"))
                self.assertIn("gediv_sessao=", set_cookie)
                self.assertIn("HttpOnly", set_cookie)
                self.assertIn("SameSite=Strict", set_cookie)
                self.assertIn("Secure", set_cookie)
                cookie_par = set_cookie.split(";", 1)[0]

                # Consulta autenticada usando apenas o cookie HttpOnly
                req_sess = Request(f"{base}/api/sessao", headers={"Cookie": cookie_par})
                with urlopen(req_sess, timeout=10) as r_s:
                    self.assertEqual(json.loads(r_s.read().decode("utf-8"))["usuario"], "analista.ger")

                # Ataques CSRF com cookie (cross-site, same-site e ausência de Origin/Sec-Fetch-Site/Referer) -> 403
                for headers_csrf in (
                    {"Content-Type": "application/json", "Cookie": cookie_par, "Sec-Fetch-Site": "cross-site"},
                    {"Content-Type": "application/json", "Cookie": cookie_par, "Sec-Fetch-Site": "same-site"},
                    {"Content-Type": "application/json", "Cookie": cookie_par},
                ):
                    req_csrf = Request(f"{base}/api/logout", data=b"{}", headers=headers_csrf, method="POST")
                    with self.assertRaises(HTTPError) as ctx_csrf:
                        urlopen(req_csrf, timeout=10)
                    self.assertEqual(ctx_csrf.exception.code, 403)

                # Pedido same-origin legítimo via cookie -> 200
                req_ok_csrf = Request(
                    f"{base}/api/logout",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "Cookie": cookie_par, "Sec-Fetch-Site": "same-origin"},
                    method="POST",
                )
                with urlopen(req_ok_csrf, timeout=10) as r_out:
                    self.assertEqual(r_out.status, 200)
            finally:
                srv.shutdown()
                srv.server_close()

    def test_06_rota_principal_unificada_rotas_legadas_e_compatibilidade_d1_d4(self) -> None:
        """Etapa 2B.2: garante que / e /index.html sirvam o painel unificado definitivo,
        preservando temporariamente /estatico/* e os endpoints das divergências D1–D4,
        o acesso autenticado aos PDFs, o Abono de Permanência (sem TS-08) e o bloqueio de path traversal.
        """
        import hashlib
        from observatorio.nucleo.acervo import Acervo

        html_esperado = UNIFICADO_HTML.read_bytes()
        sha_esperado = hashlib.sha256(html_esperado).hexdigest().upper()

        boot = _bootstrap_sintetico()
        # Inclui um item de Abono de Permanência para validar projeção e ausência de TS-08
        boot["rows"].append(
            {
                "id": "out-abono-001",
                "act": "Resenha nº 904/2026 — Abono de Permanência (conceito candidato)",
                "actType": "TEMA_FORA_DOS_EIXOS",
                "resenha": "Resenha 904/2026",
                "date": "2026-10-18",
                "page": 4,
                "url": "snapshot:rbac-4",
                "process": "PROC-TESTE-2026/004",
                "server": "SERVIDOR FICTICIO ABONO",
                "registration": "900004",
                "axis": "outros",
                "modality": "",
                "category": "ABONO_PERMANENCIA",
                "merit": "deferido",
                "validation": "pendente",
                "evidence": "ABONO DE PERMANÊNCIA DEFERIDO PROCESSO PROC-TESTE-2026/004 SERVIDOR FICTICIO ABONO.",
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            pasta = pathlib.Path(tmp)
            with Banco(pasta / "observatorio.sqlite3") as banco:
                adaptador.importar_snapshot_reconciliado(banco, boot)
                # Registra um PDF sintético no acervo para testar /api/pdf/<sha256>
                pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
                acervo = Acervo(pasta / "acervo")
                sha_pdf = acervo.guardar(pdf_bytes)[0]
                pub_id = banco.con.execute("SELECT id FROM publicacao LIMIT 1").fetchone()[0]
                banco.registrar_arquivo(pub_id, sha_pdf, len(pdf_bytes), acervo.caminho_relativo(sha_pdf))
                ato_id = banco.con.execute("SELECT id FROM ato LIMIT 1").fetchone()[0]

            contas = Contas(pasta / "contas.sqlite3")
            contas.criar("ger.rota", "Gerencia Rota", "Gerencia#2026", papel="gerencia")
            contas.criar("adm.rota", "Admin Rota", "AdminRota#2026", papel="admin")

            srv = criar_servidor(pasta, None, "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                # 1. Rotas principais (/, /index.html, /painel, /painel/, /painel/index.html) servem o HTML unificado idêntico
                for rota_unif in ("/", "/index.html", "/painel", "/painel/", "/painel/index.html"):
                    with self.subTest(rota_unif=rota_unif):
                        with urlopen(Request(f"{base}{rota_unif}"), timeout=10) as r:
                            corpo = r.read()
                            csp = r.headers.get("Content-Security-Policy") or ""
                        self.assertEqual(r.status, 200)
                        self.assertEqual(hashlib.sha256(corpo).hexdigest().upper(), sha_esperado)
                        self.assertIn("default-src 'self'", csp)
                        self.assertNotIn(b"SERVIDOR FICTICIO", corpo)

                # 2. Rotas legadas temporariamente preservadas para D1–D4 (/estatico/index.html e /estatico/app.js)
                for rota_leg in ("/estatico", "/estatico/", "/estatico/index.html", "/estatico/app.js", "/estatico/estilo.css"):
                    with self.subTest(rota_leg=rota_leg):
                        with urlopen(Request(f"{base}{rota_leg}"), timeout=10) as r_leg:
                            self.assertEqual(r_leg.status, 200)

                # 3. Bloqueio estrito de path traversal e arquivos internos do servidor
                for rota_proibida in (
                    "/../servidor.py",
                    "/painel/../servidor.py",
                    "/estatico/../servidor.py",
                    "/painel/modelo-base-sanitizado.html/../../servidor.py",
                    "/api/pdf/../../observatorio.sqlite3",
                ):
                    with self.subTest(rota_proibida=rota_proibida):
                        self.assertEqual(_req(f"{base}{rota_proibida}")[0], 404)

                # 4. Perfil Público: ausência total de dados individuais e bloqueio de PDF/endpoints restritos
                st_pub, d_pub = _req(f"{base}/api/data")
                self.assertEqual(st_pub, 200)
                self.assertEqual(d_pub["backend"]["papel"], "publico")
                self.assertEqual(d_pub["rows"], [])
                self.assertNotIn("SERVIDOR FICTICIO", json.dumps(d_pub, ensure_ascii=False))
                cats_pub = [c[0] for c in d_pub["categories"]]
                self.assertIn("ABONO_PERMANENCIA", cats_pub)
                self.assertNotIn("TS-08", cats_pub)

                self.assertEqual(_req(f"{base}/api/pdf/{sha_pdf}")[0], 401)
                self.assertEqual(_req(f"{base}/api/ato/{ato_id}")[0], 401)
                self.assertEqual(_req(f"{base}/api/conflitos")[0], 401)
                self.assertEqual(_req(f"{base}/api/auditoria")[0], 401)
                self.assertEqual(_req(f"{base}/api/exportar?formato=xlsx")[0], 401)

                # 5. Perfil Gerência: login, Abono sem TS-08, acesso ao PDF e compatibilidade com endpoints D1–D4
                st_lg, sess_ger = _req(f"{base}/api/login", payload={"usuario": "ger.rota", "senha": "Gerencia#2026"})
                self.assertEqual(st_lg, 200)
                tok_ger = sess_ger["token"]

                st_dg, d_ger = _req(f"{base}/api/data", token=tok_ger)
                self.assertEqual(st_dg, 200)
                self.assertEqual(d_ger["backend"]["papel"], "gerencia")
                self.assertFalse(d_ger["backend"]["ehAdmin"])
                # Etapa 4B: `outra_publicacao` (incluindo Abono de Permanência) fica isolada em `otherPublications`,
                # sem contaminar `rows` (decisões primárias GEDIV) e sem jamais introduzir TS-08.
                self.assertEqual([r for r in d_ger["rows"] if r["category"] == "ABONO_PERMANENCIA"], [])
                abono_pubs = [p for p in d_ger["otherPublications"] if p["category"] == "ABONO_PERMANENCIA"]
                self.assertEqual(len(abono_pubs), 1)
                self.assertEqual(abono_pubs[0]["axis"], "outros")
                self.assertFalse(any("TS-08" in str(r) for r in d_ger["rows"]))
                self.assertFalse(any("TS-08" in str(p) for p in d_ger["otherPublications"]))

                # Acesso ao PDF oficial no acervo sem regressão
                with urlopen(Request(f"{base}/api/pdf/{sha_pdf}", headers={"Authorization": f"Bearer {tok_ger}"}), timeout=10) as r_pdf:
                    self.assertEqual(r_pdf.status, 200)
                    self.assertEqual(r_pdf.read(), pdf_bytes)

                # Endpoints D1–D4 preservados para a gerência (/api/ato, /api/conflitos, /api/auditoria, /api/exportar)
                self.assertEqual(_req(f"{base}/api/ato/{ato_id}", token=tok_ger)[0], 200)
                self.assertEqual(_req(f"{base}/api/conflitos", token=tok_ger)[0], 200)
                with urlopen(Request(f"{base}/api/exportar?formato=csv", headers={"Authorization": f"Bearer {tok_ger}"}), timeout=10) as r_exp:
                    self.assertEqual(r_exp.status, 200)
                st_aud, d_aud = _req(f"{base}/api/auditoria", token=tok_ger)
                self.assertEqual(st_aud, 200)
                self.assertIn("EXPORTAR", [t["acao"] for t in d_aud["trilha"]])

                # Gerência permanece bloqueada em rotas exclusivas de Admin
                self.assertEqual(_req(f"{base}/api/admin/usuarios", token=tok_ger)[0], 403)

                # 6. Perfil Administração: acesso completo às rotas administrativas
                st_la, sess_adm = _req(f"{base}/api/login", payload={"usuario": "adm.rota", "senha": "AdminRota#2026"})
                self.assertEqual(st_la, 200)
                tok_adm = sess_adm["token"]
                self.assertEqual(_req(f"{base}/api/admin/usuarios", token=tok_adm)[0], 200)
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
