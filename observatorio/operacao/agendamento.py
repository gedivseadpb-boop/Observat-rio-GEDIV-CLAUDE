"""Regras de calendário para a coleta automática do Observatório DOE · GEDIV.

Política operacional:
- Coleta automática TODOS OS DIAS (inclusive sábados, domingos e feriados), nas janelas
  de 09:00 e 14:00 (fuso America/Sao_Paulo): o DOE pode ter edição regular, suplementar
  ou extraordinária em qualquer dia. A ausência de edição só é registrada após consultar
  a fonte oficial, nunca presumida por calendário.
- Feriados listados em `feriados_oficiais.txt` aparecem apenas como metadado informativo.
- Datas exibidas ao operador seguem `DD/MM/YYYY`.
- A janela de recuperação recua 3 dias para cobrir falhas de execuções anteriores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FUSO_PADRAO = "America/Sao_Paulo"
JANELAS_HORARIO = ("09:00", "14:00")
DIAS_RECUO = 3
NOMES_DIA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


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
    categoria: str  # "DIARIA", "MANUAL_EXCEPCIONAL"
    data_local: date
    inicio_janela: date
    fim_janela: date
    feriado: str | None = None


def formatar_data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _ler_data(texto: str) -> date:
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return date.fromisoformat(texto)


def carregar_feriados(caminho: Path | None) -> dict[date, str]:
    """Lê feriados oficiais (`DD/MM/YYYY [descrição]` ou `YYYY-MM-DD [descrição]`).
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
            d = _ler_data(partes[0])
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
    inicio = hoje - timedelta(days=DIAS_RECUO)

    if modo_manual:
        return DecisaoAgendamento(
            executar=True,
            motivo="Execução manual excepcional autorizada pelo operador.",
            categoria="MANUAL_EXCEPCIONAL",
            data_local=hoje,
            inicio_janela=inicio,
            fim_janela=hoje,
        )

    feriado = carregar_feriados(feriados_arq).get(hoje)
    aviso_feriado = (
        f" Feriado informado ({feriado}): a coleta do DOE é executada normalmente."
        if feriado is not None
        else ""
    )
    return DecisaoAgendamento(
        executar=True,
        motivo=(
            f"Coleta diária autorizada ({NOMES_DIA[hoje.weekday()]}, {formatar_data_br(hoje)}); "
            f"janela de recuperação {formatar_data_br(inicio)} a {formatar_data_br(hoje)}.{aviso_feriado}"
        ),
        categoria="DIARIA",
        data_local=hoje,
        inicio_janela=inicio,
        fim_janela=hoje,
        feriado=feriado,
    )
