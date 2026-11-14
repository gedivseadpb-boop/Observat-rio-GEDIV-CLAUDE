# Etapa 05.3.2 — Integridade da coleta, cobertura e retomada

Data: 14/11/2026. Segundo pacote de correções das auditorias (Codex, Gemini/Antigravity e GPT Work). Cada defeito foi
conferido no código antes de ser corrigido. Os principais foram reproduzidos com dados sintéticos no código de origem
e desaparecem no código corrigido (seção 6).

## 1. Origem e branch

| Item | Valor |
|---|---|
| Commit de origem | `63e196d6747cd47edc50a6b1c47256e52afcdd05` (fim da 05.3.1; CI aprovado nos 4 ambientes, execução 28) |
| Branch | `etapa05-3/pr02-coleta-cobertura` |
| Branches anteriores | `etapa05-3/pr01-seguranca-ci-validacao`, `etapa05-1/integracao-pdfs-coleta` e `main`: não alteradas |

| Commit | Grupo | Conteúdo |
|---|---|---|
| `5098d2f` | B | HTTP 206 parcial recusado |
| `c436114` | C, D | Banco: download numa única transação, reabertura e suspensão auditadas |
| `b0a8415` | A–E | Coleta: cobertura com evidência, listagens validadas, recusa, retomada, fontes |
| `0e1b609` | E | 46 testes de regressão |

Não houve mudança de esquema: o banco continua na v7. As suspensões e reaberturas usam a tabela `auditoria`, que já
existia.

## 2. Defeitos corrigidos

### Correção 1 — Falsa cobertura (`coleta/inventario.py: cobertura, evidencia_da_fonte, escopo, manifesto`)

**Antes:**
- Qualquer varredura bem-sucedida do mês certificava todos os dias do mês, inclusive os posteriores a ela.
- `COMPLETO` dependia só do estado `BAIXADA`.
- O escopo de fontes não era declarado.

**Agora:**
- **Evidência para `COMPLETO` ou `SEM_PUBLICACAO_LISTADA`:** a varredura do mês precisa ter sido feita em todas as
  fontes consideradas, depois do dia e passada a janela de suplementos (`JANELA_SUPLEMENTOS = 3` dias).
- **Prova de cada edição para `COMPLETO`:** cada uma precisa estar `BAIXADA`, ter o arquivo registrado, verificação
  estrutural aceita e o arquivo presente no acervo com o tamanho registrado.
- **Novo estado `INTEGRIDADE_NAO_CONFIRMADA`.**
- **Motivos explícitos:** `NUNCA_LIDA`, `FONTE_INDISPONIVEL`, `LISTAGEM_PARCIAL`, `LISTAGEM_INVALIDA`,
  `DATA_NAO_IDENTIFICADA`, `FONTE_SUSPENSA`, `VARREDURA_ANTERIOR_AO_DIA`, `AGUARDANDO_JANELA_DE_SUPLEMENTOS`,
  `TENTATIVAS_ESGOTADAS`, `ARQUIVO_AUSENTE_NO_ACERVO` e `SEM_VERIFICACAO_ESTRUTURAL`.
- **Escopo declarado:** cada dia informa as fontes verificadas e as que ficaram sem evidência. O manifesto traz o
  `escopo` (fontes consideradas e configuradas, `todas_as_fontes` e um aviso quando a cobertura não é geral).
- **Código de saída:** `operacao cobertura` sai com 3 quando há lacunas.

### Correção 2 — Páginas de erro e listagens inesperadas (`coleta/fontes.py: classificar_listagem`; `coletor.descobrir_mes`, `descobrir_recentes`)

- **HTTP 200 não basta.** Sem itens, a página é classificada como `MANUTENCAO`, `BLOQUEIO`, `ERRO_NA_PAGINA`,
  `FORMATO_DESCONHECIDO` ou `VAZIA_COMPROVADA`.
- **Mês vazio só com aviso explícito:** o mês só é aceito como vazio diante de uma mensagem de pasta vazia. Nos outros
  casos, a varredura registra `LISTAGEM_INVALIDA` e o mês não é certificado.
- **Edição sem data:** fica registrada, sem data inventada, e aparece em `sem_data_identificada` no manifesto. A
  varredura registra `DATA_NAO_IDENTIFICADA`, porque a edição pode pertencer a qualquer dia.
- **Página de bloqueio:** também suspende a fonte (Correção 6).

### Correção 3 — Download parcial ou PDF inválido (`nucleo/rede.py: _uma_requisicao, _faixa_completa`; `coletor.importar_manual`; `operacao/validacao_real.py`)

- **HTTP 206:** só é aceito quando o `Content-Range` cobre o arquivo inteiro e bate com os bytes recebidos. Caso
  contrário, `RESPOSTA_PARCIAL`, com nova tentativa. Outros 2xx que não 200 são recusados.
- **Mesma verificação em toda entrada:** a importação manual e o `validar-real` passaram a usar a verificação
  estrutural completa da coleta (`pdf.verificar`). Antes, a verificação mínima aceitava PDF sem páginas.
- **Quarentena:** um arquivo com estrutura não confirmada vai para a quarentena, inclusive na importação manual.
- **Procedência:** a importação manual fica registrada no manifesto com `transporte = importacao_manual`.
- **Falha ao gravar no acervo** (`FALHA_ACERVO`): é registrada e a coleta segue para as próximas edições.
- **Versão válida preservada:** uma reverificação malsucedida mantém a publicação `BAIXADA`, com a versão válida.

### Correção 4 — Interrupções entre gravações (`banco.registrar_obtencao`; `coletor.baixar_publicacao`, `reconciliar`)

**Ordem segura das gravações:**
1. Bytes recebidos.
2. Verificação estrutural.
3. Gravação atômica no acervo (arquivo temporário seguido de substituição).
4. **Uma** transação no banco com arquivo, versão, verificação, manifesto e estado `BAIXADA`.

**Reconciliação** no início de toda coleta e de todo lote, sem acesso à rede:
- edição `BAIXADA` com o arquivo ausente ou de tamanho diferente volta à fila, e isso fica registrado na trilha;
- edição sem verificação registrada é verificada a partir do acervo;
- arquivos temporários de gravação interrompida são removidos;
- arquivos sem registro são apenas contados; nada é apagado.

### Correção 5 — Tentativas esgotadas (`banco.esgotadas`, `reabrir_publicacoes`; `coletor.reabrir_esgotadas`; `operacao reabrir`)

- **Visível na cobertura:** a edição esgotada aparece com `motivo = TENTATIVAS_ESGOTADAS`. O manifesto traz `esgotada`,
  o último erro e `ultima_tentativa_em`.
- **Sem insistência automática:** `--reverificar` não força uma edição esgotada.
- **Reabertura auditada:** só com responsável e justificativa, pelo comando
  `python -m observatorio.operacao reabrir --fonte auniao --inicio … --fim … --responsavel … --justificativa …`.

### Correção 6 — Respeito à recusa da fonte (`coletor.Guarda`; `banco.suspender_fonte`, `liberar_fonte`, `suspensao_vigente`; `lotes.executar_lote`)

- **Uma guarda por fonte em todos os caminhos:** dia, intervalo, caminho antigo, descoberta e lote.
- **O que suspende a fonte:**
  - HTTP 403 ou 429;
  - `robots.txt` que proíbe a coleta ou cuja consulta é recusada (antes, a recusa do `robots.txt` não parava o
    `coletar-intervalo`);
  - página de bloqueio reconhecida.
- **Efeito:** nenhuma nova requisição àquela fonte na execução. A edição não tentada não conta como falha.
- **Prazo da suspensão:**
  - para 429, o maior entre `Retry-After` e 1 hora;
  - para os demais casos, 24 horas.
- **Entre execuções:** a suspensão vale até o prazo vencer ou até uma liberação auditada
  (`operacao liberar-fonte`).
- **Outras fontes:** uma fonte independente não é afetada.
- **Sem contorno:** nada é feito para contornar a recusa (nenhuma troca de identidade nem proxy).

### Correção 7 — Fontes e suplementos (`coleta/fontes.py: PADRAO, selecionar`; as duas linhas de comando)

- **Padrão único:** `PADRAO = ("auniao",)` vale para a coleta e para a cobertura, nas duas linhas de comando. Antes,
  `operacao` usava `auniao` e `coleta` usava todas as fontes. A escolha explícita (`--fonte`) é preservada.
- **Documentos distintos:** principal, suplementos e edição extra continuam separados.
- **Relação entre documentos no manifesto:** `SUBSTITUIDO_NO_MESMO_ENDERECO`, `MESMO_CONTEUDO_DE_OUTRA_URL` ou
  `DOCUMENTO_DISTINTO`.
- **Fora do escopo:** a reconciliação das decisões entre versões é da 05.3.3 e não foi antecipada.

## 3. Mudanças de contrato

- **`inventario.cobertura`:** ganhou o parâmetro `acervo`. Sem ele, o acervo é localizado pela convenção
  (`pasta/acervo`); se não for localizado, nenhum dia vira `COMPLETO`.
- **Dias com novas regras:** dias antes `COMPLETO` ou `SEM_PUBLICACAO_LISTADA` podem passar a outros estados por falta
  de evidência. É a correção pedida.
- **Recusa de fonte:** após uma recusa, nem um novo piloto roda antes do prazo ou da liberação auditada.
- **Importação manual:** PDF com estrutura inválida é recusado na entrada, em vez de entrar no acervo e falhar na
  leitura.
- **Comandos novos:** `reabrir` e `liberar-fonte`.

Cinco testes antigos foram ajustados a esses contratos, com a justificativa escrita no próprio teste:
- `test_lotes`: recusa até a liberação;
- `test_aquisicao`: campos novos no manifesto;
- `test_coleta`: acervo explícito com o banco em memória;
- `test_ponta_a_ponta`: PDF corrompido recusado na importação; `bug017` com PDF real em vez de registro fictício.

## 4. Preservado

- **Correções da 05.3.1:** projeção pública, fechamento de conexões, validador do corpus e códigos de saída.
- **Acervo e versões:** acervo por SHA-256, quarentena e histórico de versões.
- **Leitura:** OCR com limite de tempo e uma thread.
- **Classificação:** regras GEDIV (dois eixos, 16 grupos, 7 assuntos) inalteradas.
- **Revisões humanas e painel:** sem alteração.
- **Esquema:** continua v7.
- **Edições oficiais:** relidas com o código desta etapa, dão a mesma classificação (seção 6).

## 5. Testes

- **`tests/test_coleta_cobertura.py`:** 46 testes novos, todos com respostas HTTP simuladas e PDFs sintéticos.
- **Suíte completa:** 366 testes (320 anteriores mais 46 novos).

## 6. Evidências antes e depois (reprodução sintética)

| Cenário | Origem `63e196d` | Corrigido |
|---|---|---|
| Listagem de manutenção com HTTP 200 | dia `SEM_PUBLICACAO_LISTADA` | `NAO_VERIFICADO` |
| Requisições à fonte depois de 429 na 1ª listagem | 5 | 0 |
| HTTP 206 parcial | tratado como transferência completa | `FALHA_DOWNLOAD` (`RESPOSTA_PARCIAL`), com nova tentativa |
| Importação manual de PDF sem páginas | aceita | recusada (quarentena) |
| PDF apagado do acervo | dia `COMPLETO` | `INTEGRIDADE_NAO_CONFIRMADA` |
| Queda entre gravações | `BAIXADA` sem verificação, nunca mais revisitada | continua pendente; baixada na execução seguinte |

## 7. Resultados

Ver o relatório de entrega da etapa: números locais, conjunto-ouro e corpus com os PDFs oficiais (fora do
repositório) e os quatro jobs do CI no commit final.

## 8. Riscos residuais e limitações

- **Marcadores das páginas:** foram definidos por padrões genéricos (manutenção, bloqueio, pasta vazia). Uma página
  real de "pasta vazia" com texto diferente será tratada como inválida, e não como vazia. Esse é o lado seguro, mas
  pode deixar meses legítimos sem certificar até o padrão ser confirmado na fonte.
- **Janela de suplementos:** os 3 dias são uma escolha técnica conservadora, ainda não validada com dados reais de
  suplementos tardios.
- **Prazo de suspensão:** os 24 horas para 403, `robots.txt` e bloqueio são uma escolha conservadora, e a liberação
  antecipada exige decisão humana.
- **Teste em ambiente real:** a coleta não foi executada contra os portais oficiais nesta etapa, por proibição
  expressa. O comportamento em produção depende de homologação (05.3.5).

## 9. Fora do escopo (05.3.3 e seguintes)

- Releitura e reclassificação quando o texto muda.
- Versionamento de leituras e preservação da última leitura válida.
- Reconciliação das decisões entre versões de PDF e prevenção de duplicidade nos indicadores.
- Migrações concorrentes.
- Revisão humana de todos os campos.
- Extração e OCR (05.3.4).

## 10. Retomada após qualquer interrupção

1. Execute de novo o mesmo comando: a reconciliação roda sozinha.
2. Consulte `operacao cobertura` para ver lacunas e motivos.
3. Use `operacao reabrir` para edições esgotadas e `operacao liberar-fonte` para encerrar uma suspensão antes do
   prazo. As duas exigem responsável e justificativa.

## 11. Próxima etapa

05.3.3 — Leitura, banco e reconciliação de revisões humanas.
