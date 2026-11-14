"""Migrações do banco (Etapa 05.1): decisão pela ESTRUTURA presente, transação única, cópia de segurança.

Prepara a integração com a coleta da Etapa 05, cuja migração também foi numerada "v6" em outra linha de
desenvolvimento: um banco com user_version = 6 e esquema diferente precisa ser completado sem perda.
Os nomes `download` e `verificacao_arquivo` abaixo apenas SIMULAM tabelas de outra linha (colunas mínimas
inventadas para o teste); não reproduzem o código da Etapa 05.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.nucleo import banco as B


def _criar_ate(caminho: Path, versao: int, extras: str = "") -> None:
    con = sqlite3.connect(caminho)
    for numero, script in B._MIGRACOES:
        if numero <= versao:
            con.executescript(script)
    if extras:
        con.executescript(extras)
    con.execute(f"PRAGMA user_version = {versao}")
    con.commit()
    con.close()


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
                con = sqlite3.connect(self.caminho)
                con.execute("INSERT INTO arquivo VALUES ('sha-antigo', 10, 'x', 'agora')")
                con.commit()
                con.close()
                banco = B.Banco(self.caminho)
                try:
                    self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
                    self.assertEqual(banco.con.execute("SELECT sha256, tamanho FROM arquivo").fetchall()[0][:], ("sha-antigo", 10))
                    self.assertEqual(B.estruturas_pendentes(banco.con), {})
                finally:
                    banco.fechar()

    def test_reabrir_e_idempotente(self):
        self.abrir().fechar()
        antes = _estrutura(sqlite3.connect(self.caminho))
        banco = self.abrir()
        self.assertEqual(_estrutura(banco.con), antes)
        self.assertIsNone(banco.backup_da_migracao)                     # nada a migrar, nenhuma cópia

    def test_migracao_interrompida_no_meio_e_completada(self):
        # v5 com a coluna da v6 já criada, mas sem a versão gravada (queda entre o ALTER e o PRAGMA).
        _criar_ate(self.caminho, 5, "ALTER TABLE evento ADD COLUMN publicacoes_citadas TEXT;")
        banco = self.abrir()
        self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
        self.assertEqual(_estrutura(banco.con)["evento"].count("publicacoes_citadas"), 1)

    def test_v6_de_outra_linha_com_esquema_diferente_e_completado_sem_perda(self):
        # Mesmo número de versão (6), outra estrutura: tabelas extras e SEM a coluna de eventos desta linha.
        extras = ("CREATE TABLE download (id INTEGER PRIMARY KEY, url TEXT NOT NULL, resultado TEXT);"
                  "CREATE TABLE verificacao_arquivo (id INTEGER PRIMARY KEY, sha256 TEXT, situacao TEXT);"
                  "INSERT INTO download (url, resultado) VALUES ('https://auniao.pb.gov.br/x.pdf', 'NOVO');"
                  "INSERT INTO verificacao_arquivo (sha256, situacao) VALUES ('abc', 'QUARENTENA');")
        _criar_ate(self.caminho, 5, extras)
        con = sqlite3.connect(self.caminho)
        con.execute("PRAGMA user_version = 6")
        con.commit()
        con.close()
        banco = self.abrir()
        estrutura = _estrutura(banco.con)
        self.assertIn("publicacoes_citadas", estrutura["evento"])                  # completado
        self.assertEqual(estrutura["download"], ["id", "url", "resultado"])          # estrutura alheia intacta
        self.assertEqual(banco.con.execute("SELECT url, resultado FROM download").fetchone()[:], ("https://auniao.pb.gov.br/x.pdf", "NOVO"))
        self.assertEqual(banco.con.execute("SELECT situacao FROM verificacao_arquivo").fetchone()[0], "QUARENTENA")
        self.assertIsNotNone(banco.backup_da_migracao)

    def test_falha_no_meio_desfaz_tudo_e_mantem_a_copia(self):
        _criar_ate(self.caminho, 4)
        antes = _estrutura(sqlite3.connect(self.caminho))
        original = B._MIGRACOES
        quebrada = original[:5] + ((6, B._ESQUEMA_V6 + ";\nALTER TABLE tabela_inexistente ADD COLUMN y TEXT;"),)  # 2ª instrução falha
        with mock.patch.object(B, "_MIGRACOES", quebrada):
            with self.assertRaises(sqlite3.OperationalError):
                B.Banco(self.caminho)
        con = sqlite3.connect(self.caminho)
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)        # nada foi gravado pela metade
            self.assertEqual(_estrutura(con), antes)
        finally:
            con.close()
        self.assertTrue(Path(f"{self.caminho}.antes-v{B.VERSAO_ESQUEMA}.bak").exists())

    def test_copia_de_seguranca_restaura_o_estado_anterior(self):
        _criar_ate(self.caminho, 5)
        con = sqlite3.connect(self.caminho)
        con.execute("INSERT INTO arquivo VALUES ('sha-x', 1, 'x', 'agora')")
        con.commit()
        con.close()
        banco = self.abrir()
        copia = sqlite3.connect(banco.backup_da_migracao)
        try:
            self.assertEqual(copia.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(copia.execute("SELECT sha256 FROM arquivo").fetchone()[0], "sha-x")
            self.assertNotIn("publicacoes_citadas", _estrutura(copia)["evento"])
            self.assertEqual(copia.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            copia.close()

    def test_versao_mais_nova_e_recusada_sem_alterar_nada(self):
        _criar_ate(self.caminho, 6)
        con = sqlite3.connect(self.caminho)
        con.execute(f"PRAGMA user_version = {B.VERSAO_ESQUEMA + 1}")
        con.commit()
        con.close()
        with self.assertRaises(RuntimeError):
            B.Banco(self.caminho)
        self.assertFalse(Path(f"{self.caminho}.antes-v{B.VERSAO_ESQUEMA}.bak").exists())

    def test_toda_instrucao_de_migracao_tem_verificacao_estrutural(self):
        con = sqlite3.connect(":memory:")
        for _, script in B._MIGRACOES:
            for instrucao in B._instrucoes(script):
                self.assertIn(B._ja_existe(con, instrucao), (True, False))


if __name__ == "__main__":
    unittest.main()
