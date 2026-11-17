# Homologação GEDIV — 17/11/2026

Destino autorizado exclusivamente pela responsável: https://gedivseadpb-boop.github.io/gediv-painel-redesign-preview/ . Versão `2026.11.17-h1`. Não representa aprovação do design definitivo.

O pacote recuperado da prévia `cae5b18ede3af64c10af3b76a8bbdece08e8f62f` registra origem informada `f657cb2`. A branch `redesign/painel-publico-observatorio-doe` não estava no remoto consultado. Preservamos integralmente esse pacote no histórico da homologação, além das branches de preservação existentes. Esta entrega continua o frontend recuperado; o painel-v2 permanece preservado no repositório fonte.

Implementado: calendário de intervalo com dois meses no desktop e um no celular; Aplicar/Cancelar/Limpar; atalhos em horário de Brasília e navegação por teclado. Datas diárias ou parciais mantêm a seleção e explicam a impossibilidade de usar totais mensais. Períodos sem cobertura não viram zero. Estado público dos filtros na URL e restauração por Voltar/Avançar. Correções dos botões de ajuda dos indicadores, da unidade de atos, de dados fixos sem fonte e da largura do layout móvel/notebook. Removida referência documental individual de Pendências que não pertencia à projeção agregada.

Dados preservados byte a byte: SHA-256 `cf6c3f05cee91d9f0690cbe2a17de9781194d27601364ad66e45f70f57b42884`. Projeção de 16/11/2026 às 18h40 (Brasília), 19 edições e 884 páginas, cobertura parcial de 01/10 a 14/11. Não houve coleta, geração de novos dados ou conexão gerencial. Processos, resenhas distintas, mérito individual e eventos vinculados continuam indisponíveis nesta projeção.

O pacote tem somente 11 arquivos públicos, incluindo os dois módulos de calendário e `.nojekyll`. O gerador `scripts/preparar_homologacao.py` valida o contrato estrito Python, a lista de arquivos e os hashes dos recursos antes de gerar ZIP e manifesto fora do site. Não publica automaticamente.

Validação: 28 testes Python de privacidade/publicação/distribuição; testes JavaScript de contrato e exportação; 21 verificações locais de aceitação em Chromium com JavaScript ativo, downloads CSV/XLSX/PDF/PNG, calendário, filtros, cliques, tabelas, erro e recuperação, histórico da navegação, temas e larguras de 320/390/768/1024 px. A suíte `tests/test_homologacao_navegador.cjs` aceita `BASE_URL`, `TEST_TAG`, `EVIDENCE_DIR` e `CHROMIUM_PATH`. Playwright é dependência apenas do ambiente de testes; nenhum pacote foi adicionado ao navegador público. Resultados e capturas ficam fora da distribuição.

Publicação prevista: apenas avanço normal da branch `gh-pages` do repositório `gediv-painel-redesign-preview`, cuja configuração Pages já usa essa branch. Nenhum merge, force-push, alteração de main ou da hospedagem oficial. Restauração possível a partir do commit anterior, preservando o histórico por um novo commit. Não houve alteração da Conferência Privada, do seu acesso ou de qualquer serviço pago.

## Publicação realizada e verificada no HTTPS

A responsável incluiu o repositório da prévia na instalação GitHub. Publicado exatamente o commit `2a71073dd7a60cdee4bf1684c634008ae0f80bb1` por avanço normal de `gh-pages`, sem alterações de código. Build Pages concluído (`built`). Endereço: https://gedivseadpb-boop.github.io/gediv-painel-redesign-preview/#geral . Os onze arquivos HTTPS retornam HTTP200 e hashes idênticos ao manifesto aprovado.

Verificados no Chrome gerenciado com JavaScript ativo e TLS válido: identificação H1; dados canônicos carregados; calendário com aplicação/cancelamento; data diária sem total mensal; filtro GAJ25–29; indicadores coerentes; clique direto na legenda Vertical; clique em barra mensal; paginação, busca e detalhe de agregados; sete serviços TS; downloads CSV/XLSX/PDF/PNG. Os arquivos CSV, Excel e PDF exportados contêm o filtro GAJ e a faixa25–29; assinaturas dos quatro formatos válidas.

A suíte headless HTTPS encontrou trust store próprio sem a CA atual do ambiente; não houve bypass nem alteração de certificados. A rodada online foi feita no Chrome gerenciado. Os21 testes automatizados anteriores continuam classificados como locais, incluindo320/390/768/1024px. Emulação DevTools não foi usada após o navegador informar bloqueio pela organização.

A comparação final comprovou os oito arquivos públicos e refs main/gh-pages do painel oficial inalterados. A main da prévia continua em `cae5b18ede3af64c10af3b76a8bbdece08e8f62f`. Não houve interação com a Conferência Privada. A publicação de homologação não constitui aprovação do design definitivo.
