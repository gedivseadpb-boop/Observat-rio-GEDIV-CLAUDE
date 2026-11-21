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
   - **Correção aplicada e endurecida em `deploy_autonomo/rodar_diario.sh` (Etapas 2B.2 e 2B.2-bis):**
     - **Removida** a variável morta sem uso (`SAIDA_PUBLICA`) após confirmação de zero dependências em todo o repositório, e **exportado** `PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"` para garantir resolução do pacote `observatorio` mesmo sob `PYTHONSAFEPATH=1`.
     - **Preservado** integralmente o cálculo somente-leitura (`?mode=ro`) de `$DADOS_DIR/cobertura_resumo.json` (`ausencia_tecnica_edicoes` e `inconclusivas`), passando a abrir o SQLite por meio de `with Banco.somente_leitura(db) as banco_ro:` (`?mode=ro` + `PRAGMA query_only = ON` + encerramento explícito da conexão ao sair do contexto, eliminando `object.__new__(Banco)`).
     - **Adicionada** nessa mesma sessão somente-leitura a verificação do contrato de `/api/data` (`indicadores.painel` + `adaptador.projetar_para_dashboard_2910`), com gravação **atômica** (`.tmp` + `replace`) de `cobertura_resumo.json` **somente após** todas as asserções de privacidade e contrato passarem.
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
   - O backend atual (`observatorio/web/servidor.py`, `_cabecalho_cookie_sessao` e `_verificar_csrf_cookie`) emite o cookie `gediv_sessao` com `HttpOnly`, `SameSite=Strict`, `Path=/api`, `Max-Age=28800` (e `Secure` sob `X-Forwarded-Proto: https` ou `GEDIV_COOKIE_SECURE=1`) e, em pedidos `POST` autenticados por cookie (exceto `/api/login`), rejeita `Sec-Fetch-Site: cross-site` e `Origin` inválido/não autorizado (`--origem-admin` ou `Host`). **Não há** cabeçalho customizado nem token sincronizado anti-CSRF implementado no backend ou nos clientes atuais.
   - Nem `estatico/app.js` nem `painel-v2/admin-painel/admin.js` adotam o fluxo unificado por cookie `HttpOnly` (que convive com `Authorization: Bearer` via `sessionStorage`) nem distinguem na interface os papéis `gerencia` e `admin`.
   - *(Fragilidade do CSRF atual registrada para auditoria de segurança separada: `_verificar_csrf_cookie()` falha-aberta caso `Sec-Fetch-Site` e `Origin` estejam ambos ausentes, não bloqueia `Sec-Fetch-Site: same-site` sem `Origin`, `/api/login` executa antes dessa checagem e `sessionStorage` permanece sensível a eventual XSS.)*
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

### 2.3 Observação registrada sobre o cálculo de `ausencia_tecnica_edicoes` (sem alteração de regra nesta etapa)
- A auditoria independente identificou que, no passo `[5/6]` de `rodar_diario.sh`, a consulta de `ausencia_tecnica_edicoes` verifica apenas `NOT EXISTS (SELECT 1 FROM ato a WHERE a.sha256 = l.sha256 AND a.gerencia = 'GEDIV' AND a.eixo IN ('PROGRESSAO', 'TEMPO_SERVICO'))`, sem considerar `outra_publicacao` (onde hoje ingressam registros de Abono de Permanência) nem vigência da `classificacao`.
- Assim, uma edição do DOE que contenha **exclusivamente** publicação de Abono de Permanência em `outra_publicacao` é contabilizada em `ausencia_tecnica_edicoes`. Conforme delimitação de escopo da Etapa 2B.2-bis, **nenhuma regra de cobertura foi alterada agora**; eventual ajuste de definição (considerar ou separar edições com Abono em `outra_publicacao`) depende de autorização específica.

---

## 3. Bloqueios de Implantação e Tarefa Separada (Prioridade Crítica) — Privacidade da API Pública, CSRF e Governança de Auditoria

*(Especificação técnica e bloqueios de implantação pública registrados — nenhuma alteração nos endpoints da API foi realizada nesta etapa.)*

### 3.1 Bloqueios de implantação identificados na auditoria cruzada (não corrigidos nesta etapa)
1. **`GET /api/outras` sem autenticação:** retorna `HTTP 200` para `publico` com itens de triagem não revisados de `outra_publicacao` (incluindo `id`, `data`, `pagina`, `titulo` potencialmente com nome de servidor e benefício, e `url_oficial#page=N`), contradizendo o contrato público e `GET /api/data` (que devolve lista vazia ao público).
2. **Pequenas contagens exatas (`n=1..4`) e inventário ato-a-ato em `GET /api/painel` e `GET /api/data`:** sem login, entregam inteiros exatos em `indicadores`, 9 `series` granulares (diária, grupo, nível, subcategoria) e o vetor `resenhas[]` com `decisoes`/`deferido`/`indeferido`, `url_oficial#page=N` direto para o PDF oficial e `pdf_sha256` interno (`documental.CAMPOS` + `projecao.py`).
3. **Inferência por filtros combinados, subtração e consultas temporais:** o público pode combinar livremente `inicio`/`fim` diários, `grupo=A,B` multivalorado, `nivel`, `resultado` e `cartao`, permitindo singularização (`n=1`), subtração complementar (`Total - deferidos`) e monitoramento temporal por polling em banco vivo a cada confirmação.
4. **Divulgação de dados de triagem e metadados internos de fila:** `apoio` (`decisoes_pendentes`, `decisoes_rejeitadas`, `eventos_sem_vinculo`, `conflitos_abertos`, `vinculo_nao_expresso_pendente`), `meta.{pendentes,rejeitados,eventosPendentes}` e `dashboard.counts.unlinkedEvents` vazam sem autenticação, além de metadados operacionais em `GET /api/saude`.
5. **Controles efetivos de CSRF e `sessionStorage`:** necessário endurecer `_verificar_csrf_cookie()` (evitar falha-aberta sem `Sec-Fetch-Site`/`Origin`, avaliar token sincronizado ou restrição estrita a métodos com cookie sem `Authorization: Bearer` em `sessionStorage`) e revisar o fluxo de `/api/login`.
6. **Permissões de `GET /api/auditoria` e não-repúdio do token técnico legado:** `GET /api/auditoria` exige apenas `_exigir_gerencia()` em vez de `_exigir_admin()` (expondo eventos globais, inclusive logins de `admin`, `RECEBER_LOTE_ADMIN` e `USO_TOKEN_TECNICO_LEGADO`), e `POST /api/revisao` com token técnico legado habilitado aceita string arbitrária em `responsavel`.

### 3.2 Avaliação detalhada das respostas públicas atuais (`perfil == PUBLICO`)

| Endpoint público | O que retorna hoje para visitante sem login (`perfil == PUBLICO`) | Avaliação de risco quando houver decisões `CONFERIDO` |
|---|---|---|
| `GET /api/catalogo` | Dicionário fixo de eixos, modalidades, 16 grupos PCCR, subcategorias `TS-01`..`TS-07`, tipos de eventos e outras publicações | **SEGURO:** metadados normativos estáticos, sem contagens da base. |
| `GET /api/saude` | `versao`, `regras`, `perfil: "publico"`, `papel: "publico"` e `cobertura` (`edicoes_no_acervo`, `edicoes_lidas`, `edicoes_classificadas`, `paginas_lidas`, `primeira_data`, `ultima_data`, `ultima_atualizacao`, etc.) | **BAIXO RISCO:** contagens globais e timestamps operacionais de cobertura, sem recorte por servidor, mérito ou grupo. |
| `GET /api/outras` | Lista completa de `outra_publicacao` (`id`, `tipo`, `nome_tipo`, `data`, `pagina`, `titulo`, `vinculo`, `situacao`, `url_oficial`), ocultando apenas `trecho` e `pdf_no_acervo` (`projecao.py`) | **ALTO RISCO:** entrega itens individuais de triagem (`situacao = "triagem, a conferir"`, incluindo atos de Abono de Permanência em `outra_publicacao`) com `titulo` e ponteiro de página oficial. |
| `GET /api/painel` | Força `escopo = "conferido"`, `busca = None` e `linhas = []`, mas aceita **qualquer combinação de filtros** (`inicio`, `fim`, `eixo`, `modalidade`, `condicao`, `grupo`, `nivel`, `subcategoria`, `resultado`, `vinculo`, `cartao`) e retorna **inteiros exatos** em `indicadores`, `apoio` (fila interna não homologada), 9 `series`, `resenhas[]` (com `deferido`/`indeferido`, `url_oficial#page=N` e `pdf_sha256`) e `eventos` validados | **RISCO CRÍTICO DE INFERÊNCIA e VAZAMENTO:**<br>1. **Célula pequena direta:** filtros combinados isolam `decisoes = 1` + `url_oficial#page=N`.<br>2. **Subtração e complemento:** janelas diárias `T(1..30) - T(1..29)`, `grupo=A,B - grupo=A` e `Total - deferidos`.<br>3. **Fila interna e polling temporal:** `apoio.decisoes_pendentes` e atualizações imediatas permitem reconstruir decisões conferidas uma a uma. |
| `GET /api/data` | Chama `indicadores.painel(banco, {**consulta, "escopo": "conferido"}, PUBLICO)` e `adaptador.projetar_para_dashboard_2910(p_resp, [], [])`. Entrega `rows: []`, mas repassa integralmente `backend.indicadores`, `backend.apoio`, `backend.series`, `backend.resenhas`, `meta.{pendentes,rejeitados,eventosPendentes}` e `dashboard.counts.unlinkedEvents` | **RISCO CRÍTICO DE INFERÊNCIA:** herda os mesmos vetores de `/api/painel` e vaza contadores internos de fila e eventos não vinculados. |

### 3.3 Requisitos obrigatórios de correção para a próxima etapa independente (preservando 100% do acesso para `gerencia` e `admin`)

1. **Contenção imediata de exposição direta:** exigir `_exigir_gerencia()` em `GET /api/outras` (`401` para `publico`); zerar/remover `resenhas[]`, `pdf_sha256`, `apoio`, `meta.{pendentes,rejeitados,eventosPendentes}` e `dashboard.counts.unlinkedEvents` no perfil `PUBLICO`; restringir `GET /api/auditoria` a `_exigir_admin()` (ou ao próprio usuário) e endurecer autoria quando o token técnico legado estiver ativo.
2. **Desacoplamento e fechamento de inferência dinâmica para `PUBLICO`:** servir o perfil público apenas com base em **snapshots periódicos congelados em lote** (eliminando polling temporal), bloquear/normalizar filtros diários (`inicio`/`fim` restritos a competência mensal fechada `YYYY-MM`), desabilitar filtros combinados/multivalorados (`grupo=A,B`), `nivel`, `resultado` e `cartao` livres, e aplicar **faixas de largura 5 com `LIMIAR = 5` em decisões E matrículas distintas + supressão secundária (complementar)** (unificando `0` com `1..4` quando a existência `>= 1` for sensível).
3. **Endurecimento de CSRF e sessão:** corrigir falha-aberta em `_verificar_csrf_cookie()` e evoluir para token sincronizado/origem estrita, reduzindo a dependência de `Authorization: Bearer` em `sessionStorage`.
4. **Separação estrita entre `PUBLICO` e `GERENCIA_PERFIL`:** `gerencia` e `admin` autenticados continuam recebendo 100% dos inteiros exatos, filtros diários, `linhas`, `resenhas`, `eventos`, `apoio` e `outras_publicacoes`.

### 3.4 Testes e critérios de aceite obrigatórios para a futura etapa de segurança e privacidade
1. **Teste de `/api/outras`, `resenhas[]`, `apoio` e `GET /api/auditoria`:** comprovar `401` em `/api/outras` sem login, ausência de `resenhas`, `pdf_sha256`, `url_oficial#page=`, `decisoes_pendentes`, `unlinkedEvents` para `PUBLICO`, e `403` de `gerencia` em `GET /api/auditoria`.
2. **Teste de célula pequena e ataque por subtração/filtros combinados:** comprovar que `PUBLICO` não recebe inteiros `1..4` em nenhum agregado, que `T(d1..d2) - T(d1..d2-1)`, `grupo=A,B - grupo=A` e `Total - deferidos` não permitem reconstruir registros unitários nem evolução por confirmação unitária.
3. **Teste de não-regressão gerencial:** comprovar que `gerencia` e `admin` autenticados continuam recebendo contagens exatas, séries completas e linhas individuais em todas as abas e gráficos.

---

## 4. Plano de Integração de D1–D4 e Conferência Documental de PDFs

| Código | Funcionalidade | Origem preservada | Requisitos para futura integração em `observatorio/web/unificado/` | Ordem proposta |
|---|---|---|---|---|
| **D1** | **Correção de campos individuais (`CORRIGIR` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`corrigirDecisao`, `revisarAto`) e `observatorio/web/estatico/app.js` (`camposDecisao`, `camposAto`, `lerCampos`) | Integrar ao modal de revisão documental de `observatorio/web/unificado/index.html` (perfis `gerencia` e `admin`), exibindo o PDF oficial (`/api/pdf/<sha256>#page=<n>`) lado a lado com formulário em seções expansíveis (Progressão Vertical A–F, Progressão Horizontal, Tempo de Serviço TS-01..TS-07, Abono de Permanência sem TS-08 e Outros benefícios), `confirma_fonte` obrigatório, justificativa e autoria da sessão (`self._conta()`). | **1.ª (com Conferência de PDFs)** |
| **D2** | **Fila e resolução de conflitos (`GET /api/conflitos` e `alvo: "conflito"` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`telaConflitos`, `resolver`) e `observatorio/revisao/servico.py` (`resolver_conflito`) | Adicionar visão/modal gerencial alimentado por `GET /api/conflitos` listando conflitos abertos entre revisores, vínculos órfãos e classificações desatualizadas (`VERSAO_REGRAS`), permitindo acionar `POST /api/revisao` (`alvo: "conflito"`). | **2.ª** |
| **D3** | **Consulta visual à trilha de auditoria (`GET /api/auditoria` e `GET /api/ato/<id>`)** | `painel-v2/admin-painel/admin.js` (`telaHistorico`, `telaAto`) e `observatorio/web/estatico/app.js` (`detalhes`) | Carregar `GET /api/ato/<id>` no detalhe de ato/processo para exibir `correcoes`, `conflitos` e `trilha`, e adicionar consulta global a `GET /api/auditoria` (últimos 300 eventos). | **3.ª** |
| **D4** | **Exportação gerencial auditada (`GET /api/exportar?formato=xlsx\|csv`) e relatórios PDF/Excel organizados** | `observatorio/web/servidor.py` (`/api/exportar`), `observatorio/painel/exportacao.py`, `painel-v2/admin-painel/admin.js`, `painel-publico/xlsx.js` e `pdf.js` | Integrar o botão `Exportar visualização` do painel unificado a `/api/exportar` quando autenticado (`gerencia`/`admin`) para gravar `acao = "EXPORTAR"` na tabela `auditoria`, evoluindo a organização dos relatórios Excel e PDF conforme o perfil RBAC. | **4.ª** |
