# Guia de Implantação Autônoma e Operação Segura — Observatório GEDIV

Este guia descreve os procedimentos de implantação, agendamento automático diário (inclusive fins de semana e feriados), controle de acesso em três perfis, backup e restauração do Observatório GEDIV em servidor Linux persistente, mantendo o repositório canônico `gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE` como **única referência oficial de código**.

> **Nota de Documentação Histórica / Opcional:** Para a **demonstração pública gratuita**, a decisão atual do projeto prioriza o **GitHub Pages** estático com dados 100% sintéticos em repositório separado ([docs/30-previa-publica-github-pages.md](../docs/30-previa-publica-github-pages.md)), sem servidores institucionais ou infraestrutura externa obrigatória. Este guia Linux/`systemd` permanece preservado apenas como referência histórica/opcional para eventual uso futuro do backend completo.
>
> **Status:** Procedimentos e scripts implementados e validados por testes automatizados locais; **não ativados em servidor de produção** e **não obrigatórios** para a demonstração pública no GitHub Pages. Nenhum script deste pacote publica dados automaticamente em repositórios antigos (`gediv-painel-redesign-preview` e `gediv-conferencia-privada` estão desacoplados e desativados).

---

## 1. Opções de Hospedagem Persistente (Linux Ubuntu 24.04 LTS)

### Opção Recomendada: VM Linux Institucional (SEAD-PB / CODATA)
- **Vantagem técnica:** conectividade direta na rede governamental estadual com `auniao.pb.gov.br` e `cge.pb.gov.br`, controle institucional de firewall/VPN e ausência de encerramento por ociosidade.

### Alternativa em Nuvem: Instância Linux Dedicada (ex.: Oracle Cloud *Always Free* `sa-saopaulo-1` / `sa-vinhedo-1`)
- **Requisito obrigatório antes da migração:** executar a sonda de conectividade a partir do IP da VM para confirmar ausência de bloqueio anti-robô pelas fontes oficiais:
  ```bash
  /opt/observatorio-gediv/.venv/bin/python -m observatorio.sonda --saida /tmp/sonda_vm.json
  ```
  Se a sonda retornar falha de acesso às fontes oficiais (código `4`), utilize a VM institucional da SEAD-PB.

---

## 2. Preparação do Ambiente Isolado na VM Linux

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-por git
sudo useradd --system --create-home --shell /bin/bash gediv || true
sudo mkdir -p /opt/observatorio-gediv /var/lib/gediv/dados /var/lib/gediv/backups /etc/gediv
sudo chmod 700 /var/lib/gediv/dados /var/lib/gediv/backups /etc/gediv
sudo chown -R gediv:gediv /opt/observatorio-gediv /var/lib/gediv
```

Instalação das dependências declaradas em ambiente virtual isolado (`.venv`):

```bash
cd /opt/observatorio-gediv
sudo -u gediv python3 -m venv .venv
sudo -u gediv .venv/bin/pip install --upgrade pip
sudo -u gediv .venv/bin/pip install -r requirements.txt
```

Transferência privada da base SQLite e do acervo de PDFs (via `scp`/`sftp` privado, **nunca via Git**):

```bash
sudo -u gediv /opt/observatorio-gediv/.venv/bin/python -m observatorio.coleta conferir --dados /var/lib/gediv/dados
```

---

## 3. Autenticação Nominal, Perfis RBAC e Segurança do Servidor Web

O servidor web (`observatorio.web`) opera com três perfis distintos impostos no backend:

1. **Público (sem login):** acesso somente a indicadores agregados confirmados e informações de cobertura (`rows: []`).
2. **Gerência (`papel = "gerencia"`):** consulta documental individualizada (`Por resenha` e `Por processo`), PDFs do acervo (`/api/pdf/<sha256>`), exportações filtradas e revisão documental auditada (`POST /api/revisao`).
3. **Administração (`papel = "admin"`):** inclui gestão/listagem de contas (`GET /api/admin/usuarios`) e validação preliminar de lotes (`POST /api/admin/lote`).

### Criação de contas nominais (obrigatória antes de iniciar o serviço)

```bash
# Conta de Gerência
sudo -u gediv /opt/observatorio-gediv/.venv/bin/python -m observatorio.web.usuarios \
  --dados /var/lib/gediv/dados criar analista.gediv --nome "Nome do Analista" --papel gerencia

# Conta de Administração
sudo -u gediv /opt/observatorio-gediv/.venv/bin/python -m observatorio.web.usuarios \
  --dados /var/lib/gediv/dados criar admin.gediv --nome "Nome do Administrador" --papel admin
```

- **Token técnico legado (`GEDIV_TOKEN_GERENCIA`):** permanece **desabilitado por padrão**. Não deve ser utilizado como substituto de contas nominais administrativas (mesmo quando habilitado excepcionalmente com `--habilitar-token-tecnico` e segredo de 32+ caracteres, concede apenas perfil `gerencia` e tem cada uso registrado na auditoria).
- **Serviço `gediv-admin.service`:** escuta apenas em `127.0.0.1:8000` e deve ser exposto exclusivamente atrás de proxy reverso institucional HTTPS (com TLS válido e `X-Forwarded-Proto: https`, ativando a flag `Secure` no cookie `HttpOnly` `gediv_sessao`) ou rede VPN interna.

---

## 4. Coleta Automática Diária (Todos os Dias, Inclusive Fins de Semana e Feriados)

O agendamento automático é controlado por `deploy_autonomo/gediv-diario.timer`, `deploy_autonomo/gediv-diario.service`, `deploy_autonomo/rodar_diario.sh` e pelo módulo `observatorio.operacao.agendamento`:

- **Horário programado:** todos os dias (`OnCalendar=*-*-*`), às **12:00** no fuso horário `America/Sao_Paulo`. O timer pode acrescentar até dois minutos de atraso aleatório.
- **Sem disparo extra ao reiniciar:** se o servidor estiver desligado em um horário programado, a coleta será tentada na próxima janela. A rotina busca também os três dias anteriores; interrupções maiores podem exigir recuperação manual.
- **Sem bloqueio de calendário:** sábados, domingos e feriados executam a coleta normalmente, pois o DOE pode ter edição regular, suplementar ou extraordinária em qualquer dia.
- **Feriados são apenas informativos:** datas listadas em `/etc/gediv/feriados_oficiais.txt` (modelo em `deploy_autonomo/feriados_oficiais.example.txt`, formato `DD/MM/YYYY`) aparecem apenas como aviso informativo no log e no campo `feriado` de `agendamento.avaliar_execucao()`. A ausência de edição só é registrada no manifesto de cobertura após consulta à fonte oficial, nunca presumida por calendário.
- **Datas ao operador:** mensagens de agendamento e do `rodar_diario.sh` exibem datas em `DD/MM/YYYY`; os parâmetros da CLI continuam em `AAAA-MM-DD`.
- **Prevenção de concorrência e retomada:** `rodar_diario.sh` utiliza trava exclusiva `flock -n 9` em `.gediv-coleta.lock`. A janela automática recua **3 dias** para cobrir falhas de execuções anteriores.
- **Recuperação retroativa manual (fora do cron):**
  ```bash
  sudo -u gediv /opt/observatorio-gediv/deploy_autonomo/recuperar_edicoes_manual.sh 2026-11-10 2026-11-18
  ```

### Habilitação do timer (somente após homologação da VM)

```bash
sudo cp /opt/observatorio-gediv/deploy_autonomo/feriados_oficiais.example.txt /etc/gediv/feriados_oficiais.txt
sudo cp /opt/observatorio-gediv/deploy_autonomo/gediv-diario.service /etc/systemd/system/
sudo cp /opt/observatorio-gediv/deploy_autonomo/gediv-diario.timer /etc/systemd/system/
sudo systemctl daemon-reload
# Teste manual prévio obrigatório:
sudo -u gediv PUBLICAR_PAGES=0 /opt/observatorio-gediv/deploy_autonomo/rodar_diario.sh
# Ativação quando autorizado:
sudo systemctl enable --now gediv-diario.timer
sudo systemctl list-timers gediv-diario.timer
```

---

## 5. Procedimento de Backup Consistente e Restauração Testada

### 5.1. Backup consistente (executado automaticamente por `rodar_diario.sh` ou manualmente)

O backup utiliza a API nativa de cópia transacional do SQLite (`src.backup(dst)`), seguida de verificação `PRAGMA integrity_check == 'ok'` e geração de arquivo `.sha256`:

```bash
DATA_REF=$(date +%F)
ARQ_BAK="/var/lib/gediv/backups/observatorio-${DATA_REF}.sqlite3"
sudo -u gediv /opt/observatorio-gediv/.venv/bin/python - "$ARQ_BAK" <<'PY'
import contextlib, pathlib, sqlite3, sys
origem = pathlib.Path("/var/lib/gediv/dados/observatorio.sqlite3")
destino = pathlib.Path(sys.argv[1])
with contextlib.closing(sqlite3.connect(origem.resolve().as_uri() + "?mode=ro", uri=True)) as src:
    with contextlib.closing(sqlite3.connect(destino)) as dst:
        src.backup(dst)
with contextlib.closing(sqlite3.connect(destino.resolve().as_uri() + "?mode=ro", uri=True)) as chk:
    res = chk.execute("PRAGMA integrity_check").fetchone()[0]
    if res != "ok":
        raise SystemExit(f"Falha de integridade no backup: {res}")
print("Backup integro:", destino)
PY
sha256sum "$ARQ_BAK" > "${ARQ_BAK}.sha256"
```

### 5.2. Restauração segura

```bash
sudo systemctl stop gediv-admin.service gediv-diario.timer
sha256sum -c /var/lib/gediv/backups/observatorio-YYYY-MM-DD.sqlite3.sha256
sudo -u gediv cp /var/lib/gediv/backups/observatorio-YYYY-MM-DD.sqlite3 /var/lib/gediv/dados/observatorio.sqlite3
sudo systemctl start gediv-admin.service gediv-diario.timer
```

---

## 6. Pendências Operacionais Documentadas para Produção

1. **Importação definitiva na rota `POST /api/admin/lote` (`PENDÊNCIA OPERACIONAL`):**
   - A ação administrativa de lote na interface web realiza **exclusivamente validação preliminar e registro em auditoria** (`modo: SOMENTE_VALIDACAO`, `importado: false`), sem gravar registros no banco SQLite principal. A entrada oficial de documentos permanece restrita ao pipeline de coleta/leitura de PDFs (`observatorio.coleta` / `observatorio.operacao`).
2. **Transição completa para sessão exclusiva por cookie `HttpOnly + Secure`:**
   - Embora o backend já emita e valide o cookie `gediv_sessao` (`HttpOnly; SameSite=Strict; Path=/api`, com `Secure` sob HTTPS e proteção CSRF), o cliente SPA ainda mantém o token em `sessionStorage` para chamadas `Bearer`. Em produção sob HTTPS institucional, recomenda-se desativar a persistência em `sessionStorage` para mitigar exposição a eventual XSS.
3. **Backup externo (*off-site*):**
   - Configurar cópia criptografada diária de `/var/lib/gediv/backups/` e `/var/lib/gediv/dados/contas.sqlite3` para armazenamento institucional externo à VM.
