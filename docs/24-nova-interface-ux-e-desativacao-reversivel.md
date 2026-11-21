# Nova interface do painel GEDIV (em teste) e desativação reversível de sites

Branch: `redesign/gediv-ux-dashboard-documentos`, criada de `entrega/painel-completo-referencias`
(`c3f1eaed0e3e8454887c50bb68de750d3d65ad70`). Feita com a skill `gediv-ux-arquiteto-senior`
(`.claude/skills/gediv-ux-arquiteto-senior/`), instalada nesta branch sem alterações.

## 1. O que não foi tocado

| Item | Situação |
|---|---|
| Painel publicado (GitHub Pages, branch `gh-pages`, commit `8093132`) | intacto; nenhum push para `gh-pages` |
| Pasta `painel-publico/` (código e `dados.json`) | intacta; nenhum byte alterado |
| Workflow de preparação do Pages | intacto; ele só roda nas branches `entrega/*` e não empacota `painel-v2/` |
| `main`, PR nº 5, Conferência Privada e demais sites | intactos |

A nova interface fica em `painel-v2/` e **lê a mesma base pública** (`../painel-publico/dados.json`), com o mesmo
validador de contrato (`modelo.js`) e as mesmas rotinas de exportação (`xlsx.js`, `pdf.js`). Não há segunda cópia dos
dados nem número fixo no código.

## 2. Diagnóstico curto (uma passagem)

| Tarefa do usuário | Painel atual | Dificuldade | Mudança na nova interface |
|---|---|---|---|
| Entender o resumo | 7 cartões, vários com “—” | não sabe o que é dado e o que falta | cobertura primeiro, 3 indicadores sustentados, “Outros indicadores — aguardando dados” à parte |
| Filtrar Progressão | Visão geral, Progressão e Tempo usam a mesma tela | abas parecem iguais | páginas próprias: sub-abas Horizontal/Vertical, gráfico por grupo PCCR, evolução por modalidade |
| Ver os 7 serviços | filtro em lista | ausência parece zero | 7 cartões sempre visíveis, cada um com situação explícita |
| Achar a fonte | “Edições e fontes” no menu lateral | cadeia documental não aparece | página com a cadeia edição → PDF → página → ato → decisão e o que está disponível em cada nível |
| Saber por que não vê um processo | ficha de agregado chamada “ficha completa” | parece ficha individual | “Entender este agregado” + área gerencial marcada como indisponível |

**Contrato de dados (o que a base pública sustenta):**

| Campo | Granularidade | Acesso | Situação |
|---|---|---|---|
| Cobertura (período, edições, páginas, ausências) | total | público | disponível |
| Decisões e atos por eixo | total, em faixas | público | disponível (provisório) |
| Decisões por mês × modalidade × grupo | mensal, em faixas, só recortes ≥ 5 pessoas | público | 6 agregados, todos de Progressão |
| Tempo de Serviço por serviço | mensal | público | nenhum recorte publicável (todos protegidos) |
| Deferido / indeferido, refeitos, sem efeito, processos distintos | — | — | não disponível na base pública |
| Lista de edições, PDF, página, resenha | — | — | não disponível na base pública |
| Pessoa, matrícula, processo, ficha | individual | só gerencial autenticado | não implementado (exige servidor) |

## 3. O que foi implementado

- **Navegação em dois caminhos**: “Por assunto” (Visão geral, Progressão, Tempo de Serviço) e “Por documento e data”
  (Edições e fontes, Publicações do dia, Histórico, Alterações e refeitos, Outras publicações), mais “Entenda os
  dados” e “Área gerencial”. Trilha “Você está em”, título próprio por página, foco no título ao navegar.
- **Filtros no endereço** (`#/progressao?mod=HORIZONTAL&grupo=GAJ&mes=2026-11`): o botão Voltar do navegador
  devolve a seleção; filtros aplicados aparecem como etiquetas removíveis e há “Limpar filtros”. Valores inválidos
  no endereço são descartados.
- **Visão geral**: cobertura; 3 indicadores com unidade e situação; divisão entre os eixos; evolução mensal;
  atalhos grandes; indicadores ainda sem dado com o motivo; tabela dos agregados e exportação.
- **Progressão**: Todas / Horizontal / Vertical; Horizontal × Vertical; os 16 grupos PCCR e “não informado”
  (grupos sem agregado listados como “sem agregado publicável — não significa zero”); evolução; tabela; clique nas
  barras filtra a página (também por teclado).
- **Tempo de Serviço**: os 7 serviços sempre, com descrição simples e situação; distribuição só se houver
  recorte publicável (hoje não há — explicado sem desenhar gráfico estimado); resultado por serviço marcado como
  sem dado público.
- **Edições e fontes**: cobertura completa; cadeia documental em 7 níveis com o que está disponível em cada um;
  link para o portal oficial de A União (sem link fictício para página de ato); unidades de contagem.
- **Publicações do dia**: escolha da data; dentro do período, explica que a base é mensal e leva ao mês; fora do
  período, diz que não foi lido (sem “0 publicações”).
- **Histórico**: os 12 meses de 2026 com situação de leitura; três datas diferentes (publicação, atualização,
  conferência).
- **Alterações, Outras publicações, Área gerencial**: estados honestos, sem simular dado nem autenticação.
- **Estados distintos** com cor + símbolo + texto: Provisório, Conferido, Zero confirmado, Faixa protegida,
  Sem agregado publicável, Sem dado público, Não verificado, Só na área gerencial, Só mensal.
- **Gráficos** em SVG próprio: barra sólida até o mínimo garantido e faixa clara até o máximo; título acessível;
  “Como ler”; tabela equivalente em cada gráfico.
- **Exportação** CSV, Excel, PDF e impressão do recorte mostrado, com cabeçalho de recorte, cobertura, data da
  projeção e aviso de faixas.
- **Acessibilidade**: corpo 16 px, alvos de 44 px, foco visível, “Ir para o conteúdo”, menu em gaveta no celular
  (Escape fecha e devolve o foco), modo escuro (segue o sistema e pode ser trocado), movimento reduzido.

## 4. Testes

| Teste | Resultado |
|---|---|
| `tests/test_painel_v2.cjs` (16 testes, jsdom) | 16 aprovados |
| `npm test` do painel atual (23 testes) | 23 aprovados, sem alteração |
| Navegador (Chromium): rolagem lateral em 320, 360, 390, 768, 1024 e 1440 px, em 10 rotas | nenhuma |
| Zoom 200% | menu acessível, sem rolagem lateral |
| Teclado | “Ir para o conteúdo” é o 1º Tab; Enter na barra do gráfico filtra; foco vai ao título ao navegar |
| Celular | menu abre com foco, Escape fecha; filtro preservado ao voltar |
| Modo escuro | segue o sistema e alterna |
| Exportação real | CSV, XLSX e PDF baixados |
| Cinco tarefas da skill, por cliques | 5 de 5 concluídas |
| Erros de JavaScript | nenhum |

## 5. Mapa: funciona | sem dado | depende da área gerencial

| Funciona com a base pública | Indisponível por falta de dados | Depende da área gerencial |
|---|---|---|
| cobertura, decisões e atos por eixo, Progressão por modalidade/grupo/mês, 7 serviços (com situação), histórico mensal, exportações | deferido/indeferido, refeitos, sem efeito, processos distintos, lista de edições/PDFs/páginas, números por dia, Tempo de Serviço por serviço (protegido) | resenha → processos → decisão → ficha com trecho do Diário Oficial, conferência e correção |

## 6. Desativação e reativação reversível de sites — planejamento

**Princípio:** desativar é **tirar do ar sem apagar**. Código, interface, dados, histórico e branches ficam como
estão; reativar é desfazer um único passo. Nada aqui foi executado nos sites publicados.

### 6.1 Mecanismo já implementado na nova interface (`painel-v2`)

O arquivo `painel-v2/estado-site.json`, ao lado da página, controla a exibição:

```json
{ "ativo": true, "mensagem": "", "desde": "" }
```

- **Desativar:** mudar para `"ativo": false`, com uma mensagem, por exemplo: “Painel em manutenção programada.”
  A página mostra só o aviso. Os dados não são carregados e o código continua igual.
- **Reativar:** voltar a `"ativo": true`.
- Se o arquivo faltar ou estiver ilegível, o site **continua ativo**: uma falha de rede nunca derruba o painel.
- A mensagem é tratada como texto, nunca como HTML. Isso está coberto por testes.

### 6.2 Painel publicado hoje (GitHub Pages)

| Opção | Como desativa | Como reativa | Preserva | Observação |
|---|---|---|---|---|
| **A. Página de manutenção (recomendada)** | um commit em `gh-pages` troca só `index.html` por um aviso; os outros 8 arquivos ficam | `git revert` desse commit | todo o código, os dados e o histórico; o endereço continua respondendo | requer aprovação; um comando para cada lado |
| B. Interruptor no próprio painel | levar o mecanismo do item 6.1 ao `painel-publico` numa publicação aprovada; depois só editar o JSON | editar o JSON | idem | exige uma publicação antes, para instalar o interruptor |
| C. Desligar o GitHub Pages nas configurações | Settings → Pages → desativar | reativar e escolher de novo a branch `gh-pages` | os arquivos na branch | o endereço passa a dar erro 404 enquanto estiver desligado |

Em qualquer opção:
1. Antes de desativar, criar uma etiqueta (`git tag`) no commit publicado e registrar o SHA-256 dos arquivos.
2. Nunca apagar a branch `gh-pages`, nem o repositório, nem os arquivos de dados.
3. Depois de reativar, conferir que os SHA-256 batem com os registrados e que o endereço responde.
4. Registrar quem pediu, quando e por quê.

### 6.3 Sites hospedados fora do repositório (Conferência Privada e Visualização)

Esses sites não estão neste repositório. A desativação deles se faz no painel de controle do serviço que os
hospeda, pela responsável. O procedimento é o mesmo:
- primeiro guardar uma cópia;
- depois despublicar ou restringir o acesso, sem apagar;
- reativar pelo mesmo painel.

Por decisão da responsável, nada foi alterado neles.

### 6.4 Correção: o interruptor do item 6.1 não estava no repositório

O `.gitignore` ignora `estado*.json`, para não versionar estados locais de coleta. Essa regra também barrava
`painel-v2/estado-site.json`, que por isso nunca foi versionado. Na prática o painel-v2 ficava sempre ativo, porque
um arquivo ausente equivale a "ativo", e não havia interruptor para editar.

A correção é uma exceção exclusiva para `painel-v2/estado-site.json`, que passa a ser versionado com `"ativo": true`.
A regra geral continua valendo para os demais arquivos de estado.

### 6.5 Ferramenta de despublicação da branch `entrega/painel-completo-referencias` — não integrada

A branch `entrega/painel-completo-referencias` tem 2 commits que não estão nesta linha de integração:
`19652f0` e `70da290`, de 17/11. Eles trazem `observatorio/sites/` e `config/sites-gediv.json`, uma ferramenta que
retira um site do GitHub Pages pela API (`DELETE /pages`), com backup, plano e autorização prévia.

**Decisão técnica: não integrar agora.** A branch fica preservada, sem alteração, para uso futuro. Motivos:
1. **A operação é destrutiva e remota.** Ela apaga a configuração do Pages de um repositório. Uma ferramenta assim
   precisa de revisão e homologação próprias, não deve entrar junto com uma consolidação.
2. **A configuração está presa à própria branch.** A "fonte oficial" em `config/sites-gediv.json` aponta para
   `raw.githubusercontent.com/.../entrega/painel-completo-referencias/painel-publico/dados.json`. Ao arquivar ou
   apagar essa branch, a referência quebra.
3. **Não há segundo site cadastrado.** O próprio documento da ferramenta registra que ainda não existe um dashboard
   secundário para desativar. As prévias antigas já foram despublicadas manualmente.
4. **As opções A, B e C do item 6.2 já cobrem a necessidade atual.** São reversíveis, com um passo para cada lado,
   e não apagam nada.

Para integrá-la no futuro:
- reaplicar o conteúdo num commit novo, com autoria institucional e sem URLs privadas;
- trocar a fonte oficial por um endereço estável;
- renumerar o documento (o número 24 já existe);
- passar por PR próprio, com testes e aprovação expressa.

## 7. Para publicar (decisão pendente)

A nova interface **não foi publicada**. Para substituí-la no lugar do painel atual é preciso uma aprovação
específica. A publicação ajustaria o empacotamento (`scripts/preparar_github_pages.py`), que hoje só aceita os
arquivos do painel atual, e faria uma revisão da página no endereço de teste antes da troca.
