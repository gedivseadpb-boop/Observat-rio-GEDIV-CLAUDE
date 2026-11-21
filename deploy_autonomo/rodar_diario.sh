#!/usr/bin/env bash
set -euo pipefail

# Rotina automática do Observatório DOE · GEDIV (SOMENTE DIAS ÚTEIS: Segunda a Sexta).
# Fluxo canônico:
#   trava flock -> guarda de dia útil/feriado -> coleta DOE-PB (A União + complementar)
#   -> extração/OCR/classificação -> backup SQLite íntegro -> projeção pública sanitizada.
#
# Repositório canônico único: gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE.
# Conexão obsoleta com gediv-painel-redesign-preview foi REMOVIDA para impedir publicação indevida.

export TZ="${TZ:-America/Sao_Paulo}"

APP_DIR="${APP_DIR:-/opt/observatorio-gediv}"
DADOS_DIR="${DADOS_DIR:-/var/lib/gediv/dados}"
BACKUP_DIR="${BACKUP_DIR:-/var/lib/gediv/backups}"
SAIDA_PUBLICA="${SAIDA_PUBLICA:-/tmp/gediv-dist-publica}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
FERIADOS_ARQ="${FERIADOS_ARQ:-/etc/gediv/feriados_oficiais.txt}"
RETENCAO_DIAS="${RETENCAO_DIAS:-30}"
PUBLICAR_PAGES="${PUBLICAR_PAGES:-0}" # Mantido em 0 por padrão; exige autorização explícita
LOCK_ARQ="${LOCK_ARQ:-$DADOS_DIR/.gediv-coleta.lock}"

mkdir -p "$DADOS_DIR" "$BACKUP_DIR"

# 0. Exclusão mútua: impede dois agendadores ou execução manual simultânea no mesmo banco
exec 9>"$LOCK_ARQ"
if ! flock -n 9; then
  echo "[BLOQUEADO] Outra execução do Observatório GEDIV já está em andamento ($LOCK_ARQ)."
  exit 0
fi

# 1. Guarda de calendário no fuso America/Sao_Paulo (impede execução em sábado/domingo mesmo com Persistent=true)
DATA_HOJE="$(date +%F)"
DIA_SEMANA="$(date +%u)" # 1=Segunda .. 5=Sexta, 6=Sábado, 7=Domingo

if [ "$DIA_SEMANA" -ge 6 ]; then
  echo "[IGNORADO] $DATA_HOJE é fim de semana (dia ISO=$DIA_SEMANA, fuso=$TZ). Coleta automática permitida apenas de segunda a sexta-feira."
  exit 0
fi

if [ -n "$FERIADOS_ARQ" ] && [ -f "$FERIADOS_ARQ" ]; then
  if grep -Eq "^${DATA_HOJE}([[:space:]]|#|$)" "$FERIADOS_ARQ"; then
    echo "[IGNORADO] $DATA_HOJE consta como feriado administrativo oficial em $FERIADOS_ARQ. Nenhuma coleta automática executada."
    exit 0
  fi
fi

# 2. Janela de recuperação de lacunas: na segunda-feira recua 4 dias (cobre quinta/sexta); ter-sex recua 3 dias
if [ "$DIA_SEMANA" -eq 1 ]; then
  DIAS_RECUO=4
else
  DIAS_RECUO=3
fi
INICIO_JANELA="$(date -d "$DIAS_RECUO days ago" +%F)"

cd "$APP_DIR"

echo "[1/6] Coletando edições oficiais de $INICIO_JANELA até $DATA_HOJE (fuso=$TZ, dia ISO=$DIA_SEMANA)..."
set +e
"$PYTHON_BIN" -m observatorio.operacao coletar-intervalo --inicio "$INICIO_JANELA" --fim "$DATA_HOJE" --dados "$DADOS_DIR"
RC_COLETA=$?
set -e
if [ "$RC_COLETA" -ne 0 ] && [ "$RC_COLETA" -ne 3 ]; then
  echo "ERRO: coleta retornou código $RC_COLETA (4 = fonte inacessível/bloqueio; 1/2 = falha). Abortando sem simular sucesso."
  exit "$RC_COLETA"
fi

echo "[2/6] Executando extração, OCR (quando necessário) e classificação GEDIV (somente pendentes/novos)..."
set +e
"$PYTHON_BIN" -m observatorio.operacao executar --dados "$DADOS_DIR"
RC_EXEC=$?
set -e
if [ "$RC_EXEC" -ne 0 ] && [ "$RC_EXEC" -ne 3 ]; then
  echo "ERRO: processamento retornou código $RC_EXEC. Abortando antes da projeção pública."
  exit "$RC_EXEC"
fi

echo "[3/6] Gerando backup consistente do SQLite com verificação PRAGMA integrity_check e SHA-256..."
BACKUP_ARQ="$BACKUP_DIR/observatorio-$DATA_HOJE.sqlite3"
"$PYTHON_BIN" - "$DADOS_DIR/observatorio.sqlite3" "$BACKUP_ARQ" <<'PY'
import hashlib, sqlite3, sys
from pathlib import Path

orig, dest = Path(sys.argv[1]), Path(sys.argv[2])
tmp = dest.with_suffix(".sqlite3.tmp")
with sqlite3.connect(orig.resolve().as_uri() + "?mode=ro", uri=True) as src:
    with sqlite3.connect(tmp) as dst:
        src.backup(dst)
with sqlite3.connect(tmp.resolve().as_uri() + "?mode=ro", uri=True) as chk:
    res = chk.execute("PRAGMA integrity_check").fetchone()[0]
    if res != "ok":
        raise SystemExit(f"Backup corrompido: {res}")
tmp.replace(dest)
sha = hashlib.sha256(dest.read_bytes()).hexdigest()
dest.with_suffix(".sqlite3.sha256").write_text(f"{sha}  {dest.name}\n", encoding="utf-8")
print(f"Backup OK: {dest} ({dest.stat().st_size} bytes, sha256={sha})")
PY
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'observatorio-*.sqlite3*' -mtime "+$RETENCAO_DIAS" -delete

echo "[4/6] Verificando integridade e ausência de dados pessoais no frontend aprovado de 29/10..."
"$PYTHON_BIN" - "$APP_DIR/observatorio/web/unificado/index.html" <<'PY'
import re, sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
if re.search(r"SAD-PSE-202\d/\d+", html):
    raise SystemExit("ERRO DE PRIVACIDADE: processo individual detectado no HTML estático!")
if '"rows":[{"id":' in html.replace(" ", ""):
    raise SystemExit("ERRO DE PRIVACIDADE: payload nominal embutido no HTML estático!")
print("Integridade do frontend 29/10 confirmada (0 dados pessoais embutidos).")
PY

echo "[5/6] Calculando resumo de cobertura e validando projeção somente-leitura da API para o frontend unificado..."
COBERTURA_RESUMO="$DADOS_DIR/cobertura_resumo.json"
"$PYTHON_BIN" - "$DADOS_DIR/observatorio.sqlite3" "$COBERTURA_RESUMO" <<'PY'
import json, sqlite3, sys
from pathlib import Path

from observatorio.nucleo.banco import Banco
from observatorio.painel import adaptador, indicadores

db, out = Path(sys.argv[1]), Path(sys.argv[2])
with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
    con.row_factory = sqlite3.Row
    inconclusivas = con.execute(
        "SELECT COUNT(*) FROM leitura WHERE situacao='ERRO' OR data_edicao IS NULL OR numero_edicao IS NULL"
    ).fetchone()[0]
    ausencia = con.execute("""
        SELECT COUNT(*) FROM leitura l
        WHERE l.situacao != 'ERRO' AND l.data_edicao IS NOT NULL AND l.numero_edicao IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM ato a WHERE a.sha256 = l.sha256 AND a.gerencia = 'GEDIV'
              AND a.eixo IN ('PROGRESSAO', 'TEMPO_SERVICO')
          )
    """).fetchone()[0]
    out.write_text(json.dumps({"ausencia_tecnica_edicoes": int(ausencia), "inconclusivas": int(inconclusivas)}, indent=2) + "\n", encoding="utf-8")

    banco_ro = object.__new__(Banco)
    banco_ro.caminho = db
    banco_ro.con = con
    p_pub = indicadores.painel(banco_ro, {"escopo": "pendente"}, indicadores.PUBLICO)
    if p_pub["meta"]["escopo"] != "conferido" or p_pub["linhas"] != []:
        raise SystemExit("ERRO DE PRIVACIDADE: perfil público expôs escopo pendente ou linhas individuais!")
    proj_pub = adaptador.projetar_para_dashboard_2910(p_pub, [], [])
    if proj_pub.get("rows"):
        raise SystemExit("ERRO DE PRIVACIDADE: projeção pública para o dashboard unificado contém linhas individuais!")
    cats = [c[0] for c in proj_pub.get("categories", [])]
    if "TS-08" in cats or "ABONO_PERMANENCIA" not in cats:
        raise SystemExit(f"ERRO DE CONTRATO: categorias inválidas na projeção unificada: {cats}")
print("Resumo de cobertura e projeção somente-leitura (?mode=ro) da API validados com sucesso (0 linhas individuais públicas; sem build de painel-publico/dados.json obsoleto).")
PY

echo "[6/6] Encerramento controlado..."
if [ "$PUBLICAR_PAGES" != "1" ]; then
  echo "PUBLICAR_PAGES=$PUBLICAR_PAGES (modo seguro local). Banco SQLite atualizado e pronto para consumo pelo painel unificado via API (/ e /painel)."
  exit 0
fi

echo "AVISO: publicação automática externa desativada até conclusão da contenção de segurança e definição de destino canônico autorizado."
exit 0
