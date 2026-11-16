# PR10.1 — limites de colunas e referências documentais

Uma faixa de baixa ocupação pode conter a borda de uma palavra comprida de um
título. Usar seu ponto médio como divisor fazia dois cabeçalhos paralelos parecerem
uma linha de largura total. O classificador recebia esse texto misturado e extraía
uma referência da publicação vizinha.

A correção fica em `observatorio/leitura/pagina.py`. Se o ponto médio já tem a
menor ocupação da faixa, ele é preservado. Caso contrário, usa-se a posição menos
ocupada dentro da mesma faixa, preferindo a mais central em empate. A largura
tolerante é limitada pelos vãos observados entre células, sem tratar espaços
comuns entre palavras como separação de colunas. Permanecem os limiares existentes
de detecção, quantidade mínima de linhas e tratamento de tabelas/linhas inteiras.

Não há filtro de números de resenha, páginas ou coordenadas de um documento real.
Não se remove a referência por regex depois da classificação: o texto é separado
antes de chegar ao classificador. Citações expressas e continuações válidas
permanecem suportadas. Não mudam IDs, esquema SQLite 8, critérios administrativos,
PaddleOCR, filtros, indicadores ou estados de revisão.

Os testes de `tests/test_referencia_colunas.py` usam somente dados fictícios:
publicações paralelas, referência legítima no corpo, continuação entre colunas e
páginas, título de largura total, corredor com marcas esparsas, escalas diferentes,
tabela continuada, homônima de outro órgão, revisão pendente e exportações.

```bash
python -m unittest tests.test_referencia_colunas -v
python -m unittest discover -s tests -t . -v
```

A comprovação documental e os bancos de teste ficam fora do Git/CI. Bases históricas
não são corrigidas ou relidas automaticamente por esta tarefa. A execução real usa
acervo novo e isolado. Publicar a branch experimental não homologa dados nem
autoriza implantação, coleta diária ou ampliação de lote. A conferência das edições
cuja cobertura continua não verificada depende de autorização distinta.
