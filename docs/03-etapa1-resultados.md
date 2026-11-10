# Etapa 1 — Resultados de validação (coleta e acesso às fontes)

Data: 10/11/2026. Este documento separa o que foi **executado** do que está **pendente**.

## 1. Testes automatizados — executados

Comando: `python -m unittest discover -s tests -t .`

| Ambiente | Python | Resultado |
|---|---|---|
| Ambiente de desenvolvimento (Linux) | 3.13 | 33 testes, todos aprovados |
| GitHub Actions, Ubuntu 24.04 | 3.11 e 3.13 | 33 aprovados |
| GitHub Actions, Windows | 3.11 e 3.13 | 33 aprovados |

Estes números são da primeira entrega da etapa. Os testes de lotes e de leitura,
acrescentados depois, estão em `04-coleta-em-lotes-e-leitura.md`.

Execução de referência: <https://github.com/gedivseadpb-boop/Observat-rio-GEDIV-CLAUDE/actions/runs/42870696476>

A primeira execução no Windows falhou em um teste (um arquivo de banco ficava aberto ao
final do próprio teste). Era defeito do teste, não do sistema; foi corrigido e a execução
seguinte passou nos quatro ambientes.

**Limite destes testes:** usam um servidor local e PDFs sintéticos. Comprovam a lógica
(duplicidade, integridade, recuperação, histórico), não o comportamento das páginas reais.
As listagens sintéticas reproduzem os formatos de endereço confirmados, não a estrutura
HTML verdadeira dos portais, que ainda não pôde ser lida diretamente.

## 2. Sonda de acesso — executada três vezes em executores do GitHub

Relatórios completos em `docs/evidencias/`.

| | Execução 1 | Execução 2 | Execução 3 |
|---|---|---|---|
| Horário (UTC) | 10/11/2026 17:57 | 10/11/2026 18:00 | 10/11/2026 18:15 |
| Saída para a internet | Microsoft Azure, EUA (Illinois) | Microsoft Azure, EUA (Washington) | Microsoft Azure, EUA (Washington) |

As três execuções tiveram o mesmo resultado.

| Servidor | Endereço | DNS | Conexão (80 e 443) | Resultado |
|---|---|---|---|---|
| `auniao.pb.gov.br` (e `www`) | 138.185.34.81 | resolve | **expira sem resposta (12 s)** | inacessível |
| `cge.pb.gov.br` | 138.185.34.68 | resolve | **expira sem resposta (12 s)** | inacessível |
| `paraiba.pb.gov.br` (controle) | 138.185.34.41 | resolve | conecta em 0,15 s | responde, mas com **página de verificação anti-robô** |
| `www.gov.br` (controle) | 161.148.164.31 | resolve | conecta | responde |
| `github.com` (controle) | — | resolve | conecta | responde |

### O que estes resultados permitem afirmar

| Hipótese | Conclusão | Fundamento |
|---|---|---|
| H1. DNS | **Descartada** | Os nomes resolvem em 0,2 s. |
| H2. IPv6 | **Descartada** | As fontes só publicam endereço IPv4. |
| H4. Só HTTPS bloqueado | **Descartada** | As portas 80 e 443 falham igualmente. |
| H5. TLS/certificado | **Descartada para esta origem** | A conexão nem chega à etapa TLS. |
| H6. Identificação do programa (User-Agent) | **Descartada para esta origem** | Nenhuma requisição HTTP chega a ser enviada; o cabeçalho não pode ser a causa. |
| H8. Instabilidade momentânea | **Pouco provável** | Duas execuções hoje, mais os registros de 31/10 e 09/11 dos projetos anteriores, com o mesmo sintoma. |
| H3. Filtro de rede conforme a origem | **Compatível com tudo o que foi medido** | Pacotes descartados em silêncio, apenas para as duas fontes. |

Dois fatos novos:

1. **O bloqueio é por serviço, não da rede inteira.** `paraiba.pb.gov.br` está na mesma
   faixa de endereços das duas fontes (138.185.34.x) e aceita conexão do mesmo executor.
   Logo, a rede do Estado não rejeita os executores do GitHub como um todo; a regra
   atinge especificamente os servidores do Diário Oficial e da CGE.
2. **Existe proteção anti-robô nessa infraestrutura.** O portal de controle respondeu com
   uma página que exige navegador com JavaScript. Se as fontes do DOE estiverem atrás da
   mesma proteção, um programa pode receber essa página no lugar do PDF **mesmo a partir
   de uma rede brasileira**. O coletor já reconhece e recusa esse caso
   (`RECEBIDO_HTML_EM_VEZ_DE_PDF`), mas é um obstáculo possível que os projetos anteriores
   não haviam identificado.

### O que ainda **não** se pode afirmar

- Se o filtro é por país, por tipo de rede (datacenters) ou por lista de provedores. Só há
  medições a partir de uma origem (Azure, EUA).
- Se as fontes respondem normalmente a um programa em rede brasileira, ou se exigem navegador.
- O conteúdo do `robots.txt` das fontes. Há um indício de restrição: a ferramenta de
  leitura de páginas usada no desenvolvimento recusou `auniao.pb.gov.br/doe/` informando
  restrição de robots para aquele leitor. O coletor consulta o `robots.txt` e, por padrão,
  não coleta se houver proibição.

### Próxima medição necessária

Executar a mesma sonda em um computador ligado a uma rede no Brasil (de preferência a rede
da SEAD). O resultado define o caminho:

| Resultado da sonda no Brasil | Caminho |
|---|---|
| Fontes respondem e o início do PDF chega com assinatura `%PDF` | Executar o robô nessa rede (ou em executor equivalente) e iniciar a carga histórica. |
| Fontes conectam, mas devolvem página de verificação | Solicitar à A União/CODATA liberação para o robô da SEAD ou um canal oficial de acesso; usar importação manual enquanto isso. |
| Fontes também não conectam | Tratar institucionalmente; importação manual como contingência. |

## 3. Pendências da Etapa 1

- Leitura das listagens reais (A União e CGE) e ajuste do extrator, se a estrutura diferir.
- Confirmar o nome da pasta de março (`marco`) e o endereço da consulta da CGE.
- Download real de ao menos um PDF de cada fonte, com verificação.
- Comparar byte a byte o mesmo dia nas duas fontes (não se sabe se os arquivos são idênticos).
- Inventário de 01/01/2026 até a data atual.
