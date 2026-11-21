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
- **Perfis (RBAC):** cada conta possui papel explícito (`gerencia` por padrão ou `admin` via `--papel admin`), além do perfil `publico` (sem login, apenas agregados conferidos). Rotas administrativas exigem papel `admin`.
- **Sessão e proteção anti-CSRF:** token aleatório válido por 8 horas (`Max-Age=28800`), armazenado no banco apenas como hash SHA-256. Em `POST /api/login`, o servidor emite o cookie `gediv_sessao` com `HttpOnly`, `SameSite=Strict`, `Path=/api` e flag `Secure` sob `X-Forwarded-Proto: https` (ou `GEDIV_COOKIE_SECURE=1`), além de devolver o token no corpo JSON (mantendo compatibilidade com `Authorization: Bearer` via `sessionStorage`; ao sair, sessão e cookie são encerrados). Para pedidos `POST` autenticados por cookie (exceto `/api/login`), `_verificar_csrf_cookie()` (`observatorio/web/servidor.py`) bloqueia `Sec-Fetch-Site: cross-site` com HTTP `403` e, quando o cabeçalho `Origin` está presente, exige origem autorizada em `--origem-admin` ou igual ao `Host`. **Não há** cabeçalho customizado nem token sincronizado anti-CSRF implementado no backend atual. *(Fragilidades registradas para auditoria de segurança separada: `_verificar_csrf_cookie()` falha-aberta caso `Sec-Fetch-Site` e `Origin` estejam ambos ausentes, não bloqueia `Sec-Fetch-Site: same-site` sem `Origin`, `/api/login` executa antes dessa verificação e `sessionStorage` permanece sensível a eventual XSS.)*
- **Bloqueio:** 5 senhas erradas seguidas bloqueiam a conta por 15 minutos.
- **Mensagens de erro:** são idênticas para usuário inexistente, senha errada, conta bloqueada ou conta desativada.
- **Autoria:** quem está logado é sempre o responsável pela revisão. O nome enviado pelo navegador é ignorado. Entradas, saídas e alterações de papel/conta ficam na trilha de auditoria (`ENTRAR`/`SAIR`, etc.).
- **Trocas de conta:** trocar a senha, alterar o papel (`papel`) ou desativar a conta encerra imediatamente as sessões abertas.
- **Acesso a partir de outro site (CORS):** só é liberado para as origens explicitamente informadas em `--origem-admin` (apenas `https://` válidos, recusando `*`, `null`, HTTP remoto ou `localhost` como origem cross-origin), e só em `/api/`.
- **Token técnico legado (`GEDIV_TOKEN_GERENCIA`):** **desabilitado por padrão** na CLI (`python -m observatorio.web`). Para compatibilidade excepcional em automações locais, exige ativação explícita (`--habilitar-token-tecnico` ou `GEDIV_HABILITAR_TOKEN_TECNICO=1`) e segredo com **mínimo de 32 caracteres**, comparado em tempo constante (`hmac.compare_digest`), restrito estritamente ao papel `gerencia` (nunca concede privilégios `admin`) e registrado na trilha de auditoria apenas pelo prefixo do hash SHA-256 (jamais o segredo em texto claro).

## Como criar e administrar as contas (no servidor)

```bash
python -m observatorio.web.usuarios --dados dados criar maria.silva --nome "Maria da Silva" --papel gerencia
```

```bash
python -m observatorio.web.usuarios --dados dados criar coord.gediv --nome "Coordenação GEDIV" --papel admin
```

```bash
python -m observatorio.web.usuarios --dados dados papel maria.silva admin
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

- `tests/test_admin_contas.py` (Python): senhas, sessões (cookie `HttpOnly` + CSRF e Bearer), bloqueio, mensagens que não revelam se a conta existe, autoria, CORS estrito, token técnico legado desabilitado por padrão/endurecido (>= 32 chars, sem escalonamento para `admin`) e auditoria sem vazamento de segredo.
- `tests/test_uiux_perfis_rbac.py` (Python): separação de perfis (`publico`, `gerencia`, `admin`), revogação de sessões em mudança de papel e validação preliminar em `/api/admin/lote` sem importação no banco.
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
