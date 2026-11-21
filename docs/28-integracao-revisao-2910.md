# Integração da Revisão Interativa de 29/10

## Código original e preservação

O projeto Sites `appgprj_6ae3c7918eb88191853fa71f7e58fd66` está acessível como proprietária. A versão publicada 1 aponta para o commit original `40ded4649c83f34d2eb1457ec1cc80a0a982fc75`. O repositório foi clonado somente para leitura; não houve push, salvamento de versão ou deploy nesse Site. A candidata independente está em `revisao-2910/`, na branch `integracao/revisao-2910-dados-workflows` do repositório canônico.

O CSS e a logomarca foram preservados byte a byte. `origem-visual.json` fixa seus hashes e a hierarquia estática original: ordem dos elementos, IDs, classes e estilos inline. Os testes comparam a candidata com essas invariantes. Não foram trocados componentes, fontes, paleta ou disposição. Rótulos, conteúdo e gráficos passaram a expressar agregados mensais protegidos. O original tem somente tema claro; não foi inventado um segundo tema.

O arquivo `data.js` do protótipo **não foi copiado**. Nenhum registro da amostra, nome, processo, matrícula ou resenha individual alimenta a candidata. A referência foi aberta em Chrome real e capturada antes das alterações. O preview gerenciado deste ambiente falhou por timeout do relay; não foi substituído por um servidor paralelo nem apresentado localhost como entrega. O workflow isolado testa a candidata em Chrome real no GitHub Actions e guarda capturas públicas de desktop/celular.

Oficial `main=278abd68a3cb7846c54a08f460b2a064a6c59677` e `gh-pages=80931323551f0711d26ca2d1c9addc6ecb0926ad`; Clareza `gh-pages=53a5adea66233b8e7728fef11ef9dbec7005b412`; H1 restaurável em `backup/h1-2026-11-17=2a71073dd7a60cdee4bf1684c634008ae0f80bb1`. Não houve interação com a Conferência Privada nem alterações nesses destinos.

## Dados e comportamento implementados

A camada `adapter.js` traduz os controles originais para `GedivModelo`, o contrato público já existente. O código-fonte lê a projeção pública canônica do painel oficial; o empacotador usa uma cópia derivada dessa projeção validada, servida na mesma origem, sem outra base principal. Os controles operam sobre essa única projeção. A candidata é somente leitura.

- Decisões e atos permanecem unidades distintas. Contagens positivas continuam em faixas. Não se expandem células em pessoas fictícias.
- Período, eixo, modalidade, grupo, sete serviços TS, busca e cliques em gráficos atualizam os agregados compatíveis. Clique em barra mensal seleciona o mês inteiro, sem atribuir o total ao dia.
- Um dia específico, um resultado de mérito ou um evento não suportado mostra limitação e `—`, nunca zero inventado.
- Processos, resenhas, deferimentos, indeferimentos, refeitos, tornados sem efeito e republicações por incorreção não estão discriminados no contrato público atual. Não foram inferidos dos totais.
- A consulta individual abre uma explicação no modal original. Não existe login fictício nem endpoint individual público.
- CSV, XLSX, impressão/PDF e PNG usam somente agregados e o mesmo recorte. A aparência original dos controles e da exportação foi mantida, com rótulos corretos.
- A releitura automática usa `cache: no-store`, cinco minutos, apenas com a página visível; falhas apagam os totais e impedem exportação; nova leitura preserva filtros. Releitura não significa coleta de novas edições.
- O pacote público tem lista fixa de arquivos e validação estrita do JSON. Não contém SQLite, PDFs, amostra de protótipo, documentos privados ou credenciais.

A projeção disponível permanece a de **16/11/2026, 18:40 Brasília**, com 19 edições, 884 páginas e cobertura parcial de 01/10 a 14/11/2026. Não foi localizada projeção mais nova comprovada. A data de geração não comprova edição nova nem conferência humana.

## Onde está a base e o que funciona

Não foi encontrado `observatorio.sqlite3` GEDIV nos arquivos acessíveis em `/workspace/gediv`, `shared`, `attachments` e `/tmp`. O repositório ignora `dados/`, SQLite e PDFs. Não existe manifesto de backup com localização, hash e teste de restauração que comprove uma cópia persistente fora dos ambientes temporários. **Isso não prova que a base foi perdida; significa que sua localização e recuperabilidade não puderam ser confirmadas.** Não se inspecionaram dados da Conferência Privada ou de protótipos como atalho.

A integração GitHub disponibilizou dois repositórios públicos. Não foi identificado repositório privado de armazenamento dentre os autorizados. A API de runners retornou **403 Resource not accessible by integration**; a listagem de executores próprios não pôde ser confirmada. Não é correto afirmar que não existem runners em toda a conta. Nos YAMLs disponíveis só aparecem executores hospedados do GitHub, sem armazenamento privado durável ou agendamento de coleta.

Os 11 artifacts existentes no repositório, consultados em 18/11/2026, são exclusivamente relatórios pequenos de sonda. Nenhum é backup identificado da base ou acervo. Artifacts com expiração não devem ser tratados como armazenamento principal.

| Workflow/etapa | Evidência observada | O que comprova |
|---|---|---|
| Testes | [run 44331615057](https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/44331615057), 18/11, sucesso | Regressão de código, não atualização do acervo |
| Painel público | [run 44131797953](https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/44131797953), 17/11, sucesso | Validação e empacotamento do snapshot já versionado |
| Sonda | [run 42934585756](https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/42934585756), 10/11 às 21:51 Brasília | Diagnóstico de rede executado; não coleta |
| Pages | Deploy oficial existente e deploy Clareza preservados | Publicação de arquivos estáticos, não execução da coleta |
| Coleta diária completa | Nenhum cron encontrado nos workflows atuais | Operação diária não comprovada |

Nos logs reais da Sonda, Windows, Ubuntu e macOS falharam em TCP/443 para A União, www A União e CGE. O portal Paraíba apresentou verificação anti-robô; os controles GitHub e gov.br responderam. Não houve contorno. O YAML usa `python ... || echo`, por isso o status verde mascara a falha de acesso relatada nos logs. O workflow existente não foi alterado nesta tarefa.

O pipeline reutilizável é `coleta` → validação estrutural/hash/quarentena → `leitura` texto/OCR → classificação GEDIV → revisão humana auditada → `painel.publicacao.projetar` → contrato público. O comando `observatorio.operacao executar` reaproveita SQLite/acervo existentes e preserva revisão e conflitos. Há código de backend com contas, sessões e auditoria; isso não comprova implantação institucional HTTPS.

O novo workflow `Candidata Revisão 29-10 (sem deploy)` usa somente o snapshot público, contrato e testes. Gera pacote e evidências; não faz coleta, não grava base, não publica, não muda `main`. Suas execuções reais são CI da candidata, não prova de rotina diária operacional.

## Validação da candidata

- 13 testes de integração DOM aprovados: fonte real, integridade do visual estático, filtros, busca, meses/dias, cliques, proteção de consultas individuais, exportações, erro/recuperação e releitura mantendo filtros.
- 46 testes JavaScript existentes aprovados localmente e 15 testes Python de privacidade/distribuição aprovados localmente e no CI da candidata.
- [Execução real aprovada 44338823631](https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/44338823631): Chrome em 1440 e 390 px, sete visões, datas nativas, filtro GAJ, arquivos CSV/XLSX/PNG/PDF e ausência de erros JavaScript. Largura da página igual à viewport em ambos os casos. A barra de abas mantém a rolagem interna original no celular.
- O primeiro run encontrou transbordamento por um texto de indisponibilidade maior que o espaço original. O rótulo foi encurtado; nenhum CSS foi modificado. O teste posterior passou.
- Capturas e downloads reais estão nos artifacts `evidencias-revisao-2910-publicas` e `candidata-revisao-2910-publica` desse run. São temporários para QA e não backups de acervo. As capturas foram inspecionadas visualmente. CSS/logo/hierarquia fornecem comprovação estrutural; ainda falta comparação visual lado a lado em uma prévia HTTPS autorizada.
- A folha CSS/modelo e o HTML não contêm amostra demonstrativa. Não houve estudo com usuários nem certificação de acessibilidade.

## Datas que não devem ser confundidas

| Data | Fonte correta | Situação atual |
|---|---|---|
| Execução do workflow | GitHub Actions `created_at` e `updated_at` | Disponível para CI/sonda; não há rotina diária comprovada |
| Geração da projeção | JSON `atualizado_em` | 16/11/2026; regenerar não implica novos dados |
| Última edição identificada | `publicacao.data_publicacao` da base canônica | Não informada no contrato público |
| Última edição lida | Cobertura pública / leitura aceita | A cobertura chega a 14/11, sem prova da classificação de toda a edição |
| Última edição processada até classificação vigente | Leitura + classificação da base canônica | Não comprovada pelo contrato atual |
| Última conferência humana | Revisão vigente, sem conflito, timestamp de auditoria | Não informada; não substituída pela data de geração |

## Proposta mínima, ainda não implantada

Primeiro é preciso localizar e restaurar **a mesma base canônica e seu acervo**, verificando hash, esquema, integridade, revisões e conflitos. Se não houver cópia recuperável, não iniciar uma base vazia sob o nome de continuação histórica. A recuperação precisa ser tratada explicitamente com a responsável.

Uma opção a avaliar aproveita GitHub Actions em **repositório de operação privado**, separado dos repositórios públicos de apresentação, executando os mesmos módulos canônicos. A cada execução: restauração do último conjunto canônico aprovado → coleta incremental com as políticas existentes → extração/classificação → preservação das pendências humanas → novo backup criptografado e verificado → projeção allowlist → candidata pública. A base restaurada é a continuação da mesma base, não uma segunda fonte principal.

O armazenamento durável deve ser escolhido e autorizado antes da implantação. Uma possibilidade é manter backups criptografados em Releases privados com retenção explícita e manifesto; não usar artifacts/cache temporários como base permanente. A viabilidade depende do tamanho do acervo, limites e política de uso da conta. Releases não são banco transacional: usar snapshots consistentes, SQLite backup API, exclusão mútua, verificação de restauração e atualização atômica do ponteiro do último backup. É necessário também backup independente sob custódia institucional; uma única conta não basta como recuperação de desastre.

Medidas mínimas: criptografia autenticada antes de qualquer upload; chave de recuperação fora dos backups e sob custódia institucional; permissões mínimas; workflow privado manual/protegido; nenhuma execução de código de PR não confiável com acesso à base; isolamento de concorrência; falhas impedem substituição do último backup e publicação; logs sem extração textual ou identificadores; apenas projeção pública validada pode atravessar para o repositório público. A revisão humana continua pendente até realizada.

**Custo estimado:** proposta com teto inicial de **R$ 0**, condicionada às franquias já incluídas e à aceitação do armazenamento escolhido. Exemplo de dimensionamento, não medição: 30 execuções mensais de 20 minutos consumiriam 600 minutos de Linux; OCR pode exigir muito mais. Não é possível fechar custo de armazenamento sem tamanho do SQLite/acervo e retenção. Se as cotas gratuitas não comportarem a operação, não habilitar cobrança: apresentar orçamento e pedir autorização. Nenhum serviço, repositório de infraestrutura, segredo, backup remoto ou agendamento novo foi provisionado.

Antes de habilitar a opção GitHub, testar o acesso às fontes com o próprio executor: os logs anteriores mostram bloqueio de rede. Persistência não resolve conectividade. Se esse acesso continuar falhando, a alternativa é um executor institucional já autorizado com acesso às fontes e armazenamento seguro; não contornar bloqueios nem contratar servidor automaticamente.

## Liberação para avaliação e pendências

O item 9 do pedido exige autorização específica antes de qualquer publicação. A candidata está implementada em branch isolada; nenhum endereço foi atualizado. A prévia HTTPS independente exige escolher e autorizar o destino. Não será usado localhost como solução entregue.

Ainda faltam: localizar backup canônico e confirmar recuperação; autorizar armazenamento/executor; comprovar acesso às fontes; provar execuções sucessivas com persistência; conferir novos registros; produzir os indicadores ainda ausentes por contrato seguro; autorizar e testar uma prévia HTTPS independente. Não há declaração de aprovação definitiva da interface ou de atualização diária operacional.
