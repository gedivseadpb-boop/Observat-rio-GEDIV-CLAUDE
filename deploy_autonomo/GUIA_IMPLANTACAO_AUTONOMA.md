# Guia de Implantação Autônoma e Gratuita — Observatório GEDIV

Este pacote permite executar o Observatório GEDIV de forma **100% autônoma e gratuita**, sem depender do computador da responsável e **sem alterar absolutamente nada no layout** do painel definitivo (`gediv-painel-redesign-preview`, branch `gh-pages`).

---

## 1. Avaliação das opções gratuitas de hospedagem

### Opção 1 (Preferida): Oracle Cloud *Always Free* — São Paulo (`sa-saopaulo-1`) ou Vinhedo (`sa-vinhedo-1`)
* **Limites gratuitos aplicáveis:**
  * **Compute ARM Ampere A1:** pool gratuito de 1.500 OCPU-horas e 9.000 GB-horas/mês (equivalente a **2 OCPUs e 12 GB de RAM** contínuos, ou 1 VM de 2 OCPU / 12 GB RAM). *Alternativa x86:* até 2 VMs `VM.Standard.E2.1.Micro` (1 GB RAM cada).
  * **Disco:** até **200 GB** de Block Volume gratuitos (suficiente para anos de PDFs do DOE-PB e SQLite — o acervo inteiro de 2026 até 19/11 ocupa ~600 MB).
  * **Rede:** até **10 TB/mês** de saída gratuita.
* **Riscos e cuidados reais na Oracle Always Free:**
  1. **Escassez regional (`Out of host capacity`):** as regiões São Paulo e Vinhedo frequentemente ficam sem capacidade gratuita de instâncias ARM Ampere A1; pode exigir tentativas em horários alternativos ou usar `E2.1.Micro` (com swap de 2 GB para PDFs maiores).
  2. **Reclamação automática por ociosidade:** instâncias gratuitas são encerradas se CPU (95º percentil), rede e memória (em ARM) ficarem simultaneamente **abaixo de 20% por 7 dias seguidos**. (Observação: executar o `rodar_diario.sh` + OCR diariamente ajuda, e deve-se monitorar o uso de memória/CPU para não cair na regra.)
  3. **Bloqueio de firewall da Paraíba (TESTE OBRIGATÓRIO):** antes de migrar tudo, é obrigatório rodar `python -m observatorio.operacao sonda` **dentro da VM Oracle** para comprovar se `auniao.pb.gov.br` aceita conexões desse IP brasileiro ou se bloqueia qualquer datacenter.
  4. **Custo zero garantido:** **não** fazer upgrade para conta paga sem autorização expressa; manter apenas recursos marcados como *Always Free Eligible*.

### Opção 2 (Alternativa garantida se a Oracle bloquear ou não tiver capacidade): VM Linux institucional da SEAD-PB
* Custo: **R$ 0** em infraestrutura própria da secretaria.
* Vantagem: rede governamental brasileira com acesso direto garantido a `auniao.pb.gov.br` e `cge.pb.gov.br`, sem risco de reclamação por inatividade.
* Utiliza exatamente os mesmos arquivos deste pacote (`rodar_diario.sh`, `gediv-diario.service`, `gediv-diario.timer`, `gediv-admin.service`).

---

## 2. Pré-requisitos na VM Linux (Ubuntu 24.04 LTS)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-por git
sudo useradd --system --create-home --shell /bin/bash gediv || true
sudo mkdir -p /opt/observatorio-gediv /opt/gediv-painel-redesign-preview /var/lib/gediv/dados /var/lib/gediv/backups /etc/gediv
sudo chown -R gediv:gediv /opt/observatorio-gediv /opt/gediv-painel-redesign-preview /var/lib/gediv
```

Instalar dependências Python do projeto (sem extras pagos ou PaddleOCR/PyMuPDF AGPL):
```bash
cd /opt/observatorio-gediv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### Teste obrigatório de conectividade na VM (Sonda)
```bash
/opt/observatorio-gediv/.venv/bin/python -m observatorio.operacao sonda --fonte auniao --saida /tmp/sonda_vm.json
cat /tmp/sonda_vm.json
```
* **Resultado esperado:** código de saída `0` (`"situacao": "DOWNLOAD_INTEGRO"`). Se sair com `4`, a fonte bloqueou a VM e deve-se usar a VM institucional da SEAD-PB.

---

## 3. Transferência inicial da base já processada (2026)

Copie com segurança (SCP/SFTP privado, nunca via repositório público) a pasta local `dados/` (ou o backup `observatorio-2026-11-19.sqlite3` + pasta `acervo/`) para `/var/lib/gediv/dados/`, e confira a integridade:
```bash
/opt/observatorio-gediv/.venv/bin/python -m observatorio.coleta conferir --dados /var/lib/gediv/dados
```

---

## 4. Ativar agendamento automático e publicação exclusiva de `dados.json`

1. Configure um **Fine-grained Personal Access Token** (ou Deploy Key SSH) com permissão de escrita **apenas** no repositório `gedivseadpb-boop/gediv-painel-redesign-preview`.
2. Clone o repositório do painel em `/opt/gediv-painel-redesign-preview` na branch `gh-pages`.
3. Teste manualmente o script em modo seguro (`PUBLICAR_PAGES=0`):
   ```bash
   sudo -u gediv PUBLICAR_PAGES=0 /opt/observatorio-gediv/deploy_autonomo/rodar_diario.sh
   ```
4. Somente após validar e obter autorização da responsável, altere `Environment=PUBLICAR_PAGES=1` em `/etc/systemd/system/gediv-diario.service` e habilite o timer:
   ```bash
   sudo cp /opt/observatorio-gediv/deploy_autonomo/gediv-diario.service /etc/systemd/system/
   sudo cp /opt/observatorio-gediv/deploy_autonomo/gediv-diario.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now gediv-diario.timer
   sudo systemctl list-timers gediv-diario.timer
   ```

---

## 5. Fila de revisão humana (usuários individuais e acesso seguro)

1. Crie contas nominais individuais para a equipe GEDIV (senhas com >= 10 caracteres, armazenadas em `scrypt` no banco separado `contas.sqlite3`):
   ```bash
   /opt/observatorio-gediv/.venv/bin/python -m observatorio.web.usuarios --dados /var/lib/gediv/dados criar nome.sobrenome --nome "Nome Completo"
   ```
2. Crie `/etc/gediv/admin.env` com permissão `600` (se desejar token de fallback legado ou variáveis de ambiente).
3. Habilite `gediv-admin.service` (roda em `127.0.0.1:8000`) e exponha atrás de HTTPS gratuito com **Cloudflare Tunnel (`cloudflared`)** ou acesso via VPN institucional da SEAD.
4. À medida que a equipe conferir e aprovar decisões na fila de revisão, a próxima execução de `rodar_diario.sh` (ou execução manual) atualizará automaticamente os números conferidos no `dados.json` do GitHub Pages.

---

## 6. Checklist para consolidação futura dos repositórios (apenas após autorização)

1. Abrir PR ou avançar `main` de `Observat-rio-GEDIV-CLAUDE` a partir da linha consolidada e testada (contendo as correções e equivalências GEDIV homologadas, **sem** `dados/`, SQLite ou PDFs).
2. Confirmar workflow `Testes` 100% verde no GitHub Actions.
3. Fechar o PR nº 5 (`claude/eloquent-hawking-k43pj9`) sem merge (pois seu conteúdo já está superado na linha consolidada).
4. Em `gediv-painel-redesign-preview` (`gh-pages`), publicar **exclusivamente** o novo `dados.json` gerado e validado, preservando os 9 arquivos visuais byte a byte.
