"""Nenhuma justificativa livre nem campo interno chega ao perfil público (auditorias de 14/11/2026).

A justificativa de revisão de um evento era gravada em `evento.fundamento` e devolvida sem autenticação em
`/api/painel`. Dados SINTÉTICOS; o marcador abaixo simula uma observação interna com nome, matrícula e processo.
"""
import json
import unittest

from observatorio.gerencias.gediv import catalogo as C
from observatorio.painel import exportacao, indicadores, projecao
from observatorio.revisao import servico
from tests import test_painel as TP

GER, JUST, REVISOR = TP.GER, TP.JUST, TP.REVISOR

MARCADOR = "MARCADOR-PRIVADO-7731 PESSOA FICTICIA matricula 9000099 processo SAD-PRC-2026/99999"
PUBLICO = indicadores.PUBLICO
CHAVES_PRIVADAS = {"fundamento", "justificativa", "revisor", "revisado_em", "servidor", "matricula", "processo", "lotacao",
                   "cargo", "trecho", "detalhe"}


def chaves_com_conteudo(objeto, caminho=""):
    """(caminho, chave) de toda chave privada com valor não vazio, em qualquer nível da estrutura."""
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            if k in CHAVES_PRIVADAS and v not in (None, "", [], {}):
                yield f"{caminho}.{k}"
            yield from chaves_com_conteudo(v, f"{caminho}.{k}")
    elif isinstance(objeto, list):
        for i, v in enumerate(objeto):
            yield from chaves_com_conteudo(v, f"{caminho}[{i}]")


def conferir_originais(banco):
    for ato in banco.con.execute("SELECT id FROM ato WHERE natureza = 'ORIGINAL'").fetchall():
        try:
            servico.revisar_ato(banco, ato["id"], servico.CONFERIR, REVISOR, JUST, True, True)
        except servico.Recusada:          # já conferido pela base do teste
            pass


class Cenarios(TP.Base):
    def setUp(self):
        super().setUp()
        self.base_padrao()
        conferir_originais(self.banco)
        self.eventos = {e["tipo"]: e["id"] for e in self.banco.con.execute("SELECT id, tipo FROM evento")}

    def revisar_evento(self, tipo, decisao, justificativa=MARCADOR):
        servico.revisar_evento(self.banco, self.eventos[tipo], decisao, REVISOR, justificativa, None, True)

    def estado(self, tipo):
        return self.banco.con.execute("SELECT estado, fundamento FROM evento WHERE id = ?", (self.eventos[tipo],)).fetchone()

    def assertPublicoLimpo(self, dados):
        texto = json.dumps(dados, ensure_ascii=False)
        self.assertNotIn("MARCADOR-PRIVADO-7731", texto)
        self.assertNotIn("PESSOA FICTICIA", texto)
        self.assertEqual(list(chaves_com_conteudo(dados)), [])


class TesteProjecaoPublica(Cenarios):
    def test_evento_validado_com_justificativa_privada(self):
        self.revisar_evento(C.SEM_EFEITO, servico.VINCULAR)
        self.assertEqual(tuple(self.estado(C.SEM_EFEITO)), ("VALIDADO", MARCADOR))          # guardada na base
        publico = indicadores.painel(self.banco, {}, PUBLICO)
        self.assertEqual(publico["indicadores"]["sem_efeito"], 1)                           # o evento conta...
        self.assertEqual([e["estado"] for e in publico["eventos"]], ["VALIDADO"])            # ...e aparece
        self.assertPublicoLimpo(publico)                                                    # sem a justificativa
        gerencia = indicadores.painel(self.banco, {}, GER)
        self.assertIn(MARCADOR, [e["fundamento"] for e in gerencia["eventos"]])             # a gerência continua vendo

    def test_evento_sugerido_reaberto_e_rejeitado(self):
        self.revisar_evento(C.SEM_EFEITO, servico.VINCULAR, "primeira conferência sem marcador")
        self.revisar_evento(C.SEM_EFEITO, servico.REABRIR)                                  # reaberto → volta a SUGERIDO
        self.assertEqual(tuple(self.estado(C.SEM_EFEITO)), ("SUGERIDO", MARCADOR))
        republicacao = next(t for t in self.eventos if t != C.SEM_EFEITO)
        self.revisar_evento(republicacao, servico.REJEITAR)
        self.assertEqual(self.estado(republicacao)["estado"], "REJEITADO")
        for escopo in ("conferido", "pendente"):                                            # o público não escolhe escopo
            with self.subTest(escopo=escopo):
                publico = indicadores.painel(self.banco, {"escopo": escopo}, PUBLICO)
                self.assertEqual(publico["eventos"], [])                                    # nenhum validado
                self.assertPublicoLimpo(publico)
        gerencia = indicadores.painel(self.banco, {"escopo": "pendente"}, GER)
        self.assertEqual({e["estado"]: e["fundamento"] for e in gerencia["eventos"]}, {"SUGERIDO": MARCADOR, "REJEITADO": MARCADOR})

    def test_justificativa_automatica_do_classificador_tambem_fica_so_com_a_gerencia(self):
        self.banco.con.execute("UPDATE evento SET estado = 'VALIDADO', ato_original_id = ato_sugerido_id, fundamento = ?", (MARCADOR,))
        self.banco.con.commit()
        self.assertPublicoLimpo(indicadores.painel(self.banco, {}, PUBLICO))

    def test_outras_publicacoes_e_resenhas(self):
        self.banco.con.execute("UPDATE outra_publicacao SET trecho = ?", (MARCADOR,))
        self.banco.con.commit()
        self.assertTrue(indicadores.outras_publicacoes(self.banco, PUBLICO))
        self.assertPublicoLimpo(indicadores.outras_publicacoes(self.banco, PUBLICO))
        self.assertIn(MARCADOR, [o["trecho"] for o in indicadores.outras_publicacoes(self.banco, GER)])
        resenhas = indicadores.painel(self.banco, {}, PUBLICO)["resenhas"]
        self.assertTrue(resenhas)
        self.assertEqual({tuple(r["pendencias"]) for r in resenhas}, {()})                 # pendências internas ficam fora
        self.assertEqual({r["pdf_no_acervo"] for r in resenhas}, {None})

    def test_campo_novo_na_base_nao_vaza_por_omissao(self):
        evento = {"id": "e1", "tipo": "X", "estado": "VALIDADO", "fundamento": MARCADOR, "campo_novo_interno": MARCADOR}
        self.assertNotIn("MARCADOR-PRIVADO-7731", json.dumps(projecao.projetar("evento", evento, PUBLICO)))
        self.assertNotIn("campo_novo_interno", projecao.projetar("evento", evento, GER))
        self.assertEqual(projecao.projetar("evento", evento, GER)["fundamento"], MARCADOR)

    def test_relatorio_do_validar_real_nao_leva_justificativa(self):
        evento = {"tipo": "SEM_EFEITO", "subtipo": None, "pagina": 2, "modificador": "Portaria 1/2026", "estado": "VALIDADO",
                  "resenhas_citadas": ["904/2026"], "publicacoes_citadas": [], "fundamento": MARCADOR, "texto": MARCADOR}
        self.assertNotIn("MARCADOR-PRIVADO-7731", json.dumps(projecao.projetar("evento_relatorio", evento, PUBLICO)))

    def test_exportacao_da_gerencia_mantem_a_justificativa(self):
        self.revisar_evento(C.SEM_EFEITO, servico.VINCULAR)
        planilha = exportacao.planilha(indicadores.painel(self.banco, {}, GER))
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(planilha)) as z:
            self.assertTrue(any("MARCADOR-PRIVADO-7731" in z.read(n).decode("utf-8", "replace") for n in z.namelist()))


class TesteAPIPrivacidade(TP.Base):
    TOKEN, pedir = TP.TesteAPI.TOKEN, TP.TesteAPI.pedir          # mesmo servidor de teste, sem herdar os testes de lá

    def setUp(self):
        super().setUp()
        self.base_padrao()
        self.servidor = TP.criar_servidor(self.pasta, self.TOKEN, porta=0)
        TP.threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
    ROTAS_PUBLICAS = ("/api/painel", "/api/painel?escopo=pendente", "/api/painel?cartao=sem_efeito", "/api/outras",
                      "/api/saude", "/api/catalogo", "/", "/estatico/app.js")

    def test_marcador_nunca_sai_sem_credencial_e_a_gerencia_continua_revisando(self):
        eventos = {e["tipo"]: e["id"] for e in self.banco.con.execute("SELECT id, tipo FROM evento")}
        conferir_originais(self.banco)
        # A revisão gerencial pela própria API, com justificativa contendo o marcador.
        status, _, corpo = self.pedir("/api/revisao", self.TOKEN, {"alvo": "evento", "id": eventos[C.SEM_EFEITO], "decisao": "VINCULAR",
                                                                    "responsavel": REVISOR, "justificativa": MARCADOR, "confirma_fonte": True})
        self.assertEqual(status, 200, corpo)
        self.banco.con.execute("UPDATE outra_publicacao SET trecho = ?", (MARCADOR,))
        self.banco.con.commit()
        for rota in self.ROTAS_PUBLICAS:
            with self.subTest(rota=rota):
                status, _, corpo = self.pedir(rota)
                self.assertEqual(status, 200)
                self.assertNotIn("MARCADOR-PRIVADO-7731", corpo.decode("utf-8"))
                if rota.startswith("/api/"):
                    self.assertEqual(list(chaves_com_conteudo(json.loads(corpo))), [])
        # A gerência autenticada vê a justificativa no painel e na trilha de auditoria.
        for rota in ("/api/painel", "/api/auditoria", "/api/outras"):
            with self.subTest(gerencia=rota):
                status, _, corpo = self.pedir(rota, self.TOKEN)
                self.assertEqual(status, 200)
                self.assertIn("MARCADOR-PRIVADO-7731", corpo.decode("utf-8"))
        # Credencial errada é tratada como público nas rotas abertas: nada privado.
        status, _, corpo = self.pedir("/api/painel", "credencial-errada-0123456789")
        self.assertNotIn("MARCADOR-PRIVADO-7731", corpo.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
