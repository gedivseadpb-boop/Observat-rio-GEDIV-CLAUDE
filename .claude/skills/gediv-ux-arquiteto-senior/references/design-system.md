# GEDIV — sistema visual e regras de visualização

## A. Princípio: dashboard de leitura pública, não centro de controle técnico
Objetivo visual: informar uma pessoa com pouca experiência digital sem ocultar complexidade para quem precisa investigar. Na Visão Geral, cada bloco responde a UMA pergunta. Agrupamento visual e textos curtos antes de ornamentos.

Trabalhar com o visual institucional existente como ponto de partida: branco/azul-escuro, realces para modalidades e status. Melhorar disposição, tipografia, respiro, hierarquia, consistência, usabilidade e microcópia. Não copiar indevidamente telas privadas nem inserir dados reais nos mockups.

### Sistema de tokens recomendado (ajustar ao repositório)
- **Escala de espaçamento** consistente: 4 / 8 / 12 / 16 / 24 / 32 px.
- **Tipografia:** título da página 28–32 px, título de seção 20–24 px, cartão 16–18 px, corpo 14–16 px, metadados 12–14 px; zoom 200% sem perda grave de navegação.
- **Cores por significado**: Azul progressão vertical, verde progressão horizontal, laranja Tempo de Serviço somente em gráficos de modalidade. Para resultado, verde deferido e vermelho indeferido; **não depender apenas da cor**, incluir rótulo/ícone e padrões acessíveis.
- **Superfícies:** fundo claro, cartões brancos com borda suave, contraste legível; modo escuro com tokens semanticamente equivalentes.
- **Botões:** primário somente para a ação principal por bloco, secundários para filtros/exports; altura-alvo confortável, estados hover/focus/disabled coerentes.
- **Grid:** desktop coluna principal de conteúdo e filtros laterais recolhíveis; painel de detalhes contextual opcional, sem truncar gráficos. Mobile uma coluna, filtros drawer e ações fixas não obstrutivas.

### Ordem de leitura:
Contexto (onde estou?) → Fonte/cobertura (posso confiar nesse recorte?) → Resumo → Composição → Evolução → Consulta/tabela → Documento/detalhe → Exportar.
Eliminar competição entre sete cartões idênticos quando a maioria está indisponível.

## B. Componentes reutilizáveis que devem existir
`PageHeader`, `DataFreshness`, `CoverageBanner`, `SectionNav`, `FilterBar`, `ActiveFilters`, `KpiCard`, `AvailabilityState`, `ChartPanel`, `ChartLegend`, `TableWithPagination`, `DocumentBreadcrumbs`, `SourceLink`, `DetailsDrawer`, `ExportMenu`, `PrivacyNotice`, `EmptyState`, `StatusTag`, `MobileFilterDrawer`, `HelpPopover`.

Adapte à stack real. Não reescrever tudo em React se o projeto é HTML/JS sem build e isso aumentaria risco/manutenção. Modularizar no grau necessário, sem introduzir framework apenas por estética.

## C. Padrões para gráficos

| Pergunta | Gráfico recomendado | Regras |
|---|---|---|
| Que proporção corresponde a cada eixo/modalidade? | Rosca com legenda e tabela | Categorias poucas, denominador seguro, indicar base parcial/limites |
| Qual grupo PCCR tem mais ocorrências publicáveis? | Barras horizontais | Ordenação e opção “Não informado”; não ranquear células suprimidas |
| Como evoluíram os indicadores por mês? | Linhas ou colunas | Eixo temporal com meses, sem inventar série diária |
| Como se distribuem os sete serviços? | Barras horizontais + rosca opcional | Todos os sete serviços visíveis, inclusive “Não verificado” |
| Como se dividem deferidos e indeferidos? | Barra empilhada 100% ou contagens | Somente com resultados autorizados; não usar nº de decisões totais como deferidos |
| O que posso consultar em detalhe? | Tabela paginada | Ordenação, filtro, unidades de contagem, coluna de origem, estado e detalhes autorizados |

**Percentuais em faixas:** não desenhar arcos exatos se não há denominador exato. Quando o repositório já usa limites inferiores para composição, rotular de forma inequívoca “distribuição ilustrativa dos limites inferiores publicáveis”, complementar tabela de intervalos e alertar que categorias suprimidas não entram; preferir um gráfico de barras de intervalos se a rosca induzir erro.

**Filtros por clique** em fatias/legendas devem refletir visualmente chips de filtro ativo e oferecer reset. Nunca transformar filtro de decisão indisponível em gráfico com números inventados.

**Gráfico tem sempre** título, subtítulo legível (unidade/período), estado de conferência/cobertura, eixo/legenda, interpretação curta e link para tabela correspondente. Export PNG deve preservar isso tudo.

## D. Estados e microcópias exatas (ajustar ao contexto)
- `Não verificado`: “Ainda não há informação conferida para esta categoria; isso não significa zero.”
- `Sem dado público`: “Este detalhamento não está disponível na base pública atual.”
- `Suprimido`: “O recorte foi protegido para evitar identificação de pessoas.”
- `Recorte impossível`: “Os dados publicados são mensais; escolha um mês completo.”
- `Não atualizado`: “Última projeção em DD/MM/AAAA HH:mm. Esta página não realiza coleta do Diário Oficial.”
- `Erro de carregamento`: “Não foi possível carregar os dados agora. Tentar novamente.” Desabilitar métricas/exports velhos.
- `Sem resultados após filtro`: “Nenhum agregado divulgável para estes filtros; não é prova de inexistência de publicações.”
- `Área gerencial`: “Consulta individual indisponível nesta versão pública; exige autenticação e autorização no servidor.”

Não usar a palavra “ficha completa” para demonstrativo de agregado. Separar visualmente 'documentação do dado' de 'documento oficial individual'.

## E. Formas de interação por nível de experiência
- **Ação rápida**: grandes botões “Ver progressões”, “Ver Tempo de Serviço”, “Ver edições” na home.
- **Filtros básicos primeiro**: período (meses fechados), eixo, modalidade, grupo/serviço; avançados sob disclosure.
- **Filtros sincronizados**: cada alteração atualiza título, resumo, gráficos, tabela, export e URL/histórico, sem estado invisível.
- **Ajuda contextual**: “O que é uma resenha?”, “Por que a contagem aparece como faixa?”, “Qual a diferença entre PDF e decisão?”
- **Lista + ficha**: em desktop, lista de resenhas/processos e detalhe lado a lado somente em área gerencial autorizada; no mobile, lista → detalhe → voltar preservando estado.
- **Impressão**: título, escopo, filtros, atualização, fonte, legenda, lacunas/supressões.

## F. Referências fornecidas pelo usuário (sem dados pessoais)
As 12 imagens anteriores descrevem, entre outros:
- Abas `Visão Geral / Progressão / Tempo de Serviço / Publicações do dia / Histórico / Alterações-Refeitos / Outras publicações`.
- Sete indicadores: processos, resenhas, decisões, deferidos, indeferidos, refeitos, sem efeito.
- Sidebar de filtros com período, grupo, modalidades, sete serviços e resultado.
- Barras de evolução, gráfico de rosca por assunto, resultados empilhados por área.
- Rosca dos sete serviços; alternância quantidade/percentual, quando possível.
- Progresso por grupo PCCR.
- Consulta por resenha/processo, navegação expansível, tabela de processos, ficha documental e link para página do DOE — **apenas se a conexão gerencial autenticada existir**.
- Avisos de revisão, cobertura e projeção parcial.

Implemente essas intenções de UX nas fontes de dados adequadas. Não cole as 12 imagens em repositórios públicos; podem exibir nomes, matrículas ou processos.
