# Revisão sênior por telas e componentes — GEDIV

## Ordem de inspeção
1. `#geral`: cards, gráfico evolução, rosca/pizza, resultado, comparativos, consultas, filtros e avisos.
2. `#progressao`: Horizontal, Vertical, 16 grupos PCCR e legendas.
3. `#tempo`: TS-01 a TS-07, abas, filtros, gráficos e tabelas.
4. `#dia`: calendário, fonte, edições por data e cobertura.
5. `#historico`: escala temporal, meses vazios, mudanças de ano.
6. `#alteracoes`: refeito, sem efeito, republicação por incorreção; não confundir com deferidos.
7. `#outras`: agrupamentos sem criar novos eixos GEDIV.
8. `#cobertura`: edições/páginas/categorias de falha, ausência técnica ≠ ausência de ato.
9. `#pendencias`: mensagens acionáveis sem cara de página quebrada.
10. shell pública de `#gerencial`: nunca inserir dados individuais ou autenticação falsa.

## Estados a capturar em ambos os temas
- Normal desktop; filtros aplicados; modal/detalhes; tooltip; menus; tabela com muitas linhas; ausência de dados;
  erro de carregamento; exportação; calendário aberto com intervalo; dropdown aberto; rolagem total mobile.
- Desabilitado, foco teclado, hover, seleção, sucesso, aviso e erro.

## Verificações por componente
- **Cabeçalho:** título visível, status e data da projeção, sem muitas barras empilhadas.
- **Navegação:** local atual reconhecível; no mobile não esconder o botão para menu; rótulos com ícones.
- **Indicadores:** unidade explícita, número ou faixa legível; nunca zero para ausente; contexto e data.
- **Gráficos:** titulo, eixo/unidade, legenda, foco, padrão acessível por cor e forma, estados vazios reais;
  cliques ligados a recorte verdadeiro e não a outro tipo documental.
- **Calendário:** data selecionada persistente até aplicar, botões Cancelar/Limpar, não inferir atos do dia a
  partir de total mensal, cobertura de edições por data, histórico desde 2026 quando implementado.
- **Filtros:** estado central, limpar, remoção unitária, sincronização KPI/gráfico/tabela/exportações; link compartilhável público.
- **Tabelas:** cabeçalhos, scroll horizontal só dentro da tabela quando inevitável; ordenação, paginação, linhas legíveis.
- **Mobile:** 320 e 390, alvos de toque ~44px, botões sem sobreposição, gráfico e legenda refluem.
- **Dark:** contraste de grafos, badges, textos secundários, bordas, tooltips, inputs, `select`, calendário, hover.
- **Light:** branco/ofuscamento, camadas separadas sem usar cinza quase invisível, títulos fortes, separação entre cards.
- **A11y:** labels nativos, semântica, foco, zoom 200%, navegação sem mouse, feedback aria-live quando pertinente.
- **Design:** uma linguagem visual consistente em todos os 10 ambientes, contraste testado,
  densidade informativa suficiente, ícones coerentes e reconhecíveis; não usar ícone sozinho quando ambíguo.

## Testes heurísticos (não substituir testes com pessoas)
- Em 5 segundos, uma pessoa iniciante identifica **onde buscar por data** e **onde ver totais**?
- Em um clique, encontra Progressão e Tempo de Serviço sem saber siglas?
- Ao clicar em gráfico, percebe filtro ativo, resultado atualizado e caminho de retorno?
- Ao escolher modo escuro, todas as seções mudam corretamente, incluindo overlays?
- Quando não há dados, sabe se é ausência de publicação, lacuna de coleta ou restrição de divulgação?
