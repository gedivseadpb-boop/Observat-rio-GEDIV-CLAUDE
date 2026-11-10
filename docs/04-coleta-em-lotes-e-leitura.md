# Coleta em lotes e início da leitura de PDFs

Data: 10/11/2026.

## 1. Avaliação da estratégia em lotes

| Pergunta | Resposta |
|---|---|
| Resolve o bloqueio de conexão? | **Não.** O bloqueio medido ocorre antes de qualquer requisição (a conexão não se estabelece). Baixar pouco ou muito não muda isso. |
| Melhora o desempenho? | **Não; é um pouco mais lento**, de propósito. O volume é pequeno e o tempo não é o problema (ver estimativa abaixo). |
| Melhora a confiabilidade? | **Sim.** Cada item é gravado ao terminar; uma queda perde no máximo o download em curso. |
| Melhora a segurança da operação? | **Sim.** Um problema aparece em 5 ou 10 arquivos, não em 200; o lote para sozinho diante de recusa da fonte. |
| Melhora a rastreabilidade? | **Sim.** Cada lote e cada item ficam no banco com resultado, tamanho, SHA-256, duração e erro. |
| Reduz a carga sobre os portais? | **Sim.** Uma requisição por vez, com pausa. |

**Estimativa de volume (não medida nas fontes):** a numeração das edições observada no índice
de busca vai de 18.561 (01/04/2026) a 18.693 (15/10/2026), cerca de 20 edições por mês.
De janeiro a novembro isso sugere algo em torno de 220 edições, mais suplementos. Com lotes
de 10 e pausa de 8 s, a carga inteira caberia em cerca de 25 lotes, poucas horas de execução
distribuídas como se quiser. O número real só será conhecido depois da descoberta nas fontes.

## 2. Parâmetros iniciais e critérios de ajuste

| Parâmetro | Piloto | Histórico | Onde se altera |
|---|---|---|---|
| Publicações por lote | 5 (máximo) | 10 (máximo) | `--tamanho` |
| Pausa entre downloads | 10 s | 8 s | `--pausa` |
| Pausa entre lotes | — | 120 s | `--pausa-entre-lotes` |
| Lotes por execução | 1 | 1 (padrão) | `--lotes` |
| Requisições simultâneas | 1 | 1 | fixo |
| Tentativas por requisição | 3, com espera crescente | 3 | código (`Politica`) |
| Falhas seguidas que encerram o lote | 2 | 3 | código (`Parametros`) |
| Tentativas por publicação (todos os lotes) | 5 | 5 | código (`Parametros`) |
| Tempo limite por requisição | 30 s | 30 s | código (`Politica`) |
| Tamanho máximo do arquivo | 80 MB | 80 MB | código (`Politica`) |

Critérios de ajuste, a aplicar somente com base nos registros dos lotes reais:

| Observação nos lotes | Ajuste |
|---|---|
| Três lotes seguidos concluídos sem nenhuma falha | Pode-se executar mais lotes por execução (`--lotes`). O tamanho permanece 10. |
| Tempo esgotado em downloads que depois funcionam | Aumentar o tempo limite; verificar o tamanho dos arquivos. |
| Qualquer resposta 429 ou 403 | Parar. Dobrar as pausas e só retomar no dia seguinte; se repetir, tratar institucionalmente. |
| Página de verificação no lugar do PDF | Parar. Não há ajuste de parâmetro que resolva; exige liberação da fonte. |
| Arquivos acima de 80 MB recusados | Conferir manualmente o arquivo e elevar o limite. |
| Duração média por arquivo muito abaixo da pausa | A pausa pode ser reduzida, nunca abaixo de 3 s. |

## 3. Como o progresso é registrado

Tudo fica no banco SQLite local (`dados/observatorio.sqlite3`):

| Tabela | Conteúdo |
|---|---|
| `varredura` | Para cada fonte e mês: se a listagem foi lida, quantos itens, ou o erro. |
| `publicacao` | Cada endereço oferecido por uma fonte: data, tipo (normal, suplemento, extra), ordem, estado, tentativas, último erro. |
| `arquivo` | Cada PDF distinto, pelo SHA-256. |
| `versao` | Todos os conteúdos já observados em cada endereço (republicações preservadas). |
| `lote` | Cada lote: fonte, tipo, parâmetros, início, fim, estado, aprovação (piloto). |
| `lote_item` | Cada publicação tratada em um lote: resultado, SHA-256, tamanho, duração, erro. |

Resultados possíveis de um item: `NOVO`, `DUPLICADO` (conteúdo já presente no acervo por
outra publicação, por exemplo o mesmo arquivo na outra fonte), `IGUAL`, `ALTERADO`,
`FALHA_DOWNLOAD`, `INVALIDA`.

Estados de um lote: `CONCLUIDO`, `INTERROMPIDO_POR_FALHAS`, `INTERROMPIDO_RECUSA_DA_FONTE`,
`INTERROMPIDO_PROTECAO_DA_FONTE`, `INTERROMPIDO_PELO_OPERADOR`, `INTERROMPIDO_EXECUCAO`
(o programa caiu; detectado na execução seguinte).

O comando `progresso` mostra, por mês e por fonte: listadas, verificadas, duplicadas,
pendentes, falhas, inválidas e suplementos.

## 4. Salvaguardas

- **Trava da carga histórica:** o comando `lote` é recusado enquanto não houver um piloto
  aprovado em cada fonte oficial (A União e CGE). O piloto só é aprovado com pelo menos
  três edições de datas diferentes, todas baixadas e verificadas.
- **Sem insistência:** falhas seguidas encerram o lote; 403, 429 ou página de verificação
  encerram na primeira ocorrência.
- **Sem contorno de proteção:** o sistema não simula navegador, não troca de identidade e
  não usa intermediários. Identifica-se com nome e endereço do projeto.
- **robots.txt:** consultado antes de cada lote; havendo proibição, o lote não roda.
- **Uma conexão por vez.**
- **Processos separados:** descobrir, baixar, ler e (futuramente) classificar são comandos
  distintos, cada um com seu próprio registro de andamento.

## 5. O que está implementado, simulado e validado

| Funcionalidade | Implementada | Testada com simulação | Validada com as fontes reais |
|---|---|---|---|
| Descoberta mensal retomável | Sim | Sim | **Não** |
| Lote piloto (até 5 datas diferentes) | Sim | Sim | **Não** |
| Trava da carga histórica | Sim | Sim | Não se aplica |
| Lotes históricos por mês, em ordem | Sim | Sim | **Não** |
| Pausas configuráveis | Sim | Sim | **Não** |
| Registro por item e por lote | Sim | Sim | **Não** |
| Retomada após queda ou interrupção | Sim | Sim | **Não** |
| Duplicidade entre fontes (SHA-256) | Sim | Sim | **Não** (não se sabe se os arquivos das duas fontes são idênticos) |
| Parada diante de recusa ou proteção | Sim | Sim | **Não** |
| Atualização de banco antigo (versão 1 → 2) | Sim | Sim | Não se aplica |
| Leitura por colunas | Sim | Sim (PDF sintético) | **Não** (nenhum DOE real foi lido) |
| Número e data da edição pelo cabeçalho | Sim | Sim (texto de cabeçalhos reais obtido por índice de busca) | **Não** (não lido de um PDF real) |
| Detecção de página sem texto | Sim | Sim | **Não** |
| OCR das páginas sem texto | **Não** | — | — |
| Acesso automatizado às fontes | — | — | **Não comprovado** (três medições, todas com falha de conexão a partir dos EUA) |

"Simulação" significa servidor HTTP local e PDFs sintéticos, sem conteúdo real.

### Testes executados

Comando: `python -m unittest discover -s tests -t .` — 61 testes.

| Arquivo | Testes | O que verifica |
|---|---|---|
| `tests/test_nucleo.py` | 14 | PDF, acervo, banco, rede |
| `tests/test_coleta.py` | 19 | Listagens, coleta, inventário, importação manual |
| `tests/test_lotes.py` | 16 | Piloto, trava, lotes, retomada, recusa, migração do banco |
| `tests/test_leitura.py` | 12 | Colunas, cabeçalho, página sem texto, retomada da leitura |

Os resultados por ambiente (desenvolvimento e GitHub Actions) estão registrados no fim
deste documento.

## 6. Leitura de PDFs — estado atual

- Lê a posição de cada palavra, encontra o corredor entre colunas e reconstrói o texto
  coluna por coluna. Linhas que atravessam a página (cabeçalhos, títulos de órgão)
  delimitam faixas, para que um ato não seja emendado com o da coluna vizinha.
- Extrai número e data da edição do cabeçalho da primeira página.
- Marca páginas sem texto para OCR posterior.
- Processo próprio: `python -m observatorio.leitura processar`. Lê o que estiver no acervo,
  inclusive PDFs importados manualmente, e não depende dos downloads automáticos.
- O texto das páginas fica apenas no banco local.

Observação obtida do texto indexado de edições reais: a palavra "Oficial" aparece como
"Ofi cial" (efeito da ligadura tipográfica "fi"). A leitura do cabeçalho já tolera isso;
a busca de termos nas etapas seguintes terá de tratar o mesmo efeito em todo o texto.

Limites conhecidos, a medir com edições reais: tabelas largas, páginas com três colunas,
anexos em paisagem e colunas de larguras desiguais.

## 7. Próximas ações para iniciar a coleta histórica

1. **Responsável:** executar a sonda em rede brasileira e enviar o `sonda.json`
   (instruções no README).
2. Conforme o resultado:
   - acesso normal → `descobrir`, depois `piloto` em cada fonte, na mesma máquina;
   - página de verificação ou conexão recusada → pedido institucional de liberação à
     A União/CODATA e à CGE; enquanto isso, importação manual.
3. Com os dois pilotos aprovados: conferir manualmente os PDFs do piloto (abrem? são as
   edições certas?), comparar o mesmo dia nas duas fontes e só então liberar lotes de 10.
4. Em paralelo: importar manualmente algumas edições reais para validar a leitura por
   colunas e ajustar seus parâmetros.
