# Painel Diário Oficial | GEDIV

Observatório automatizado das publicações do Diário Oficial do Estado da Paraíba relacionadas à
Gerência Executiva de Concessão de Direitos e Vantagens (GEDIV/SEAD-PB).

Abrange dois eixos principais — **Progressão Funcional** (modalidades Horizontal e Vertical A–F, por grupo do PCCR, mantendo expressões não homologadas como `PENDENTE:TEC. ADM` e `PENDENTE:STF` separadas) e **Tempo de Serviço/Contribuição** (subcategorias `TS-01` a `TS-07` e **Abono de Permanência**, sem `TS-08`) — além de **Outros benefícios**, **Publicações do dia** e **Histórico**.

Este é o repositório canônico oficial (`gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE`).

> **Demonstração Pública Gratuita (GitHub Pages):** a prévia estática interativa do Painel Unificado (**Delicadeza Visual**, dados 100% sintéticos, sem backend e sem custos de hospedagem) está publicada em https://gedivseadpb-boop.github.io/gediv-painel-unificado-previa/ (repositório dedicado `gedivseadpb-boop/gediv-painel-unificado-previa`, preservando o GitHub Pages legado). Veja detalhes em [docs/30-previa-publica-github-pages.md](docs/30-previa-publica-github-pages.md). Os guias em `deploy_autonomo/` permanecem preservados apenas como documentação histórica/opcional para backend em servidor Linux, não sendo requisito atual.

---

## 1. Situação e Estágios de Maturidade

Para total transparência institucional, o projeto distingue estritamente três estágios:

**Implementado localmente → Homologado em teste → Ativado em produção**

| Componente / Funcionalidade | Implementado localmente | Homologado em teste | Ativado em produção | Observações e Pendências |
| :--- | :---: | :---: | :---: | :--- |
| Coleta DOE-PB por fonte (`auniao`, `cge`) e retomada | Sim | Sim (lotes locais) | **Não** | Requer execução prévia de `observatorio.sonda` na VM Linux definitiva |
| Agendamento diário (12:00 `America/Sao_Paulo`), inclusive sábados, domingos e feriados | Sim | Sim (testes automatizados) | **Não** | Timer `systemd` preparado em `deploy_autonomo/`; não ativado em servidor definitivo |
| Leitura por colunas, OCR (`tesseract-ocr-por`) e qualidade | Sim | Sim (acervo local) | **Não** | Preserva revisões humanas em releituras |
| Classificação GEDIV (Vertical A–F, Horizontal, TS-01..TS-07, Abono de Permanência, Outros) | Sim | Sim | **Não** | `TEC. ADM` vs `AST` e `STF` vs `SFT` aguardam deliberação formal da GEDIV |
| Painel Unificado (`/painel`) com 7 abas e build reproduzível sem dados embutidos | Sim | Sim (4 resoluções) | **Não** | Construído a partir de `observatorio/web/unificado/modelo-base-sanitizado.html` |
| Controle de acesso RBAC em 3 perfis (`Público`, `Gerência`, `Administração`) | Sim | Sim | **Não** | Contas nominais `scrypt` em `contas.sqlite3` |
| Revisão documental humana com trilha de auditoria imutável (`POST /api/revisao`) | Sim | Sim (banco descartável) | **Não** | Exige conta autenticada, justificativa e confirmação de fonte/vínculo |
| Recebimento administrativo de lotes (`POST /api/admin/lote`) | **Somente validação** | **Somente validação** | **Não** | **PENDÊNCIA OPERACIONAL:** valida formato/duplicidades e audita, mas **não importa** no banco principal |
| Implantação em servidor Linux institucional (documentação histórica/opcional) | Preparado | Em banco de teste | **Não** | Não obrigatório; prévia pública gratuita prioriza GitHub Pages com dados sintéticos |
| Prévia pública estática gratuita no GitHub Pages (repositório separado, dados 100% sintéticos) | Sim | Sim (desktop e mobile) | **Prévia sintética ativa** | Publicada via GitHub Actions em `gediv-painel-unificado-previa` (sem backend e sem dados reais) |

---

## 2. Como Usar e Executar Localmente

Requisito: Python 3.11 ou superior (`python -m pip install -r requirements.txt` para leitura de PDFs e `python -m pip install -r requirements-dev.txt` para ambiente de testes). O OCR requer `tesseract-ocr` com o pacote de idioma português (`por`). A API HTTP e o painel web utilizam exclusivamente a biblioteca padrão do Python.

### 2.1. Demonstração e homologação local com dados sintéticos (ambiente isolado)

Existem dois conjuntos sintéticos isolados, com finalidades distintas:

1. **Base de demonstração com PDFs sintéticos (`demonstracao`):** exercita também o pipeline de geração/leitura de PDFs:

```bash
python -m pip install -r requirements-dev.txt
python -m observatorio.operacao demonstracao --dados dados-demo
python -m observatorio.operacao publicar-snapshot-publico --dados dados-demo
python -m observatorio.web --dados dados-demo
```

2. **Base sintética canônica de homologação (alinhada ao GitHub Pages — 6 edições, 42 Progressões Verticais nas 5 situações A–F):** gerada pela fonte única `observatorio/operacao/previa_sintetica.py`:

```bash
python scripts/preparar_previa_github_pages.py --banco-local dados-previa-sintetica
python -m observatorio.operacao publicar-snapshot-publico --dados dados-previa-sintetica
python -m observatorio.web --dados dados-previa-sintetica
```

Acesse `http://127.0.0.1:8000/painel/`. Sem autenticação, o painel opera no perfil **Público** consumindo o `snapshot_publico.json` congelado (exibindo apenas indicadores agregados protegidos ≥ 5 de decisões conferidas, sem nomes, matrículas, processos ou PDFs).

### 2.1.1. Publicação e validação do snapshot público (`publicar-snapshot-publico`)

```bash
python -m observatorio.operacao publicar-snapshot-publico --dados PASTA [--saida ARQUIVO.json]
```

- **Finalidade:** gera, valida integralmente e grava de forma atômica (`.tmp` + `fsync` + `os.replace`) o arquivo `snapshot_publico.json` consumido pela consulta pública da aplicação com backend (`/api/painel` e `/api/data`).
- **Argumentos:** `--dados PASTA` (padrão `dados`, diretório contendo `observatorio.sqlite3`) e `--saida ARQUIVO.json` (opcional; quando omitido, grava em `<PASTA>/snapshot_publico.json`).
- **Condições de uso e falha fechada:** exige que `<PASTA>/observatorio.sqlite3` já exista. Se o banco não existir, retorna JSON `{"resultado": "BANCO_AUSENTE", "codigo_de_saida": 4}` com código de saída `4` (`NAO_EXECUTADO`), **sem criar banco SQLite vazio**. Se o snapshot violar qualquer regra de validação, retorna `SNAPSHOT_INVALIDO` com código `1` sem sobrescrever o arquivo anterior.
- **Proteção de dados pessoais:** aplica k-anonymity (`>= 5` decisões e `>= 5` matrículas distintas), faixas de largura 5, granularidade mensal, supressão complementar e secundária (inclusive em `por_situacao_nivel_vertical` e `resumo_nivel_vertical`), zerando `rows`, `events`, `resenhas` e `transicoes`. O resumo exibido em `stdout` contém apenas agregados protegidos (sem PII).

Veja a comparação detalhada entre a **prévia pública estática (GitHub Pages)** e a **aplicação com backend Python/SQLite** em [docs/30-previa-publica-github-pages.md](docs/30-previa-publica-github-pages.md).

### 2.2. Reconstrução reproduzível do frontend (sem dependências externas)

O painel unificado (`observatorio/web/unificado/index.html`) é gerado de forma determinística a partir do modelo sanitizado versionado (`observatorio/web/unificado/modelo-base-sanitizado.html`) e validado contra a paleta oficial de 240 cores (`observatorio/web/unificado/paleta-aprovada.json`):

```bash
python scripts/construir_painel_unificado.py
```

Nenhum dado pessoal, processo, matrícula ou caminho local faz parte do modelo ou do HTML gerado.

### 2.3. Gestão de contas nominais e perfis RBAC (`Público`, `Gerência`, `Administração`)

As contas de acesso são armazenadas com hash `scrypt` e sal individual em `contas.sqlite3` (separado do banco de publicações):

```bash
# Criar conta de Gerência (consulta documental, PDFs, exportações e revisão auditada)
python -m observatorio.web.usuarios --dados dados criar nome.analista --nome "Nome do Analista" --papel gerencia

# Criar conta de Administração (inclui gestão de usuários e validação preliminar de lotes)
python -m observatorio.web.usuarios --dados dados criar nome.gestor --nome "Nome do Gestor" --papel admin

# Alterar papel de conta existente (encerra sessões abertas da conta)
python -m observatorio.web.usuarios --dados dados papel nome.analista --papel admin

# Listar contas cadastradas
python -m observatorio.web.usuarios --dados dados listar
```

### 2.4. Comandos operacionais do pipeline (coleta, leitura, classificação e revisão)

```bash
python -m observatorio.sonda --saida sonda.json
python -m observatorio.coleta descobrir --inicio 2026-01-01
python -m observatorio.coleta piloto --fonte auniao
python -m observatorio.coleta lote --fonte auniao
python -m observatorio.coleta progresso | inventario | conferir
python -m observatorio.leitura processar [--refazer]
python -m observatorio.leitura validar --saida validacao.json
python -m observatorio.gerencias.gediv classificar [--refazer] | situacao | catalogo
python -m observatorio.revisao fila | ato ID ... | decisao ID ... | evento ID ... | trilha
```

### 2.5. Execução das suítes de testes

```bash
# Suíte completa Python (sem acesso à internet e sem tocar em bancos oficiais)
python -m unittest discover -s tests -t . -v

# Testes JavaScript do pacote estático e acessibilidade estrutural (quando Node.js 20+ estiver instalado)
npm ci --ignore-scripts --no-audit --no-fund
npm test
node --test tests/test_revisao_2910.cjs

# Testes de acessibilidade e responsividade em navegador real (Playwright: Tab, Shift+Tab, Enter, Espaço, Escape, 1440/768/390px)
npm run test:a11y
node tests/test_acessibilidade_navegador.cjs --url http://127.0.0.1:8000/painel/
```

---

## 3. Segurança, Sessões, CORS e Controle de Acesso

1. **Separação estrita de perfis no backend (`observatorio/web/servidor.py`):**
   - **Público:** recebe exclusivamente indicadores agregados confirmados (`rows: []`, `events: []`); exportação individual `.csv` e rotas documentais retornam `HTTP 401`.
   - **Gerência (`papel = "gerencia"`):** consulta individualizada (`Por resenha` e `Por processo`), PDFs oficiais (`/api/pdf/<sha256>`), exportações completas, revisão documental auditada (`POST /api/revisao`) e trilha de auditoria (`GET /api/auditoria`). Não possui acesso a rotas administrativas (`HTTP 403`).
   - **Administração (`papel = "admin"`):** possui acesso às rotas administrativas (`GET /api/admin/usuarios` e `POST /api/admin/lote`).
2. **Token técnico legado (`GEDIV_TOKEN_GERENCIA`):**
   - **Desabilitado por padrão** na inicialização do servidor (`python -m observatorio.web`).
   - Só pode ser ativado mediante flag explícita `--habilitar-token-tecnico` (ou `GEDIV_HABILITAR_TOKEN_TECNICO=1`) com segredo de no mínimo **32 caracteres**.
   - Comparado em tempo constante (`hmac.compare_digest`), restrito ao papel `gerencia` (nunca concede papel `admin`) e todo uso é registrado na tabela `auditoria` (`USO_TOKEN_TECNICO_LEGADO`) identificando apenas o prefixo SHA-256 do token.
3. **Sessões e armazenamento no cliente:**
   - O servidor emite cookie de sessão `gediv_sessao` com `HttpOnly; SameSite=Strict; Path=/api; Max-Age=28800` (e `Secure` sob HTTPS / `X-Forwarded-Proto: https`), aplicando validação anti-CSRF (`Sec-Fetch-Site` e `Origin`) em requisições `POST` autenticadas por cookie.
   - Por compatibilidade com a interface SPA atual, o frontend também mantém suporte ao cabeçalho `Authorization: Bearer` em `sessionStorage` (nunca em `localStorage`). Como `sessionStorage` permanece acessível a JavaScript em caso de XSS, a migração para autenticação exclusivamente via cookie `HttpOnly + Secure` atrás de proxy HTTPS institucional está documentada como etapa recomendada de produção.
   - As sessões expiram em 8 horas e são revogadas imediatamente no logout, na desativação do usuário, na troca de senha ou na alteração de papel.
4. **Política CORS:**
   - Desabilitada por padrão; quando configurada via `--origem-admin`, aceita exclusivamente origens `https://` explícitas, rejeitando curingas (`*`), `null`, `http://` e `localhost`/`127.0.0.1`.

---

## 4. Pendências Operacionais e de Produção

1. **Importação definitiva de lotes (`POST /api/admin/lote` — PENDÊNCIA OPERACIONAL):**
   - A rota `POST /api/admin/lote` e o modal administrativo correspondente (`Validar lote oficial (sem importação no banco)`) executam **exclusivamente a validação preliminar** de estrutura e verificação de IDs já existentes, registrando a tentativa na trilha de auditoria (`modo: SOMENTE_VALIDACAO`, `importado: false`), **sem gravar registros no banco principal**. A incorporação de novos documentos continua ocorrendo exclusivamente pelo pipeline oficial de coleta e leitura de PDFs.
2. **Deliberações normativas da GEDIV:** ver [docs/homologacao/questoes-pendentes-gediv.md](docs/homologacao/questoes-pendentes-gediv.md) (`Q1` a `Q10`, incluindo vínculo normativo de `TEC. ADM` com `AST` e de `STF` com `SFT`).
3. **Implantação, agendamento diário e backup/restauração:** ver [deploy_autonomo/GUIA_IMPLANTACAO_AUTONOMA.md](deploy_autonomo/GUIA_IMPLANTACAO_AUTONOMA.md).

---

## 5. Regras deste Repositório

- **Nunca versionar** a pasta `dados/`, bancos `.sqlite3`, backups, PDFs do acervo, exportações `.xlsx`/`.csv`, arquivos `.env`, senhas, tokens ou dados pessoais.
- Integração por branch dedicada e Pull Request revisado após aprovação integral da suíte de testes.
