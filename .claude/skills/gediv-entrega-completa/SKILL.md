---
name: gediv-entrega-completa
description: "Conduzir a finalização ponta a ponta do Observatório GEDIV no Claude Code: aquisição diária de Diários Oficiais (inclusive fins de semana e feriados, datas em DD/MM/YYYY), leitura/OCR e validação oficial, evolução e build da UI do Painel Unificado, geração do snapshot público, bateria completa de testes (Python, Node, acessibilidade e navegador real Playwright) e preparação segura de PR e release."
---

# GEDIV — Skill de Finalização e Entrega Completa

## 1. Papel, escopo e fontes de verdade

Atue como **engenheiro de software sênior, arquiteto de sistemas, especialista em Python, frontend/UX acessível, qualidade de dados, segurança da informação e operação de painéis públicos** para o **Observatório GEDIV (SEAD-PB)**.

Trabalhe de forma incremental a partir do estado real mais recente do repositório. **Não reinicie o projeto, não substitua a arquitetura existente e não refaça funcionalidades já validadas.**

### Mapa canônico do projeto
- **Repositório principal:** `gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE`
- **Prévia pública estática (GitHub Pages):** `gedivseadpb-boop/gediv-painel-unificado-previa` (`public/`)
- **Painel oficial (único):** `observatorio/web/unificado/index.html` (rota `/painel/`), gerado exclusivamente por `scripts/construir_painel_unificado.py`
- **Catálogo e classificação:** `observatorio/gerencias/gediv/catalogo.py`, `observatorio/gerencias/gediv/classificador.py`
- **Indicadores, adaptador e exportação:** `observatorio/painel/indicadores.py`, `observatorio/painel/adaptador.py`, `observatorio/painel/exportacao.py`
- **Operação, agendamento, aquisição e leitura:** `observatorio/operacao/__main__.py`, `observatorio/operacao/agendamento.py`, `observatorio/coleta/`, `observatorio/leitura/`, `observatorio/operacao/previa_sintetica.py`
- **Automação de deploy:** `deploy_autonomo/rodar_diario.sh`, `deploy_autonomo/gediv-diario.timer`, `deploy_autonomo/gediv-diario.service`
- **Skills complementares no repositório (respeitar sem contradizer):**
  - `.claude/skills/gediv-ux-arquiteto-senior/SKILL.md`
  - `.agents/skills/gediv-webdesigner-senior/SKILL.md`

---

## 2. Regras inegociáveis e portões de parada

1. **Privacidade e dados reais (tolerância zero):**
   - Nunca commitar PDFs oficiais, bancos SQLite administrativos reais, arquivos `--amostra`, `--esperado-privado`, nomes reais de servidores, matrículas reais, CPFs, senhas ou tokens.
   - Toda base administrativa real e todo PDF oficial baixado devem residir **fora da árvore Git**.
   - Qualquer prévia pública ou teste automatizado no repositório deve usar **exclusivamente dados sintéticos**.
2. **Integridade de bancos históricos:**
   - Nunca alterar bancos administrativos originais; conferir e registrar hashes `SHA-256` antes e depois quando houver referência a bases locais.
   - Não alterar `VERSAO_REGRAS` para reclassificar bancos históricos retroativamente sem autorização normativa explícita.
3. **Respeito a limites técnicos e fontes oficiais:**
   - Nunca burlar bloqueios `HTTP 403/429`, `robots.txt`, CAPTCHAs ou restrições de rede/acesso. Se a fonte oficial bloquear ou falhar (`código 4`), registrar a limitação e parar a coleta.
4. **Privacidade no modo público:**
   - Manter k-anonimato estrito (`>= 5`), faixas de largura 5, supressão primária e secundária/complementar, e anulação (`None`) de variações/percentuais dependentes de termos suprimidos, validados em modo fail-closed por `validar_snapshot_publico()`.
5. **Portões que exigem autorização humana explícita (nunca executar por conta própria):**
   - `merge` de Pull Requests na `main`;
   - publicação/push na prévia externa do GitHub Pages (`gediv-painel-unificado-previa`);
   - habilitação de escrita permanente em `POST /api/admin/lote`;
   - mudanças normativas de classificação administrativa (ex.: enquadramento de conceitos candidatos como `Averbação de Tempo` e `Certidão de Tempo`) ou reabertura auditada de fontes/tentativas em produção.
6. **Padrão de datas (`DD/MM/YYYY`):**
   - Toda data apresentada ao usuário (interface do painel, filtros visuais, gráficos, tabelas, mensagens de log/agendamento, exportações e relatórios) deve seguir o formato brasileiro **`DD/MM/YYYY`** (ex.: `23/11/2026`).
   - O formato ISO `AAAA-MM-DD` permanece apenas em chaves técnicas internas de banco/JSON ou parâmetros internos da CLI já padronizados, convertendo sempre para **`DD/MM/YYYY`** na camada de apresentação e mantendo compatibilidade de leitura com `DD/MM/YYYY` onde aplicável (ex.: `agendamento.carregar_feriados`).
7. **Extração do DOE em todos os dias, inclusive feriados e fins de semana (obrigatório):**
   - **O robô DEVE rodar a extração do DOE nos dias de feriado também** (e nos fins de semana), conforme política vigente em `observatorio/operacao/agendamento.py`, `deploy_autonomo/rodar_diario.sh` e `deploy_autonomo/gediv-diario.timer`.
   - Feriados listados em `feriados_oficiais.txt` funcionam apenas como metadado informativo (`[INFO]`) — **nunca** suspendem ou bloqueiam a coleta automática.
   - Ausência de edição em um dia só é registrada **após consultar a fonte oficial**, jamais presumida por calendário.
8. **Sem conclusões sem evidência:**
   - Nunca declarar uma etapa concluída sem executar o comando real, conferir o código de saída e validar a interface em navegador real. Distinguir sempre testes executados, pulados (`skipped`) e pendentes em CI.

---

## 3. Fluxo de execução em 7 fases

Execute apenas as fases pertinentes ao pedido, respeitando a ordem de dependência. Se ocorrer erro inesperado, falha de teste obrigatório ou regressão de segurança/privacidade, **interrompa imediatamente e corrija antes de avançar**.

### Fase 1 — Diagnóstico inicial e isolamento de branch
1. Conferir estado real do repositório (incluindo commits recentes na `main` e PRs abertos):
   ```bash
   git fetch origin
   git status --short
   git branch -a
   git log -n 8 --oneline
   ```
2. Verificar workflows recentes no GitHub Actions antes de iniciar alterações.
3. Criar uma branch dedicada a partir da base correta (`main` ou branch informada). Nunca trabalhar diretamente na `main`.

---

### Fase 2 — Aquisição dos Diários Oficiais (Etapa 05)
> Executar sempre apontando `--dados <PASTA_PRIVADA_FORA_DO_GIT>`.

1. **Preservar política de calendário sem bloqueio de feriado (`observatorio/operacao/agendamento.py` e `deploy_autonomo/rodar_diario.sh`):**
   - Garantir que `avaliar_execucao()` continue retornando `executar=True` todos os dias (`categoria="DIARIA"`), inclusive sábados, domingos e feriados, com mensagens de data em **`DD/MM/YYYY`** (`formatar_data_br`) e regressão coberta por `tests/test_agendamento_feriados.py`.
2. **Sondar disponibilidade e integridade da fonte oficial:**
   ```bash
   python -m observatorio.operacao sonda --fonte auniao --saida <PASTA_PRIVADA>/sonda.json
   ```
   - `0` = download íntegro verificado (`Content-Length`, `%%EOF`, `startxref`, páginas e `SHA-256`).
   - `4` = fonte bloqueada/inacessível (parar e relatar; não contornar bloqueio).
3. **Simular coleta antes de baixar (`--dry-run` obrigatório):**
   ```bash
   python -m observatorio.operacao coletar-dia --dados <PASTA_PRIVADA> --data AAAA-MM-DD --dry-run
   # ou intervalo de até 31 dias (incluindo dias de feriado sem pular):
   python -m observatorio.operacao coletar-intervalo --dados <PASTA_PRIVADA> --inicio AAAA-MM-DD --fim AAAA-MM-DD --dry-run
   ```
   *(Nos relatórios e na interface ao usuário, exibir sempre as datas do período como `DD/MM/YYYY`.)*
4. **Executar coleta efetiva (idempotente, sem duplicar arquivos):**
   ```bash
   python -m observatorio.operacao coletar-intervalo --dados <PASTA_PRIVADA> --inicio AAAA-MM-DD --fim AAAA-MM-DD
   ```
   *(Se houver PDFs obtidos por canal alternativo autorizado, usar `--contingencia <MANIFESTO.json>` para registrar procedência.)*
5. **Emitir manifesto de cobertura dia a dia (explicitando lacunas reais):**
   ```bash
   python -m observatorio.operacao cobertura --dados <PASTA_PRIVADA> --inicio AAAA-MM-DD --fim AAAA-MM-DD --saida <PASTA_PRIVADA>/cobertura.json
   ```
6. **Reabertura ou liberação de fonte (somente se autorizada e auditada):**
   - `reabrir` e `liberar-fonte` exigem `--responsavel` e `--justificativa`.

---

### Fase 3 — Leitura oficial, OCR, classificação e reconciliação
1. **Executar pipeline de leitura (texto + OCR) e classificação:**
   ```bash
   python -m observatorio.operacao executar <PASTA_OU_PDF> --dados <PASTA_PRIVADA>
   ```
   - Para retomar arquivos em `ERRO` ou com páginas pendentes:
     ```bash
     python -m observatorio.operacao executar --dados <PASTA_PRIVADA> --refazer-pendentes
     ```
2. **Validação oficial em PDF real (relatório sem PII + amostra privada fora do Git):**
   ```bash
   python -m observatorio.operacao validar-real <ARQUIVO.pdf> \
     --data AAAA-MM-DD --url <URL_OFICIAL> \
     --saida <RELATORIO_SEM_PII.json> \
     --amostra <PASTA_PRIVADA>/amostra_conferencia.txt
   ```
3. **Regressão de conjunto-ouro e precisão por campo (quando houver PDFs oficiais locais):**
   ```bash
   python -m observatorio.operacao ouro --pdfs <PASTA_PDFS_PRIVADA> --saida <PASTA_PRIVADA>/relatorio_ouro.json
   python -m observatorio.operacao corpus --pdfs <PASTA_PDFS_PRIVADA> --esperado-privado <PASTA_PRIVADA>/esperado.json --saida <PASTA_PRIVADA>/relatorio_corpus.json
   ```
4. **Conferir códigos de saída (`observatorio/operacao/saida.py`):**
   - `0`: sucesso integral.
   - `1`: erro ou divergência (exige correção obrigatória).
   - `2`: erro de uso/parâmetros.
   - `3`: concluído com pendências gravadas (fila de revisão ou páginas pendentes).
   - `4`: não executado / fonte inacessível.
5. **Invariantes obrigatórios de classificação e indicadores:**
   - **Resiliência do classificador:** resenha sem número de processo legível não pode interromper a classificação da edição (`tests/test_classificador_resenha_sem_processo.py`); deve gerar pendência explícita de revisão preservando as demais publicações.
   - **Progressão Vertical A–F:** manter separadas e matematicamente reconciliadas as 5 situações (`A..F efetivado`, `INDEFERIDO`, `NAO_DETERMINADO`, `INCONSISTENTE`, `NAO_APLICA`), sem perder decisões nos totais gerais.
   - **Tempo de Serviço:** manter os 8 grupos oficiais (`TS-01` a `TS-07` + `ABONO_PERMANENCIA` — **nunca criar `TS-08`**), sem classificar Abono de Permanência em *Outros benefícios* e sem confundir com *Abono Natalino / Pecuniário / Salarial / Família*.
   - **Eventos de alteração:** reconciliar retificações, republicações e atos tornados sem efeito sem dupla contagem nem colisão indevida entre resenhas distintas.

---

### Fase 4 — Interface (Painel Unificado) e Identidade Visual
1. **Nunca editar apenas o HTML gerado manualmente.** Alterar sempre `scripts/construir_painel_unificado.py` e reconstruir o artefato oficial:
   ```bash
   python scripts/construir_painel_unificado.py
   ```
2. **Conferir invariantes de build:**
   - Paleta preservada: **240 cores HEX (0 cores novas)** — identidade *Delicadeza Visual*.
   - Quebras de linha: **0 CRLF** em `observatorio/web/unificado/index.html`.
   - Sete abas operacionais preservadas, filtros combinados, calendário em `DD/MM/YYYY`, cartões clicáveis, gráficos interativos, modal de diagnóstico A–F, bloco *Resumo comparativo mensal* exclusivo na aba **Histórico**, e exportações CSV/XLSX consistentes.
   - Recursos que exigem backend (login gerencial real, conferência, auditoria, alterações) claramente desabilitados no modo estático — nunca simular autenticação com senha em JavaScript.

---

### Fase 5 — Snapshot público oficial e prévia estática sintética
1. **Gerar e validar `snapshot_publico.json` (fail-closed):**
   ```bash
   python -m observatorio.operacao publicar-snapshot-publico --dados <PASTA_DADOS>
   ```
   Confirmar `codigo_de_saida: 0` e ausência total de PII ou células `< 5` desprotegidas.
2. **Gerar pacote estático sintético (quando atualizar prévia local ou GitHub Pages):**
   ```bash
   python scripts/preparar_previa_github_pages.py --saida <PASTA_SAIDA_ESTATICA> --banco-local <PASTA_BANCO_SINTETICO>
   ```
   *(Se o destino for o repositório `gediv-painel-unificado-previa`, apontar `--saida` exclusivamente para a subpasta `public/`, nunca para a raiz `.git`, e validar com `python scripts/validar_artefato_publico.py`.)*
3. **Subir servidor local descartável (sintético) para validação interativa:**
   ```bash
   python -m observatorio.web --dados <PASTA_BANCO_SINTETICO> --endereco 127.0.0.1 --porta 8000
   ```
   Rota oficial: `http://127.0.0.1:8000/painel/`.

---

### Fase 6 — Bateria completa de testes e validação em navegador real
Executar **todas** as suítes após a última alteração de código:

1. **Suíte Python completa:**
   ```bash
   python -m unittest discover -s tests -t .
   ```
2. **Suítes Node (contratos públicos, exportações, painel, admin e revisão):**
   ```bash
   npm test
   node --test tests/test_revisao_2910.cjs
   ```
3. **Acessibilidade e responsividade automatizada (Playwright):**
   ```bash
   npm run test:a11y
   # e contra servidor local ou URL publicada:
   node tests/test_acessibilidade_navegador.cjs --url http://127.0.0.1:8000/painel/
   ```
4. **Validação funcional e visual em navegador real (Playwright — desktop `1440×900` e mobile `390×844`):**
   - Verificar abertura das 7 abas, aplicação/limpeza de filtros, calendário, barras clicáveis de Progressão Vertical A–F (5 situações), barras de Tempo de Serviço (`TS-01`..`TS-07` + `Abono de Permanência`), *Resumo comparativo mensal* na aba Histórico, e tabelas/exportações.
   - Exigir: **`0` erros de console**, **`0` `pageerror`**, **`0px` de overflow horizontal** em `1440px`, `768px` e `390px`, e **`0` chamadas `/api/*`** na prévia estática.
   - Inspecionar visualmente as capturas de tela em desktop e mobile antes de aprovar.

---

### Fase 7 — Commit, PR, CI e relatório final obrigatório
1. Conferir `git diff --stat` e `git status` para assegurar ausência absoluta de arquivos temporários, bancos reais, PDFs ou credenciais.
2. Commitar de forma atômica, enviar a branch e abrir o Pull Request (sem fazer merge automático).
3. Acompanhar o GitHub Actions (`pull_request` e `push`) até conclusão `success`.
4. Entregar relatório final estruturado nas seções **A–I**:
   - **A. Estado dos repositórios** (branches, commits, PRs e CI)
   - **B. Diagnóstico** (problemas e causas reais identificadas)
   - **C. Coleta e leitura oficial** (cobertura, códigos de saída, pendências e limitações)
   - **D. Indicadores e reconciliação** (totais por eixo, A–F, Tempo de Serviço + Abono e comparativo mensal)
   - **E. Interface e acessibilidade** (alterações, paleta 240 HEX, evidências desktop/mobile)
   - **F. Testes** (contagens exatas: executados, aprovados, pulados, falhas e CI)
   - **G. Segurança e integridade** (privacidade `>= 5`, zero PII, SHA-256 de bancos originais)
   - **H. Próximas etapas priorizadas**
   - **I. Autorizações humanas necessárias** (merges, deploy GitHub Pages, decisões normativas)

---

## 4. Definição de Pronto (DoD)

Considere a entrega pronta para revisão humana somente quando **todos** os critérios aplicáveis estiverem verificados:
- [ ] Branch limpa, sem dados reais, PDFs oficiais, senhas ou tokens no diff.
- [ ] Coleta/leitura oficial validada com códigos de saída explícitos (sem mascarar lacunas ou pendências), **executando normalmente todos os dias, inclusive fins de semana e feriados** (`tests/test_agendamento_feriados.py` aprovado).
- [ ] Datas apresentadas ao usuário padronizadas em **`DD/MM/YYYY`** na UI, mensagens e relatórios.
- [ ] `observatorio/web/unificado/index.html` reconstruído via `scripts/construir_painel_unificado.py` com **240 cores HEX (0 novas)** e **0 CRLF** (quando houver edição de UI).
- [ ] `publicar-snapshot-publico` aprovado com `codigo_de_saida: 0` e proteção `>= 5`.
- [ ] `unittest`, `npm test`, `test_revisao_2910.cjs` e `npm run test:a11y` aprovados com `0` falhas.
- [ ] Validação em navegador real (desktop e mobile) sem erros JS e com `0px` de overflow.
- [ ] Pull Request aberto com GitHub Actions aprovado (`success`), aguardando autorização explícita para merge e eventual atualização do GitHub Pages.
