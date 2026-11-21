"""Testes abrangentes de segurança, privacidade da API pública, CSRF, RBAC de auditoria e fluxos D1–D4 (Etapa E)."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import threading
import unittest
import zipfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from observatorio.gerencias.gediv import catalogo as C
from observatorio.nucleo.acervo import Acervo
from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores
from observatorio.web.contas import Contas
from observatorio.web.servidor import criar_servidor


def _http(url: str, token: str | None = None, payload: dict | None = None, headers: dict | None = None, method: str | None = None):
    hdrs = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _bootstrap_privacidade() -> dict:
    """Fixture sintética com grupo pequeno (ANS n=2), grupo maior (MAG n=6, 5 deferidos + 1 indeferido),
    tempo de serviço TS-03 (n=1), duas datas no mesmo mês e itens pendentes/rejeitados/abono."""
    rows = []
    # MAG: 6 decisões conferidas em 2026-03-02 (5 DEFERIDO + 1 INDEFERIDO -> INDEFERIDO < 5)
    for i in range(1, 7):
        rows.append({
            "id": f"dec-mag-{i:03d}",
            "resenha": f"Resenha 10{(i // 2) + 1}/2026",
            "date": "2026-03-02",
            "page": 10 + (i // 2),
            "url": f"snapshot:mag-{i}",
            "process": f"PROC-SINT-2026/{i:04d}",
            "server": f"SERVIDOR SINTETICO MAG {i}",
            "registration": f"81000{i}",
            "axis": "progressao",
            "modality": "Vertical",
            "group": "MAG",
            "groupExpression": "MAG",
            "merit": "indeferido" if i == 6 else "deferido",
            "validation": "conferido",
            "levelFrom": "A",
            "levelTo": "B" if i != 6 else "",
            "evidence": f"Progressão sintética MAG {i}.",
        })
    # ANS: 2 decisões conferidas em 2026-03-03 (célula pequena < 5) + 1 PENDENTE para teste de polling
    for i in range(1, 4):
        rows.append({
            "id": f"dec-ans-{i:03d}",
            "resenha": "Resenha 201/2026",
            "date": "2026-03-03",
            "page": 18,
            "url": "snapshot:ans-1",
            "process": f"PROC-SINT-2026/10{i:02d}",
            "server": f"SERVIDOR SINTETICO ANS {i}",
            "registration": f"82000{i}",
            "axis": "progressao",
            "modality": "Horizontal",
            "group": "ANS",
            "groupExpression": "ANS",
            "merit": "deferido",
            "validation": "pendente" if i == 3 else "conferido",
            "evidence": f"Progressão sintética ANS {i}.",
        })
    # SSA: 7 decisões conferidas em 2026-04-05 (mês distinto >= 5 -> sobrevivente, enquanto 2026-03 = 8)
    for i in range(1, 8):
        rows.append({
            "id": f"dec-ssa-{i:03d}",
            "resenha": f"Resenha 30{i}/2026",
            "date": "2026-04-05",
            "page": 20 + i,
            "url": f"snapshot:ssa-{i}",
            "process": f"PROC-SINT-2026/20{i:02d}",
            "server": f"SERVIDOR SINTETICO SSA {i}",
            "registration": f"83000{i}",
            "axis": "progressao",
            "modality": "Horizontal",
            "group": "SSA",
            "groupExpression": "SSA",
            "merit": "deferido",
            "validation": "conferido",
            "evidence": f"Progressão sintética SSA {i}.",
        })
    # TS-03: 1 decisão conferida (< 5 -> suprimida; único suprimido em tempo força supressão secundária quando aplicável)
    rows.append({
        "id": "dec-ts3-001",
        "resenha": "Resenha 401/2026",
        "date": "2026-03-03",
        "page": 29,
        "url": "snapshot:ts3-1",
        "process": "PROC-SINT-2026/3001",
        "server": "SERVIDOR SINTETICO TS3",
        "registration": "840001",
        "axis": "tempo",
        "modality": "",
        "category": "TS-03",
        "merit": "deferido",
        "validation": "conferido",
        "evidence": "Licença sintética TS-03.",
    })
    # 1 rejeitada
    rows.append({
        "id": "dec-rej-001",
        "resenha": "Resenha 501/2026",
        "date": "2026-03-04",
        "page": 30,
        "url": "snapshot:rej-1",
        "process": "PROC-SINT-2026/4001",
        "server": "SERVIDOR SINTETICO REJ",
        "registration": "850001",
        "axis": "tempo",
        "modality": "",
        "category": "TS-01",
        "merit": "deferido",
        "validation": "rejeitado",
        "evidence": "Rejeitado sintético.",
    })
    return {"rows": rows, "events": []}


class TestSegurancaPrivacidadeAPI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.pasta = pathlib.Path(self._tmp.name)

        boot = _bootstrap_privacidade()
        with Banco(self.pasta / "observatorio.sqlite3") as banco:
            adaptador.importar_snapshot_reconciliado(banco, boot)
            sha_ref = banco.con.execute("SELECT sha256 FROM arquivo LIMIT 1").fetchone()[0]
            with banco.con:
                banco.con.execute(
                    "INSERT INTO outra_publicacao (id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        "outra-abono-sint-1",
                        "GEDIV",
                        sha_ref,
                        "PORTARIA",
                        21,
                        "2026-03-03",
                        "Portaria 99/2026 - Abono de Permanencia - SERVIDOR SINTETICO 99",
                        "EXPRESSO",
                        "Texto interno triagem Abono de Permanencia.",
                    ),
                )
                # Abre um conflito aberto para testar D2 e insere 1 evento pendente
                ato_mag = banco.con.execute("SELECT id FROM ato WHERE grupo='MAG' LIMIT 1").fetchone()[0]
                banco.con.execute(
                    "INSERT INTO conflito (alvo_tipo, alvo_id, campo, valor_vigente, valor_proposto, origem, estado, criado_em) "
                    "VALUES ('ato', ?, 'grupo', ?, ?, 'releitura', 'ABERTO', '2026-03-05T10:00:00Z')",
                    (ato_mag, json.dumps("MAG"), json.dumps("GAJ")),
                )
                banco.con.execute(
                    "INSERT INTO evento (id, gerencia, sha256, tipo, pagina, data_publicacao, vinculo, texto, estado) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    ("ev-sint-001"[:20].ljust(20, "0"), "GEDIV", sha_ref, C.RETIFICACAO, 15, "2026-03-05", "EXPRESSO", "Retificação sintética", "SUGERIDO"),
                )
                self.ato_id_teste = ato_mag
                self.sha_pdf = sha_ref

        acervo = Acervo(self.pasta / "acervo")
        pdf_fake = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
        destino_pdf = acervo.caminho(self.sha_pdf)
        destino_pdf.parent.mkdir(parents=True, exist_ok=True)
        destino_pdf.write_bytes(pdf_fake)

        contas = Contas(self.pasta / "contas.sqlite3")
        contas.criar("ger1.gediv", "Gerente Um", "SenhaGer1#2026", papel="gerencia")
        contas.criar("ger2.gediv", "Gerente Dois", "SenhaGer2#2026", papel="gerencia")
        contas.criar("adm1.gediv", "Admin Geral", "SenhaAdm1#2026", papel="admin")

        self.token_legado = "token-legado-super-seguro-32-caracteres-2026"
        self.srv = criar_servidor(
            self.pasta,
            self.token_legado,
            "127.0.0.1",
            0,
            origens_admin=["https://admin-oficial.exemplo.gov.br"],
        )
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def _login(self, usuario: str, senha: str) -> tuple[str, str]:
        st, hdrs, body = _http(f"{self.base}/api/login", payload={"usuario": usuario, "senha": senha})
        self.assertEqual(st, 200, body)
        cookie = (hdrs.get("Set-Cookie") or "").split(";", 1)[0]
        return json.loads(body)["token"], cookie

    def test_01_protecao_publica_apis_e_anti_inferencia(self) -> None:
        # 1. /api/outras bloqueado sem autenticação e preservado para gerência
        self.assertEqual(_http(f"{self.base}/api/outras")[0], 401)
        self.assertEqual(_http(f"{self.base}/api/outras", token="token-invalido-0123456789")[0], 403)
        tok_g1, _ = self._login("ger1.gediv", "SenhaGer1#2026")
        st_o, _, body_o = _http(f"{self.base}/api/outras", token=tok_g1)
        self.assertEqual(st_o, 200)
        self.assertEqual(len(json.loads(body_o)["itens"]), 1)

        # 2. /api/painel público: zero resenhas, zero eventos, zero fila interna, zero inteiros 1..4, zero subtração complementar
        st_p, _, body_p = _http(f"{self.base}/api/painel")
        self.assertEqual(st_p, 200)
        p_pub = json.loads(body_p)
        self.assertEqual(p_pub["resenhas"], [])
        self.assertEqual(p_pub["eventos"], [])
        self.assertEqual(p_pub["linhas"], [])
        for k, v in p_pub["apoio"].items():
            self.assertIsNone(v, f"apoio.{k} não deveria vazar em /api/painel público")
        # 16 decisões conferidas (6 MAG + 2 ANS + 7 SSA + 1 TS-03) -> faixa piso 15; INDEFERIDO=1 (<5) força supressão de deferidos e indeferidos
        self.assertEqual(p_pub["indicadores"]["decisoes"], 15)
        self.assertIsNone(p_pub["indicadores"]["deferidos"])
        self.assertIsNone(p_pub["indicadores"]["indeferidos"])
        self.assertNotIn("pdf_sha256", body_p.decode("utf-8"))
        self.assertNotIn("SERVIDOR SINTETICO", body_p.decode("utf-8"))
        # por_data tem apenas meses YYYY-MM (nenhum dia YYYY-MM-DD)
        for pt in p_pub["series"]["por_data"]:
            self.assertRegex(pt["data"], r"^\d{4}-\d{2}$")
        # ANS (n=2 < 5) é suprimido; por existir apenas 1 grupo positivo suprimido (<5) em Progressão (ANS),
        # supressão secundária também remove o menor restante (MAG=6), sobrando apenas SSA (>=5, faixa 5)!
        grupos_pub = {g["grupo"] for g in p_pub["series"]["por_grupo"]}
        self.assertNotIn("ANS", grupos_pub)
        self.assertNotIn("MAG", grupos_pub)
        self.assertIn("SSA", grupos_pub)

        # 3. Bloqueio de ataques de diferenciação/filtros combinados em /api/painel e /api/data
        queries_ataque = (
            "/api/painel?inicio=2026-03-03&fim=2026-03-03&grupo=ANS",
            "/api/painel?inicio=2026-03-01&fim=2026-03-02",
            "/api/painel?grupo=MAG,ANS",
            "/api/painel?grupo=MAG",
            "/api/painel?cartao=indeferidos",
            "/api/painel?escopo=pendente",
        )
        for q in queries_ataque:
            st_q, _, b_q = _http(f"{self.base}{q}")
            self.assertEqual(st_q, 200)
            self.assertEqual(json.loads(b_q)["indicadores"], p_pub["indicadores"], f"Query alterou resposta pública: {q}")

        # 4. /api/data público zera contadores internos e mantém integridade de contrato
        st_d, _, body_d = _http(f"{self.base}/api/data?grupo=ANS&inicio=2026-03-03&fim=2026-03-03")
        self.assertEqual(st_d, 200)
        d_pub = json.loads(body_d)
        self.assertEqual(d_pub["rows"], [])
        self.assertEqual(d_pub["backend"]["resenhas"], [])
        self.assertEqual(d_pub["meta"]["pendentes"], 0)
        self.assertEqual(d_pub["meta"]["rejeitados"], 0)
        self.assertEqual(d_pub["meta"]["eventosPendentes"], 0)
        self.assertEqual(d_pub["dashboard"]["counts"]["unlinkedEvents"], 0)
        self.assertEqual(d_pub["backend"]["indicadores"], p_pub["indicadores"])

        # 5. Resistência a polling temporal: confirmar 1 decisão pendente de ANS (16 -> 17 permanece no piso 15)
        st_rev, _, _ = _http(
            f"{self.base}/api/revisao",
            token=tok_g1,
            payload={
                "alvo": "decisao",
                "ids": ["dec-ans-003"],
                "decisao": "CONFERIR",
                "justificativa": "Conferência sintética para teste temporal",
                "confirma_fonte": True,
                "confirma_vinculo": True,
            },
        )
        self.assertEqual(st_rev, 200)
        d_pub_apos = json.loads(_http(f"{self.base}/api/data")[2])
        self.assertEqual(d_pub_apos["backend"]["indicadores"]["decisoes"], 15)
        self.assertEqual(d_pub_apos["dashboard"]["revision"], d_pub["dashboard"]["revision"])
        # Enquanto isso, gerência autenticada enxerga os 18 registros exatos (17 decisões + 1 abono/outras; rejeitada separada)
        d_ger = json.loads(_http(f"{self.base}/api/data", token=tok_g1)[2])
        self.assertEqual(d_ger["meta"]["conferidos"], 17)
        d_ger_conf = json.loads(_http(f"{self.base}/api/data?escopo=conferido", token=tok_g1)[2])
        self.assertEqual(len(d_ger_conf["backend"]["resenhas"]), 15)

    def test_02_auditoria_rbac_e_nao_repudio_token_legado(self) -> None:
        tok_g1, _ = self._login("ger1.gediv", "SenhaGer1#2026")
        tok_g2, _ = self._login("ger2.gediv", "SenhaGer2#2026")
        tok_adm, _ = self._login("adm1.gediv", "SenhaAdm1#2026")

        # ger1 realiza uma exportação e ger2 realiza outra ação; admin recebe lote
        self.assertEqual(_http(f"{self.base}/api/exportar?formato=csv", token=tok_g1)[0], 200)
        self.assertEqual(
            _http(
                f"{self.base}/api/revisao",
                token=tok_g2,
                payload={
                    "alvo": "decisao",
                    "ids": ["dec-ans-003"],
                    "decisao": "REABRIR",
                    "justificativa": "Reabertura para segunda revisão sintética",
                    "confirma_fonte": True,
                },
            )[0],
            200,
        )
        self.assertEqual(
            _http(f"{self.base}/api/admin/lote", token=tok_adm, payload={"rows": [{"id": "novo-x"}]})[0],
            200,
        )
        # Token legado registra prefixo explícito credencial_tecnica_legada em POST /api/revisao e é barrado em /api/auditoria
        st_leg_rev, _, _ = _http(
            f"{self.base}/api/revisao",
            token=self.token_legado,
            payload={
                "alvo": "decisao",
                "ids": ["dec-ans-003"],
                "decisao": "CONFERIR",
                "responsavel": "Admin Geral (adm1.gediv)",
                "justificativa": "Tentativa com nome arbitrário via token legado",
                "confirma_fonte": True,
                "confirma_vinculo": True,
            },
        )
        self.assertEqual(st_leg_rev, 200)
        self.assertEqual(_http(f"{self.base}/api/auditoria", token=self.token_legado)[0], 403)

        # ger1 vê SOMENTE seu próprio escopo (não vê ger2, adm1 nem eventos administrativos/legados)
        st_a1, _, body_a1 = _http(f"{self.base}/api/auditoria", token=tok_g1)
        self.assertEqual(st_a1, 200)
        aud1 = json.loads(body_a1)
        self.assertEqual(aud1["escopo"], "proprio")
        autores_a1 = {t["autor"] for t in aud1["trilha"]}
        self.assertEqual(autores_a1, {"Gerente Um (ger1.gediv)"})
        acoes_a1 = {t["acao"] for t in aud1["trilha"]}
        self.assertNotIn("RECEBER_LOTE_ADMIN", acoes_a1)
        self.assertNotIn("USO_TOKEN_TECNICO_LEGADO", acoes_a1)

        # admin vê trilha global e comprova prefixo não-repudiável no uso do token legado
        st_aa, _, body_aa = _http(f"{self.base}/api/auditoria", token=tok_adm)
        self.assertEqual(st_aa, 200)
        aud_adm = json.loads(body_aa)
        self.assertEqual(aud_adm["escopo"], "global")
        self.assertIn("RECEBER_LOTE_ADMIN", {t["acao"] for t in aud_adm["trilha"]})
        self.assertIn("credencial_tecnica_legada: Admin Geral (adm1.gediv)", {t["autor"] for t in aud_adm["trilha"]})

    def test_03_csrf_endurecido_e_login_origem(self) -> None:
        _, cookie = self._login("ger1.gediv", "SenhaGer1#2026")
        host_local = self.base.replace("http://", "")

        # Vetores CSRF bloqueados com cookie (fail-closed)
        for hdrs in (
            {"Cookie": cookie, "Sec-Fetch-Site": "cross-site"},
            {"Cookie": cookie, "Sec-Fetch-Site": "same-site"},
            {"Cookie": cookie, "Sec-Fetch-Site": "none"},
            {"Cookie": cookie},  # sem Sec-Fetch-Site, Origin nem Referer
            {"Cookie": cookie, "Origin": "null"},
            {"Cookie": cookie, "Origin": "https://atacante.example"},
            {"Cookie": cookie, "Referer": "https://atacante.example/pagina.html"},
        ):
            st, _, _ = _http(f"{self.base}/api/logout", payload={}, headers=hdrs, method="POST")
            self.assertEqual(st, 403, f"Deveria bloquear CSRF para headers={hdrs}")

        # Bloqueia /api/login vindo de origem não autorizada ou cross-site sem origem autorizada
        st_log_bad, _, _ = _http(
            f"{self.base}/api/login",
            payload={"usuario": "ger1.gediv", "senha": "SenhaGer1#2026"},
            headers={"Origin": "https://atacante.example", "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(st_log_bad, 403)

        # Permite /api/login vindo da origem explicitamente configurada em --origem-admin
        st_log_cors, hdrs_cors, _ = _http(
            f"{self.base}/api/login",
            payload={"usuario": "ger1.gediv", "senha": "SenhaGer1#2026"},
            headers={"Origin": "https://admin-oficial.exemplo.gov.br", "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(st_log_cors, 200)
        self.assertEqual(hdrs_cors.get("Access-Control-Allow-Origin"), "https://admin-oficial.exemplo.gov.br")

        # Permite logout legítimo com cookie + same-origin + Origin igual ao Host
        st_ok, _, _ = _http(
            f"{self.base}/api/logout",
            payload={},
            headers={"Cookie": cookie, "Sec-Fetch-Site": "same-origin", "Origin": f"http://{host_local}"},
            method="POST",
        )
        self.assertEqual(st_ok, 200)

    def test_04_fluxos_d1_a_d4_ponta_a_ponta(self) -> None:
        tok_g1, _ = self._login("ger1.gediv", "SenhaGer1#2026")
        tok_adm, _ = self._login("adm1.gediv", "SenhaAdm1#2026")

        # D1: corrigir campos em decisão individual e auditar valor anterior
        st_d1, _, body_d1 = _http(
            f"{self.base}/api/revisao",
            token=tok_g1,
            payload={
                "alvo": "decisao",
                "ids": ["dec-mag-001"],
                "decisao": "CONFERIR",
                "justificativa": "Correção documental D1 validada no PDF",
                "confirma_fonte": True,
                "confirma_vinculo": True,
                "correcoes": {"processo": "PROC-SINT-2026/9991", "classe_anterior": "B", "classe_posterior": "C"},
            },
        )
        self.assertEqual(st_d1, 200, body_d1)

        # D2: listar conflito aberto e resolver via POST /api/revisao alvo="conflito"
        st_c, _, body_c = _http(f"{self.base}/api/conflitos", token=tok_g1)
        self.assertEqual(st_c, 200)
        conflitos = json.loads(body_c)["conflitos"]
        self.assertEqual(len(conflitos), 1)
        st_d2, _, body_d2 = _http(
            f"{self.base}/api/revisao",
            token=tok_g1,
            payload={
                "alvo": "conflito",
                "id": conflitos[0]["id"],
                "decisao": "MANTER",
                "justificativa": "Resolução D2 confirmada contra edição oficial",
                "confirma_fonte": True,
            },
        )
        self.assertEqual(st_d2, 200, body_d2)
        self.assertEqual(json.loads(_http(f"{self.base}/api/conflitos", token=tok_g1)[2])["conflitos"], [])

        # D3: detalhe de ato (/api/ato/<id>) com correcoes + trilha + auditoria
        st_ato, _, body_ato = _http(f"{self.base}/api/ato/{self.ato_id_teste}", token=tok_g1)
        self.assertEqual(st_ato, 200, body_ato)
        ato_d = json.loads(body_ato)
        self.assertTrue(any(c["campo"] == "processo" for c in ato_d["correcoes"]))
        self.assertTrue(any(t["autor"] == "Gerente Um (ger1.gediv)" for t in ato_d["trilha"]))

        # D4: exportação CSV e XLSX auditada (independente de openpyxl para leitura de XLSX)
        st_csv, _, raw_csv = _http(f"{self.base}/api/exportar?formato=csv", token=tok_g1)
        self.assertEqual(st_csv, 200)
        self.assertIn("PROC-SINT-2026/9991", raw_csv.decode("utf-8"))
        st_xlsx, _, raw_xlsx = _http(f"{self.base}/api/exportar?formato=xlsx", token=tok_g1)
        self.assertEqual(st_xlsx, 200)
        self.assertEqual(raw_xlsx[:2], b"PK")
        with zipfile.ZipFile(io.BytesIO(raw_xlsx)) as z:
            self.assertIn("xl/workbook.xml", z.namelist())
        st_aud_g, _, body_aud_g = _http(f"{self.base}/api/auditoria", token=tok_adm)
        self.assertEqual(st_aud_g, 200)
        self.assertIn("EXPORTAR", [t["acao"] for t in json.loads(body_aud_g)["trilha"]])

    def test_05_snapshot_publico_controlado_anti_inferencia_4_5_e_9_10(self) -> None:
        """Tarefa 3: comprova que confirmações sequenciais em POST /api/revisao cruzando múltiplos
        de 5 (4 -> 5 e 9 -> 10) NÃO alteram imediatamente /api/painel nem /api/data públicos antes
        da publicação controlada do snapshot, e que snapshots inválidos são rejeitados sem substituir o anterior."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            pasta = pathlib.Path(tmp)
            rows = []
            # 12 decisões sintéticas do grupo SSA (4 inicialmente conferidas, 8 pendentes)
            for i in range(1, 13):
                rows.append({
                    "id": f"dec-seq-{i:03d}",
                    "resenha": f"Resenha 80{i}/2026",
                    "date": "2026-05-10",
                    "page": i,
                    "url": f"snapshot:seq-{i}",
                    "process": f"PROC-SEQ-2026/{i:04d}",
                    "server": f"SERVIDOR SEQUENCIAL {i}",
                    "registration": f"8800{i:02d}",
                    "axis": "progressao",
                    "modality": "Horizontal",
                    "group": "SSA",
                    "groupExpression": "SSA",
                    "merit": "deferido",
                    "validation": "conferido" if i <= 4 else "pendente",
                    "evidence": f"Progressão sequencial {i}.",
                })
            with Banco(pasta / "observatorio.sqlite3") as banco:
                adaptador.importar_snapshot_reconciliado(banco, {"rows": rows, "events": []})
                indicadores.publicar_snapshot_publico(banco, pasta / indicadores.ARQUIVO_SNAPSHOT_PUBLICO)

            contas = Contas(pasta / "contas.sqlite3")
            contas.criar("ger.seq", "Gerente Sequencial", "SenhaSeq#2026", papel="gerencia")
            contas.criar("adm.seq", "Admin Sequencial", "SenhaAdm#2026", papel="admin")

            srv = criar_servidor(pasta, None, "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            base_seq = f"http://127.0.0.1:{srv.server_address[1]}"

            st_g, _, body_g = _http(f"{base_seq}/api/login", payload={"usuario": "ger.seq", "senha": "SenhaSeq#2026"})
            self.assertEqual(st_g, 200)
            tok_ger = json.loads(body_g)["token"]
            st_a, _, body_a = _http(f"{base_seq}/api/login", payload={"usuario": "adm.seq", "senha": "SenhaAdm#2026"})
            self.assertEqual(st_a, 200)
            tok_adm = json.loads(body_a)["token"]

            # Estado inicial (4 conferidos < 5): público vê decisoes = None
            p0 = json.loads(_http(f"{base_seq}/api/painel")[2])
            d0 = json.loads(_http(f"{base_seq}/api/data")[2])
            self.assertIsNone(p0["indicadores"]["decisoes"])
            self.assertIsNone(d0["backend"]["indicadores"]["decisoes"])

            # 1) Cruzar fronteira 4 -> 5 via POST /api/revisao
            st_r5, _, _ = _http(
                f"{base_seq}/api/revisao",
                token=tok_ger,
                payload={
                    "alvo": "decisao",
                    "ids": ["dec-seq-005"],
                    "decisao": "CONFERIR",
                    "justificativa": "Cruzando limiar 4 para 5",
                    "confirma_fonte": True,
                    "confirma_vinculo": True,
                },
            )
            self.assertEqual(st_r5, 200)
            # Público NÃO observa mudança imediata (continua None), enquanto gerência vê 5 em tempo real
            self.assertIsNone(json.loads(_http(f"{base_seq}/api/painel")[2])["indicadores"]["decisoes"])
            self.assertIsNone(json.loads(_http(f"{base_seq}/api/data")[2])["backend"]["indicadores"]["decisoes"])
            self.assertEqual(json.loads(_http(f"{base_seq}/api/data", token=tok_ger)[2])["meta"]["conferidos"], 5)

            # 2) Confirmar 6, 7, 8, 9 e cruzar fronteira 9 -> 10 via POST /api/revisao
            for idx in range(6, 11):
                st_ri, _, _ = _http(
                    f"{base_seq}/api/revisao",
                    token=tok_ger,
                    payload={
                        "alvo": "decisao",
                        "ids": [f"dec-seq-{idx:03d}"],
                        "decisao": "CONFERIR",
                        "justificativa": f"Conferência sequencial item {idx}",
                        "confirma_fonte": True,
                        "confirma_vinculo": True,
                    },
                )
                self.assertEqual(st_ri, 200)
                # Em todas as etapas (inclusive 9 -> 10), público segue congelado no snapshot anterior
                self.assertIsNone(json.loads(_http(f"{base_seq}/api/painel")[2])["indicadores"]["decisoes"])
                self.assertIsNone(json.loads(_http(f"{base_seq}/api/data")[2])["backend"]["indicadores"]["decisoes"])

            # Gerência enxerga 10 conferidos em tempo real, mas não tem permissão para publicar snapshot público (403)
            self.assertEqual(json.loads(_http(f"{base_seq}/api/data", token=tok_ger)[2])["meta"]["conferidos"], 10)
            self.assertEqual(_http(f"{base_seq}/api/admin/snapshot-publico", token=tok_ger, payload={})[0], 403)

            # 3) Publicação controlada do snapshot público pelo admin atualiza para a faixa permitida (10)
            st_pub, _, body_pub = _http(f"{base_seq}/api/admin/snapshot-publico", token=tok_adm, payload={})
            self.assertEqual(st_pub, 200, body_pub)
            self.assertEqual(json.loads(body_pub)["indicadores"]["decisoes"], 10)
            self.assertEqual(json.loads(_http(f"{base_seq}/api/painel")[2])["indicadores"]["decisoes"], 10)
            self.assertEqual(json.loads(_http(f"{base_seq}/api/data")[2])["backend"]["indicadores"]["decisoes"], 10)

            # 4) Snapshot inválido é rejeitado e NÃO substitui o arquivo anterior em disco
            caminho_snap = pasta / indicadores.ARQUIVO_SNAPSHOT_PUBLICO
            bytes_antes = caminho_snap.read_bytes()
            snap_valido = json.loads(bytes_antes.decode("utf-8"))

            for mutacao in (
                lambda s: s["painel"]["indicadores"].__setitem__("decisoes", 7),  # fora de múltiplo de 5
                lambda s: s["painel"]["indicadores"].__setitem__("decisoes", 3),  # abaixo do limiar 5
                lambda s: s["painel"]["indicadores"].__setitem__("indeferidos", None),  # quebra supressão complementar
                lambda s: s["painel"]["series"]["por_data"].append({"data": "2026-05-10", "total": 10}),  # data diária
                lambda s: s["data"]["rows"].append({"id": "vazamento"}),  # linha individual
            ):
                candidato = json.loads(bytes_antes.decode("utf-8"))
                mutacao(candidato)
                with self.assertRaises(ValueError):
                    indicadores.publicar_snapshot_publico(None, caminho_snap, snapshot=candidato)
                self.assertEqual(caminho_snap.read_bytes(), bytes_antes)
                self.assertEqual(
                    indicadores.carregar_snapshot_publico(caminho_snap)["painel"]["indicadores"]["decisoes"],
                    snap_valido["painel"]["indicadores"]["decisoes"],
                )

    def test_06_ciclo_sessao_cookie_httponly_sem_bearer(self) -> None:
        """Tarefa 2: comprova autenticação integral via cookie HttpOnly (sem cabeçalho Authorization),
        retorno 401 quando a sessão do cookie expira ou é encerrada, e invalidação no logout."""
        _, cookie = self._login("ger1.gediv", "SenhaGer1#2026")
        host_local = self.base.replace("http://", "")
        hdrs_get = {"Cookie": cookie}
        hdrs_post = {"Cookie": cookie, "Sec-Fetch-Site": "same-origin", "Origin": f"http://{host_local}"}

        # 1. Sessão e rotas protegidas funcionam apenas com o cookie HttpOnly (sem Bearer)
        st_s, _, body_s = _http(f"{self.base}/api/sessao", headers=hdrs_get)
        self.assertEqual(st_s, 200)
        self.assertEqual(json.loads(body_s)["usuario"], "ger1.gediv")

        st_d, _, body_d = _http(f"{self.base}/api/data", headers=hdrs_get)
        self.assertEqual(st_d, 200)
        d_cookie = json.loads(body_d)
        self.assertTrue(d_cookie["backend"]["autenticado"])
        self.assertEqual(d_cookie["backend"]["usuario"], "ger1.gediv")
        self.assertEqual(d_cookie["backend"]["nome"], "Gerente Um")
        self.assertGreater(len(d_cookie["rows"]), 0)

        self.assertEqual(_http(f"{self.base}/api/conflitos", headers=hdrs_get)[0], 200)
        self.assertEqual(_http(f"{self.base}/api/auditoria", headers=hdrs_get)[0], 200)

        # 2. Logout via cookie invalida a sessão no servidor e limpa o cookie (Max-Age=0)
        st_out, hdrs_out, _ = _http(f"{self.base}/api/logout", payload={}, headers=hdrs_post, method="POST")
        self.assertEqual(st_out, 200)
        self.assertIn("Max-Age=0", hdrs_out.get("Set-Cookie") or "")

        # 3. Reutilizar o cookie após logout/expiração retorna 401 nas rotas protegidas e volta /api/data ao modo público
        self.assertEqual(_http(f"{self.base}/api/sessao", headers=hdrs_get)[0], 401)
        self.assertEqual(_http(f"{self.base}/api/conflitos", headers=hdrs_get)[0], 401)
        self.assertEqual(_http(f"{self.base}/api/auditoria", headers=hdrs_get)[0], 401)
        self.assertEqual(
            _http(f"{self.base}/api/revisao", payload={"alvo": "decisao"}, headers=hdrs_post, method="POST")[0],
            401,
        )
        d_apos_exp = json.loads(_http(f"{self.base}/api/data", headers=hdrs_get)[2])
        self.assertFalse(d_apos_exp["backend"]["autenticado"])
        self.assertEqual(d_apos_exp["rows"], [])


if __name__ == "__main__":
    unittest.main()
