# 25 — Painel do admin (`/admin-painel`) com login por pessoa

## O que é

Uma página de administração no mesmo endereço do painel, com a variação `/admin-painel`. Nela, cada pessoa da GEDIV entra com o próprio usuário e a própria senha para:

- conferir, corrigir, rejeitar ou reabrir decisões;
- resolver conflitos;
- consultar o histórico;
- baixar a planilha gerencial.

Endereço depois de publicado: `https://gedivseadpb-boop.github.io/Observat-rio-GEDIV-CLAUDE/admin-painel/`. **Nada foi publicado ainda.**

## Por que são duas partes

O GitHub Pages só serve arquivos públicos. Uma senha conferida no navegador, ou dados escondidos por CSS, podem ser lidos por qualquer pessoa. Por isso:

| Parte | Onde fica | O que contém |
|---|---|---|
| Página `admin-painel/` (`index.html`, `admin.js`, `admin.css`, `config.json`) | GitHub Pages (pública) | Só a tela. **Nenhum dado, nenhuma senha.** |
| Servidor gerencial (`python -m observatorio.web`) | Máquina da equipe, atrás de HTTPS | Banco, PDFs, contas, sessões, histórico |

A página só funciona depois que o servidor gerencial estiver no ar e o endereço dele estiver em `admin-painel/config.json`. Enquanto `config.json` tiver `"api": ""`, a página mostra "servidor gerencial ainda não configurado" e o formulário fica desligado.

O endereço do servidor nunca vem da barra de endereços, porque isso permitiria um link falso que roubasse senhas. Só são aceitos endereços `https://`, ou `http://` no próprio computador.

## Segurança das contas (`observatorio/web/contas.py`)

As contas ficam num banco separado, `contas.sqlite3`, na pasta de dados. O banco principal não muda.

- **Senha:** scrypt com sal próprio por conta. A senha nunca é guardada nem registrada. Exige no mínimo 10 caracteres e não pode conter o nome de usuário.
- **Sessão:** token aleatório que dura 8 horas. No banco fica só o SHA-256 do token. No navegador, o token fica só na aba aberta (`sessionStorage`) e é apagado ao sair.
- **Bloqueio:** 5 senhas erradas seguidas bloqueiam a conta por 15 minutos.
- **Mensagens de erro:** são idênticas para usuário inexistente, senha errada, conta bloqueada ou conta desativada.
- **Autoria:** quem está logado é sempre o responsável pela revisão. O nome enviado pelo navegador é ignorado. Entradas e saídas ficam no histórico (`ENTRAR`/`SAIR`).
- **Trocas de conta:** trocar a senha ou desativar a conta encerra as sessões abertas.
- **Acesso a partir de outro site (CORS):** só é liberado para as origens informadas em `--origem-admin`, e só em `/api/`.
- **Token antigo:** a credencial única `GEDIV_TOKEN_GERENCIA` continua aceita, por compatibilidade.

## Como criar e administrar as contas (no servidor)

```bash
python -m observatorio.web.usuarios --dados dados criar maria.silva --nome "Maria da Silva"
```

```bash
python -m observatorio.web.usuarios --dados dados listar
```

```bash
python -m observatorio.web.usuarios --dados dados senha maria.silva
```

```bash
python -m observatorio.web.usuarios --dados dados desativar maria.silva
```

A senha é digitada duas vezes, sem aparecer na tela.

## Como ligar o servidor para o `/admin-painel`

```bash
python -m observatorio.web --dados dados --endereco 127.0.0.1 --porta 8000 --origem-admin https://gedivseadpb-boop.github.io
```

O servidor precisa ficar atrás de um HTTPS institucional (proxy reverso). Depois disso, o endereço público dele vai em `painel-v2/admin-painel/config.json`, por exemplo `{"api": "https://gediv-api.exemplo.gov.br"}`.

## Testes

- `tests/test_admin_contas.py` (Python, 14 testes): senhas, sessões, bloqueio, mensagens que não revelam se a conta existe, autoria, CORS e token antigo.
- `tests/test_admin_painel.cjs` (jsdom, 6 testes): a página estática não contém dados, o caso sem servidor configurado, endereço inseguro recusado, login errado e certo, token no cabeçalho, saída, sessão expirada.
- **Navegador, de ponta a ponta,** com servidor local e dados sintéticos (17 verificações):
  - login errado e certo;
  - conferência que exige justificativa e a confirmação de consulta ao PDF;
  - revisão gravada no nome da pessoa;
  - histórico;
  - abas;
  - planilha baixada;
  - recarregar a página mantém a sessão;
  - celular de 360 px sem rolagem lateral;
  - depois de sair, o token é recusado pelo servidor.

## Desativar e reativar

O painel do admin segue o mesmo mecanismo reversível do documento 24. Também dá para desligar só o acesso de uma pessoa: o comando `desativar` encerra as sessões dela, e o comando `ativar` devolve o acesso sem perder o histórico.
