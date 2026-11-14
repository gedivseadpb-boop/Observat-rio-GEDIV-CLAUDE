"""Painel Diário Oficial | GEDIV — fluxo completo.

    python -m observatorio.operacao executar PASTA_OU_ARQUIVO.pdf [--data AAAA-MM-DD] [--url URL_OFICIAL]
        importa o(s) PDF(s), lê (texto e OCR) e classifica; os registros ficam PENDENTES de revisão
    python -m observatorio.operacao executar          # sem origem: lê e classifica o que já está no acervo
    python -m observatorio.operacao validar-real ARQUIVO.pdf --data AAAA-MM-DD --url URL_OFICIAL --saida relatorio.json --amostra amostra.txt
        validação com PDF OFICIAL: executa o fluxo e grava um relatório SEM dados pessoais (versionável)
        e, se pedido, uma amostra PRIVADA para a conferência humana contra o PDF
    python -m observatorio.operacao ouro --pdfs PASTA_COM_PDFS_OFICIAIS [--manifesto docs/validacao/conjunto_ouro.json] [--saida rel.json]
        conjunto-ouro: roda o fluxo real em cada edição do manifesto (PDFs localizados pelo SHA-256) e compara com o
        resultado esperado; saída 1 em caso de regressão. Relatório sem dados pessoais.
    python -m observatorio.operacao corpus --pdfs PASTA --esperado-privado ARQUIVO.json [--saida rel.json]
        corpus de PDFs difíceis: precisão POR CAMPO contra o esperado conferido visualmente (arquivo PRIVADO,
        fora do repositório); relatório só com contagens e percentuais
    python -m observatorio.operacao demonstracao --dados dados-demo
        cria uma base de DEMONSTRAÇÃO com documentos SINTÉTICOS (pessoas e processos fictícios)

Aquisição dos PDFs oficiais (Etapa 05):
    python -m observatorio.operacao sonda --fonte auniao [--saida sonda.json]
        descobre a edição mais recente na página oficial, baixa o PDF num diretório temporário VAZIO e verifica
        integridade (Content-Length, %%EOF, startxref, páginas) e SHA-256. Saída 0 = download íntegro; 4 = bloqueado.
    python -m observatorio.operacao coletar-dia --data 2026-11-07 [--dry-run] [--limite N]
    python -m observatorio.operacao coletar-intervalo --inicio 2026-11-04 --fim 2026-11-12 [--dry-run] [--limite N]
        descobre (edições recentes + listagens mensais) e baixa só o período; repetir não duplica nada.
        Intervalos acima de 31 dias são recusados: a carga histórica é da Etapa 06.
        --contingencia MANIFESTO.json usa arquivos obtidos por outro meio (procedência registrada como contingência).
    python -m observatorio.operacao cobertura --inicio 2026-01-01 --fim 2026-11-12 [--saida cobertura.json]
        manifesto de cobertura dia a dia com lacunas explícitas, o escopo de fontes e a procedência de cada arquivo.
    python -m observatorio.operacao reabrir --fonte auniao --inicio 2026-01-01 --fim 2026-11-12 --responsavel NOME --justificativa TEXTO
        reabre (auditado) publicações com tentativas esgotadas; nada é reaberto automaticamente.
    python -m observatorio.operacao liberar-fonte --fonte auniao --responsavel NOME --justificativa TEXTO
        encerra (auditado) uma suspensão da fonte por recusa (403/429, robots, bloqueio) antes do prazo.
Códigos de saída (observatorio/operacao/saida.py), para agendadores:
    0 = sucesso integral; 1 = falha (erro ou divergência: exige intervenção); 2 = erro de uso;
    3 = concluído com pendências (dados gravados; retomar ou revisar); 4 = não executado / fonte inacessível.
    executar e validar-real: 1 se houver importação recusada, leitura em ERRO (também de execuções anteriores ainda
    não refeitas) ou arquivo que a classificação não processou; 3 se houver páginas pendentes ou fila.
    Retomada: python -m observatorio.operacao executar --refazer-pendentes

Depois: python -m observatorio.web --dados PASTA
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import fluxo, saida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observatorio.operacao", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["executar", "demonstracao", "validar-real", "ouro", "corpus",
                                        "sonda", "coletar-dia", "coletar-intervalo", "cobertura", "reabrir", "liberar-fonte"])
    ap.add_argument("origem", nargs="?")
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--data", type=date.fromisoformat)
    ap.add_argument("--url")
    ap.add_argument("--saida", help="validar-real: arquivo JSON do relatório sem dados pessoais")
    ap.add_argument("--amostra", help="validar-real: arquivo de texto PRIVADO para a conferência humana")
    ap.add_argument("--pdfs", help="ouro: pasta com os PDFs oficiais (fora do repositório)")
    ap.add_argument("--manifesto", help="ouro: manifesto do conjunto-ouro")
    ap.add_argument("--refazer-pendentes", action="store_true",
                    help="executar: relê os arquivos com leitura em ERRO ou com páginas pendentes (retomada)")
    ap.add_argument("--esperado-privado", help="corpus: arquivo PRIVADO com os valores esperados por campo")
    ap.add_argument("--fonte", action="append", choices=["auniao", "cge"],
                    help="aquisição e cobertura: fonte(s); padrão único em coleta.fontes.PADRAO (auniao)")
    ap.add_argument("--responsavel", help="reabrir / liberar-fonte: quem decide (fica na trilha de auditoria)")
    ap.add_argument("--justificativa", help="reabrir / liberar-fonte: por quê (fica na trilha de auditoria)")
    ap.add_argument("--inicio", type=date.fromisoformat)
    ap.add_argument("--fim", type=date.fromisoformat)
    ap.add_argument("--limite", type=int, help="aquisição: máximo de downloads nesta execução")
    ap.add_argument("--dry-run", action="store_true", help="aquisição: só descobre e lista o que seria baixado")
    ap.add_argument("--reverificar", action="store_true", help="aquisição: consulta de novo publicações já baixadas")
    ap.add_argument("--contingencia", help="aquisição: manifesto JSON de arquivos obtidos por outro meio")
    ap.add_argument("--permitir-longo", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--hashes", help="sonda: JSON {url_oficial: sha256} com hashes históricos para comparação")
    ap.add_argument("--guardar", help="sonda: pasta (fora do Git) onde copiar o PDF baixado")
    a = ap.parse_args(argv)
    if a.comando == "corpus":
        from . import corpus
        if not a.pdfs or not a.esperado_privado:
            ap.error("corpus exige --pdfs PASTA e --esperado-privado ARQUIVO")
        resultado = corpus.executar(a.pdfs, a.esperado_privado)
        if a.saida:
            with open(a.saida, "w", encoding="utf-8") as destino:
                json.dump(resultado, destino, ensure_ascii=False, indent=2)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return resultado["codigo_de_saida"]       # 0 só com o contrato inteiro avaliado e conferido
    if a.comando in ("sonda", "coletar-dia", "coletar-intervalo", "cobertura", "reabrir", "liberar-fonte"):
        from . import aquisicao
        from ..coleta.fontes import selecionar
        siglas = selecionar(a.fonte)
        if a.comando in ("reabrir", "liberar-fonte"):
            if len(siglas) != 1 or not a.responsavel or not a.justificativa:
                ap.error(f"{a.comando} exige exatamente uma --fonte, --responsavel e --justificativa")
            if a.comando == "liberar-fonte":
                resultado = aquisicao.liberar_fonte(a.dados, siglas[0], a.responsavel, a.justificativa)
            else:
                if not a.inicio or not a.fim:
                    ap.error("reabrir exige --inicio e --fim")
                resultado = aquisicao.reabrir(a.dados, siglas[0], a.inicio, a.fim, a.responsavel, a.justificativa)
            aquisicao.gravar(resultado, a.saida)
            return saida.SUCESSO
        if a.comando == "sonda":
            hashes = json.loads(open(a.hashes, encoding="utf-8").read()) if a.hashes else None
            relatorio = aquisicao.sonda(siglas[0], hashes, guardar_em=a.guardar)
            aquisicao.gravar(relatorio, a.saida)
            return 0 if relatorio["situacao"] == "DOWNLOAD_INTEGRO" else 4
        if a.comando == "cobertura":
            if not a.inicio:
                ap.error("cobertura exige --inicio")
            manifesto = aquisicao.cobertura(a.dados, siglas, a.inicio, a.fim or date.today())
            aquisicao.gravar(manifesto, a.saida)
            # 0 só sem lacunas conhecidas no escopo declarado; lacunas são pendência (3), não sucesso integral.
            return saida.SUCESSO if not manifesto["lacunas"] and not manifesto["sem_data_identificada"] else saida.CONCLUIDO_COM_PENDENCIAS
        if a.comando == "coletar-dia":
            if not a.data:
                ap.error("coletar-dia exige --data")
            inicio = fim = a.data
        else:
            if not a.inicio or not a.fim:
                ap.error("coletar-intervalo exige --inicio e --fim")
            inicio, fim = a.inicio, a.fim
        from ..coleta.coletor import IntervaloInvalido
        try:
            resumo = aquisicao.coletar(a.dados, siglas, inicio, fim, a.limite, a.dry_run, a.reverificar, a.contingencia,
                                       a.permitir_longo)
        except IntervaloInvalido as erro:
            ap.error(str(erro))
        aquisicao.gravar(resumo, a.saida)
        if resumo["fontes"] and all(aquisicao.fonte_bloqueada(p) for p in resumo["fontes"].values()):
            return 4
        return 3 if resumo["pendencias"] else 0
    if a.comando == "ouro":
        from . import ouro
        if not a.pdfs:
            ap.error("ouro exige --pdfs PASTA")
        resultado = ouro.executar(a.pdfs, a.manifesto or ouro.MANIFESTO_PADRAO)
        if a.saida:
            with open(a.saida, "w", encoding="utf-8") as destino:
                json.dump(resultado, destino, ensure_ascii=False, indent=2)
        print(json.dumps({"resumo": resultado["resumo"], "edicoes": [{k: e.get(k) for k in ("data", "situacao", "divergencias", "desempenho")}
                                                                     for e in resultado["edicoes"]]}, ensure_ascii=False, indent=2))
        return ouro.codigo_de_saida(resultado)
    if a.comando == "validar-real":
        from . import validacao_real
        if not a.origem or not a.data:
            ap.error("validar-real exige ARQUIVO.pdf e --data")
        from pathlib import Path
        if not Path(a.origem).is_file():
            print(json.dumps({"resultado": "ARQUIVO_AUSENTE", "codigo_de_saida": saida.NAO_EXECUTADO,
                              "arquivo": Path(a.origem).name}, ensure_ascii=False, indent=2))
            return saida.NAO_EXECUTADO
        resumo = validacao_real.executar(a.origem, a.data, a.url, a.dados, a.amostra)
        if a.saida:
            with open(a.saida, "w", encoding="utf-8") as destino:
                json.dump(resumo, destino, ensure_ascii=False, indent=2)
        print(json.dumps({k: v for k, v in resumo.items() if k != "fluxo"}, ensure_ascii=False, indent=2))
        return resumo["codigo_de_saida"]
    if a.comando == "demonstracao":
        from . import demonstracao
        print(json.dumps(demonstracao.criar(a.dados), ensure_ascii=False, indent=2))
        return saida.SUCESSO
    resumo = fluxo.executar(a.dados, a.origem, a.data, a.url, a.refazer_pendentes)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return resumo["resultado"]["codigo"]


if __name__ == "__main__":
    sys.exit(main())
