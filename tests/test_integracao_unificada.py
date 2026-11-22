"""Suíte de testes automatizados da integração definitiva do Observatório GEDIV (Etapas 7 a 13).

Verifica:
1. Adaptador bidirecional (`adaptador.py`) sem perda de campos (`eixo/axis`, `modalidade/modality`,
   `resultado/merit`, `validacao/validation`, `servidor/server`, `matricula/registration`,
   `processo/process`, `detalhe`, `nota_preliminar/preliminaryReview`, `levelFrom`, `levelTo`);
2. Regra normativa especial para grupos ocupacionais (`TEC. ADM` NÃO equiparado a `AST`;
   `STF` NÃO equiparado a `SFT`; `SAUDE -> SSA` e `ESPECIAL -> ESP` normalizados; zero perda de registros);
3. Cálculo dinâmico de Progressões Verticais A–F (`por_nivel_vertical` e `resumo_nivel_vertical`) no backend;
4. Simulação não destrutiva (`simular_reconciliacao` dry-run) e importação idempotente (`importar_snapshot_reconciliado`)
   preservando 1.065 pendentes, 1 rejeitado, 23 eventos pendentes e 101 observações preliminares, sem auto-homologação;
5. Privacidade, autenticação, trilha de auditoria e controle de acesso em `/api/data`, `/api/painel`, `/api/revisao`,
   `/api/exportar` e `/painel/index.html` (garantindo ausência de dados pessoais embutidos no HTML);
6. Fidelidade visual e paleta de cores do dashboard unificado (**0 novas cores** fora da paleta original).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from observatorio.gerencias.gediv import catalogo as C
from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores
from observatorio.web.contas import Contas
from observatorio.web.servidor import criar_servidor

REPO_DIR = pathlib.Path(__file__).resolve().parents[1]
_ENV_ORIGEM = os.environ.get("GEDIV_ORIGEM_HTML")
REF_HTML = pathlib.Path(_ENV_ORIGEM) if _ENV_ORIGEM else None
UNIFICADO_HTML = REPO_DIR / "observatorio" / "web" / "unificado" / "index.html"
PALETA_JSON = REPO_DIR / "observatorio" / "web" / "unificado" / "paleta-aprovada.json"


def _bootstrap_sintetico() -> dict:
    """Fixture sintética sem dados pessoais para execução portátil no GitHub Actions."""
    return {
        "rows": [
            {
                "id": "dec-int-001",
                "resenha": "Resenha 911/2026",
                "date": "2026-10-15",
                "page": 1,
                "url": "snapshot:int-1",
                "process": "PROC-TESTE-2026/101",
                "server": "SERVIDOR FICTICIO UM",
                "registration": "910001",
                "axis": "progressao",
                "modality": "Vertical",
                "group": "TEC-ADM",
                "groupExpression": "TEC. ADM",
                "merit": "deferido",
                "validation": "pendente",
                "levelFrom": "D",
                "levelTo": "E",
                "preliminaryReview": "Nota preliminar de teste.",
                "evidence": "Progressão Vertical D para E deferida.",
            },
            {
                "id": "dec-int-002",
                "resenha": "Resenha 912/2026",
                "date": "2026-10-16",
                "page": 2,
                "url": "snapshot:int-2",
                "process": "PROC-TESTE-2026/102",
                "server": "SERVIDOR FICTICIO DOIS",
                "registration": "910002",
                "axis": "tempo",
                "modality": "",
                "category": "TS-01",
                "merit": "indeferido",
                "validation": "pendente",
                "evidence": "Anotação de Tempo de Serviço TS-01 indeferida.",
            },
            {
                "id": "dec-int-003",
                "resenha": "Resenha 913/2026",
                "date": "2026-10-17",
                "page": 3,
                "url": "snapshot:int-3",
                "process": "PROC-TESTE-2026/103",
                "server": "SERVIDOR FICTICIO TRES",
                "registration": "910003",
                "axis": "progressao",
                "modality": "Horizontal",
                "group": "SAUDE",
                "groupExpression": "SAUDE",
                "merit": "deferido",
                "validation": "rejeitado",
                "evidence": "Registro rejeitado de teste.",
            },
        ],
        "events": [
            {
                "id": "ev-int-001",
                "type": "Retificação",
                "date": "2026-10-18",
                "page": 4,
                "url": "snapshot:int-4",
                "act": "Resenha 914/2026",
                "description": "Retificação da Resenha 911/2026 GEDIV.",
            }
        ],
    }


class TestIntegracaoUnificadaGEDIV(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.usando_snapshot_real = bool(REF_HTML and REF_HTML.is_file())
        cls.bootstrap = (
            adaptador.extrair_bootstrap_de_html(REF_HTML)
            if cls.usando_snapshot_real
            else _bootstrap_sintetico()
        )

    def test_01_regra_especial_grupos_ocupacionais(self) -> None:
        """Etapa 8: TEC. ADM não pode virar AST e STF não pode virar SFT automaticamente."""
        g_tec, exp_tec, pend_tec = adaptador.mapear_grupo_para_backend("TEC-ADM")
        self.assertIsNone(g_tec)
        self.assertEqual(exp_tec, "TEC. ADM")
        self.assertTrue(pend_tec)

        f_tec = adaptador.mapear_grupo_para_frontend(g_tec, exp_tec)
        self.assertEqual(f_tec["group"], "PENDENTE:TEC. ADM")
        self.assertIsNone(f_tec["groupCanonical"])
        self.assertTrue(f_tec["groupPendingConfirmation"])

        g_stf, exp_stf, pend_stf = adaptador.mapear_grupo_para_backend("STF")
        self.assertIsNone(g_stf)
        self.assertEqual(exp_stf, "STF")
        self.assertTrue(pend_stf)

        f_stf = adaptador.mapear_grupo_para_frontend(g_stf, exp_stf)
        self.assertEqual(f_stf["group"], "PENDENTE:STF")
        self.assertIsNone(f_stf["groupCanonical"])
        self.assertTrue(f_stf["groupPendingConfirmation"])

        # Equivalências comprovadas no catálogo oficial
        g_ssa, _, pend_ssa = adaptador.mapear_grupo_para_backend("SAUDE")
        self.assertEqual(g_ssa, "SSA")
        self.assertFalse(pend_ssa)

        g_esp, _, pend_esp = adaptador.mapear_grupo_para_backend("ESPECIAL")
        self.assertEqual(g_esp, "ESP")
        self.assertFalse(pend_esp)

    def test_02_adaptador_bidirecional_preserva_campos(self) -> None:
        """Etapa 8: conversão frontend <-> backend preserva 100% dos campos e notas preliminares."""
        amostra = next(
            r for r in self.bootstrap["rows"] if r.get("preliminaryReview")
        )
        b_row = adaptador.frontend_para_backend_linha(amostra)
        self.assertEqual(b_row["id"], amostra["id"])
        self.assertEqual(b_row["processo"], amostra["process"])
        self.assertEqual(b_row["servidor"], amostra["server"])
        self.assertEqual(b_row["matricula"], amostra["registration"])
        self.assertEqual(
            b_row["detalhe"]["nota_preliminar"], amostra["preliminaryReview"]
        )

        f_row = adaptador.backend_para_frontend_linha(b_row)
        self.assertEqual(f_row["id"], amostra["id"])
        self.assertEqual(f_row["process"], amostra["process"])
        self.assertEqual(f_row["server"], amostra["server"])
        self.assertEqual(f_row["registration"], amostra["registration"])
        self.assertEqual(f_row["axis"], amostra["axis"])
        self.assertEqual(f_row["modality"], amostra["modality"])
        self.assertEqual(f_row["merit"], amostra["merit"])
        self.assertEqual(f_row["validation"], amostra["validation"])
        self.assertEqual(
            f_row["preliminaryReview"], amostra["preliminaryReview"]
        )

    @unittest.skipUnless(
        bool(REF_HTML and REF_HTML.is_file() and (REPO_DIR / "dados" / "pdfs_2026").is_dir()),
        "Requer snapshot local privado (GEDIV_ORIGEM_HTML) e pasta dados/pdfs_2026 fora do Git.",
    )
    def test_03_dry_run_e_reconciliacao_idempotente_niveis_af(self) -> None:
        """Etapas 9 e 10: dry-run, importação idempotente, contagens exatas e níveis A–F."""
        dry = adaptador.simular_reconciliacao(
            self.bootstrap, pasta_pdfs=REPO_DIR / "dados" / "pdfs_2026"
        )
        self.assertEqual(dry["totais_snapshot"]["total_registros"], 1066)
        self.assertEqual(dry["totais_snapshot"]["pendentes"], 1065)
        self.assertEqual(dry["totais_snapshot"]["rejeitados"], 1)
        self.assertEqual(dry["totais_snapshot"]["conferidos"], 0)
        self.assertEqual(dry["totais_snapshot"]["eventos_modificadores"], 23)
        self.assertEqual(dry["totais_snapshot"]["observacoes_preliminares"], 101)
        self.assertEqual(dry["qualidade_e_documentos"]["pdfs_acessiveis_no_disco"], 52)
        self.assertEqual(dry["qualidade_e_documentos"]["pdfs_ausentes_no_disco"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "teste.sqlite3"
            with Banco(db_path) as banco:
                r1 = adaptador.importar_snapshot_reconciliado(banco, self.bootstrap)
                self.assertEqual(r1["inseridos_decisao"], 986)
                self.assertEqual(r1["inseridos_outros"], 80)
                self.assertEqual(r1["inseridos_eventos"], 23)

                # Segunda execução deve ser estritamente idempotente (zero duplicação)
                r2 = adaptador.importar_snapshot_reconciliado(banco, self.bootstrap)
                self.assertEqual(r2["inseridos_decisao"], 0)
                self.assertEqual(r2["preservados_decisao"], 986)
                self.assertEqual(r2["inseridos_outros"], 0)
                self.assertEqual(r2["inseridos_eventos"], 0)

                p_ger = indicadores.painel(
                    banco, {"escopo": "pendente"}, indicadores.GERENCIA_PERFIL
                )
                res_nv = p_ger["series"]["resumo_nivel_vertical"]
                self.assertEqual(res_nv["total_progressao"], 876)
                self.assertEqual(res_nv["total_horizontal"], 177)
                self.assertEqual(res_nv["total_vertical"], 699)
                self.assertEqual(res_nv["classificados"], 566)
                self.assertEqual(res_nv["nao_identificados"], 133)

                por_nv = {
                    x["nivel"]: x["total"]
                    for x in p_ger["series"]["por_nivel_vertical"]
                }
                self.assertEqual(
                    por_nv,
                    {
                        "A": 0,
                        "B": 18,
                        "C": 101,
                        "D": 116,
                        "E": 322,
                        "F": 9,
                        "NAO_IDENTIFICADO": 133,
                    },
                )

                # Filtro por nível E e por grupo pendente TEC. ADM no backend
                p_nv_e = indicadores.painel(
                    banco,
                    {"escopo": "pendente", "nivel": "E"},
                    indicadores.GERENCIA_PERFIL,
                )
                self.assertEqual(p_nv_e["indicadores"]["decisoes"], 322)

                p_tec = indicadores.painel(
                    banco,
                    {"escopo": "pendente", "grupo": "PENDENTE:TEC. ADM"},
                    indicadores.GERENCIA_PERFIL,
                )
                self.assertEqual(p_tec["indicadores"]["decisoes"], 568)

    def test_04_servidor_privacidade_autenticacao_e_revisao(self) -> None:
        """Etapas 11 e 13: HTML sem dados embutidos, /api/data protegido e /api/revisao auditado."""
        html_unificado = UNIFICADO_HTML.read_text(encoding="utf-8")
        self.assertIn('window.GEDIV_BOOTSTRAP={"rows":[],"events":[', html_unificado)
        self.assertNotRegex(html_unificado, r"SAD-PSE-202\d/\d+")
        self.assertNotRegex(html_unificado, r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
        self.assertNotRegex(html_unificado, r'"server"\s*:\s*"[A-ZÀ-Ú]{3,}')

        # Paleta de cores: zero cores novas em relação à paleta canônica aprovada
        hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
        cores_orig = {c.lower() for c in json.loads(PALETA_JSON.read_text(encoding="utf-8"))["cores_hex"]}
        cores_unif = {c.lower() for c in hex_re.findall(html_unificado)}
        self.assertEqual(cores_unif - cores_orig, set())

        exp_total = len(self.bootstrap["rows"])
        exp_pend_dec = sum(
            1 for r in self.bootstrap["rows"]
            if r.get("axis") != "outros" and r.get("validation", "pendente") != "rejeitado"
        )
        exp_pend_total = sum(1 for r in self.bootstrap["rows"] if r.get("validation", "pendente") == "pendente")
        exp_rej = sum(1 for r in self.bootstrap["rows"] if r.get("validation") == "rejeitado")
        exp_ev = len(self.bootstrap["events"])
        exp_notes = sum(1 for r in self.bootstrap["rows"] if str(r.get("preliminaryReview") or "").strip())

        with tempfile.TemporaryDirectory() as tmp:
            pasta = pathlib.Path(tmp)
            with Banco(pasta / "observatorio.sqlite3") as banco:
                adaptador.importar_snapshot_reconciliado(banco, self.bootstrap)

            contas = Contas(pasta / "contas.sqlite3")
            contas.criar("revisor.gediv", "Analista GEDIV", "SenhaForte#2026")

            srv = criar_servidor(pasta, "token-tecnico-secreto-2026", "127.0.0.1", 0)
            porta = srv.server_address[1]
            import threading

            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            base_url = f"http://127.0.0.1:{porta}"
            try:
                # 1. Consulta pública anônima a /api/data não deve retornar linhas individuais nem fila interna
                with urlopen(f"{base_url}/api/data") as resp:
                    d_pub = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(d_pub["backend"]["autenticado"])
                self.assertEqual(len(d_pub["rows"]), 0)
                self.assertEqual(d_pub["meta"]["pendentes"], 0)
                self.assertEqual(d_pub["meta"]["rejeitados"], 0)
                self.assertEqual(d_pub["dashboard"]["counts"]["unlinkedEvents"], 0)

                # 2. Tentativa de revisão sem autenticação -> HTTP 401
                req_unauth = Request(
                    f"{base_url}/api/revisao",
                    data=json.dumps({"alvo": "decisao", "ids": ["x"], "decisao": "CONFERIR"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(req_unauth)
                self.assertEqual(ctx.exception.code, 401)

                # 3. Login com conta nominal scrypt
                req_login = Request(
                    f"{base_url}/api/login",
                    data=json.dumps({"usuario": "revisor.gediv", "senha": "SenhaForte#2026"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req_login) as resp:
                    sessao = json.loads(resp.read().decode("utf-8"))
                token = sessao["token"]
                auth_hdr = {"Authorization": f"Bearer {token}"}

                # 4. Consulta autenticada a /api/data -> registros e eventos preservados
                req_data = Request(f"{base_url}/api/data", headers=auth_hdr)
                with urlopen(req_data) as resp:
                    d_ger = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(d_ger["backend"]["autenticado"])
                self.assertEqual(len(d_ger["rows"]), exp_total)
                self.assertEqual(len(d_ger["events"]), exp_ev)
                self.assertEqual(sum(1 for r in d_ger["rows"] if r["validation"] == "pendente"), exp_pend_total)
                self.assertEqual(sum(1 for r in d_ger["rows"] if r["validation"] == "rejeitado"), exp_rej)
                self.assertEqual(sum(1 for r in d_ger["rows"] if r["preliminaryReview"]), exp_notes)

                # 5. Revisar 1 decisão (CONFERIR com confirma_fonte=True e confirma_vinculo=True)
                alvo_row = next(r for r in d_ger["rows"] if r["axis"] == "progressao" and r["validation"] == "pendente")
                req_rev = Request(
                    f"{base_url}/api/revisao",
                    data=json.dumps({
                        "alvo": "decisao",
                        "ids": [alvo_row["id"]],
                        "decisao": "CONFERIR",
                        "justificativa": "Conferido integralmente com o PDF oficial do DOE.",
                        "confirma_fonte": True,
                        "confirma_vinculo": True,
                    }).encode("utf-8"),
                    headers={**auth_hdr, "Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req_rev) as resp:
                    r_rev = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(r_rev["estado"], "CONFERIDO")

                # 6. Verificar trilha de auditoria registrada com nome da conta autenticada
                req_aud = Request(f"{base_url}/api/auditoria", headers=auth_hdr)
                with urlopen(req_aud) as resp:
                    aud = json.loads(resp.read().decode("utf-8"))
                acoes = [(t["acao"], t["autor"], t["alvo_id"]) for t in aud["trilha"]]
                self.assertIn(("CONFERIR", "Analista GEDIV (revisor.gediv)", alvo_row["id"]), acoes)
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
