# Preparação para publicação na internet — 17/11/2026

## Versão e proposta

Continuação do commit `bd69223f62380ec9264918a8b0f0de33b63af75d`, na branch
`entrega/painel-completo-referencias`. A interface e as 12 referências inventariadas
foram preservadas. A preparação não publica nem atualiza qualquer Site.

Proposta: **novo endereço público no GitHub Pages**,
`https://gedivseadpb-boop.github.io/Observat-rio-GEDIV-CLAUDE/`.
Não é uma URL já disponibilizada. O repositório é público, não arquivado, com
permissão administrativa disponível; `has_pages=false`, consulta de configuração
Pages retorna 404 e não existe branch remota `gh-pages` nesta verificação.

O plano usa a hospedagem estática gratuita disponível para repositórios públicos,
HTTPS no domínio `github.io`, sem domínio comprado, servidor pessoal, IA paga ou
contratação adicional. Não foi habilitada cobrança. Aplicam-se os limites do GitHub
Pages; este pacote pequeno de consulta pública não executa processamento no servidor.

Referências da plataforma:
[disponibilidade, arquitetura e URL](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[publicação por branch](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site),
[HTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https).

## Pacote congelado e proteção dos dados

`scripts/preparar_github_pages.py` cria uma pasta **nova, externa ao repositório**.
Exige a branch autorizada e árvore limpa e compara os oito arquivos públicos com
seus bytes no commit. Reutiliza o gerador existente, valida novamente o contrato
público e exige preservar `dados.json` byte a byte. Recusa arquivos extras e links.

O resultado tem três entradas:

- `site/`: oito arquivos da interface e o marcador vazio `.nojekyll`.
- `GEDIV_GitHub_Pages.zip`: exatamente esses nove arquivos na raiz, sem fontes
  privadas, imagens de referência, relatórios, testes, bancos ou histórico Git.
- `MANIFESTO_PUBLICACAO.json`: SHA completo de origem, URL proposta, hashes SHA-256
  de cada arquivo e do ZIP e metadados da projeção. Não vai ao ZIP publicado.

O comando `--verificar` detecta adulteração ou inclusão posterior de arquivos no
diretório e no ZIP. O ZIP é reproduzível para os mesmos arquivos. O CI mantém apenas
`contents: read`; prepara e verifica a entrega no Linux e Windows, sem deploy.
Atributos Git e escrita explícita de LF evitam mudanças de bytes entre plataformas.

A aprovação deve se referir ao commit e ao pacote congelado entregues, e não a
um novo build com dados posteriores. Os hashes verificam integridade; não substituem
a revisão do conteúdo nem a autorização da responsável.

## Projeção a disponibilizar

SHA-256 do JSON preservado:
`cf6c3f05cee91d9f0690cbe2a17de9781194d27601364ad66e45f70f57b42884`.
Contrato 1, origem `dados_reais`, experimental, regras `gediv-2026.11.14-1`.
Geração comprovada no arquivo: **16/11/2026 às 18:40:56, horário de Brasília**.

São **19 edições e 884 páginas**, com extremos documentais de **01/10 a 14/11/2026**;
histórico parcial desde 01/01/2026. Os extremos não comprovam cobertura de todos
os dias. A projeção informa cinco edições com ausência técnica proposta de atos
pertinentes e uma inconclusiva; isso não confirma ausência de edição, homologação
humana nem permite calcular o número total de edições pendentes no calendário.
Não há matriz por edição nem relação pública de PDFs processados.

Existem seis células mensais publicáveis: decisões provisórias em faixas, resumo
geral 210–214, atos e publicações pendentes 35–39. Conferidas registradas: zero.
Progressão tem resumo 190–194; Tempo de Serviço, 15–19, sem células divulgáveis por
TS-01 a TS-07. Célula suprimida não representa zero. Resultados por decisão,
resenhas, processos e fontes individuais não foram inventados nem acrescentados.

A lista fechada do contrato exclui nomes, matrículas, números de processo,
justificativas, identificadores documentais e texto livre. O navegador consulta
somente o JSON estático, sem conexão com MCP, R2 ou API privada. Exportações usam
essa mesma seleção de agregados e conservam as faixas e avisos de conferência.

## Carregamento e navegação

JS/CSS têm caminhos `./` e hashes de conteúdo nas URLs. O JSON é solicitado com
`cache: no-cache`; Atualizar relê a projeção disponível. Não há service worker nem
dependência externa no carregamento da interface. Os cabeçalhos do CDN definitivo
e a revalidação HTTP ainda serão conferidos após publicação autorizada; não se
promete controle de cabeçalhos que o GitHub Pages não oferece.

As áreas usam fragmentos, como `/Observat-rio-GEDIV-CLAUDE/#historico`. Esse é o
endereço direto suportado, inclusive após recarregar; não se presume que
`/historico` seja uma rota de servidor. A validação local deve servir o pacote no
mesmo subdiretório do futuro endereço para detectar referências incorretas à raiz.

Os testes visuais e funcionais da interface e exportações já constam em
[22-validacao-visual-painel.md](22-validacao-visual-painel.md). Nesta etapa, os novos
testes se concentram em integridade, privacidade e subcaminho da hospedagem.
O teste de falha 503 e recuperação anterior continua aplicável: o código da
interface e o JSON não foram modificados nesta preparação.

### Resultado dos testes desta preparação

O pacote foi aberto em Chromium em
`http://127.0.0.1:8767/Observat-rio-GEDIV-CLAUDE/#historico`, com JavaScript ativo.
A abertura direta e a recarga preservaram Histórico, indicadores e cobertura real.
Retorno à Visão geral mostrou os gráficos; aplicar GAJ mostrou uma linha, quatro
SVGs e a faixa 25–29. O CSV baixado pelo botão real conservou GAJ e 25–29, sem
linhas de outros grupos. Limpar restaurou 210–214. A área gerencial exibiu
`NÃO HABILITADA (SEGURANÇA)`.

Os sete recursos HTTP da página (CSS, quatro scripts, logo e JSON) retornaram 200
no subdiretório, com bytes iguais aos do pacote; o JSON mantém o hash acima.
JS/CSS conservaram suas versões por conteúdo. Largura da janela: 1180 pixels CSS;
documento: 1165, sem rolagem horizontal da página. A execução anterior em 388 pixels
CSS, tema, falha/recuperação e quatro exportações permanece documentada no relatório 22.
Esta etapa acrescenta a prova de carregamento e exportação no subcaminho, sem repetir
toda a auditoria. Somente Chromium foi usado na verificação visual; Firefox e Safari
não foram executados nesta sessão.

Os 35 testes Python focados incluem sete novos cenários de origem/branch limpa,
reprodução do pacote, arquivos extras, adulteração, caminhos relativos, versão de
cache, contrato privado e metadados de cobertura. O workflow público executa também
os 23 testes JavaScript existentes no Linux e Windows. O primeiro pacote desta
preparação passou no [CI público](https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/44110506596).
A situação do commit final fica registrada na verificação externa da entrega.

Evidências adicionais ficam fora do repositório e do ZIP de publicação:
`VALIDACAO_SUBCAMINHO.json`, duas capturas e `filtro-GAJ-subdiretorio.csv`.
O manifesto da entrega final identifica seu SHA de origem. **Nenhum teste local
comprova a disponibilização ou o comportamento do CDN/HTTPS definitivo.**

## Execução somente depois da autorização específica

A execução técnica permanece com o assistente; a responsável precisa apenas
aprovar o endereço e conteúdo propostos. Não é necessário que ela execute Git,
Python ou configure servidores.

1. Conferir novamente os hashes do pacote, branch/SHA remoto e ausência de
   Pages e `gh-pages`; se surgir configuração inesperada, não a substituir.
2. Criar `gh-pages` contendo **somente os nove arquivos do pacote aprovado**,
   sem copiar a árvore ou histórico do projeto; preservar a branch de entrega.
   Ativar Pages com origem na raiz dessa branch e HTTPS. Essa operação está
   pendente e só será executada após autorização.
3. Aguardar a implantação do GitHub e testar o endereço HTTPS em navegador
   externo: carregamento do JSON aprovado, gráficos, filtros, tabelas, temas,
   exports, cobertura, atualização, acesso direto por fragmento e tela estreita.
   Comparar os bytes remotos com o manifesto, verificando também cache e MIME.
4. Só então declarar a versão disponibilizada e fornecer o link funcional.
   Se a implantação falhar, diagnosticar nesse endereço, sem alterar os Sites antigos.

Não haverá merge na `main`, force-push, modificação de branch experimental,
alteração de audiência, DNS ou publicação nos Sites existentes. Atualizações
futuras da branch de código **não** atualizam o Pages por este CI; a branch de
publicação só receberá novos pacotes aprovados. Não se agenda coleta nesta tarefa.

## Pendências preservadas

- Publicação externa e teste final HTTPS: aguardam autorização do endereço proposto.
- Área gerencial e consultas individuais: não habilitadas; exigem autenticação,
  autorização no servidor, auditoria e validação da integração.
- Automação diária: não comprovada, não habilitada nem anunciada como operacional.
- Recuperação histórica e metadados documentais: cobertura parcial; exigem trabalho
  de dados e validação, sem substituir lacunas por exemplos das referências.
- Conferência Privada: nenhuma configuração, rota, permissão ou dado alterado.
  O risco identificado anteriormente e a correção isolada continuam registrados
  no relatório reservado da entrega; sua implantação é uma decisão separada.
