"""Códigos de saída dos comandos de operação — contrato para agendadores (ex.: GitHub Actions).

| Código | Situação                    | O que o agendador deve fazer                                           |
|--------|-----------------------------|------------------------------------------------------------------------|
| 0      | SUCESSO                     | nada: trabalho integralmente concluído                                 |
| 1      | FALHA                       | alertar; exige intervenção (erro de execução ou divergência)           |
| 2      | USO_INCORRETO               | corrigir a chamada (argumentos inválidos; código padrão do argparse)   |
| 3      | CONCLUIDO_COM_PENDENCIAS    | não é falha fatal: dados gravados e retomáveis; tentar de novo/revisar |
| 4      | NAO_EXECUTADO               | faltam insumos (arquivos, dados privados); nada foi avaliado           |

Nenhuma execução com falha relevante sai com 0. Uma pendência recuperável não é sucesso integral (3), e também
não é tratada como falha fatal (1): o estado gravado permite retomar.
"""
from __future__ import annotations

SUCESSO, FALHA, USO_INCORRETO, CONCLUIDO_COM_PENDENCIAS, NAO_EXECUTADO = 0, 1, 2, 3, 4

NOMES = {SUCESSO: "SUCESSO", FALHA: "FALHA", USO_INCORRETO: "USO_INCORRETO",
         CONCLUIDO_COM_PENDENCIAS: "CONCLUIDO_COM_PENDENCIAS", NAO_EXECUTADO: "NAO_EXECUTADO"}


def pior(*codigos: int) -> int:
    """Combina resultados de etapas: falha > não executado > pendências > sucesso."""
    ordem = (FALHA, NAO_EXECUTADO, CONCLUIDO_COM_PENDENCIAS, SUCESSO)
    presentes = set(codigos) or {SUCESSO}
    return next(c for c in ordem if c in presentes)
