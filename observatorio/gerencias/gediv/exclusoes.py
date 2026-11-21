"""Publicações FORA DO ESCOPO da GEDIV (regra 5.3 da consolidação, Etapa 02).

- Licença-saúde não pertence ao painel GEDIV.
- Vacância pertence à DEREH e não entra nos indicadores GEDIV.
- Publicações de outras gerências não pertencem à GEDIV.

Uma exclusão só é aplicada quando o ato NÃO tem tema de um dos dois eixos (Progressão Funcional ou
Tempo de Serviço). A sigla DEREH, sozinha, nunca exclui: um ato com cabeçalho DEREH que trata de
progressão ou de tempo de serviço continua classificado (com vínculo NAO_EXPRESSO quando a GEDIV
não aparece).

Os atos excluídos não somem: ficam registrados na tabela privada `fora_escopo`, com o motivo e a
expressão que o comprova, para que não reapareçam em "Outras publicações" nem em indicadores.
"""
from __future__ import annotations

import re

LICENCA_SAUDE = "LICENCA_SAUDE"
VACANCIA = "VACANCIA"
OUTRA_GERENCIA = "OUTRA_GERENCIA"

MOTIVOS = {
    LICENCA_SAUDE: "Licença-saúde: fora do painel GEDIV",
    VACANCIA: "Vacância: competência da DEREH, fora dos indicadores GEDIV",
    OUTRA_GERENCIA: "Ato de outra gerência",
}

# Aplicados ao texto NORMALIZADO (maiúsculas, sem acentos) do ato.
_PADROES = (
    (LICENCA_SAUDE, re.compile(
        r"PERICIA\s+MEDICA"
        r"|LICENCA\s+(?:PARA\s+)?(?:TRATAMENTO\s+(?:DE\s+|DA\s+(?:PROPRIA\s+)?)?SAUDE|MEDICA\b|SAUDE\b|POR\s+MOTIVO\s+DE\s+DOENCA)"
        r"|TIPO\s+DE\s+LICENCA\s*=?\s*>?\s*DOENCA"
        r"|DOENCA\s+(?:NAO\s+)?RELACIONADA\s+AO\s+TRABALHO")),
    (VACANCIA, re.compile(r"\bVACANCIA\b|DECLARA(?:R|DO|DA|NDO)?\s+(?:A\s+)?VAG[OA]S?\b")),
)


def motivo_de_exclusao(texto_normalizado: str) -> tuple[str, str] | None:
    """(motivo, expressão literal) quando o texto trata de assunto excluído; None caso contrário.

    Não verifica o tema dos eixos: quem chama só deve pedir a exclusão para atos SEM tema dos eixos.
    """
    for motivo, padrao in _PADROES:
        achado = padrao.search(texto_normalizado)
        if achado:
            return motivo, achado.group(0)
    return None
