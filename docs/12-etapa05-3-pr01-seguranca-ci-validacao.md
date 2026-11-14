# Etapa 05.3.1 — Segurança, SQLite, validação e tratamento de erros

Data: 14/11/2026. Primeiro pacote de correções apontadas pelas auditorias independentes (Codex, Gemini/Antigravity,
GPT Work) sobre a versão `964ce4d`. Cada defeito foi conferido no código antes de ser corrigido e reproduzido por um
teste que **falha na versão de origem** e passa na corrigida.

## 1. Base de origem

| Item | Valor |
|---|---|
| Repositório | `gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE` |
| Branch de origem | `etapa05-1/integracao-pdfs-coleta` (não alterada) |
| Commit de origem | `964ce4d2c7e2e88f9e18ef4a57690fc6f028f45f` (conferido no GitHub antes de começar) |

## 2. Branch criada

`etapa05-3/pr01-seguranca-ci-validacao`, a partir exatamente de `964ce4d`. Não houve merge, PR, deploy nem alteração da
`main`.

| Commit | Correção |
|---|---|
| `f60563f` | 1 — privacidade da API pública |
| `743f6cc` | 2 — conexões SQLite fechadas também na falha |
| `d6e7296` | 3 — validador do corpus estrito |
| `fb8328a` | 4 — códigos de saída dos comandos |

## 3. Defeitos corrigidos

### Correção 1 — Justificativa privada saía na API pública (P1)

**Defeito (reproduzido):** a justificativa livre da revisão de um evento, gravada em `evento.fundamento`, era
devolvida sem autenticação em `/api/painel`. Ela pode conter nome, matrícula, processo ou observação interna.

**Correção:**
- `observatorio/painel/projecao.py` é a **política única** do que cada perfil recebe. Ela usa uma lista explícita de
  campos permitidos por tipo de registro: evento, resenha, outra publicação e evento no relatório do `validar-real`.
- Um campo novo na base não chega ao público por omissão.
- A proteção acontece no servidor, antes de a resposta sair.
- O relatório do `validar-real`, documentado como "sem dados pessoais", também deixou de levar o `fundamento`.
- A justificativa continua na base, na trilha de auditoria e na exportação da gerência.
- A revisão gerencial não mudou.

### Correção 2 — Conexões SQLite abertas após falha (P1)

**Defeito:** no CI de `964ce4d`, os dois jobs Windows falharam com 5 erros cada, por "arquivo em uso por outro
processo" ao apagar o banco temporário. As causas:
- Em `Banco.__init__`, se a migração falhava (versão mais nova, estrutura incompatível ou erro no meio), a conexão
  ficava aberta, e quem chamou não recebia o objeto para fechá-la.
- `tests/test_migracoes.py` abria cinco conexões para inspecionar a estrutura e nunca as fechava.

**Correção:**
- `Banco.__init__` fecha a conexão em qualquer falha e propaga o erro **original**, inclusive `KeyboardInterrupt`.
- Uma falha no próprio `ROLLBACK` não esconde mais o erro da migração.
- `Banco` passa a aceitar `with Banco(...) as banco:`.
- Os testes usam `contextlib.closing`. `with sqlite3.connect(...)` controla a transação, mas não fecha a conexão.
- Transação única, ROLLBACK, cópia `.antes-vN.bak` e migrações v1–v7 continuam iguais.

### Correção 3 — Validador do corpus aprovava resultados incompletos (P1)

**Defeitos confirmados no código:**
- Um caso sem esperado privado era pulado em silêncio.
- Um PDF ausente ficava fora do total, que ainda podia dar 100%.
- Com o esperado vazio, o resultado era `{}` e o teste real fazia **zero** asserções, ou seja, "passava".
- Linhas extras não contavam, e duplicatas ficavam escondidas.
- Sem matrícula correspondente, o pareamento caía para a posição da linha.
- O código de saída do subprocesso era ignorado, e `sqlite3.connect` criava um banco vazio no lugar do ausente.
- O comando `corpus` saía sempre com 0.

**Correção:**
- Estados explícitos para o resultado geral: `APROVADO`, `REPROVADO`, `PARCIAL` e `INDISPONIVEL`.
- Estados explícitos por caso: `CONFERE`, `DIVERGENTE`, `PDF_AUSENTE`, `ESPERADO_AUSENTE`, `ESPERADO_VAZIO`,
  `CASO_NAO_CONTRATADO` e `FALHA_EXECUCAO`.
- Pareamento um a um pela matrícula, contando ausentes, extras, duplicadas, ambíguas e campos divergentes.
- O banco da leitura é aberto só para leitura, e o código de saída do subprocesso é conferido.
- `corpus` sai com 0 só quando o resultado é `APROVADO`.

**Achado real:** o validador estrito revelou que o caso "Portaria 8/2026-DEREH" (10/11) **nunca era avaliado**. O
esperado dele é um evento público, não linhas privadas. Agora esse caso é avaliado pelo evento extraído na página, e
confere.

### Correção 4 — Comandos saíam com sucesso apesar de falhas (P1)

**Defeitos (reproduzidos):**
- `executar` saía com 0 mesmo com leitura em `ERRO`.
- Numa segunda execução, o arquivo com erro não era relido e o comando saía com 0 de novo.
- Uma origem inexistente também saía com 0.
- `validar-real` tinha o mesmo comportamento.
- `ouro` saía com 0 com o manifesto vazio e usava 2 (erro de uso) para PDF ausente.

**Correção:** códigos comuns definidos em `observatorio/operacao/saida.py`.

| Código | Significado | O que o agendador deve fazer |
|---|---|---|
| 0 | Sucesso integral | Nada |
| 1 | Falha | Alertar; exige intervenção |
| 2 | Erro de uso | Corrigir a chamada |
| 3 | Concluído com pendências | Os dados estão gravados; retomar ou revisar |
| 4 | Não executado | Faltam insumos |

- `executar` devolve `resultado = {codigo, situacao, motivos, retomada}`.
- Leituras em `ERRO` de execuções anteriores continuam contando como falha até serem refeitas com
  `executar --refazer-pendentes`.
- A classificação isola a falha de um arquivo: os outros seguem, e o arquivo fica na fila para a próxima execução.
  As regras de classificação não mudaram.
- `validar-real` e `ouro` refletem o resultado, e o `ouro` aceita a leitura com pendências (3) como execução válida.

## 4. Arquivos modificados

| Arquivo | Correção |
|---|---|
| `observatorio/painel/projecao.py` (novo) | 1 |
| `observatorio/painel/indicadores.py` | 1 |
| `observatorio/operacao/validacao_real.py` | 1, 4 |
| `observatorio/nucleo/banco.py` | 2 |
| `tests/test_migracoes.py` | 2 (fechamento das conexões; nenhuma asserção mudou) |
| `observatorio/operacao/saida.py` (novo) | 3, 4 |
| `observatorio/operacao/corpus.py` | 3 |
| `tests/test_pdfs_dificeis.py` | 3 (o teste real passa a exigir `APROVADO`: mais estrito) |
| `observatorio/operacao/__main__.py` | 3, 4 |
| `observatorio/operacao/fluxo.py` | 4 |
| `observatorio/operacao/ouro.py` | 4 |
| `observatorio/gerencias/gediv/processo.py` | 4 (isolamento de falha por arquivo; regras intactas) |

**Mudanças de contrato:**
- O retorno de `corpus.executar` passou a ser `{situacao, aprovado, codigo_de_saida, motivo, conjuntos}`.
- `fluxo.executar` ganhou a chave `resultado`.
- O relatório do `validar-real` ganhou `codigo_de_saida`.
- `classificar_pendentes` ganhou `com_erro` e `erros`.
- No `ouro`, PDF ausente passou de 2 para 1 (se faltar parte dos PDFs) ou 4 (se faltarem todos).
- Nenhuma chave existente foi removida, exceto o `fundamento` nas projeções públicas, que é intencional.

## 5. Comportamentos preservados

- Dois eixos, 16 grupos PCCR, 7 categorias de Tempo de Serviço e exclusões: as regras de classificação não foram
  tocadas.
- As seis edições oficiais de novembro (05, 06, 07, 10, 11 e 12/11), relidas nesta branch, são **idênticas** à Etapa 04
  em todas as colunas de `ato`, `decisao`, `evento`, `pagina`, `leitura`, `fora_escopo`, `outra_publicacao` e
  `classificacao`.
- Revisões humanas, quarentena, SHA-256, rastreabilidade e versionamento estão inalterados.
- Continuam valendo o OCR com uma thread por chamada e o limite de tempo.
- O dashboard funciona: a página tolera a ausência do `fundamento` no perfil público.

## 6. Testes novos (50)

| Arquivo | Testes | Cobre |
|---|---|---|
| `tests/test_privacidade_publica.py` | 8 | Evento validado, sugerido, rejeitado e reaberto com marcador privado; API sem credencial em todas as rotas abertas, inclusive estruturas aninhadas; gerência autenticada; exportação; relatório |
| `tests/test_conexoes_sqlite.py` | 8 | Registra cada conexão e exige que esteja fechada ao fim de cada cenário (sucesso, `with`, reabertura, falha na migração, falha também no ROLLBACK, versão mais nova, estrutura incompatível, exceção qualquer); depois renomeia e apaga o arquivo |
| `tests/test_corpus_validador.py` | 21 | Conjunto vazio, PDF ausente, caso não encontrado, extra, duplicado, fora de ordem, ambíguo, divergência de campo, falha de subprocesso, corpus correto, caso de evento, CLI sem dados pessoais |
| `tests/test_codigos_de_saida.py` | 13 | Sucesso integral, falha na leitura e retomada, pendências, falha na classificação e retomada, importação recusada, validação com divergência, ausência de arquivos (também no processo real) |

**Prova de que os testes pegam os defeitos:** rodados contra o código de `964ce4d`, os testes de privacidade falham
(o marcador aparece em `/api/painel` sem credencial). Também falham os de conexão (6 cenários deixam a conexão aberta,
mesmo no Linux), os de código de saída (leitura em `ERRO` e origem inexistente saem com 0) e o validador (esperado
vazio devolve `{}`).

## 7–9. Testes executados e resultados (locais, Linux, Python 3.13)

| Execução | Executados | Aprovados | Pulados | Falhos |
|---|---|---|---|---|
| Suíte completa, só sintéticos | 320 | 318 | 2 | 0 |
| Suíte completa com PDFs oficiais e esperado privado (fora do repositório) | 320 | **320** | 0 | 0 |

- **Testes pulados sem os dados reais:** conjunto-ouro e corpus real, que exigem `GEDIV_PDFS_OURO` e
  `GEDIV_CORPUS_PRIVADO`.
- **Testes pulados no Windows do CI:** os que exigem o Tesseract, que o workflow só instala no Linux.

| Comando com dados reais | Resultado |
|---|---|
| `ouro` | 5/5 `CONFERE`, código de saída 0 |
| `corpus` | `APROVADO`: 10/10 casos, 99/99 linhas pareadas, 0 ausentes, extras, duplicadas ou divergentes; código de saída 0 |
| `validar-real` nas 6 edições de novembro | 0, exceto 06/11 e 10/11, que saem com 3 (cada uma tem uma página pendente, como na Etapa 04) |

Esses resultados com PDFs oficiais são **regressão**: são as mesmas edições usadas no desenvolvimento, não uma
validação independente.

## 10. Resultado do CI

Registrado após o push, em commit próprio. Esperado: 4 jobs aprovados (Linux e Windows × Python 3.11 e 3.13).

Referência anterior, no CI de `964ce4d`: Linux aprovado nas duas versões; Windows reprovado nas duas, com 5 erros cada,
todos em `tests/test_migracoes.py` (`PermissionError: WinError 32` ao apagar o SQLite temporário).

## 11. Riscos residuais

- O Windows só foi exercitado pelo CI. As provas locais de fechamento são independentes do sistema operacional
  (conexões registradas).
- `outra_publicacao.titulo` é público. Ele é gerado pelo classificador ("Resenha nº…", "Portaria nº…"), não por
  texto livre, mas a origem precisa continuar assim.
- O código 3 é frequente com PDFs reais (uma página de baixa confiança basta). Um agendador deve tratá-lo como
  "revisar", não como falha.

## 12. Limitações

- Nenhuma coleta real foi executada nesta etapa, e não houve teste contra a rede.
- A validação com PDFs oficiais usa os mesmos documentos do desenvolvimento.
- Esta etapa não trata defeitos de coleta, classificação ou leitura apontados pelas auditorias fora deste pacote.

## 13. Próxima etapa

Etapa 05.3.2: o próximo pacote de correções das auditorias, dentro dos limites que forem autorizados. A Etapa 06
(automação) continua dependendo dos pacotes 05.3.x e de infraestrutura autorizada.
