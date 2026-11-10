# Fase 1 — Recuperação e diagnóstico do projeto existente

> **Mudança de estratégia (10/11/2026):** a responsável decidiu **não migrar** o código anterior. O sistema é escrito do zero; este levantamento permanece como referência. As seções 6 e 9 foram substituídas pelo plano em `02-plano-desenvolvimento.md`.

Data do levantamento: 10/11/2026.
Escopo: os quatro repositórios da conta `gedivseadpb-boop` e as duas fontes oficiais do DOE/PB.
Este documento não contém dados pessoais, PDFs, estados de coleta nem credenciais.

Legenda de confiança usada abaixo:

- **Comprovado** — verificado diretamente neste levantamento (leitura do Git, execução de comando).
- **Documentado** — afirmado em relatórios versionados dos projetos anteriores; não reexecutado agora.
- **Hipótese** — inferência ainda não testada.

## 1. O que foi e o que não foi acessado

| Fonte | Situação | Observação |
|---|---|---|
| `Observat-rio-GEDIV-CLAUDE` (oficial) | Acessado, com escrita | Estava **vazio** (sem commits). Visibilidade: **público**. |
| `robo-gediv-pb` (privado) | Acessado, leitura | 3 branches. |
| `robo-gediv-gemini` (privado) | Acessado, leitura | 4 branches. |
| `robo-gediv-V2` (privado) | Acessado, leitura | 11 branches; é o mais avançado. |
| Google Drive (pasta do projeto) | **Não acessado** | O conector disponível nesta sessão só lista drives compartilhados; não abre pastas do "Meu Drive". |
| Conversas do ChatGPT | **Não acessado** | Sem acesso. O que se sabe delas vem dos relatórios versionados no Git. |
| `auniao.pb.gov.br` e `cge.pb.gov.br` | **Sem acesso direto** a partir deste ambiente | Ver seção 5. A existência das edições de 2026 foi confirmada apenas por índice de busca. |

## 2. Linha do tempo dos repositórios

| Repositório | Período | Papel |
|---|---|---|
| `robo-gediv-pb` | 29/10/2026 | Primeira versão: `src/robo.py` (23 KB), painel estático, 2 testes, 1 workflow. |
| `robo-gediv-gemini` | 31/10 a 03/11/2026 | Cópia do anterior com piloto: extração de texto, importação do histórico, revisão em JSON, gateway/cliente para um backend, documentação extensa (`docs/`). |
| `robo-gediv-V2` | 04/11 a 09/11/2026 | Reescrita incremental do coletor e criação do portal de revisão. A `main` contém só a cópia inicial; o trabalho real está nas branches. |

## 3. Versão com evidências mais sólidas

**`robo-gediv-V2`, branch `candidata/integridade-historico-eventos-20261107`**
(commit `dbd02a8`, correspondente ao PR #4 em rascunho).

Conteúdo (52 arquivos), todos em Python + HTML/JS estático:

| Arquivo | Função |
|---|---|
| `src/robo.py` (parser v2.2) | Descoberta de edições, download, identificação de blocos GEDIV, resenhas, processos, decisões (deferido/indeferido), tipos e grupos; estado em JSON com versões e tentativas pendentes. |
| `src/leitura_doe.py` | Leitura por colunas da página, texto nativo e OCR por coluna/faixa. |
| `src/reconferencia.py` | Segunda leitura independente do PDF para conferir os registros extraídos. |
| `src/aquisicao.py` | Enumeração mensal do acervo A União, resolução `/view → @@download/file`, SHA-256, contagem de páginas. |
| `src/importacao_lote.py` | Importação de PDFs locais por manifesto, com validação de assinatura, data, URL, hash e páginas. |
| `src/checkpoint.py` | Backup cifrado (Fernet) e restauração do estado. |
| `src/portal.py` | Portal local com dois perfis (`revisao` e `gerencia`), fila de conferência, liberações, exportação Excel/PDF. |
| `src/rotina_diaria.py`, `src/relatorio.py`, `src/painel_local.py` | Rotina de atualização, relatório e painel offline. |
| `painel-interativo/` | Dashboard e tela de revisão (HTML/CSS/JS sem framework). |
| `tests/` (19 arquivos) | Testes de extração, histórico, integridade de versões, portal, importação, checkpoint, rotina diária. |

### Evidências documentadas (relatório de 09/11/2026 na branch `experimento/prova-direta-cge-20261109`)

- Importação real de dois DOEs fornecidos manualmente: 02/10/2026 (40 páginas, 58 candidatos) e 04/11/2026 (60 páginas, 41 candidatos).
- 99 candidatos em 8 resenhas, todos por texto nativo; reconferência sem divergências.
- Segunda passagem idempotente: mesmos 99 identificadores, nenhum duplicado.
- Controle de acesso do portal: sem credencial → 401; perfil errado → 403.
- Backup cifrado restaurado byte a byte; chave errada rejeitada.

### O que **não** está comprovado

- Download automático de qualquer PDF por um executor em nuvem.
- Carga histórica de 2026 (só duas edições foram processadas).
- OCR em português em documento real.
- Qualquer revisão humana: os 99 candidatos estão "A conferir"; nenhum foi liberado.
- Rotina diária em operação, hospedagem web, banco de dados.
- Os testes não foram reexecutados neste levantamento (o ambiente não tem a biblioteca PyMuPDF nem permite instalá-la).

## 4. Tentativas que falharam

| Tentativa | Resultado documentado |
|---|---|
| GitHub Actions (runner da nuvem) → A União | DNS funciona; conexão HTTPS expira (`ConnectTimeout`) em todas as execuções, em 31/10 e 09/11. |
| GitHub Actions → CGE/SAP | `ConnectTimeout` após 20 s, nenhum byte recebido (09/11). |
| Cloudflare Workers | Código de teste preparado, **não executado** de forma conclusiva (um teste manual relatou HTTP 206 parcial e depois 522). |
| Google Apps Script | Não testado. |
| Runner Windows institucional (self-hosted) | Workflow e scripts PowerShell prontos; **execução real não verificada**. |
| Integração com backend do repositório "gemini" | Apenas ensaio sem escrita (dry-run). |

## 5. Fontes oficiais — situação verificada em 10/11/2026

- **Correção (10/11/2026, mesma data):** a primeira versão deste documento afirmava que as fontes "não respondem" a partir do ambiente de desenvolvimento. A afirmação não tinha valor de prova: aquele ambiente não tem saída direta para a internet (nem `github.com` resolve), portanto nada informa sobre as fontes. As medições válidas estão em `03-etapa1-resultados.md`.
- **Comprovado por índice de busca:** existem edições de 2026 publicadas no padrão
  `https://auniao.pb.gov.br/servicos/doe/2026/<mês>/diario-oficial-DD-MM-2026-portal.pdf`
  (confirmadas edições de abril a outubro; ex.: nº 18.561 em 01/04 e nº 18.693 em 15/10).
- **Comprovado por índice:** existem arquivos com sufixo `-portal-1.pdf` (ex.: 17/09/2026), o que indica segunda versão ou suplemento no mesmo dia. O coletor precisa tratar esse caso.
- **Comprovado por índice:** há edições aos sábados (ex.: 25/07 e 01/08/2026). Não se pode presumir publicação apenas em dias úteis.
- **Documentado:** padrão CGE `https://cge.pb.gov.br/gati/Uploads/doe/2026/01-Janeiro/07-Diario Oficial 07-01-2026 TOTAL.pdf`.
- A causa da falha de acesso **não é presumida**. A investigação e os resultados medidos estão em `02-plano-desenvolvimento.md` (seção 5) e `03-etapa1-resultados.md`.

## 6. Componentes reaproveitáveis

| Componente | Destino no repositório oficial | Observação |
|---|---|---|
| `robo.py`, `leitura_doe.py`, `reconferencia.py` | `robot/` | Separar o que é leitura genérica de PDF do que é regra GEDIV (padrões, tipos, grupos). |
| `aquisicao.py`, `importacao_lote.py` | `robot/` | Acrescentar CGE como fonte complementar e o caso `-portal-1`. |
| `checkpoint.py` | `infra/` ou `robot/` | Útil para backup; deixa de ser o mecanismo principal quando houver banco. |
| `portal.py` + `painel-interativo/` | `backend/` e `frontend/` | Base da fila de revisão e do dashboard; hoje usa arquivos JSON e senha por variável de ambiente. |
| `tests/` | `tests/` | Revisar fixtures antes de migrar (ver seção 8). |
| `docs/` do repositório gemini | `docs/` | Especificação V3 e checklist servem de referência histórica. |

## 7. O que falta desenvolver (em relação à especificação)

1. Executor com acesso às fontes (pré-requisito de tudo).
2. Carga histórica desde 01/01/2026 com inventário de edições, suplementos e lacunas.
3. Banco de dados persistente (hoje: JSON).
4. Campos do Eixo 2 — Tempo de Serviço (natureza do tempo, dias) e do Eixo 1 (classe/referência anterior e posterior, PCCR): cobertura atual a medir.
5. Vínculo de retificações e republicações ao ato original.
6. Painel gerencial com as 12 decisões, usuários individuais e trilha de auditoria.
7. Dashboard com todos os filtros combináveis e calendário.
8. Aprendizado controlado a partir das revisões.
9. Automação diária, monitoramento e hospedagem web.
10. Camada de "gerência" na modelagem, para expansão futura.

## 8. Pontos de atenção

- **O repositório oficial é público; os três anteriores são privados** e passaram por uma "blindagem pré-privatização" em 09/11/2026. Antes de migrar código e testes para cá, é preciso decidir a visibilidade e revisar fixtures (por exemplo `tests/fixtures/resenha_540_conferida.json`) quanto a dados pessoais.
- O estado da coleta, os PDFs e os 99 candidatos nunca foram versionados (corretamente) — estão fora do Git, em local que este levantamento não acessou.
- PyMuPDF tem licença AGPL; conferir compatibilidade com o uso pretendido antes da operação continuada.

## 9. Próxima tarefa prioritária

Resolver o executor: comprovar, em uma máquina com rede brasileira, o download de um PDF de cada fonte com verificação de assinatura, tamanho e SHA-256. Só depois iniciar a carga histórica.
