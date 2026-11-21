"""Painel de administração: contas por pessoa, sessões, bloqueio, CORS e autoria das revisões. Dados SINTÉTICOS."""
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from observatorio.web import contas as K
from observatorio.web.servidor import criar_servidor
from tests import test_painel as TP

SENHA = "senha-de-teste-forte-123"
ORIGEM = "https://gedivseadpb-boop.github.io"


class TesteContas(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(pasta.cleanup)
        self.caminho = Path(pasta.name) / "contas.sqlite3"
        self.c = K.Contas(self.caminho)
        self.c.criar("maria.silva", "Maria da Silva", SENHA)

    def bruto(self, sql, *par):
        con = sqlite3.connect(self.caminho)
        try:
            with con:
                return con.execute(sql, par).fetchall()
        finally:
            con.close()

    def test_senha_nunca_fica_em_texto_e_cada_conta_tem_sal_proprio(self):
        self.c.criar("joao", "João Teste", SENHA)
        linhas = self.bruto("SELECT sal, senha_hash FROM usuario")
        self.assertTrue(all(SENHA.encode() not in bytes(h) for _, h in linhas))
        self.assertNotEqual(linhas[0][0], linhas[1][0])
        self.assertNotEqual(linhas[0][1], linhas[1][1])
        self.assertNotIn(SENHA.encode(), self.caminho.read_bytes())

    def test_regras_de_criacao(self):
        for usuario, nome, senha in (("ab", "Nome Ok", SENHA), ("Maria Silva", "Nome Ok", SENHA), ("ana", "Ana Teste", "curta"),
                                     ("carla", "Carla", "carla-senha-longa"), ("maria.silva", "Outra", SENHA)):
            with self.subTest(usuario=usuario, senha=senha):
                with self.assertRaises(ValueError):
                    self.c.criar(usuario, nome, senha)

    def test_login_cria_sessao_guardada_so_pelo_hash(self):
        s = self.c.entrar("Maria.Silva ", SENHA)
        self.assertEqual((s["usuario"], s["nome"]), ("maria.silva", "Maria da Silva"))
        self.assertEqual(self.c.sessao(s["token"])["nome"], "Maria da Silva")
        self.assertEqual(self.bruto("SELECT COUNT(*) FROM sessao WHERE token_hash = ?", s["token"])[0][0], 0)
        self.assertIsNone(self.c.sessao("token-inventado"))

    def test_erros_nao_revelam_se_o_usuario_existe(self):
        for usuario, senha in (("maria.silva", "errada-errada"), ("ninguem", SENHA), ("", ""), ("x" * 500, SENHA)):
            with self.subTest(usuario=usuario[:10]):
                with self.assertRaises(K.AcessoNegado) as ctx:
                    self.c.entrar(usuario, senha)
                self.assertEqual(str(ctx.exception), "")

    def test_bloqueio_depois_de_cinco_erros_e_liberacao_depois_do_prazo(self):
        for _ in range(K.MAX_FALHAS):
            with self.assertRaises(K.AcessoNegado):
                self.c.entrar("maria.silva", "errada-errada")
        with self.assertRaises(K.AcessoNegado):                               # bloqueada mesmo com a senha certa
            self.c.entrar("maria.silva", SENHA)
        passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
        self.bruto("UPDATE usuario SET bloqueado_ate = ?", passado)
        self.assertTrue(self.c.entrar("maria.silva", SENHA)["token"])

    def test_sessao_expirada_desativacao_e_troca_de_senha_encerram_o_acesso(self):
        s = self.c.entrar("maria.silva", SENHA)
        self.bruto("UPDATE sessao SET expira_em = ?", (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds"))
        self.assertIsNone(self.c.sessao(s["token"]))
        s = self.c.entrar("maria.silva", SENHA)
        self.c.trocar_senha("maria.silva", "outra-senha-forte-456")
        self.assertIsNone(self.c.sessao(s["token"]))
        s = self.c.entrar("maria.silva", "outra-senha-forte-456")
        self.c.definir_ativo("maria.silva", False)
        self.assertIsNone(self.c.sessao(s["token"]))
        with self.assertRaises(K.AcessoNegado):
            self.c.entrar("maria.silva", "outra-senha-forte-456")

    def test_sair_encerra_a_sessao(self):
        s = self.c.entrar("maria.silva", SENHA)
        self.c.sair(s["token"])
        self.assertIsNone(self.c.sessao(s["token"]))


class TesteServidorAdmin(TP.Base):
    TOKEN = "credencial-tecnica-0123456789"

    def setUp(self):
        super().setUp()
        self.base_padrao()
        K.Contas(self.pasta / "contas.sqlite3").criar("maria.silva", "Maria da Silva", SENHA)
        self.servidor = criar_servidor(self.pasta, self.TOKEN, porta=0, origens_admin=[ORIGEM])
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def pedir(self, caminho, token=None, corpo=None, metodo=None, origem=None):
        pedido = urllib.request.Request(self.url + caminho, data=json.dumps(corpo).encode() if corpo is not None else None, method=metodo,
                                        headers={"Content-Type": "application/json"} if corpo is not None else {})
        if token:
            pedido.add_header("Authorization", "Bearer " + token)
        if origem:
            pedido.add_header("Origin", origem)
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def entrar(self, senha=SENHA, usuario="maria.silva"):
        return self.pedir("/api/login", corpo={"usuario": usuario, "senha": senha})

    def test_login_sessao_e_saida(self):
        status, _, corpo = self.entrar()
        self.assertEqual(status, 200)
        token = json.loads(corpo)["token"]
        status, _, corpo = self.pedir("/api/sessao", token)
        self.assertEqual((status, json.loads(corpo)["nome"]), (200, "Maria da Silva"))
        self.assertEqual(self.pedir("/api/painel?escopo=pendente", token)[0], 200)
        self.assertTrue(json.loads(self.pedir("/api/painel?escopo=pendente", token)[2])["linhas"])
        self.assertEqual(self.pedir("/api/logout", token, corpo={})[0], 200)
        self.assertEqual(self.pedir("/api/sessao", token)[0], 401)
        self.assertEqual(self.pedir("/api/conflitos", token)[0], 403)
        acoes = [r[0] for r in self.banco.con.execute("SELECT acao FROM auditoria WHERE alvo_tipo = 'sessao' ORDER BY id")]
        self.assertEqual(acoes, ["ENTRAR", "SAIR"])

    def test_senha_errada_e_usuario_inexistente_tem_a_mesma_resposta(self):
        a, b = self.entrar("errada-errada"), self.entrar(SENHA, "ninguem")
        self.assertEqual((a[0], a[2]), (b[0], b[2]))
        self.assertEqual(a[0], 401)

    def test_token_invalido_nao_da_acesso_e_publico_segue_sem_dados_individuais(self):
        self.assertEqual(self.pedir("/api/auditoria", "token-inventado")[0], 403)
        corpo = self.pedir("/api/painel?escopo=pendente", "token-inventado")[2].decode()
        self.assertEqual(json.loads(corpo)["linhas"], [])
        self.assertNotIn("PESSOA FICTICIA", corpo)

    def test_revisao_registra_a_pessoa_logada_e_ignora_o_nome_enviado(self):
        token = json.loads(self.entrar()[2])["token"]
        ato = self.ato("901/2026")["id"]
        status, _, corpo = self.pedir("/api/revisao", token, {"alvo": "ato", "id": ato, "decisao": "CONFERIR", "responsavel": "Outra Pessoa",
                                                               "justificativa": "conferido no PDF", "confirma_fonte": True, "confirma_vinculo": True})
        self.assertEqual(status, 200, corpo)
        revisores = {r[0] for r in self.banco.con.execute("SELECT revisor FROM decisao WHERE ato_id = ?", (ato,))}
        self.assertEqual(revisores, {"Maria da Silva (maria.silva)"})
        autor = self.banco.con.execute("SELECT autor FROM auditoria WHERE acao = 'CONFERIR' ORDER BY id DESC").fetchone()[0]
        self.assertEqual(autor, "Maria da Silva (maria.silva)")

    def test_credencial_tecnica_continua_valendo(self):
        self.assertEqual(self.pedir("/api/conflitos", self.TOKEN)[0], 200)

    def test_cors_so_para_a_origem_autorizada_e_so_na_api(self):
        status, cab, _ = self.pedir("/api/login", metodo="OPTIONS", origem=ORIGEM)
        self.assertEqual(status, 204)
        self.assertEqual(cab.get("Access-Control-Allow-Origin"), ORIGEM)
        self.assertIn("Authorization", cab.get("Access-Control-Allow-Headers"))
        status, cab, _ = self.pedir("/api/login", metodo="OPTIONS", origem="https://site-estranho.example")
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", cab)
        self.assertNotIn("Access-Control-Allow-Origin", self.pedir("/api/saude", origem="https://site-estranho.example")[1])
        self.assertEqual(self.pedir("/api/saude", origem=ORIGEM)[1].get("Access-Control-Allow-Origin"), ORIGEM)

    def test_corpo_invalido_no_login(self):
        self.assertEqual(self.pedir("/api/login", corpo=None, metodo="POST")[0], 415)


if __name__ == "__main__":
    unittest.main()
