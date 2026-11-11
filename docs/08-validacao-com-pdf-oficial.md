# Validação com PDFs oficiais do DOE-PB — 10/11/2026

Primeira execução do fluxo completo sobre Diários Oficiais reais. Este documento registra só o que
foi **executado**. Os relatórios completos, sem dados pessoais, estão em `docs/evidencias/pdf-oficial/`.

## 1. Arquivos

| Edição | Nº | Páginas | Bytes | SHA-256 |
|---|---|---|---|---|
| **02/10/2026** (principal) | 18.684 | 40 | 2.369.879 | `0f437acc186a7e808ae09f348968d99b7086ccdbcb21e87d29b7c529d8562757` |
| 01/10/2026 | 18.683 | 56 | 3.665.577 | `bb5b8b65a07243193f7f318ef05a9ed7b1a959d7e22e5bb24da851136330a18d` |
| 03/10/2026 | 18.685 | 48 | 2.366.914 | `6f436c7f204a50b4a70e727d8e1106765177d3210d123e52b9b8ac9a8d803c13` |
| 06/10/2026 | 18.686 | 28 | 2.506.423 | `915cb793a24056d65f2cd09698d9550b5a1598b2bbfd907fe390951d9579b504` |

URL oficial registrada para 02/10: `https://auniao.pb.gov.br/servicos/doe/2026/outubro/diario-oficial-02-10-2026-portal.pdf`.

**Procedência (limite importante):** os quatro PDFs foram obtidos da pasta do projeto no Google Drive.
**Não foram baixados por este sistema do servidor oficial** — em 10/11/2026 `auniao.pb.gov.br` e
`cge.pb.gov.br` continuaram sem responder a partir do **ambiente remoto de desenvolvimento** (contêiner
Linux em nuvem, com saída por proxy; a conexão é encerrada após ~10 s, por HTTPS direto, pelo espelho
da CGE e pelo leitor de páginas). Nenhuma tentativa foi feita a partir do computador da responsável
nem da rede da SEAD: esse resultado não diz nada sobre essas redes. O arquivo de 02/10 tem
exatamente o hash, o tamanho e o número de páginas que os projetos anteriores haviam registrado para
o arquivo oficial. Os originais ficam preservados no acervo privado (por SHA-256), fora do Git.

## 2. Leitura — 172 páginas

| Edição | Texto nativo | Texto + OCR do trecho | OCR da página | Qualidade | Colunas |
|---|---|---|---|---|---|
| 01/10 | 52 | 1 | 3 | 56 OK | 53 com duas, 3 com uma |
| 02/10 | 36 | 3 (p. 5, 14, 26) | 1 (p. 40) | 39 OK, 1 baixa confiança (p. 14) | 38 com duas, 1 com uma, 1 com quatro (p. 14) |
| 03/10 | 45 | 1 | 2 | 48 OK | 45 com duas, 3 com uma |
| 06/10 | 25 | 0 | 3 | 28 OK | 26 com duas, 2 com uma |

Número e data de cada edição foram lidos do próprio cabeçalho e coincidem com a data informada.
O método e a qualidade de **cada página** estão no campo `pagina_a_pagina` dos relatórios.

## 3. Resultado na edição de 02/10/2026

| Resenha | Página | Vínculo GEDIV | Classificação | Resultado | Decisões |
|---|---|---|---|---|---|
| 488/2026 | 5 | expresso | Tempo de Serviço · TS-05 Licença Especial | Indeferido | 1 |
| 504/2026 | 5 | expresso | Tempo de Serviço · TS-04 Desistência de Licença de Interesse Particular | Deferido | 1 |
| 473/2026 | 5 | expresso | Tempo de Serviço · TS-01 Anotação de Tempo de Serviço/Contribuição | Deferido | 4 |
| 470/2026 | 5 | expresso | Tempo de Serviço · TS-05 Licença Especial | Deferido | 1 |

- **4 resenhas, 7 decisões, 7 processos distintos**; processo, servidor, matrícula e lotação preenchidos
  nas 7; dias/períodos em 5 (as duas restantes não publicam esses dados).
- Resenhas 505/2026 e 506/2026 (p. 4): GEDIV expressa, licenças por perícia médica — **fora dos dois
  eixos**, listadas em "Outras publicações", sem gerar decisão.
- Resenha 116/2026/GOCESP (p. 4): outra gerência, não atribuída à GEDIV.
- Nenhum evento de alteração nesta edição.
- **Banco:** 4 atos, 7 decisões, todas `PENDENTE`. **Nenhum registro foi conferido automaticamente.**
- **Painel:** consulta pública = todos os indicadores em zero (nada conferido); visão "em conferência"
  da gerência para 02/10 = 7 processos, 4 resenhas, 7 decisões, 6 deferidos, 1 indeferido; Refeitos e
  Tornados sem efeito não calculados em dados preliminares.

### Conferência manual da amostra

Feita pelo desenvolvedor (não pela GEDIV), comparando a extração com a imagem das páginas 4 e 5:

| Item conferido | Resultado |
|---|---|
| Número, expediente e preâmbulo das 4 resenhas | conferem (o expediente da 504 não foi capturado: está em linha separada do cabeçalho) |
| 7 linhas: processo, matrícula, nome, lotação | 7 de 7 conferem |
| Dias da resenha 473 (privada/federal/estadual/municipal) e da 470 (90 dias, períodos) | conferem |
| Deferido × indeferido | confere (488 é a única indeferida) |
| Algo da GEDIV na página que não foi extraído | não encontrado |

A **conferência pela GEDIV continua pendente**: é ela que torna os registros "conferidos".

## 4. Progressão em PDF real — edição de 03/10/2026

| Resenha | Página | Vínculo | Classificação | Resultado | Decisões |
|---|---|---|---|---|---|
| 524/2026 | 5 | **não expresso** (só DEREH) | Progressão Vertical · grupo TEC-ADM | Deferido | 21 |
| 527/2026 | 5 | **não expresso** (só DEREH) | Progressão Vertical · grupo TEC-ADM | Deferido | 20 |
| 512/2026 | 6 | expresso | Progressão Horizontal · grupo Saúde | Indeferido | 1 |

42 decisões; classe anterior e posterior extraídas em 41 (a indeferida não publica classe).
Comparação processo a processo com o histórico do painel anterior
(`evidencias/pdf-oficial/comparacao-com-historico.json`):

| Edição | Histórico | Sistema | Processo, matrícula, resenha e resultado iguais | Nome igual |
|---|---|---|---|---|
| 02/10 | 5 | 7 | 5 de 5 | 5 de 5 |
| 03/10 | 42 | 42 | 42 de 42 | 37 de 42 |

Em 02/10 o sistema encontrou **2 decisões que o histórico não tinha** (resenhas 488 e 504).
As edições de 01/10 e 06/10 não contêm atos da GEDIV nos dois eixos (nenhuma página traz a
expressão "Direitos e Vantagens").

## 5. Defeitos revelados pelo PDF real e corrigidos

| # | Defeito | Onde apareceu | Correção | Teste de regressão |
|---|---|---|---|---|
| 1 | Trecho em fonte **sem mapeamento de caracteres** saía como `(cid:…)`: duas resenhas da GEDIV ficavam invisíveis | 02/10, p. 5 | OCR **somente do trecho ilegível**, recolocado na posição (método `TEXTO+OCR`, confiança 94,8) | `test_trecho_em_fonte_sem_mapeamento_…`, `test_blocos_de_fonte_ilegivel_…` |
| 2 | Vãos de **tabela** viravam "colunas" (7 numa página), misturando o cabeçalho de uma resenha com ato de outra gerência | 02/10, p. 4 | havendo corredor central, só ele divide a página; as linhas da tabela ficam inteiras | `test_vaos_de_tabela_nao_viram_colunas_…` |
| 3 | Ato sem processos "herdava" o tema do ato seguinte (associação errada de resenha) | 02/10, p. 4→5 | consequência dos itens 1 e 2; coberto por teste próprio | `test_ato_sem_processos_nao_toma_emprestado_…` |
| 4 | Número da edição não identificado na capa real ("DIÁRIO OFICIAL / ESTADO DA PARAÍBA / Nº 18.684 João Pessoa…") | 02/10, p. 1 | padrão acrescentado | `identificar_edicao` (forma da capa real) |
| 5 | Texto justificado letra a letra ("T E C N IC O") impedia separar nome e cargo | 03/10, p. 5 | junção das letras espaçadas | `test_linha_justificada_letra_a_letra_…` |
| 6 | Nome e cargo quebrados em duas linhas da tabela | 03/10, p. 5 | o que precede a continuação do cargo na linha de baixo volta para o nome | idem |
| 7 | Cabeçalho com "Expediente :" e "Resenha nº :" em linhas separadas | 02/10, p. 5 | padrão acrescentado | `test_cabecalho_com_expediente_e_resenha_…` |

Fechados também os dois itens que restavam da auditoria:
- **RISCO-013 (página mista texto + imagem):** página com texto nativo e imagem cobrindo 25% ou mais
  é relida por OCR; sem OCR fica `TEXTO_PARCIAL` (pendente) e volta à fila com `--refazer`. Nenhuma
  das 172 páginas reais caiu nesse caso.
- **LIMITE-014 (PDF corrompido com marcadores válidos):** entra no acervo, mas a leitura registra
  `ERRO`, nada é classificado e a cobertura o mostra como pendência. Testado.

## 6. Problemas observados que permanecem

1. **Nomes em linhas quebradas:** em 03/10, 5 de 42 nomes saem incompletos (a parte que falta fica em
   outra linha da célula). As 41 linhas de tabela quebrada saem com o aviso `linha_quebrada`; processo,
   matrícula, classe e resultado dessas linhas estão corretos.
2. **Página 14 de 02/10** (anúncio com fontes decorativas, sem relação com a GEDIV): OCR de baixa
   confiança (66,8) e 4 colunas; a edição fica `LIDA_COM_PENDENCIAS`.
3. **Vínculo não expresso:** as duas resenhas de Progressão Vertical de 03/10 (41 decisões) não citam
   a GEDIV; só podem ser conferidas com confirmação explícita do revisor.
4. **Expediente** da resenha 504/2026 não capturado.
5. Amostra pequena: 4 edições, 7 resenhas dos dois eixos. Não há ainda precisão/revocação medidas em
   escala, nem edição com evento de alteração (retificação, sem efeito) lida de PDF real.

## 7. Como repetir

```
python -m observatorio.operacao validar-real diario-oficial-02-10-2026-portal.pdf --data 2026-10-02 \
       --url https://auniao.pb.gov.br/servicos/doe/2026/outubro/diario-oficial-02-10-2026-portal.pdf \
       --dados dados --saida validacao-real.json --amostra amostra-privada.txt
python -m observatorio.web --dados dados
```

`validacao-real.json` não contém dados pessoais. `amostra-privada.txt` contém e **não deve ser
versionada nem publicada** (o `.gitignore` já a exclui).

## 8. Segurança

- Nenhum nome, matrícula ou número de processo real está no repositório: os 147 valores extraídos
  dos PDFs foram procurados em todos os arquivos versionados, sem ocorrência.
- As capturas de tela do painel sobre a base real mostram só números de resenha e contagens.
- **Recomendação ao responsável autorizado:** a pasta do Drive está acessível a qualquer pessoa com o
  link e contém planilha com dados pessoais. Convém restringi-la a pessoas autorizadas. Nenhuma
  permissão do Drive foi alterada nesta entrega.

## 9. Onde o acesso ao servidor oficial foi tentado (atualização de 11/11/2026)

| Ambiente | Tentou acessar `auniao.pb.gov.br` / `cge.pb.gov.br`? | Resultado |
|---|---|---|
| Contêiner remoto de desenvolvimento (Linux em nuvem, saída por proxy) | Sim, 10/11 | conexão encerrada sem resposta após ~11 s |
| GitHub Actions Linux (Microsoft, EUA — Illinois, Washington, Iowa) | Sim, 4 execuções da sonda | DNS resolve; a porta 443 não aceita conexão |
| GitHub Actions Windows (Microsoft, EUA — Virgínia) | Sim, 1 execução da sonda em 11/11 | idem |
| GitHub Actions macOS (Microsoft, EUA — Califórnia) | Sim, 1 execução da sonda em 11/11 | idem |
| Computador da responsável | **Não** | sem medição |
| Rede da SEAD | **Não** | sem medição |

Nos mesmos executores, `www.gov.br` e `github.com` respondem, e `paraiba.pb.gov.br` (mesma faixa de
endereços das fontes) aceita a conexão e devolve uma página de verificação anti-robô. Evidência:
`evidencias/sonda-github-2026-11-11-tres-executores.json`.

**O que isso sustenta:** a partir de datacenters nos EUA, as duas fontes não aceitam conexão; a falha
ocorre antes de qualquer requisição do coletor, portanto não é um defeito do código medido ali.
**O que não sustenta:** nada sobre redes brasileiras. O coletor nunca recebeu uma página real das
fontes, então a leitura das listagens reais continua sem teste. Os testes automatizados em Windows
usam servidor simulado e não representam nenhum computador real. O coletor não foi alterado.
