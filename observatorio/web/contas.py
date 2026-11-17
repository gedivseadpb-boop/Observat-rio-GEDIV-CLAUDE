"""Contas individuais da gerência: login com usuário e senha, sessões e bloqueio por tentativas.

Fica num banco SEPARADO (`contas.sqlite3`, na pasta de dados), para não mexer no esquema do banco principal.
- Senhas: scrypt (n=2^14, r=8, p=1) com sal aleatório; nunca guardadas nem registradas em texto.
- Sessões: token aleatório entregue ao navegador uma única vez; no banco fica só o SHA-256 dele. Expiram.
- Bloqueio: depois de MAX_FALHAS senhas erradas seguidas o usuário fica bloqueado por BLOQUEIO_MINUTOS.
- Respostas de erro iguais para usuário inexistente, senha errada, bloqueado ou desativado (não revelam qual).
Biblioteca padrão apenas.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

USUARIO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
MIN_SENHA = 10
MAX_FALHAS = 5
BLOQUEIO_MINUTOS = 15
DURACAO_SESSAO_HORAS = 8
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_SAL_FICTICIO = b"\0" * 16

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuario (
    usuario        TEXT PRIMARY KEY,
    nome           TEXT NOT NULL,
    sal            BLOB NOT NULL,
    senha_hash     BLOB NOT NULL,
    ativo          INTEGER NOT NULL DEFAULT 1,
    falhas         INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate  TEXT,
    criado_em      TEXT NOT NULL,
    ultimo_acesso  TEXT
);
CREATE TABLE IF NOT EXISTS sessao (
    token_hash  TEXT PRIMARY KEY,
    usuario     TEXT NOT NULL REFERENCES usuario(usuario),
    criada_em   TEXT NOT NULL,
    expira_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessao_usuario ON sessao (usuario);
"""


class AcessoNegado(Exception):
    """Login recusado. A mensagem é sempre a mesma, para não indicar se o usuário existe."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _hash_senha(senha: str, sal: bytes) -> bytes:
    return hashlib.scrypt(senha.encode("utf-8"), salt=sal, **_SCRYPT)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Contas:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        with self._conexao() as con:
            con.executescript(ESQUEMA)

    @contextlib.contextmanager
    def _conexao(self):
        con = sqlite3.connect(self.caminho, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    # --- administração (linha de comando) ---------------------------------
    def criar(self, usuario: str, nome: str, senha: str) -> None:
        usuario = usuario.strip().lower()
        if not USUARIO.match(usuario):
            raise ValueError("usuário: 3 a 40 caracteres, letras minúsculas, números, ponto, hífen ou sublinhado")
        nome = " ".join(nome.split())
        if not 3 <= len(nome) <= 120:
            raise ValueError("informe o nome da pessoa (3 a 120 caracteres)")
        self._validar_senha(senha, usuario)
        sal = secrets.token_bytes(16)
        with self._conexao() as con:
            if con.execute("SELECT 1 FROM usuario WHERE usuario = ?", (usuario,)).fetchone():
                raise ValueError("esse usuário já existe")
            con.execute("INSERT INTO usuario (usuario, nome, sal, senha_hash, criado_em) VALUES (?,?,?,?,?)",
                        (usuario, nome, sal, _hash_senha(senha, sal), _agora().isoformat(timespec="seconds")))

    def trocar_senha(self, usuario: str, senha: str) -> None:
        self._validar_senha(senha, usuario)
        sal = secrets.token_bytes(16)
        with self._conexao() as con:
            alterados = con.execute("UPDATE usuario SET sal = ?, senha_hash = ?, falhas = 0, bloqueado_ate = NULL WHERE usuario = ?",
                                    (sal, _hash_senha(senha, sal), usuario)).rowcount
            if not alterados:
                raise ValueError("usuário não encontrado")
            con.execute("DELETE FROM sessao WHERE usuario = ?", (usuario,))       # senha nova encerra sessões abertas

    def definir_ativo(self, usuario: str, ativo: bool) -> None:
        with self._conexao() as con:
            if not con.execute("UPDATE usuario SET ativo = ? WHERE usuario = ?", (int(ativo), usuario)).rowcount:
                raise ValueError("usuário não encontrado")
            if not ativo:
                con.execute("DELETE FROM sessao WHERE usuario = ?", (usuario,))

    def listar(self) -> list[dict]:
        with self._conexao() as con:
            return [dict(r) for r in con.execute("SELECT usuario, nome, ativo, bloqueado_ate, criado_em, ultimo_acesso FROM usuario ORDER BY usuario")]

    @staticmethod
    def _validar_senha(senha: str, usuario: str) -> None:
        if len(senha) < MIN_SENHA:
            raise ValueError(f"a senha precisa ter pelo menos {MIN_SENHA} caracteres")
        if usuario and usuario.lower() in senha.lower():
            raise ValueError("a senha não pode conter o nome de usuário")

    # --- login e sessão ----------------------------------------------------
    def entrar(self, usuario: str, senha: str) -> dict:
        usuario = (usuario or "").strip().lower()
        agora = _agora()
        resultado = None
        # A recusa só é levantada DEPOIS que a transação grava o contador de falhas (levantar dentro do bloco
        # desfaria a gravação e o bloqueio nunca aconteceria).
        with self._conexao() as con:
            u = con.execute("SELECT * FROM usuario WHERE usuario = ?", (usuario,)).fetchone() if USUARIO.match(usuario) else None
            calculado = _hash_senha(senha or "", u["sal"] if u else _SAL_FICTICIO)    # mesmo custo com ou sem usuário
            bloqueado = bool(u and u["bloqueado_ate"] and datetime.fromisoformat(u["bloqueado_ate"]) > agora)
            if u is not None and u["ativo"] and not bloqueado:
                if hmac.compare_digest(calculado, u["senha_hash"]):
                    token = secrets.token_urlsafe(32)
                    expira = agora + timedelta(hours=DURACAO_SESSAO_HORAS)
                    con.execute("DELETE FROM sessao WHERE expira_em <= ?", (agora.isoformat(timespec="seconds"),))
                    con.execute("INSERT INTO sessao VALUES (?,?,?,?)", (_hash_token(token), usuario, agora.isoformat(timespec="seconds"),
                                                                         expira.isoformat(timespec="seconds")))
                    con.execute("UPDATE usuario SET falhas = 0, bloqueado_ate = NULL, ultimo_acesso = ? WHERE usuario = ?",
                                (agora.isoformat(timespec="seconds"), usuario))
                    resultado = {"token": token, "usuario": usuario, "nome": u["nome"], "expira_em": expira.isoformat(timespec="seconds")}
                else:
                    falhas = u["falhas"] + 1
                    bloqueio = (agora + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat(timespec="seconds") if falhas >= MAX_FALHAS else None
                    con.execute("UPDATE usuario SET falhas = ?, bloqueado_ate = ? WHERE usuario = ?",
                                (0 if bloqueio else falhas, bloqueio, usuario))
        if resultado is None:
            raise AcessoNegado()
        return resultado

    def sessao(self, token: str) -> dict | None:
        if not token or len(token) > 200:
            return None
        with self._conexao() as con:
            s = con.execute("SELECT s.usuario, s.expira_em, u.nome, u.ativo FROM sessao s JOIN usuario u ON u.usuario = s.usuario "
                            "WHERE s.token_hash = ?", (_hash_token(token),)).fetchone()
        if s is None or not s["ativo"] or datetime.fromisoformat(s["expira_em"]) <= _agora():
            return None
        return {"usuario": s["usuario"], "nome": s["nome"], "expira_em": s["expira_em"]}

    def sair(self, token: str) -> None:
        with self._conexao() as con:
            con.execute("DELETE FROM sessao WHERE token_hash = ?", (_hash_token(token or ""),))
