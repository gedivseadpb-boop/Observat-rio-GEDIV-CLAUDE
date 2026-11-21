# Validação visual e funcional local — GEDIV

A responsável escolheu explicitamente o servidor local Python para testes, preservando os
Sites publicados e sem autorizar deploy. A interface foi executada em Chromium com
JavaScript ativo sobre a projeção pública real, preservada byte a byte.

## Carregamento e escopo

HTTP 200 para `dados.json`; 19 edições, 884 páginas, limites documentais de 01/10 a
14/11/2026, cobertura histórica parcial. O cartão geral apresenta 210–214 decisões
provisórias, e seis agregados publicáveis aparecem na tabela. O resumo de Tempo de
Serviço apresenta 15–19; as sete células por serviço não são divulgadas. Essas unidades
não foram confundidas com processos ou resenhas.

## Execução em navegador

| Fluxo | Resultado observado |
|---|---|
| Grupo GAJ + Aplicar filtros | Uma linha na tabela e 25–29 decisões; Limpar restaura o recorte geral. |
| Clique em outubro no gráfico | Período de 01/10 a 31/10 e faixa 40–44; não herda novembro. |
| Ficha de agregado | Abre período, grupo, faixas, conferência e proveniência; retorno preserva a consulta. |
| Paginação e Ver todos | Segunda página com uma linha; Ver todos mostra os seis agregados. |
| Navegação | Visão geral, Progressão, Tempo de Serviço, Publicações do dia, Histórico, Alterações/Refeitos, Outras, Cobertura, Pendências e Gerencial abriram com seus estados reais. |
| Filtro Hoje | Informa que dados mensais não permitem atribuir contagem ao dia; indicador usa —. Tudo recupera a visão disponível. |
| Histórico estreito | Calendário de novembro com 30 dias e estados não verificados; sem inferir dias sem publicação. |
| Menu móvel | Abre, fecha por Escape, aplica filtros e retorna à consulta. Botão Aplicar permanece visível. |
| Tema | Alternância claro/escuro verificada. |
| Falha planejada HTTP 503 | Remove contagens anteriores e desabilita exportação; Tentar novamente restaura dados e controles. |
| Excel, CSV e PDF | Downloads iniciados pelos botões reais; arquivos completos lidos por openpyxl, csv e pypdf estrito. |
| PNG | Download real, imagem válida de 1400 × 1201; conferida visualmente com filtros, legenda e data. |

A verificação responsiva utilizou janela normal a 485 pixels e largura de 388 pixels CSS
com zoom de 125%. Nessas larguras e no desktop não foi observada rolagem horizontal da
página; tabelas e barra de abas têm seus próprios contêineres de rolagem.

## Correções feitas a partir da execução

- Campos de datas com trilhas de largura mínima zero para eliminar rolagem lateral do menu.
- Formulário com rolagem própria; Aplicar e Limpar ficam fora dessa rolagem, vinculados ao formulário.
- Menu com recorte que impede a navegação automática de esconder seu cabeçalho.
- Espaço reservado para o botão de definição de cada indicador, evitando sobreposição com o título.
- Gráficos SVG calculados pela largura real do contêiner, preservando legibilidade dos rótulos.
- PNG preserva proporções e inclui legenda, filtros e proveniência.
- URLs de JS/CSS recebem hash de conteúdo no pacote; o navegador não reutiliza um recurso antigo após atualização.

## Evidências e limites

O pacote de evidências contém capturas novas da interface pública em desktop e largura
estreita, além dos quatro exports baixados. Essas capturas contêm apenas agregados
públicos e não são cópias das 12 imagens privadas fornecidas como referência.

O navegador recusou abrir o PDF pelo protocolo local `file:`. A validação desse arquivo
foi feita pelo leitor pypdf em modo estrito, sem contornar a política do navegador.

A área gerencial permanece NÃO HABILITADA (SEGURANÇA) na interface entregue. As opções
Por resenha/Por processo apresentam a restrição; nenhuma lista individual é simulada.
Resultados por decisão, metadados por edição e fonte/página por registro continuam fora
do contrato público disponível. A conferência dessas funcionalidades depende de dados
aprovados e ambiente gerencial seguro.

Nenhum acesso de Site, registro, lote, domínio ou publicação de produção foi alterado.
