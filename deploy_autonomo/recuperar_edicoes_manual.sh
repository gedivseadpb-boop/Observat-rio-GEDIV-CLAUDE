#!/usr/bin/env bash
set -euo pipefail

# Comando MANUAL EXCEPCIONAL para recuperação retroativa de edições do DOE-PB.
# Separado do agendamento automático (gediv-diario.timer), compartilha a mesma trava
# flock para impedir concorrência com a rotina de dias úteis.
#
# Uso:
#   ./deploy_autonomo/recuperar_edicoes_manual.sh 2026-09-10 2026-09-15

if [ "$#" -lt 2 ]; then
  echo "Uso: $0 <DATA_INICIO YYYY-MM-DD> <DATA_FIM YYYY-MM-DD>"
  exit 2
fi

export TZ="${TZ:-America/Sao_Paulo}"
INICIO="$1"
FIM="$2"

APP_DIR="${APP_DIR:-/opt/observatorio-gediv}"
DADOS_DIR="${DADOS_DIR:-/var/lib/gediv/dados}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
LOCK_ARQ="${LOCK_ARQ:-$DADOS_DIR/.gediv-coleta.lock}"

mkdir -p "$DADOS_DIR"

exec 9>"$LOCK_ARQ"
if ! flock -n 9; then
  echo "[BLOQUEADO] Outra coleta/processamento já está em execução ($LOCK_ARQ)."
  exit 1
fi

cd "$APP_DIR"
echo "[MANUAL] Recuperando edições de $INICIO até $FIM..."
"$PYTHON_BIN" -m observatorio.operacao coletar-intervalo --inicio "$INICIO" --fim "$FIM" --dados "$DADOS_DIR"
echo "[MANUAL] Executando leitura/OCR e classificação incremental..."
"$PYTHON_BIN" -m observatorio.operacao executar --dados "$DADOS_DIR"
echo "[MANUAL] Recuperação concluída sem sobrescrever documentos originais ou revisões humanas."
