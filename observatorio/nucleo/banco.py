"""Registro persistente da coleta (SQLite).

Tabelas desta etapa:
- arquivo     um PDF único, identificado pelo SHA-256 do conteúdo;
- publicacao  um endereço em que uma fonte oferece um documento;
- versao      histórico dos conteúdos já observados em cada endereço;
- varredura   resultado da leitura da listagem mensal de cada fonte;
- execucao    registro de cada rodada do robô.

O mesmo arquivo oferecido por duas fontes gera duas linhas em `publicacao`
e uma única linha em `arquivo`: não é contado como dois documentos.
O SQL usado é compatível com uma futura migração para PostgreSQL.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSAO_ESQUEMA = 1

DESCOBERTA = "DESCOBERTA"
BAIXADA = "BAIXADA"
FALHA_DOWNLOAD = "FALHA_DOWNLOAD"
INVALIDA = "INVALIDA"

_ESQUEMA = """
CREATE TABLE arquivo (
    sha256      TEXT PRIMARY KEY,
    tamanho     INTEGER NOT NULL,
    caminho     TEXT NOT NULL,
    guardado_em TEXT NOT NULL
);
CREATE TABLE publicacao (
    id              INTEGER PRIMARY KEY,
    fonte           TEXT NOT NULL,
    url             TEXT NOT NULL,
    data_publicacao TEXT,
    tipo            TEXT NOT NULL,
    ordem           INTEGER NOT NULL DEFAULT 0,
    rotulo          TEXT,
    estado          TEXT NOT NULL,
    sha256          TEXT REFERENCES arquivo(sha256),
    tentativas      INTEGER NOT NULL DEFAULT 0,
    ultimo_erro     TEXT,
    descoberta_em   TEXT NOT NULL,
    atualizada_em   TEXT NOT NULL,
    UNIQUE (fonte, url)
);
CREATE INDEX publicacao_data ON publicacao (data_publicacao);
CREATE TABLE versao (
    id            INTEGER PRIMARY KEY,
    publicacao_id INTEGER NOT NULL REFERENCES publicacao(id),
    sha256        TEXT NOT NULL REFERENCES arquivo(sha256),
    observada_em  TEXT NOT NULL,
    UNIQUE (publicacao_id, sha256)
);
CREATE TABLE varredura (
    fonte        TEXT NOT NULL,
    ano          INTEGER NOT NULL,
    mes          INTEGER NOT NULL,
    realizada_em TEXT NOT NULL,
    itens        INTEGER,
    erro         TEXT,
    PRIMARY KEY (fonte, ano, mes)
);
CREATE TABLE execucao (
    id           INTEGER PRIMARY KEY,
    comando      TEXT NOT NULL,
    iniciada_em  TEXT NOT NULL,
    concluida_em TEXT,
    resumo       TEXT
);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: str | Path):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(caminho))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        versao = self.con.execute("PRAGMA user_version").fetchone()[0]
        if versao == 0:
            with self.con:
                self.con.executescript(_ESQUEMA)
                self.con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
        elif versao != VERSAO_ESQUEMA:
            raise RuntimeError(f"esquema {versao} não suportado (esperado {VERSAO_ESQUEMA})")

    def fechar(self) -> None:
        self.con.close()

    # --- execuções -------------------------------------------------------
    def iniciar_execucao(self, comando: str) -> int:
        with self.con:
            return self.con.execute(
                "INSERT INTO execucao (comando, iniciada_em) VALUES (?, ?)", (comando, agora())
            ).lastrowid

    def concluir_execucao(self, execucao_id: int, resumo: dict) -> None:
        with self.con:
            self.con.execute(
                "UPDATE execucao SET concluida_em = ?, resumo = ? WHERE id = ?",
                (agora(), json.dumps(resumo, ensure_ascii=False), execucao_id),
            )

    def ultima_execucao(self):
        return self.con.execute("SELECT * FROM execucao ORDER BY id DESC LIMIT 1").fetchone()

    # --- varreduras ------------------------------------------------------
    def registrar_varredura(self, fonte: str, ano: int, mes: int, itens: int | None, erro: str | None) -> None:
        with self.con:
            self.con.execute(
                "INSERT INTO varredura (fonte, ano, mes, realizada_em, itens, erro) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT (fonte, ano, mes) DO UPDATE SET realizada_em = excluded.realizada_em, "
                "itens = excluded.itens, erro = excluded.erro",
                (fonte, ano, mes, agora(), itens, erro),
            )

    def varreduras(self):
        return self.con.execute("SELECT * FROM varredura").fetchall()

    # --- publicações -----------------------------------------------------
    def registrar_descoberta(self, fonte, url, data_publicacao, tipo, ordem, rotulo) -> bool:
        """Inclui a publicação se ainda não existir. Devolve True quando é nova."""
        momento = agora()
        with self.con:
            cursor = self.con.execute(
                "INSERT INTO publicacao (fonte, url, data_publicacao, tipo, ordem, rotulo, estado, descoberta_em, atualizada_em) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (fonte, url) DO NOTHING",
                (fonte, url, data_publicacao, tipo, ordem, rotulo, DESCOBERTA, momento, momento),
            )
        return cursor.rowcount == 1

    def publicacao(self, fonte: str, url: str):
        return self.con.execute("SELECT * FROM publicacao WHERE fonte = ? AND url = ?", (fonte, url)).fetchone()

    def publicacoes(self, fonte: str | None = None, estados: tuple[str, ...] | None = None):
        sql, parametros = "SELECT * FROM publicacao WHERE 1=1", []
        if fonte:
            sql += " AND fonte = ?"
            parametros.append(fonte)
        if estados:
            sql += f" AND estado IN ({','.join('?' * len(estados))})"
            parametros += list(estados)
        return self.con.execute(sql + " ORDER BY data_publicacao, ordem, id", parametros).fetchall()

    def registrar_falha(self, publicacao_id: int, estado: str, erro: str) -> None:
        with self.con:
            self.con.execute(
                "UPDATE publicacao SET estado = ?, ultimo_erro = ?, tentativas = tentativas + 1, atualizada_em = ? WHERE id = ?",
                (estado, erro, agora(), publicacao_id),
            )

    def registrar_arquivo(self, publicacao_id: int, sha256: str, tamanho: int, caminho: str) -> str:
        """Associa o arquivo à publicação preservando o histórico.

        Devolve NOVO, IGUAL (mesmo conteúdo já associado) ou ALTERADO
        (o endereço passou a oferecer outro conteúdo; a versão anterior é mantida).
        """
        momento = agora()
        with self.con:
            self.con.execute(
                "INSERT INTO arquivo (sha256, tamanho, caminho, guardado_em) VALUES (?,?,?,?) ON CONFLICT (sha256) DO NOTHING",
                (sha256, tamanho, caminho, momento),
            )
            anterior = self.con.execute("SELECT sha256 FROM publicacao WHERE id = ?", (publicacao_id,)).fetchone()[0]
            self.con.execute(
                "INSERT INTO versao (publicacao_id, sha256, observada_em) VALUES (?,?,?) ON CONFLICT (publicacao_id, sha256) DO NOTHING",
                (publicacao_id, sha256, momento),
            )
            self.con.execute(
                "UPDATE publicacao SET estado = ?, sha256 = ?, ultimo_erro = NULL, tentativas = tentativas + 1, atualizada_em = ? WHERE id = ?",
                (BAIXADA, sha256, momento, publicacao_id),
            )
        if anterior is None:
            return "NOVO"
        return "IGUAL" if anterior == sha256 else "ALTERADO"

    def versoes(self, publicacao_id: int):
        return self.con.execute("SELECT * FROM versao WHERE publicacao_id = ? ORDER BY id", (publicacao_id,)).fetchall()

    def arquivos(self):
        return self.con.execute("SELECT * FROM arquivo ORDER BY sha256").fetchall()
