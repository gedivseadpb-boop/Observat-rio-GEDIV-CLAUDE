# GEDIV — arquitetura de informação e organização documental

> Guia de implementação. Não confundir interface desejada com dados já autorizados.

## 1. Dois modelos de leitura que devem coexistir

### Navegação por assunto — analítica
- **Visão Geral:** panorama, cobertura e atualidade dos dados, divisão dos dois eixos, comparação temporal, atalhos.
- **Progressão Funcional:** separar Horizontal e Vertical, permitir “Ambas”; filtro grupo PCCR; mostrar não informado e siglas dependentes de conferência; conter gráfico de evolução, comparação por grupo e tabela do recorte.
- **Tempo de Serviço:** exibir SEMPRE as sete modalidades no catálogo, inclusive “sem dado verificado” sem substituir por zero; distribuição, resultados apenas se disponíveis, evolução e tabela.
- **Histórico:** linha do tempo por mês ou data realmente disponível; diferenciar atualização do painel, publicação do DOE e conferência.
- **Alterações / Refeitos:** distinguir ato original, republicação por incorreção, retificação, refeito e tornado sem efeito; exigir vínculo verificável, não inferir resultado administrativo.
- **Outras publicações:** relacionada à GEDIV/DEREH, mas fora dos dois eixos; nenhum terceiro eixo público.
- **Publicações do dia:** se só houver consolidados mensais, destacar “sem base diária autorizada” e oferecer visão daquele mês, sem criar falsa lista de atos diários.

### Navegação por documento — documental
Usar esta cadeia de entidades quando houver metadados com proveniência:

`Ano → Mês → Edição DOE → Edição normal/suplemento → PDF → Página → Publicação/ato/resenha → Decisão/ocorrência → Processo → Ficha/evidência → Evento posterior`

**Relacional, não rígida:** uma resenha pode conter várias decisões e vários processos; uma pessoa pode ter processos distintos; um ato pode ser publicado/republicado; um processo pode aparecer em mais de um eixo; uma edição pode conter muitos PDFs/suplementos. A estrutura de UI deve representar cardinalidades e versões sem falsear equivalência.

**Matriz por unidade de contagem**

| Unidade | O que representa | Pode ser somada sem cuidado? |
|---|---|---|
| Edição | Edição DOE específica identificada | Não entre recortes duplicados |
| PDF / suplemento | Artefato documentado com versão e hash | Não confundir com edição |
| Página | Página do arquivo físico | Não confundir com publicação |
| Publicação / ato | Texto administrativo publicado | Pode comportar várias decisões |
| Resenha | Agrupamento documental identificado | Pode conter várias decisões/processos |
| Processo | Identificador administrativo | Pode reaparecer em atos/edições |
| Decisão | Resultado individual, quando explicitamente extraído | Diferenciar decisões vigentes e versões |
| Ocorrência | Ligação/menção documental | Não é sinônimo de decisão única |
| Pessoa | Identidade restrita | Não publicar |
| Evento modificador | Retificação, republicação, refeito, sem efeito | Não é novo terceiro eixo |

## 2. Navegação proposta (com páginas autênticas)

### Menu global principal
- Visão geral
- Progressão Funcional
- Tempo de Serviço
- Publicações do dia
- Histórico
- Alterações / Refeitos
- Outras publicações
- Edições e fontes (acesso global fácil)

### Navegação contextual de cada seção
**Progressão:** `Todas | Horizontal | Vertical` + `Grupos PCCR`; destacar status de validação do catálogo.

**Tempo de Serviço:** sete serviços, seletor quantidade/% se legítimo, composição e resultado por serviço somente quando houver desfecho autorizado.

**Edições e fontes:** cobertura geral, cronologia e, condicionalmente, lista autorizada de edições/suplementos e PDF oficial verificado.

**Área gerencial:** ponto de acesso separado, marcado “não habilitada até autenticação segura” enquanto não existir serviço server-side. Não criar links que pareçam abrir ficha individual mas só mostram agregados.

## 3. Hierarquia de elementos na tela

Topo compartilhado:
1. Identidade GEDIV/DOE PB.
2. Nome da seção + descrição em linguagem simples.
3. “Dados até…” e faixa de cobertura real com atualização.
4. Navegação visível e indicador do local atual.
5. Filtros relevantes à seção + estado de filtros ativos.
6. Conteúdo principal ordenado por utilidade.
7. Fonte, limitações e botão de contexto/ajuda.
8. Exportar somente quando houver objeto exportável válido.

**Visão Geral — prioridade:**
- Ficha curta de cobertura: edições, páginas, período real, data de extração/conferência.
- Até 3 cartões úteis sustentados. Indicadores não suportados numa seção “Outros indicadores — aguardando dados”, não sete caixas vazias como primeira impressão.
- Gráfico por assunto (eixos/modalidades) com denominador/supressão explícitos.
- Evolução mensal legível + tabela simples dos dados publicáveis.
- Atalhos “Explorar Progressões”, “Explorar Tempo de Serviço”, “Ver edições e fontes”.
- Limitações sempre encontráveis, nunca suprimir aviso de parcialidade.

**Progressão — prioridade:** distribuição Horizontal × Vertical, recortes PCCR, evolução, tabela, legenda de siglas.

**Tempo de Serviço — prioridade:** sete modalidades, barras horizontais, resultados por serviço (se autorizados), distribuição em rosca, tabela e explicações.

**Edições/Fontes — prioridade:** árvore/catálogo ordenado por data, estado verificado/parcial/pendente, links PDF com paginação confirmada.

## 4. Contrato de dados — não maquiar limitações

Crie uma tabela `campo → fonte → granularidade → acesso → status` a partir do repositório efetivo:
- `periodo` mensal público; `eixo`, `modalidade`, `grupo`, `subcategoria`, `situacao`, contagem em faixas; total de edições/páginas — aparentemente disponíveis, confirmar schema.
- `resenha`, `processo`, `matricula`, `nome`, `decisao individual`, `pagina_pdf`, `pdf_url`, `eventos vinculados`, `resultado explícito`, `edicao por dia` — **não presumir disponíveis na projeção atual**.
- Situações explícitas: `CONFERIDO`, `PROVISORIO`, `PENDENTE`, `SUPRIMIDO`, `NAO_EXTRAIDO`, `SEM_DADO_AUTORIZADO`, `ZERO_CONFIRMADO`, `FALHA_CARGA`; usar formas e textos distintos.
- Não preencher `null` com zero, não inferir denominador total quando há categorias omitidas.
- Não somar atos de células mensais como atos distintos, nem transformar faixas em contagens exatas.
- Antes de divulgar novo campo de edição/documento/resenha, exigir **revisão de risco de identificabilidade** (inclusive cruzamento de filtros e link oficial).

## 5. Contrato de navegação para documentação segura

Proponha interfaces e nomes de campos, sem endpoints fictícios:

```
Edicao { id_publico?, data?, numero?, tipo?, suplementos?, status?, fonte_oficial? }
Documento { id_publico?, edicao_id?, tipo?, paginas?, sha256?, url_publica_validada? }
Ato { id_interno, documento_id, pagina?, numero_resenha?, natureza?, data? }
Decisao { id_restrito, ato_id, processo_id_restrito?, resultado?, modalidade?, validacao? }
Evento { id_interno, ato_origem_id?, ato_modificador_id?, natureza?, data_evento?, estado_vinculo? }
```

Um campo com `?` é opcional e só existe se obtido/confirmado. IDs internos/restritos e dados individuais **não integram JSON estático público**. Não lançar componentes que dependem de entidades ausentes como se fossem prontos.

## 6. Critérios de uma consulta documental bem projetada

Público (quando metadados autorizados existirem):
`Edições e Fontes > Out/2026 > Edição X > Suplemento Y > PDF oficial`
→ breadcrumbs, fonte, datas e status reais, ações claras e retorno aos filtros.

Gerência (somente com autenticação server-side):
`Edições > Resenha Z > Processos (N) > Processo > Ficha completa > Página oficial + Evidência + Eventos`.
→ manter pesquisa, paginação, aba, ordenação e caminho de volta; relação um-para-muitos; log de acesso quando exigido; nada no cliente público.

Se a fonte não entregar lista de edições, a tela *não* pode apresentar "Edição X": mostrar somente “19 edições identificadas no agregado; relação individual não disponibilizada” (ou o valor corrente obtido do JSON), com botão de informações sobre a limitação.
