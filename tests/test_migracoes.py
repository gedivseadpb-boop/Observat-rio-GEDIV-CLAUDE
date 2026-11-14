"""Migrações do banco (Etapa 05.1): decisão pela ESTRUTURA presente, transação única, cópia de segurança.

Integração 05.1: a migração da coleta (Etapa 05) foi numerada "v6" na sua linha de desenvolvimento, como a
de eventos da Etapa 04. Na integração ela é a v7; um banco marcado v6 por qualquer das duas linhas é levado à
v7 pela estrutura efetivamente presente, sem perda. Os testes usam o esquema REAL das duas linhas.
"""
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.nucleo import banco as B


def _conectar(caminho):
    """Conexão que SEMPRE é fechada ao sair do bloco, mesmo se uma verificação falhar no meio.
    (`with sqlite3.connect(...)` sozinho controla a transação e NÃO fecha a conexão.)"""
    return contextlib.closing(sqlite3.connect(caminho))


def _criar_ate(caminho: Path, versao: int, extras: str = "") -> None:
    with _conectar(caminho) as con:
        for numero, script in B._MIGRACOES:
            if numero <= versao:
                con.executescript(script)
        if extras:
            con.executescript(extras)
        con.execute(f"PRAGMA user_version = {versao}")
        con.commit()


def _estrutura_do_arquivo(caminho) -> dict:
    with _conectar(caminho) as con:
        return _estrutura(con)


def _executar(caminho, *instrucoes) -> None:
    with _conectar(caminho) as con:
        for instrucao in instrucoes:
            con.execute(instrucao)
        con.commit()


def _estrutura(con) -> dict:
    tabelas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    return {t: [c[1] for c in con.execute(f"PRAGMA table_info({t})")] for t in tabelas}


class TesteMigracoes(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = Path(self.pasta.name) / "observatorio.sqlite3"

    def abrir(self, **k):
        banco = B.Banco(self.caminho, **k)
        self.addCleanup(banco.fechar)
        return banco

    def test_banco_novo_tem_toda_a_estrutura_e_a_versao_atual(self):
        banco = self.abrir()
        self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
        self.assertEqual(B.estruturas_pendentes(banco.con), {})
        self.assertIn("publicacoes_citadas", _estrutura(banco.con)["evento"])
        self.assertIsNone(banco.backup_da_migracao)                     # nada a proteger num banco novo

    def test_migracao_de_versoes_antigas_preserva_dados(self):
        for versao in (1, 4, 5):
            with self.subTest(versao=versao):
                self.caminho.unlink(missing_ok=True)
                _criar_ate(self.caminho, versao)
                _executar(self.caminho, "INSERT INTO arquivo VALUES ('sha-antigo', 10, 'x', 'agora')")
                banco = B.Banco(self.caminho)
                try:
                    self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
                    self.assertEqual(banco.con.execute("SELECT sha256, tamanho FROM arquivo").fetchall()[0][:], ("sha-antigo", 10))
                    self.assertEqual(B.estruturas_pendentes(banco.con), {})
                finally:
                    banco.fechar()

    def test_reabrir_e_idempotente(self):
        self.abrir().fechar()
        antes = _estrutura_do_arquivo(self.caminho)
        banco = self.abrir()
        self.assertEqual(_estrutura(banco.con), antes)
        self.assertIsNone(banco.backup_da_migracao)                     # nada a migrar, nenhuma cópia

    def test_migracao_interrompida_no_meio_e_completada(self):
        # v5 com a coluna da v6 já criada, mas sem a versão gravada (queda entre o ALTER e o PRAGMA).
        _criar_ate(self.caminho, 5, "ALTER TABLE evento ADD COLUMN publicacoes_citadas TEXT;")
        banco = self.abrir()
        self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
        self.assertEqual(_estrutura(banco.con)["evento"].count("publicacoes_citadas"), 1)

    def _v6_da_etapa05(self):
        """Banco como a linha da Etapa 05 o deixava: versões 1–5, as tabelas de download (hoje v7) e user_version 6,
        SEM a coluna de eventos da v6 da Etapa 04. Com um download e uma verificação registrados."""
        _criar_ate(self.caminho, 5, B._ESQUEMA_V7)
        _executar(self.caminho, "PRAGMA user_version = 6",
                  "INSERT INTO publicacao (id, fonte, url, tipo, estado, descoberta_em, atualizada_em) "
                  "VALUES (1, 'auniao', 'https://auniao.pb.gov.br/x.pdf', 'normal', 'BAIXADA', 'x', 'x')",
                  "INSERT INTO arquivo VALUES ('sha-x', 10, 'x', 'agora')",
                  "INSERT INTO verificacao_arquivo VALUES ('sha-x', 3, 'OK', 'agora')",
                  "INSERT INTO download (publicacao_id, url_pedida, transporte, resultado, versao_coletor, iniciado_em) "
                  "VALUES (1, 'https://auniao.pb.gov.br/x.pdf', 'direto', 'NOVO', '0.5', 'agora')")

    def test_v6_da_etapa05_vira_v7_ganhando_so_a_coluna_de_eventos(self):
        self._v6_da_etapa05()
        antes = _estrutura_do_arquivo(self.caminho)
        banco = self.abrir()
        depois = _estrutura(banco.con)
        self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
        # Da v7 da Etapa 05, o evento ganha só a coluna da v6 da Etapa 04 (as colunas novas da v8 vêm depois dela).
        self.assertEqual(depois["evento"][:len(antes["evento"]) + 1], antes["evento"] + ["publicacoes_citadas"])
        # Etapa 05.3.3 (v8): só ACRÉSCIMOS. Nenhuma tabela ou coluna anterior some, muda de nome ou de posição; as
        # tabelas novas são exatamente as da v8.
        for tabela, colunas in antes.items():
            if tabela != "evento":
                self.assertEqual(depois[tabela][:len(colunas)], colunas, tabela)
        self.assertEqual(set(depois) - set(antes), {"tentativa_leitura", "correcao", "conflito"})
        self.assertEqual(banco.con.execute("SELECT resultado, versao_coletor FROM download").fetchone()[:], ("NOVO", "0.5"))
        self.assertEqual(banco.con.execute("SELECT integridade FROM verificacao_arquivo").fetchone()[0], "OK")
        self.assertEqual(B.estruturas_pendentes(banco.con), {})

    def test_v6_da_etapa04_vira_v7_ganhando_as_tabelas_de_download(self):
        _criar_ate(self.caminho, 6)
        _executar(self.caminho, "INSERT INTO arquivo VALUES ('sha-y', 10, 'x', 'agora')")
        banco = self.abrir()
        estrutura = _estrutura(banco.con)
        self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
        self.assertIn("publicacoes_citadas", estrutura["evento"])
        self.assertIn("tentativas_rede", estrutura["download"])
        self.assertIn("integridade", estrutura["verificacao_arquivo"])
        self.assertEqual(banco.con.execute("SELECT sha256 FROM arquivo").fetchone()[0], "sha-y")

    def test_tabela_homonima_incompativel_falha_sem_alterar_nada(self):
        # Uma tabela "download" com outra estrutura não é "completada" às cegas: a migração falha inteira.
        _criar_ate(self.caminho, 6, "CREATE TABLE download (id INTEGER PRIMARY KEY, url TEXT);")
        antes = _estrutura_do_arquivo(self.caminho)
        with self.assertRaises(sqlite3.OperationalError):
            B.Banco(self.caminho)
        with _conectar(self.caminho) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertEqual(_estrutura(con), antes)

    def test_falha_no_meio_desfaz_tudo_e_mantem_a_copia(self):
        _criar_ate(self.caminho, 4)
        antes = _estrutura_do_arquivo(self.caminho)
        original = B._MIGRACOES
        quebrada = original[:5] + ((6, B._ESQUEMA_V6 + ";\nALTER TABLE tabela_inexistente ADD COLUMN y TEXT;"),)  # 2ª instrução falha
        with mock.patch.object(B, "_MIGRACOES", quebrada):
            with self.assertRaises(sqlite3.OperationalError):
                B.Banco(self.caminho)
        with _conectar(self.caminho) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)        # nada foi gravado pela metade
            self.assertEqual(_estrutura(con), antes)
        self.assertTrue(Path(f"{self.caminho}.antes-v{B.VERSAO_ESQUEMA}.bak").exists())

    def test_copia_de_seguranca_restaura_o_estado_anterior(self):
        _criar_ate(self.caminho, 5)
        _executar(self.caminho, "INSERT INTO arquivo VALUES ('sha-x', 1, 'x', 'agora')")
        banco = self.abrir()
        with _conectar(banco.backup_da_migracao) as copia:
            self.assertEqual(copia.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(copia.execute("SELECT sha256 FROM arquivo").fetchone()[0], "sha-x")
            self.assertNotIn("publicacoes_citadas", _estrutura(copia)["evento"])
            self.assertEqual(copia.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_versao_mais_nova_e_recusada_sem_alterar_nada(self):
        _criar_ate(self.caminho, 6)
        _executar(self.caminho, f"PRAGMA user_version = {B.VERSAO_ESQUEMA + 1}")
        with self.assertRaises(RuntimeError):
            B.Banco(self.caminho)
        self.assertFalse(Path(f"{self.caminho}.antes-v{B.VERSAO_ESQUEMA}.bak").exists())

    def test_toda_instrucao_de_migracao_tem_verificacao_estrutural(self):
        with _conectar(":memory:") as con:
            for _, script in B._MIGRACOES:
                for instrucao in B._instrucoes(script):
                    self.assertIn(B._ja_existe(con, instrucao), (True, False))


if __name__ == "__main__":
    unittest.main()
