# Homologação GEDIV — 17/11/2026

Destino autorizado exclusivamente pela responsável: https://gedivseadpb-boop.github.io/gediv-painel-redesign-preview/ . Versão `2026.11.17-h1`. Não representa aprovação do design definitivo.

O pacote recuperado da prévia `cae5b18ede3af64c10af3b76a8bbdece08e8f62f` registra origem informada `f657cb2`. A branch `redesign/painel-publico-observatorio-doe` não estava no remoto consultado. Preservamos integralmente esse pacote no histórico da homologação, além das branches de preservação existentes. Esta entrega continua o frontend recuperado; o painel-v2 permanece preservado no repositório fonte.

Implementado: calendário de intervalo com dois meses no desktop e um no celular; Aplicar/Cancelar/Limpar; atalhos em horário de Brasília e navegação por teclado. Datas diárias ou parciais mantêm a seleção e explicam a impossibilidade de usar totais mensais. Períodos sem cobertura não viram zero. Estado público dos filtros na URL e restauração por Voltar/Avançar. Correções dos botões de ajuda dos indicadores, da unidade de atos, de dados fixos sem fonte e da largura do layout móvel/notebook. Removida referência documental individual de Pendências que não pertencia à projeção agregada.

Dados preservados byte a byte: SHA-256 `cf6c3f05cee91d9f0690cbe2a17de9781194d27601364ad66e45f70f57b42884`. Projeção de 16/11/2026 às 18h40 (Brasília), 19 edições e 884 páginas, cobertura parcial de 01/10 a 14/11. Não houve coleta, geração de novos dados ou conexão gerencial. Processos, resenhas distintas, mérito individual e eventos vinculados continuam indisponíveis nesta projeção.

O pacote tem somente 11 arquivos públicos, incluindo os dois módulos de calendário e `.nojekyll`. O gerador `scripts/preparar_homologacao.py` valida o contrato estrito Python, a lista de arquivos e os hashes dos recursos antes de gerar ZIP e manifesto fora do site. Não publica automaticamente.

Validação: 28 testes Python de privacidade/publicação/distribuição; testes JavaScript de contrato e exportação; 21 verificações locais de aceitação em Chromium com JavaScript ativo, downloads CSV/XLSX/PDF/PNG, calendário, filtros, cliques, tabelas, erro e recuperação, histórico da navegação, temas e larguras de 320/390/768/1024 px. A suíte `tests/test_homologacao_navegador.cjs` aceita `BASE_URL`, `TEST_TAG`, `EVIDENCE_DIR` e `CHROMIUM_PATH`. Playwright é dependência apenas do ambiente de testes; nenhum pacote foi adicionado ao navegador público. Resultados e capturas ficam fora da distribuição.

Publicação prevista: apenas avanço normal da branch `gh-pages` do repositório `gediv-painel-redesign-preview`, cuja configuração Pages já usa essa branch. Nenhum merge, force-push, alteração de main ou da hospedagem oficial. Restauração possível a partir do commit anterior, preservando o histórico por um novo commit. Não houve alteração da Conferência Privada, do seu acesso ou de qualquer serviço pago.

## Bloqueio da publicação

O commit local do pacote é `2a71073dd7a60cdee4bf1684c634008ae0f80bb1`. Tanto o push Git quanto a operação GitHub de criação de árvore foram recusados com HTTP403 (`Resource not accessible by integration`). Nenhuma referência remota foi atualizada. A prévia ainda serve `cae5b18ede3af64c10af3b76a8bbdece08e8f62f`; os testes HTTPS da versão nova permanecem pendentes até haver conexão com gravação. A responsável já autorizou a publicação exclusivamente na homologação; não é necessária nova autorização de design ou publicação.

A comparação final confirmou os oito arquivos públicos e refs main/gh-pages do painel oficial idênticos ao início do trabalho. Não houve acesso à Conferência Privada.
