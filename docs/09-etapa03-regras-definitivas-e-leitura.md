# Etapa 03 — Regras definitivas e correções de leitura (PR-01 e PR-02)

Data: 12/11/2026. Base: código do PR #5 (`c49f9ec`). Ambiente: cópia isolada (git worktree), sem
alteração remota. Todos os números abaixo foram **executados**; nada aqui é estimativa, salvo
quando indicado.

## 1. O que mudou

| PR | Mudança | Arquivos |
|---|---|---|
| PR-01 | Nome oficial "Painel Diário Oficial \| GEDIV" | `observatorio/__init__.py`, README, cabeçalhos dos comandos, web |
| PR-01 | Grupos definitivos: `SAUDE`→`SSA`, `ESPECIAL`→`ESP`, `INT` (provisório); lista exata dos 16 códigos | `gerencias/gediv/catalogo.py` |
| PR-01 | `TEC. ADM` e `STF` sem grupo homologado: ato sem grupo, expressão guardada, pendência | `catalogo.py` (`EXPRESSOES_SEM_GRUPO`) |
| PR-01 | Exclusões `FORA_ESCOPO`: licença-saúde, vacância, outra gerência; motivo lido do preâmbulo; DEREH nunca exclui os dois eixos | `gerencias/gediv/exclusoes.py`, `classificador.py` |
| PR-01 | Banco esquema 5: tabela privada `fora_escopo` (sem linhas de servidores) | `nucleo/banco.py` |
| PR-02 | Tolerância horizontal entre letras de 1,5 pt (padrão do pdfplumber: 3 pt) | `leitura/leitor.py` (`TOLERANCIA_X`, versão do leitor 0.4) |
| PR-02 | Recursos de cada página liberados após a leitura | `leitura/leitor.py` |
| PR-02 | Assunto procurado também com letras reunidas e em forma compacta (sem espaços), nessa ordem, com pendência quando o texto foi reconstituído | `classificador.py`, `catalogo.py` |
| PR-02 | Conjunto-ouro: manifesto sem dados pessoais e comando `operacao ouro` | `docs/validacao/conjunto_ouro.json`, `operacao/ouro.py` |
| PR-02 | Tempo e pico de memória no relatório `validar-real` | `operacao/validacao_real.py` |

## 2. Conjunto-ouro (5 edições oficiais, 232 páginas)

Os PDFs foram baixados automaticamente de `auniao.pb.gov.br` em 12/11/2026, a partir de um
ambiente de nuvem que **não** é o GitHub Actions. Os SHA-256 são iguais aos das referências.
Expectativas conferidas tecnicamente (§2.1). **Não homologadas pela GEDIV.**

| Edição | Esperado | Antes do PR-02 | Depois do PR-02 |
|---|---|---|---|
| 01/10 | 0 atos | confere | confere |
| 02/10 | 4 atos (470, 473, 488, 504), 7 decisões; 505 e 506 = licença-saúde | confere | confere |
| 03/10 | 3 atos (524, 527, 512), 42 decisões; 117/GOCESP = outra gerência; 507 e 509 = licença-saúde | confere | confere |
| 06/10 | 0 atos | confere | confere |
| 04/11 | 540 TS-03 deferido (1); 543 TS-02 indeferido (1); 541 e 544 = licença-saúde; 568 = vacância | **diverge**: 540 e 543 ausentes | confere |

Os relatórios completos, sem dados pessoais, estão em `docs/evidencias/conjunto-ouro/`.

**Antes de qualquer mudança** (código do PR #5): 04/11 sem nenhum ato; 541 e 544 em "Outras
publicações"; nenhum ato fora do escopo registrado.

### 2.1 Como as expectativas foram conferidas

| Resenhas | Método |
|---|---|
| 470, 473, 540, 543, 541, 544, 568 | Leitura independente (pypdfium2): número de processos e palavras-chave do assunto |
| 524, 527, 512 (03/10) | 42 processos distintos na p. 5 (41 das resenhas 524/527 + 1 da 117/GOCESP, cessão) e 1 na p. 6 |
| 488 e 504 (02/10) | Fonte sem mapeamento de caracteres, ilegível para qualquer motor de texto: conferência visual na imagem da página 5 |

## 3. Comparação campo a campo PR-01 × PR-02

Decisões de 02/10, 03/10 e 04/11: nenhuma decisão existente mudou em processo, matrícula, nome,
lotação, cargo, detalhe, resultado ou página. Diferença única: +2 decisões em 04/11 (540 e 543).

## 4. Ablação (04/11)

| Configuração | Atos encontrados |
|---|---|
| Sem correção (tolerância 3, só texto original) | nenhum |
| Só tolerância 1,5 | 540 |
| Só variantes do preâmbulo | 540 e 543 (540 com pendência de texto reconstituído) |
| As duas (adotado) | 540 e 543 (540 lido diretamente, sem pendência) |

**Efeito da tolerância em 225 páginas** comparáveis, medido pela concordância de vocabulário com a
leitura independente: com 1,5 pt, 10 páginas melhoram e nenhuma piora. Com 1 pt, 12 melhoram, mas
mais palavras se partem em letras soltas. O valor adotado é 1,5.

## 5. Memória e tempo (por edição, processo próprio, Linux, Tesseract 5.3.4)

| Edição | Antes: tempo / pico | Depois: tempo / pico |
|---|---|---|
| 01/10 (56 p.) | 27,0 s / 1.148 MB | 23,7 s / 224 MB |
| 02/10 (40 p.) | 14,2 s / 797 MB | 12,3 s / 219 MB |
| 03/10 (48 p.) | 21,1 s / 972 MB | 19,9 s / 219 MB |
| 06/10 (28 p.) | 14,7 s / 567 MB | 13,4 s / 168 MB |
| 04/11 (60 p.) | 21,9 s / 1.211 MB | 19,0 s / 160 MB |

## 6. Testes

| Situação | Resultado |
|---|---|
| Antes (PR #5) | 155 testes, todos aprovados |
| Depois, sem PDFs oficiais | 188 aprovados + 1 pulado (o teste do conjunto-ouro real) |
| Depois, com `GEDIV_PDFS_OURO` | **189 aprovados, 0 pulados** |

Novos: `tests/test_regras_definitivas.py` (21) e `tests/test_leitura_correcoes.py` (13).
Atualizados para as regras definitivas: 9 testes em `test_gediv.py`, `test_painel.py`,
`test_ponta_a_ponta.py` e `test_leitura.py`.

Para rodar o conjunto-ouro:

```
GEDIV_PDFS_OURO=/pasta/com/os/pdfs python -m unittest tests.test_leitura_correcoes
python -m observatorio.operacao ouro --pdfs /pasta/com/os/pdfs --saida relatorio-ouro.json
```

## 7. Pendências

**Decisões da GEDIV:**

- `TEC. ADM` = AST? (41 decisões reais em 03/10 hoje sem grupo)
- `STF` = SFT?
- expressões do grupo INT;
- regra para ato só com DEREH (524 e 527);
- homologar o conjunto-ouro.

**Defeitos ainda abertos:** ver `RISCOS_E_PENDENCIAS.md` da Etapa 02 e o relatório da Etapa 03.

**Modo de aprovação:** continua MANUAL. Nada é aprovado automaticamente e os indicadores só contam
registros conferidos por pessoa.
