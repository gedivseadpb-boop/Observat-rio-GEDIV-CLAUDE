# PR09 — PaddleOCR complementar experimental

O leitor 0.8 (texto nativo + Tesseract) e o classificador administrativo continuam como base. O novo comando explícito acrescenta somente pares de classes totalmente ausentes de decisões pendentes de progressão vertical. Não altera nome, cargo ou matrícula, não confere decisões e não muda o esquema SQLite 8.

## Preparação opcional em CPU

Use ambiente separado Linux/Python 3.10–3.12. Instale o extra `paddleocr` do projeto (não é instalado por requirements-dev.txt ou CI). As versões conferidas são PaddleOCR 3.7.0, PaddleX 3.7.2, PaddlePaddle CPU 3.2.0, PyMuPDF 1.26.6 e psutil 7.x. Código PaddleOCR e os dois model cards oficiais declaram Apache-2.0. O renderizador PyMuPDF tem licença dual AGPL-3.0/comercial; não é Apache. O uso deste protótipo público não equivale a aprovação de licença para uma implantação institucional fechada. Essa condição deve ser avaliada antes da homologação/implantação.

Providencie por download explícito os arquivos inference.json, inference.pdiparams e inference.yml de cada modelo oficial, nas subpastas PP-OCRv6_medium_det e PP-OCRv6_medium_rec. O programa verifica os seis hashes fixados em paddle_complementar.MODELOS antes de carregar o motor e novamente no worker. Não há download automático.

- https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det/tree/8e0f56fb2ef86b461d99cfc7ac5c137738985f61
- https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec/tree/e5a92bcbc5cc1b494628e458d267778f0704fd7c
- Código/licença: https://github.com/PaddlePaddle/PaddleOCR/tree/v3.7.0

Depois da leitura e classificação normais, em uma cópia autorizada do acervo:

```sh
python -m observatorio.gerencias.gediv complementar --dados /copia/privada/dados \
  --paddleocr-modelos /modelos/locais --paddleocr-python /venv/cpu/bin/python --limite 1
```

O comando não coleta nem lê novamente todo o PDF. Só considera classificações vigentes na revisão atual. Os avisos e propostas continuam pendentes; o código de saída 3 indica propostas, sinais ou falha do complemento, não falha/descarte da leitura original. A saída do terminal contém somente contagens.

## Seleção e segurança

Seleciona páginas com par ausente/parcial ou observação de insegurança em decisões de Progressão Vertical. Renderiza a página inteira a 400 dpi, descobre grades por linhas longas nos pixels e filtra seis colunas com duas últimas estreitas. Texto nativo com âncoras de outra tabela evita OCR do controle; a confirmação óptica dos seis cabeçalhos exige Processo/Matrícula/Nome/Cargo/Classe/PClasse. Não contém casos individuais, números de resenha, datas, páginas ou coordenadas fixas de uma publicação.

Monta células por contenção de pelo menos 90% da caixa. Qualquer caixa ambígua na linha impede preenchimento. Exige processo e matrícula inequívocos e confiança mínima 0,90 nos dois identificadores e nas duas classes. Não corrige caracteres; classes válidas são A–F, de acordo com o contrato existente. Pares regressivos/iguais são apenas sinalizados. Par parcial não é completado. Classe existente nunca é substituída; divergências viram conflitos PADDLEOCR e pendências explícitas.

Nome/cargo divergentes são identificados por nome do campo, sem copiar as identidades candidatas para metadados. Uma correção/revisão anterior, inclusive uma ausência deliberada, bloqueia preenchimento e preserva o dado humano. Todas as gravações ocorrem depois da inferência, em transação, com releitura da revisão/decisão e bloqueio de escrita. A auditoria usa alvo classificacao para não se passar por revisão humana de decisão.

A origem inclui SHA do PDF, revisão da leitura, página, caixa da linha, classes candidatas, confiança, versões e hashes dos modelos no JSON detalhe. Reclassificação da mesma revisão e mesmas identidades/texto preserva propostas e origem; uma nova leitura ou regras distintas não reutiliza evidência antiga silenciosamente. Os conflitos e o histórico permanecem disponíveis. Nada é homologado por esse reaproveitamento.

## Limites e fallback

Worker local e isolado: padrão 180 s por arquivo, RSS até 3.584 MiB, quatro páginas e oito regiões, imagem até 25 milhões de pixels. O supervisor encerra o processo em timeout/excesso de RSS e conserva o leitor original. Ausência de biblioteca, versão/peso incorreto, falta de monitor, PDF adulterado, exceção, seleção inconclusiva ou limite geram aviso pendente. Falha não apaga classes existentes ou a proveniência anterior. Não há endpoint remoto de inferência.

Os valores são conservadores e configuráveis pela API dentro de limites superiores. Logs/transcrições ficam em diretório temporário privado e são removidos ao encerrar o worker. Não publique esse diretório, acervo, banco, PDFs ou saídas de pessoas no GitHub/CI.

## Verificação

```sh
python -m unittest tests.test_paddle_complementar -v
python -m unittest discover -s tests -t . -v
```

Testes permanentes usam exclusivamente pessoas, processos e documentos fictícios. O teste óptico real fica fora do repositório. CI normal não instala Paddle/pesos. Uma branch experimental e uma medição pontual não constituem integração homologada; esta exige regressão privada de todos os PDFs e revisão independente.
