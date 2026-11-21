# Etapa 05.3.4 — Extração de PDFs difíceis, OCR e classificação dos atos

Relatório da quarta correção da Etapa 05.3. Trata só de **como o texto é extraído do PDF** e de **como os atos são
classificados**. Não altera coleta, banco (o esquema continua na versão 8), revisão humana nem regras
administrativas homologadas. Nenhum PDF oficial, nome, matrícula ou processo real está neste repositório: os
testes usam dados sintéticos e a regressão com os PDFs oficiais foi feita fora do repositório.

## 1. Commit de origem

`54423442e2d70b1af95b15d054cd6e5d708d3c28` — ponta da branch `etapa05-3/pr03-leitura-banco-revisao`
(Etapa 05.3.3). Antes de começar foi conferido: mesmo SHA no remoto e no local, CI aprovado nos quatro
ambientes, suíte local com dados reais 396/396, nenhuma alteração pendente.

## 2. Branch e commits

Branch: `etapa05-3/pr04-extracao-ocr-classificacao`, criada a partir do commit acima.

| Grupo | Commit | Conteúdo |
|---|---|---|
| A | `feat(05.3.4/A)` | linhas de tabela pela geometria e regiões da página (`leitura/pagina.py`) |
| B | `feat(05.3.4/B)` | completude do OCR, fontes com mapeamento errado, limites por página e por arquivo (`leitura/leitor.py`, `leitura/ocr.py`) |
| C e D | `feat(05.3.4/C-D)` | continuidade entre páginas e classificação (`gerencias/gediv/classificador.py`, `catalogo.py`) |
| E | `test(05.3.4/E)` e `fix(05.3.4/B)` | 53 testes sintéticos, integração com a revisão da 05.3.3 e a correção achada na regressão (ligaduras) |
| — | `docs(05.3.4)` | este relatório e o índice do README |

Os grupos C e D estão no mesmo commit porque mexem na mesma função (`_decisoes`) e não podiam ser separados sem
deixar um commit intermediário quebrado.

## 3. Defeitos corrigidos

Cada linha foi confirmada na base antes da correção: os testes novos, executados sobre o código de `5442344`,
falham em 43 dos 52 casos escritos primeiro (os 9 restantes são testes de preservação, que devem passar
antes e depois). O 53º teste nasceu de um achado da regressão (seção 10).

| # | Defeito na base | Correção |
|---|---|---|
| 1 | Célula de tabela quebrada em duas linhas: a primeira metade do nome, quando ficava **acima** da linha do processo, era atribuída à pessoa de cima; cargo e evolução podiam ir junto. | Cada fragmento é juntado, coluna a coluna, à linha de tabela a que pertence, pela geometria. |
| 2 | Quando a geometria não decide, o fragmento era colado a alguém mesmo assim. | O fragmento sai marcado no texto, não é colado a ninguém e as decisões vizinhas e o ato recebem pendência. |
| 3 | Tabela de largura total numa página de duas colunas: a linha cujo vão entre células caía sobre o corredor central era partida em duas e o cargo se separava da pessoa. | A linha é reconhecida como parte da tabela e lida inteira; a ordem de leitura das regiões é mantida. |
| 4 | Só o sinal `(cid:N)` denunciava fonte sem mapeamento; fonte com mapeamento **errado** (letras trocadas) passava como texto íntegro. | A fonte é julgada pelo próprio texto (vogais, sinais estranhos) e as palavras seguem para o OCR seletivo. |
| 5 | Imagem com texto abaixo de 25% da página nunca era examinada. | Imagem sem palavras por cima é lida por OCR, só na região. |
| 6 | O OCR podia devolver a página sem uma linha e nada indicava a falta. | Faixas com tinta de texto e sem palavra são relidas; se continuarem sem leitura, a página fica `LEITURA_INCOMPLETA`. |
| 7 | Só havia limite de tempo por chamada ao OCR. | Limites por página e por arquivo (tempo e número de chamadas). |
| 8 | Cabeçalho da resenha repetido na página seguinte abria um segundo ato com o mesmo número. | É o mesmo ato; as decisões continuam ligadas ao ato original. |
| 9 | Linha da tabela repetida no alto da página seguinte virava duas decisões. | Contada uma vez, com pendência na decisão. |
| 10 | Todo ato que atravessava página recebia a mesma pendência genérica. | A pendência existe só quando a continuidade é duvidosa, e diz o motivo. |
| 11 | Linha sem processo reconhecido não virava decisão: era colada à pessoa de cima ou sumia. | Vira decisão com **processo ausente** (nunca um número presumido) e pendência. |
| 12 | Resenha mista: a linha logo acima de `INDEFERIDOS:` absorvia o título e virava indeferida; as demais ficavam sem resultado. | Resultado por bloco; o da própria linha prevalece; sem indicação, fica "não informado" com pendência. |
| 13 | Portaria com o número na linha seguinte não era reconhecida; a unidade no cabeçalho de cima ficava fora do ato. | Reconhecida nas três formas vistas; o cabeçalho anterior entra no ato. |
| 14 | Portaria só da DEREH, e portaria da GEDIV com assunto de um dos eixos, não iam para lugar nenhum. | Toda portaria relacionada vai para "Outras publicações"; nenhuma vira decisão. |
| 15 | Dois grupos do PCCR no mesmo ato: valia o que o código avaliava primeiro. | O ato fica sem grupo, com as expressões guardadas e pendência. |
| 16 | Qualquer "desistência de licença" virava TS-04; qualquer "conversão de licença especial" virava TS-06. | TS-04 exige a licença de interesses particulares; TS-06 exige a conversão em tempo de serviço. Sem o requisito, o ato fica em Tempo de Serviço sem assunto, com pendência. |

`TEC. ADM` e `STF` continuam sem grupo, como já estavam; a regra foi coberta por novos testes, inclusive quando
a expressão aparece ao lado da sigla homologada.

## 4. Arquivos e funções alterados

| Arquivo | Funções novas ou alteradas |
|---|---|
| `observatorio/leitura/pagina.py` | `Palavra` (inalterada), `LeituraPagina`, `limiar_de_celula`, `_celulas`, `_suavizar_regioes`, `_intervalos_de_colunas`, `_coluna_de`, `reconstruir_tabelas`, `_linhas_pela_grade`, `_linhas_da_tabela`, `_juntar_celulas`, `ler_pagina_detalhada`; `ler_pagina` mantém a assinatura e ganha o parâmetro opcional `reguas` |
| `observatorio/leitura/leitor.py` | `VERSAO` 0.6 → 0.7; `fontes_suspeitas`, `_marcar_fontes_suspeitas`, `_imagens_sem_texto`, `_ler_regioes_sem_texto`, `faixas_sem_leitura`, `_ocr_completo`, `_reguas`; `_classificar_ocr` e `_ler_uma_pagina` alteradas; `ler_arquivo` zera os limites a cada arquivo e página |
| `observatorio/leitura/ocr.py` | `iniciar_arquivo`, `iniciar_pagina`, `uso`, `_folga`; `_chamar` passa a contar tempo e chamadas |
| `observatorio/gerencias/gediv/catalogo.py` | `VERSAO_REGRAS`; padrões de TS-04 e TS-06; `grupos_presentes`, `avaliar_grupo`, `avaliar_subcategoria`; `identificar_grupo` e `identificar_subcategoria` mantêm a assinatura |
| `observatorio/gerencias/gediv/classificador.py` | `_portaria_no_cabecalho`, `_continuacao_repetida`, `_chave_do_cabecalho`, `_continuidade_duvidosa`, `_Marco`, `_marcos_da_linha`, `_titulo_de_merito`; alteradas: `_linhas`, `_inicios`, `_fim`, `_decisoes`, `_tema`, `_tema_progressao`, `classificar`; `PAT_CABECALHO_UNIDADE` passa a reconhecer "Gerência Operacional" |
| `tests/test_extracao_ocr_classificacao.py` | novo |
| `tests/test_gediv.py`, `tests/test_leitura_correcoes.py` | um teste ajustado em cada (seção 6) |

Variáveis de ambiente novas, todas opcionais: `GEDIV_OCR_TEMPO_PAGINA` (padrão 300 s),
`GEDIV_OCR_TEMPO_ARQUIVO` (1800 s), `GEDIV_OCR_CHAMADAS_PAGINA` (80). `GEDIV_OCR_TEMPO_MAXIMO` continua valendo
por chamada.

## 5. Algoritmos modificados

### 5.1 Linha de tabela pela geometria

1. As palavras de cada linha física são agrupadas em **células**: um vão maior que o limite separa duas células.
   O limite é o menor entre três vezes o vão mediano da página e 2,2 vezes a largura mediana de uma letra (a
   segunda medida serve às páginas quase só de tabelas, em que a mediana dos vãos já é um vão entre células).
2. Um **trecho de tabela** começa numa linha com três ou mais células e segue enquanto as linhas tiverem três ou
   mais células, ou forem fragmentos próximos (até 1,35 vez a entrelinha típica) que cabem nas colunas. São
   exigidas pelo menos três linhas completas e três colunas.
3. O trecho **termina** na primeira linha que não cabe nas colunas ou que recomeça sozinha na primeira coluna
   (título, "Publique-se", parágrafo). Essas linhas nunca são absorvidas.
4. **Com grade vetorial** (réguas horizontais que atravessam pelo menos 60% da tabela): cada faixa entre duas
   réguas é uma linha da tabela. A grade só é usada se nenhuma faixa contiver duas linhas completas — réguas que
   só contornam a tabela não dizem onde cada linha termina.
5. **Sem grade**: é âncora a linha com a primeira coluna preenchida e pelo menos metade das colunas. Cada
   fragmento vai para a âncora mais próxima na vertical (folga de 15%). Nos empates vale o indício do próprio
   trecho: se todos os fragmentos decididos ficam abaixo da sua âncora, o empate também (células alinhadas no
   alto, o padrão do DOE); se ficam acima, idem (células centradas). Com indícios nos dois sentidos, o fragmento
   **não é atribuído**: sai numa linha própria, com a marca `[LINHA DE TABELA SEM ATRIBUICAO SEGURA]`.
6. As células são juntadas coluna a coluna, de cima para baixo. Texto justificado letra a letra é reunido em
   cada pedaço antes da junção.

### 5.2 Regiões da página

A página continua dividida pelo corredor central. A novidade: uma sequência de até três linhas divididas pelo
corredor, entre duas linhas de largura total, com a primeira célula e a célula à direita do corredor alinhadas às
células das vizinhas, é tratada como parte da mesma tabela larga e lida inteira. Texto em colunas entre dois
títulos não satisfaz o alinhamento e continua lido coluna por coluna.

### 5.3 Completude do OCR

- **Fonte suspeita**: com 40 letras ou mais na página, menos de 18% de vogais, ou mais de 30% de sinais fora do
  alfabeto, dos algarismos e da pontuação comum. As palavras dessa fonte recebem o mesmo sinal de ilegível das
  `(cid:N)` e seguem o caminho que já existia (OCR do trecho ou da tabela; sem OCR, página `INCONSISTENTE`).
- **Imagem sem texto**: pelo menos 1,5% da página, 60 × 12 pt, sem nenhuma palavra nativa por cima. A região é
  lida por OCR. Menos de três palavras confiáveis: é figura, nada muda. Figura com pouco texto: ficam só as
  palavras confiáveis. Região densa (15 palavras ou mais) mal lida: tudo é guardado e a página fica pendente.
- **Linhas não lidas** (páginas inteiras por OCR): a imagem é projetada na vertical para achar as faixas com
  tinta; em cada faixa, os grupos de tinta são projetados na horizontal. Um segmento com seis ou mais traços e
  nenhuma palavra reconhecida por cima é uma linha não lida (uma régua tem um traço só). O segmento é relido
  isolado; se continuar sem leitura, a página fica `LEITURA_INCOMPLETA`.
- **Limites**: tempo de OCR por página e por arquivo, e número de chamadas por página. A chamada recebe só o
  tempo que resta. Estourado o limite, a página fica `OCR_ESGOTADO` com o texto nativo e o arquivo segue.

### 5.4 Continuidade

- Cabeçalho de resenha com o mesmo número e sufixo do ato em curso, sem "Publique-se" entre os dois, em outra
  página ou declarado "continuação", e sem palavra de alteração (republicação, retificação, sem efeito) nas três
  linhas seguintes: é o mesmo ato.
- Decisão igual à anterior (processo, matrícula e nome) em página diferente: linha repetida, contada uma vez.
  Na mesma página, o mesmo processo para duas pessoas continua sendo duas decisões.
- Continuidade demonstrada: o ato termina em "Publique-se" e tem linhas de processo na primeira e na última
  página, ou o cabeçalho foi repetido. Caso contrário, pendência com o motivo.

### 5.5 Classificação

- **Decisão sem processo**: linha que começa pela matrícula (com ou sem um processo de grafia defeituosa antes) e
  segue com o nome. Só conta depois da primeira linha com processo, ou num ato sem nenhum processo reconhecido,
  para o preâmbulo nunca virar decisão. O processo é gravado como ausente; a grafia publicada vai na pendência.
  A identidade lógica da decisão (05.3.3) cai na matrícula.
- **Mérito por bloco**: uma linha que é só um título de mérito vale para as linhas abaixo até o próximo título e
  interrompe a continuação da linha de cima. Ordem: resultado na própria linha, depois o do bloco, depois o do
  ato. Em ato misto sem nenhum dos dois, "não informado" e pendência.
- **Portarias**: reconhecidas no início da linha, depois de nomes de unidades na mesma linha, e com o número (ou
  "Nº" e o número) na linha seguinte. Citação no meio do texto não abre ato. Toda portaria original relacionada
  vai para `outra_publicacao` com o tipo `PORTARIA`: vínculo expresso com a GEDIV, ou não expresso quando só a
  DEREH aparece. Se o assunto é de um dos eixos, isso vai no título como indício. Portaria de outra gerência ou
  de outra secretaria continua fora. Portaria que altera publicação continua sendo evento.
- **Grupos**: todos os grupos presentes no preâmbulo são levantados; mais de um, nenhum é atribuído.
- **Assuntos**: os padrões de TS-04 e TS-06 exigem o requisito; a expressão genérica sem o requisito impede a
  queda no assunto vizinho e gera pendência.

Decisões e atos novos ou alterados seguem pelo mecanismo da 05.3.3 sem código novo: a mudança da versão do
leitor gera nova revisão de leitura, a reclassificação compara com o que estava gravado, e o que diverge de dado
já revisado vira conflito para a gerência.

## 6. Testes novos

`tests/test_extracao_ocr_classificacao.py`, 53 testes:

| Grupo | Classe | Testes |
|---|---|---|
| A | `TesteLinhasDeTabelaPelaGeometria` | 6 |
| A | `TesteRegioesDaPagina` | 3 |
| B | `TesteFontesComMapeamentoErrado` | 3 |
| B | `TesteLinhasQueOcrNaoLeu` | 4 |
| B | `TesteRegiaoSemTextoEOcrCompleto` | 3 (exigem Tesseract) |
| B | `TesteLimitesDoOcr` | 4 |
| C | `TesteContinuidade` | 6 |
| D | `TesteDecisaoSemProcesso` | 4 |
| D | `TesteMeritoPorBloco` | 4 |
| D | `TestePortarias` | 9 |
| D | `TesteGruposEAssuntosAmbiguos` | 7 |

Quatro deles gravam no banco e conferem a integração com a 05.3.3: fila de revisão, chave lógica pela
matrícula, correção do assunto pela revisão, gravação em "Outras publicações".

Dois testes antigos foram ajustados, porque a regra que eles fixavam mudou de propósito:

- `test_gediv.py`, resenha que continua na página seguinte: esperava a pendência genérica de continuidade. Agora
  confere que não há pendência quando a continuidade está demonstrada e que há quando falta o "Publique-se".
- `test_leitura_correcoes.py`, padrões compactos: o exemplo de TS-04 era "desistência da licença para tratar",
  sem "interesses particulares". O exemplo foi completado.

## 7. Resultados locais

Ambiente: Python 3.13, pdfplumber, pypdf, reportlab, pytesseract, Tesseract 5.3.4 com português.

| Execução | Testes | Aprovados | Falhos | Pulados |
|---|---|---|---|---|
| Suíte sem dados reais (como no CI completo) | 449 | 447 | 0 | 2 |
| Suíte com os 11 PDFs oficiais e o corpus privado | 449 | 449 | 0 | 0 |

Eram 396 testes na 05.3.3; são 53 novos. Os dois pulados na primeira linha são os que exigem os PDFs oficiais e
o corpus privado, que não estão no repositório.

Antes e depois, com o mesmo arquivo de testes novo executado sobre o código de `5442344`: 24 falhas e 19 erros
em 52; sobre esta branch, 53 aprovados em 53.

## 8. Resultados do CI

Workflow `Testes`, execução nº 31, sobre o commit de código `18084de114c91afafdf73d4831d0bdbd4a478431`
(<https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/43671349443>):

| Ambiente | Resultado | Testes | Pulados |
|---|---|---|---|
| ubuntu-24.04, Python 3.13 | aprovado | 449 | 3 |
| ubuntu-24.04, Python 3.11 | aprovado | 449 | 3 |
| windows-latest, Python 3.13 | aprovado | 449 | 13 |
| windows-latest, Python 3.11 | aprovado | 449 | 13 |

No Ubuntu (com Tesseract) os três pulados são os dois que exigem os PDFs oficiais e o corpus privado e o da
planilha, que exige `openpyxl`; todos os testes novos desta etapa foram executados. No Windows o workflow não
instala o Tesseract: aos dez pulados que já existiam somam-se os três testes novos que fazem OCR de verdade
(`TesteRegiaoSemTextoEOcrCompleto`). Os demais 50 testes novos rodam no Windows.

O commit de documentação que inclui este relatório é posterior a essa execução; o resultado da execução sobre
ele está no relatório final de entrega, fora do repositório.

## 9. Resultados do corpus conhecido

Corpus de PDFs difíceis (manifesto público em `docs/validacao/corpus_pdfs_dificeis.json`; valores esperados em
arquivo privado, fora do repositório). Situação: **APROVADO**, código de saída 0.

| Conjunto | Casos | Linhas esperadas | Encontradas | Inteiramente corretas | Extras | Ausentes | Duplicadas | Ambíguas |
|---|---|---|---|---|---|---|---|---|
| Desenvolvimento | 7 | 63 | 63 | 63 | 0 | 0 | 0 | 0 |
| Validação cega | 3 | 36 | 36 | 36 | 0 | 0 | 0 | 0 |

Precisão por campo (acertos/total), somando os dois conjuntos: processo 99/99; matrícula 99/99; nome 99/99;
cargo 99/99; evolução anterior 85/85; evolução posterior 85/85. São os mesmos números da 05.3.3: o corpus já
estava inteiro correto, e esta etapa não o piorou. Ele mede 10 atos de Progressão; não mede Tempo de Serviço,
portarias nem os casos de ambiguidade.

Casos não avaliados: nenhum caso do manifesto ficou sem avaliação.

## 10. Comparação com a etapa anterior

### 10.1 Leitura, página a página (11 edições oficiais, 532 páginas)

| Medida | Base `5442344` (leitor 0.6) | Esta branch (leitor 0.7) |
|---|---|---|
| Páginas OK / baixa confiança / inconsistente | 529 / 2 / 1 | 529 / 2 / 1 |
| Páginas pendentes | 3 | 3 (as mesmas) |
| Método TEXTO / TEXTO+OCR / OCR | 501 / 13 / 18 | 470 / 44 / 18 |
| Tempo de leitura das 11 edições (2 processos) | 249 s | 241 s |
| Fontes apontadas como suspeitas | — | 0 |
| Páginas com linhas de tabela reconstruídas | — | 84 |
| Fragmentos juntados à sua linha de tabela | — | 1.758 |
| Fragmentos sem atribuição segura (marcados) | — | 49 |
| Linhas de tabela larga que deixaram de ser partidas | — | 33 |

As 31 páginas que passaram de TEXTO para TEXTO+OCR ganharam o texto de imagens pequenas (faixas e anúncios com
texto), todas com confiança entre 89 e 96; nenhuma mudou de qualidade. Nenhum dos 49 fragmentos marcados fica
dentro de um ato da GEDIV (nenhuma decisão recebeu a pendência correspondente): estão em tabelas de outros órgãos.

### 10.2 Classificação, edições de novembro contra a base de referência da Etapa 04

Seis edições (05, 06, 07, 10, 11 e 12/11/2026), comparadas coluna a coluna.

| Medida | Resultado |
|---|---|
| Códigos de saída | 0, 3, 0, 3, 0, 0 — os esperados |
| Atos | 23 e 23; nenhum a mais, nenhum a menos |
| Decisões | 156 e 156; nenhuma extra, ausente ou duplicada |
| Processo, matrícula, nome, lotação, cargo, resultado | idênticos nas 156 |
| Eixo, modalidade, condição, grupo, assunto, vínculo, páginas dos atos | idênticos nos 23 |
| Eventos, "Outras publicações", fora do escopo | idênticos |
| Detalhe das decisões | 26 decisões perderam a observação "nome e cargo podem continuar na linha seguinte" |
| Pendências dos atos | 1 ato (576/2026) teve a pendência de continuidade reescrita com o motivo |

As 26 decisões são linhas que antes chegavam ao classificador em duas linhas físicas e eram recompostas por uma
lista de palavras; agora chegam inteiras, pela geometria, com o mesmo nome e o mesmo cargo. Nada novo apareceu
para reclassificar nessas edições; por isso o mecanismo de conflito da 05.3.3 não foi acionado por dados reais.

### 10.3 Contagens nas 11 edições (classificação sobre a leitura 0.7)

| Tema | Contagem |
|---|---|
| Atos / decisões / eventos | 32 / 207 / 1 |
| Decisões deferidas / indeferidas / sem resultado | 188 / 19 / 0 |
| Decisões sem processo reconhecido | 0 |
| Decisões com resultado vindo de título de bloco | 0 |
| Atos que atravessam página | 1 (continuidade duvidosa: 1) |
| Tempo de Serviço por assunto | TS-01 1, TS-02 1, TS-03 2, TS-04 1, TS-05 6; sem assunto 0 |
| Progressão por grupo | GAJ 5, SSA 3, AST 2, GPC 2, FAP 1, MAG 1, SFT 1; sem grupo 6 (5 por `TEC. ADM`/`STF`, 1 sem expressão) |
| Atos com dois grupos | 0 |
| Portarias em "Outras publicações" | 0 (a única portaria relacionada é uma alteração e continua evento) |

### 10.4 Achados da própria regressão, corrigidos antes da publicação

A regressão com os PDFs oficiais reprovou quatro versões intermediárias desta etapa. Ficam registrados porque
mostram onde o algoritmo é sensível:

1. Cabeçalho da resenha seguinte e "Publique-se" absorvidos como fragmentos da última linha da tabela: três atos e
   três registros de exclusão sumiram. Correção: linha que recomeça na margem encerra a tabela; folga vertical.
2. Réguas que só contornavam a tabela fundiram todas as linhas numa só (resenha 583, 11/11). Correção: a grade só
   vale se separar as linhas.
3. Duas palavras justificadas letra a letra viraram uma ao serem juntadas (resenha 569, 05/11). Correção: cada
   pedaço é reunido antes da junção.
4. Faixa de anúncio com logotipo deixou a página 55 de 12/11 em baixa confiança, e a edição, pendente. Correção:
   em figura com pouco texto ficam só as palavras confiáveis.
5. Subconjunto de fonte só com a ligadura "ﬁ" foi apontado como fonte suspeita em quatro páginas. Correção:
   ligaduras são decompostas antes do julgamento; teste novo.

Nenhuma dessas correções usa número de resenha, de página ou de edição: são regras gerais, cobertas por testes
sintéticos.

## 11. Riscos residuais

- **Tabela com poucas linhas completas.** A reconstrução exige três linhas com três ou mais células. Numa tabela
  em que todas as linhas têm células quebradas e centradas, nenhuma linha física é completa e o trecho não é
  reconhecido: o texto sai como na versão anterior, sem marca de ambiguidade.
- **Título centrado logo abaixo da tabela**, dentro de uma coluna e a menos de 1,35 entrelinha: pode ser juntado
  à última linha. As linhas que recomeçam na margem estão protegidas; esta não.
- **Limiares calibrados com 11 edições.** Vogais, sinais, área de imagem, traços por linha e folgas verticais
  foram escolhidos para não alterar nenhuma dessas edições além do previsto. Outras diagramações podem pedir
  ajuste.
- **Linha não lida em página de duas colunas**: a conferência é por segmento horizontal de tinta; duas colunas
  separadas por menos de 3% da largura da imagem são vistas como um segmento só.
- **Linha sem processo dentro do preâmbulo de um ato sem nenhum processo**: se o preâmbulo tiver uma linha que
  começa por matrícula e nome, ela vira decisão sem processo. Fica pendente de revisão, mas é um extra.

## 12. Limitações

- Texto desenhado como **contorno vetorial** (sem caracteres e sem imagem) não é detectado como região sem texto.
- Sem Tesseract, imagens abaixo de 25% da página continuam sem exame, como antes; a página não é marcada.
- A marca de ambiguidade fica no texto da página. É visível para quem lê o texto extraído; não tem tela própria.
- A conferência de linhas não lidas vale para páginas inteiras por OCR, não para os trechos relidos dentro de
  uma página nativa.
- Os PDFs oficiais não trouxeram nenhum exemplo de: fonte com mapeamento errado sem `(cid:N)`, cabeçalho de
  resenha repetido, linha repetida entre páginas, resenha mista com títulos de bloco, dois grupos no mesmo ato,
  TS-04 ou TS-06 sem o requisito. Esses caminhos estão provados só com dados sintéticos.
- Nenhuma validação independente (outra pessoa conferindo no PDF) foi feita nesta etapa.

## 13. Pendências de homologação GEDIV

1. `TEC. ADM` corresponde a `AST`? Continua sem grupo.
2. `STF` corresponde a `SFT`? Continua sem grupo.
3. Ato com dois grupos do PCCR: deve ser contado nos dois, em nenhum, ou dividido por linha?
4. "Desistência de licença" sem dizer qual licença, e "conversão de licença especial" sem dizer em quê: têm
   assunto próprio ou ficam fora das sete subcategorias?
5. Decisão publicada sem número de processo: entra nos indicadores depois de revisada?
6. Portaria com assunto de progressão ou de tempo de serviço: basta constar em "Outras publicações"?
7. Denominação e expressões do grupo `INT` (pendência anterior, mantida).

## 14. Próxima etapa

Etapa 05.3.5 — Homologação Geral. Pontos que esta etapa deixa para ela:

- Conferir no PDF, por pessoa da gerência, uma amostra das linhas reconstruídas pela geometria.
- Decidir os sete itens da seção 13.
- Obter exemplos reais dos casos que só têm prova sintética (seção 12) ou registrar que não ocorrem.
- Reler o acervo com o leitor 0.7 num ambiente de homologação e tratar os conflitos que aparecerem.

A operação diária (Etapa 06) continua não autorizada.
