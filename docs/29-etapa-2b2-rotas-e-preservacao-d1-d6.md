# 29 — Etapa 2B.2: Correção da Rota Principal, Rotina Diária, Preservação de D1–D6 e Especificação de Privacidade da API Pública

## 1. Escopo executado na Etapa 2B.2

1. **Rota principal `/` e `/index.html` no servidor Python (`observatorio/web/servidor.py`):**
   - Passaram a servir diretamente o frontend definitivo homologado (`observatorio/web/unificado/index.html`, `SHA-256: 3B2DF03954615419FB50A79A2503EEFBE2A61F64CFC8A94970C4530B6F3F6649`), idêntico byte a byte a `/painel`, `/painel/` e `/painel/index.html`, com cabeçalho `Content-Security-Policy` e sem duplicar arquivos HTML.
   - As rotas legadas `/estatico`, `/estatico/` e `/estatico/<arquivo>` e todas as pastas históricas (`observatorio/web/estatico/`, `painel-v2/`, `revisao-2910/` e `painel-publico/`) foram **integralmente preservadas** no repositório para referência das funcionalidades D1–D6 e execução dos testes existentes.

2. **Decisão fundamentada sobre a rotina diária (`deploy_autonomo/rodar_diario.sh`) e `dados.json`:**
   - A inspeção completa do código comprovou que a saída `/tmp/gediv-dist-publica` (`SAIDA_PUBLICA`) gerada por `scripts/preparar_painel_publico.py` no passo `[5/6]` de `rodar_diario.sh` **não possui nenhum consumidor ativo**:
     - O servidor `observatorio.web` (`gediv-admin.service`) lê `$DADOS_DIR/observatorio.sqlite3` diretamente a cada requisição em `/api/data` e `/api/painel`.
     - `PUBLICAR_PAGES` permanece em `0` e o bloco final de `rodar_diario.sh` encerra sem publicar arquivos externos.
     - A chamada a `scripts/preparar_painel_publico.py` copiava a cada execução diária os 9 arquivos do frontend antigo `painel-publico/` e gerava um `dados.json` não utilizado.
   - **Correção aplicada em `deploy_autonomo/rodar_diario.sh`:**
     - **Preservado** integralmente o cálculo somente-leitura (`?mode=ro`) de `$DADOS_DIR/cobertura_resumo.json` (`ausencia_tecnica_edicoes` e `inconclusivas`), sem substituir nenhuma validação anterior.
     - **Adicionada** na mesma conexão estritamente somente-leitura (`sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)`) a verificação do contrato de `/api/data` (`indicadores.painel` + `adaptador.projetar_para_dashboard_2910`), garantindo matematicamente que o banco `observatorio.sqlite3` **não sofre nenhuma escrita** após o backup do passo `[3/6]`, que o perfil `PUBLICO` retorna `escopo='conferido'` com `0` linhas individuais e que `ABONO_PERMANENCIA` (sem `TS-08`) está íntegro.
     - **Eliminada** apenas a chamada sem consumidor a `scripts/preparar_painel_publico.py` (sem gerar `dados.json` órfão e sem copiar `painel-publico/`). O script `scripts/preparar_painel_publico.py` e o módulo `observatorio/painel/publicacao.py` permanecem intactos no repositório.

---

## 2. Auditoria de Segurança das Interfaces Legadas (`/estatico/index.html` e `painel-v2/admin-painel/`) e Proposta de Contenção

### 2.1 Riscos técnicos identificados em `/estatico/index.html` e `painel-v2/admin-painel/`
Embora os endpoints de mutação e leitura individual (`/api/revisao`, `/api/ato/*`, `/api/conflitos`, `/api/auditoria`, `/api/exportar`, `/api/pdf/*`) exijam autenticação no servidor, **as interfaces legadas apresentam riscos operacionais e de governança se permanecerem acessíveis como telas paralelas**:

1. **Exposição pública desnecessária em `/estatico/*`:** `/estatico/index.html` e `/estatico/app.js` são entregues sem autenticação de rota (`HTTP 200`), expondo ao público externo os diálogos administrativos `#dlgAcesso` e `#dlgRevisao` e a estrutura interna de campos de correção (`CORRIGIR`, `OMITIDA`, `VINCULAR`).
2. **Incompatibilidade com o modelo de autenticação individual e desabilitação do token legado:**
   - `/estatico/index.html` não possui login por usuário e senha (`POST /api/login`); solicita apenas um segredo único (`#campoToken`). Como o token técnico legado (`GEDIV_TOKEN_GERENCIA`) está **desabilitado por padrão** na CLI de produção (`python -m observatorio.web`), a tela induz o operador a erro ou incentiva a reativação indevida de credencial compartilhada.
   - Se um usuário autenticado no painel unificado tiver um token Bearer válido na mesma aba (`sessionStorage`) ou se o servidor for iniciado com `--habilitar-token-tecnico`, `/estatico/index.html` permitiria executar revisões contornando a interface homologada.
3. **Ausência de suporte a cookie `HttpOnly` + `X-GEDIV-CSRF` e ao RBAC de 3 perfis (`publico`, `gerencia`, `admin`):**
   - Nem `estatico/app.js` nem `painel-v2/admin-painel/admin.js` enviam o cabeçalho `X-GEDIV-CSRF` nem distinguem na interface os papéis `gerencia` e `admin`.
4. **Visão parcial e desatualizada dos dados em `/estatico/index.html`:**
   - Consome `/api/painel` sem `adaptador.projetar_para_dashboard_2910()`, omitindo os níveis verticais A–F, a separação `PENDENTE:TEC. ADM`/`PENDENTE:STF` e a integração dos `106` registros de Abono de Permanência ao eixo Tempo de Serviço (`394`).

### 2.2 Proposta para impedir o uso das interfaces legadas como sistema operacional paralelo
*(Para execução após aprovação, sem remoção de código nesta etapa)*

1. **Desativar `/estatico/*` por padrão no servidor de produção (`observatorio/web/servidor.py` e `__main__.py`):**
   - Em modo padrão de produção, requisições a `/estatico`, `/estatico/` e `/estatico/index.html` devem retornar redirecionamento `302 Found` para `/painel` (ou `404 Not Found` para `/estatico/app.js`), habilitando o atendimento de `/estatico/*` somente quando acionado explicitamente por flag de teste/compatibilidade (`habilitar_rotas_legadas: bool = False`).
2. **Manter `painel-v2/admin-painel/` desacoplado do servidor Python:**
   - `observatorio/web/servidor.py` já não serve a pasta `painel-v2/`, e `painel-v2/admin-painel/config.json` deve permanecer travado com `"api": ""` (modo desligado), impedindo que seja usado como painel administrativo paralelo.
3. **Migrar D1–D4 para dentro de `observatorio/web/unificado/`:**
   - Concluída a incorporação de D1–D4 ao painel unificado (Seção 4 abaixo) e atualizados os 2 testes legados (`test_painel.py:L282` e `test_privacidade_publica.py:L136`), arquivar definitivamente `observatorio/web/estatico/` e `painel-v2/admin-painel/`.

---

## 3. Tarefa Separada (Prioridade Crítica) — Proteção da API Pública contra Inferência por Filtros Combinados e Subtração

*(Especificação técnica registrada — nenhuma alteração na API foi realizada nesta etapa.)*

### 3.1 Avaliação de todas as respostas públicas atuais (`perfil == PUBLICO`)

| Endpoint público | O que retorna hoje para visitante sem login (`perfil == PUBLICO`) | Avaliação de risco quando houver decisões `CONFERIDO` |
|---|---|---|
| `GET /api/catalogo` | Dicionário fixo de eixos, modalidades, 16 grupos PCCR, subcategorias `TS-01`..`TS-07`, tipos de eventos e outras publicações | **SEGURO:** metadados normativos estáticos, sem contagens da base. |
| `GET /api/saude` | `versao`, `regras`, `perfil: "publico"`, `papel: "publico"` e `cobertura` (`edicoes_no_acervo`, `edicoes_lidas`, `edicoes_classificadas`, `paginas_lidas`, `primeira_data`, `ultima_data`, etc.) | **BAIXO RISCO:** contagens globais de edições/páginas do DOE-PB (documentos públicos), sem recorte por servidor, mérito ou grupo. |
| `GET /api/outras` | Lista de registros da tabela `outra_publicacao` (`id`, `tipo`, `nome_tipo`, `data`, `pagina`, `titulo`, `vinculo`, `situacao`, `url_oficial`), ocultando apenas o campo `trecho` (`projecao.py`) | **ALTO RISCO:** embora oculte `trecho`, entrega itens individuais de triagem (`situacao = "triagem, a conferir"`, incluindo atos de Abono de Permanência em `outra_publicacao`) com `id`, `data`, `pagina` e `titulo`. |
| `GET /api/painel` | Força `escopo = "conferido"`, `busca = None` e `linhas = []`, mas aceita **qualquer combinação de filtros** (`inicio`, `fim`, `eixo`, `modalidade`, `condicao`, `grupo`, `nivel`, `subcategoria`, `resultado`, `vinculo`, `cartao`) e retorna **inteiros exatos** em `indicadores` (`processos`, `resenhas`, `decisoes`, `deferidos`, `indeferidos`, `refeitos`, `sem_efeito`), `apoio`, `series` (`por_data`, `por_assunto`, `por_grupo`, `por_grupo_detalhado`, `por_nivel_vertical`, `por_subcategoria`), `resenhas` (lista de resenhas conferidas com `deferido`/`indeferido` por resenha!) e `eventos` validados | **RISCO CRÍTICO DE INFERÊNCIA:**<br>1. **Célula pequena direta:** filtrar `inicio=2026-05-10&fim=2026-05-10&grupo=G1&nivel=F` pode retornar `decisoes: 1, indeferidos: 1`, revelando o mérito de um único servidor.<br>2. **Inferência por subtração (diferença de períodos ou filtros):** consultar `01/05 a 31/05` (`total = 10`) e `01/05 a 29/05` (`total = 9`) revela exatamente `1` decisão no dia `30/05` e seu resultado.<br>3. **Exposição por resenha em `resenhas`:** uma resenha conferida com apenas `1` ou `2` servidores expõe em `resenhas[i]` a contagem exata de `deferido` e `indeferido` daquela resenha. |
| `GET /api/data` | Chama `indicadores.painel(banco, {**consulta, "escopo": "conferido"}, PUBLICO)` e `adaptador.projetar_para_dashboard_2910(p_resp, [], [])`. Entrega `rows: []`, mas repassa integralmente `backend.indicadores`, `backend.apoio`, `backend.series`, `backend.resenhas` e `dashboard.counts` com os mesmos inteiros exatos de `/api/painel` | **RISCO CRÍTICO DE INFERÊNCIA:** herda os mesmos vetores de célula pequena, subtração e contagem exata por resenha de `/api/painel`. |

### 3.2 Especificação da correção futura obrigatória (antes de expor decisões `CONFERIDO` ao público)

1. **Granularidade temporal exclusivamente mensal no perfil `PUBLICO`:**
   - Em `normalizar_filtros(bruto, PUBLICO)`, arredondar ou restringir `inicio` e `fim` a meses fechados (`YYYY-MM-01` até o último dia de `YYYY-MM`) e agrupar `series["por_data"]` por competência mensal (`YYYY-MM`), eliminando ataques de diferença dia a dia (`T(1..30) - T(1..29)`).
2. **Limiar mínimo (`k-anonymity` com `LIMIAR = 5` decisões E `>= 5` matrículas distintas) + Supressão Secundária (Complementar):**
   - Qualquer recorte filtrado ou série (`por_grupo`, `por_nivel_vertical`, `por_subcategoria`, `por_condicao`, `por_data`) cuja célula possua `0 < decisoes < 5` ou `< 5` matrículas distintas deve ter seus contadores (`decisoes`, `deferidos`, `indeferidos`, `processos`, `resenhas`) **suprimidos (`None` / `"protegido": true`)**.
   - **Proteção contra subtração de subtotais (supressão complementar e faixas de passo 5):**
     - Se uma linha/série tiver apenas **uma** categoria com `0 < n < 5` (suprimida) e o total da série for exibido como inteiro exato, o atacante descobriria `n = Total - soma(demais)`.
     - Portanto, no perfil `PUBLICO`, todas as contagens positivas em `indicadores` e `series` devem ser entregues em **faixas de largura 5 (`metrica(n)` de `observatorio/painel/publicacao.py`: `minimo = (n // 5) * 5`, `maximo = minimo + 4`, `rotulo = "min–max"`, ocultando `0 < n < 5`)** OU aplicar **supressão secundária** (suprimindo a segunda menor célula da dimensão sempre que apenas uma célula for `< 5`) e ocultar a decomposição `deferidos`/`indeferidos` sempre que qualquer um dos dois lados tiver `0 < lado < 5`!
3. **Omissão de `resenhas` individuais, `apoio` interno e `outras_publicacoes` não conferidas no perfil `PUBLICO`:**
   - No perfil `PUBLICO`, `/api/painel` e `/api/data` devem retornar `resenhas: []`, `eventos: []` e ocultar contadores internos de fila em `apoio` (`decisoes_pendentes`, `conflitos_abertos`, `vinculo_nao_expresso_pendente`).
   - `GET /api/outras` deve exigir `self._exigir_gerencia()` (ou retornar lista vazia no perfil `PUBLICO`, pois o próprio docstring de `outras_publicacoes` declara que *"São resultados de triagem, pendentes de conferência"*).
4. **Separação estrita entre `PUBLICO` e `GERENCIA_PERFIL`:**
   - Os perfis autenticados (`gerencia` e `admin`) continuam recebendo 100% dos inteiros exatos, filtros diários, `linhas`, `resenhas`, `eventos`, `apoio` e `outras_publicacoes` sem nenhuma perda de precisão analítica.

### 3.3 Testes e critérios de aceite obrigatórios para a futura tarefa de privacidade
1. **Teste de célula pequena direta (`1 <= n < 5`):** popular banco com 3 decisões `CONFERIDO` em um grupo/nível e verificar que `GET /api/painel` e `GET /api/data` sem token não retornam `1`, `2`, `3` ou `4` em nenhum campo numérico.
2. **Teste de ataque por subtração de datas (`T(mês) - T(mês menos 1 dia)`):** verificar que filtros com datas intermediárias (`2026-03-01` a `2026-03-14` vs. `2026-03-01` a `2026-03-15`) no perfil `PUBLICO` são normalizados para o mês fechado `2026-03` (ou recusados), produzindo exatamente a mesma saída e impedindo isolar um único dia.
3. **Teste de ataque por subtração complementar (`Total - (Cat_A + Cat_B)`):** popular Grupo A com `10` decisões conferidas e Grupo B com `2` decisões conferidas (`Total = 12`); comprovar que a resposta pública de `/api/painel` e `/api/data` não permite deduzir `12 - 10 = 2` nem a razão `deferidos`/`indeferidos` quando um dos méritos for `< 5`.
4. **Teste de `/api/outras` e `resenhas` no perfil `PUBLICO`:** comprovar que nenhum item em triagem de `outra_publicacao` nem contagens por resenha individual saem sem autenticação.
5. **Teste de não-regressão gerencial:** comprovar que `gerencia` e `admin` autenticados continuam recebendo contagens inteiras exatas (`12`, `10`, `2`, `3.669`, `394`, `106`, `94`, `12`) em todas as abas e gráficos.

---

## 4. Plano de Integração de D1–D4 e Conferência Documental de PDFs

| Código | Funcionalidade | Origem preservada | Requisitos para futura integração em `observatorio/web/unificado/` | Ordem proposta |
|---|---|---|---|---|
| **D1** | **Correção de campos individuais (`CORRIGIR` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`corrigirDecisao`, `revisarAto`) e `observatorio/web/estatico/app.js` (`camposDecisao`, `camposAto`, `lerCampos`) | Integrar ao modal de revisão documental de `observatorio/web/unificado/index.html` (perfis `gerencia` e `admin`), exibindo o PDF oficial (`/api/pdf/<sha256>#page=<n>`) lado a lado com formulário em seções expansíveis (Progressão Vertical A–F, Progressão Horizontal, Tempo de Serviço TS-01..TS-07, Abono de Permanência sem TS-08 e Outros benefícios), `confirma_fonte` obrigatório, justificativa e autoria da sessão (`self._conta()`). | **1.ª (com Conferência de PDFs)** |
| **D2** | **Fila e resolução de conflitos (`GET /api/conflitos` e `alvo: "conflito"` em `POST /api/revisao`)** | `painel-v2/admin-painel/admin.js` (`telaConflitos`, `resolver`) e `observatorio/revisao/servico.py` (`resolver_conflito`) | Adicionar visão/modal gerencial alimentado por `GET /api/conflitos` listando conflitos abertos entre revisores, vínculos órfãos e classificações desatualizadas (`VERSAO_REGRAS`), permitindo acionar `POST /api/revisao` (`alvo: "conflito"`). | **2.ª** |
| **D3** | **Consulta visual à trilha de auditoria (`GET /api/auditoria` e `GET /api/ato/<id>`)** | `painel-v2/admin-painel/admin.js` (`telaHistorico`, `telaAto`) e `observatorio/web/estatico/app.js` (`detalhes`) | Carregar `GET /api/ato/<id>` no detalhe de ato/processo para exibir `correcoes`, `conflitos` e `trilha`, e adicionar consulta global a `GET /api/auditoria` (últimos 300 eventos). | **3.ª** |
| **D4** | **Exportação gerencial auditada (`GET /api/exportar?formato=xlsx\|csv`) e relatórios PDF/Excel organizados** | `observatorio/web/servidor.py` (`/api/exportar`), `observatorio/painel/exportacao.py`, `painel-v2/admin-painel/admin.js`, `painel-publico/xlsx.js` e `pdf.js` | Integrar o botão `Exportar visualização` do painel unificado a `/api/exportar` quando autenticado (`gerencia`/`admin`) para gravar `acao = "EXPORTAR"` na tabela `auditoria`, evoluindo a organização dos relatórios Excel e PDF conforme o perfil RBAC. | **4.ª** |
