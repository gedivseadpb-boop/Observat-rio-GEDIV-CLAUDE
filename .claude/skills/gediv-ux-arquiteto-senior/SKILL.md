---
name: gediv-ux-arquiteto-senior
description: Implementa UX/UI, arquitetura de informação e controle reversível de publicação do Painel GEDIV.
---

# GEDIV — arquiteto sênior de UX e publicação reversível

Use esta skill para implementar interfaces públicas GEDIV, fluxo documental e comparação entre dashboards.
Leia primeiro `painel-publico/index.html`, `estilo.css`, `app.js`, `modelo.js`, `dados.json`, testes e
`docs/24-controle-reversivel-sites-gediv.md`. A tarefa do usuário prevalece sobre esta skill.

Construa fluxos reais, não apenas avaliação estética. A interface deve distinguir agregado mensal,
edição, PDF, ato, resenha, processo e decisão. Dados públicos permanecem agregados e protegidos;
camadas gerenciais exigem autenticação de servidor e nunca são simuladas no navegador.

Antes de redesenhar, faça uma passagem curta: confirme rotas distintas, campos públicos e indisponíveis,
e cinco tarefas usuais: resumo, Progressão, sete serviços, cobertura e motivo de uma consulta individual
estar indisponível. Implemente em fatias: navegação/visão geral; Progressão/Tempo; documentos/fontes;
acabamento, acessibilidade, exportações e mobile. Preserve filtros, faixas de privacidade e exportações.

## Controle reversível de sites

Nunca escolha vencedor, desative, publique ou reative por inferência. O mecanismo em
`observatorio.sites` só administra GitHub Pages estático de repositórios independentes e exclui a
Conferência Privada. Antes de desativar, deve haver vencedor explícito, prova funcional atual do vencedor,
independência da fonte oficial, backup íntegro do secundário, plano válido e autorização específica.

Use `python -m observatorio.sites verificar` para leitura. Os pedidos “desative” e “reative” exigem o
processo documentado em `docs/24-controle-reversivel-sites-gediv.md`; eles nunca apagam repositórios,
branches, commits ou dados. Cópias e autorizações ficam fora do Git público, sem segredos.

Não altere `main`, não altere a Conferência Privada e não publique uma nova versão sem autorização
explícita para esse endereço e conteúdo.
