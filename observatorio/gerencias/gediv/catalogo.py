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

VERSAO_REGRAS = "gediv-2026.11.14-1"   # 05.3.4: dois grupos no mesmo ato e TS-04/TS-06 sem o requisito viram pendência
# (antes: "gediv-2026.11.12-1" — grupos definitivos (SSA, ESP, INT), TEC. ADM e STF sem grupo, exclusões)

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
    Grupo("MAG", "Magistério",
          r"\bMAG\b|MAGISTERIO|PROFISSI\w*\s+(?:D[AE]\s+)?EDUCACAO|(?:LEI\s*(?:N[O°.]*\s*)?)?7\.?419\s*/\s*(?:03|2003)",
          CONFIRMADA,
          "Inclui evidência normativa 'profissinais de Educação' e Lei nº 7.419/03."),
    Grupo("SSA", "Saúde",
          r"\bSSA\b|GRUPO\s+(?:OCUPACIONAL\s+)?(?:DA\s+)?SAUDE|PROFISSI\w*\s+(?:D[AE]\s+)?SAUDE|"
          r"DA\s+SAUDE\s+PROFISSI\w*|(?:LEI\s*(?:N[O°.]*\s*)?)?7\.?376\s*/\s*(?:03|2003)",
          CONFIRMADA,
          "Código SSA (antes registrado como SAUDE). Inclui 'profissinais da Saúde' e Lei nº 7.376/03."),
    Grupo("GAJ", "Apoio Judiciário",
          r"\bGAJ\b|APOIO\s+JUDICIARIO|(?:LEI\s*(?:N[O°.]*\s*)?)?11\.?359\s*/\s*(?:19|2019)",
          CONFIRMADA, "Visto também como GAJ-1700 e Lei nº 11.359/2019."),
    Grupo("FAP", "Fiscalização Agropecuária", r"\bFAP\b|FISCALIZACAO\s+AGROPECUARIA", CONFIRMADA,
          "Visto também como FAP-1300."),
    Grupo("AST", "Técnicos Administrativos",
          r"\bAST\b|(?:LEI\s*(?:N[O°.]*\s*)?)?14\.?386\s*/\s*2026",
          CONFIRMADA,
          "Grupo canônico AST — Técnicos Administrativos (Lei nº 14.386/2026). "
          "'TEC. ADM' é normalizado para AST em registros compatíveis preservando grupo_expressao original."),
    Grupo("ANS", "Nível Superior", r"\bANS\b|ATIVIDADES\s+DE\s+NIVEL\s+SUPERIOR", PROVISORIA),
    Grupo("ESP", "Grupo Especial", r"\bESP\b|GRUPO\s+(?:OCUPACIONAL\s+)?ESPECIAL", PROVISORIA,
          "Código ESP (antes registrado como ESPECIAL)."),
    Grupo("DPS", "Divulgação e Promoção", r"\bDPS\b|DIVULGACAO\s+E\s+PROMOCAO", PROVISORIA),
    Grupo("SFT", "Fazenda · Auditor Fiscal",
          r"\bSFT\b|SERVIDORES\s+FISCAIS\s+TRIBUTARIOS|(?:GRUPO|PROFISSI\w*)\s+(?:D[AO]\s+)?FAZENDA|"
          r"AUDITOR(?:ES)?\s+FISCA(?:L|IS)\s+TRIBUTARIOS?|(?:LEI\s*(?:N[O°.]*\s*)?)?8\.?427\s*/\s*(?:07|2007)",
          CONFIRMADA,
          "Inclui 'profissinais da Fazenda', Lei nº 8.427/07 e 'STF' quando verificado com enquadramento fiscal/tributário."),
    Grupo("OSPB", "Orquestra Sinfônica", r"\bOSPB\b|ORQUESTRA\s+SINFONICA", PROVISORIA),
    Grupo("GPC", "Polícia Civil", r"\bGPC\b|GRUPO\s+(?:OCUPACIONAL\s+)?(?:D[AE]\s+)?POLICIA\s+CIVIL", PROVISORIA),
    Grupo("SEI", "Informática", r"\bSEI\b|GRUPO\s+(?:DE\s+)?INFORMATICA", PROVISORIA),
    Grupo("SAT", "Área Tecnológica", r"\bSAT\b|AREA\s+TECNOLOGICA", PROVISORIA),
    Grupo("ACI", "Auditoria e Controle Interno",
          r"\bACI\b|AUDITORIA\s+E\s+CONTROLE\s+INTERNO|PROFISSI\w*\s+(?:DA\s+)?CGE|"
          r"(?:LEI\s*(?:N[O°.]*\s*)?)?8\.?698\s*/\s*(?:08|2008)",
          PROVISORIA,
          "Inclui evidência normativa 'profissinais CGE' e Lei nº 8.698/08 (Auditor de Contas Públicas)."),
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

# Expressões com normalização condicional sujeita a compatibilidade de contexto/cargo.
# Registros incompatíveis ou ambíguos permanecem sem grupo atribuído, preservando a expressão original.
EXPRESSOES_SEM_GRUPO = (
    ("TEC. ADM", r"\bTEC\.?\s*-?\s*ADM\b", "expressão 'TEC. ADM' incompatível ou ambígua com o contexto/cargo do ato: grupo AST não atribuído automaticamente"),
    ("STF", r"\bSTF\b", "sigla 'STF' sem cargo ou enquadramento fiscal/tributário verificado: grupo SFT não atribuído automaticamente"),
)

_PAT_TEC_ADM = re.compile(r"\bTEC\.?\s*-?\s*ADM\b")
_PAT_STF = re.compile(r"\bSTF\b")
_PAT_CARGO_COMPATIVEL_AST = re.compile(r"TECNIC[OA]?\s+ADMIN|TEC\.?\s*-?\s*ADM|ASSISTENTE\s+ADMIN|AUXILIAR\s+ADMIN")
_PAT_CARGO_INCOMPATIVEL_AST = re.compile(
    r"PROFESSOR|MAGISTERIO|POLICIAL|AUDITOR\s+FISCAL|FISCAL\s+TRIBUTAR|MEDIC[OA]|ENFERMEIR|"
    r"DELEGAD|AUDITOR\s+DE\s+CONTAS|FISCAL\s+ESTADUAL\s+AGROPECUAR|FARMACEUT|FISIOTERAP|PSICOLOG|ODONTOLOG"
)
_PAT_CARGO_COMPATIVEL_SFT = re.compile(r"AUDITOR\s*FISCAL|FISCAL\s*TRIBUTAR|TRIBUTAR|FAZENDA")
_PAT_CARGO_INCOMPATIVEL_SFT = re.compile(
    r"PROFESSOR|TECNIC[OA]?\s+ADMIN|POLICIAL|MEDIC[OA]|ENFERMEIR|DELEGAD|FARMACEUT|FISIOTERAP|AUDITOR\s+DE\s+CONTAS"
)
_PAT_ENQUADRAMENTO_SFT = re.compile(
    r"\bSFT\b|AUDITOR(?:ES)?\s+FISCA(?:L|IS)\s+TRIBUTARIOS?|FISCAL\s+TRIBUTARIO|"
    r"SERVIDORES\s+FISCAIS\s+TRIBUTARIOS|FAZENDA|(?:LEI\s*(?:N[O°.]*\s*)?)?8\.?427\s*/\s*(?:07|2007)"
)
_PAT_CARGO_INCOMPATIVEL_ACI = re.compile(
    r"PROFESSOR|TECNIC[OA]?\s+ADMIN|POLICIAL|AUDITOR\s+FISCAL|MEDIC[OA]|ENFERMEIR|DELEGAD"
)

# Padrões longos/inequívocos para fallback em preâmbulos com letras espaçadas ("G A J - 1 7 0 0", "L e i 1 1 . 3 5 9 / 2 0 1 9").
# Nunca inclui siglas curtas de 3 letras sem delimitador (ex.: MAG, AST, INT, STF) para evitar falsos positivos.
_GRUPOS_COMPACTOS = (
    ("GAJ", re.compile(r"GAJ-?1700|APOIOJUDICIARIO|(?:LEIN?[O°.]*)?11\.?359/(?:19|2019)")),
    ("MAG", re.compile(r"MAGISTERIO|PROFISSI\w*(?:D[AE])?EDUCACAO|(?:LEIN?[O°.]*)?7\.?419/(?:03|2003)")),
    ("SSA", re.compile(r"GRUPO(?:OCUPACIONAL)?(?:DA)?SAUDE|PROFISSI\w*(?:D[AE])?SAUDE|DASAUDEPROFISSI\w*|(?:LEIN?[O°.]*)?7\.?376/(?:03|2003)")),
    ("AST", re.compile(r"GRUPO(?:OCUPACIONAL)?TECNICOADMINISTRATIVO|(?:LEIN?[O°.]*)?14\.?386/2026")),
    ("SFT", re.compile(r"SERVIDORESFISCAISTRIBUTARIOS|AUDITOR(?:ES)?FISCA(?:L|IS)TRIBUTARIOS?|(?:LEIN?[O°.]*)?8\.?427/(?:07|2007)")),
    ("ACI", re.compile(r"AUDITORIAECONTROLEINTERNO|(?:LEIN?[O°.]*)?8\.?698/(?:08|2008)")),
    ("FAP", re.compile(r"FAP-?1300|FISCALIZACAOAGROPECUARIA")),
    ("ANS", re.compile(r"ANS-?900|ATIVIDADESDENIVELSUPERIOR")),
    ("DPS", re.compile(r"DPS-?1600|DIVULGACAOEPROMOCAO")),
    ("OSPB", re.compile(r"ORQUESTRASINFONICA")),
    ("GPC", re.compile(r"GRUPO(?:OCUPACIONAL)?(?:D[AE])?POLICIACIVIL")),
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
    # TS-04 exige que a licença objeto da desistência seja a de interesses particulares (Etapa 05.3.4).
    Subcategoria("TS-04", "Desistência de Licença de Interesse Particular",
                 r"DESISTENCIA\s+D[AE]\s+LICENCA\s+(?:\S+\s+){0,8}?INTERESSES?\s+PARTICULAR"),
    Subcategoria("TS-05", "Licença Especial", r"LICENCA\s+ESPECIAL"),
    # TS-06 exige a conversão EM TEMPO de serviço/contribuição (conversão em pecúnia não é TS-06; Etapa 05.3.4).
    Subcategoria("TS-06", "Conversão de Licença Especial em Tempo de Serviço",
                 r"CONVERSAO\s+D[AE]\s+LICENCA\s+ESPECIAL\s+(?:\S+\s+){0,4}?(?:EM|PARA)\s+(?:FINS\s+DE\s+)?(?:CONTAGEM\s+(?:DE\s+)?)?"
                 r"(?:DOBRO\s+(?:D[OE]\s+)?)?TEMPO\s+DE\s+(?:SERVICO|CONTRIBUICAO)"),
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


def grupos_presentes(preambulo_normalizado: str) -> list[tuple[str, str]]:
    """Todos os grupos cuja expressão aparece no preâmbulo: [(código, expressão literal)], na ordem do texto."""
    achados = []
    for grupo in GRUPOS_AVALIACAO:
        achado = re.search(grupo.padrao, preambulo_normalizado)
        if achado:
            achados.append((achado.start(), grupo.codigo, achado.group(0)))
    return [(c, e) for _, c, e in sorted(achados)]


def avaliar_grupo(preambulo_normalizado: str, *, cargos=None) -> tuple[str | None, str | None, str | None]:
    """(código, expressão, pendência).
    - Dois ou mais grupos distintos no mesmo ato NÃO são resolvidos pela ordem dos padrões (fica sem grupo + pendência).
    - 'TEC. ADM' normaliza para 'AST' em registros compatíveis (sem conflito com outro grupo ou cargo incompatível),
      preservando a expressão original em `grupo_expressao`.
    - 'STF' normaliza para 'SFT' somente quando há cargo ou enquadramento fiscal/tributário verificado e sem conflito,
      preservando a expressão original 'STF'. Registros ambíguos ou incompatíveis ficam sem grupo.
    - Quando o preâmbulo possui letras espaçadas ("G A J - 1 7 0 0", "L e i 1 1 . 3 5 9 / 2 0 1 9"), aplica fallback
      compacto restrito a expressões longas/normativas inequívocas.
    """
    cargos_norm = [normalizar(c) for c in (cargos or ()) if str(c or "").strip()]
    presentes = grupos_presentes(preambulo_normalizado)
    codigos_presentes = {c for c, _ in presentes}

    m_tec = _PAT_TEC_ADM.search(preambulo_normalizado)
    if m_tec:
        exp_lit = m_tec.group(0)
        outros = codigos_presentes - {"AST"}
        cargo_incomp = (
            bool(cargos_norm)
            and any(_PAT_CARGO_INCOMPATIVEL_AST.search(c) for c in cargos_norm)
            and not any(_PAT_CARGO_COMPATIVEL_AST.search(c) for c in cargos_norm)
        )
        if outros or cargo_incomp:
            return None, exp_lit, EXPRESSOES_SEM_GRUPO[0][2]
        return "AST", exp_lit, None

    m_stf = _PAT_STF.search(preambulo_normalizado)
    if m_stf and "SUPREMO TRIBUNAL FEDERAL" not in preambulo_normalizado:
        outros = codigos_presentes - {"SFT"}
        enquadramento_ok = bool(_PAT_ENQUADRAMENTO_SFT.search(preambulo_normalizado)) or any(
            _PAT_CARGO_COMPATIVEL_SFT.search(c) for c in cargos_norm
        )
        cargo_incomp = bool(cargos_norm) and any(_PAT_CARGO_INCOMPATIVEL_SFT.search(c) for c in cargos_norm)
        if enquadramento_ok and not outros and not cargo_incomp:
            return "SFT", "STF", None
        return None, "STF", EXPRESSOES_SEM_GRUPO[1][2]

    if len(presentes) > 1:
        codigos = ", ".join(c for c, _ in presentes)
        return None, " | ".join(e for _, e in presentes), f"mais de um grupo do PCCR no mesmo ato ({codigos}); grupo não atribuído"
    if presentes:
        codigo, expressao = presentes[0]
        if codigo == "ACI" and "CGE" in expressao and "8.698" not in preambulo_normalizado and "8698" not in preambulo_normalizado:
            if cargos_norm and any(_PAT_CARGO_INCOMPATIVEL_ACI.search(c) for c in cargos_norm):
                return None, expressao, "expressão 'CGE' com cargo incompatível com ACI; grupo não atribuído automaticamente"
        return codigo, expressao, None

    # Fallback compacto seguro para preâmbulos com letras espaçadas ("G A J - 1 7 0 0", "L e i 1 1 . 3 5 9 / 2 0 1 9")
    comp = compactar(preambulo_normalizado)
    achados_comp = []
    for codigo, padrao in _GRUPOS_COMPACTOS:
        m = padrao.search(comp)
        if m:
            achados_comp.append((m.start(), codigo, m.group(0)))
    achados_comp.sort()
    if len(achados_comp) > 1:
        codigos = ", ".join(c for _, c, _ in achados_comp)
        return None, " | ".join(e for _, _, e in achados_comp), f"mais de um grupo do PCCR no mesmo ato ({codigos}); grupo não atribuído"
    if len(achados_comp) == 1:
        return achados_comp[0][1], achados_comp[0][2], None
    return None, None, None


def identificar_grupo(preambulo_normalizado: str, *, cargos=None) -> tuple[str | None, str | None]:
    """Código do grupo e a expressão literal que o demonstra. Sem expressão reconhecida: (None, None).
    Expressões condicionais ('TEC. ADM', 'STF') preservam a expressão literal original e só normalizam quando
    compatíveis com o contexto/cargo. Mais de um grupo: (None, expressões) — ver `avaliar_grupo`."""
    codigo, expressao, _ = avaliar_grupo(preambulo_normalizado, cargos=cargos)
    return codigo, expressao


def _sem_espacos(padrao: str) -> str:
    """Versão do padrão para texto COMPACTO (sem nenhum espaço): "\\s+" e "\\s*" deixam de exigir espaço."""
    return re.sub(r"\\s[+*]", "", padrao)


_SUB_COMPACTA = {s.codigo: re.compile(_sem_espacos(s.padrao)) for s in SUBCATEGORIAS}


def compactar(texto_normalizado: str) -> str:
    return re.sub(r"\s+", "", texto_normalizado)


# Expressões que ABREM um assunto específico mas não trazem o requisito dele (Etapa 05.3.4). Elas impedem que o ato
# caia num assunto genérico por aproximação ("desistência de licença especial" não é Licença Especial; "conversão de
# licença especial em pecúnia" não é TS-06 nem TS-05): o ato fica em Tempo de Serviço sem assunto, com pendência.
_SUB_INCOMPLETAS = (
    ("TS-04", r"DESISTENCIA\s+D[AE]\s+LICENCA",
     "desistência de licença sem indicação de que é a licença para tratar de interesses particulares (TS-04 exige)"),
    ("TS-06", r"CONVERSAO\s+D[AE]\s+LICENCA\s+ESPECIAL",
     "conversão de licença especial sem indicação de conversão em tempo de serviço (TS-06 exige)"),
)
_SUB_INCOMPLETAS_COMPACTAS = tuple((c, re.compile(_sem_espacos(p)), m) for c, p, m in _SUB_INCOMPLETAS)


def avaliar_subcategoria(preambulo_normalizado: str, compacto: bool = False) -> tuple[str | None, str | None]:
    """(subcategoria, pendência). Assunto específico sem o seu requisito: (None, pendência) — o ato é de Tempo de
    Serviço, mas o assunto fica para a gerência; nunca vai para o assunto genérico mais próximo."""
    for codigo in _ORDEM_SUB:
        padrao = _SUB_COMPACTA[codigo] if compacto else SUBCATEGORIA_POR_CODIGO[codigo].padrao
        if re.search(padrao, preambulo_normalizado):
            return codigo, None
        for incompleta, padrao_incompleto, pendencia in (_SUB_INCOMPLETAS_COMPACTAS if compacto else _SUB_INCOMPLETAS):
            if incompleta == codigo and re.search(padrao_incompleto, preambulo_normalizado):
                return None, pendencia
    return None, None


def identificar_subcategoria(preambulo_normalizado: str, compacto: bool = False) -> str | None:
    """Subcategoria de Tempo de Serviço. Com `compacto=True`, o texto deve vir sem espaços (ver `compactar`):
    recurso para palavras coladas ou partidas pela extração do PDF; só deve ser usado quando a busca normal falhar."""
    return avaliar_subcategoria(preambulo_normalizado, compacto)[0]


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
