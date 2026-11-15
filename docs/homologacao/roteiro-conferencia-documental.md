# Roteiro de conferência documental pela GEDIV

**Situação: VALIDAÇÃO DOCUMENTAL INDEPENDENTE PENDENTE.**

Até a Etapa 05.3.5 o robô só foi medido contra documentos que também serviram para desenvolvê-lo (seção G de
`docs/16-etapa05-3-pr05-homologacao-geral.md`). Falta alguém que **não** seja o robô conferir no PDF oficial o que
ele extraiu. Este roteiro diz como fazer isso. Ele não contém dados pessoais: a planilha com nomes, matrículas e
processos é gerada à parte, fica fora do repositório e é entregue só à responsável pelo projeto.

## 1. O que a GEDIV recebe

| Arquivo (privado, fora do GitHub) | Conteúdo |
|---|---|
| `amostra_conferencia.csv` | Uma linha por decisão sorteada: edição, página, resenha, o que o robô leu em cada campo, e três colunas em branco para a conferência |
| `paginas_para_contagem.csv` | Uma linha por resenha da amostra: edição, página, quantas linhas o robô extraiu, e uma coluna em branco para a contagem feita no PDF |
| `LEIA-ME.txt` | Estas mesmas instruções, resumidas |

Os PDFs são os oficiais, baixados do portal de A União pela própria conferente (o nome do arquivo e o SHA-256 de
cada edição estão na planilha, para garantir que é o mesmo documento).

## 2. Como a amostra é escolhida

Critérios fixos, aplicados por programa (não se escolhem só os casos fáceis):

- todas as resenhas da GEDIV de cada edição entram na contagem de linhas;
- de cada resenha entram a primeira linha, a última e até quatro intermediárias, igualmente espaçadas;
- entram **todas** as linhas com alguma ressalva do robô (linha quebrada, tabela ambígua, OCR, sem processo, sem
  resultado) e todas as de resenhas que atravessam página;
- entram todos os atos modificadores (retificação, republicação, tornado sem efeito) e todas as portarias
  relacionadas.

A distribuição da amostra por tipo (Progressão, Tempo de Serviço, tabela, OCR, várias páginas, portaria,
modificador, caso ambíguo) vai no cabeçalho do `LEIA-ME.txt`, com as quantidades reais — inclusive os tipos que
ficaram com zero por não existirem nas edições disponíveis.

## 3. O que conferir em cada linha

Abra o PDF na página indicada, localize a resenha e a linha, e compare campo a campo:

| Campo | Pergunta |
|---|---|
| Processo | O número é exatamente o publicado? |
| Matrícula | É a matrícula **desta** pessoa (e não a da linha de cima ou de baixo)? |
| Nome | Está completo, sem pedaço de outra linha e sem faltar sobrenome? |
| Cargo | É o cargo desta pessoa, completo? |
| Classe/nível anterior e atual | São os desta linha, como publicados? |
| Resultado | Deferido ou indeferido, conforme a resenha (ou o bloco, se a resenha for mista)? |
| Modalidade e grupo (Progressão) | Horizontal ou Vertical? O grupo é o que a resenha diz? |
| Assunto (Tempo de Serviço) | É um dos sete assuntos, e o certo? |

Preencha as três colunas em branco:

- **Confere?** `S` se todos os campos estão certos; `N` se algum está errado; `?` se o PDF não permite decidir.
- **Campo(s) com erro** — os nomes dos campos errados (por exemplo: `nome; cargo`).
- **Como está no PDF** — o valor correto, copiado do documento.

## 4. Contagem de linhas (para achar omissões e duplicações)

Em `paginas_para_contagem.csv`, para cada resenha: conte no PDF quantas pessoas (linhas da tabela) a resenha tem e
escreva o número. Se a resenha continua em outra página, conte tudo. Anote também, em "Observação", qualquer resenha
da GEDIV que esteja na página e **não** apareça na planilha — é o caso mais grave (um ato inteiro não lido).

## 5. Páginas sem resenha da GEDIV

A planilha traz ainda, por edição, as páginas em que o robô não encontrou nada da GEDIV mas registrou ressalva de
leitura (baixa confiança, texto ilegível, leitura incompleta). Basta olhar cada uma e responder: há resenha da
GEDIV/DEREH nessa página? `S`/`N`.

## 6. Como registrar o resultado

Devolva as duas planilhas preenchidas e o termo abaixo. Não envie as planilhas por canal público nem as anexe ao
GitHub.

```
TERMO DE CONFERÊNCIA DOCUMENTAL — Painel Diário Oficial | GEDIV

Conferente: ______________________________   Cargo/função: ____________________
Período da conferência: ____/____/______ a ____/____/______
Edições conferidas (datas): _____________________________________________________

Linhas conferidas: ______   Conferem: ______   Não conferem: ______   Indecidíveis: ______
Resenhas contadas: ______   Com a mesma quantidade de linhas: ______   Com diferença: ______
Atos da GEDIV encontrados no PDF e ausentes da planilha: ______

Resultado:  (  ) ACEITO   (  ) ACEITO COM RESSALVAS   (  ) REPROVADO
Ressalvas ou motivo da reprovação: ______________________________________________
________________________________________________________________________________

Assinatura: ______________________________   Data: ____/____/______
```

## 7. O que acontece depois

- Cada linha marcada `N` vira um caso de teste do robô (sem dados pessoais no repositório) e uma correção, quando
  for defeito de leitura; ou uma questão em `questoes-pendentes-gediv.md`, quando for regra.
- As medidas (linhas ausentes, extras, duplicadas, acerto por campo) são calculadas sobre essa conferência, com os
  denominadores declarados. Antes dela, nenhum percentual de acerto "geral" é divulgado.
- A validação só é considerada **independente** se incluir edições que o robô nunca viu durante o
  desenvolvimento. As 11 edições já usadas servem para esta primeira conferência, mas não bastam: para a
  homologação final devem ser sorteadas edições novas, de 2026, baixadas pela GEDIV.
