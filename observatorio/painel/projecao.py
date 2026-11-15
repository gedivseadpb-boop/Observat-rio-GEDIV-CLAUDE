"""Política única do que cada perfil recebe, por tipo de registro.

Lista explícita de campos PERMITIDOS: um campo novo na base (ou no registro montado pelo painel) não chega ao perfil
público só porque existe — precisa ser acrescentado aqui, de propósito. A proteção acontece no servidor, antes da
resposta sair; esconder no navegador não basta.

Achado das auditorias de 14/11/2026: a justificativa livre da revisão de um evento (`evento.fundamento`) era
entregue sem autenticação em `/api/painel`. A justificativa continua guardada na base e na trilha de auditoria, e a
gerência autenticada continua a vê-la.
"""
from __future__ import annotations

GERENCIA, PUBLICO = "gerencia", "publico"

# Campos que o perfil público recebe com valor neutro (vazio), para que a página continue funcionando
# sem condicionais; o conteúdo real fica só com a gerência.
_NEUTROS = {"pendencias": [], "pdf_no_acervo": None, "texto": None, "processos_citados": [], "trecho": None}

_PUBLICOS = {
    "evento": ("id", "tipo", "subtipo", "data_publicacao", "pagina", "modificador", "estado", "ato_original_id",
               "ato_sugerido_id", "vinculo", "resenhas_citadas", "url_oficial"),
    "resenha": ("ato_id", "resenha", "sufixo", "data", "pagina", "eixo", "modalidade", "condicao", "grupo", "subcategoria",
                "vinculo", "natureza", "decisoes", "deferido", "indeferido", "refeito", "sem_efeito", "url_oficial", "conflito_aberto"),
    "outra_publicacao": ("id", "tipo", "nome_tipo", "data", "pagina", "titulo", "vinculo", "situacao", "url_oficial"),
    # Relatório `validar-real --saida`, documentado como "sem dados pessoais": mesma regra do perfil público.
    "evento_relatorio": ("tipo", "subtipo", "pagina", "modificador", "estado", "resenhas_citadas", "publicacoes_citadas"),
}
_PRIVADOS = {
    "evento": _PUBLICOS["evento"] + ("fundamento", "texto", "processos_citados", "pdf_no_acervo"),
    "resenha": _PUBLICOS["resenha"] + ("pendencias", "pdf_no_acervo"),
    "outra_publicacao": _PUBLICOS["outra_publicacao"] + ("trecho", "pdf_no_acervo"),
}
_NEUTROS_POR_TIPO = {
    "evento": ("texto", "processos_citados", "pdf_no_acervo"),
    "resenha": ("pendencias", "pdf_no_acervo"),
    "outra_publicacao": (),
    "evento_relatorio": (),
}

# Chaves de primeiro nível de /api/painel. "linhas" (decisões individuais) é sempre vazia para o público.
CHAVES_PAINEL = ("meta", "indicadores", "ajuda", "apoio", "series", "resenhas", "linhas", "eventos")


def campos(tipo: str, perfil: str) -> tuple[str, ...]:
    if perfil == GERENCIA and tipo in _PRIVADOS:
        return _PRIVADOS[tipo]
    return _PUBLICOS[tipo]


def projetar(tipo: str, registro: dict, perfil: str) -> dict:
    """Só os campos permitidos ao perfil; para o público, os campos de `_NEUTROS_POR_TIPO` saem vazios."""
    saida = {k: registro[k] for k in campos(tipo, perfil) if k in registro}
    if perfil != GERENCIA:
        saida.update({k: _NEUTROS[k] for k in _NEUTROS_POR_TIPO[tipo]})
    return saida
