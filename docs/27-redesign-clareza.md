# GEDIV Clareza r1 — entrega para avaliação

Versão: `2026.11.18-clareza-r1`. Branch local: `redesign/h1-clareza-institucional`. Base funcional: H1 publicada, `2a71073dd7a60cdee4bf1684c634008ae0f80bb1`. Esta revisão não foi publicada. O site de homologação continua na H1; o painel oficial, suas branches e a Conferência Privada foram preservados.

A skill foi instalada a partir dos cinco arquivos fornecidos em `.agents/skills/gediv-webdesigner-senior/`, com as três referências e o script de contraste. Foi aplicada diretamente nesta sessão. O catálogo dinâmico do executor não expôs um comando de invocação; por isso não se afirma que houve reconhecimento automático pelo catálogo. A pasta e o cabeçalho da skill estão preparados para a descoberta pelo Codex.

## O que mudou no software

| Problema observado | Correção implementada |
|---|---|
| Cores fixas e exceções conflitantes no tema escuro | Tokens semânticos independentes para os dois temas; estados e séries de gráficos harmonizados |
| Gráficos espremidos ao lado de uma coluna de consultas | Área analítica mais ampla; consultas e detalhes organizados abaixo em larguras intermediárias |
| Texto pequeno e controles apertados | Corpo de 15 px, textos auxiliares legíveis e ações principais de 44 px |
| Título institucional comprimido e metadados concorrentes | Cabeçalho reorganizado em grid, com identidade e título legíveis |
| Navegação móvel ocupava quase toda a primeira tela | Três áreas principais visíveis; outras consultas e exportação em controles nativos de um nível |
| Data, busca e totais difíceis de localizar | Três ações rápidas com ícones vetoriais, rótulos curtos e foco no destino |
| Menu perdia o estado ativo após filtros na URL | Correção de `aria-current` para URLs filtradas; botão Voltar preserva o contexto |
| Calendário escuro com texto branco sobre primário claro | Cores de texto/fundo por tema, foco, áreas de toque e rodapé de ações legíveis |
| Alguns textos mostravam números fora do recorte ou derivados sem garantia do contrato | Atos de Tempo de Serviço obedecem ao filtro; histórico usa a seleção; removida a inferência de 13 edições / 68% com atos |
| PNG exportado dependia de cores fixas e não preservava o tema | Exportação serializa cores computadas dos SVGs e mantém fundo, texto, legenda, período e faixas |

As dez seções foram percorridas nos dois temas: Visão geral, Progressão, Tempo de Serviço, Dia, Histórico, Alterações, Outras publicações, Edições/fontes e cobertura, Pendências e shell público gerencial. Se faltam dados públicos, a seção explica a indisponibilidade e não cria uma lista de documentos ou resultados individuais.

## Evidências e verificação

- Antes: 84 capturas reais preservadas, incluindo Visão Geral inteira em 1440/390 px, dois temas, calendário, tabela, modal, filtros, menu e páginas secundárias.
- Depois: 64 verificações visuais/semânticas aprovadas e 118 capturas. Larguras de 320, 390, 768, 1280 e 1440 px sem rolagem horizontal da página.
- Navegador funcional: 21 verificações aprovadas de filtros combinados, cliques, busca, tabelas, paginação, histórico, calendário, exportações e recuperação após falha.
- Avaliação heurística: 10 tarefas guiadas aprovadas (cinco por tema), incluindo selecionar período, reconhecer totais, consultar um serviço e voltar, pesquisar com filtros visíveis e exportar no celular. Não houve estudo com participantes reais.
- Contraste: 54 pares de tokens aprovados; 44 estados renderizados, sem falhas obrigatórias nos pares avaliados. As duas faixas hachuradas foram verificadas separadamente: mínimo 4,55:1 no claro e 5,07:1 no escuro. A avaliação não equivale a uma certificação WCAG integral.
- Zoom: reflow automatizado equivalente a 200% (720 CSS px / DPR 2) e inspeção com zoom nativo 200% no Chrome, nos dois temas. No teste nativo, largura de 606 CSS px, documento de 598 px, calendário de 590 px e um mês visível; não houve corte horizontal. Zoom restaurado a 100%.
- Regressão: 46 testes JavaScript e 35 testes Python de contrato, exportação, privacidade e preparação de pacotes aprovados.

Os relatórios e imagens completos ficam em `/workspace/gediv-evidencias/clareza/`. A galeria de entrega inclui os pares antes/depois e as páginas secundárias, com acesso às capturas inteiras.

## Dados, preservação e limites

`dados.json` foi preservado byte a byte: SHA-256 `cf6c3f05cee91d9f0690cbe2a17de9781194d27601364ad66e45f70f57b42884`. Continua sendo a projeção pública de 16/11/2026, com 19 edições e 884 páginas, cobertura parcial de 01/10 a 14/11. Não houve nova coleta nem alteração da base, de métricas ou de regras de privacidade.

Processos distintos, resenhas distintas, deferimentos, indeferimentos, eventos vinculados e fichas individuais continuam dependentes de dados conferidos e da camada gerencial segura. A revisão visual não libera esses dados.

`scripts/preparar_revisao_visual.py` gera somente um pacote local: os 11 arquivos públicos, manifesto, ZIP e uma cópia HTML autossuficiente para avaliação sem instalação. Essa cópia incorpora a mesma projeção pública congelada e não atualiza dados pela internet. O script não publica e não acessa o GitHub. A preparação estática existente também foi corrigida para incluir os dois arquivos do calendário.

Uma publicação desta revisão exige autorização específica para a nova versão e exclusivamente para o endereço de homologação. A autorização anterior para publicar H1 não foi usada para publicar Clareza r1.
