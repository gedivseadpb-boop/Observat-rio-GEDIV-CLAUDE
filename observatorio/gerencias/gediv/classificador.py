"""Classificação GEDIV do texto de uma edição, em duas camadas.

Camada institucional: delimita cada ato (resenha ou portaria) e verifica se ele demonstra
vínculo com a GEDIV. Somente depois vem a camada temática: eixo, modalidade ou subcategoria,
condição, grupo, resultado e alteração de publicação.

Princípios (Especificação V3 e registro de decisões do projeto):
- palavra-chave é gatilho, não prova: tudo o que sai daqui é CANDIDATO, pendente de conferência humana;
- menção apenas à DEREH não comprova GEDIV: o ato fica com vínculo NAO_EXPRESSO, sinalizado;
- ato de outra gerência é descartado, mesmo com tema parecido;
- o que está ausente ou ambíguo fica "não informado", nunca é preenchido;
- resenha, decisão e processo são unidades distintas; republicação não vira decisão nova.

A entrada é o texto de cada página já reconstruído coluna a coluna pela leitura.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from . import catalogo as C
from . import exclusoes as EX

# Número do processo/documento. O separador antes do número final é "/" (SAD-PSE-2026/12345) ou, em ofícios
# da Polícia Civil, "-" (SDS-OFI-AAAA-NNNNN, DOE 07/11/2026): ambos aceitos e guardados COMO PUBLICADOS.
PAT_PROCESSO = re.compile(r"\b([A-Z]{2,6})\s*-\s*(PSE|PRC|OFI)\s*-\s*(\d{4})\s*([/-])\s*(\d{3,9})\b")
PAT_RESENHA = re.compile(r"\bRESENHA\s*(?:N[O°.]*)?\s*:?\s*(\d{1,5})\s*/\s*(20\d{2})((?:\s*[-/]\s*[A-Z]{2,10})*)")
PAT_PORTARIA = re.compile(r"^PORTARIA\s+N[O°.]*\s*(\d{1,5})\s*/\s*(20\d{2})")
# Etapa 05.3.4: a portaria também é reconhecida quando, antes do número, só há nomes de unidades na mesma linha
# ("GERENCIA EXECUTIVA ... PORTARIA Nº 12/2026-GEDIV"); o sufixo (-GEDIV, -DEREH) é guardado como na resenha.
PAT_PORTARIA_LIVRE = re.compile(r"\bPORTARIA\s+N[O°.]*\s*:?\s*(\d{1,5})\s*/\s*(20\d{2})((?:\s*[-/]\s*[A-Z]{2,10})*)")
# Processo publicado com grafia que não fecha o padrão ("SAD-PSE-2O26/12345", "SAD-PSE-2026/"): a linha é uma
# decisão, mas o número não é reconstituído.
PAT_PROCESSO_SUSPEITO = re.compile(r"\b[A-Z0-9]{2,6}\s*-\s*(?:PSE|PRC|OFI)\s*-\s*[\dA-Z/ .-]{0,14}")
# Título de bloco de mérito numa resenha mista ("DEFERIDOS:", "PROCESSOS INDEFERIDOS").
PAT_TITULO_MERITO = re.compile(r"^\W*(?:(?:PROCESSOS?|REQUERIMENTOS?|PEDIDOS?)\s+)?(IN)?DEFERID[OA]S?\b\W*(?:\([^)]*\))?\W*$")
MARCA_AMBIGUA = "[LINHA DE TABELA SEM ATRIBUICAO SEGURA]"   # pagina.MARCA_AMBIGUA, já normalizada
PAT_EXPEDIENTE = re.compile(r"EXPEDIENTE(?:\s+DO\s+DIA)?\s*:?\s*(\d{2})[-/.](\d{2})[-/.](20\d{2})")
PAT_GEDIV = re.compile(r"GER(?:ENCIA|\.)\s+EXEC(?:UTIVA|\.)\s+(?:D[EA]\s+)?CONC(?:ESSAO|\.)?\s*(?:D[EA]\s+)?"
                       r"DIREITOS\s+E\s+VANTAGENS|\bGEDIV\b")
PAT_OUTRA_GERENCIA = re.compile(r"GER(?:ENCIA|\.)\s+(?:EXECUTIVA|EXEC\.|OPERACIONAL|OPER\.)\s+(?!.{0,40}DIREITOS\s+E\s+VANTAGENS)")
PAT_DEREH = re.compile(r"\bDEREH\b|DIRETORI?A?\s+EXECUTIV[OA]\s+DE\s+RECURSOS\s+HUMANOS")
PAT_CABECALHO_UNIDADE = re.compile(r"^(?:SECRETARIA\s+DE\s+ESTADO|DIRETORIA\s+EXECUTIVA|GER(?:ENCIA|\.)\s+(?:EXEC|OPER)|GOVERNO\s+DO\s+ESTADO)")
PAT_OUTRA_SECRETARIA = re.compile(r"^SECRETARIA\s+DE\s+ESTADO\s+D[AEO]S?\s+(?!ADMINISTRACAO\b)")
PAT_PUBLIQUE = re.compile(r"^\W*PUBLIQUE-?\s?SE")
PAT_MOBILIARIO = re.compile(r"^(?:\d{1,3}\s+)?JOAO\s+PESSOA\s*-\s*[\w-]+\s*,\s*\d{1,2}\s+DE\s+\w+\s+DE\s+20\d{2}"
                            r"(?:\s+DIARIO\s+OFICIAL)?(?:\s+\d{1,3})?$|^DIARIO\s+OFICIAL\s+JOAO\s+PESSOA\b.{0,60}$")
PAT_MERITO = re.compile(r"\b(IN)?DEFER(?:I(?:U|R|D[AO]S?|MOS|MENTO)|E)\b")
PAT_MATRICULA = re.compile(r"(?<![\w/.-])(\d{3}\.\d{3}-\d|\d{5,7}-\d|\d{6,8})(?![\w/-])")
PAT_PROGRESSAO = re.compile(r"PROGRESSAO\s+FUNCIONAL|PROGRESSAO\s+(?:HORIZONTAL|VERTICAL)")
# Referência à publicação do ato ORIGINAL dentro de uma retificação, republicação ou "sem efeito":
# "publicado no D.O.E. edição do dia 28/07/1999" (DOE 10/11/2026, Portaria 008/2026-DEREH).
PAT_PUBLICACAO_CITADA = re.compile(r"PUBLICAD[OA]S?\s+NO\s+D\.?\s*O\.?\s*E?\.?\s*(?:,\s*)?(?:EDICAO\s+)?(?:DO\s+DIA\s+|DE\s+)?"
                                   r"(\d{2})[/.](\d{2})[/.](\d{4})")
# Processo antigo citado nesses atos, no formato "999.999-9" — só quando precedido da palavra PROCESSO
# (o mesmo formato é usado para matrículas).
PAT_PROCESSO_ANTIGO = re.compile(r"PROCESSO\s+(?:N[O°.]*\s*)?(\d{2,3}\.\d{3}-\d)\b")
PAT_REF_RESENHA = re.compile(r"RESENHA\s*(?:N[O°.]*)?\s*:?\s*(\d{1,5})\s*/\s*(20\d{2})")

_ALTERACOES = (
    (C.SEM_EFEITO, re.compile(r"TORN(?:A|AR|OU|O|AD[AO]S?)\s+SEM\s+EFEITO")),
    (C.REPUBLICACAO, re.compile(r"REPUBLICA(?:D[AO]S?|CAO|R|-SE)\b")),
    (C.RETIFICACAO, re.compile(r"RETIFICA|ONDE\s+SE\s+LE\b|\bLEIA-SE\b")),
    (C.CORRECAO, re.compile(r"\bCORRECAO\b|\bCORRIG")),
)
_CARGOS = (r"TECNIC|PROFESSOR|POLICIAL|FISCAL|AUDITOR|AGENTE|ANALISTA|AUXILIAR|ASSISTENTE|ENFERMEIR|MEDIC[OA]|"
           r"PSICOLOG|MOTORISTA|DELEGAD|ESCRIVA|PERITO|MUSICO|FARMACEUT|FISIOTERAP|FONOAUDIOLOG|NUTRICIONISTA|"
           r"ODONTOLOG|BIOQUIMIC|ATENDENTE|ENGENHEIR|ADVOGAD|CONTADOR|ADMINISTRADOR|ARQUIVISTA|BIBLIOTECARI|"
           r"PEDAGOG|REGENTE|SUPERVISOR|ORIENTADOR|INSPETOR|VIGILANTE|DIGITADOR|PROGRAMADOR|GESTOR|ESPECIALISTA|"
           r"INVESTIGADOR|PAPILOSCOPIST|COMISSARI|NECROTOMIST")
PAT_NOME = re.compile(r"^([A-Z][A-Z .'-]{4,80}?)\s*(?=\*|\d|$|\s(?:" + _CARGOS + r"|SEC\.|SECRETARIA\b))")

MAX_LINHAS_RESENHA = 600
MAX_LINHAS_PORTARIA = 30
EXPRESSO, NAO_EXPRESSO = "EXPRESSO", "NAO_EXPRESSO"


@dataclass
class Linha:
    pagina: int
    texto: str
    norm: str


@dataclass
class Ato:
    id: str
    tipo: str                      # RESENHA | PORTARIA
    numero: str | None
    sufixo: str | None
    pagina: int
    pagina_final: int
    data_expediente: str | None
    vinculo: str
    expressao_vinculo: str | None
    natureza: str
    eixo: str | None
    modalidade: str | None
    condicao: str | None
    grupo: str | None
    grupo_expressao: str | None
    subcategoria: str | None
    resultado: str
    texto: str
    pendencias: list[str] = field(default_factory=list)


@dataclass
class Decisao:
    id: str
    ato_id: str
    pagina: int
    processo: str | None           # None: decisão sem processo reconhecido (Etapa 05.3.4), nunca um número presumido
    servidor: str | None
    matricula: str | None
    lotacao: str | None
    cargo: str | None
    detalhe: dict
    resultado: str
    trecho: str


@dataclass
class Evento:
    id: str
    ato_id: str | None
    tipo: str
    subtipo: str | None
    pagina: int
    modificador: str | None
    resenhas_citadas: list[str]
    processos_citados: list[str]
    vinculo: str
    texto: str
    publicacoes_citadas: list[str] = field(default_factory=list)   # datas (AAAA-MM-DD) de edições do DOE citadas no ato


@dataclass
class Outra:
    id: str
    tipo: str
    pagina: int
    titulo: str
    vinculo: str
    trecho: str


@dataclass
class ForaEscopo:
    """Ato reconhecido e EXCLUÍDO do escopo GEDIV (licença-saúde, vacância, outra gerência). Registro privado."""
    id: str
    tipo: str
    numero: str | None
    pagina: int
    titulo: str
    motivo: str
    expressao: str
    vinculo: str


@dataclass
class Resultado:
    atos: list[Ato] = field(default_factory=list)
    decisoes: list[Decisao] = field(default_factory=list)
    eventos: list[Evento] = field(default_factory=list)
    outras: list[Outra] = field(default_factory=list)
    fora_escopo: list[ForaEscopo] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    descartados: int = 0           # atos de outras unidades, não atribuídos à GEDIV


def _id(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:20]


def _linhas(paginas) -> list[Linha]:
    saida = []
    for numero, texto in paginas:
        for bruta in (texto or "").split("\n"):
            limpa = re.sub(r"\s+", " ", C.limpar(bruta)).strip()
            if not limpa:
                continue
            norm = C.normalizar(limpa)
            if PAT_MOBILIARIO.match(norm):          # cabeçalho ou rodapé corrido da página
                continue
            anterior = saida[-1] if saida else None
            if anterior and ((re.search(r"(?:RESENHA|PORTARIA\s+N[O°.]*)\s*(?:N[O°.]*)?\s*:?$", anterior.norm)
                              and re.match(r"\d{1,5}\s*/\s*20\d{2}", norm))
                             or (re.fullmatch(r"(?:.*\s)?PORTARIA", anterior.norm) and re.match(r"N[O°.]+\s*\d{1,5}\s*/\s*20\d{2}", norm))):
                # cabeçalho quebrado pela largura da coluna: "RESENHA Nº" (ou "PORTARIA", "PORTARIA Nº") numa linha e o
                # número na seguinte
                anterior.texto, anterior.norm = f"{anterior.texto} {limpa}", f"{anterior.norm} {norm}"
                continue
            saida.append(Linha(numero, limpa, norm))
    return saida


def _resenha_no_cabecalho(norm: str):
    """A linha abre uma resenha (e não apenas cita uma) quando, antes do número, só há nomes de unidades."""
    achado = PAT_RESENHA.search(norm)
    if not achado:
        return None
    antes = re.sub(r"N[O°.]*\s*DA\s*$", "", norm[:achado.start()]).strip()
    return achado if len(antes) < 90 and re.fullmatch(r"[A-Z .]*", antes) else None


def _portaria_no_cabecalho(norm: str):
    """A linha abre uma portaria: no início, ou depois apenas de nomes de unidades (nunca numa citação)."""
    achado = PAT_PORTARIA_LIVRE.search(norm)
    if not achado:
        return None
    antes = norm[:achado.start()].strip()
    if not antes:
        return achado
    return achado if len(antes) < 120 and re.fullmatch(r"[A-Z .-]*", antes) and PAT_CABECALHO_UNIDADE.match(antes) else None


def _inicios(linhas: list[Linha]) -> list[tuple[int, str, int]]:
    """(índice inicial já recuado aos cabeçalhos, tipo, índice da linha que identifica o ato)."""
    inicios, limite = [], 0
    for i, linha in enumerate(linhas):
        tipo = "RESENHA" if _resenha_no_cabecalho(linha.norm) else "PORTARIA" if _portaria_no_cabecalho(linha.norm) else None
        if PAT_PUBLIQUE.match(linha.norm):
            limite = i + 1
        if not tipo:
            continue
        inicio = i
        while (inicio > limite and i - inicio < 3 and len(linhas[inicio - 1].norm) < 110
               and PAT_CABECALHO_UNIDADE.match(linhas[inicio - 1].norm) and not PAT_PROCESSO.search(linhas[inicio - 1].norm)
               and not PAT_OUTRA_SECRETARIA.match(linhas[inicio - 1].norm)):
            inicio -= 1
        if inicios and tipo == "RESENHA" and _continuacao_repetida(linhas, inicios[-1], i):
            continue                     # o mesmo cabeçalho repetido na continuação: não é um ato novo
        inicios.append((inicio, tipo, i))
        limite = i + 1
    return inicios


def _chave_do_cabecalho(norm: str) -> tuple[str, str] | None:
    achado = _resenha_no_cabecalho(norm)
    return (f"{int(achado.group(1))}/{achado.group(2)}", re.sub(r"\s+", "", achado.group(3))) if achado else None


def _continuacao_repetida(linhas: list[Linha], anterior: tuple[int, str, int], i: int) -> bool:
    """Etapa 05.3.4: resenha que continua em outra página ou coluna com o cabeçalho repetido ("RESENHA Nº 12/2026
    (continuação)"). É o MESMO ato quando o número e o sufixo são iguais, o ato anterior não foi encerrado
    (nenhum "Publique-se" entre os dois) e a repetição está em outra página ou se declara continuação."""
    _, tipo_anterior, marco = anterior
    if tipo_anterior != "RESENHA" or _chave_do_cabecalho(linhas[marco].norm) != _chave_do_cabecalho(linhas[i].norm):
        return False
    if any(PAT_PUBLIQUE.match(l.norm) for l in linhas[marco + 1:i]):
        return False
    if re.search(r"REPUBLICA|RETIFICA|SEM\s+EFEITO", " ".join(l.norm for l in linhas[i:i + 3])):
        return False                     # alteração do ato publicada com o mesmo número: é outro ato
    return linhas[i].pagina != linhas[marco].pagina or "CONTINUA" in linhas[i].norm


def _fim(linhas: list[Linha], inicio: int, marco: int, proximo: int, tipo: str) -> tuple[int, str | None]:
    """Fim (exclusivo) do ato e eventual pendência de delimitação."""
    teto = MAX_LINHAS_RESENHA if tipo == "RESENHA" else MAX_LINHAS_PORTARIA
    for j in range(marco + 1, min(proximo, marco + 1 + teto)):
        if PAT_PUBLIQUE.match(linhas[j].norm):
            return j + 1, None
        if PAT_OUTRA_SECRETARIA.match(linhas[j].norm):
            return j, None
        if tipo == "RESENHA" and _chave_do_cabecalho(linhas[j].norm) == _chave_do_cabecalho(linhas[marco].norm):
            continue                     # cabeçalho do próprio ato repetido na continuação (ver _continuacao_repetida)
        # Cabeçalho de outra unidade no meio do texto (por exemplo, com o número da resenha ilegível):
        # o ato termina ali, para que linhas alheias nunca sejam atribuídas à GEDIV.
        if j > marco + 2 and (linhas[j].norm.startswith("SECRETARIA DE ESTADO DA ADMINISTRACAO")
                              or (PAT_OUTRA_GERENCIA.match(linhas[j].norm) and not PAT_GEDIV.search(linhas[j].norm))):
            return j, "o ato foi encerrado em um cabeçalho de outra unidade; conferir se não há linhas faltando"
    if proximo - marco - 1 > teto:
        return marco + 1 + teto, f"ato sem término reconhecido em {teto} linhas; alcance a conferir"
    return proximo, None


def _continuidade_duvidosa(corpo: list[Linha], pendencia_de_fim: str | None) -> str | None:
    """Motivo de dúvida na continuidade de um ato que atravessa página ou coluna; None quando ela está demonstrada:
    o ato termina em "Publique-se" e tem linhas de processo na primeira e na última página (ou o cabeçalho foi
    repetido na continuação)."""
    if pendencia_de_fim:
        return "término do ato não reconhecido com segurança"
    if not PAT_PUBLIQUE.match(corpo[-1].norm):
        return "o ato não termina em Publique-se"
    primeira, ultima = corpo[0].pagina, corpo[-1].pagina
    repetido = sum(bool(_resenha_no_cabecalho(l.norm)) for l in corpo) > 1
    com_processo = {l.pagina for l in corpo if PAT_PROCESSO.search(l.norm)}
    if repetido or (primeira in com_processo and ultima in com_processo):
        return None
    paginas_sem = sorted({primeira, ultima} - com_processo)
    return "sem linhas de processo na página " + ", ".join(map(str, paginas_sem))


def _merito(norm: str) -> str:
    achados = {bool(m.group(1)) for m in PAT_MERITO.finditer(norm)}
    if achados == {False}:
        return "DEFERIDO"
    return "INDEFERIDO" if achados == {True} else "NAO_INFORMADO"


def _natureza(norm: str) -> tuple[str, str | None]:
    for tipo, padrao in _ALTERACOES:
        if padrao.search(norm):
            return tipo, ("POR_INCORRECAO" if tipo == C.REPUBLICACAO and re.search(r"POR\s+INCORRE", norm) else None)
    return C.ORIGINAL, None


def _processo(achado) -> str:
    return f"{achado.group(1)}-{achado.group(2)}-{achado.group(3)}{achado.group(4)}{achado.group(5)}"


_CONECTIVOS = {"DE", "DA", "DO", "DOS", "DAS", "E"}
# Palavras que só aparecem na continuação do CARGO quando a célula quebra em duas linhas
# ("TECNICO" / "ADMINISTRATIVO"). O que vier antes delas, na linha de baixo, é continuação do NOME.
_CONTINUACAO_DE_CARGO = {"ADMINISTRATIVO", "ADMINISTRATIVA", "PENAL", "AGROPECUARIO", "AGROPECUARIA", "ESTADUAL", "EST", "FISCAL",
                         "TRIBUTARIO", "TRIBUTARIA", "ENFERMAGEM", "EDUCACAO", "BAS", "BASICA", "SUPERIOR", "MEDIO", "NIVEL",
                         "SAUDE", "LABORATORIO", "ESPECIALIZADO", "ESPECIALIZADA", "JUDICIARIO", "CIVIL", "DE", "EM", "I", "II", "III"}
# Começa numa letra isolada, segue com pedaços de 1–2 letras e termina no resto da palavra:
# "T E C N IC O", "A D M IN IS TRATIVO". Um conectivo de nome ("DE", "DO") nunca inicia a sequência.
PAT_LETRAS_ESPACADAS = re.compile(r"(?<![A-Z])[A-Z] (?:[A-Z]{1,2} ){2,}[A-Z]+\b")


def _juntar_letras_espacadas(texto: str) -> str:
    """ "T E C N IC O" (texto justificado letra a letra no PDF) volta a ser "TECNICO"."""
    return PAT_LETRAS_ESPACADAS.sub(lambda m: m.group(0).replace(" ", ""), texto)
PAT_MOBILIARIO_COLADO = re.compile(r"\s*DIARIO\s+OFICIAL\s+JOAO\s+PESSOA\b.*$|\s*\d*\s*JOAO\s+PESSOA\s*-\s*[\w-]+\s*,.*$")


_CLASSES = "ABCDEF"
_ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
PAT_CLASSES = re.compile(r"(?:^|\s)([A-Z])\s+([A-Z])$")
PAT_CLASSES_COLADAS = re.compile(r"\s([A-Z])([A-Z])$")
PAT_NIVEIS_ROMANOS = re.compile(r"(?:^|\s)([IVX]{1,4})\s+([IVX]{1,4})$")
PAT_NIVEIS_NUMERADOS = re.compile(r"(?:^|\s)(NIVEL\s*\d{1,2})\s+(NIVEL\s*\d{1,2})$")


def _posicao(valor: str, ordem) -> int | None:
    """Posição ordinal do valor publicado: letra na sequência A–F, algarismo romano ou "NÍVEL n"."""
    if isinstance(ordem, str):
        return ordem.find(valor) + 1 or None
    numero = re.search(r"\d+", valor)
    return int(numero.group(0)) if numero else ordem.get(valor)


def _observar_evolucao(anterior: str, posterior: str, ordem) -> list[str]:
    """Observações sobre a evolução PUBLICADA. Nunca altera o valor: salto (A→E), regressão ou valor fora da
    faixa ficam registrados como foram lidos, para conferência."""
    a, p = _posicao(anterior, ordem), _posicao(posterior, ordem)
    if a is None or p is None:
        return [f"valor fora da faixa esperada ({anterior} → {posterior}); mantido como publicado"]
    if p <= a:
        return [f"evolução sem avanço ({anterior} → {posterior}); mantida como publicada, conferir no PDF"]
    if p - a > 1:
        return [f"salto de {p - a} posições ({anterior} → {posterior}); mantido como publicado"]
    return []


def _evolucao(cauda: str, eixo, modalidade, subcategoria) -> tuple[str, dict]:
    """Dados expressamente publicados no fim da linha: classe (Progressão VERTICAL, letras A–F), nível (Progressão
    HORIZONTAL, algarismos romanos ou "NÍVEL n") e dias/períodos (Tempo de Serviço).
    Devolve (o que sobrou antes desses dados, detalhe). Nada é deduzido nem corrigido: classe e nível ficam em
    campos distintos, com o valor como publicado; formato trocado (nível numa vertical, classe numa horizontal),
    salto ou regressão geram observação, nunca conversão."""
    cauda = re.sub(r"\s+", " ", re.sub(r"[$%*]+", " ", cauda)).strip()
    if eixo == C.PROGRESSAO:
        classes = PAT_CLASSES.search(cauda)
        niveis = PAT_NIVEIS_NUMERADOS.search(cauda) or PAT_NIVEIS_ROMANOS.search(cauda)
        if modalidade == C.VERTICAL:
            if classes and not (niveis and niveis.start() <= classes.start()):
                a, p = classes.group(1), classes.group(2)
                detalhe = {"classe_anterior": a, "classe_posterior": p}
                observacoes = _observar_evolucao(a, p, _CLASSES)
                return cauda[:classes.start()].strip(), {**detalhe, **({"observacoes": observacoes} if observacoes else {})}
            m = PAT_CLASSES_COLADAS.search(cauda)
            if m and not niveis:            # as duas letras saíram coladas na leitura ("AC"): guardado como lido, a conferir
                return cauda[:m.start()].strip(), {"classe_anterior": m.group(1), "classe_posterior": m.group(2),
                                                   "observacao": f"classes lidas coladas: {m.group(1)}{m.group(2)}"}
            if niveis:
                return cauda[:niveis.start()].strip(), {"evolucao_lida": f"{niveis.group(1)} {niveis.group(2)}",
                                                        "observacoes": ["progressão VERTICAL publicada com níveis, não classes; "
                                                                        "não convertido, conferir no PDF"]}
        elif modalidade == C.HORIZONTAL:
            if niveis:
                # "NÍVEL3" e "NÍVEL 3" (o OCR às vezes perde o espaço) são a mesma grafia: guardada como "NIVEL 3".
                a, p = (re.sub(r"^NIVEL\s*", "NIVEL ", v) for v in (niveis.group(1), niveis.group(2)))
                detalhe = {"nivel_anterior": a, "nivel_atual": p}
                observacoes = _observar_evolucao(a, p, _ROMANOS)
                return cauda[:niveis.start()].strip(), {**detalhe, **({"observacoes": observacoes} if observacoes else {})}
            if classes and classes.group(1) in _CLASSES and classes.group(2) in _CLASSES:
                return cauda[:classes.start()].strip(), {"evolucao_lida": f"{classes.group(1)} {classes.group(2)}",
                                                         "observacoes": ["progressão HORIZONTAL publicada com classes, não níveis; "
                                                                         "não convertido, conferir no PDF"]}
        return cauda, {}
    m = re.search(r"(\d{1,4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})", cauda)
    if m:
        return cauda[:m.start()].strip(), {"dias": int(m.group(1)), "periodo_inicial": m.group(2), "periodo_final": m.group(3)}
    if subcategoria == "TS-01":
        m = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)$", cauda)
        if m:
            dias = [int(v.replace(".", "")) for v in m.groups()]
            return cauda[:m.start()].strip(), dict(zip(("dias_privada", "dias_federal", "dias_estadual", "dias_municipal"), dias))
    return cauda, {}


@dataclass
class _Marco:
    """Onde começa uma decisão numa linha do ato: pelo processo reconhecido ou, sem ele, pela matrícula."""
    inicio: int
    fim: int
    processo: str | None
    lido: str | None = None        # grafia publicada de um processo que não fecha o padrão


# Linha de tabela sem processo reconhecido (Etapa 05.3.4): começa (opcionalmente depois de um processo com grafia
# defeituosa) pela matrícula e segue com o nome. A decisão é registrada com o processo AUSENTE, nunca presumido.
PAT_LINHA_SEM_PROCESSO = re.compile(r"^(?P<lido>[A-Z0-9]{2,6}\s*-\s*(?:PSE|PRC|OFI)\b\S*\s+)?"
                                    r"(?P<mat>\d{3}\.\d{3}-\d|\d{5,7}-\d)\s+(?=[A-Z][A-Z .'-]{4,})")


def _marcos_da_linha(norm: str) -> list[_Marco]:
    marcos = [_Marco(m.start(), m.end(), _processo(m)) for m in PAT_PROCESSO.finditer(norm)]
    if marcos:
        return marcos
    sem = PAT_LINHA_SEM_PROCESSO.match(norm)
    if sem:
        lido = sem.group("lido").strip() if sem.group("lido") else None
        return [_Marco(0, sem.start("mat"), None, lido)]
    return []


def _titulo_de_merito(norm: str) -> str | None:
    achado = PAT_TITULO_MERITO.match(norm)
    return ("INDEFERIDO" if achado.group(1) else "DEFERIDO") if achado else None


def _decisoes(ato: Ato, corpo: list[Linha], chave_arquivo: str) -> list[Decisao]:
    marcos = [(i, m) for i, linha in enumerate(corpo) if i > 0 or not _resenha_no_cabecalho(linha.norm)
              for m in _marcos_da_linha(linha.norm)]
    # Linhas sem processo só contam DEPOIS da primeira linha com processo, ou num ato sem nenhum processo
    # reconhecido (assim o texto corrido do preâmbulo nunca vira decisão).
    primeira_com_processo = next((i for i, m in marcos if m.processo), None)
    marcos = [(i, m) for i, m in marcos if m.processo or primeira_com_processo is None or i > primeira_com_processo]
    # Mérito por bloco (Etapa 05.3.4): numa resenha mista, "DEFERIDOS:" / "INDEFERIDOS:" valem para as linhas abaixo
    # até o próximo título; a decisão nunca herda o resultado de outro bloco nem o do ato inteiro misto.
    bloco, titulos = {}, {}
    atual = None
    for i, linha in enumerate(corpo):
        titulo = _titulo_de_merito(linha.norm)
        if titulo:
            atual = titulos[i] = titulo
        bloco[i] = atual
    misto = PAT_MERITO.search(" ".join(l.norm for l in corpo[:marcos[0][0]] if marcos)) and ato.resultado == "NAO_INFORMADO"
    decisoes, repeticoes = [], {}
    for n, (i, achado) in enumerate(marcos):
        linha = corpo[i]
        proxima_linha = marcos[n + 1][0] if n + 1 < len(marcos) else len(corpo)
        mesma_linha = n + 1 < len(marcos) and marcos[n + 1][0] == i
        primeira = linha.norm[achado.fim:marcos[n + 1][1].inicio if mesma_linha else None]
        primeira = re.sub(r"\s+", " ", PAT_MOBILIARIO_COLADO.sub("", primeira)).strip()
        continuacao, ambigua = [], False
        for j in range(i + 1, proxima_linha if not mesma_linha else i + 1):
            if MARCA_AMBIGUA in corpo[j].norm:
                ambigua = True          # fragmento que a leitura não soube atribuir: não é colado a esta pessoa
                break
            if (len(continuacao) >= 4 or PAT_PUBLIQUE.match(corpo[j].norm) or PAT_CABECALHO_UNIDADE.match(corpo[j].norm)
                    or re.match(r"^\W*(?:REPUBLICAD|PUBLICAD)", corpo[j].norm) or j in titulos):
                break
            continuacao.append(corpo[j].norm)
        acima_ambigua = i > 0 and MARCA_AMBIGUA in corpo[i - 1].norm
        antes = linha.norm[:achado.inicio].strip() if not (n and marcos[n - 1][0] == i) else ""
        lotacao = antes if 3 <= len(antes) <= 60 and not PAT_MERITO.search(antes) and "PROCESSO" not in antes else None

        # A linha do processo é lida primeiro; as linhas de continuação (células quebradas) só completam o que faltar.
        matricula = servidor = cargo = None
        detalhe: dict = {}
        resto = primeira if primeira else " ".join(continuacao)
        usou_continuacao = not primeira and bool(continuacao)
        m = PAT_MATRICULA.search(resto)
        if m and m.start() < 12:
            matricula, resto = m.group(1), resto[m.end():].strip()
        resto, detalhe = _evolucao(resto, ato.eixo, ato.modalidade, ato.subcategoria)
        resto = _juntar_letras_espacadas(resto)
        nome = PAT_NOME.match(resto)
        if nome:
            servidor = nome.group(1).strip(" .-")
            cauda = resto[nome.end():].strip()
            lot = re.match(r"^(SEC\.[A-Z. ]{3,50}|SECRETARIA [A-Z ]{3,60})$", cauda)
            if lot and not lotacao:
                lotacao = lot.group(1).strip()
            else:
                cargo = cauda or None
        if continuacao and not usou_continuacao:
            if not detalhe:                               # classe, nível ou dias podem ter ficado na linha seguinte
                _, detalhe = _evolucao(" ".join([resto] + continuacao), ato.eixo, ato.modalidade, ato.subcategoria)
            abaixo = _juntar_letras_espacadas(continuacao[0]).split()
            corte = len(abaixo)
            while corte and abaixo[corte - 1] in _CONTINUACAO_DE_CARGO:
                corte -= 1
            if servidor and cargo and 0 < corte < len(abaixo) and all(re.fullmatch(r"[A-Z'.-]+", p) for p in abaixo[:corte]):
                # "NOME ... DOS | TECNICO | A E" na linha do processo e "SANTOS ADMINISTRATIVO" na de baixo
                servidor, cargo = f"{servidor} {' '.join(abaixo[:corte])}", f"{cargo} {' '.join(abaixo[corte:])}"
            elif servidor and cargo and corte == 0:
                cargo = f"{cargo} {' '.join(abaixo)}"
            elif servidor and servidor.split()[-1] in _CONECTIVOS and abaixo:
                servidor = f"{servidor} {abaixo[0]}"       # "... DOS" + sobrenome que desceu de linha
            if ato.eixo == C.PROGRESSAO:
                detalhe = {**detalhe, "linha_quebrada": "nome e cargo podem continuar na linha seguinte; conferir no PDF"}
        pendencias = []
        if achado.processo is None:
            pendencias.append("processo não reconhecido na linha; registrado como ausente, sem número presumido"
                              + (f" (grafia publicada: {achado.lido})" if achado.lido else ""))
        if ambigua or acima_ambigua:
            pendencias.append("linha de tabela vizinha sem atribuição segura; nome, cargo ou evolução podem estar incompletos")
        texto_da_linha = " ".join([primeira] + continuacao)
        proprio = _merito(texto_da_linha) if PAT_MERITO.search(texto_da_linha) else None
        resultado = proprio or bloco.get(i) or ato.resultado
        if not proprio and not bloco.get(i) and misto:
            pendencias.append("resultado misto no ato (deferimento e indeferimento); resultado desta decisão não identificado")
        if proprio is None and bloco.get(i):
            detalhe = {**detalhe, "resultado_do_bloco": bloco[i]}
        processo = achado.processo
        anterior = decisoes[-1] if decisoes else None
        if (anterior and anterior.pagina != linha.pagina and anterior.processo == processo and anterior.matricula == matricula
                and anterior.servidor == servidor and (processo or matricula)):
            # A mesma linha repetida no alto da página seguinte (continuação): contada uma vez.
            anterior.detalhe.setdefault("pendencias", []).append(
                f"linha repetida na continuação (p. {linha.pagina}); contada uma vez, conferir no PDF")
            continue
        if pendencias:
            detalhe = {**detalhe, "pendencias": pendencias}
        chave = processo or f"SEM_PROCESSO:{matricula or ''}"
        ordem = repeticoes[chave] = repeticoes.get(chave, 0) + 1
        trecho = " ⏎ ".join(l.texto for l in corpo[i:i + 1 + len(continuacao)])[:400]
        decisoes.append(Decisao(_id(chave_arquivo, ato.id, chave if processo is None else processo, ordem), ato.id, linha.pagina,
                                processo, servidor, matricula, lotacao, cargo, detalhe, resultado, trecho))
    return decisoes


PAT_PROGRESSAO_COMPACTA = re.compile(r"PROGRESSAO(?:FUNCIONAL|HORIZONTAL|VERTICAL)")


def _variantes_do_preambulo(preambulo: str) -> list[tuple[str, str]]:
    """Formas do preâmbulo em que o ASSUNTO é procurado, nesta ordem (a primeira que identificar um eixo vale):
    1. o texto como foi lido;
    2. com letras espaçadas reunidas ("D E S A V E R B A Ç Ã O" — DOE 04/11/2026, resenha 543);
    3. compacto, sem espaços ("LICENÇAPARATRATAR" — palavras coladas pela extração, DOE 04/11/2026, resenha 540)."""
    juntado = _juntar_letras_espacadas(preambulo)
    variantes = [("original", preambulo)]
    if juntado != preambulo:
        variantes.append(("letras_reunidas", juntado))
    variantes.append(("compacto", C.compactar(preambulo)))
    return variantes


def _tema(preambulo: str) -> dict:
    tema = dict(eixo=None, modalidade=None, condicao=None, grupo=None, grupo_expressao=None, subcategoria=None,
                candidato=None, pendencias=[])
    incompleto = None
    for forma, texto in _variantes_do_preambulo(preambulo):
        compacto = forma == "compacto"
        if (PAT_PROGRESSAO_COMPACTA if compacto else PAT_PROGRESSAO).search(texto):
            return _tema_progressao(tema, preambulo, texto, forma)
        sub, pendencia = C.avaliar_subcategoria(texto, compacto=compacto)
        if sub:
            tema["eixo"], tema["subcategoria"] = C.TEMPO, sub
            if forma != "original":
                tema["pendencias"].append(f"assunto identificado com texto reconstituído ({forma}); conferir a leitura no PDF")
            return tema
        incompleto = incompleto or pendencia
    if incompleto:
        # Assunto específico sem o seu requisito (TS-04 sem interesses particulares, TS-06 sem tempo de serviço): o ato
        # é de Tempo de Serviço, o assunto fica em branco para a gerência; nunca vai para o assunto genérico vizinho.
        tema["eixo"] = C.TEMPO
        tema["pendencias"].append(incompleto)
        return tema
    for nome, padrao in C.CONCEITOS_CANDIDATOS:
        if re.search(padrao, preambulo):
            tema["candidato"] = nome
            break
    return tema


def _tema_progressao(tema: dict, preambulo: str, texto: str, forma: str) -> dict:
    """Progressão Funcional. A modalidade é procurada no texto em que o eixo foi achado; grupo e condição,
    no preâmbulo como foi lido (os padrões de grupo dependem dos limites de palavra)."""
    tema["eixo"] = C.PROGRESSAO
    if forma != "original":
        tema["pendencias"].append(f"assunto identificado com texto reconstituído ({forma}); conferir a leitura no PDF")
    h, v = "HORIZONTAL" in texto, "VERTICAL" in texto
    if h != v:
        tema["modalidade"] = C.HORIZONTAL if h else C.VERTICAL
    else:
        tema["pendencias"].append("modalidade da progressão não identificada de forma inequívoca")
    tema["condicao"] = C.identificar_condicao(preambulo)
    # Etapa 05.3.4: dois grupos no mesmo ato não são resolvidos pela ordem dos padrões (ver catalogo.avaliar_grupo).
    tema["grupo"], tema["grupo_expressao"], pendencia = C.avaliar_grupo(preambulo)
    if not tema["grupo"]:
        tema["pendencias"].append(pendencia or "grupo do PCCR não informado ou não reconhecido")
    return tema


def classificar(paginas, chave_arquivo: str = "") -> Resultado:
    """paginas: sequência de (número da página, texto). chave_arquivo: SHA-256 do PDF, para ids estáveis."""
    linhas = _linhas(paginas)
    resultado = Resultado()
    inicios = _inicios(linhas)
    for n, (inicio, tipo, marco) in enumerate(inicios):
        proximo = inicios[n + 1][0] if n + 1 < len(inicios) else len(linhas)
        fim, pendencia = _fim(linhas, inicio, marco, proximo, tipo)
        corpo = linhas[inicio:fim]
        norm = " ".join(l.norm for l in corpo)
        cabecalho = _resenha_no_cabecalho(linhas[marco].norm) if tipo == "RESENHA" else _portaria_no_cabecalho(linhas[marco].norm)
        numero = f"{int(cabecalho.group(1))}/{cabecalho.group(2)}"
        sufixo = re.sub(r"\s+", "", cabecalho.group(3)) or None

        gediv = PAT_GEDIV.search(norm)
        outra_sigla = bool(sufixo and re.search(r"[-/](?!DEREH\b|GS\b|SEAD\b|SAD\b|GEDIV\b)[A-Z]{3,10}", sufixo))
        primeiro = PAT_PROCESSO.search(norm)
        preambulo = norm[:primeiro.start()] if primeiro else norm[:1500]
        tema = _tema(preambulo)
        natureza, subtipo = _natureza(norm)
        pagina = linhas[marco].pagina
        titulo = f"{'Resenha' if tipo == 'RESENHA' else 'Portaria'} nº {numero}"

        def excluir(motivo: str, expressao: str, vinculo_ato: str) -> None:
            resultado.fora_escopo.append(ForaEscopo(_id(chave_arquivo, "FORA_ESCOPO", tipo, numero, pagina), tipo, numero, pagina,
                                                    titulo, motivo, expressao[:120], vinculo_ato))

        if not gediv:
            dereh = PAT_DEREH.search(norm)
            outra_gerencia = outra_sigla or PAT_OUTRA_GERENCIA.search(norm)
            if outra_gerencia or not dereh:
                if tema["eixo"]:
                    resultado.descartados += 1
                if outra_gerencia and dereh:
                    # Ato da estrutura da SEAD/DEREH atribuído a outra gerência: registrado para não reaparecer.
                    expressao = sufixo if outra_sigla else PAT_OUTRA_GERENCIA.search(norm).group(0)
                    excluir(EX.OUTRA_GERENCIA, expressao, NAO_EXPRESSO)
                continue
            if not tema["eixo"]:
                exclusao = EX.motivo_de_exclusao(preambulo)
                if exclusao:                              # licença-saúde ou vacância sob a DEREH
                    excluir(*exclusao, NAO_EXPRESSO)
                    continue
            if tipo == "PORTARIA" and natureza == C.ORIGINAL:
                pass                                      # portaria da DEREH: vai para "Outras publicações" (abaixo)
            elif not tema["eixo"] and natureza == C.ORIGINAL:
                continue                                  # ato da DEREH sem tema dos dois eixos: fora do escopo
            elif not tema["eixo"] and not (PAT_PROGRESSAO.search(norm) or C.identificar_subcategoria(norm)):
                continue
        vinculo = EXPRESSO if gediv else NAO_EXPRESSO
        trecho = " ".join(l.texto for l in corpo)

        if not tema["eixo"]:
            exclusao = EX.motivo_de_exclusao(preambulo)
            if exclusao:                                  # licença-saúde ou vacância, mesmo com a GEDIV no cabeçalho
                excluir(*exclusao, vinculo)
                continue

        if tipo == "PORTARIA" and natureza == C.ORIGINAL:
            # Etapa 05.3.4: toda portaria relacionada (GEDIV expressa, ou só DEREH) tem destino: "Outras publicações".
            # Portaria com assunto de um dos eixos NÃO vira decisão de progressão ou de tempo: o assunto vai no título,
            # como indício, para a gerência.
            assunto = (f" — assunto: {C.EIXOS[tema['eixo']]} (indício; não convertida em decisão)" if tema["eixo"]
                       else f" — {tema['candidato']} (conceito candidato)" if tema["candidato"] else "")
            resultado.outras.append(Outra(_id(chave_arquivo, "PORTARIA", numero, pagina), "PORTARIA", pagina,
                                          titulo + (f" {sufixo}" if sufixo else "") + assunto, vinculo, trecho[:600]))
            continue
        if not tema["eixo"] and natureza == C.ORIGINAL:
            # GEDIV comprovada, tema fora dos dois eixos: página "Outras publicações".
            chave = "TEMA_FORA_DOS_EIXOS"
            rotulo = titulo + (f" — {tema['candidato']} (conceito candidato)" if tema["candidato"] else "")
            resultado.outras.append(Outra(_id(chave_arquivo, chave, numero, pagina), chave, pagina, rotulo, vinculo, trecho[:600]))
            continue

        expediente = PAT_EXPEDIENTE.search(norm)
        ato = Ato(
            id=_id(chave_arquivo, tipo, numero, natureza, pagina), tipo=tipo, numero=numero, sufixo=sufixo, pagina=pagina,
            pagina_final=corpo[-1].pagina, vinculo=vinculo, expressao_vinculo=gediv.group(0) if gediv else None,
            data_expediente=f"{expediente.group(3)}-{expediente.group(2)}-{expediente.group(1)}" if expediente else None,
            natureza=natureza, eixo=tema["eixo"], modalidade=tema["modalidade"], condicao=tema["condicao"],
            grupo=tema["grupo"], grupo_expressao=tema["grupo_expressao"], subcategoria=tema["subcategoria"],
            resultado=_merito(preambulo) if _merito(preambulo) != "NAO_INFORMADO" else _merito(_juntar_letras_espacadas(preambulo)), texto=trecho[:6000], pendencias=list(tema["pendencias"]),
        )
        if pendencia:
            ato.pendencias.append(pendencia)
        if vinculo == NAO_EXPRESSO:
            ato.pendencias.append("vínculo com a GEDIV não expresso no ato (apenas DEREH); confirmar no PDF")
        if ato.pagina_final != ato.pagina:
            duvida = _continuidade_duvidosa(corpo, pendencia)
            if duvida:
                ato.pendencias.append(f"ato continua até a página {ato.pagina_final}; continuidade duvidosa ({duvida}); conferir")
        if ato.resultado == "NAO_INFORMADO" and natureza == C.ORIGINAL:
            ato.pendencias.append("resultado (deferido/indeferido) não identificado no preâmbulo")

        if natureza != C.ORIGINAL:
            citadas = sorted({f"{int(a)}/{b}" for a, b in PAT_REF_RESENHA.findall(norm)} - ({numero} if tipo == "RESENHA" and natureza != C.REPUBLICACAO else set()))
            processos = sorted({_processo(m) for m in PAT_PROCESSO.finditer(norm)} | set(PAT_PROCESSO_ANTIGO.findall(norm)))
            publicacoes = sorted({f"{a}-{m}-{d}" for d, m, a in PAT_PUBLICACAO_CITADA.findall(norm)})
            resultado.eventos.append(Evento(_id(chave_arquivo, "EVENTO", natureza, tipo, numero, pagina), ato.id, natureza, subtipo,
                                            pagina, titulo, citadas, processos, vinculo, trecho[:2000], publicacoes))
            if subtipo == "POR_INCORRECAO":
                resultado.outras.append(Outra(_id(chave_arquivo, "REPUB", numero, pagina), "REPUBLICADO_POR_INCORRECAO", pagina,
                                              titulo, vinculo, trecho[:600]))
        if tipo == "RESENHA" and ato.eixo:
            decisoes = _decisoes(ato, corpo, chave_arquivo)
            if not decisoes:
                ato.pendencias.append("nenhum processo extraído neste ato; exige revisão")
            sem_processo = sum(d.processo is None for d in decisoes)
            if sem_processo:
                ato.pendencias.append(f"{sem_processo} decisão(ões) sem processo reconhecido; registradas sem número, para revisão")
            if any(MARCA_AMBIGUA in l.norm for l in corpo):
                ato.pendencias.append("linha de tabela sem atribuição segura a uma pessoa; conferir no PDF")
            if any("resultado misto" in " ".join(d.detalhe.get("pendencias", [])) for d in decisoes):
                ato.pendencias.append("resultado misto (deferimento e indeferimento) sem indicação por linha; conferir")
            resultado.decisoes += decisoes
            resultado.atos.append(ato)
        elif natureza != C.ORIGINAL:
            resultado.atos.append(ato)

    _outras_normativas(linhas, chave_arquivo, resultado)
    return resultado


def _outras_normativas(linhas: list[Linha], chave_arquivo: str, resultado: Resultado) -> None:
    """Triagem para a página "Outras publicações": atos normativos e alterações de lei relacionados à SEAD/DEREH/GEDIV.
    São indícios; a relação com a GEDIV precisa de confirmação humana."""
    for i, linha in enumerate(linhas):
        tipo = None
        if re.match(r"^ATO\s+NORMATIVO\b", linha.norm):
            tipo = "ATO_NORMATIVO"
        elif re.match(r"^LEI(?:\s+COMPLEMENTAR)?\s+N[O°.]*\s*[\d.]+", linha.norm):
            tipo = "ALTERACAO_LEI"
        if not tipo:
            continue
        janela = " ".join(l.norm for l in linhas[i:i + 10])
        gediv = PAT_GEDIV.search(janela)
        relacionado = gediv or PAT_DEREH.search(janela) or re.search(
            r"SERVIDOR(?:ES)?\s+PUBLIC|PLANO\s+DE\s+CARGOS|PCCR|PROGRESSAO\s+FUNCIONAL|TEMPO\s+DE\s+(?:SERVICO|CONTRIBUICAO)|LICENCA\s+ESPECIAL",
            janela)
        if tipo == "ALTERACAO_LEI" and not re.search(r"\bALTERA|\bMODIFICA|NOVA\s+REDACAO|\bREVOGA", janela):
            continue
        if relacionado:
            resultado.outras.append(Outra(_id(chave_arquivo, tipo, linha.pagina, linha.norm[:60]), tipo, linha.pagina, linha.texto[:160],
                                          EXPRESSO if gediv else NAO_EXPRESSO, " ".join(l.texto for l in linhas[i:i + 10])[:600]))
