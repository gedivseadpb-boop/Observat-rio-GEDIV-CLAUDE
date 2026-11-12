"""Dicionário controlado e versionado da GEDIV: eixos, modalidades, condições, grupos e subcategorias.

Fontes, em ordem de precedência (ver docs/06-regras-consolidadas.md):
1. documento "Eixos e grupos da GEDIV" (pasta do projeto no Google Drive, lido em 10/11/2026);
2. Especificação Funcional V3 (29/10/2026) — contrato dos indicadores e das três dimensões;
3. expressões observadas em resenhas reais registradas no histórico do projeto.

Regras fixas: existem exatamente DOIS eixos. Horizontal e Vertical são modalidades da Progressão;
grupo não é eixo; Tempo de Serviço tem exatamente SETE subcategorias. Denominação nova entra
como candidata e nunca altera sozinha a classificação nem os totais.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

VERSAO_REGRAS = "gediv-2026.11.12-1"   # grupos definitivos (SSA, ESP, INT), TEC. ADM e STF sem grupo, exclusões

PROGRESSAO = "PROGRESSAO"
TEMPO = "TEMPO_SERVICO"
EIXOS = {PROGRESSAO: "Progressão Funcional", TEMPO: "Tempo de Serviço/Contribuição"}

HORIZONTAL, VERTICAL = "HORIZONTAL", "VERTICAL"
MODALIDADES = {HORIZONTAL: "Horizontal", VERTICAL: "Vertical"}

CONDICOES = {"PLENA": "Plena", "CONDICIONAL": "Condicional", "NAO_INFORMADA": "Não informada"}
RESULTADOS = {"DEFERIDO": "Deferido", "INDEFERIDO": "Indeferido", "NAO_INFORMADO": "Não informado"}

# Estado de cada entrada do dicionário.
CONFIRMADA = "CONFIRMADA"      # consta do documento oficial E a expressão foi vista em resenha real do histórico
PROVISORIA = "PROVISORIA"      # consta do documento oficial; ainda sem resenha examinada neste projeto
CANDIDATA = "CANDIDATA"        # denominação encontrada, fora do documento oficial


# Hífen discricionário e caracteres de controle que o PDF do DOE deixa no meio das palavras
# ("FUN\x02CIONAL", "COM\x02PETÊNCIA"): são removidos para a palavra voltar a ser uma só.
_INVISIVEIS = re.compile("[\x00-\x08\x0b-\x1f\x7f\u00ad\u200b-\u200d\ufeff]")


def limpar(texto: str) -> str:
    return _INVISIVEIS.sub("", str(texto or ""))


def normalizar(texto: str) -> str:
    """Maiúsculas, sem acentos, e sem a quebra que a ligadura tipográfica "fi"/"fl" produz
    no texto extraído do DOE ("Ofi cial", "retifi cação")."""
    t = _INVISIVEIS.sub("", str(texto or ""))
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).upper()
    return re.sub(r"(?<=[A-Z])(F[IL]) (?=[A-Z])", r"\1", t)


@dataclass(frozen=True)
class Grupo:
    codigo: str
    nome: str
    padrao: str          # aplicado ao preâmbulo NORMALIZADO do ato, nunca às linhas de servidores
    estado: str
    observacao: str = ""


# Os 16 grupos do PCCR definidos pela GEDIV (regra definitiva da Etapa 02), nesta ordem:
# MAG, SSA, GAJ, FAP, AST, ANS, ESP, DPS, SFT, OSPB, GPC, SEI, SAT, ACI, PPGG, INT.
# A ordem de avaliação é a de GRUPOS_AVALIACAO (casos específicos primeiro).
GRUPOS = (
    Grupo("MAG", "Magistério", r"\bMAG\b|MAGISTERIO", CONFIRMADA),
    Grupo("SSA", "Saúde", r"\bSSA\b|GRUPO\s+(?:OCUPACIONAL\s+)?(?:DA\s+)?SAUDE", CONFIRMADA,
          "Código SSA (antes registrado como SAUDE). Visto em resenha real como 'GRUPO SAUDE'."),
    Grupo("GAJ", "Apoio Judiciário", r"\bGAJ\b|APOIO\s+JUDICIARIO", CONFIRMADA, "Visto também como GAJ-1700."),
    Grupo("FAP", "Fiscalização Agropecuária", r"\bFAP\b|FISCALIZACAO\s+AGROPECUARIA", CONFIRMADA,
          "Visto também como FAP-1300."),
    Grupo("AST", "Técnicos Administrativos", r"\bAST\b", CONFIRMADA,
          "Visto como 'Grupo TECNICO ADMINISTRATIVO - AST -'. A expressão 'TEC. ADM' NÃO é tratada como AST "
          "sem decisão da GEDIV (ver EXPRESSOES_SEM_GRUPO)."),
    Grupo("ANS", "Nível Superior", r"\bANS\b|ATIVIDADES\s+DE\s+NIVEL\s+SUPERIOR", PROVISORIA),
    Grupo("ESP", "Grupo Especial", r"\bESP\b|GRUPO\s+(?:OCUPACIONAL\s+)?ESPECIAL", PROVISORIA,
          "Código ESP (antes registrado como ESPECIAL)."),
    Grupo("DPS", "Divulgação e Promoção", r"\bDPS\b|DIVULGACAO\s+E\s+PROMOCAO", PROVISORIA),
    Grupo("SFT", "Fazenda · Auditor Fiscal", r"\bSFT\b|SERVIDORES\s+FISCAIS\s+TRIBUTARIOS|"
          r"(?:GRUPO|PROFISSI\w*)\s+(?:D[AO]\s+)?FAZENDA|AUDITOR(?:ES)?\s+FISCA(?:L|IS)\s+TRIBUTARIOS?", CONFIRMADA,
          "Visto como 'profissionais da Fazenda'. A sigla 'STF' NÃO é tratada como SFT sem comprovação "
          "(ver EXPRESSOES_SEM_GRUPO)."),
    Grupo("OSPB", "Orquestra Sinfônica", r"\bOSPB\b|ORQUESTRA\s+SINFONICA", PROVISORIA),
    Grupo("GPC", "Polícia Civil", r"\bGPC\b|GRUPO\s+(?:OCUPACIONAL\s+)?(?:D[AE]\s+)?POLICIA\s+CIVIL", PROVISORIA),
    Grupo("SEI", "Informática", r"\bSEI\b|GRUPO\s+(?:DE\s+)?INFORMATICA", PROVISORIA),
    Grupo("SAT", "Área Tecnológica", r"\bSAT\b|AREA\s+TECNOLOGICA", PROVISORIA),
    Grupo("ACI", "Auditoria e Controle Interno", r"\bACI\b|AUDITORIA\s+E\s+CONTROLE\s+INTERNO", PROVISORIA),
    Grupo("PPGG", "PPGG", r"\bPPGG\b|POLITICAS\s+PUBLICAS\s+E\s+GESTAO", PROVISORIA,
          "O documento oficial lista a sigla sem a denominação."),
    # INT: incluído por regra da GEDIV; denominação e expressões ainda não confirmadas. Só a sigla em forma
    # inequívoca de grupo é reconhecida ("GRUPO INT", "INT-1234"), nunca "INT" solto no texto.
    Grupo("INT", "INT (denominação a confirmar)", r"GRUPO\s+(?:OCUPACIONAL\s+)?INT\b|\bINT\s*-\s*\d{3,4}\b", PROVISORIA,
          "Expressões a confirmar pela GEDIV."),
)
GRUPO_POR_CODIGO = {g.codigo: g for g in GRUPOS}
CODIGOS_GRUPOS = ("MAG", "SSA", "GAJ", "FAP", "AST", "ANS", "ESP", "DPS", "SFT", "OSPB", "GPC", "SEI", "SAT", "ACI",
                  "PPGG", "INT")
_ORDEM_AVALIACAO = ("AST", "GAJ", "FAP", "SSA", "SFT", "GPC", "OSPB", "ACI", "DPS", "PPGG", "ANS",
                    "ESP", "SEI", "SAT", "INT", "MAG")
GRUPOS_AVALIACAO = tuple(GRUPO_POR_CODIGO[c] for c in _ORDEM_AVALIACAO)
assert tuple(g.codigo for g in GRUPOS) == CODIGOS_GRUPOS
assert len(GRUPOS) == len(GRUPOS_AVALIACAO) == len(set(_ORDEM_AVALIACAO)) == 16

# Expressões vistas em resenhas reais que NÃO têm grupo homologado: o ato fica sem grupo, com a expressão
# literal guardada e uma pendência — nunca é atribuído por aproximação a um dos 16 grupos.
EXPRESSOES_SEM_GRUPO = (
    ("TEC. ADM", r"\bTEC\.?\s*ADM\b", "expressão 'TEC. ADM' sem grupo homologado: a GEDIV precisa decidir se corresponde a AST"),
    ("STF", r"\bSTF\b", "sigla 'STF' sem grupo homologado: a equivalência com SFT não está comprovada"),
)


@dataclass(frozen=True)
class Subcategoria:
    codigo: str
    nome: str
    padrao: str


# As sete subcategorias de Tempo de Serviço, na ordem oficial. Não existe oitava categoria:
# "abono de permanência", "averbação", "certidão" e afins ficam como conceitos candidatos.
SUBCATEGORIAS = (
    Subcategoria("TS-01", "Anotação de Tempo de Serviço/Contribuição", r"ANOTACAO\s+(?:DE\s+)?TEMPO"),
    Subcategoria("TS-02", "Desaverbação de Tempo de Serviço", r"DESAVERBACAO"),
    Subcategoria("TS-03", "Licença para Tratar de Interesses Particulares",
                 r"LICENCA\s+(?:PARA\s+)?(?:TRATO|TRATAR)\s+DE\s+INTERESSES?\s+PARTICULAR"),
    Subcategoria("TS-04", "Desistência de Licença de Interesse Particular", r"DESISTENCIA\s+D[AE]\s+LICENCA"),
    Subcategoria("TS-05", "Licença Especial", r"LICENCA\s+ESPECIAL"),
    Subcategoria("TS-06", "Conversão de Licença Especial em Tempo de Serviço", r"CONVERSAO\s+D[AE]\s+LICENCA\s+ESPECIAL"),
    Subcategoria("TS-07", "Conversão de Férias", r"CONVERSAO\s+D[AE]\s+FERIAS"),
)
SUBCATEGORIA_POR_CODIGO = {s.codigo: s for s in SUBCATEGORIAS}
# Casos específicos antes dos genéricos: "desistência de licença" antes de "licença para tratar",
# "conversão de licença especial" antes de "licença especial".
_ORDEM_SUB = ("TS-04", "TS-06", "TS-07", "TS-02", "TS-01", "TS-03", "TS-05")
assert len(SUBCATEGORIAS) == 7

# Conceitos candidatos: reconhecidos para triagem, nunca classificados nos dois eixos.
CONCEITOS_CANDIDATOS = (
    ("Abono de Permanência", r"ABONO\s+DE\s+PERMANENCIA"),
    ("Averbação de Tempo", r"(?<!DES)AVERBACAO\s+D[EO]\s+TEMPO"),
    ("Certidão de Tempo", r"CERTIDAO\s+DE\s+TEMPO"),
)

# Alterações de publicação (dimensão B) e quais contam para o indicador REFEITOS (dimensão C).
ORIGINAL = "ORIGINAL"
RETIFICACAO, CORRECAO, REPUBLICACAO, SEM_EFEITO = "RETIFICACAO", "CORRECAO", "REPUBLICACAO", "TORNADO_SEM_EFEITO"
ALTERACOES = {RETIFICACAO: "Retificação", CORRECAO: "Correção", REPUBLICACAO: "Republicação",
              SEM_EFEITO: "Tornado sem efeito"}
TIPOS_REFEITO = (RETIFICACAO, CORRECAO, REPUBLICACAO)

# Página "Outras publicações" pedida no documento oficial.
OUTRAS = {"REPUBLICADO_POR_INCORRECAO": "Republicado por incorreção", "PORTARIA": "Portaria",
          "ATO_NORMATIVO": "Ato Normativo", "ALTERACAO_LEI": "Alterações na Lei",
          "TEMA_FORA_DOS_EIXOS": "Tema GEDIV fora dos dois eixos"}


def expressao_sem_grupo(preambulo_normalizado: str) -> tuple[str, str] | None:
    """(expressão literal, pendência) quando o preâmbulo usa uma expressão de grupo sem homologação."""
    for _rotulo, padrao, pendencia in EXPRESSOES_SEM_GRUPO:
        achado = re.search(padrao, preambulo_normalizado)
        if achado:
            return achado.group(0), pendencia
    return None


def identificar_grupo(preambulo_normalizado: str) -> tuple[str | None, str | None]:
    """Código do grupo e a expressão literal que o demonstra. Sem expressão reconhecida: (None, None).
    Expressão sem grupo homologado (TEC. ADM, STF) tem precedência: devolve (None, expressão)."""
    sem_grupo = expressao_sem_grupo(preambulo_normalizado)
    if sem_grupo:
        return None, sem_grupo[0]
    for grupo in GRUPOS_AVALIACAO:
        achado = re.search(grupo.padrao, preambulo_normalizado)
        if achado:
            return grupo.codigo, achado.group(0)
    return None, None


def identificar_subcategoria(preambulo_normalizado: str) -> str | None:
    for codigo in _ORDEM_SUB:
        if re.search(SUBCATEGORIA_POR_CODIGO[codigo].padrao, preambulo_normalizado):
            return codigo
    return None


def identificar_condicao(preambulo_normalizado: str) -> str:
    if re.search(r"\bCONDICIONAL\b|\bSOB\s+CONDICAO\b", preambulo_normalizado):
        return "CONDICIONAL"
    return "PLENA" if re.search(r"\bPLENA\b", preambulo_normalizado) else "NAO_INFORMADA"


def como_dicionario() -> dict:
    return {
        "versao": VERSAO_REGRAS,
        "eixos": [{"codigo": c, "nome": n} for c, n in EIXOS.items()],
        "modalidades": [{"codigo": c, "nome": n} for c, n in MODALIDADES.items()],
        "condicoes": [{"codigo": c, "nome": n} for c, n in CONDICOES.items()],
        "grupos": [{"codigo": g.codigo, "nome": g.nome, "estado": g.estado, "observacao": g.observacao} for g in GRUPOS],
        "expressoes_sem_grupo": [{"expressao": r, "pendencia": p} for r, _padrao, p in EXPRESSOES_SEM_GRUPO],
        "subcategorias": [{"codigo": s.codigo, "nome": s.nome} for s in SUBCATEGORIAS],
        "alteracoes": [{"codigo": c, "nome": n} for c, n in ALTERACOES.items()],
        "outras": [{"codigo": c, "nome": n} for c, n in OUTRAS.items()],
    }
