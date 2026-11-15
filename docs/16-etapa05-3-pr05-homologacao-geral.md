# Etapa 05.3.5 — Homologação geral

Relatório da homologação técnica do sistema integrado (Etapas 03, 04, 05, 05.2 e 05.3.1 a 05.3.4). Diz o que foi
verificado, o que foi corrigido, o que continua pendente e o que falta para a Etapa 06. Nenhum PDF oficial, nome,
matrícula ou processo real está no repositório; as medições com documentos oficiais foram feitas fora dele.

**Conclusão em uma frase:** a homologação técnica está **aprovada com restrições** — o sistema preserva dados e
revisões e não perde nem duplica decisões nos cenários testados, mas a validação documental independente e as
decisões administrativas da GEDIV continuam pendentes, e a operação automática em nuvem não tem infraestrutura
comprovada.

## A — Base examinada

| Item | Resultado |
|---|---|
| Commit de origem | `9abec4cc65d310769fbd0925ef54f3cdc711443a` (ponta de `etapa05-3/pr04-extracao-ocr-classificacao`) |
| Mesmo SHA no GitHub e no local | sim |
| CI do commit de origem | execução nº 32 do workflow `Testes`: 4 de 4 aprovados |
| Árvore de trabalho | sem alterações pendentes |
| `main` | `278abd68a3cb7846c54a08f460b2a064a6c59677`, de 10/11/2026 (merge do PR nº 4); sem alteração desde então |
| Mudanças desde a última entrega | nenhuma: nenhum commit novo em nenhuma branch |
| Branch desta etapa | `etapa05-3/pr05-homologacao-geral`, criada do commit de origem |

Ancestralidade, conferida com `git merge-base --is-ancestor` — cada linha é ancestral da seguinte e todas são
ancestrais do commit de origem:

| Etapa | Branch | Ponta |
|---|---|---|
| base | `main` | `278abd6` |
| (PR nº 5) | `claude/eloquent-hawking-k43pj9` | `c49f9ec` |
| 03 | `etapa03/pr01-regras-definitivas`, `etapa03/pr02-leitura-ouro` | `1fc2469`, `b225289` |
| 04, 05 e 05.1 | `etapa05-1/integracao-pdfs-coleta` | `964ce4d` |
| 05.3.1 | `etapa05-3/pr01-seguranca-ci-validacao` | `63e196d` |
| 05.3.2 | `etapa05-3/pr02-coleta-cobertura` | `8839ae2` |
| 05.3.3 | `etapa05-3/pr03-leitura-banco-revisao` | `5442344` |
| 05.3.4 | `etapa05-3/pr04-extracao-ocr-classificacao` | `9abec4c` |

O histórico é linear: nada foi reescrito e nenhuma correção anterior ficou de fora.

## B — Matriz de auditorias

Situações: **C** corrigido; **P** parcialmente corrigido; **V** depende de validação externa. "Reexecutado" indica
que o teste rodou de novo nesta etapa (toda a suíte foi reexecutada, no local e no CI). Onde a evidência anterior
bastava, nada foi refeito à parte.

### Coleta e cobertura (Etapa 05.3.2 — commits `5098d2f`, `c436114`, `b0a8415`; testes em `tests/test_coleta_cobertura.py`)

| Achado | Situação | Evidência atual | Risco residual e ação |
|---|---|---|---|
| Dia marcado como completo sem verificação suficiente | C | 46 regressões com HTTP simulado, reexecutadas | Só provado com servidor simulado: a fonte real não é alcançada deste ambiente (seção J) |
| Página HTTP 200 que não é listagem válida | C | idem | idem |
| Paginação incompleta | C | idem (listagem além do limite fica parcial e é relida) | idem |
| Suplemento tardio | C | idem (reconciliação de dias já fechados) | A janela de revisita precisa ser definida na operação |
| PDF inválido ou parcial (inclusive HTTP 206) | C | idem + `test_homologacao_geral` cenário 02 (três formas de arquivo inválido recusadas, comando sai com falha) | — |
| Arquivo ausente no acervo apesar do registro | C | download registrado numa única transação; conferência por SHA-256 antes de ler | — |
| Tentativas esgotadas / suspensão após bloqueio | C | guarda por fonte, registrada na auditoria | Comportamento real da fonte sob bloqueio: não observado |
| Cobertura de uma fonte apresentada como geral | C | todo relatório declara as fontes; padrão único `auniao` | A CGE só entra quando pedida |
| Verificação e recuperação por SHA-256 | C | `Acervo.conferir` em toda leitura; cenário 01 e 06 da homologação | — |

### Leitura, classificação e banco

| Achado | Etapa / commit | Teste | Situação | Risco residual e ação |
|---|---|---|---|---|
| Releitura que destrói páginas válidas | 05.3.3 `b31a44c` | `test_leitura_banco_revisao` (reexecutado); homologação 03-04 | C | — |
| Reclassificação não acionada após mudança de texto | 05.3.3 `b31a44c` | idem; homologação 12 | C | — |
| Dupla contagem de versões técnicas | 05.3.3 `b31a44c`, `c21e50c` | idem; homologação 06 e indicadores 03 | C | Identidade ambígua vira conflito para a gerência (indicadores 08) |
| Revisão humana sobrescrita | 05.3.3 `45538c7` | idem; homologação 12 e indicadores 11 | C | A trilha não tem trava no banco contra alteração por fora do programa (seção E) |
| Eventos com vínculos inconsistentes | 05.3.3 `c21e50c`, `45538c7` | idem; homologação 07 e indicadores 12 | C | — |
| Linha de tabela associada à pessoa errada | 05.3.4 `5c80d51`; 05.3.5 `5fa151d` | `test_extracao_ocr_classificacao`, `test_limites_do_leitor` | P | Tabela sem três linhas completas não é reconstruída; a decisão fica sinalizada. Falta conferência humana (seção G) |
| OCR que deixa conteúdo invisível | 05.3.4 `ce3f7cb`; 05.3.5 `5fa151d` | idem | P | Detectados e tratados: fonte errada, imagem pequena, linha não lida, texto em contorno. Não coberto: região em contorno que envolve texto nativo (só aviso) |
| Decisão descartada por falta de processo | 05.3.4 `757adba` | `TesteDecisaoSemProcesso`; indicadores 09 | C | Sem exemplo real nas 11 edições |
| Portaria pertinente não persistida | 05.3.4 `757adba` | `TestePortarias` | C | Sem exemplo real de portaria original; critério depende da GEDIV (Q9) |
| Classificação ambígua resolvida indevidamente | 05.3.4 `757adba` | `TesteGruposEAssuntosAmbiguos`; indicadores 10 | C | Regras dependem da GEDIV (Q1 a Q8) |

### Segurança e operação (Etapa 05.3.1 — commits `f60563f`, `743f6cc`, `d6e7296`, `fb8328a`)

| Achado | Teste | Situação | Risco residual e ação |
|---|---|---|---|
| Justificativa privada na API pública | `test_privacidade_publica`; homologação 09-11 e indicadores 14-15; teste no navegador | C | — |
| Conexões SQLite abertas | `test_conexoes_sqlite` | C | — |
| Corpus vazio aprovado | `test_corpus_validador` | C | — |
| Comando com código de sucesso apesar de falha | `test_codigos_de_saida`; homologação 02, 03-04, 13, 14, 15 | C | — |
| Dados pessoais em logs, relatórios, testes ou artefatos | varredura dos objetos novos antes de cada publicação; relatório do `validar-real` sem dados pessoais (teste) | C | O repositório é **público**: bancos e PDFs nunca podem ir para ele nem para artefatos do CI (seção J) |
| Falha que não permite retomada | homologação 03-04, 13, 14, 15 | C | — |

## C — Homologação integrada

`tests/test_homologacao_geral.py`, 26 testes com PDFs gerados no próprio teste. Todos passam também sobre o código
de origem (`9abec4c`): **a cadeia não tinha defeito de integração**. O que cada cenário conferiu:

| Nº | Cenário | O que foi conferido nos registros intermediários |
|---|---|---|
| 1 | PDF íntegro com ato pertinente | Arquivo no acervo idêntico ao que entrou (SHA-256); edição e data lidas do documento; atos e decisões presos ao arquivo e à página; processo e nome presentes no texto lido; nada conferido = indicadores em zero |
| 2 | PDF inválido ou incompleto | Três formas recusadas com motivo; nada entra no acervo; comando sai com falha (1) |
| 3 e 4 | Página ilegível; leitura recuperada depois | Página pendente registrada; arquivo "lido com pendências"; comando sai com 3; pendência chega à classificação; a retomada relê, reclassifica e não duplica; o histórico de tentativas fica |
| 5 | Decisão omitida | A gerência registra com o trecho literal; trecho que não está no documento é recusado; a decisão humana sobrevive à nova execução do robô |
| 6 | Nova versão técnica do PDF | As duas versões ficam no acervo; 10 registros, 5 vigentes; indicadores contam 5 |
| 7 | Publicação modificadora | Vira evento; só conta depois de vinculada pela gerência; não pode apontar para si mesma; a decisão original não some |
| 8 | Documento sem pertinência | Nenhum ato, nenhuma decisão; atos de outras unidades reconhecidos e postos de lado; arquivo marcado como examinado |
| 9, 10, 11 | Validar, corrigir e rejeitar (pela API) | Sem credencial: recusado; com credencial: estados gravados, correção com valor anterior e autor, três registros de auditoria; rejeitada fora da contagem e visível à gerência; planilha gerencial válida |
| 12 | Releitura depois da homologação humana | Mesma leitura: nada muda. Texto diferente: o valor humano fica, abre-se conflito, indicadores intactos, execução sai com 3 |
| 13 | Falha na classificação | Nada gravado pela metade; leitura preservada; só o tipo do erro é registrado; a execução seguinte conclui |
| 14 | Interrupção na persistência | Transação desfeita por inteiro (cinco tabelas vazias); arquivo continua na fila; banco íntegro; a execução seguinte conclui |
| 15 | Retomada após erro de leitura | O erro antigo continua bloqueando o sucesso até ser refeito |

Indicadores e revisão (15 cenários do item 6 do pedido, mais um invariante):

| Cenário | Resultado |
|---|---|
| Uma decisão válida | contada uma vez |
| Duas pessoas no mesmo processo | 2 decisões, 1 processo |
| Mesmo ato em duas versões físicas | contado uma vez; nada apagado |
| Republicação verdadeira | evento, não decisão nova; só conta depois de vinculada |
| Rejeitada, corrigida, reaberta | rejeitada sai da contagem e continua consultável; a correção sobrevive à reabertura; reaberta volta à fila |
| Identidade ambígua | fora da contagem, com conflito aberto e resolúvel; cada decisão fora da contagem tem o seu conflito |
| Sem número de processo | está na fila; conferida, conta como decisão e não como processo |
| Grupo não homologado | conta no total, sem grupo; não aparece no filtro de nenhum grupo |
| Conflito após releitura | valor humano mantido; conflito único (não se multiplica); some só quando a gerência decide |
| Evento que modifica ato anterior | só conta com vínculo confirmado |
| Histórico de auditoria | quem, o quê, antes, depois, justificativa; nenhum ponto do programa altera ou apaga a trilha |
| Exportação gerencial | linhas das decisões conferidas |
| Acesso público | mesmos números; nenhuma linha individual, nome, matrícula, processo, revisor ou justificativa |
| **Invariante** | toda decisão está em exatamente uma situação: contada, na fila, rejeitada, representada por outra versão, ou com conflito aberto |

Teste de interface no navegador (Chromium, servidor local, base de demonstração sintética): acesso público sem
nomes e com exportação recusada (401); entrada da gerência; conferir uma resenha (fila de 11 para 8, conferidas de
45 para 48); rejeitar outra (rejeitadas de 0 para 2); corrigir o grupo de uma resenha; as sete abas carregam;
planilha exportada; rotas de auditoria e de conflitos respondem; nenhum erro de JavaScript.

## D — Qualidade documental

Medido nas 11 edições oficiais disponíveis (532 páginas), com o leitor 0.8 e as regras desta branch.

| Medida | Leitor 0.7 (origem) | Leitor 0.8 (esta branch) |
|---|---|---|
| Páginas OK / baixa confiança / inconsistente | 529 / 2 / 1 | 529 / 2 / 1 |
| Páginas cujo texto mudou | — | 2 (as duas com texto em contorno) |
| Tempo de leitura das 11 edições (2 processos) | 241 s | 288 s |
| Atos / decisões / eventos | 32 / 207 / 1 | 33 / 208 / 1 |
| Decisões sem nome | 18 | 0 |
| Decisões sem cargo | 30 | 12 (todas de Tempo de Serviço, cuja tabela não tem coluna de cargo) |
| Decisões com ressalva de leitura | 10 | 25 (11 com linha solta; 14 com cargo sem a primeira letra) |
| Fragmentos de tabela juntados / marcados como ambíguos | 1.758 / 49 | 1.743 / 49 (nenhum ambíguo dentro de ato da GEDIV) |

**Omissão encontrada e corrigida.** Na edição de 07/11/2026, página 6, a **resenha 578/2026** (Progressão
Funcional Vertical, deferida, uma pessoa) está publicada como desenho — cada letra é uma curva, sem caractere e sem
imagem. O robô nunca a tinha lido, e a leitura independente usada na conferência técnica também não a via. O
detector criado nesta etapa a apontou; a região agora é lida por OCR e a resenha entra na fila de revisão. As
classes da linha não foram extraídas: a decisão está sinalizada. A mesma detecção achou uma página inteira de outra
matéria (balanço de empresa, 12/11/2026, p. 55), sem relação com a GEDIV.

**Campos corrigidos.** Na resenha 570/2026 (07/11/2026), lida por OCR, as 18 linhas estavam sem nome e sem cargo: o
traço da borda da tabela saía como o caractere "|" antes do nome. Agora as 18 têm nome; 4 têm o cargo lido por
inteiro e 14 têm o cargo com a primeira letra cortada pelo OCR, guardado como lido e sinalizado.

**Duplicações:** nenhuma nas 11 edições (156 decisões das seis edições de novembro: nenhuma extra nem duplicada em
relação à referência; a única a mais é a da resenha 578).

**Ambiguidades em aberto:** 6 atos de Progressão sem grupo (5 por `TEC. ADM`/`STF`, e as resenhas de "profissionais
de Educação"); 1 ato com continuidade duvidosa entre páginas; 3 páginas com ressalva de leitura fora de atos da
GEDIV.

**Corpus conhecido:** aprovado — 10 casos, 99 de 99 linhas corretas em processo, matrícula, nome e cargo; evolução
85 de 85. **Conjunto-ouro** (5 edições): atos e decisões iguais ao esperado.

**Limitações do leitor — situação depois desta etapa**

| Limite documentado na 05.3.4 | Situação |
|---|---|
| Título centrado depois da tabela absorvido pela última linha | **Corrigido**: depois da última linha, só é juntado o fragmento alinhado à célula. Restante: título que, por coincidência, se alinhe à célula (mesma margem ou mesmo centro) |
| Tabela sem três linhas com três células | **Sinalizado, não corrigido**: nada é associado por suposição; a linha solta sinaliza a decisão nos dois eixos |
| OCR parcial em página que mistura texto e imagem | **Corrigido**: os trechos relidos também são conferidos; linha com tinta e sem palavra deixa a página pendente |
| Texto em contorno vetorial | **Corrigido em parte**: região sem texto nativo dentro é lida por OCR; região que envolve texto nativo fica só com aviso (arquivo "lido com pendências") |
| Sem Tesseract, imagem pequena não examinada | **Sinalizado**: o arquivo fica "lido com pendências" com o aviso `IMAGEM_NAO_EXAMINADA` |

Nenhuma dessas limitações fica mais escondida atrás de um arquivo dado como lido sem ressalva.

## E — Segurança e revisão humana

- **Projeção pública:** conferida por teste em três camadas (função, API e navegador). O público recebe agregados e
  a lista de resenhas sem pessoas; exportação, auditoria, conflitos e revisão exigem credencial.
- **Revisão humana:** nenhuma correção é sobrescrita por releitura ou reclassificação; divergência vira conflito
  visível; decisão omitida exige o trecho literal do documento.
- **Trilha de auditoria:** toda ação da gerência grava autor, alvo, valor anterior, valor posterior e
  justificativa. **Risco residual:** o banco não tem trava contra alteração da trilha por fora do programa (alguém
  com acesso ao arquivo SQLite pode editá-la). Não foi corrigido aqui porque exigiria nova versão do esquema; fica
  como requisito da Etapa 06 (cópia de segurança diária da trilha, com SHA-256, fora da máquina que executa).
- **Dados pessoais:** os objetos novos da branch foram varridos antes da publicação contra os 267 valores do corpus
  privado, credenciais, caminhos locais, e-mail e binários: nenhum achado.
- **Repositório público:** o repositório `gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE` é público. Bancos, PDFs,
  planilhas de conferência e artefatos com dados pessoais não podem ser guardados nele.

## F — Testes e CI

Ambiente local: Python 3.13, pdfplumber, pypdf, reportlab, pytesseract, openpyxl, Tesseract 5.3.4 com português.

| Execução | Testes | Aprovados | Falhos | Pulados |
|---|---|---|---|---|
| Local, sem dados reais | 499 | 497 | 0 | 2 |
| Local, com as 11 edições oficiais e o corpus privado | 499 | 499 | 0 | 0 |
| CI ubuntu-24.04, Python 3.11 | 499 | 496 | 0 | 3 |
| CI ubuntu-24.04, Python 3.13 | 499 | 496 | 0 | 3 |
| CI windows-latest, Python 3.11 | 499 | 486 | 0 | 13 |
| CI windows-latest, Python 3.13 | 499 | 486 | 0 | 13 |

A linha de base informada (449) foi confirmada no commit de origem. São **50 testes novos**: 26 em
`tests/test_homologacao_geral.py` e 24 em `tests/test_limites_do_leitor.py`. Nenhum teste antigo foi alterado,
desativado ou removido.

CI: workflow `Testes`, execução nº 33, sobre o commit de código `edb1ff1bb9220e1c6a6749f5cdaaf4f504304c69`
(<https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/43743428131>). O commit de documentação
que traz este relatório é posterior; o resultado da execução sobre ele consta da entrega final, fora do repositório.

**Pulados não são aprovados.** O que cada ambiente deixou de executar:

| Motivo | Local sem dados | Ubuntu (CI) | Windows (CI) |
|---|---|---|---|
| Exigem os PDFs oficiais e o corpus privado (2 testes) | pulados | pulados | pulados |
| Exige `openpyxl` (abrir a planilha exportada num leitor independente; 1 teste) | executado | pulado | pulado |
| Exigem o Tesseract (OCR de verdade; 10 testes) | executados | executados | pulados |

No Windows o workflow não instala o Tesseract; os testes novos desta etapa que tratam de OCR usam o Tesseract
simulado e por isso rodam nos quatro ambientes.

Por tipo de dado:

| Tipo | Onde |
|---|---|
| Sintético (497 testes) | toda a suíte, em todos os ambientes |
| PDFs oficiais conhecidos (2 testes: conjunto-ouro e corpus por campo) | só no ambiente local, com os arquivos privados |
| Amostra realmente independente | **nenhum teste** (seção G) |

Cobertura por assunto pedido: unitários e integração (toda a suíte); migrações SQLite (`test_migracoes`);
fechamento de conexões (`test_conexoes_sqlite`); segurança da API pública (`test_privacidade_publica`,
`test_painel`, `test_homologacao_geral`); revisão gerencial e exportação (`test_painel`,
`test_leitura_banco_revisao`, `test_homologacao_geral`); corpus estrito (`test_corpus_validador`); conjunto-ouro
(`test_leitura_correcoes`); reclassificação e reconciliação (`test_leitura_banco_revisao`); integridade da coleta
(`test_coleta`, `test_coleta_cobertura`, `test_aquisicao`, `test_lotes`); OCR e extração (`test_leitura`,
`test_pdfs_dificeis`, `test_ocr_limite`, `test_extracao_ocr_classificacao`, `test_limites_do_leitor`); códigos de
saída e retomada (`test_codigos_de_saida`, `test_homologacao_geral`); painel (`test_painel`, teste no navegador).

Antes e depois desta etapa, com os testes novos executados sobre o commit de origem: os 26 de homologação passam
(não havia defeito de integração); dos de limites do leitor, 11 dos 16 escritos primeiro falhavam, e os 8
acrescentados depois nasceram de achados da regressão com os PDFs oficiais.

## G — Validação independente

**Situação: VALIDAÇÃO DOCUMENTAL INDEPENDENTE PENDENTE.**

O que já foi usado, e para quê:

| Edição | Páginas | Uso |
|---|---|---|
| 01/10, 02/10, 03/10, 06/10 e 04/11/2026 | 56, 40, 48, 28, 60 | Conjunto-ouro (esperado por edição: atos e total de decisões, conferido tecnicamente em 12/11/2026 com leitura por outra biblioteca); desenvolvimento das Etapas 03 e 04; regressão |
| 05/11, 06/11, 07/11, 10/11, 11/11 e 12/11/2026 | 56, 52, 44, 48, 44, 56 | Corpus de PDFs difíceis (10 atos, valores por campo conferidos visualmente; 3 deles medidos antes de serem olhados); referência coluna a coluna da Etapa 04; desenvolvimento das Etapas 04, 05.3.4 e 05.3.5; regressão |

Não há no ambiente nenhum PDF oficial que não tenha participado do desenvolvimento, e esta etapa não autoriza
baixar outros. Por isso:

- nenhuma medida deste relatório é validação cega;
- a "leitura independente" do conjunto-ouro compartilha uma limitação com o robô (não lê texto em contorno), como
  o caso da resenha 578 demonstrou — ela não substitui a conferência humana;
- nenhum percentual geral de acerto é declarado.

**O que foi preparado.** Um pacote de conferência para a GEDIV, gerado por programa a partir das 11 edições, com
204 das 208 decisões, as 33 resenhas para contagem de linhas, as páginas com ressalva e os atos modificadores. Ele
contém dados pessoais e está **fora do repositório**. O roteiro, os campos a conferir, as perguntas e o termo de
aceite estão em `docs/homologacao/roteiro-conferencia-documental.md`. Distribuição real da amostra: 22 resenhas de
Progressão, 10 de Tempo de Serviço, 27 em página lida no todo ou em parte por OCR, 1 que atravessa página, 7 sem
grupo ou sem assunto, 1 ato modificador, 0 portarias originais (não existem nas edições disponíveis).

Essa conferência, quando feita, mede o robô contra o documento — mas sobre edições conhecidas. Para a homologação
final é preciso repeti-la com edições novas de 2026, escolhidas e baixadas pela GEDIV.

## H — Pendências administrativas GEDIV

Dez questões, todas em `docs/homologacao/questoes-pendentes-gediv.md`, com o estado **PENDENTE DE DELIBERAÇÃO
GEDIV**: `TEC. ADM` e `AST`; `STF` e `SFT`; denominação do grupo `INT`; "profissionais de Educação" e `MAG`; ato
com dois grupos; decisão sem processo; desistência de licença sem indicar a licença; conversão de licença especial
sem destino; critério das portarias relacionadas; pendências individuais (resenhas 570, 576 e 578/2026 e Portaria
8/2026-DEREH). Nenhuma resposta foi presumida e nenhuma regra administrativa foi alterada nesta etapa.

## I — Pull Request nº 5

Exame apenas consultivo. Nada foi alterado: o PR continua aberto, com a mesma descrição e a mesma branch.

| Item | Resultado |
|---|---|
| Situação | aberto, não integrado; última atualização em 11/11/2026 |
| Origem → destino | `claude/eloquent-hawking-k43pj9` (`c49f9ec`) → `main` (`278abd6`) |
| Commits | 4: `209ebc7` (classificação, revisão, API e painel), `b9d3e20` (validação com PDFs oficiais), `8e38463` e `c49f9ec` (sonda de acesso em três sistemas) |
| Tamanho | 68 arquivos; +7.455 / −78 linhas |
| Conflito com a `main` | nenhum (o GitHub informa integração limpa) |
| CI do commit do PR | aprovado |
| Relação com a linha atual | `c49f9ec` é **ancestral** de todas as branches das Etapas 03 a 05.3.5. A linha atual está 37 commits à frente (até a 05.3.4) e o PR não tem nenhum commit que ela não tenha |
| Conteúdo exclusivo do PR | **nenhum**: nenhum arquivo do PR está ausente da linha atual; 40 dos seus arquivos foram alterados depois e 38 arquivos novos foram criados |

**Classificação: SUPERADO.** Tudo o que o PR propõe já está na linha atual, numa forma corrigida.

**Risco de integrar o PR nº 5 diretamente na `main`.** A `main` passaria a ter a versão de 11/11/2026, anterior a
todas as correções das auditorias: a API pública que deixava passar justificativa interna, comandos que saíam com
sucesso apesar de falha, corpus vazio aprovado, cobertura de coleta sem evidência, releitura que apagava páginas
válidas, dupla contagem de versões, revisão humana que podia ser sobrescrita, decisões sem processo descartadas.
Quem usasse a `main` teria um painel com defeitos já conhecidos e corrigidos em outro lugar.

**Procedimento mais seguro, quando houver autorização:** integrar a ponta da linha atual (a branch homologada), e
não o PR nº 5. Como a `main` é ancestral da linha atual, a integração é um avanço simples, sem conflito. Feito
isso, o PR nº 5 fica automaticamente contido na `main` e pode ser encerrado pela responsável, sem perda. A decisão
— integrar, quando e a partir de qual commit — é da responsável pelo projeto.

## J — Prontidão da Etapa 06

**A Etapa 06 continua NÃO LIBERADA PARA PRODUÇÃO.** Nada foi implantado, agendado ou coletado nesta etapa.

| Requisito | Evidência existente | Lacuna | Risco | Próxima ação | Exige autorização? |
|---|---|---|---|---|---|
| Execução gratuita agendada | O repositório é público e usa o GitHub Actions; os workflows `Testes` e `Sonda` rodam em executores hospedados | Nenhum workflow agendado existe. Gratuidade e limites são regra do provedor e podem mudar; agendamentos de repositórios sem atividade costumam ser suspensos | Custo ou interrupção imprevistos | Confirmar na documentação vigente do provedor, na data do piloto, os limites para repositório público e a regra de suspensão | Sim, para criar o agendamento |
| Requisitos técnicos do executor | O workflow `Testes` instala Python, as bibliotecas e o Tesseract em português no Linux e passa em 10 minutos | No Windows o Tesseract não é instalado. A leitura de uma edição leva de 15 a 60 s; a carga histórica de 2026 (centenas de edições) não foi medida | Tempo de execução acima do limite por tarefa | Usar executor Linux; medir uma semana de edições num piloto | Sim (piloto) |
| Fontes exigidas | Fonte padrão única: A União (`auniao.pb.gov.br`); CGE complementar | Suplementos e republicações tardias dependem de revisita | Dia dado como completo cedo demais | Definir a janela de revisita com a GEDIV | Não |
| **Acesso do executor em nuvem às fontes** | Sonda de 10 e 11/11/2026 em executores Linux, Windows e macOS do GitHub (saída pelos EUA): `auniao.pb.gov.br` e `cge.pb.gov.br` **não aceitaram conexão** (porta 443); `paraiba.pb.gov.br` respondeu com verificação anti-robô | **O acesso a partir da nuvem não está comprovado; a evidência disponível é de bloqueio.** Não há teste a partir de rede brasileira | **Impeditivo**: sem acesso não há coleta automática | Repetir a sonda de um computador ou serviço em rede no Brasil (de preferência a rede da SEAD); se confirmar o bloqueio só para o exterior, definir onde o coletor roda | Sim |
| Causa das falhas de rede | A sonda separa DNS, conexão, TLS e HTTP: a falha é na conexão | Não se sabe se é bloqueio por país, por provedor de nuvem ou instabilidade | Solução errada para o problema errado | Sonda em rede brasileira; consulta à área de TI responsável pelo portal | Sim (contato institucional) |
| Armazenamento persistente | Acervo por SHA-256 e banco SQLite num diretório; migrações com cópia de segurança | Não há destino persistente definido. O executor do GitHub é descartável e o repositório é público | Perda do histórico; exposição de dados pessoais | Escolher um armazenamento **privado** (por exemplo, pasta institucional) e o modo de acesso | Sim |
| Não perder histórico em ambiente efêmero | O robô retoma de onde parou se o diretório de dados for o mesmo | Sem restauração do diretório antes de cada execução, cada execução começaria do zero | Indicadores zerados ou duplicados | Desenhar "restaurar → executar → conferir → guardar" e testar com dados sintéticos | Sim |
| Backup e restauração | Cópia automática antes de migração; SHA-256 de cada PDF | Não há rotina de backup do banco nem teste de restauração | Perda das revisões humanas | Backup diário do banco e da trilha com SHA-256; ensaio de restauração mensal | Sim |
| Proteção de bancos, logs, PDFs e dados pessoais | API pública por lista explícita; logs sem endereços consultados; relatórios sem dados pessoais | Artefatos de CI de repositório público são acessíveis a terceiros; credencial da gerência só por variável de ambiente | Vazamento | Nunca publicar banco, PDF ou planilha como artefato; guardar a credencial como segredo do ambiente | Sim |
| Detectar e retomar execução incompleta | Códigos de saída 0, 1, 3 e 4; fila de leitura e de classificação; `--refazer-pendentes` | Não há alerta para ninguém quando a execução falha | Falha silenciosa por dias | Notificação por e-mail em saída 1 e resumo em saída 3 | Sim |
| Tratar o código 3 (`CONCLUIDO_COM_PENDENCIAS`) | Testado: 3 significa "terminou, há algo para olhar" | Um agendador comum trata qualquer código diferente de 0 como falha | Alarme falso diário, ou pendência ignorada | No agendamento: 3 não interrompe a publicação do painel, mas gera aviso à gerência | Não (decisão de desenho) |
| Não declarar mês incompleto como coletado | Cobertura por dia com evidência; mês só fecha com todos os dias verificados | Só provado com servidor simulado | Buraco no histórico | Conferir um mês real contra o índice do portal, no piloto | Sim (coleta real) |
| Recuperação histórica desde 01/01/2026 | Comandos de coleta por intervalo e de cobertura | Nunca executada contra a fonte real | Volume e bloqueios desconhecidos | Piloto de um mês, depois o restante em lotes | Sim |
| Atualização segura do painel | Leitura do painel em instantâneo; servidor local | Não há hospedagem definida; o endereço público exige HTTPS | Painel fora do ar ou exposto | Definir hospedagem com a TI | Sim |
| Revisão gerencial | Fila, correções, conflitos e auditoria testados, inclusive no navegador | Um só perfil de gerência, por credencial única | Autoria declarada, não autenticada | Definir quem revisa e como se identifica | Sim |

**O que impede o início da operação:** (1) acesso da nuvem à fonte não comprovado; (2) armazenamento persistente
privado não definido; (3) backup e restauração não ensaiados; (4) validação documental independente pendente;
(5) decisões da GEDIV pendentes.

## K — Conclusão

**Homologação técnica: APROVADA COM RESTRIÇÕES.**

Aprovada, porque: a cadeia inteira foi exercitada em 15 cenários sem defeito de integração; os defeitos críticos das
auditorias têm correção, teste e evidência atual; indicadores e revisões humanas se mantêm consistentes em todos os
cenários; a regressão com as 11 edições oficiais não perdeu nem duplicou decisão; os testes passam nos quatro
ambientes.

Com restrições, porque:

1. a validação documental independente não foi feita (não há edições inéditas no ambiente nem conferência humana);
2. esta mesma etapa encontrou uma resenha inteira que o robô não lia — prova de que os testes existentes não
   garantiam completude, e de que pode haver outros casos em edições ainda não examinadas;
3. dez decisões administrativas da GEDIV estão pendentes;
4. restam limites conhecidos do leitor, agora sinalizados;
5. a operação em nuvem não tem acesso à fonte comprovado.

## L — Continuidade

Ações concretas, na ordem em que destravam as seguintes:

1. **GEDIV — conferência documental** com o pacote entregue (roteiro em `docs/homologacao/`), incluindo as resenhas
   570 e 578/2026.
2. **GEDIV — deliberação** das dez questões pendentes.
3. **Amostra inédita:** a GEDIV escolhe e baixa edições de 2026 que o robô nunca viu; repete-se a conferência.
4. **Sonda em rede brasileira** (computador da SEAD), para saber de onde a coleta consegue alcançar o portal.
5. **Decisão da responsável sobre a `main` e o PR nº 5** (recomendação na seção I).
6. **Definição, com a TI, do armazenamento privado, do backup e da hospedagem** do painel.
7. Só então: piloto da Etapa 06 com um mês de edições, sem agendamento, medindo tempo, cobertura e pendências.
