# GEDIV — ampliação da interface com as 12 referências

O painel público foi ampliado sobre `entrega/painel-publico-gediv`, a partir de
`2240dcd37a74bba4497e239d7c642fca5b5b29c2`. Esta é uma entrega **parcial do escopo
integral solicitado**: há implementação e testes, mas as consultas documentais
individuais e os resultados completos dependem de dados autorizados e integração gerencial segura.
A validação visual da interface pública foi concluída em Chromium local.
Não se declara o painel integralmente concluído.

Repositório: https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE

Na implementação anterior, a branch local era `entrega/painel-publico-gediv`, com
preservação remota em `entrega/painel-completo-referencias`. Em 17/11/2026, conforme
o novo pedido, o trabalho local passou a `entrega/painel-completo-referencias`,
continuando de `bd69223f62380ec9264918a8b0f0de33b63af75d`.
O histórico da branch remota publicada e a `main` não são substituídos. Não há PR,
merge, publicação de Site, alteração de DNS ou ativação de agendamento nesta entrega.

A proposta de disponibilização, pacote seguro e limitações estão em
[23-preparacao-publicacao-internet.md](docs/23-preparacao-publicacao-internet.md).
GitHub Pages ainda não foi ativado: a publicação depende da autorização específica
do endereço e pacote apresentados à responsável.

## Código entregue

- Sete abas principais e acessos a cobertura, pendências e área gerencial.
- Filtros laterais recolhíveis, formulário com Aplicar/Limpar, datas e atalhos Hoje,
  Este mês, Este ano e Tudo; seleção múltipla entre TS-01 e TS-07.
- Sete cartões com definições próprias. Somente decisões podem ser contadas a
  partir da projeção atual. Processos, resenhas e resultados desconhecidos usam `—`.
- Colunas agrupadas, linhas sem ligação através de lacunas, roscas por modalidade
  e TS, barras por grupo e serviço, controle Quantidade/%, tabelas equivalentes e
  seleção por mouse ou teclado. Partes claras representam os intervalos.
- Os percentuais são intervalos entre agregados exibidos, com denominador explícito;
  categorias suprimidas nunca são tratadas como zero nem como parte conhecida da base.
- Resultados por área, grupo e pelos sete serviços têm estados de indisponibilidade;
  não foram criadas barras empilhadas numéricas sem dados autorizados de resultado.
- Consulta de agregados, busca local, expansão, paginação, ordenação, Ver todos,
  ficha do agregado com proveniência e retorno preservando a seleção.
- As opções Por resenha e Por processo explicam a indisponibilidade atual. Agregados
  mensais nunca são apresentados como resenhas ou processos fictícios.
- Histórico com mapa de meses e calendário; publicação do dia com estado honesto
  de ausência de metadados diários; telas de alterações, outras matérias e pendências.
- CSV, XLSX e PDF baixáveis, além de impressão específica. Os relatórios incluem os
  mesmos filtros, todas as páginas e a versão da projeção. Exportação da lista aplica
  sua busca local; a exportação geral usa os filtros aplicados, como informado na tela.
- PNG dos gráficos de evolução foi baixado e conferido visualmente, com proporções
  preservadas, legenda, filtros e data da projeção.
- Modo claro/escuro, foco visível, atalho para conteúdo, alternativas em tabela,
  menu móvel e diálogo com retorno de foco. Testes visuais cobrem larguras de desktop,
  485 pixels e 388 pixels CSS com zoom de 125%.
- Validação fechada da projeção; erros removem valores anteriores, esvaziam o relatório
  e bloqueiam exportações. Atualizar apenas relê `dados.json`; não executa coleta/OCR.
- Gerador do pacote com lista fixa de oito arquivos. Células duplicadas e dimensões
  cruzadas são recusadas antes de distribuir dados.

## Dados efetivamente disponíveis

`painel-publico/dados.json` foi preservado byte a byte. A validação estrutural e os
testes da interface usam esse arquivo real, não números das imagens.

| Informação | Projeção disponível |
|---|---|
| Origem | `dados_reais`, experimental |
| Versão das regras | `gediv-2026.11.14-1` |
| Geração informada no arquivo | `2026-11-16T21:40:56.238189+00:00` |
| Edições / páginas | 19 / 884, na base inteira |
| Limites documentais | 01/10/2026 a 14/11/2026 |
| Histórico desde 01/01/2026 | Parcial |
| Decisões conferidas registradas | 0 na base disponível |
| Decisões provisórias | Faixa 210–214 |
| Agregados mensais publicáveis | 6, em outubro e novembro/2026 |
| Resumo de Progressão | Faixa 190–194 decisões provisórias |
| Resumo de Tempo de Serviço | Faixa 15–19 decisões provisórias |
| Células públicas por serviço TS | Nenhuma; não divulgado não é zero |
| Resultados, resenhas, processos e PDFs por registro | Não disponibilizados |

Os totais da base e as somas dos seis agregados têm escopos diferentes. Recortes
pequenos permanecem suprimidos no gerador privado. A consulta não solicita novos
recortes ao servidor e não divulga números exatos por combinação de filtros.
A interface recusa atribuir contagem mensal a uma data isolada. Cobertura de 19
edições não confirma que todas as datas entre os extremos tenham edição disponível.

## Inventário das 12 referências

Todas as 12 capturas e seu índice foram abertos na conversa privada. Não foram
copiados identificadores pessoais, valores ilustrativos ou imagens para o código.
A coluna Prova diferencia testes de integração DOM de execução em navegador.

| Imagem | Estado do escopo | Implementação e prova |
|---|---|---|
| 01 | Implementado e testado em navegador | Abas, atualização, situação, exportações e sete cartões; carregamento e navegação verificados em Chromium. |
| 02 | Parcial | Filtros, cartões, gráficos disponíveis, consulta e ficha de agregados. Resenhas e resultados dependem de projeção autorizada. |
| 03 | Parcial | Sete serviços, histórico, calendário e cobertura geral. Distribuição por edição, processo e PDF individual indisponíveis. |
| 04 | Parcial | Colunas agrupadas e roscas em faixas, seleção e tabelas. Rosca TS sem valores enquanto as células permanecerem suprimidas. |
| 05 | Parcial | Sete modalidades e Quantidade/%. Distribuição Deferido/Indeferido/Outros não calculável; estados Não verificado. |
| 06 | Parcial | Alternância de modos, busca nos agregados, expansão e paginação testadas. Pesquisa real de resenhas/processos bloqueada. |
| 07 | Bloqueado para dados individuais | Tabela pública ordenável e exportável funcional; lista por resenha com identificação exige servidor gerencial seguro. |
| 08 | Bloqueado para dados individuais | Ficha pública de agregado com origem funcional; ficha de processo e PDF por registro exigem acesso seguro e metadados. |
| 09 | Parcial | Catálogo dos 16 grupos e Não informado, barras, filtros e tabela. Resultados por grupo não disponibilizados. |
| 10 | Implementado e testado em navegador | Datas, calendário nativo e atalhos; testes impedem aplicar total mensal a um dia. Cobertura geral tem escopo explícito. |
| 11 | Implementado; valores limitados pela fonte | Sete KPIs com unidades distintas; desconhecidos usam — e conferência zero só aparece quando documentada. Testes DOM/modelo e navegador. |
| 12 | Bloqueado para dados individuais | Estrutura da ficha documental descrita na área separada; campos de progressão, TS, evidências e revisão não recebem dados sem autenticação. |

## Segurança e acesso gerencial

**NÃO HABILITADA (SEGURANÇA).** Não há conexão ativa com serviço gerencial seguro nesta
prévia estática, e os registros da fonte privada não foram copiados para a interface pública. O sistema privado já existente
foi preservado. Não foi criado login fictício, credencial no JavaScript ou envio de dados
individuais antes de autenticação. Sua futura integração precisa de autenticação no
servidor, autorização por perfil/escopo e auditoria; campos ausentes usam Não extraído.

A implantação das telas públicas não supre metadados que não existem no contrato atual:
resultado, resenha, processo, edição por dia, URL/página de fonte e vínculos de alterações.
Esses bloqueios devem ser resolvidos com projeção autorizada ou no ambiente gerencial;
reprocessamento de OCR e classificação não integra esta mudança.

## Verificação e limites

- Suíte Python completa: 587 testes executados, 13 ignorados por componentes opcionais,
  sem falhas. Após adicionar o teste de duplicatas/dimensões, seis testes do pacote foram
  executados com sucesso. Coleta, OCR e bases privadas não foram reexecutados.
- JavaScript: 23 testes passaram, incluindo nove de integração DOM com a projeção real,
  dez de consulta/privacidade, dois de XLSX e dois do PDF.
- Python focado na versão atual: 28 testes de projeção, distribuição e privacidade passaram.
  O teste novo garante que um CSS atualizado recebe uma URL de recurso diferente.
- PDF, XLSX e CSV foram baixados pelos controles reais no Chromium e lidos com
  `pypdf` em modo estrito, `openpyxl` e `csv`: PDF de uma página e planilhas de 14 linhas.
  Isso comprova formato e conteúdo; não comprova layout visual em leitores gráficos.
- Build: oito arquivos estáticos permitidos; nenhuma dependência de teste vai ao navegador.
- O serviço de prévia Sites falhou com `relay could not open browser port 4173`.
  A responsável escolheu explicitamente substituí-lo por servidor local Python para os testes.
  A nova versão foi aberta em Chromium com JavaScript ativo: dados HTTP 200, gráficos,
  filtros, fichas de agregados, tabelas, dez áreas, exports e layout estreito foram verificados.
  Falha HTTP 503 controlada removeu números antigos e bloqueou exports; a recuperação
  restaurou os dados. Datas de um único dia não receberam totais mensais.
- Nenhum site foi publicado para obter uma prévia. O servidor de teste só escuta o loopback.
  A troca do método de teste foi escolhida expressamente pela responsável.
- A leitura da referência privada e dos metadados da conexão recebeu autorização específica
  na retomada. Essa fonte permanece separada da projeção pública. A responsável decidiu
  manter o acesso do serviço existente como está; nenhuma mudança foi aplicada nele.
- CI Linux/Windows está configurado para validar pacote, modelo, DOM e exports, sem
  bancos privados, publicação ou agendamento. O resultado remoto deve ser consultado pelo
  commit de entrega; não se presume CI aprovado a partir dos testes locais.

## Como executar e revisar

Depois de baixar o repositório nesta revisão, execute na sua pasta:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory painel-publico
```

Abra `http://127.0.0.1:8765/`. Esse endereço é da máquina que executa o comando, não
uma publicação na internet. Abrir `index.html` por duplo clique não basta, pois o navegador
precisa ler o arquivo JSON por HTTP. O pacote local tem instruções equivalentes.

Para repetir os testes e gerar a distribuição:

```sh
npm ci --ignore-scripts
npm test
python -m unittest discover -s tests
python scripts/preparar_painel_publico.py --projecao painel-publico/dados.json --saida dist
```

**Para disponibilizar a versão completa na internet:** disponibilizar uma projeção autorizada
com os metadados/resultados faltantes, habilitar o ambiente gerencial com autenticação,
autorização e auditoria verificadas e obter autorização de publicação. A interface pública
foi testada localmente; nenhum Site existente foi substituído e nenhum deploy foi feito.

Detalhes da execução e correções visuais: `docs/22-validacao-visual-painel.md`.
