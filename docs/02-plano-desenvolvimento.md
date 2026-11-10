# Plano de desenvolvimento — Painel de Publicações DOE-PB GEDIV

Versão de 10/11/2026. Substitui a estratégia de migração descrita no documento 01:
**o sistema é escrito do zero**; os repositórios anteriores servem apenas como referência.

## 1. Princípios

1. Código inteiramente novo neste repositório. Nada é copiado dos projetos anteriores.
2. Um módulo só é considerado pronto depois de testado **neste** projeto. O que os projetos
   anteriores registraram como bem-sucedido é tratado como indicação, não como prova.
3. Cada etapa termina com critérios objetivos de validação e um registro do que foi
   executado, do que foi apenas proposto e do que ficou pendente.
4. Nenhuma causa é presumida. Falhas são medidas antes de se escolher a solução.
5. Simplicidade: poucas dependências, serviços gratuitos, nada de infraestrutura que a
   operação inicial não exija.
6. Dados pessoais, PDFs, banco e credenciais ficam fora do Git.

## 2. Arquitetura

```
        FONTES OFICIAIS                         PLATAFORMA (geral)                     GERÊNCIA (específico)
   A União ─┐
            ├─► coleta ─► acervo de PDFs ─► leitura ─► atos ─────────► classificação GEDIV ─► registros
   CGE/SAP ─┘     │        (SHA-256)       (colunas,   (blocos por      (eixos, grupos,         │
                  ▼                          OCR)       órgão/resenha)   resultados)            ▼
            banco de dados ◄──────────────────────────────────────────────────────────── revisão humana
                  │                                                                             │
                  └──────────────► indicadores ◄── somente registros aprovados ◄────────────────┘
                                        │
                                   dashboard web
```

Regra de separação: tudo o que está à esquerda da classificação não conhece a GEDIV.
As regras da gerência (termos de identificação, eixos, tipos, grupos, campos) ficam em um
pacote próprio de configuração e código. Uma nova gerência, no futuro, acrescenta o seu
pacote e reutiliza o restante.

### Estrutura do repositório

| Pasta | Conteúdo | Situação |
|---|---|---|
| `observatorio/nucleo/` | Verificação de PDF, acervo, banco, rede | **Etapa 1 — implementado** |
| `observatorio/coleta/` | Fontes, coletor, inventário, importação manual | **Etapa 1 — implementado** |
| `observatorio/sonda/` | Diagnóstico de acesso às fontes | **Etapa 1 — implementado** |
| `observatorio/leitura/` | Texto por página e coluna, OCR sob demanda | **Etapa 2 — iniciado** (colunas e cabeçalho; OCR pendente) |
| `observatorio/atos/` | Segmentação da edição em atos (órgão, resenha, portaria) | Etapa 3 |
| `observatorio/gerencias/gediv/` | Identificação, eixos, campos, regras da GEDIV | Etapa 4 |
| `observatorio/conferencia/` | Segunda leitura independente e comparação | Etapa 4 |
| `observatorio/revisao/` | Fila, decisões do gerente, auditoria | Etapa 5 |
| `observatorio/web/` | API, autenticação, dashboard e painel gerencial | Etapas 5 e 6 |
| `observatorio/operacao/` | Rotina diária, backup cifrado, monitoramento | Etapa 7 |
| `tests/` | Testes automatizados | contínuo |
| `docs/` | Documentação e resultados de validação | contínuo |
| `.github/workflows/` | Testes a cada envio; sonda; rotina diária (futuro) | parcial |

### Tecnologias

| Necessidade | Escolha | Motivo |
|---|---|---|
| Linguagem | Python 3.10+ | Já usada; boa para PDF e dados. |
| Coleta | Somente biblioteca padrão | Roda em qualquer máquina com Python, sem instalar nada. |
| Banco | SQLite agora; PostgreSQL quando houver hospedagem | Arquivo único, sem servidor, sem custo. O SQL usado é compatível com a migração. |
| Leitura de PDF | pdfplumber (licença MIT), a confirmar por medição em edições reais | Entrega a posição de cada palavra, necessária para separar colunas. PyMuPDF (AGPL) fica como alternativa se a qualidade ou a velocidade não bastarem. |
| OCR | Tesseract com idioma português, só quando a página não tiver texto | Gratuito. |
| Web | A decidir na Etapa 5 | Depende da hospedagem escolhida. |

## 3. Etapas

Cada etapa só começa depois de a anterior cumprir os critérios, salvo quando forem
tecnicamente independentes.

### Etapa 1 — Coleta e integridade dos documentos (em andamento)

Entregas: descoberta das edições nas duas fontes, download, verificação estrutural, acervo
por SHA-256, registro em banco, histórico de versões, inventário de cobertura, importação
manual e sonda de diagnóstico.

| Critério | Situação em 10/11/2026 |
|---|---|
| Reexecução não baixa nem registra em duplicidade | Testado (automatizado) |
| Arquivo inválido ou truncado não entra no acervo | Testado (automatizado) |
| Falha de download é registrada e recuperada depois | Testado (automatizado) |
| Listagem inacessível não é confundida com "sem publicação" | Testado (automatizado) |
| Mesmo arquivo em duas fontes conta como um documento | Testado (automatizado) |
| Conteúdo alterado no mesmo endereço preserva o original | Testado (automatizado) |
| Somente servidores oficiais, inclusive após redirecionamento | Testado (automatizado) |
| Funciona em Linux e Windows | Testado no GitHub Actions |
| Leitura das listagens **reais** das fontes | **Pendente** — depende de executor com acesso |
| Download de PDF **real** com verificação | **Pendente** — idem |
| Inventário de 01/01/2026 até hoje | **Pendente** — idem |

### Etapa 2 — Leitura dos PDFs

Texto por página preservando a ordem das colunas; detecção de página sem texto; OCR apenas
nessas páginas; número e data da edição lidos do próprio documento; contagem de páginas.
Critérios: em uma amostra de edições reais escolhida pela GEDIV, 100% das páginas são
lidas ou marcadas explicitamente como ilegíveis; nenhuma linha de uma coluna é misturada com
a coluna vizinha nas páginas conferidas manualmente; o número da edição lido coincide com o
impresso.

### Etapa 3 — Segmentação em atos

Divide cada edição em blocos (órgão emissor → ato → corpo), guardando página e trecho de
origem. Reconhece suplementos e mais de um arquivo no mesmo dia. Critério: em edições
conferidas, a quantidade de resenhas da SEAD encontradas coincide com a contagem manual.

### Etapa 4 — Classificação GEDIV e conferência independente

Identificação dos atos da GEDIV, eixo (Progressão Funcional ou Tempo de Serviço), campos
de cada eixo, resultado, grupo/PCCR, retificações e republicações. Uma segunda leitura, por
caminho diferente, confere processos e decisões; divergência envia o registro à revisão.
Tudo o que for incerto ou ausente é marcado, nunca preenchido. Critérios: conjunto de casos
de teste aprovado pela GEDIV; processos distintos contados separadamente de atos;
retificação nunca apaga o ato original.

### Etapa 5 — Revisão gerencial

Fila de pendências com o trecho original ao lado, as doze decisões previstas, usuários
individuais, trilha de auditoria e reversão. Critérios: acesso negado sem credencial e
entre perfis; toda decisão registra autor, momento, estado anterior e posterior.

### Etapa 6 — Dashboard

Indicadores com fórmulas documentadas, filtros combináveis, calendário, exportação
Excel/PDF. Só entram registros aprovados. Critério: cada número exibido pode ser
reconstruído a partir da lista de registros que o compõem.

### Etapa 7 — Automação e operação

Execução diária com novas tentativas, backup cifrado testado por restauração, painel de
saúde (última execução, pendências, falhas).

### Etapa 8 — Hospedagem e aperfeiçoamento contínuo

Publicação web com HTTPS e autenticação; uso das correções validadas como casos de teste
permanentes e como base para melhorar as regras, sempre com comparação antes/depois.

### Fase futura — outras gerências

Não implementada. A preparação consiste em manter a fronteira descrita na seção 2.

## 4. Conhecimentos aproveitados dos projetos anteriores

Aproveita-se a **ideia**, não o código. A coluna "Evidência anterior" indica o que os
relatórios antigos registraram; a coluna "Neste projeto" indica o que já foi verificado aqui.

| Lição | Evidência anterior | Neste projeto |
|---|---|---|
| Ler a página por colunas evita misturar atos de órgãos diferentes | Documentada (99 candidatos em 2 edições) | A implementar e medir (Etapa 2) |
| OCR só quando a página não tem texto | Documentada; OCR nunca homologado em documento real | A implementar e medir (Etapa 2) |
| Segunda leitura independente para conferir registros | Documentada | A implementar (Etapa 4) |
| Identificador estável por conteúdo impede duplicidade | Documentada | **Verificado** na coleta (SHA-256) |
| Importação manual de PDF com as mesmas validações | Documentada | **Verificado** (teste automatizado) |
| Nova leitura com resultado pior não substitui a anterior | Documentada | **Verificado** para arquivos (versões preservadas) |
| Backup cifrado com teste de restauração | Documentada | A implementar (Etapa 7) |
| Perfis separados de revisão e gerência | Documentada | A implementar (Etapa 5) |
| Indicadores só com registros aprovados | Documentada | A implementar (Etapa 6) |
| O mesmo documento aparece com `/view` e `/@@download/file` | Documentada e visível no índice de busca | **Verificado** com listagem sintética; falta a página real |
| A pasta do ano nem sempre é o ano (2025 = `2025-1`) | Visível no índice de busca | Tratado por configuração |
| Há edições aos sábados e arquivos `-portal-1` | Visível no índice de busca | Tratado: nenhum dia é presumido sem publicação |

### Erros a não repetir

| Erro observado | Como o novo projeto evita |
|---|---|
| Um arquivo de 47 KB concentrava descoberta, download, leitura, regras e relatório | Módulos pequenos com uma responsabilidade cada |
| Estado guardado em um único arquivo JSON | Banco de dados desde a primeira etapa |
| Trabalho espalhado em 11 branches sem integração à principal | Uma branch por etapa, integrada quando os testes passam |
| Muitos experimentos para contornar a falha de download sem medir a causa | Sonda por camada antes de qualquer solução |
| Testes dependentes de PDFs reais que só existiam em uma máquina | Testes com dados sintéticos; PDFs reais apenas em validação local |
| Regras da GEDIV misturadas ao leitor de PDF | Fronteira explícita entre plataforma e gerência |
| "Funciona" registrado sem indicar onde e como foi testado | Tabelas de critérios com situação e data |

## 5. Investigação do acesso às fontes

O que estava em aberto: por que os executores anteriores não conseguiam baixar os PDFs.
Em vez de presumir a causa, a sonda (`python -m observatorio.sonda`) testa cada camada
separadamente. Hipóteses e como cada uma é distinguida:

| Hipótese | O que a sonda observaria |
|---|---|
| H1. Nome não resolve (DNS) | Falha na etapa DNS |
| H2. Problema apenas em IPv6 | IPv4 conecta, IPv6 não |
| H3. Filtro de rede por origem da conexão | DNS ok; TCP expira nas portas 80 e 443; controles funcionam |
| H4. Somente HTTPS bloqueado | Porta 80 conecta, 443 não |
| H5. Certificado ou protocolo TLS | TCP conecta; TLS falha |
| H6. Bloqueio por identificação do programa | HTTP responde com erro para o robô e normalmente para navegador |
| H7. Proteção anti-robô (exige navegador) | HTTP 200 com página de verificação em vez do conteúdo |
| H8. Indisponibilidade momentânea | Resultado muda entre execuções em horários diferentes |
| H9. Restrição declarada no robots.txt | Regras do arquivo listadas no relatório |

Os resultados medidos ficam em `docs/03-etapa1-resultados.md`.

## 6. Decisões que dependem da responsável

1. Visibilidade do repositório (hoje público). O código da coleta não contém dados
   pessoais; a decisão passa a ser necessária antes da Etapa 4, quando surgem casos de
   teste baseados em publicações reais.
2. Onde o robô será executado, depois de conhecido o resultado da sonda em rede brasileira.
3. Onde ficarão guardados o acervo de PDFs e o banco (armazenamento institucional).
4. Eventual contato institucional com A União/CGE, caso o acesso automatizado dependa de
   liberação.
