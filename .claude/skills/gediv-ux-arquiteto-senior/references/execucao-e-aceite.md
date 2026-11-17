# GEDIV — execução e critérios de aceite da skill

## 0. Limites de autonomia
- Permissões normais: ler projeto, desenvolver em branch, rodar testes locais, gerar screenshots com dados públicos, commitar mudanças não sigilosas e enviar apenas branch autorizada se ambiente permitir.
- **Sem autorização**: alterar `main`, merge, PR quando não solicitado, publicação/deploy, desativar GitHub Pages, trocar domínio, mexer em Site privado, habilitar conexão gerencial, contratar serviços ou retirar controles de privacidade.
- Se política/navegador bloquear inspeção, respeitar; não contornar bloqueio via CDP, URLs alternativas proibidas ou simulações de autenticação.
- Antes de qualquer captura, assegurar que apenas dados públicos são visíveis; redigir/omitir material de referência com registros individuais.

## 1. Primeiro contato com o projeto (máximo 1 passagem)
1. `git status`, branch, commit, remotos, teste de recursos básicos.
2. Localize UI (HTML/CSS/JS), modelo, JSON de projeção e testes.
3. Leia fluxos da UI atual e confirme divergências com estas referências:
   - Conferência Privada (rico em painéis, gráficos, filtros e consultas).
   - Visualização Claude (abas completas e navegação por conteúdo).
   - Inventário de 12 capturas (não exigir anexos novamente se já existentes).
4. Produza **matriz de lacunas curta**: tarefa do usuário | tela atual | dificuldade | mudança.
5. Imediatamente implemente a primeira fatia. Evite longa especulação arquitetural.

## 2. Iterações de entrega recomendadas
**Fatia A — Fazer o usuário entender**
- Refazer Visão Geral e cabeçalho: três indicadores utilizáveis, escopo, cobertura, atualização; filtro mensal básico; atalhos; texto de confiança e estados.
- Critério: uma pessoa entende em 30 segundos o período e o grau de cobertura.

**Fatia B — Fazer o usuário comparar**
- Separar de fato os templates de Progressão e Tempo de Serviço (sem compartilhamento de função `overview` para todas).
- Progressão: H/V e PCCR; Tempo de Serviço: TS-01 a TS-07, gráficos legíveis, pequenas tabelas e estado dos resultados por modalidade.
- Critério: duas páginas têm conteúdo de natureza diferente, testes independentes.

**Fatia C — Fazer o usuário encontrar documentos**
- Implementar `Edições e fontes` como explorador documental, até o nível de detalhe permitido pelo contrato real.
- Diferenciar unidades de contagem e proveniência. Se faltar edição/PDF/página, deixar documentado o campo ausente no dado, sem fake listagens.
- Desenhar contrato gerencial futuro, sem criar endpoints inseguros.

**Fatia D — Fazer o usuário aprofundar**
- Histórico, publicações do dia, alterações, outras publicações: estados verdadeiros, cronologia e links que não induzam a erro.
- Busca apenas onde o contrato permite; filtro avançado bloqueado com explicação quando não calculável; export da mesma seleção.

**Fatia E — Polimento sério**
- Componentes acessíveis, responsividade, foco, escala tipográfica e ajuste de gráficos/legendas para 320/360/390/768/1024/1440 px.
- Teste de zoom 200%, teclado, tema escuro, reduções de movimento, impressão/PDF.
- Capturas de tela de depois e comparação de tarefa, não comparações puramente estéticas.

Fatia é **implementação e teste**; não desviar para uma sequência de cinco relatórios de análise.

## 3. Testes funcionais por tarefa (browser)
1. **Orientação:** entrar na home; ler cobertura/última atualização; identificar status de conferência.
2. **Progressão:** acionar Horizontal, depois Vertical, escolher grupo PCCR, limpar filtros; verificar títulos, contagens em faixas e tabela.
3. **Tempo de Serviço:** observar todos os sete serviços; selecionar dois; alternar quantidade/% quando disponível; confirmar ausência ≠ zero.
4. **Exploração documental:** ir a Edições e Fontes, encontrar período, clicar no único link realmente autorizado ou ler estado “lista não disponibilizada”; nunca clicar em PDF fictício.
5. **Dia:** selecionar uma data sem metadados diários; ver aviso correto e caminho ao mês, sem um falso “0 publicações”.
6. **Restrições:** tentar resultado/deferimento individual sem dado autorizado; UI não deve produzir números fictícios.
7. **Exportação:** CSV/XLSX/PDF/PNG trazem filtro aplicado, fonte, cobertura, contexto de faixa e não incluem nomes/processos.
8. **Mobile/teclado:** abrir e fechar menu, selecionar filtro, navegar até gráfico/tabela e retornar; sem rolagem horizontal na página.
9. **Erro:** simular `dados.json` ausente; todos os números antigos desaparecem, downloads ficam desabilitados; recuperação funcional.
10. **Privacidade:** inspecionar bundle e rede; nenhum registro individual indevido. Verificar cruzamento de filtros e possibilidade de dedução por diferença.
11. **Regressão:** testes JS/Python existentes e CI se disponível; não apagar casos de privacidade.
12. **Roteiro do gestor leigo:** “Quero saber quais assuntos apareceram no período, qual a cobertura e onde encontrar as fontes”; deve ser resolvido sem tutorial externo.

## 4. Contratos de aceite da interface
- [ ] Há conteúdo específico em Visão Geral, Progressão e Tempo de Serviço; não é `overview()` repetido em três rotas.
- [ ] O usuário encontra “Edições e fontes” facilmente e entende a relação com documentos, ainda que o JSON só tenha contagem agregada.
- [ ] Indicador desconhecido não ocupa cartão principal com travessão sem explicação.
- [ ] Toda métrica mostra unidade, período, escopo e conferência.
- [ ] Sete serviços são visíveis e distinguem não verificado de zero.
- [ ] Gráficos têm legenda, tabela alternativa e clique de filtro sincronizado.
- [ ] Não há interação com aparência de sucesso que termina apenas numa tela vazia genérica.
- [ ] Dados individuais exigem backend protegido; nenhum dado sensível no pacote público.
- [ ] O painel tem ligação real com projeção autorizada; nenhum exemplo tratado como real.
- [ ] Exportações e tema funcionam.
- [ ] Layout responsivo e acessível por teclado.
- [ ] Não houve deploy, alteração de `main` ou de Sites existentes sem autorização.

## 5. Entrega curta, mas demonstrável
Responder em português do Brasil, **depois de implementar**, com:
- O que mudou **visivelmente**, por rota e fluxo; evitar “melhorias gerais”.
- Uma captura legível da home e uma de Progressão/Tempo, além de mobile, se navegador disponível; se não, informar bloqueio.
- Branch e SHA integral de commit publicado na branch, não confundir com deploy.
- Testes executados e resultado.
- Matriz de acesso: `público funcional | gerencial indisponível | dados ausentes`.
- Uma ação objetiva solicitada ao gestor apenas quando necessária (por exemplo, aprovação específica de deploy).

## 6. Não são critérios de sucesso
- “CI passou” sem teste visual.
- “Criamos 30 gráficos” com números fictícios.
- “Sete cartões” quando seis estão “—”.
- “Busca por processo” que vasculha JSON público agregado.
- “PDF oficial” sem URL/página verificadas.
- “Menu completo” com cinco seções que mostram as mesmas células.
- “Consulta diária” alimentada por base só mensal.
- “Dashboard completo” quando a integração gerencial depende de mecanismo ainda não implantado.
