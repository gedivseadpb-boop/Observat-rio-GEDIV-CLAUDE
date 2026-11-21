# 29 — Etapa 2B.2: Correção da Rota Principal, Rotina Diária, Preservação de D1–D6 e Especificação de Privacidade da API Pública

## 1. Escopo executado na Etapa 2B.2

1. **Rota principal `/` e `/index.html` no servidor Python (`observatorio/web/servidor.py`):**
   - Passaram a servir diretamente o frontend definitivo homologado (`observatorio/web/unificado/index.html`, `SHA-256: 3B2DF03954615419FB50A79A2503EEFBE2A61F64CFC8A94970C4530B6F3F6649`), idêntico byte a byte a `/painel`, `/painel/` e `/painel/index.html`, com cabeçalho `Content-Security-Policy` e sem duplicar arquivos HTML.
   - As rotas legadas `/estatico`, `/estatico/` e `/estatico/<arquivo>` e todas as pastas históricas (`observatorio/web/estatico/`, `painel-v2/`, `revisao-2910/` e `painel-publico/`) foram **integralmente preservadas** no repositório para referência das funcionalidades D1–D6 e execução dos testes existentes.

2. **Decisão fundamentada sobre a rotina diária (`deploy_autonomo/rodar_diario.sh`) e `dados.json`:**
   - A inspeção completa do código comprovou que a saída de painel estático (`/tmp/gediv-dist-publica`, antes definida na variável `SAIDA_PUBLICA`) gerada por `scripts/preparar_painel_publico.py` no passo `[5/6]` de `rodar_diario.sh` **não possui nenhum consumidor ativo**:
     - O servidor `observatorio.web` (`gediv-admin.service`) lê `$DADOS_DIR/observatorio.sqlite3` diretamente a cada requisição em `/api/data` e `/api/painel`.
     - `PUBLICAR_PAGES` permanece em `0` e o bloco final de `rodar_diario.sh` encerra sem publicar arquivos externos.
     - A chamada a `scripts/preparar_painel_publico.py` copiava a cada execução diária os 9 arquivos do frontend antigo `painel-publico/` e gerava um `dados.json` não utilizado.
   - **Correção aplicada e endurecida em `deploy_autonomo/rodar_diario.sh` (Etapas 2B.2, 2B.2-bis e Missão Operacional):**
     - **Removida** a variável morta sem uso (`SAIDA_PUBLICA`) após confirmação de zero dependências em todo o repositório, e **exportado** `PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"` para garantir resolução do pacote `observatorio` mesmo sob `PYTHONSAFEPATH=1`.
     - **Preservado e corrigido** o cálculo somente-leitura (`?mode=ro`) de `$DADOS_DIR/cobertura_resumo.json` por meio de `with Banco.somente_leitura(db) as banco_ro:` (`?mode=ro` + `PRAGMA query_only = ON` + encerramento explícito) chamando `indicadores.resumo_cobertura_edicoes(banco_ro)`, que contabiliza também edições com Abono de Permanência em `outra_publicacao` (`adaptador._eh_abono_permanencia`).
     - **Adicionada** nessa mesma sessão somente-leitura a verificação do contrato protegido de `/api/data` (`indicadores.painel(..., proteger_publico=True)` + `adaptador.projetar_para_dashboard_2910`), com gravação **atômica** (`.tmp` + `replace`) de `cobertura_resumo.json` **somente após** todas as asserções de privacidade e contrato passarem.
     - **Adicionado** [`deploy_autonomo/verificar_ambiente_linux.sh`](../deploy_autonomo/verificar_ambiente_linux.sh) para pré-validação somente leitura de `bash -n`, `flock`, `date -d`, `systemd-analyze verify` e importação Python sob `PYTHONSAFEPATH=1` no servidor Linux de destino.
     - **Eliminada** a chamada sem consumidor a `scripts/preparar_painel_publico.py` (sem gerar `dados.json` órfão e sem copiar `painel-publico/`). O script `scripts/preparar_painel_publico.py` e o módulo `observatorio/painel/publicacao.py` permanecem intactos no repositório.

---

## 2. Auditoria de Segurança das Interfaces Legadas (`/estatico/index.html` e `painel-v2/admin-painel/`) e Proposta de Contenção

### 2.1 Riscos técnicos identificados em `/estatico/index.html` e `painel-v2/admin-painel/`
Embora os endpoints de mutação e leitura individual (`/api/revisao`, `/api/ato/*`, `/api/conflitos`, `/api/auditoria`, `/api/exportar`, `/api/pdf/*`) exijam autenticação no servidor, **as interfaces legadas apresentam riscos operacionais e de governança se permanecerem acessíveis como telas paralelas**:

1. **Exposição pública desnecessária em `/estatico/*`:** `/estatico/index.html` e `/estatico/app.js` são entregues sem autenticação de rota (`HTTP 200`), expondo ao público externo os diálogos administrativos `#dlgAcesso` e `#dlgRevisao` e a estrutura interna de campos de correção (`CORRIGIR`, `OMITIDA`, `VINCULAR`).
2. **Incompatibilidade com o modelo de autenticação individual e desabilitação do token legado:**
   - `/estatico/index.html` não possui login por usuário e senha (`POST /api/login`); solicita apenas um segredo único (`#campoToken`). Como o token técnico legado (`GEDIV_TOKEN_GERENCIA`) está **desabilitado por padrão** na CLI de produção (`python -m observatorio.web`), a tela induz o operador a erro ou incentiva a reativação indevida de credencial compartilhada.
   - Se um usuário autenticado no painel unificado tiver um token Bearer válido na mesma aba (`sessionStorage`) ou se o servidor for iniciado com `--habilitar-token-tecnico`, `/estatico/index.html` permitiria executar revisões contornando a interface homologada.
3. **Ausência de alinhamento ao fluxo unificado de cookie `HttpOnly` + proteção anti-CSRF vigente e ao RBAC de 3 perfis (`publico`, `gerencia`, `admin`):**
   - O backend atual (`observatorio/web/servidor.py`, `_cabecalho_cookie_sessao` e `_verificar_csrf_cookie`) emite o cookie `gediv_sessao` com `HttpOnly`, `SameSite=Strict`, `Path=/api`, `Max-Age=28800` (e `Secure` sob `X-Forwarded-Proto: https` ou `GEDIV_COOKIE_SECURE=1`) e atua em modo *fail-closed* para pedidos `POST` autenticados por cookie (rejeitando `cross-site`, `same-site`, `none`, ausência simultânea de cabeçalhos de origem verificáveis e origens fora de `--origem-admin`/`Host`, além de validar origem em `/api/login`). **Não há** cabeçalho customizado nem token sincronizado anti-CSRF implementado no backend ou nos clientes atuais.
   - Nem `estatico/app.js` nem `painel-v2/admin-painel/admin.js` adotam o fluxo unificado por cookie `HttpOnly` (que no cliente unificado ainda convive com `Authorization: Bearer` via `sessionStorage`) nem distinguem na interface os papéis `gerencia` e `admin`.
4. **Visão parcial e desatualizada dos dados em `/estatico/index.html`:**
   - Consome `/api/painel` sem `adaptador.projetar_para_dashboard_2910()`, omitindo os níveis verticais A–F, a separação `PENDENTE:TEC. ADM`/`PENDENTE:STF` e a integração dos registros de Abono de Permanência ao eixo Tempo de Serviço (`ABONO_PERMANENCIA`).

### 2.2 Proposta para impedir o uso das interfaces legadas como sistema operacional paralelo
*(Para execução após aprovação, sem remoção de código nesta etapa)*

1. **Desativar `/estatico/*` por padrão no servidor de produção (`observatorio/web/servidor.py` e `__main__.py`):**
   - Em modo padrão de produção, requisições a `/estatico`, `/estatico/` e `/estatico/index.html` devem retornar redirecionamento `302 Found` para `/painel` (ou `404 Not Found` para `/estatico/app.js`), habilitando o atendimento de `/estatico/*` somente quando acionado explicitamente por flag de teste/compatibilidade (`habilitar_rotas_legadas: bool = False`).
2. **Manter `painel-v2/admin-painel/` desacoplado do servidor Python:**
   - `observatorio/web/servidor.py` já não serve a pasta `painel-v2/`, e `painel-v2/admin-painel/config.json` deve permanecer travado com `"api": ""` (modo desligado), impedindo que seja usado como painel administrativo paralelo.
3. **Migrar D1–D4 para dentro de `observatorio/web/unificado/`:**
   - Concluída a incorporação de D1–D4 ao painel unificado (Seção 4 abaixo) e atualizados os 2 testes legados (`test_painel.py:L282` e `test_privacidade_publica.py:L136`), arquivar definitivamente `observatorio/web/estatico/` e `painel-v2/admin-painel/`.

### 2.3 Correção aplicada ao cálculo de `ausencia_tecnica_edicoes` (Prioridade 2)
- Substituída a query isolada do passo `[5/6]` de `rodar_diario.sh` por `indicadores.resumo_cobertura_edicoes(banco_ro)` (`observatorio/painel/indicadores.py`), que considera como cobertura ativa tanto os atos GEDIV (`PROGRESSAO`/`TEMPO_SERVICO`) quanto as edições que possuem registros reconhecidos de Abono de Permanência em `outra_publicacao` (`adaptador._eh_abono_permanencia`, excluindo distratores como Abono Natalino).

---

## 3. Endurecimento Implementado na API Pública, CSRF e Auditoria (Prioridade 1 — Missão Operacional)

### 3.1 Controles implementados no backend (`observatorio/painel/indicadores.py`, `adaptador.py`, `servidor.py`)
1. **`GET /api/outras` protegido por `_exigir_gerencia()`:** retorna HTTP `401` sem credencial e `403` para token inválido, removendo a exposição de triagens não revisadas (`outra_publicacao`).
2. **`GET /api/painel` e `GET /api/data` com proteção pública (`proteger_publico=True`):** para `perfil != GERENCIA_PERFIL`, os filtros dinâmicos combináveis são ignorados, `resenhas[]`, `eventos[]` e contadores internos de fila (`apoio`, `meta.{pendentes,rejeitados,eventosPendentes}`, `dashboard.counts.unlinkedEvents`) são zerados/ocultados, `por_data` passa a granularidade mensal (`YYYY-MM`) e todas as contagens usam `LIMIAR_PUBLICO = 5` (decisões e matrículas distintas) em faixas de largura 5 com supressão complementar e secundária; `rev_hash` público é desacoplado de contadores internos.
3. **CSRF e sessão:** `_verificar_origem_post()` opera em modo *fail-closed* em `_verificar_csrf_cookie()` e valida `Origin`/`Sec-Fetch-Site` em `POST /api/login` (preservando origens autorizadas em `--origem-admin`).
4. **RBAC em `GET /api/auditoria` e não-repúdio do token técnico legado:** `admin` consulta `escopo: "global"`, `gerencia` nominal consulta apenas `escopo: "proprio"` (filtrando ações administrativas/legadas), e o token técnico legado recebe `403` em `/api/auditoria` e grava prefixo `credencial_tecnica_legada: <responsável>` em `POST /api/revisao`.
5. **Testes automatizados adicionados:** `tests/test_seguranca_privacidade_api.py` (anti-inferência, polling, CSRF, RBAC `/api/auditoria` e fluxos D1–D4 ponta a ponta no backend).

### 3.2 Pendências ainda dependentes de autorização específica para alterar o HTML homologado
- Substituição definitiva de `Authorization: Bearer` em `sessionStorage` e integração visual de D2–D4 em `observatorio/web/unificado/index.html` permanecem aguardando autorização expressa para editar o HTML homologado.
- Desativação opcional de `/estatico/*` em produção e proteção/despublicação de `gh-pages` seguem registradas como decisões externas da proprietária.

---

## 4. Plano de Integração de D1–D4 e Conferência Documental de PDFs

| Código | Funcionalidade | Origem preservada | Requisitos para futura integração em `observatorio/web/unificado/` | Ordem proposta |
|---|---|---|---|---|
| **D1** | **Correção de campos individuais (`CORRIGIR` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`corrigirDecisao`, `revisarAto`) e `observatorio/web/estatico/app.js` (`camposDecisao`, `camposAto`, `lerCampos`) | Integrar ao modal de revisão documental de `observatorio/web/unificado/index.html` (perfis `gerencia` e `admin`), exibindo o PDF oficial (`/api/pdf/<sha256>#page=<n>`) lado a lado com formulário em seções expansíveis (Progressão Vertical A–F, Progressão Horizontal, Tempo de Serviço TS-01..TS-07, Abono de Permanência sem TS-08 e Outros benefícios), `confirma_fonte` obrigatório, justificativa e autoria da sessão (`self._conta()`). | **1.ª (com Conferência de PDFs)** |
| **D2** | **Fila e resolução de conflitos (`GET /api/conflitos` e `alvo: "conflito"` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`telaConflitos`, `resolver`) e `observatorio/revisao/servico.py` (`resolver_conflito`) | Adicionar visão/modal gerencial alimentado por `GET /api/conflitos` listando conflitos abertos entre revisores, vínculos órfãos e classificações desatualizadas (`VERSAO_REGRAS`), permitindo acionar `POST /api/revisao` (`alvo: "conflito"`). | **2.ª** |
| **D3** | **Consulta visual à trilha de auditoria (`GET /api/auditoria` e `GET /api/ato/<id>`)** | `painel-v2/admin-painel/admin.js` (`telaHistorico`, `telaAto`) e `observatorio/web/estatico/app.js` (`detalhes`) | Carregar `GET /api/ato/<id>` no detalhe de ato/processo para exibir `correcoes`, `conflitos` e `trilha`, e adicionar consulta global a `GET /api/auditoria` (últimos 300 eventos). | **3.ª** |
| **D4** | **Exportação gerencial auditada (`GET /api/exportar?formato=xlsx\|csv`) e relatórios PDF/Excel organizados** | `observatorio/web/servidor.py` (`/api/exportar`), `observatorio/painel/exportacao.py`, `painel-v2/admin-painel/admin.js`, `painel-publico/xlsx.js` e `pdf.js` | Integrar o botão `Exportar visualização` do painel unificado a `/api/exportar` quando autenticado (`gerencia`/`admin`) para gravar `acao = "EXPORTAR"` na tabela `auditoria`, evoluindo a organização dos relatórios Excel e PDF conforme o perfil RBAC. | **4.ª** |
