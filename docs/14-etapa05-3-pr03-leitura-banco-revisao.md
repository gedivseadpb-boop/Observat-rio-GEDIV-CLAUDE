# Etapa 05.3.3 — Leitura, banco de dados, reclassificação e revisão humana

Data: 14/11/2026. Terceiro pacote de correções das auditorias (Codex, Gemini/Antigravity e GPT Work) sobre `964ce4d`.
Cada achado foi confirmado no HEAD de origem antes de ser corrigido e reproduzido com dados sintéticos (seção 6).

## 1. Origem e branch

| Item | Valor |
|---|---|
| Commit de origem | `8839ae2fbdd9987af3fde6cd6c9397bf7d50096e` (fim da 05.3.2; CI 4/4 aprovado na execução 29; 366 testes) |
| Branch | `etapa05-3/pr03-leitura-banco-revisao` |
| Branches anteriores | `main`, `pr01`, `pr02` e `etapa05-1`: não alteradas |

| Commit | Grupos | Conteúdo |
|---|---|---|
| `b31a44c` | A, B, C, E, F | Banco v8: tentativas e última leitura válida, reclassificação por revisão de leitura, identidade lógica, conflitos e vínculos |
| `c21e50c` | C, E | Painel: só decisões vigentes, eventos por ato lógico, instantâneo consistente |
| `45538c7` | D | Revisão humana: correções de todos os campos essenciais, decisão omitida, conflitos, API e interface |
| `847bd36` | — | 30 testes de regressão |

## 2. Defeitos corrigidos

### Correção 1 — Última leitura válida (A03; perda de páginas)

Arquivos: `nucleo/banco.py` (`registrar_leitura`, `comparar_leituras`, `arquivos_sem_leitura`, `tentativas_de_leitura`) e
`leitura/leitor.py` (`processar`).

**Registro das tentativas.** Toda tentativa fica em `tentativa_leitura`, com versão do leitor, momento, situação,
resultado, páginas, revisão, erro e detalhe.

**Classificação da tentativa**, comparando página a página com a última leitura válida:

| Resultado | Quando acontece | Aceita? |
|---|---|---|
| `PRIMEIRA` | não havia leitura válida | sim |
| `NEUTRA` | mesmo texto e mesma qualidade | sim |
| `MELHORA` | página que deixa de ter pendência, ou página acrescida | sim |
| `MUDANCA` | texto diferente, sem perda | sim |
| `PERDA_DE_CONTEUDO` | página ausente, página que piorou ou ficou sem texto | **não** |
| `FALHA_TECNICA` | erro na leitura | **não** |

**Efeito de cada caso:**
- **Tentativa recusada:** não toca as páginas, a situação nem a versão da leitura válida, e só deixa um aviso.
- **Contagem de palavras:** nunca é usada como medida de qualidade.
- **Fila sem repetição automática:** uma tentativa malsucedida desta versão do leitor não se repete a cada execução,
  mas não some: volta com `--refazer-pendentes`. Antes, ela gravava a versão nova e saía da fila.
- **Releitura recusada:** aparece no fluxo como pendência (`RELEITURA_RECUSADA`, código de saída 3).

### Correção 2 — Reclassificação após releitura (A02)

Arquivos: `banco.py` (`arquivos_sem_classificacao`, `classificacoes_desatualizadas`, `gravar_classificacao`) e
`gerencias/gediv/processo.py`.

- **Revisão da leitura:** `leitura.revisao` é o hash do texto aceito de cada página, e `classificacao.revisao_leitura`
  registra de qual revisão a classificação veio.
- **Quando volta à fila:** texto novo do mesmo PDF (mesmo SHA) faz o arquivo voltar à fila de classificação. Uma versão
  nova do leitor com o mesmo texto não volta.
- **Transição segura:** a troca da classificação antiga pela nova é uma única transação. Uma falha mantém a anterior
  intacta e o arquivo na fila.
- **Decisão já revisada:** não é regravada. Se a nova extração diverge dela, ou do valor que a extração tinha antes de
  uma correção humana, cada campo diferente vira **conflito**.
- **Ato com decisões revisadas:** os metadados técnicos (texto, pendências, páginas, data do expediente, versão das
  regras) passam a ser atualizados, e não ficam mais congelados. Só a classificação homologada é preservada, e uma
  divergência nela vira conflito.

### Correção 3 — Versões de PDF e identidade lógica (A06)

Arquivos: `banco.py` (`chave_ato`, `chave_decisao`, `_reconciliar_atos`, `_aplicar_resolucoes`) e `painel/indicadores.py`.

**Identidade:**
- **Física:** o SHA-256 do PDF. Todas as versões continuam guardadas.
- **Lógica do ato:** gerência, tipo, número, sufixo e natureza. Uma republicação tem natureza própria e nunca é
  fundida com o original.
- **Decisão dentro do ato lógico:** o processo; quando o mesmo processo aparece para mais de uma pessoa, também a
  matrícula; e, sem processo, a matrícula.

**Representação principal** de cada ato lógico: a que já tem revisão humana (a mais antiga) ou, sem revisão, a do arquivo
mais recente. As outras representações são tratadas assim:

| Situação da decisão na outra representação | Tratamento |
|---|---|
| Mesma decisão | fica guardada, fora da contagem, apontando para a principal; o que diverge vira conflito |
| Mesmo processo com outra matrícula, ou sem processo nem matrícula | **correspondência ambígua**: fora dos indicadores até a gerência decidir; nunca herda a revisão de outra pessoa |
| Só existe na versão mais nova | acréscimo: vai à conferência normalmente |
| Só existe numa versão mais antiga | fora dos indicadores, com conflito |

**Painel:** conta só as decisões vigentes, e os eventos de alteração por ato lógico.

### Correção 4 — Preservação das revisões humanas

- **Registro de cada correção** (tabela `correcao`): valor extraído (o original), valor anterior, valor corrigido,
  autor, momento e justificativa.
- **Conflitos** (tabela `conflito`): explícitos e idempotentes. Uma proposta mantida pela gerência não volta.
- **Resolução:** a gerência aceita (o valor é aplicado, com registro de correção) ou mantém.
- **Decisões que prevalecem:** as decisões da gerência sobre vigência prevalecem sobre a reconciliação automática.
- **Correção não se perde:** uma releitura com extração igual à original não gera conflito.

### Correção 5 — Ferramenta gerencial

Arquivos: `revisao/servico.py`, `web/servidor.py` e `web/estatico/`.

**Condições para corrigir:** credencial da gerência, declaração de que o PDF oficial foi consultado e justificativa. Tudo
vai para a trilha de auditoria, e a justificativa continua privada.

| O que se corrige | Campos | Domínio aceito |
|---|---|---|
| Decisão | processo, servidor, matrícula, cargo, lotação | texto |
| Decisão | resultado | deferido, indeferido ou não informado |
| Decisão | classe anterior e posterior | A a F |
| Decisão | nível anterior e atual | como publicado: algarismos romanos ou "NIVEL n" |
| Ato | eixo | só os dois eixos |
| Ato | modalidade, condição | catálogo |
| Ato | grupo PCCR | os 16 do catálogo |
| Ato | assunto do Tempo de Serviço | os 7 do catálogo |

- **Consistência entre campos:** um assunto do Tempo de Serviço não pode ser dado a uma Progressão.
- **Sem equivalências presumidas:** TEC. ADM e STF continuam sem grupo.
- **Decisão omitida:** só pode ser registrada com o trecho literal, que precisa constar do texto lido da página. O
  processo, a matrícula e o nome informados precisam constar do trecho. O registro é idempotente.
- **API:** em `/api/revisao`, os alvos `ato_classificacao`, `decisao_omitida` e `conflito`; também `/api/conflitos`
  (com vínculos órfãos e classificações desatualizadas) e conflitos e correções dentro de `/api/ato`.
- **Interface:** botões "Corrigir campos…", "Corrigir classificação…", "Registrar decisão omitida…" e "Aceitar…" /
  "Manter…" para cada conflito, com listas fechadas do catálogo. Antes, a interface não enviava correção alguma.
- **Teste no navegador** (Playwright, base de demonstração sintética): entrar, abrir a resenha, corrigir o grupo pela
  tela e confirmar. O diálogo fechou sem erro, não houve erro de JavaScript e a trilha registrou a correção com a
  responsável.

### Correção 6 — Eventos e vínculos (A15)

- **Atos protegidos:** um ato referenciado por qualquer evento remanescente (modificador, original ou sugerido) não é
  apagado na reclassificação. Antes, o ato modificador de um evento validado podia sumir.
- **Validação do vínculo:** só pode apontar para um ato **original** da mesma gerência, não posterior ao evento.
- **Diagnóstico de vínculos:** `vinculos_orfaos()` aponta, sem alterar nada, referências inexistentes e alvos
  incompatíveis.
- **Sem chaves estrangeiras novas:** não foram impostas a bancos históricos, porque o SQLite não as acrescenta por
  `ALTER` e eventos antigos não podem ser apagados para satisfazê-las.

## 3. Migração v8

- **Estrutura:** só acréscimos. São três tabelas novas (`tentativa_leitura`, `correcao`, `conflito`), colunas novas em
  `leitura`, `classificacao`, `ato` e `decisao`, e índices.
- **Motor de migração:** passou a reconhecer `CREATE UNIQUE INDEX`. As migrações históricas não mudaram.
- **Backfill idempotente:** calcula a revisão das leituras, liga as classificações existentes à leitura atual (sem
  reclassificar a base inteira), calcula as identidades lógicas e reconcilia as versões já existentes.
- **Teste:** banco v7 com dados, migrado com cópia `.antes-v8.bak`, reaberto sem pendências. Os testes de migração
  existentes (v1 a v7, interrupção, rollback, versão mais nova, fechamento de conexões) continuam passando.

## 4. Mudanças de contrato

- `registrar_leitura` devolve o resultado da comparação. A situação e a versão da leitura válida só mudam com tentativa
  aceita.
- `leitor.processar` pode devolver a chave `RELEITURA_RECUSADA`.
- `classificar_pendentes` ganhou `conflitos`.
- O painel conta só as decisões com `vigente = 1`.
- `apoio` ganhou `conflitos_abertos` e `classificacoes_desatualizadas`.
- `revisar_evento` recusa alvo que não seja original.
- Correções de campo exigem a declaração de consulta ao PDF.
- **Teste antigo ajustado:** só o de migração v6→v7, que comparava a estrutura inteira. Ele passa a aceitar os
  acréscimos da v8 e continua exigindo que nenhuma estrutura anterior suma ou mude.

## 5. Preservado

- Correções das Etapas 05.3.1 (privacidade, conexões, validador, códigos de saída) e 05.3.2 (coleta, cobertura,
  integridade, suspensão, retomada).
- Regras GEDIV: dois eixos, 16 grupos, 7 assuntos, exclusões e histórico a partir de 01/01/2026.
- **Edições oficiais de novembro, relidas nesta branch:** idênticas à Etapa 04 em todas as tabelas comparadas. Na
  edição de 07/11, as 85 decisões estão vigentes e não há nenhum conflito falso.

## 6. Evidências antes e depois (reprodução sintética)

| Cenário | Origem `8839ae2` | Corrigido |
|---|---|---|
| Releitura com erro: versão gravada | `v2` (sai da fila como lida) | `v1` (tentativa registrada; volta com `--refazer-pendentes`) |
| Releitura parcial: páginas restantes | 1 | 2 |
| Texto novo do mesmo PDF volta à classificação | não | sim |
| Duas versões conferidas: decisões no indicador (correto: 3) | 6 | 3 |
| Ato modificador de evento validado após releitura | apagado | preservado |
| Correção de grupo, eixo ou assunto | impossível | disponível, validada e auditada |

## 7. Testes

- **Testes novos:** 30, em `tests/test_leitura_banco_revisao.py`.
- **Total:** 396 testes (366 anteriores mais 30 novos).
- **Resultados locais e do CI:** no relatório de entrega da etapa.

## 8. Riscos residuais e limitações

- **Identidade lógica:** depende do número do ato publicado. Atos sem número não são reconciliados automaticamente:
  ficam como estão e não são fundidos.
- **Representação principal:** a escolha "revisada mais antiga, senão arquivo mais recente" é uma regra técnica. Casos
  raros (por exemplo, duas versões conferidas por pessoas diferentes) geram conflito para decisão humana.
- **Valores corrigidos:** a correção de nível exige o formato publicado, mas não confere o valor contra o PDF, cuja
  leitura pode estar errada; a declaração de consulta é obrigatória.
- **Teste da interface:** o caminho na interface foi testado no navegador com a base de demonstração; não há teste
  automatizado de navegador no CI.
- **Validação independente:** a validação com PDFs oficiais é regressão sobre as edições do desenvolvimento, não
  validação independente.

## 9. Pendências administrativas (GEDIV)

- Grupo de TEC. ADM e STF, ainda sem homologação.
- Revisão humana do 570/2026.
- Amostra inédita de edições, conferida por uma pessoa.

## 10. Próxima etapa

05.3.4 — Extração e classificação GEDIV: geometria de tabelas, colunas, completude do OCR, portarias, decisões sem
processo reconhecido e ambiguidades.
