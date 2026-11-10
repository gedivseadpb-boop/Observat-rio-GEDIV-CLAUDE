"""Registro persistente da coleta (SQLite).

Tabelas desta etapa:
- arquivo     um PDF único, identificado pelo SHA-256 do conteúdo;
- publicacao  um endereço em que uma fonte oferece um documento;
- versao      histórico dos conteúdos já observados em cada endereço;
- varredura   resultado da leitura da listagem mensal de cada fonte;
- execucao    registro de cada rodada do robô;
- lote        cada lote de downloads (piloto ou histórico) e seu desfecho;
- lote_item   resultado de cada publicação tratada em um lote;
- leitura     situação da leitura de cada arquivo do acervo;
- pagina      texto de cada página lida (fica somente no banco local).

O mesmo arquivo oferecido por duas fontes gera duas linhas em `publicacao`
e uma única linha em `arquivo`: não é contado como dois documentos.
O SQL usado é compatível com uma futura migração para PostgreSQL.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSAO_ESQUEMA = 3

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

# Acrescentado na versão 2 do esquema. Bancos da versão 1 são atualizados sem perda de dados.
_ESQUEMA_V2 = """
CREATE TABLE lote (
    id           INTEGER PRIMARY KEY,
    fonte        TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    estado       TEXT NOT NULL,
    aprovado     INTEGER,
    parametros   TEXT NOT NULL,
    iniciado_em  TEXT NOT NULL,
    concluido_em TEXT,
    observacao   TEXT
);
CREATE TABLE lote_item (
    id            INTEGER PRIMARY KEY,
    lote_id       INTEGER NOT NULL REFERENCES lote(id),
    publicacao_id INTEGER NOT NULL REFERENCES publicacao(id),
    resultado     TEXT NOT NULL,
    sha256        TEXT,
    tamanho       INTEGER,
    segundos      REAL,
    erro          TEXT,
    registrado_em TEXT NOT NULL
);
CREATE INDEX lote_item_lote ON lote_item (lote_id);
CREATE TABLE leitura (
    sha256        TEXT PRIMARY KEY REFERENCES arquivo(sha256),
    situacao      TEXT NOT NULL,
    versao_leitor TEXT NOT NULL,
    paginas       INTEGER,
    paginas_sem_texto INTEGER,
    numero_edicao TEXT,
    data_edicao   TEXT,
    erro          TEXT,
    concluida_em  TEXT NOT NULL
);
CREATE TABLE pagina (
    sha256  TEXT NOT NULL REFERENCES arquivo(sha256),
    numero  INTEGER NOT NULL,
    metodo  TEXT NOT NULL,
    colunas INTEGER NOT NULL,
    texto   TEXT NOT NULL,
    PRIMARY KEY (sha256, numero)
);
"""

# Versão 3: qualidade e rastreabilidade da leitura.
_ESQUEMA_V3 = """
ALTER TABLE pagina ADD COLUMN qualidade TEXT NOT NULL DEFAULT 'OK';
ALTER TABLE pagina ADD COLUMN confianca REAL;
ALTER TABLE pagina ADD COLUMN palavras INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pagina ADD COLUMN texto_sha256 TEXT;
ALTER TABLE leitura ADD COLUMN paginas_com_pendencia INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leitura ADD COLUMN inconsistencias TEXT;
"""

PENDENTES = (DESCOBERTA, FALHA_DOWNLOAD, INVALIDA)


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
        if versao > VERSAO_ESQUEMA:
            raise RuntimeError(f"esquema {versao} é mais novo que este programa ({VERSAO_ESQUEMA})")
        for numero, script in ((1, _ESQUEMA), (2, _ESQUEMA_V2), (3, _ESQUEMA_V3)):
            if versao < numero:
                with self.con:
                    self.con.executescript(script)
                    self.con.execute(f"PRAGMA user_version = {numero}")

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

    # --- lotes -----------------------------------------------------------
    def pendentes(self, fonte: str, max_tentativas: int, mes: str | None = None):
        sql = (f"SELECT * FROM publicacao WHERE fonte = ? AND estado IN ({','.join('?' * len(PENDENTES))}) "
               "AND tentativas < ? AND data_publicacao IS NOT NULL")
        parametros = [fonte, *PENDENTES, max_tentativas]
        if mes:
            sql += " AND substr(data_publicacao, 1, 7) = ?"
            parametros.append(mes)
        return self.con.execute(sql + " ORDER BY data_publicacao, ordem, id", parametros).fetchall()

    def encerrar_lotes_abandonados(self) -> int:
        """Lotes que ficaram abertos por queda do programa passam a INTERROMPIDO_EXECUCAO."""
        with self.con:
            return self.con.execute(
                "UPDATE lote SET estado = 'INTERROMPIDO_EXECUCAO', concluido_em = ? WHERE concluido_em IS NULL", (agora(),)
            ).rowcount

    def abrir_lote(self, fonte: str, tipo: str, parametros: dict) -> int:
        with self.con:
            return self.con.execute(
                "INSERT INTO lote (fonte, tipo, estado, parametros, iniciado_em) VALUES (?,?,?,?,?)",
                (fonte, tipo, "ABERTO", json.dumps(parametros, ensure_ascii=False), agora()),
            ).lastrowid

    def registrar_item_lote(self, lote_id, publicacao_id, resultado, sha256, tamanho, segundos, erro) -> None:
        with self.con:
            self.con.execute(
                "INSERT INTO lote_item (lote_id, publicacao_id, resultado, sha256, tamanho, segundos, erro, registrado_em) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (lote_id, publicacao_id, resultado, sha256, tamanho, segundos, erro, agora()),
            )

    def concluir_lote(self, lote_id: int, estado: str, aprovado: bool | None, observacao: str | None) -> None:
        with self.con:
            self.con.execute(
                "UPDATE lote SET estado = ?, aprovado = ?, observacao = ?, concluido_em = ? WHERE id = ?",
                (estado, None if aprovado is None else int(aprovado), observacao, agora(), lote_id),
            )

    def lote(self, lote_id: int):
        return self.con.execute("SELECT * FROM lote WHERE id = ?", (lote_id,)).fetchone()

    def lotes(self, fonte: str | None = None):
        if fonte:
            return self.con.execute("SELECT * FROM lote WHERE fonte = ? ORDER BY id", (fonte,)).fetchall()
        return self.con.execute("SELECT * FROM lote ORDER BY id").fetchall()

    def itens_do_lote(self, lote_id: int):
        return self.con.execute("SELECT * FROM lote_item WHERE lote_id = ? ORDER BY id", (lote_id,)).fetchall()

    def piloto_aprovado(self, fonte: str) -> bool:
        return self.con.execute(
            "SELECT 1 FROM lote WHERE fonte = ? AND tipo = 'piloto' AND aprovado = 1 LIMIT 1", (fonte,)
        ).fetchone() is not None

    def progresso(self):
        """Situação por mês e por fonte. `duplicadas` = verificadas cujo conteúdo já pertence a outra publicação."""
        return self.con.execute(
            """
            SELECT substr(p.data_publicacao, 1, 7) AS mes, p.fonte,
                   COUNT(*) AS listadas,
                   SUM(p.estado = 'BAIXADA') AS verificadas,
                   SUM(p.estado = 'BAIXADA' AND EXISTS (
                       SELECT 1 FROM publicacao o WHERE o.sha256 = p.sha256 AND o.id < p.id)) AS duplicadas,
                   SUM(p.estado = 'DESCOBERTA') AS pendentes,
                   SUM(p.estado = 'FALHA_DOWNLOAD') AS falhas,
                   SUM(p.estado = 'INVALIDA') AS invalidas,
                   SUM(p.tipo <> 'normal' OR p.ordem > 0) AS suplementos_ou_adicionais
            FROM publicacao p GROUP BY mes, p.fonte ORDER BY mes, p.fonte
            """
        ).fetchall()

    # --- leitura ---------------------------------------------------------
    def arquivos_sem_leitura(self, versao_leitor: str):
        return self.con.execute(
            "SELECT a.* FROM arquivo a LEFT JOIN leitura l ON l.sha256 = a.sha256 AND l.versao_leitor = ? "
            "WHERE l.sha256 IS NULL ORDER BY a.guardado_em, a.sha256", (versao_leitor,)
        ).fetchall()

    def registrar_leitura(self, sha256, situacao, versao_leitor, paginas, numero_edicao, data_edicao, erro,
                          inconsistencias=()) -> None:
        """Grava páginas e resumo na mesma transação: ou o arquivo fica lido por inteiro, ou não fica."""
        with self.con:
            self.con.execute("DELETE FROM pagina WHERE sha256 = ?", (sha256,))
            self.con.executemany(
                "INSERT INTO pagina (sha256, numero, metodo, colunas, texto, qualidade, confianca, palavras, texto_sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [(sha256, p["numero"], p["metodo"], p["colunas"], p["texto"], p["qualidade"], p.get("confianca"),
                  p["palavras"], hashlib.sha256(p["texto"].encode("utf-8")).hexdigest()) for p in paginas],
            )
            self.con.execute(
                "INSERT INTO leitura (sha256, situacao, versao_leitor, paginas, paginas_sem_texto, numero_edicao, "
                "data_edicao, erro, concluida_em, paginas_com_pendencia, inconsistencias) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT (sha256) DO UPDATE SET situacao = excluded.situacao, versao_leitor = excluded.versao_leitor, "
                "paginas = excluded.paginas, paginas_sem_texto = excluded.paginas_sem_texto, "
                "numero_edicao = excluded.numero_edicao, data_edicao = excluded.data_edicao, erro = excluded.erro, "
                "concluida_em = excluded.concluida_em, paginas_com_pendencia = excluded.paginas_com_pendencia, "
                "inconsistencias = excluded.inconsistencias",
                (sha256, situacao, versao_leitor, len(paginas), sum(p["metodo"] != "TEXTO" for p in paginas),
                 numero_edicao, data_edicao, erro, agora(),
                 sum(p["qualidade"] not in ("OK", "VAZIA") for p in paginas),
                 json.dumps(list(inconsistencias), ensure_ascii=False)),
            )

    def origens(self, sha256: str):
        """De onde veio o arquivo: todas as publicações (fonte, endereço, data) que o ofereceram."""
        return self.con.execute(
            "SELECT DISTINCT p.fonte, p.url, p.data_publicacao, p.tipo, p.ordem FROM publicacao p "
            "LEFT JOIN versao v ON v.publicacao_id = p.id WHERE p.sha256 = ? OR v.sha256 = ? ORDER BY p.fonte, p.url",
            (sha256, sha256),
        ).fetchall()

    def arquivo(self, sha256: str):
        return self.con.execute("SELECT * FROM arquivo WHERE sha256 = ?", (sha256,)).fetchone()

    def leituras(self):
        return self.con.execute("SELECT * FROM leitura ORDER BY sha256").fetchall()

    def paginas(self, sha256: str):
        return self.con.execute("SELECT * FROM pagina WHERE sha256 = ? ORDER BY numero", (sha256,)).fetchall()
