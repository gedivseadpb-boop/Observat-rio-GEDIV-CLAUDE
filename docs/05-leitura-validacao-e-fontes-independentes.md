# Leitura de PDFs, validação e fontes independentes

Data: 10/11/2026. Projeto: **Painel de Publicações DOE-PB GEDIV**.

## 1. Quatro níveis de comprovação

Este documento usa sempre os mesmos quatro termos:

| Nível | Significado |
|---|---|
| **Código** | A funcionalidade está escrita. |
| **Teste automatizado** | Passa em testes com servidor local e documentos **sintéticos**. Comprova a lógica, não o comportamento com o Diário real. |
| **Validação com documento oficial** | Executada sobre PDFs reais do DOE e conferida. |
| **Operação efetiva** | Em uso contínuo, com dados reais. |

Situação em 10/11/2026: **nada passou do segundo nível.** Nenhum PDF oficial foi baixado,
importado ou lido por este sistema até aqui.

## 2. Correções desta entrega

### 2.1 Validação independente por fonte

Antes: a carga histórica exigia piloto aprovado na A União **e** na CGE.
Agora: cada fonte tem piloto, situação e liberação próprios.

| Situação da fonte | Significado | Carga histórica |
|---|---|---|
| `NAO_TESTADA` | Nenhuma listagem lida, nenhum lote | Bloqueada |
| `INACESSIVEL` | Todas as listagens tentadas falharam | Bloqueada |
| `ACESSIVEL` | Listagem lida, sem piloto aprovado | Bloqueada |
| `PILOTO_REPROVADO` | Último piloto não aprovado | Bloqueada |
| `VALIDADA` | Piloto aprovado nesta fonte | **Liberada para esta fonte** |
| `SUSPENSA` | Último lote encerrado por recusa (403, 429) ou proteção da fonte | Bloqueada até novo piloto aprovado |

A situação `SUSPENSA` é nova: depois de uma recusa, o sistema não volta a tentar lotes
históricos por conta própria. Só um novo piloto aprovado reabre a fonte.

### 2.2 Cobertura sempre declarada com suas lacunas

Os comandos `progresso` e `inventario` passam a emitir um parecer de cobertura:

| Parecer | Quando |
|---|---|
| `SEM_COBERTURA_AUTOMATICA` | Nenhuma fonte validada e nenhum dia completo |
| `PARCIAL` | Alguma fonte não validada, ou algum dia não verificado, pendente ou parcial |
| `SEM_LACUNAS_CONHECIDAS` | Todas as fontes validadas e nenhum dia com lacuna |

O sistema **nunca** declara o acervo "completo". O parecer lista as fontes não validadas,
os dias com lacuna e os dias cobertos por uma única fonte (nos quais não há conferência cruzada).

### 2.3 Importação manual no mesmo fluxo

Um PDF fornecido manualmente passa por: verificação estrutural → SHA-256 → acervo →
registro com origem `manual` → leitura → relatório de validação. É o mesmo caminho dos
arquivos baixados; a leitura não distingue a origem. Novidades:

- `importar PASTA` importa todos os PDFs de uma pasta; a data vem do nome do arquivo
  (formato `DD-MM-AAAA`, como nos arquivos oficiais).
- Arquivo sem data no nome, ou que não seja PDF íntegro, é recusado com o motivo.
- Se a data lida no cabeçalho do documento divergir da data informada, a leitura registra
  a inconsistência.

### 2.4 Leitura — Etapa 2

| Requisito | Como foi atendido |
|---|---|
| Colunas sem mistura de textos | Detecção do corredor entre colunas; linhas de largura total delimitam faixas. |
| Edição e data | Lidas do cabeçalho da primeira página; ausência é registrada como inconsistência. |
| Páginas | Contagem, método e quantidade de colunas por página. |
| Origem | Cada leitura é ligada ao arquivo (SHA-256) e este a todas as publicações que o ofereceram (fonte, endereço, data). |
| OCR em português | Tesseract, a 300 pontos por polegada, somente em páginas sem texto; o resultado também é reconstruído por colunas. |
| Páginas ilegíveis ou inconsistentes | Qualidade por página (tabela abaixo); o documento fica `LIDA_COM_PENDENCIAS`. |
| Integridade e rastreabilidade | SHA-256 do arquivo reconferido antes da leitura; SHA-256 do texto de cada página; contagem de palavras conservada na reordenação; gravação em transação única por arquivo. |

Qualidade da página:

| Valor | Critério |
|---|---|
| `OK` | Texto nativo íntegro, ou OCR com confiança média de 75 ou mais |
| `BAIXA_CONFIANCA` | OCR com confiança entre 50 e 75 |
| `ILEGIVEL` | OCR abaixo de 50, ou nenhuma palavra reconhecida em página com conteúdo gráfico |
| `INCONSISTENTE` | Texto nativo com caracteres corrompidos em proporção relevante |
| `OCR_INDISPONIVEL` | A página exige OCR e o Tesseract com português não está instalado |
| `VAZIA` | Sem texto e sem conteúdo gráfico |

Os limiares 75 e 50 são valores iniciais, escolhidos sem base em documentos reais. Devem
ser revistos na validação.

## 3. Testes executados

Comando: `python -m unittest discover -s tests -t .` — 71 testes.

| Arquivo | Testes | Assunto |
|---|---|---|
| `tests/test_nucleo.py` | 14 | PDF, acervo, banco, rede |
| `tests/test_coleta.py` | 19 | Listagens, coleta, inventário, importação |
| `tests/test_lotes.py` | 18 | Piloto, liberação por fonte, suspensão, retomada, migração |
| `tests/test_leitura.py` | 20 | Colunas, cabeçalho, OCR, qualidade, rastreabilidade, fluxo manual, nome do sistema |

Todos usam dados sintéticos. O teste de OCR usa uma página sintética transformada em
imagem, que é muito mais limpa do que uma digitalização real; a confiança obtida (acima de
90) não deve ser esperada em documentos reais.

Os resultados por ambiente estão no fim deste documento.

## 4. Validação com os PDFs de 02/10 e 04/11/2026 — preparada, não executada

Os dois arquivos não estavam disponíveis: não foram anexados e não puderam ser baixados.
A validação está pronta para ser executada assim que forem fornecidos.

Procedimento (na pasta do projeto, com os dois PDFs em uma pasta `entrada`):

```
python -m pip install -r requirements.txt
python -m observatorio.coleta importar entrada
python -m observatorio.leitura processar
python -m observatorio.leitura validar --saida validacao.json
```

O arquivo `validacao.json` não contém texto das publicações nem dados pessoais e pode ser
enviado para análise. Ele traz, por arquivo: SHA-256, tamanho, origem, edição e data
lidas, páginas por método, por colunas e por qualidade, inconsistências, comparação com
valores de referência e cobertura frente a uma leitura independente.

Valores de referência (`docs/validacao/referencias.json`), **registrados nos projetos
anteriores e ainda não verificados aqui**:

| Edição | Páginas | Tamanho | SHA-256 (início) |
|---|---|---|---|
| 02/10/2026 | 40 | 2.369.879 bytes | `0f437acc…` |
| 04/11/2026 | 60 | 2.202.466 bytes | `02cbb8ae…` |

Critérios para considerar a leitura validada nesses dois documentos:

1. SHA-256, tamanho e número de páginas coincidem com a referência (confirma que são os mesmos arquivos).
2. Número e data da edição lidos do cabeçalho coincidem com o impresso.
3. Nenhuma página `INCONSISTENTE` ou `ILEGIVEL` sem explicação.
4. Cobertura frente à leitura independente de 95% ou mais em todas as páginas de texto.
5. **Conferência humana** de pelo menos cinco páginas por edição, incluindo as que contêm
   resenhas da SEAD: `python -m observatorio.leitura pagina SHA256 NUMERO` mostra o texto
   na ordem lida, para comparar com o PDF aberto ao lado. Este item não pode ser automatizado.

O item 4 mede perda de texto, não a ordem das colunas. A ordem só é confirmada pelo item 5.

## 5. Limites conhecidos

- A estrutura real das páginas de listagem das fontes nunca foi lida; o extrator foi
  escrito a partir dos formatos de endereço observados em índice de busca.
- Páginas com três colunas, tabelas largas e anexos em paisagem não foram exercitados.
- No Windows, o teste de OCR é pulado na automação do GitHub (o Tesseract não é instalado
  lá); no Linux ele é executado.
- A palavra "Oficial" aparece como "Ofi cial" no texto de edições reais (ligadura "fi").
  O cabeçalho já tolera; as etapas de busca de termos precisarão tratar o mesmo efeito.

## 6. Pendências que dependem da responsável

1. **Fornecer os PDFs oficiais de 02/10 e 04/11/2026** (anexando aqui ou executando o
   procedimento da seção 4 e enviando o `validacao.json`). Sem documentos oficiais não há
   validação real da leitura.
2. **Executar a sonda em rede brasileira** e enviar o `sonda.json`, para definir se há
   caminho técnico para a coleta automática.
3. **Decisão institucional**, se a sonda mostrar recusa ou proteção: solicitar liberação
   de acesso à A União/CODATA e à CGE.
4. **Visibilidade do repositório** (hoje público), antes da etapa de classificação.
