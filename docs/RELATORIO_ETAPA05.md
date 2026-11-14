# Relatório da Etapa 05: coleta oficial e aquisição verificável de PDFs

**Projeto:** Painel Diário Oficial | GEDIV
**Data:** 14/11/2026
**Branch local:** `etapa05/coleta-oficial`. Commit de código `8d9c640`; base `etapa03/pr02-leitura-ouro` (`b225289`).
**Situação geral:** **BLOQUEADO PARA AUTOMAÇÃO.**
- O código está concluído e testado.
- O download real a partir da fonte oficial não pôde ser executado neste ambiente: a saída de rede da sandbox recusa o domínio.
- Nenhum outro ambiente foi testado sem autorização.

Sem push, merge, deploy, cron ou serviço externo ativado. Este relatório não contém dados pessoais.

---

## 0. Ponto de partida conferido por Git

| Item | Esperado pelo prompt | Encontrado em 14/11/2026 | Consequência |
|---|---|---|---|
| `main` | `278abd6` | `278abd6` | Inalterada |
| PR #5 | `c49f9ec`, não mesclado | `c49f9ec`, não mesclado; está contido na base da Etapa 03 | — |
| Etapa 03 | `etapa03/pr01…` e `pr02…` | `1fc2469` e `b225289` (PR01 ⊂ PR02) | **Base usada: `b225289`** |
| Etapa 04 | `etapa04/pdfs-dificeis` @ `7ee3933` | **Ausente** do GitHub; nenhum bundle ou patch anexado, nem nos documentos do Projeto | **BLOQUEIO 1.** As melhorias de OCR da Etapa 04 **não estão integradas**. Os 205 testes dela não puderam ser rodados |

A Etapa 05 não altera o extrator, o classificador, o banco de leitura nem o painel. Quando a Etapa 04 for publicada, a junção deve ser simples: a Etapa 04 mexe em `observatorio/leitura/`, e esta etapa mexe em `observatorio/coleta/`, `nucleo/` e `operacao/`. A possibilidade de conflito em `tests/apoio.py` não foi verificada.

## 1. Diagnóstico do coletor existente (MANTER / ADAPTAR / CRIAR)

| Caminho | Decisão | Motivo |
|---|---|---|
| `observatorio/coleta/fontes.py` | ADAPTAR | O leitor de links já tolerava `/view`, `/@@download/file`, sufixo `-N` e paginação `b_start`. Acrescentado `url_recentes()` |
| `observatorio/coleta/coletor.py` | ADAPTAR | O núcleo de descoberta e de versões estava correto. Acrescentados: manifesto por tentativa, quarentena, `coletar_intervalo`, `descobrir_recentes`, simulação, filtro de período e validação de intervalo |
| `observatorio/coleta/lotes.py` | MANTER | Piloto e lotes históricos continuam iguais; herdam a nova verificação |
| `observatorio/coleta/inventario.py` | ADAPTAR | Motivo do `NAO_VERIFICADO`, estado `QUARENTENA`, manifesto de cobertura |
| `observatorio/coleta/transporte.py` | CRIAR | Contrato plugável de transporte |
| `observatorio/nucleo/rede.py` | ADAPTAR | Lista de servidores autorizados, redirecionamento manual e limite de tamanho mantidos. Acrescentados: truncamento, `Retry-After`, espera progressiva e `PROXY_RECUSOU` |
| `observatorio/nucleo/pdf.py` | ADAPTAR | `examinar()` mantido para leitura e importação; criado `verificar()` com várias checagens combinadas |
| `observatorio/nucleo/acervo.py` | ADAPTAR | Acrescentada a área de quarentena, fora do acervo |
| `observatorio/nucleo/banco.py` | ADAPTAR | Esquema v6 com as tabelas `download` e `verificacao_arquivo`, sem alterar tabelas antigas |
| `observatorio/sonda/` | MANTER | Diagnóstico por camada (DNS, TCP, TLS, HTTP) continua útil e independe de bibliotecas |
| `observatorio/operacao/aquisicao.py` | CRIAR | Sonda real de download, coleta e cobertura |
| `observatorio/operacao/__main__.py` | ADAPTAR | Comandos novos; os antigos foram preservados |

A aquisição de bytes continua separada da leitura e da classificação: um arquivo só chega à leitura depois de verificado e gravado no acervo.

## 2. Código implementado

Um único commit local: **`8d9c640`** (15 arquivos, cerca de 1.240 linhas acrescentadas). O que muda:

- **Integridade (`nucleo/pdf.verificar`)** — quatro checagens combinadas:
  1. assinatura `%PDF-` e detecção de HTML no lugar do PDF;
  2. bytes recebidos iguais ao `Content-Length`;
  3. `%%EOF` no fim e `startxref` apontando para uma `xref` ou um objeto dentro do arquivo;
  4. leitura da estrutura e contagem de páginas com o pypdf.

  Estrutura inconclusiva leva a `QUARENTENA`.
- **Rede:**
  - HTTP 200 com menos bytes que o anunciado, ou `IncompleteRead`, vira `TRUNCADO`, que é transitório e repetido;
  - espera progressiva `espera × 2^(n−1)` com teto de 60 s; um `Retry-After` maior prevalece até o teto;
  - 403 e 429 continuam sem repetição; o `Retry-After` do 429 fica registrado;
  - recusa do proxy do executor gera `PROXY_RECUSOU`, que não é atribuído à fonte;
  - a validação TLS é sempre a padrão; não existe opção para desativá-la.
- **Destinos autorizados:** só `https` e só os servidores da fonte, inclusive após redirecionamento. URLs com usuário, IPs internos e `file://` são recusados (há testes para isso). A função de download não serve como proxy genérico.
- **Manifesto de downloads (tabela `download`):** uma linha por tentativa, nunca reescrita. Campos:
  - URL pedida e URL final, redirecionamentos, transporte;
  - status HTTP, tipo de conteúdo, `Content-Length`, bytes recebidos;
  - SHA-256, páginas, integridade, alertas;
  - resultado, erro, versão do coletor (`coletor-etapa05-2026.11.14`), início em UTC, segundos e tentativas de rede.
- **Versões:** um mesmo endereço que passa a entregar outro conteúdo gera `ALTERADO`, e a versão anterior é mantida. Conteúdo idêntico em dois endereços gera `DUPLICADO`, gravado uma vez só.
- **Transporte plugável:**
  - `direto`;
  - `manifesto_contingencia`: arquivos obtidos por outro meio, com SHA-256 conferido e procedência registrada como contingência. Não é coleta automática;
  - relay: **não implementado**.

## 3. Comandos da linha de comando e exemplos executados

```bash
python -m observatorio.operacao sonda --fonte auniao [--saida sonda.json] [--hashes historico.json] [--guardar PASTA]
python -m observatorio.operacao coletar-dia --data 2026-11-07 [--dry-run] [--limite N] [--reverificar]
python -m observatorio.operacao coletar-intervalo --inicio 2026-11-04 --fim 2026-11-12 [--dry-run] [--limite N]
python -m observatorio.operacao cobertura --inicio 2026-01-01 --fim 2026-11-12 [--saida cobertura.json]
```

Códigos de saída: **0** concluído; **3** concluído com pendências; **4** fonte inacessível ou bloqueada; **2** erro de uso. Os comandos antigos (`python -m observatorio.coleta descobrir | piloto | lote | progresso | inventario | importar | conferir`) foram preservados.

Comandos executados de verdade neste ambiente em 14/11/2026, por volta de 15h44 UTC:

| Comando | Saída | Resultado |
|---|---|---|
| `sonda --fonte auniao` | 4 | `LISTAGEM_INACESSIVEL`, categoria `PROXY_RECUSOU` (`Tunnel connection failed: 403`) |
| `coletar-dia --data 2026-11-07 --dry-run` | 4 | robots `INACESSIVEL`; listagens recente e mensal com o mesmo erro; nada previsto |
| `coletar-intervalo --inicio 2026-01-01 --fim 2026-11-12` | 2 | Recusado: 316 dias excedem 31 (a carga histórica é da Etapa 06) |

## 4. Provas de download

| Prova | Situação | Evidência |
|---|---|---|
| Descoberta da URL oficial pela página `edicoes-recentes` | **PARCIAL** | A página foi lida por uma ferramenta de leitura web, que não é o código do coletor. Ela confirmou a estrutura: 12 itens por página, paginação `?b_start:int=12…996` (84 páginas), links `/servicos/doe/2026/novembro/diario-oficial-DD-MM-AAAA-portal.pdf/view`, um caso real de `-portal-1.pdf` (12/11/2026) e a edição mais recente de 14/11/2026. O leitor do coletor foi testado contra uma fixture com essa estrutura |
| Download direto de um PDF oficial pelo coletor | **BLOQUEADO** | A saída de rede da sandbox recusa `auniao.pb.gov.br` e `cge.pb.gov.br` no próprio proxy (403 no túnel), antes de chegar ao portal. **Nenhum PDF foi baixado nesta etapa.** Nenhuma tentativa de contorno foi feita |
| Edição inédita × já conhecida | **NÃO TESTADO** | Depende do download |
| SHA-256, páginas e integridade de um PDF real | **NÃO TESTADO** com PDF real; **CONCLUÍDO E TESTADO** com PDFs sintéticos | — |
| Idempotência | **CONCLUÍDO E TESTADO** com servidor local | Segunda coleta: zero downloads, zero linhas novas no manifesto e no acervo |

Nenhum PDF de conversa, Drive, fixture ou cache foi apresentado como download.

## 5. Matriz de ambientes

| Ambiente | Listagem | PDF inteiro | Situação | Observação |
|---|---|---|---|---|
| Sandbox de nuvem desta sessão (Linux, EUA) | Não | Não | **BLOQUEADO** | Recusa do proxy de saída da própria sandbox; não diz nada sobre o portal |
| Ferramenta de leitura web desta sessão | Sim (HTML convertido) | Não se aplica | **Não adequado à rotina** | Não entrega bytes nem usa o código do coletor; serviu só para conferir a estrutura da página |
| Executor padrão do GitHub Actions | — | — | **NÃO TESTADO** | Execução remota não autorizada. Há registro anterior (10/11) de conexão recusada na porta 443 |
| Cloudflare Workers / Google Apps Script | — | — | **NÃO TESTADO** | Exigiriam conta e autorização |
| Computador da usuária ou rede da SEAD (Brasil) | — | — | **NÃO TESTADO** | Candidato mais provável; ver o passo a passo na seção 11 |

O SQLite num executor efêmero **não** sobrevive entre execuções. O armazenamento persistente é uma decisão separada (Etapa 06).

## 6. Integridade e cobertura

**Caso do HTTP 200 truncado (07/11/2026).** Três camadas de proteção, todas testadas:
1. **Na rede:** bytes recebidos menores que o `Content-Length` geram `TRUNCADO`. A tentativa é repetida e nada entra no acervo. Teste: truncado na 1ª tentativa e completo na 2ª, sem corrupção.
2. **Sem `Content-Length`:** a falta de `%%EOF` ou de estrutura legível reprova o arquivo e o deixa para nova tentativa.
3. **Limitação conhecida:** se o arquivo tiver revisões incrementais e o corte ocorrer exatamente depois de um `%%EOF` intermediário, **sem** `Content-Length`, a cópia cortada pode parecer completa. Nesse caso fica registrado o alerta `SEM_CONTENT_LENGTH`. Com `Content-Length`, o corte é detectado (há teste).

**Estados de cobertura de um dia:**
- `COMPLETO`;
- `SEM_PUBLICACAO_LISTADA` (dia sem edição, com a listagem lida);
- `PENDENTE` (edição listada e ausente do acervo);
- `PARCIAL`;
- `QUARENTENA`;
- `BAIXADO_SEM_VARREDURA_COMPLETA`;
- `NAO_VERIFICADO`, com motivo `FONTE_INDISPONIVEL`, `LISTAGEM_PARCIAL` ou `NUNCA_LIDA`.

O manifesto de cobertura (`cobertura --saida`) lista as lacunas de forma explícita e a procedência de cada edição: URL oficial, data, tipo e ordem, SHA-256, bytes, páginas, integridade, versões, data da coleta, transporte e versão do coletor.

## 7. Resultados dos testes

| Momento | Testes | Resultado | Tempo |
|---|---|---|---|
| ANTES (base `b225289`) | 189 | OK (1 ignorado) | 41 s |
| Meio da implementação | 189 | 2 falhas e 3 erros, corrigidos (abaixo) | 41 s |
| DEPOIS (`8d9c640`) | **228** (189 + 39 novos) | **OK (1 ignorado)** | 59 s |

Ajustes em testes antigos, cada um com justificativa:
1. `tests/apoio.py`: `pdf_sintetico` agora gera um PDF estruturalmente válido (xref correta e páginas em branco), sem conteúdo real. Sem isso, a nova verificação estrutural mandaria para quarentena o arquivo que os testes usam como "PDF bom". O PDF ruim antigo virou `pdf_sem_paginas`, usado no único teste que precisa de um arquivo ilegível (`test_leitura.py`). **Nenhuma expectativa mudou.**
2. `test_regras_definitivas.py`: a versão do esquema passou a ser comparada com `B.VERSAO_ESQUEMA` em vez do número 5 fixo. O teste continua provando que o banco antigo é atualizado sem perda de dados.
3. **Expectativa preservada:** a primeira versão trocava `NAO_VERIFICADO` por um estado novo, o que quebraria o contrato já usado. Em vez disso, o estado foi mantido e o campo `motivo` foi acrescentado.
4. **Defeito real encontrado pelos testes novos e corrigido:** um 404 no endereço alternativo apagava a evidência de truncamento do endereço principal.

Testes novos (`tests/test_aquisicao.py`, 39) cobrem:
- a estrutura real da listagem;
- mudanças no HTML e página sem edições;
- várias edições na mesma data (`-1`), suplemento e republicação idêntica;
- ausência de edição e fonte indisponível;
- tempo esgotado, falha de conexão no meio do download, 403, 404, 429 com `Retry-After`, 500 e 503;
- HTML no lugar do PDF;
- redirecionamento para destino não autorizado; esquema, usuário na URL e IP interno;
- 200 truncado com e sem `Content-Length`;
- tamanho divergente, PDF inválido, PDF íntegro e quarentena;
- recuperação na execução seguinte sem corrupção;
- hash idêntico (`IGUAL`) e hash novo para o mesmo endereço (`ALTERADO`, 2 versões);
- deduplicação e processamento fora de ordem;
- simulação (`dry-run`), limite de downloads e tentativas esgotadas;
- validação de intervalo;
- procedência no manifesto;
- transporte de contingência;
- sonda em diretório vazio e sonda bloqueada;
- recusa de proxy;
- CGE sem listagem recente.

Fixture da listagem: `tests/fixtures/auniao_edicoes_recentes.html` é uma **reconstrução da estrutura** observada em 14/11/2026, **não uma cópia byte a byte** (o portal não é alcançável deste ambiente). Não contém dados pessoais.

Não executados: o conjunto-ouro (`operacao ouro`), que exige os PDFs oficiais e não estão nesta sandbox, e os 205 testes da Etapa 04, cujo código não está acessível.

## 8. Desempenho (sandbox Linux 6.18, Python 3.13.18, servidor local)

| PDF | Download local | Verificação estrutural | Pico de memória Python |
|---|---|---|---|
| 5 MB, 40 páginas | 0,01 s | 0,93 s (inclui o carregamento do pypdf) | 15,5 MB |
| 25 MB | 0,03 s | 0,04 s | 50,1 MB |
| 60 MB | 0,05 s | 0,06 s | 120,1 MB |

O pico de memória é cerca de 2× o tamanho do arquivo, porque ele é montado em memória (teto de 80 MB por resposta). O processo inteiro chegou a 559 MB de memória residente na medição. Os tempos de rede reais **não foram medidos**: dependem do acesso à fonte.

## 9. Custos, cotas e permissões pendentes

- Custo desta etapa: nenhum serviço novo e nenhuma conta criada.
- **Custo zero na operação definitiva não é garantido.** Depende do ambiente que conseguir acessar a fonte, e nenhum foi testado com sucesso.
- Permissões pendentes:
  - push da branch (ou envio do bundle) para a revisão em PR;
  - execução, se você quiser, de uma sonda no GitHub Actions (`workflow_dispatch`, sem dados pessoais);
  - execução da sonda no seu computador ou na rede da SEAD.

## 10. Preparação para a Etapa 06

- `coletor.coletar_intervalo(..., transporte=...)` e `baixar_pendentes(..., inicio, fim, simular, reverificar)` são os pontos de entrada da fila.
- O manifesto `download` e `inventario.manifesto` dão a cobertura e as lacunas a reprocessar.
- O contrato `Transporte` permite trocar `direto` por outro transporte autorizado sem mudar verificação, acervo ou leitura.
- **A fazer na Etapa 06:**
  - gravar direto em disco durante o download, para reduzir memória;
  - fila persistente e agendamento;
  - armazenamento que sobreviva ao executor;
  - liberar o limite de 31 dias com `--permitir-longo`, só para a carga histórica autorizada.

## 11. Bloqueios e como destravar

1. **Acesso direto à A União a partir de um ambiente que você controla.** É o bloqueio principal. Passo a passo para testar no seu computador com Windows:
   1. Instale o Python 3.11 ou mais novo (python.org).
   2. Baixe o arquivo `etapa05.bundle` entregue com este relatório.
   3. Abra o Prompt de Comando na pasta do arquivo e rode:
      `git clone etapa05.bundle gediv && cd gediv && git checkout etapa05/coleta-oficial`
   4. Instale as dependências: `python -m pip install -r requirements.txt`.
   5. Rode a sonda: `python -m observatorio.operacao sonda --saida sonda.json`.
   6. Envie o `sonda.json`. Ele não contém dados pessoais nem o nome da máquina.

   Saída 0 (`DOWNLOAD_INTEGRO`) comprova o download direto naquele ambiente.
2. **Etapa 04 ausente.** É preciso publicar a branch `etapa04/pdfs-dificeis` ou anexar o bundle dela.
3. **Autorização para push** da branch `etapa05/coleta-oficial` e abertura de PR, sem merge.

## 12. Status por funcionalidade

| Funcionalidade | Status |
|---|---|
| Descoberta pela listagem "Edições recentes" e mensal | IMPLEMENTADO NÃO HOMOLOGADO (estrutura real conferida; leitura real pelo coletor bloqueada) |
| Download direto da fonte oficial | **BLOQUEADO** (ambiente) |
| Verificação de integridade (`Content-Length`, `%%EOF`, `startxref`, páginas) | CONCLUÍDO E TESTADO (sintético) |
| HTTP 200 truncado | CONCLUÍDO E TESTADO (sintético) |
| Quarentena | CONCLUÍDO E TESTADO |
| Manifesto de downloads e procedência | CONCLUÍDO E TESTADO |
| Versões (`IGUAL`, `ALTERADO`, `DUPLICADO`) e idempotência | CONCLUÍDO E TESTADO |
| `Retry-After`, espera progressiva, recusa sem insistência | CONCLUÍDO E TESTADO |
| Destinos autorizados e redirecionamentos | CONCLUÍDO E TESTADO |
| Comandos `sonda`, `coletar-dia`, `coletar-intervalo`, `cobertura`, `--dry-run` | CONCLUÍDO E TESTADO (execução real só até o bloqueio) |
| Manifesto de cobertura com lacunas explícitas | CONCLUÍDO E TESTADO |
| Transporte de contingência | IMPLEMENTADO NÃO HOMOLOGADO |
| Relay autorizado | NÃO INICIADO (por decisão) |
| Matriz de ambientes | PARCIAL (1 testado e bloqueado; 4 não testados) |
| Integração com a Etapa 04 | **BLOQUEADO** (código ausente) |
| Automação diária e carga histórica | NÃO INICIADO (Etapa 06) |
