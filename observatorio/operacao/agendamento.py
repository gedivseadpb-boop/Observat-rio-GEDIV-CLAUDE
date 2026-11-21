"""Regras de calendário para a coleta automática do Observatório DOE · GEDIV.

Política operacional:
- Coleta automática permitida exclusivamente de segunda a sexta-feira (ISO 1..5),
  nas janelas de 09:00 e 14:00 (fuso America/Sao_Paulo).
- Sábados e domingos (ISO 6 e 7) são bloqueados, inclusive após reinício de servidor
  ou disparo atrasado de timer persistente.
- Feriados administrativos oficiais são configuráveis via arquivo externo validado
  (`feriados_oficiais.txt`), sendo explicitamente diferenciados de fim de semana.
- Na segunda-feira, a janela de recuperação recua 4 dias para cobrir lacunas de dias úteis
  anteriores; de terça a sexta, recua 3 dias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FUSO_PADRAO = "America/Sao_Paulo"
JANELAS_HORARIO = ("09:00", "14:00")


def _resolver_fuso(fuso: str) -> tzinfo:
    try:
        return ZoneInfo(fuso)
    except ZoneInfoNotFoundError:
        if fuso in ("America/Sao_Paulo", "America/Fortaleza", "America/Recife"):
            return timezone(timedelta(hours=-3), name=fuso)
        raise


@dataclass(frozen=True)
class DecisaoAgendamento:
    executar: bool
    motivo: str
    categoria: str  # "DIA_UTIL", "FIM_DE_SEMANA", "FERIADO_ADMINISTRATIVO", "MANUAL_EXCEPCIONAL"
    data_local: date
    inicio_janela: date
    fim_janela: date


def carregar_feriados(caminho: Path | None) -> dict[date, str]:
    """Lê feriados administrativos oficiais (formato `YYYY-MM-DD [descrição]`).
    Nunca presume feriados quando o arquivo não é fornecido ou não existe.
    """
    feriados: dict[date, str] = {}
    if caminho is None or not Path(caminho).is_file():
        return feriados
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#"):
            continue
        partes = limpa.split(None, 1)
        try:
            d = date.fromisoformat(partes[0])
        except ValueError:
            continue
        desc = partes[1].strip() if len(partes) > 1 else "Feriado administrativo oficial"
        feriados[d] = desc
    return feriados


def avaliar_execucao(
    agora: datetime | None = None,
    feriados_arq: Path | None = None,
    modo_manual: bool = False,
    fuso: str = FUSO_PADRAO,
) -> DecisaoAgendamento:
    """Decide se a rotina automática deve executar na data/hora informada."""
    tz = _resolver_fuso(fuso)
    ref = agora.astimezone(tz) if agora is not None else datetime.now(tz)
    hoje = ref.date()
    dia_iso = hoje.isoweekday()  # 1=Seg .. 5=Sex, 6=Sab, 7=Dom

    dias_recuo = 4 if dia_iso == 1 else 3
    inicio = hoje - timedelta(days=dias_recuo)

    if modo_manual:
        return DecisaoAgendamento(
            executar=True,
            motivo="Execução manual excepcional autorizada pelo operador.",
            categoria="MANUAL_EXCEPCIONAL",
            data_local=hoje,
            inicio_janela=inicio,
            fim_janela=hoje,
        )

    if dia_iso >= 6:
        nome_dia = "sábado" if dia_iso == 6 else "domingo"
        return DecisaoAgendamento(
            executar=False,
            motivo=f"Execução automática bloqueada em fim de semana ({nome_dia}, {hoje.isoformat()}).",
            categoria="FIM_DE_SEMANA",
            data_local=hoje,
            inicio_janela=inicio,
            fim_janela=hoje,
        )

    feriados = carregar_feriados(feriados_arq)
    if hoje in feriados:
        return DecisaoAgendamento(
            executar=False,
            motivo=f"Execução automática suspensa por feriado administrativo configurado ({feriados[hoje]}).",
            categoria="FERIADO_ADMINISTRATIVO",
            data_local=hoje,
            inicio_janela=inicio,
            fim_janela=hoje,
        )

    return DecisaoAgendamento(
        executar=True,
        motivo=f"Dia útil autorizado ({hoje.isoformat()}, ISO={dia_iso}); janela de recuperação {inicio.isoformat()} a {hoje.isoformat()}.",
        categoria="DIA_UTIL",
        data_local=hoje,
        inicio_janela=inicio,
        fim_janela=hoje,
    )
