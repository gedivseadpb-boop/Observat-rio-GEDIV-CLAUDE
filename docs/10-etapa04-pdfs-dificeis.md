# Etapa 04 — PDFs difíceis do DOE-PB: diagramação, OCR por região e medição por campo

Datas: 12–13/11/2026. Base: branch `etapa03/pr02-leitura-ouro` (`b225289`). Regime: análise e protótipo não
destrutivo, em cópia isolada. Este documento não contém nomes, matrículas nem números de processo.

## 1. Material estudado

| Item | Detalhe |
|---|---|
| Edições | 11 edições oficiais, 532 páginas: 01, 02, 03 e 06/10 e 04, 05, 06, 07, 10, 11 e 12/11/2026. A edição de 12/11 é o arquivo `-portal-1` da listagem. |
| Fonte | `auniao.pb.gov.br`, download automático a partir de um ambiente de nuvem (não GitHub Actions) |
| Integridade | SHA-256 de todos os arquivos (`docs/validacao/`) |
| Achado de transferência | O primeiro download de 07/11 voltou **HTTP 200 com o arquivo truncado** (1.446.670 de 2.449.072 bytes). A verificação estrutural do projeto recusou o arquivo (`SEM_FIM_DE_ARQUIVO`) e o novo download veio íntegro. Houve também 3 quedas de conexão em 10 tentativas. |

## 2. Corpus de casos reais

O manifesto público é `docs/validacao/corpus_pdfs_dificeis.json`: arquivo, SHA-256, página do PDF, página
impressa, dificuldades e o esperado sem dados pessoais. Em todas as páginas do corpus, a página impressa
coincide com o índice do PDF.

Os valores por campo ficam num **arquivo privado** fora do repositório. Cada linha foi conferida contra a
imagem renderizada da página.

**Conjunto de desenvolvimento:** usado para criar as correções.

| Caso | Edição / página | Linhas | Dificuldade principal |
|---|---|---|---|
| Resenha 579 | 07/11 p. 7 | 20 | Tabela inteira em fonte sem mapeamento (`cid`); grade grossa; ofício com hífen; "NÍVEL n" |
| Resenha 575 | 07/11 p. 6 | 16 | Corpo pequeno (palavras coladas); salto II → V publicado |
| Resenha 576 | 11/11 p. 5 → 6 | 1 | Cabeçalho no pé da última coluna da p. 5; tabela no topo da p. 6 |
| Resenha 564 | 05/11 p. 5 | 21 | Caractere sobreposto (correção impressa por cima); saltos A→C…A→F publicados |
| Resenha 549 | 06/11 p. 5 | 1 | Resenha inteira em `cid`; ruído de OCR no cabeçalho |
| Resenha 531 | 12/11 p. 5 | 4 | Indeferimento sem classe/nível |
| Portaria 8/2026 | 10/11 p. 2 | — | "Tornado sem efeito" de ato publicado em 1999 |

**Conjunto de validação cega:** medido **antes** de ser olhado no desenvolvimento.

| Caso | Edição / página | Linhas |
|---|---|---|
| Resenha 580 | 07/11 p. 7 (GPC) | 22 |
| Resenha 550 | 07/11 p. 7 (MAG) | 9 |
| Resenha 584 | 11/11 p. 6 (GAJ, salto III → VII publicado) | 5 |

## 3. Casos reais encontrados e tratamento

| # | Caso real | Causa medida | Tratamento | Situação |
|---|---|---|---|---|
| 1 | GPC 579/580 com 0 decisões | Tabela em fonte sem mapeamento; o OCR do bloco inteiro lia só 2 de 6 colunas por causa das linhas grossas da grade | **OCR de tabela guiado pela grade vetorial** (`leitura/tabela_ocr.py`): bordas das células tiradas do próprio PDF; OCR coluna a coluna por dentro das bordas; uma linha de texto por linha da tabela | 42 decisões recuperadas |
| 2 | Ofício no formato "SDS-OFI-AAAA-NNNNN" | Padrão aceitava só "/" antes do número | Aceita "/" ou "-", guardado como publicado; o mesmo ofício em várias linhas gera decisões distintas | Implementado |
| 3 | Nível "NÍVEL 3" | Só algarismos romanos eram reconhecidos | "NÍVEL n" reconhecido; "NÍVEL3" (OCR sem espaço) gravado como "NIVEL 3" | Implementado |
| 4 | Nomes colados ("…YANDRADE") em tabelas de 4–5,5 pt | Vão entre palavras de 0,87–1,13 pt (≈ 20% do corpo); a tolerância fixa de 1,5 pt colava | **Tolerância proporcional ao corpo da letra (0,15)** | Implementado. Em 513 páginas: 17 melhores que 1,5 pt, nenhuma pior. |
| 5 | Classe perdida na linha 10 da 564 | Camada de texto "A" e, no mesmo ponto, glifo "D" em fonte sem mapeamento (correção impressa por cima) | Palavra com caracteres sobrepostos de fontes diferentes é relida por OCR do próprio recorte; vale o que está **impresso visível**; página marcada `TEXTO+OCR` | Implementado |
| 6 | Saltos A→E, A→F, II→V, III→VII | Publicados assim (conferido na imagem) | **Nunca corrigidos**: valor como publicado + observação (salto, sem avanço, fora da faixa) | Implementado |
| 7 | Classe × nível | Risco de gravar nível como classe ou vice-versa | Vertical aceita só letras; horizontal, romanos ou "NÍVEL n"; formato trocado vai para `evolucao_lida` com observação, sem conversão | Implementado |
| 8 | "Sem efeito" de ato de 1999 | Sem resenha citada; original fora da base | A data da publicação citada ("publicado no D.O.E. … 28/07/1999") e o processo antigo ficam no evento (esquema 6). O vínculo continua pendente, com o motivo registrado (anterior a 01/01/2026). | Implementado |
| 9 | Resenha entre páginas (576) | Cabeçalho na p. 5, tabela na p. 6 | Fluxo linear de linhas (já existente) | Conferido no documento real: 6/6 campos corretos |
| 10 | Grades de diagramação | Molduras de página e de coluna também são "tabelas" | Salvaguardas: menor tabela que contém o bloco; busca numa faixa horizontal; área ≤ 1,3 × área ilegível (incluindo o cabeçalho das colunas); ≥ 80% das células de dados ilegíveis | Implementado. Em 02/10, 05/11 e 06/11, recusou as grades; em 07/11, aceitou as tabelas. |
| 11 | Abono de permanência (559, 572, 527 de 06/11) | Não é uma das 7 categorias | Fora dos eixos, como manda a regra | Decisão da GEDIV |
| 12 | "profissionais de Educação" (570) | Grupo não expresso por sigla | Sem grupo, com pendência | Decisão da GEDIV (MAG?) |
| 13 | Assinatura | Imagem e cargo após o "PUBLIQUE-SE", fechando o bloco DEREH inteiro, não cada resenha | Não associada às resenhas (seria atribuição errada) | Registrado |

## 4. Comparação de motores (integridade de linha, 63 linhas conferidas, 6 páginas)

Critério: a linha da tabela sai inteira e na ordem numa mesma linha de texto (processo/documento,
matrícula, nome, classe/nível).

| Motor | Linhas inteiras | Tempo |
|---|---|---|
| pdfplumber `extract_text()` padrão | 65,1% | 0,84 s/página |
| PyMuPDF `get_text()` | 0,0% | 0,30 s/página |
| PyMuPDF `get_text(sort=True)` | 65,1% | 0,08 s/página |
| PyMuPDF `find_tables()` | 39,7% | 1,15 s/página |
| pypdfium2 `get_text_range()` | 65,1% | 0,02 s/página |
| Tesseract, página inteira (300 ppp) | 7,9% | 8,46 s/página |
| Pipeline PR-02 (leitor 0.4) | 66,7% | — |
| **Pipeline Etapa 04 (leitor 0.6)** | **98,4%** | 17 s/edição em média |

Nenhuma biblioteca, sozinha, recupera as tabelas em fonte sem mapeamento nem os caracteres sobrepostos. O
ganho vem do algoritmo: colunas e faixas, OCR por região guiado pela grade, tolerância proporcional. A única
linha que não sai numa só linha de texto é a da 576, porque o nome quebra dentro da célula; o classificador a
reúne, e os campos estão corretos.

**Licenças.**

| Biblioteca | Licença |
|---|---|
| PyMuPDF | AGPL-3.0 ou licença comercial da Artifex. Com AGPL, oferecer o painel pela rede obriga a disponibilizar o código-fonte do programa combinado sob licença compatível. |
| pdfplumber e pdfminer.six | MIT |
| pypdfium2 | Apache-2.0 / BSD-3 |
| Tesseract | Apache-2.0 |

Não há ganho medido que justifique adotar PyMuPDF: `sort=True` empata com pdfplumber e pypdfium2 na
integridade de linha. Mantém-se a decisão da Etapa 02. Isto é uma avaliação técnica, não parecer jurídico.

## 5. Medição por campo

Campos: processo, matrícula, nome, cargo, classe/nível anterior e posterior.

| Conjunto | Antes (PR-02) | Depois (Etapa 04) |
|---|---|---|
| Desenvolvimento (63 linhas, 368 campos) | 243/368 = **66,0%**; 43/63 linhas encontradas | 368/368 = 100% (**não independente**: as correções foram feitas sobre estes casos) |
| Validação cega (36 linhas, 198 campos), **1ª passagem** | — | estrito **176/198 = 88,9%**; só o valor **196/198 = 99,0%** |
| Validação cega, após as 2 correções que ela revelou | — | 198/198 = 100% (deixa de ser cega) |

Os dois defeitos revelados pela validação cega foram:

- o cargo "Necrotomista" estava ausente do vocabulário, e o nome absorvia o cargo;
- "NÍVEL3" sem espaço, com o valor correto mas a grafia diferente.

A fronteira entre nome e cargo continua dependente de um vocabulário de cargos: limite conhecido (§7).

**Conjunto-ouro** (01, 02, 03, 06/10 e 04/11): **5/5 confere** após todas as mudanças. Ele também detectou
uma regressão durante o desenvolvimento: uma grade de diagramação em 02/10 apagou resenhas legíveis. Isso
motivou as salvaguardas do item 10.

**Taxa de falha e desempenho** (11 edições, 532 páginas):

| Medida | Resultado |
|---|---|
| Método de leitura | 501 páginas por texto nativo, 13 por texto + OCR de região, 18 por OCR de página |
| Qualidade | 529 OK, 2 de baixa confiança, 1 inconsistente |
| Erros de leitura de arquivo | 0 |
| Tempo por edição | 10,9 a 31,6 s (média 17,0) |
| Pico de memória | 161 a 289 MB por edição |

## 6. Testes

- `tests/test_pdfs_dificeis.py`: 15 testes com PDFs e textos sintéticos (OCR de tabela pela grade e as
  salvaguardas, tolerância proporcional, sobreposição, ofício com hífen, classe × nível, saltos, eventos,
  migração v5 → v6, comparação por campo e manifesto sem dados pessoais) + 1 teste real, que só roda com
  `GEDIV_PDFS_OURO` e `GEDIV_CORPUS_PRIVADO`.
- Suíte completa: **205 testes**; aprovados com os PDFs oficiais e o esperado privado.
- Medição: `python -m observatorio.operacao corpus --pdfs PASTA --esperado-privado ARQUIVO.json`.
- Evidências sem dados pessoais: `docs/evidencias/etapa04/`.

## 7. Limites e pendências

1. **Limiares calibrados com poucos casos:** área da tabela 1,3×, células ilegíveis 80%, tolerância 0,15.
   Rever com mais edições.
2. A fronteira **nome/cargo** depende do vocabulário de cargos. Melhoria possível: usar as bordas das células
   também em tabelas nativas com grade.
3. **Dígitos lidos por OCR:** a matrícula tem dígito verificador, cujo algoritmo é desconhecido. Validá-lo
   reduziria o risco de erro de OCR (pendência com a SEAD).
4. Resenha que continua na página seguinte **sem** repetir o cabeçalho de tabela: há 1 caso real, que
   funcionou; mais casos são necessários.
5. A página "INCONSISTENTE" de 10/11 e as 2 de "BAIXA_CONFIANCA" não têm atos GEDIV. O motivo foi registrado,
   sem tratamento.
6. **Decisões da GEDIV:** abono de permanência fora dos eixos; "profissionais de Educação" = MAG?; TEC. ADM =
   AST?; regra para ato só com DEREH.
7. A aprovação continua **manual**. Nada desta etapa altera indicadores.
