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


if __name__ == "__main__":
    unittest.main()
