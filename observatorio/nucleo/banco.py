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
- pagina      texto de cada página lida (fica somente no banco local);
- ato, decisao, evento, outra_publicacao, classificacao   resultado da classificação por gerência;
- auditoria   trilha de todas as decisões de revisão humana.

O mesmo arquivo oferecido por duas fontes gera duas linhas em `publicacao`
e uma única linha em `arquivo`: não é contado como dois documentos.
O SQL usado é compatível com uma futura migração para PostgreSQL.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSAO_ESQUEMA = 8

DESCOBERTA = "DESCOBERTA"
BAIXADA = "BAIXADA"
FALHA_DOWNLOAD = "FALHA_DOWNLOAD"
INVALIDA = "INVALIDA"
QUARENTENA = "QUARENTENA"  # bytes aparentemente completos, estrutura não confirmada; retidos à parte
MAX_TENTATIVAS = 5         # falhas por publicação antes de ela ficar ESGOTADA (só volta por reabertura auditada)
INTEGRIDADES_ACEITAS = frozenset({"ESTRUTURA_VERIFICADA", "ESTRUTURA_VERIFICADA_COM_ALERTA"})

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

# Versão 4: classificação por gerência, revisão humana e trilha de auditoria.
# Tudo o que a classificação grava nasce PENDENTE; só a revisão humana muda esse estado.
_ESQUEMA_V4 = """
CREATE TABLE classificacao (
    sha256        TEXT NOT NULL REFERENCES arquivo(sha256),
    gerencia      TEXT NOT NULL,
    versao_regras TEXT NOT NULL,
    atos          INTEGER NOT NULL,
    decisoes      INTEGER NOT NULL,
    eventos       INTEGER NOT NULL,
    descartados   INTEGER NOT NULL,
    pendencias    TEXT,
    concluida_em  TEXT NOT NULL,
    PRIMARY KEY (sha256, gerencia)
);
CREATE TABLE ato (
    id                TEXT PRIMARY KEY,
    gerencia          TEXT NOT NULL,
    sha256            TEXT NOT NULL REFERENCES arquivo(sha256),
    tipo              TEXT NOT NULL,
    numero            TEXT,
    sufixo            TEXT,
    pagina            INTEGER NOT NULL,
    pagina_final      INTEGER NOT NULL,
    data_publicacao   TEXT,
    data_expediente   TEXT,
    vinculo           TEXT NOT NULL,
    expressao_vinculo TEXT,
    natureza          TEXT NOT NULL,
    eixo              TEXT,
    modalidade        TEXT,
    condicao          TEXT,
    grupo             TEXT,
    grupo_expressao   TEXT,
    subcategoria      TEXT,
    resultado         TEXT NOT NULL,
    texto             TEXT NOT NULL,
    pendencias        TEXT,
    versao_regras     TEXT NOT NULL
);
CREATE INDEX ato_arquivo ON ato (sha256);
CREATE TABLE decisao (
    id            TEXT PRIMARY KEY,
    ato_id        TEXT NOT NULL REFERENCES ato(id),
    sha256        TEXT NOT NULL REFERENCES arquivo(sha256),
    pagina        INTEGER NOT NULL,
    processo      TEXT,
    servidor      TEXT,
    matricula     TEXT,
    lotacao       TEXT,
    cargo         TEXT,
    detalhe       TEXT,
    resultado     TEXT NOT NULL,
    trecho        TEXT NOT NULL,
    validacao     TEXT NOT NULL DEFAULT 'PENDENTE',
    revisor       TEXT,
    revisado_em   TEXT,
    justificativa TEXT
);
CREATE INDEX decisao_ato ON decisao (ato_id);
CREATE INDEX decisao_arquivo ON decisao (sha256);
CREATE TABLE evento (
    id                TEXT PRIMARY KEY,
    gerencia          TEXT NOT NULL,
    sha256            TEXT NOT NULL REFERENCES arquivo(sha256),
    ato_id            TEXT,
    tipo              TEXT NOT NULL,
    subtipo           TEXT,
    pagina            INTEGER NOT NULL,
    data_publicacao   TEXT,
    modificador       TEXT,
    resenhas_citadas  TEXT,
    processos_citados TEXT,
    vinculo           TEXT NOT NULL,
    texto             TEXT NOT NULL,
    ato_sugerido_id   TEXT,
    ato_original_id   TEXT,
    estado            TEXT NOT NULL DEFAULT 'PENDENTE_VINCULACAO',
    fundamento        TEXT,
    revisor           TEXT,
    revisado_em       TEXT
);
CREATE INDEX evento_arquivo ON evento (sha256);
CREATE TABLE outra_publicacao (
    id              TEXT PRIMARY KEY,
    gerencia        TEXT NOT NULL,
    sha256          TEXT NOT NULL REFERENCES arquivo(sha256),
    tipo            TEXT NOT NULL,
    pagina          INTEGER NOT NULL,
    data_publicacao TEXT,
    titulo          TEXT NOT NULL,
    vinculo         TEXT NOT NULL,
    trecho          TEXT NOT NULL
);
CREATE TABLE auditoria (
    id            INTEGER PRIMARY KEY,
    momento       TEXT NOT NULL,
    autor         TEXT NOT NULL,
    acao          TEXT NOT NULL,
    alvo_tipo     TEXT NOT NULL,
    alvo_id       TEXT NOT NULL,
    anterior      TEXT,
    posterior     TEXT,
    justificativa TEXT
);
CREATE INDEX auditoria_alvo ON auditoria (alvo_tipo, alvo_id);
"""

# Versão 5: registro PRIVADO dos atos excluídos do escopo da gerência (licença-saúde, vacância, outra gerência),
# para que não reapareçam em "Outras publicações" nem nos indicadores. Não contém linhas de servidores.
_ESQUEMA_V5 = """
CREATE TABLE fora_escopo (
    id              TEXT PRIMARY KEY,
    gerencia        TEXT NOT NULL,
    sha256          TEXT NOT NULL REFERENCES arquivo(sha256),
    tipo            TEXT NOT NULL,
    numero          TEXT,
    pagina          INTEGER NOT NULL,
    data_publicacao TEXT,
    titulo          TEXT NOT NULL,
    motivo          TEXT NOT NULL,
    expressao       TEXT NOT NULL,
    vinculo         TEXT NOT NULL,
    versao_regras   TEXT NOT NULL
);
CREATE INDEX fora_escopo_arquivo ON fora_escopo (sha256);
"""

# Versão 6: datas das edições do DOE citadas por retificações, republicações e "sem efeito" (ato original).
_ESQUEMA_V6 = """
ALTER TABLE evento ADD COLUMN publicacoes_citadas TEXT;
"""

# Versão 7 (Etapa 05, numerada v6 na linha de desenvolvimento original e renumerada na integração 05.1):
# manifesto de cada tentativa de download, com procedência completa, e o resultado da verificação estrutural
# do arquivo. Nenhuma linha anterior é alterada. Um banco marcado v6 por essa linha (com estas tabelas e sem a
# coluna de eventos da v6 da Etapa 04) é completado pela verificação estrutural de `_migrar`.
_ESQUEMA_V7 = """
CREATE TABLE verificacao_arquivo (
    sha256        TEXT PRIMARY KEY REFERENCES arquivo(sha256),
    paginas       INTEGER,
    integridade   TEXT NOT NULL,
    verificado_em TEXT NOT NULL
);
CREATE TABLE download (
    id              INTEGER PRIMARY KEY,
    publicacao_id   INTEGER NOT NULL REFERENCES publicacao(id),
    url_pedida      TEXT NOT NULL,
    url_final       TEXT,
    redirecionamentos TEXT,
    transporte      TEXT NOT NULL,
    status_http     INTEGER,
    tipo_conteudo   TEXT,
    content_length  INTEGER,
    bytes           INTEGER,
    sha256          TEXT,
    paginas         INTEGER,
    integridade     TEXT,
    resultado       TEXT NOT NULL,
    erro            TEXT,
    alertas         TEXT,
    versao_coletor  TEXT NOT NULL,
    iniciado_em     TEXT NOT NULL,
    segundos        REAL,
    tentativas_rede INTEGER
);
CREATE INDEX download_publicacao ON download (publicacao_id);
"""

PENDENTES = (DESCOBERTA, FALHA_DOWNLOAD, INVALIDA)
_COLUNAS_DOWNLOAD = frozenset({"url_pedida", "url_final", "redirecionamentos", "transporte", "status_http", "tipo_conteudo",
                               "content_length", "bytes", "sha256", "paginas", "integridade", "resultado", "erro", "alertas",
                               "versao_coletor", "iniciado_em", "segundos", "tentativas_rede"})


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- identidade lógica e comparação de leituras (Etapa 05.3.3) -------------------------------------------------
# A identidade FÍSICA de um documento é o SHA-256 do PDF; a identidade LÓGICA de um ato é o que o próprio ato publica
# (gerência, tipo, número, sufixo e natureza: original ou republicação/retificação). Uma decisão é reconhecida dentro do
# ato lógico pelo processo e, na falta dele, pela matrícula. Sem número do ato, ou sem processo e matrícula, não há
# identidade segura: nada é fundido automaticamente e a correspondência vai para conferência.
import unicodedata as _ud


def _normalizar_chave(valor) -> str:
    texto = "".join(c for c in _ud.normalize("NFKD", str(valor or "")) if not _ud.combining(c)).upper()
    return re.sub(r"[^0-9A-Z]", "", texto)


def normalizar_texto(valor) -> str:
    texto = "".join(c for c in _ud.normalize("NFKD", str(valor or "")) if not _ud.combining(c)).upper()
    return re.sub(r"\s+", " ", texto).strip()


def chave_ato(gerencia, tipo, numero, sufixo, natureza) -> str | None:
    if not _normalizar_chave(numero):
        return None
    return "|".join((_normalizar_chave(gerencia), _normalizar_chave(tipo), _normalizar_chave(numero),
                     _normalizar_chave(sufixo), _normalizar_chave(natureza)))


def chave_decisao(chave_do_ato: str | None, processo, matricula) -> str | None:
    if not chave_do_ato:
        return None
    if _normalizar_chave(processo):
        return f"{chave_do_ato}|P:{_normalizar_chave(processo)}"
    if _normalizar_chave(matricula):
        return f"{chave_do_ato}|M:{_normalizar_chave(matricula)}"
    return None


def revisao_de_paginas(paginas) -> str:
    """Identificação da REVISÃO de leitura: muda se, e somente se, o texto aceito de alguma página muda."""
    partes = sorted((int(numero), hashlib.sha256((texto or "").encode("utf-8")).hexdigest()) for numero, texto in paginas)
    return hashlib.sha256(json.dumps(partes).encode("utf-8")).hexdigest()[:24]


PRIMEIRA, NEUTRA, MELHORA, MUDANCA = "PRIMEIRA", "NEUTRA", "MELHORA", "MUDANCA"
PERDA_DE_CONTEUDO, FALHA_TECNICA = "PERDA_DE_CONTEUDO", "FALHA_TECNICA"
LEITURA_ACEITA = (PRIMEIRA, NEUTRA, MELHORA, MUDANCA)
_RUIM = lambda qualidade: qualidade not in ("OK", "VAZIA")


def comparar_leituras(anteriores, novas) -> tuple[str, dict]:
    """Compara a última leitura VÁLIDA com uma nova tentativa, página a página. Não usa contagem de palavras como
    medida de qualidade: perda de página, página que piora de qualidade ou que fica sem texto é PERDA_DE_CONTEUDO
    (a tentativa não substitui a leitura válida); texto diferente sem perda é MUDANCA (aceita e encaminhada à
    reclassificação); página que deixa de ter pendência é MELHORA; nada diferente é NEUTRA."""
    if not novas:
        return FALHA_TECNICA, {}
    if not anteriores:
        return PRIMEIRA, {}
    a = {int(p["numero"]): p for p in anteriores}
    n = {int(p["numero"]): p for p in novas}
    faltam = sorted(set(a) - set(n))
    pioraram = sorted(k for k in a if k in n and not _RUIM(a[k]["qualidade"]) and _RUIM(n[k]["qualidade"]))
    esvaziadas = sorted(k for k in a if k in n and (a[k]["texto"] or "").strip() and not (n[k]["texto"] or "").strip())
    if faltam or pioraram or esvaziadas:
        return PERDA_DE_CONTEUDO, {"paginas_ausentes": faltam, "paginas_que_pioraram": pioraram, "paginas_sem_texto": esvaziadas}
    melhoraram = sorted(k for k in a if k in n and _RUIM(a[k]["qualidade"]) and not _RUIM(n[k]["qualidade"]))
    acrescidas = sorted(set(n) - set(a))
    mudaram = sorted(k for k in a if k in n and (a[k]["texto"] or "") != (n[k]["texto"] or ""))
    if not (melhoraram or acrescidas or mudaram) and all(a[k]["qualidade"] == n[k]["qualidade"] for k in a):
        return NEUTRA, {}
    detalhe = {"paginas_que_melhoraram": melhoraram, "paginas_acrescidas": acrescidas, "paginas_com_texto_alterado": mudaram}
    return (MELHORA if melhoraram or acrescidas else MUDANCA), detalhe


# Versão 8 (Etapa 05.3.3): revisões de leitura, classificação ligada à leitura que a originou, identidade lógica e
# vigência das decisões, correções humanas por campo e conflitos explícitos. Só acréscimos: nenhuma tabela ou coluna
# anterior muda, e bancos v1–v7 (inclusive as duas variantes da v6) são levados à v8 pela estrutura presente.
_ESQUEMA_V8 = """
CREATE TABLE tentativa_leitura (
    id            INTEGER PRIMARY KEY,
    sha256        TEXT NOT NULL,
    versao_leitor TEXT NOT NULL,
    situacao      TEXT NOT NULL,
    resultado     TEXT NOT NULL,
    aceita        INTEGER NOT NULL,
    paginas       INTEGER,
    revisao       TEXT,
    erro          TEXT,
    detalhe       TEXT,
    momento       TEXT NOT NULL
);
CREATE INDEX tentativa_leitura_arquivo ON tentativa_leitura (sha256, versao_leitor);
ALTER TABLE leitura ADD COLUMN revisao TEXT;
ALTER TABLE classificacao ADD COLUMN revisao_leitura TEXT;
ALTER TABLE ato ADD COLUMN chave_logica TEXT;
ALTER TABLE decisao ADD COLUMN chave_logica TEXT;
ALTER TABLE decisao ADD COLUMN vigente INTEGER NOT NULL DEFAULT 1;
ALTER TABLE decisao ADD COLUMN representada_por TEXT;
ALTER TABLE decisao ADD COLUMN origem TEXT NOT NULL DEFAULT 'EXTRAIDA';
CREATE INDEX ato_chave ON ato (chave_logica);
CREATE INDEX decisao_chave ON decisao (chave_logica);
CREATE TABLE correcao (
    id              INTEGER PRIMARY KEY,
    alvo_tipo       TEXT NOT NULL,
    alvo_id         TEXT NOT NULL,
    campo           TEXT NOT NULL,
    valor_extraido  TEXT,
    valor_anterior  TEXT,
    valor_corrigido TEXT,
    autor           TEXT NOT NULL,
    momento         TEXT NOT NULL,
    justificativa   TEXT NOT NULL
);
CREATE INDEX correcao_alvo ON correcao (alvo_tipo, alvo_id, campo);
CREATE TABLE conflito (
    id             INTEGER PRIMARY KEY,
    alvo_tipo      TEXT NOT NULL,
    alvo_id        TEXT NOT NULL,
    campo          TEXT NOT NULL,
    valor_vigente  TEXT NOT NULL,
    valor_proposto TEXT NOT NULL,
    origem         TEXT NOT NULL,
    referencia     TEXT,
    estado         TEXT NOT NULL DEFAULT 'ABERTO',
    criado_em      TEXT NOT NULL,
    resolvido_por  TEXT,
    resolvido_em   TEXT,
    justificativa  TEXT
);
CREATE UNIQUE INDEX conflito_unico ON conflito (alvo_tipo, alvo_id, campo, valor_proposto, origem)
"""

_MIGRACOES = ((1, _ESQUEMA), (2, _ESQUEMA_V2), (3, _ESQUEMA_V3), (4, _ESQUEMA_V4), (5, _ESQUEMA_V5), (6, _ESQUEMA_V6),
              (7, _ESQUEMA_V7), (8, _ESQUEMA_V8))
_CRIAR = re.compile(r"^CREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX)\s+(\w+)", re.I)
_ADICIONAR = re.compile(r"^ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.I)


def _instrucoes(script: str) -> list[str]:
    return [i.strip() for i in script.split(";") if i.strip()]


def _ja_existe(con: sqlite3.Connection, instrucao: str) -> bool:
    """A estrutura que a instrução cria já está no banco? (tabela, índice ou coluna)"""
    criar = _CRIAR.match(instrucao)
    if criar:
        tipo = criar.group(1).lower()
        return con.execute("SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?", (tipo, criar.group(2))).fetchone() is not None
    adicionar = _ADICIONAR.match(instrucao)
    if adicionar:
        return any(c[1] == adicionar.group(2) for c in con.execute(f"PRAGMA table_info({adicionar.group(1)})"))
    raise ValueError(f"instrução de migração sem verificação estrutural: {instrucao[:60]}")


def estruturas_pendentes(con: sqlite3.Connection) -> dict[int, list[str]]:
    """Por versão, as instruções cuja estrutura AINDA NÃO existe no banco — decidido pela estrutura presente,
    não só pelo número gravado em `user_version` (bancos de desenvolvimento podem ter o mesmo número com
    esquemas diferentes)."""
    pendentes = {}
    for numero, script in _MIGRACOES:
        faltam = [i for i in _instrucoes(script) if not _ja_existe(con, i)]
        if faltam:
            pendentes[numero] = faltam
    return pendentes


class Banco:
    def __init__(self, caminho: str | Path, backup_antes_de_migrar: bool = True):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self.backup_da_migracao: Path | None = None
        self.con = sqlite3.connect(str(caminho))
        try:
            self.con.row_factory = sqlite3.Row
            self.con.execute("PRAGMA foreign_keys = ON")
            self._migrar(backup_antes_de_migrar)
            self._completar_v8()
        except BaseException:
            # Quem chamou não recebe o objeto e não teria como fechar a conexão: no Windows o arquivo ficava
            # preso (não podia ser apagado nem renomeado). Fecha aqui e propaga o erro ORIGINAL.
            self._fechar_sem_mascarar()
            raise

    @classmethod
    def somente_leitura(cls, caminho: str | Path) -> "Banco":
        """Abre um banco SQLite existente estritamente em modo somente-leitura (`?mode=ro` + `PRAGMA query_only = ON`),
        sem criar arquivos nem aplicar migrações. Deve ser usado com `with Banco.somente_leitura(caminho) as banco:`."""
        alvo = Path(caminho)
        if not alvo.is_file():
            raise FileNotFoundError(f"banco SQLite inexistente: {alvo}")
        inst = cls.__new__(cls)
        inst.caminho = alvo
        inst.backup_da_migracao = None
        inst.con = sqlite3.connect(alvo.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            inst.con.row_factory = sqlite3.Row
            inst.con.execute("PRAGMA query_only = ON")
        except BaseException:
            inst._fechar_sem_mascarar()
            raise
        return inst

    def _completar_v8(self) -> None:
        """Preenche, em bancos anteriores à v8, o que a migração estrutural não calcula: revisão da leitura, revisão
        da leitura das classificações já feitas (que vieram da leitura atual) e identidades lógicas; reconcilia as
        versões já existentes. Idempotente: só toca linhas ainda sem valor."""
        sem_revisao = self.con.execute("SELECT sha256 FROM leitura WHERE revisao IS NULL AND situacao <> 'ERRO'").fetchall()
        atos_sem_chave = self.con.execute("SELECT * FROM ato WHERE chave_logica IS NULL AND numero IS NOT NULL").fetchall()
        if not (sem_revisao or atos_sem_chave):
            return
        with self.con:
            for linha in sem_revisao:
                paginas = self.con.execute("SELECT numero, texto FROM pagina WHERE sha256 = ?", (linha["sha256"],)).fetchall()
                self.con.execute("UPDATE leitura SET revisao = ? WHERE sha256 = ?",
                                 (revisao_de_paginas((p["numero"], p["texto"]) for p in paginas), linha["sha256"]))
                # Só a leitura que veio de esquema antigo é vinculada aqui. Uma classificação sem vínculo de uma
                # leitura que já tinha revisão deve permanecer desatualizada até uma reclassificação real.
                self.con.execute("UPDATE classificacao SET revisao_leitura = (SELECT revisao FROM leitura l WHERE l.sha256 = "
                                 "classificacao.sha256) WHERE sha256 = ? AND revisao_leitura IS NULL", (linha["sha256"],))
            chaves = set()
            for a in atos_sem_chave:
                chave = chave_ato(a["gerencia"], a["tipo"], a["numero"], a["sufixo"], a["natureza"])
                self.con.execute("UPDATE ato SET chave_logica = ? WHERE id = ?", (chave, a["id"]))
                for d in self.con.execute("SELECT id, processo, matricula FROM decisao WHERE ato_id = ?", (a["id"],)).fetchall():
                    self.con.execute("UPDATE decisao SET chave_logica = ? WHERE id = ?",
                                     (chave_decisao(chave, d["processo"], d["matricula"]), d["id"]))
                if chave:
                    chaves.add(chave)
            self._reconciliar_atos(chaves)

    def __enter__(self) -> "Banco":
        return self

    def __exit__(self, *_) -> None:
        self.fechar()

    def _fechar_sem_mascarar(self) -> None:
        try:
            self.con.close()
        except Exception:      # o erro que importa é o que já está sendo propagado
            pass

    def _migrar(self, backup: bool) -> None:
        """Leva o banco à versão VERSAO_ESQUEMA.

        - Cada instrução só é executada se a estrutura (tabela, índice, coluna) ainda não existir: uma migração
          interrompida no meio, ou um banco com o mesmo número de versão e esquema diferente, é completado sem
          erro e sem perda.
        - Todas as instruções pendentes e a nova versão são gravadas numa ÚNICA transação explícita (o
          `executescript` do sqlite3 faz COMMIT antes de rodar e não permitia isso).
        - Antes de alterar um banco existente em arquivo, é feita uma cópia íntegra (`.antes-v<N>.bak`).
        - Banco gravado por uma versão MAIS NOVA do programa é recusado.
        """
        versao = self.con.execute("PRAGMA user_version").fetchone()[0]
        if versao > VERSAO_ESQUEMA:
            raise RuntimeError(f"esquema {versao} é mais novo que este programa ({VERSAO_ESQUEMA})")
        pendentes = estruturas_pendentes(self.con)
        if not pendentes and versao == VERSAO_ESQUEMA:
            return
        existia = bool(self.con.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone())
        if backup and existia and str(self.caminho) != ":memory:":
            destino = Path(f"{self.caminho}.antes-v{VERSAO_ESQUEMA}.bak")
            copia = sqlite3.connect(str(destino))
            try:
                self.con.backup(copia)
            finally:
                copia.close()
            self.backup_da_migracao = destino
        nivel = self.con.isolation_level
        self.con.isolation_level = None                       # controle manual da transação
        try:
            self.con.execute("BEGIN IMMEDIATE")
            try:
                for numero in sorted(pendentes):
                    for instrucao in pendentes[numero]:
                        self.con.execute(instrucao)
                self.con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
                self.con.execute("COMMIT")
            except BaseException:
                try:
                    self.con.execute("ROLLBACK")
                except Exception:
                    pass       # uma falha no ROLLBACK não pode esconder o erro original da migração
                raise
        finally:
            self.con.isolation_level = nivel

    def fechar(self) -> None:
        """Encerra a conexão. Pode ser chamado mais de uma vez. (`with sqlite3.connect(...)` controla a transação,
        não fecha a conexão; use `with Banco(...)` ou `fechar()`.)"""
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
        """Registra uma tentativa malsucedida. Uma publicação que já tem arquivo íntegro (BAIXADA) CONTINUA BAIXADA:
        a falha de uma reverificação não apaga a versão válida nem a tira da cobertura; só o erro fica registrado."""
        with self.con:
            self.con.execute(
                "UPDATE publicacao SET estado = CASE WHEN estado = ? AND sha256 IS NOT NULL THEN estado ELSE ? END, "
                "ultimo_erro = ?, tentativas = tentativas + 1, atualizada_em = ? WHERE id = ?",
                (BAIXADA, estado, erro, agora(), publicacao_id),
            )

    def registrar_obtencao(self, publicacao_id: int, sha256: str, tamanho: int, caminho: str, paginas: int | None,
                           integridade: str, **download) -> str:
        """Registra, numa ÚNICA transação, tudo o que comprova um download íntegro: arquivo, versão, verificação
        estrutural, linha do manifesto de downloads e o estado BAIXADA da publicação. Ou tudo fica gravado, ou nada.
        O arquivo já deve estar no acervo (gravação atômica feita antes): uma queda entre as duas etapas deixa só um
        arquivo sem registro, que a reconciliação aponta, e a publicação continua pendente — nunca falsamente baixada.

        Devolve NOVO, DUPLICADO (conteúdo que já pertencia a outra publicação), IGUAL ou ALTERADO."""
        if integridade not in INTEGRIDADES_ACEITAS:
            raise ValueError(f"integridade {integridade!r} não comprova um arquivo íntegro")
        desconhecidas = set(download) - _COLUNAS_DOWNLOAD
        if desconhecidas:
            raise ValueError(f"colunas inexistentes no manifesto: {sorted(desconhecidas)}")
        momento = agora()
        with self.con:
            ja_existia = self.con.execute("SELECT 1 FROM arquivo WHERE sha256 = ?", (sha256,)).fetchone() is not None
            de_outra = self.con.execute("SELECT 1 FROM publicacao WHERE sha256 = ? AND id <> ? LIMIT 1",
                                        (sha256, publicacao_id)).fetchone() is not None
            anterior = self.con.execute("SELECT sha256 FROM publicacao WHERE id = ?", (publicacao_id,)).fetchone()[0]
            self.con.execute(
                "INSERT INTO arquivo (sha256, tamanho, caminho, guardado_em) VALUES (?,?,?,?) ON CONFLICT (sha256) DO NOTHING",
                (sha256, tamanho, caminho, momento))
            self.con.execute(
                "INSERT INTO versao (publicacao_id, sha256, observada_em) VALUES (?,?,?) ON CONFLICT (publicacao_id, sha256) DO NOTHING",
                (publicacao_id, sha256, momento))
            self.con.execute(
                "INSERT INTO verificacao_arquivo (sha256, paginas, integridade, verificado_em) VALUES (?,?,?,?) "
                "ON CONFLICT (sha256) DO UPDATE SET paginas = excluded.paginas, integridade = excluded.integridade, "
                "verificado_em = excluded.verificado_em", (sha256, paginas, integridade, momento))
            self.con.execute(
                "UPDATE publicacao SET estado = ?, sha256 = ?, ultimo_erro = NULL, tentativas = tentativas + 1, atualizada_em = ? WHERE id = ?",
                (BAIXADA, sha256, momento, publicacao_id))
            if anterior is None:
                resultado = "DUPLICADO" if ja_existia and de_outra else "NOVO"
            else:
                resultado = "IGUAL" if anterior == sha256 else "ALTERADO"
            colunas = ["publicacao_id", "sha256", "bytes", "paginas", "integridade", "resultado", *download]
            self.con.execute(f"INSERT INTO download ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
                             (publicacao_id, sha256, tamanho, paginas, integridade, resultado, *download.values()))
        return resultado

    def marcar_para_reobter(self, publicacao_id: int, motivo: str) -> None:
        """Reconciliação: a publicação estava BAIXADA, mas falta a prova (arquivo no acervo ou verificação). Volta à fila
        sem perder o histórico de versões. O contador de falhas recomeça, porque as tentativas anteriores tiveram êxito."""
        with self.con:
            self.con.execute("UPDATE publicacao SET estado = ?, ultimo_erro = ?, tentativas = 0, atualizada_em = ? WHERE id = ?",
                             (FALHA_DOWNLOAD, f"RECONCILIACAO: {motivo}", agora(), publicacao_id))
            self.auditar("robô (reconciliação da coleta)", "REOBTER", "publicacao", str(publicacao_id), {"estado": BAIXADA},
                         {"estado": FALHA_DOWNLOAD, "motivo": motivo}, motivo)

    def esgotadas(self, fonte: str | None = None):
        sql = (f"SELECT * FROM publicacao WHERE estado IN ({','.join('?' * len(PENDENTES))}) AND tentativas >= ?")
        parametros = [*PENDENTES, MAX_TENTATIVAS]
        if fonte:
            sql += " AND fonte = ?"
            parametros.append(fonte)
        return self.con.execute(sql + " ORDER BY data_publicacao, ordem, id", parametros).fetchall()

    def reabrir_publicacoes(self, ids, autor: str, justificativa: str) -> int:
        """Reabertura CONTROLADA de publicações com tentativas esgotadas: zera o contador e registra autor e motivo na
        trilha de auditoria. Não age sozinha num ciclo automático — exige quem decida e por quê."""
        autor, justificativa = (autor or "").strip(), (justificativa or "").strip()
        if not autor or len(justificativa) < 5:
            raise ValueError("reabertura exige responsável e justificativa")
        reabertas = 0
        with self.con:
            for pid in ids:
                linha = self.con.execute("SELECT * FROM publicacao WHERE id = ?", (pid,)).fetchone()
                if linha is None or linha["estado"] not in PENDENTES or linha["tentativas"] < MAX_TENTATIVAS:
                    continue
                self.con.execute("UPDATE publicacao SET tentativas = 0, atualizada_em = ? WHERE id = ?", (agora(), pid))
                self.auditar(autor[:120], "REABRIR_TENTATIVAS", "publicacao", str(pid),
                             {"tentativas": linha["tentativas"], "ultimo_erro": linha["ultimo_erro"]}, {"tentativas": 0},
                             justificativa[:1000])
                reabertas += 1
        return reabertas

    # --- suspensão de fontes (recusa 403/429, robots, bloqueio) -----------------------------------------------
    # Registrada na trilha de auditoria (sem mudança de esquema): a última ação SUSPENDER_FONTE/LIBERAR_FONTE vale.
    def suspender_fonte(self, fonte: str, categoria: str, detalhe: str, ate: str | None) -> None:
        with self.con:
            self.auditar("robô (coleta)", "SUSPENDER_FONTE", "fonte", fonte, None,
                         {"categoria": categoria, "ate": ate}, detalhe[:300])

    def liberar_fonte(self, fonte: str, autor: str, justificativa: str) -> bool:
        autor, justificativa = (autor or "").strip(), (justificativa or "").strip()
        if not autor or len(justificativa) < 5:
            raise ValueError("liberação exige responsável e justificativa")
        vigente = self.suspensao_vigente(fonte)
        if vigente is None:
            return False
        with self.con:
            self.auditar(autor[:120], "LIBERAR_FONTE", "fonte", fonte, vigente, None, justificativa[:1000])
        return True

    def suspensao_vigente(self, fonte: str, momento: str | None = None) -> dict | None:
        """{categoria, ate, desde, detalhe} da suspensão em vigor, ou None. `ate` None não ocorre hoje: toda suspensão
        automática tem prazo; antes dele, só uma liberação auditada a encerra."""
        ultima = self.con.execute(
            "SELECT * FROM auditoria WHERE alvo_tipo = 'fonte' AND alvo_id = ? AND acao IN ('SUSPENDER_FONTE', 'LIBERAR_FONTE') "
            "ORDER BY id DESC LIMIT 1", (fonte,)).fetchone()
        if ultima is None or ultima["acao"] != "SUSPENDER_FONTE":
            return None
        dados = json.loads(ultima["posterior"] or "{}")
        if dados.get("ate") and dados["ate"] <= (momento or agora()):
            return None
        return {"categoria": dados.get("categoria"), "ate": dados.get("ate"), "desde": ultima["momento"],
                "detalhe": ultima["justificativa"]}

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

    def registrar_verificacao(self, sha256: str, paginas: int | None, integridade: str) -> None:
        with self.con:
            self.con.execute(
                "INSERT INTO verificacao_arquivo (sha256, paginas, integridade, verificado_em) VALUES (?,?,?,?) "
                "ON CONFLICT (sha256) DO UPDATE SET paginas = excluded.paginas, integridade = excluded.integridade, "
                "verificado_em = excluded.verificado_em", (sha256, paginas, integridade, agora()))

    def verificacao(self, sha256: str):
        return self.con.execute("SELECT * FROM verificacao_arquivo WHERE sha256 = ?", (sha256,)).fetchone()

    def registrar_download(self, publicacao_id: int, **campos) -> int:
        """Acrescenta uma linha ao manifesto de downloads. Nunca altera linhas anteriores."""
        desconhecidas = set(campos) - _COLUNAS_DOWNLOAD
        if desconhecidas:
            raise ValueError(f"colunas inexistentes no manifesto: {sorted(desconhecidas)}")
        colunas = ["publicacao_id", *campos]
        with self.con:
            cursor = self.con.execute(
                f"INSERT INTO download ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
                (publicacao_id, *campos.values()))
        return cursor.lastrowid

    def downloads(self, publicacao_id: int | None = None):
        if publicacao_id is None:
            return self.con.execute("SELECT * FROM download ORDER BY id").fetchall()
        return self.con.execute("SELECT * FROM download WHERE publicacao_id = ? ORDER BY id", (publicacao_id,)).fetchall()

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
    def arquivos_sem_leitura(self, versao_leitor: str, refazer_pendentes: bool = False):
        """Arquivos ainda não lidos por esta versão do leitor. Uma tentativa desta versão que falhou ou foi recusada
        (perda de conteúdo) não volta sozinha à fila — senão repetiria a cada execução —, mas continua visível e volta
        com `refazer_pendentes`, junto com leituras em ERRO ou com páginas pendentes (por exemplo, OCR indisponível).
        Antes (Etapa 05.3.3), a tentativa malsucedida gravava a versão nova e o arquivo saía da fila como se lido."""
        extra = ""
        if refazer_pendentes:
            extra = (" OR l.situacao IN ('ERRO', 'LIDA_COM_PENDENCIAS') OR l.paginas_com_pendencia > 0 OR EXISTS (SELECT 1 FROM tentativa_leitura t "
                     "WHERE t.sha256 = a.sha256 AND t.versao_leitor = :v AND t.aceita = 0 AND t.id = "
                     "(SELECT MAX(id) FROM tentativa_leitura u WHERE u.sha256 = a.sha256))")
        return self.con.execute(
            "SELECT a.* FROM arquivo a LEFT JOIN leitura l ON l.sha256 = a.sha256 "
            "WHERE l.sha256 IS NULL OR (l.versao_leitor <> :v AND NOT EXISTS (SELECT 1 FROM tentativa_leitura t "
            f"WHERE t.sha256 = a.sha256 AND t.versao_leitor = :v)){extra} ORDER BY a.guardado_em, a.sha256",
            {"v": versao_leitor}).fetchall()

    def tentativas_de_leitura(self, sha256: str):
        return self.con.execute("SELECT * FROM tentativa_leitura WHERE sha256 = ? ORDER BY id", (sha256,)).fetchall()

    def registrar_leitura(self, sha256, situacao, versao_leitor, paginas, numero_edicao, data_edicao, erro,
                          inconsistencias=()) -> str:
        """Registra uma TENTATIVA de leitura e decide, numa só transação, se ela substitui a última leitura válida.

        - Toda tentativa fica em ``tentativa_leitura`` (versão, momento, resultado, páginas, revisão, erro, detalhe).
        - A última leitura válida (``leitura`` + ``pagina``) só é substituída por tentativa ACEITA: primeira leitura,
          melhora, mudança sem perda ou mudança neutra. Falha técnica ou perda de conteúdo (página ausente, página que
          piorou ou ficou sem texto) não toca nas páginas, no estado nem na versão da leitura válida.
        - A revisão da leitura (``revisao``) muda quando o texto aceito muda; a classificação derivada da revisão
          anterior passa a desatualizada e volta à fila (ver ``arquivos_sem_classificacao``).
        Devolve o resultado da comparação (PRIMEIRA, NEUTRA, MELHORA, MUDANCA, PERDA_DE_CONTEUDO, FALHA_TECNICA)."""
        anterior = self.con.execute("SELECT * FROM leitura WHERE sha256 = ?", (sha256,)).fetchone()
        valida = anterior is not None and anterior["situacao"] != "ERRO"
        paginas_validas = self.paginas(sha256) if valida else []
        novas = [] if situacao == "ERRO" else list(paginas)
        resultado, detalhe = comparar_leituras(paginas_validas, novas)
        aceita = resultado in LEITURA_ACEITA
        revisao = revisao_de_paginas((p["numero"], p["texto"]) for p in novas) if novas else None
        momento = agora()
        with self.con:
            self.con.execute(
                "INSERT INTO tentativa_leitura (sha256, versao_leitor, situacao, resultado, aceita, paginas, revisao, erro, detalhe, "
                "momento) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sha256, versao_leitor, situacao, resultado, int(aceita), len(novas), revisao, erro,
                 json.dumps(detalhe, ensure_ascii=False) if detalhe else None, momento))
            if not aceita and valida:
                # A tentativa não substitui a leitura válida: só o aviso fica registrado (estado e versão intactos).
                motivo = (f"releitura falhou; mantida a leitura anterior ({anterior['situacao']}): {erro}" if resultado == FALHA_TECNICA
                          else f"releitura recusada por perda de conteúdo; mantida a leitura anterior: {json.dumps(detalhe)}")
                self.con.execute("UPDATE leitura SET erro = ? WHERE sha256 = ?", (motivo[:1000], sha256))
                return resultado
            if resultado == NEUTRA:
                # O texto não mudou, mas a conferência da origem e os avisos podem ter mudado.
                self.con.execute("UPDATE leitura SET situacao = ?, versao_leitor = ?, concluida_em = ?, erro = NULL, numero_edicao = ?, "
                                 "data_edicao = ?, inconsistencias = ? WHERE sha256 = ?",
                                 (situacao, versao_leitor, momento, numero_edicao, data_edicao,
                                  json.dumps(list(inconsistencias), ensure_ascii=False), sha256))
                return resultado
            self.con.execute("DELETE FROM pagina WHERE sha256 = ?", (sha256,))
            self.con.executemany(
                "INSERT INTO pagina (sha256, numero, metodo, colunas, texto, qualidade, confianca, palavras, texto_sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [(sha256, p["numero"], p["metodo"], p["colunas"], p["texto"], p["qualidade"], p.get("confianca"),
                  p["palavras"], hashlib.sha256(p["texto"].encode("utf-8")).hexdigest()) for p in novas],
            )
            self.con.execute(
                "INSERT INTO leitura (sha256, situacao, versao_leitor, paginas, paginas_sem_texto, numero_edicao, "
                "data_edicao, erro, concluida_em, paginas_com_pendencia, inconsistencias, revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT (sha256) DO UPDATE SET situacao = excluded.situacao, versao_leitor = excluded.versao_leitor, "
                "paginas = excluded.paginas, paginas_sem_texto = excluded.paginas_sem_texto, "
                "numero_edicao = excluded.numero_edicao, data_edicao = excluded.data_edicao, erro = excluded.erro, "
                "concluida_em = excluded.concluida_em, paginas_com_pendencia = excluded.paginas_com_pendencia, "
                "inconsistencias = excluded.inconsistencias, revisao = excluded.revisao",
                (sha256, situacao, versao_leitor, len(novas), sum(p["metodo"] != "TEXTO" for p in novas),
                 numero_edicao, data_edicao, erro, momento,
                 sum(p["qualidade"] not in ("OK", "VAZIA") for p in novas),
                 json.dumps(list(inconsistencias), ensure_ascii=False), revisao),
            )
        return resultado

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

    # --- classificação por gerência -------------------------------------
    def data_do_arquivo(self, sha256: str) -> str | None:
        """Data de publicação: a informada pela fonte; na falta, a lida no cabeçalho do documento."""
        linha = self.con.execute(
            "SELECT MIN(data_publicacao) FROM publicacao WHERE sha256 = ? AND data_publicacao IS NOT NULL", (sha256,)).fetchone()
        if linha[0]:
            return linha[0]
        linha = self.con.execute("SELECT data_edicao FROM leitura WHERE sha256 = ?", (sha256,)).fetchone()
        return linha[0] if linha else None

    def url_oficial(self, sha256: str) -> str | None:
        """Endereço oficial (https) de onde o arquivo veio, se conhecido. Importação manual sem endereço: None."""
        for origem in self.origens(sha256):
            if str(origem["url"]).startswith("https://"):
                return origem["url"]
        return None

    def arquivos_sem_classificacao(self, gerencia: str, versao_regras: str):
        """Arquivos lidos sem classificação VIGENTE: nunca classificados, classificados por outra versão das regras ou
        classificados a partir de outra revisão da leitura (o mesmo PDF relido com texto diferente — antes, a
        classificação antiga continuava valendo porque só o SHA do PDF e as regras eram comparados)."""
        return self.con.execute(
            "SELECT l.sha256 FROM leitura l LEFT JOIN classificacao c ON c.sha256 = l.sha256 AND c.gerencia = ? "
            "WHERE l.situacao <> 'ERRO' AND (c.sha256 IS NULL OR c.versao_regras <> ? OR "
            "(l.revisao IS NOT NULL AND c.revisao_leitura IS NOT l.revisao)) ORDER BY l.sha256",
            (gerencia, versao_regras)).fetchall()

    def classificacoes_desatualizadas(self, gerencia: str, versao_regras: str | None = None) -> int:
        return self.con.execute(
            "SELECT COUNT(*) FROM classificacao c LEFT JOIN leitura l ON l.sha256 = c.sha256 WHERE c.gerencia = ? "
            "AND (l.sha256 IS NULL OR l.situacao = 'ERRO' OR (l.revisao IS NOT NULL AND c.revisao_leitura IS NOT l.revisao) "
            "OR (? IS NOT NULL AND c.versao_regras <> ?))", (gerencia, versao_regras, versao_regras)).fetchone()[0]

    # Campos homologados por conferência/correção humana: uma nova extração não os sobrescreve; propõe (conflito).
    CAMPOS_ATO_HOMOLOGADOS = ("eixo", "modalidade", "condicao", "grupo", "subcategoria", "vinculo")
    CAMPOS_DECISAO = ("processo", "servidor", "matricula", "lotacao", "cargo", "resultado")
    CAMPOS_DETALHE = ("classe_anterior", "classe_posterior", "nivel_anterior", "nivel_atual")

    def _conflito(self, alvo_tipo, alvo_id, campo, vigente, proposto, origem, referencia=None) -> None:
        """Conflito explícito para a gerência. Idempotente: a mesma proposta (mesmo alvo, campo, valor e origem) não é
        repetida — nem depois de resolvida (uma proposta já mantida pela gerência não volta a incomodar)."""
        self.con.execute(
            "INSERT OR IGNORE INTO conflito (alvo_tipo, alvo_id, campo, valor_vigente, valor_proposto, origem, referencia, criado_em) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (alvo_tipo, alvo_id, campo, json.dumps(vigente, ensure_ascii=False), json.dumps(proposto, ensure_ascii=False),
             origem, referencia, agora()))

    def conflitos(self, estado: str | None = "ABERTO", alvo_tipo: str | None = None, alvo_ids=None):
        sql, parametros = "SELECT * FROM conflito WHERE 1=1", []
        if estado:
            sql += " AND estado = ?"
            parametros.append(estado)
        if alvo_tipo:
            sql += " AND alvo_tipo = ?"
            parametros.append(alvo_tipo)
        if alvo_ids is not None:
            alvo_ids = list(alvo_ids)
            if not alvo_ids:
                return []
            sql += f" AND alvo_id IN ({','.join('?' * len(alvo_ids))})"
            parametros += alvo_ids
        return self.con.execute(sql + " ORDER BY id", parametros).fetchall()

    def correcoes(self, alvo_tipo: str, alvo_id: str):
        return self.con.execute("SELECT * FROM correcao WHERE alvo_tipo = ? AND alvo_id = ? ORDER BY id",
                                (alvo_tipo, alvo_id)).fetchall()

    def _extraido_original(self, alvo_tipo: str, alvo_id: str, campo: str, atual):
        """Valor que a extração tinha produzido antes da primeira correção humana do campo (ou o atual, sem correção)."""
        primeira = self.con.execute("SELECT valor_extraido FROM correcao WHERE alvo_tipo = ? AND alvo_id = ? AND campo = ? "
                                    "ORDER BY id LIMIT 1", (alvo_tipo, alvo_id, campo)).fetchone()
        return json.loads(primeira[0]) if primeira and primeira[0] is not None else atual

    def gravar_classificacao(self, gerencia: str, sha256: str, versao_regras: str, data: str | None, resultado) -> dict:
        """Substitui os candidatos deste arquivo preservando TUDO o que já passou por revisão humana, numa só transação.

        Etapa 05.3.3:
        - a classificação fica ligada à revisão da leitura que a originou (``revisao_leitura``);
        - decisão já revisada não é regravada; se a nova extração diverge dela (inclusive de um valor corrigido por uma
          pessoa), o que muda vira CONFLITO explícito para a gerência, nunca sobrescrita silenciosa;
        - o ato com decisões revisadas não fica mais "congelado": metadados técnicos (texto, pendências, páginas,
          versão das regras) são atualizados; só a classificação homologada (eixo, modalidade, grupo, assunto...)
          é preservada, e a divergência vira conflito;
        - ato referenciado por QUALQUER evento remanescente (modificador, original ou sugerido) não é apagado
          (antes, o ato modificador de um evento revisado podia sumir e deixar o evento órfão);
        - as várias representações do mesmo ato lógico (versões do PDF, releituras) são reconciliadas para que cada
          decisão lógica tenha uma só representação vigente nos indicadores.
        """
        j = lambda v: json.dumps(v, ensure_ascii=False)
        revisao_leitura = (self.con.execute("SELECT revisao FROM leitura WHERE sha256 = ?", (sha256,)).fetchone() or [None])[0]
        with self.con:
            revisadas = {r["id"]: r for r in self.con.execute(
                "SELECT d.* FROM decisao d WHERE d.sha256 = ? AND (d.validacao <> 'PENDENTE' "
                "OR d.origem = 'MANUAL' OR d.revisado_em IS NOT NULL "
                "OR EXISTS (SELECT 1 FROM correcao c WHERE c.alvo_tipo = 'decisao' AND c.alvo_id = d.id) "
                "OR EXISTS (SELECT 1 FROM auditoria t WHERE t.alvo_tipo = 'decisao' AND t.alvo_id = d.id))", (sha256,))}
            eventos_revisados = {r["id"] for r in self.con.execute(
                "SELECT id FROM evento WHERE sha256 = ? AND estado NOT IN ('PENDENTE_VINCULACAO', 'SUGERIDO')", (sha256,))}
            atos_homologados = {r["ato_id"] for r in revisadas.values()}
            atos_homologados |= {r[0] for r in self.con.execute("SELECT ato_original_id FROM evento WHERE ato_original_id IS NOT NULL")}
            atos_homologados |= {r[0] for r in self.con.execute("SELECT alvo_id FROM correcao WHERE alvo_tipo = 'ato'")}
            existentes = {r["id"]: r for r in self.con.execute("SELECT * FROM ato WHERE sha256 = ? AND gerencia = ?", (sha256, gerencia))}
            self.con.execute(
                "DELETE FROM decisao WHERE sha256 = ? AND validacao = 'PENDENTE' AND origem <> 'MANUAL' "
                "AND revisado_em IS NULL AND NOT EXISTS (SELECT 1 FROM correcao c WHERE c.alvo_tipo = 'decisao' AND c.alvo_id = decisao.id) "
                "AND NOT EXISTS (SELECT 1 FROM auditoria t WHERE t.alvo_tipo = 'decisao' AND t.alvo_id = decisao.id)", (sha256,))
            self.con.execute("DELETE FROM evento WHERE sha256 = ? AND estado IN ('PENDENTE_VINCULACAO', 'SUGERIDO')", (sha256,))
            self.con.execute("DELETE FROM outra_publicacao WHERE sha256 = ? AND gerencia = ?", (sha256, gerencia))
            self.con.execute("DELETE FROM fora_escopo WHERE sha256 = ? AND gerencia = ?", (sha256, gerencia))
            self.con.execute(
                "DELETE FROM ato WHERE sha256 = ? AND gerencia = ? AND id NOT IN (SELECT ato_id FROM decisao) "
                "AND id NOT IN (SELECT ato_id FROM evento WHERE ato_id IS NOT NULL) "
                "AND id NOT IN (SELECT ato_original_id FROM evento WHERE ato_original_id IS NOT NULL) "
                "AND id NOT IN (SELECT ato_sugerido_id FROM evento WHERE ato_sugerido_id IS NOT NULL)", (sha256, gerencia))
            conflitos = 0
            chaves = {r["chave_logica"] for r in existentes.values() if r["chave_logica"]}
            for a in resultado.atos:
                chave = chave_ato(gerencia, a.tipo, a.numero, a.sufixo, a.natureza)
                if chave:
                    chaves.add(chave)
                atual = existentes.get(a.id)
                if a.id in atos_homologados and atual is not None:
                    for campo in self.CAMPOS_ATO_HOMOLOGADOS:
                        novo, vigente = getattr(a, campo), atual[campo]
                        if novo != self._extraido_original("ato", a.id, campo, vigente) and novo != vigente:
                            self._conflito("ato", a.id, campo, vigente, novo, "RECLASSIFICACAO", sha256)
                            conflitos += 1
                    self.con.execute(
                        "UPDATE ato SET pagina = ?, pagina_final = ?, data_publicacao = ?, data_expediente = ?, expressao_vinculo = ?, "
                        "grupo_expressao = ?, resultado = ?, texto = ?, pendencias = ?, versao_regras = ?, chave_logica = ? WHERE id = ?",
                        (a.pagina, a.pagina_final, data, a.data_expediente, a.expressao_vinculo, a.grupo_expressao, a.resultado,
                         a.texto, j(a.pendencias), versao_regras, chave, a.id))
                    continue
                self.con.execute(
                    "INSERT OR REPLACE INTO ato (id, gerencia, sha256, tipo, numero, sufixo, pagina, pagina_final, data_publicacao, "
                    "data_expediente, vinculo, expressao_vinculo, natureza, eixo, modalidade, condicao, grupo, grupo_expressao, "
                    "subcategoria, resultado, texto, pendencias, versao_regras, chave_logica) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (a.id, gerencia, sha256, a.tipo, a.numero, a.sufixo, a.pagina, a.pagina_final, data, a.data_expediente, a.vinculo,
                     a.expressao_vinculo, a.natureza, a.eixo, a.modalidade, a.condicao, a.grupo, a.grupo_expressao, a.subcategoria,
                     a.resultado, a.texto, j(a.pendencias), versao_regras, chave))
            chave_do_ato = {r["id"]: r["chave_logica"] for r in self.con.execute("SELECT id, chave_logica FROM ato WHERE sha256 = ?", (sha256,))}
            for d in resultado.decisoes:
                if d.id in revisadas:
                    conflitos += self._comparar_com_revisada(revisadas[d.id], d, sha256)
                    continue
                self.con.execute(
                    "INSERT INTO decisao (id, ato_id, sha256, pagina, processo, servidor, matricula, lotacao, cargo, detalhe, resultado, "
                    "trecho, chave_logica) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d.id, d.ato_id, sha256, d.pagina, d.processo, d.servidor, d.matricula, d.lotacao, d.cargo, j(d.detalhe),
                     d.resultado, d.trecho, chave_decisao(chave_do_ato.get(d.ato_id), d.processo, d.matricula)))
            for e in resultado.eventos:
                if e.id in eventos_revisados:
                    continue
                self.con.execute(
                    "INSERT INTO evento (id, gerencia, sha256, ato_id, tipo, subtipo, pagina, data_publicacao, modificador, "
                    "resenhas_citadas, processos_citados, vinculo, texto, publicacoes_citadas) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (e.id, gerencia, sha256, e.ato_id, e.tipo, e.subtipo, e.pagina, data, e.modificador, j(e.resenhas_citadas),
                     j(e.processos_citados), e.vinculo, e.texto, j(getattr(e, "publicacoes_citadas", []))))
            for o in resultado.outras:
                self.con.execute(
                    "INSERT OR REPLACE INTO outra_publicacao (id, gerencia, sha256, tipo, pagina, data_publicacao, titulo, vinculo, trecho) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (o.id, gerencia, sha256, o.tipo, o.pagina, data, o.titulo, o.vinculo, o.trecho))
            for f in getattr(resultado, "fora_escopo", []):
                self.con.execute(
                    "INSERT OR REPLACE INTO fora_escopo (id, gerencia, sha256, tipo, numero, pagina, data_publicacao, titulo, motivo, "
                    "expressao, vinculo, versao_regras) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f.id, gerencia, sha256, f.tipo, f.numero, f.pagina, data, f.titulo, f.motivo, f.expressao, f.vinculo, versao_regras))
            conflitos += self._reconciliar_atos(chaves)
            resumo = {"atos": len(resultado.atos), "decisoes": len(resultado.decisoes), "eventos": len(resultado.eventos),
                      "outras": len(resultado.outras), "fora_escopo": len(getattr(resultado, "fora_escopo", [])),
                      "descartados": resultado.descartados,
                      "preservadas_por_revisao": len(revisadas) + len(eventos_revisados), "conflitos": conflitos}
            self.con.execute(
                "INSERT OR REPLACE INTO classificacao (sha256, gerencia, versao_regras, atos, decisoes, eventos, descartados, "
                "pendencias, concluida_em, revisao_leitura) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sha256, gerencia, versao_regras, resumo["atos"], resumo["decisoes"], resumo["eventos"], resumo["descartados"],
                 j(resultado.pendencias), agora(), revisao_leitura))
        return resumo

    def _comparar_com_revisada(self, revisada, d, sha256) -> int:
        """A nova extração da MESMA decisão (mesmo id) diverge do que foi revisado? Cada campo diferente vira conflito.
        Pessoa diferente (matrícula ou nome) na mesma posição nunca herda a revisão: conflito de identidade."""
        novos = 0
        detalhe_revisado = json.loads(revisada["detalhe"] or "{}")
        for campo in self.CAMPOS_DECISAO + self.CAMPOS_DETALHE:
            vigente = detalhe_revisado.get(campo) if campo in self.CAMPOS_DETALHE else revisada[campo]
            novo = d.detalhe.get(campo) if campo in self.CAMPOS_DETALHE else getattr(d, campo)
            original = self._extraido_original("decisao", revisada["id"], campo, vigente)
            if normalizar_texto(novo) not in (normalizar_texto(original), normalizar_texto(vigente)):
                self._conflito("decisao", revisada["id"], campo, vigente, novo, "RECLASSIFICACAO", sha256)
                novos += 1
        return novos

    def _reconciliar_atos(self, chaves) -> int:
        """Uma decisão LÓGICA tem uma única representação vigente. Para cada ato lógico com mais de uma representação
        (versões do PDF, mesmo ato em dois arquivos, releitura que mudou a página), escolhe a principal — a que tem
        revisão humana (a mais antiga), senão a do arquivo mais recente — e liga as demais a ela:

        - mesma decisão (mesmo processo; sem processo, mesma matrícula): a cópia deixa de ser vigente e aponta para a
          principal; o que diverge vira conflito na principal (nada é sobrescrito);
        - mesmo processo com matrícula diferente, ou decisão sem processo nem matrícula: correspondência AMBÍGUA — fica
          fora dos indicadores até a gerência decidir (conflito);
        - decisão só na versão mais nova: acréscimo legítimo, vigente (vai à conferência normalmente);
        - decisão só numa versão mais antiga: fora dos indicadores, com conflito (pode ter sido retirada).
        Republicação/retificação tem natureza própria no ato lógico: nunca é fundida com o original.
        Decisões manuais e resoluções da gerência sobre vigência prevalecem."""
        novos = 0
        for chave in sorted(c for c in chaves if c):
            instancias = self.con.execute(
                "SELECT a.id, a.sha256, COALESCE(f.guardado_em, '') AS guardado_em, "
                "(SELECT MIN(revisado_em) FROM decisao d WHERE d.ato_id = a.id AND d.validacao <> 'PENDENTE') AS revisado_em "
                "FROM ato a LEFT JOIN arquivo f ON f.sha256 = a.sha256 WHERE a.chave_logica = ?", (chave,)).fetchall()
            ids = [i["id"] for i in instancias]
            if not ids:
                continue
            marcas = ",".join("?" * len(ids))
            if len(instancias) == 1:
                self.con.execute(f"UPDATE decisao SET vigente = 1, representada_por = NULL WHERE ato_id IN ({marcas}) "
                                 "AND representada_por IS NOT NULL", ids)
                self._aplicar_resolucoes(ids)
                continue
            revisadas = [i for i in instancias if i["revisado_em"]]
            principal = (min(revisadas, key=lambda i: (i["revisado_em"], i["id"])) if revisadas
                         else max(instancias, key=lambda i: (i["guardado_em"], i["id"])))
            base = self.con.execute("SELECT * FROM decisao WHERE ato_id = ? ORDER BY rowid", (principal["id"],)).fetchall()
            self.con.execute("UPDATE decisao SET vigente = 1, representada_por = NULL WHERE ato_id = ?", (principal["id"],))
            por_processo, por_matricula = {}, {}
            for b in base:
                if _normalizar_chave(b["processo"]):
                    por_processo.setdefault(_normalizar_chave(b["processo"]), []).append(b)
                if _normalizar_chave(b["matricula"]):
                    por_matricula.setdefault(_normalizar_chave(b["matricula"]), []).append(b)
            for outra in instancias:
                if outra["id"] == principal["id"]:
                    continue
                mais_nova = (outra["guardado_em"], outra["id"]) >= (principal["guardado_em"], principal["id"])
                encontradas = set()
                for d in self.con.execute("SELECT * FROM decisao WHERE ato_id = ? ORDER BY rowid", (outra["id"],)).fetchall():
                    proc, mat = _normalizar_chave(d["processo"]), _normalizar_chave(d["matricula"])
                    candidatas = por_processo.get(proc, []) if proc else por_matricula.get(mat, []) if mat else []
                    if len(candidatas) > 1 and mat:
                        # O mesmo processo para mais de uma pessoa no ato: a matrícula desfaz a dúvida, se for única.
                        candidatas = [b for b in candidatas if _normalizar_chave(b["matricula"]) == mat] or candidatas
                    if proc and not candidatas and mat:
                        candidatas = por_matricula.get(mat, [])          # processo alterado: mesma pessoa pela matrícula
                    alvo = candidatas[0] if len(candidatas) == 1 else None
                    ambigua = (not proc and not mat) or len(candidatas) > 1 or (
                        alvo is not None and _normalizar_chave(alvo["matricula"]) and mat and _normalizar_chave(alvo["matricula"]) != mat)
                    if ambigua:
                        self.con.execute("UPDATE decisao SET vigente = 0, representada_por = NULL WHERE id = ?", (d["id"],))
                        self._conflito("decisao", d["id"], "vigencia", "fora dos indicadores",
                                       f"decisão distinta das da representação {principal['id']}", "CORRESPONDENCIA_AMBIGUA", principal["id"])
                        novos += 1
                        continue
                    if alvo is None:
                        if mais_nova:
                            self.con.execute("UPDATE decisao SET vigente = 1, representada_por = NULL WHERE id = ?", (d["id"],))
                        else:
                            self.con.execute("UPDATE decisao SET vigente = 0, representada_por = NULL WHERE id = ?", (d["id"],))
                            self._conflito("decisao", d["id"], "vigencia", "fora dos indicadores",
                                           "decisão só existe em versão anterior do documento", "AUSENTE_NA_VERSAO_PRINCIPAL", principal["id"])
                            novos += 1
                        continue
                    encontradas.add(alvo["id"])
                    self.con.execute("UPDATE decisao SET vigente = 0, representada_por = ? WHERE id = ?", (alvo["id"], d["id"]))
                    detalhe_alvo, detalhe_d = json.loads(alvo["detalhe"] or "{}"), json.loads(d["detalhe"] or "{}")
                    for campo in self.CAMPOS_DECISAO + self.CAMPOS_DETALHE:
                        va = detalhe_alvo.get(campo) if campo in self.CAMPOS_DETALHE else alvo[campo]
                        vd = detalhe_d.get(campo) if campo in self.CAMPOS_DETALHE else d[campo]
                        if normalizar_texto(vd) and normalizar_texto(va) != normalizar_texto(vd) and \
                                normalizar_texto(self._extraido_original("decisao", alvo["id"], campo, va)) != normalizar_texto(vd):
                            self._conflito("decisao", alvo["id"], campo, va, vd, "VERSAO_DO_DOCUMENTO", d["id"])
                            novos += 1
                if mais_nova:
                    for b in base:
                        if b["id"] not in encontradas and b["origem"] != "MANUAL":
                            self._conflito("decisao", b["id"], "presenca", "presente", f"ausente na versão {outra['sha256'][:12]}",
                                           "AUSENTE_EM_VERSAO_MAIS_NOVA", outra["id"])
                            novos += 1
            self._aplicar_resolucoes(ids)
        return novos

    def _aplicar_resolucoes(self, atos) -> None:
        """Decisões da gerência sobre vigência prevalecem sobre a reconciliação automática."""
        marcas = ",".join("?" * len(atos))
        for c in self.con.execute(
                f"SELECT c.* FROM conflito c JOIN decisao d ON d.id = c.alvo_id WHERE c.alvo_tipo = 'decisao' AND d.ato_id IN ({marcas}) "
                "AND c.campo IN ('vigencia', 'presenca') AND c.estado IN ('ACEITO', 'MANTIDO') ORDER BY c.id", list(atos)).fetchall():
            if c["campo"] == "vigencia" and c["estado"] == "ACEITO":
                self.con.execute("UPDATE decisao SET vigente = 1, representada_por = NULL WHERE id = ?", (c["alvo_id"],))
            elif c["campo"] == "presenca" and c["estado"] == "ACEITO":
                self.con.execute("UPDATE decisao SET vigente = 0 WHERE id = ?", (c["alvo_id"],))

    def vinculos_orfaos(self) -> list[dict]:
        """Diagnóstico (sem alterar nada) de eventos cujo ato modificador, original ou sugerido não existe, ou cujo
        original não é um ato ORIGINAL da mesma gerência. Chaves estrangeiras não são impostas a bancos históricos:
        os problemas são apontados para a gerência."""
        atos = {a["id"]: a for a in self.con.execute("SELECT id, gerencia, natureza FROM ato")}
        saida = []
        for e in self.con.execute("SELECT * FROM evento ORDER BY id"):
            for campo in ("ato_id", "ato_original_id", "ato_sugerido_id"):
                alvo = e[campo]
                if alvo is None:
                    continue
                if alvo not in atos:
                    saida.append({"evento": e["id"], "campo": campo, "problema": "ATO_INEXISTENTE", "ato": alvo})
                elif campo == "ato_original_id" and (atos[alvo]["natureza"] != "ORIGINAL" or atos[alvo]["gerencia"] != e["gerencia"]):
                    saida.append({"evento": e["id"], "campo": campo, "problema": "ALVO_INCOMPATIVEL", "ato": alvo})
        return saida

    @contextlib.contextmanager
    def instantaneo(self):
        """Leitura consistente: todas as consultas do bloco veem o banco num mesmo momento (transação de leitura),
        mesmo que outro processo grave durante o cálculo dos indicadores."""
        abriu = not self.con.in_transaction
        if abriu:
            self.con.execute("BEGIN")
        try:
            yield self
        finally:
            if abriu and self.con.in_transaction:
                self.con.execute("COMMIT")

    def auditar(self, autor: str, acao: str, alvo_tipo: str, alvo_id: str, anterior, posterior, justificativa: str | None) -> None:
        """Chamado dentro da transação de quem altera o registro."""
        self.con.execute(
            "INSERT INTO auditoria (momento, autor, acao, alvo_tipo, alvo_id, anterior, posterior, justificativa) VALUES (?,?,?,?,?,?,?,?)",
            (agora(), autor, acao, alvo_tipo, alvo_id, json.dumps(anterior, ensure_ascii=False),
             json.dumps(posterior, ensure_ascii=False), justificativa))

    def trilha(self, alvo_tipo: str | None = None, alvo_id: str | None = None, limite: int = 200):
        sql, parametros = "SELECT * FROM auditoria WHERE 1=1", []
        if alvo_tipo:
            sql += " AND alvo_tipo = ?"
            parametros.append(alvo_tipo)
        if alvo_id:
            sql += " AND alvo_id = ?"
            parametros.append(alvo_id)
        return self.con.execute(sql + " ORDER BY id DESC LIMIT ?", parametros + [limite]).fetchall()
