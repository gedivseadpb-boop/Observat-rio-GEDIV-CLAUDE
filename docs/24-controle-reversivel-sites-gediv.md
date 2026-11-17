# Controle reversível dos Sites GEDIV

O controle preserva versões e publicação sem apagar repositórios, branches, commits, dados ou o Site Conferência Privada. Ele não escolhe nem desativa um site por conta própria.

## Situação inicial

O único site cadastrado hoje é o Painel Público GEDIV no GitHub Pages: `https://gedivseadpb-boop.github.io/Observat-rio-GEDIV-CLAUDE/`. A publicação vem do commit isolado `80931323551f0711d26ca2d1c9addc6ecb0926ad` na branch `gh-pages`, com somente os nove arquivos públicos aprovados.

Ainda não existe um segundo dashboard público independente cadastrado. A Conferência Privada não é candidato, pois tem dados e controles de acesso próprios e está excluída do módulo. O segundo site só será cadastrado depois de possuir repositório próprio, URL HTTPS, origem de publicação e lista fechada de arquivos públicos.

## Guardas antes de desativar

O cadastro em `config/sites-gediv.json` obriga os dashboards comparados a apontar para a mesma projeção pública oficial. Antes de retirar um secundário da internet, o mecanismo exige vencedor explícito, prova recente das tarefas do vencedor, hashes do que está no ar, independência da fonte oficial, cópia íntegra do secundário e plano válido com autorização específica.

A cópia inclui bundle Git completo, ZIP exato da publicação, configuração Pages, workflows e manifesto SHA-256. Depois congela automações de publicação, remove somente Pages e confirma HTTP 404/410 do secundário; a fonte oficial e os workflows de dados/testes continuam ativos.

Reativação usa os bytes arquivados em branch determinística, não `main`, `HEAD` ou um build novo. Backups, planos, autorizações e diário ficam fora do repositório público em `--controle`, sem segredos ou dados pessoais.

## Pedidos disponíveis ao Claude

| Pedido | Resultado |
| --- | --- |
| “Claude, verificar sites GEDIV.” | Informa URLs, versões, dados e situação. Não altera nada. |
| “Claude, cadastre este segundo site GEDIV.” | Verifica independência antes de cadastrá-lo. Não escolhe vencedor. |
| “Claude, escolha SITE-A como definitivo e SITE-B como secundário.” | Registra os papéis sem desativar. |
| “Claude, prepare a desativação do site que não escolhi.” | Preserva e testa; gera plano identificado. Não retira o site. |
| “Claude, desative o site que não escolhi e preserve tudo.” | Exige autorização específica vinculada ao plano. |
| “Claude, reative o site arquivado.” | Restaura a versão preservada após novo plano e autorização. |

A frase de desativação não pode atingir o vencedor: o alvo fica definido previamente e o código recusa IDs iguais, cadastro alterado, hashes divergentes, ausência de backup e mudança nos dados do vencedor.

## Limites

Os testes simulam GitHub Pages para comprovar preservação, adulteração, dependência externa, plano expirado, alvo trocado e recuperação sem rebuild. Eles não executam `DELETE /pages` em produção. A Conferência Privada não é modificada, e automação diária, recuperação histórica e integração gerencial seguem fora deste módulo.
