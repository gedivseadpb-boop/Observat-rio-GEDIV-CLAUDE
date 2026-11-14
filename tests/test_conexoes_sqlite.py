"""Toda conexão aberta pelo Banco é fechada, no sucesso e na falha (CI de 14/11/2026: 5 erros por job Windows,
"arquivo em uso por outro processo" ao apagar o SQLite temporário).

No Linux um arquivo aberto pode ser apagado, então o defeito não aparece sozinho: estes testes registram cada
conexão criada e verificam que ela está FECHADA ao fim de cada cenário — inclusive depois de exceção — e, por fim,
renomeiam e apagam o arquivo (o que falha no Windows enquanto houver conexão aberta).
"""
import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observatorio.nucleo import banco as B
from tests.test_migracoes import _criar_ate, _executar

_conectar_original = sqlite3.connect


class ConexaoComRollbackQuebrado(sqlite3.Connection):
    def execute(self, sql, *a):
        if sql.strip().upper() == "ROLLBACK":
            raise sqlite3.OperationalError("falha simulada no ROLLBACK")
        return super().execute(sql, *a)


def fechada(con: sqlite3.Connection) -> bool:
    try:
        con.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


class TesteConexoes(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)            # sem ignore_cleanup_errors: um arquivo preso derruba o teste no Windows
        self.caminho = Path(pasta.name) / "observatorio.sqlite3"
        self.abertas: list[sqlite3.Connection] = []

    @contextlib.contextmanager
    def registrando(self, factory=None):
        def conectar(*a, **k):
            if factory is not None:
                k["factory"] = factory
            con = _conectar_original(*a, **k)
            self.abertas.append(con)
            return con
        with mock.patch.object(B.sqlite3, "connect", conectar):
            yield

    def assertTudoFechadoEArquivoLivre(self):
        self.assertTrue(self.abertas, "nenhuma conexão foi registrada")
        self.assertEqual([fechada(c) for c in self.abertas], [True] * len(self.abertas))
        if self.caminho.exists():
            movido = self.caminho.with_suffix(".movido")
            os.replace(self.caminho, movido)       # Windows: PermissionError se ainda houver conexão aberta
            movido.unlink()
        for copia in self.caminho.parent.glob("*.bak"):
            copia.unlink()

    def test_inicializacao_bem_sucedida_e_fechar(self):
        with self.registrando():
            banco = B.Banco(self.caminho)
        banco.fechar()
        banco.fechar()                             # fechar de novo não é erro
        self.assertTudoFechadoEArquivoLivre()

    def test_bloco_with_fecha_mesmo_com_excecao_dentro(self):
        with self.registrando(), self.assertRaises(ZeroDivisionError):
            with B.Banco(self.caminho) as banco:
                self.assertEqual(banco.con.execute("PRAGMA user_version").fetchone()[0], B.VERSAO_ESQUEMA)
                1 / 0
        self.assertTudoFechadoEArquivoLivre()

    def test_reabertura_idempotente(self):
        with self.registrando():
            for _ in range(3):
                with B.Banco(self.caminho) as banco:
                    self.assertIsNone(banco.backup_da_migracao if _ else None)
        self.assertEqual(len(self.abertas), 3)
        self.assertTudoFechadoEArquivoLivre()

    def test_falha_durante_a_migracao_desfaz_fecha_e_preserva_o_erro(self):
        _criar_ate(self.caminho, 4)
        quebrada = B._MIGRACOES[:5] + ((6, B._ESQUEMA_V6 + ";\nALTER TABLE tabela_inexistente ADD COLUMN y TEXT;"),)
        with self.registrando(), mock.patch.object(B, "_MIGRACOES", quebrada):
            with self.assertRaisesRegex(sqlite3.OperationalError, "tabela_inexistente"):
                B.Banco(self.caminho)
        with contextlib.closing(_conectar_original(self.caminho)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)            # rollback: nada pela metade
        self.assertTudoFechadoEArquivoLivre()

    def test_falha_tambem_no_rollback_nao_esconde_o_erro_original(self):
        _criar_ate(self.caminho, 4)
        quebrada = B._MIGRACOES[:5] + ((6, B._ESQUEMA_V6 + ";\nALTER TABLE tabela_inexistente ADD COLUMN y TEXT;"),)
        with self.registrando(ConexaoComRollbackQuebrado), mock.patch.object(B, "_MIGRACOES", quebrada):
            with self.assertRaisesRegex(sqlite3.OperationalError, "tabela_inexistente"):     # não "falha simulada no ROLLBACK"
                B.Banco(self.caminho)
        with contextlib.closing(_conectar_original(self.caminho)) as con:
            # A transação não confirmada é descartada ao fechar a conexão.
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)
        self.assertTudoFechadoEArquivoLivre()

    def test_banco_de_versao_mais_nova(self):
        _criar_ate(self.caminho, 6)
        _executar(self.caminho, f"PRAGMA user_version = {B.VERSAO_ESQUEMA + 1}")
        with self.registrando(), self.assertRaisesRegex(RuntimeError, "mais novo"):
            B.Banco(self.caminho)
        self.assertTudoFechadoEArquivoLivre()

    def test_estrutura_incompativel(self):
        _criar_ate(self.caminho, 6, "CREATE TABLE download (id INTEGER PRIMARY KEY, url TEXT);")
        with self.registrando(), self.assertRaises(sqlite3.OperationalError):
            B.Banco(self.caminho)
        self.assertTudoFechadoEArquivoLivre()

    def test_excecao_qualquer_na_inicializacao_fecha_e_propaga(self):
        for erro in (RuntimeError("falha simulada"), KeyboardInterrupt()):
            with self.subTest(erro=type(erro).__name__):
                self.abertas.clear()
                with self.registrando(), mock.patch.object(B.Banco, "_migrar", side_effect=erro):
                    with self.assertRaises(type(erro)):
                        B.Banco(self.caminho)
                self.assertTudoFechadoEArquivoLivre()


if __name__ == "__main__":
    unittest.main()
