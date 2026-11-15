# Etapa 05.3 — PR06: integridade após a homologação técnica

Esta alteração parte de `11681ba9073b2a8d2b2ffb17dff9876b694300cc` (leitor 0.8, esquema SQLite 8). Os cenários usam exclusivamente dados e PDFs sintéticos. Não representam homologação documental, deliberação administrativa nem liberação para produção.

## Revisões e dados ausentes

Decisões pendentes com correção, revisão anterior ou origem manual não são eliminadas ao reclassificar. O registro, a trilha e a escolha humana permanecem; novas divergências produzem conflitos idempotentes. `null` recebido em uma correção passa a significar ausência, assim como texto vazio; a palavra literal `None` continua sendo texto literal. Nenhuma migração do esquema é necessária.

## Acervo e execução

A cobertura e a reconciliação verificam o SHA-256 efetivo, além do tamanho e do registro de verificação. Se o arquivo não conferir, a publicação volta à fila com motivo e auditoria; o histórico de versões não é apagado. Um arquivo corrompido no local endereçado pelo SHA deve ser preservado fora desse local antes da restauração ou obtenção controlada do conteúdo correto: a guarda existente recusa sobrescrever um arquivo corrompido.

O fluxo informa fontes e intervalos presentes na base e considera leituras pendentes persistidas, falhas/recusas de releitura ainda não resolvidas e conflitos abertos, inclusive quando não há novo trabalho na fila. Mantêm-se os códigos 0 (sucesso), 1 (falha), 3 (pendências) e 4 (não executado). Em leitura de texto neutro, mudanças nas inconsistências atualizam o estado e permitem retomada.

## Indicadores e pendências de classificação

Uma classificação que não corresponde à revisão da leitura ou à versão atual das regras fica fora das contagens até ser processada novamente. O banco e as decisões humanas são preservados. Uma classificação sem vínculo de revisão não recebe automaticamente um vínculo inventado ao reabrir um banco já atualizado. A migração de bancos antigos segue preenchendo os vínculos associados às leituras migradas.

Para preservar o contrato anterior, decisões conferidas com conflito aberto continuam contadas, porém o painel indica quantas estão nessa situação, as resenhas trazem a marca de conflito e a exportação gerencial registra a condição. O aviso de cobertura também identifica decisões temporariamente fora dos indicadores. A GEDIV mantém a decisão institucional sobre o significado definitivo dessas situações.

## OCR em contornos

Mesmo quando o Tesseract reconhece parte do texto em contornos e atribui confiança alta, pode omitir palavras. Por precaução, toda região de contornos detectada conserva o aviso `POSSIVEL_TEXTO_EM_CONTORNO` e exige conferência. A alteração não redesenha o OCR e não garante a detecção de todos os tipos de contorno nem a recuperação de todas as palavras. Os testes cobrem PDF sintético com texto nativo, contornos, sinal CID, grade e imagem, com e sem Tesseract.

## Verificação e limites

Os testes permanentes estão em `tests/test_integridade_pr06.py` e `tests/test_regressao_contornos_pr06.py`. Para executá-los e rodar a suíte completa:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest tests.test_integridade_pr06 tests.test_regressao_contornos_pr06 -v
python -m unittest discover -s tests -t . -v
```

O teste de OCR real requer Tesseract com idioma português; a ausência é registrada como teste pulado. O teste gerador de contornos usa `fonttools` e a fonte fornecida pelo ReportLab. A conferência independente das edições oficiais e do corpus privado não é substituída por testes sintéticos. Permanecem fora do escopo D08–D12, as dez deliberações da GEDIV e a implantação, coleta oficial e operação da Etapa 06.
