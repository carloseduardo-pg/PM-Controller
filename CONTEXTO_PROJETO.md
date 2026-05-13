# CONTEXTO DO PROJETO — DAILY (PM Controller)

Este arquivo resume o **propósito**, a **arquitetura**, o que já foi **implementado** e **decisões recentes**, para reutilizar em novos chats quando o contexto da conversa acabar.  
**Última atualização:** maio/2026.

---

## 1. O que é o produto

- **Nome na interface e PWA:** **DAILY** (antes referido como “Project Management” / diário de P.O.).
- **Função:** aplicação web (**PWA**) para **registro de atividades** por projeto (duração em minutos), **agenda** com lembretes, **dashboard** com gráficos, **relatório diário** em bullets, gestão de **clientes/empresas**, **projetos** e **anexos**.
- **Público:** uso individual / corporativo (Product Owner, gerente de projetos).

---

## 2. Estrutura de pastas (raiz do repositório)

| Caminho | Conteúdo |
|---------|-----------|
| `run.py` | Entrada do servidor Flask (`FLASK_PORT`, padrão 5000). |
| `requirements.txt` | `Flask`, `flask-cors`, `mysql-connector-python` (Werkzeug vem com Flask — senhas e uploads). |
| `backend/app.py` | API REST, sessão, rotas estáticas, lógica de negócio. |
| `backend/config.py` | `DB_NAME`, `DB_CONFIG_BASE`, `get_connection()` — **MariaDB** (`MARIADB_*` via env). |
| `backend/criar_banco.py` | Cria schema `po_diary_db`, usuário inicial, **empresas/projetos iniciais** (sem logs/agenda fake). |
| `frontend/index.html` | SPA principal (HTML + CSS + JS inline). |
| `frontend/login.html` | Página de login. |
| `frontend/manifest.json` | PWA (nome DAILY, cores de tema). |
| `frontend/sw.js` | Service worker — cache shell (ver constante `CACHE` no arquivo). |
| `frontend/icons/` | Ícones PWA (192/512). |
| `imagens/` | Branding: `logo_daily.png`, `logo_empresarial_daily.png` (pode existir `.jpeg` legado — o login usa **.png**). |
| `uploads/` | Anexos de projetos (criado em runtime). |
| `README.md` | Instalação geral (pode citar nomes antigos; este **CONTEXTO** complementa). |

Banco padrão: **`po_diary_db`** (`backend/config.py` → `DB_NAME`).

---

## 3. Variáveis de ambiente relevantes

| Variável | Uso |
|----------|-----|
| `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD` | Conexão MariaDB (`config.py`). |
| `FLASK_PORT` | Porta do servidor (`run.py`). |
| `FLASK_SECRET_KEY` | Sessão Flask (obrigatório trocar em produção). |

---

## 4. Backend (Flask)

### 4.1 Sessão e segurança

- Cookie de sessão; `user_id` após login.
- `@app.before_request` (`_require_login_api`): exige login em **`/api/*`**, exceto **`POST /api/auth/login`**. **`/uploads/`** exige sessão se não houver `user_id`.
- Páginas: **`/`** e **`/index.html`** redirecionam para **`/login.html`** se não autenticado; login redireciona para **`/`** se já autenticado.

### 4.2 Arquivos estáticos e assets

- `FRONTEND_DIR`, `ICONS_DIR`, `UPLOADS_DIR`, `IMAGENS_DIR`.
- **`GET /imagens/<filename>`** — serve `imagens/` com proteção contra `..` e path absoluto (útil para logos no login **sem** exigir login).
- Demais estáticos: raiz PWA, manifest, sw, ícones.

### 4.3 Autenticação (`usuarios`)

- Senha: **Werkzeug** `generate_password_hash` / `check_password_hash`.
- **`GET/POST/DELETE /api/auth/avatar`** — BLOB + MIME no MariaDB (`avatar_blob`, `avatar_mime`), limite 2 MB, tipos JPEG/PNG/WebP/GIF.
- **`GET /api/auth/me`** — objeto `user` inclui **`tem_avatar`** (booleano; backend normaliza tipos vindos do MySQL).
- Perfil: `PUT /api/auth/profile`, `PUT /api/auth/password`, login/logout.

### 4.4 Domínio principal (APIs)

- **Clientes:** `GET/POST /api/clientes`
- **Projetos:** `GET/POST /api/projetos`, `GET/PUT/DELETE /api/projetos/<id>`, atividades, anexos, servir arquivo em `/uploads/projetos/...`
- **Diário (logs):** `POST /api/logs`, `GET /api/logs/dia/<data>`, `GET/PUT/DELETE /api/logs/<id>` — categorias enum, `data_hora_fim` derivada/ajustada conforme schema.
- **Relatório:** `GET /api/relatorio_diario/<data>`
- **Dashboard:** `GET /api/dashboard/stats` (mês/ano)
- **Agenda:** `GET/POST /api/agenda` (+ fluxo de notificações no front)

Detalhes de payloads estão em `app.py` e no JS que chama `apiGet`/`apiPost`/etc.

---

## 5. Banco de dados (`criar_banco.py`)

Tabelas principais (resumo): **`usuarios`**, **`clientes`**, **`projetos`**, **`logs_diarios`**, **`agenda`**, **`projeto_anexos`**. FKs e índices conforme script.

### Usuário inicial

- Script **`garantir_usuario_padrao`**: usuário **`cadu`**, senha inicial **`senha123`** (se não existir). Ajustar em produção.

### Dados iniciais reais (sem Acme/Beta fake)

Função **`popular_dados_iniciais`** — só roda se **`clientes`** estiver **vazio**:

| Cliente (empresa) | Projeto |
|-------------------|---------|
| João Barbosa Advocacia | Protótipo SAJ 2026 |
| FB Minerios | BA Santana - Manus Breno |

Não insere mais logs/agenda de demonstração automáticos.

---

## 6. Frontend — SPA (`index.html`)

### 6.1 Navegação (seções)

Home, Diário, Projetos, Dashboard, Relatório, Agenda, **Ajustes** (tema, perfil, senha, avatar, “Sobre”).

### 6.2 Marca e tema **DAILY**

- **Claro:** fundos branco/cinza claro; **detalhes em azul** (`#2563eb` e afins).
- **Escuro:** preto/cinza escuro; **detalhes em verde** (`#4ade80` e afins).
- Tipografia: **Inter** + **Roboto Slab** (títulos de página/cards/modais) + **Roboto Mono** (rótulos tipo “NAVEGAÇÃO”).
- **Favicon:** `/imagens/logo_daily.png`.

### 6.3 Sidebar

- Largura **`--sidebar-w: 236px`** (expandida); **72px** quando `html[data-sidebar-collapsed="true"]`.
- **Topo:** barra de ferramentas (recolher menu + **sino**); abaixo, **identidade**: foto **acima** do nome e “DAILY”, centralizado.
- **Avatar:** variável **`--brand-avatar-size`** — expandido `min(185px, calc(var(--sidebar-w) - 1.35rem))`; recolhido **38px**; círculo, foto via **`fetch` + object URL** para credenciais confiáveis; fallback com iniciais.
- **Logo rodapé:** `/imagens/logo_daily.png` acima do botão **Sair**; some no modo só ícones.
- **Notificações:** painel **`position: fixed`**, posicionado à **direita do sino** via JS (`positionNotifyPanel`, `clearNotifyPanelPosition`), `z-index` alto; recalcula em resize/scroll.

### 6.4 Gráficos

Chart.js via CDN; paleta usa `--accent` e cores auxiliares definidas no CSS.

### 6.5 Estado local

Ex.: `po_theme`, `po_sidebar_collapsed`, chaves de notificação da agenda — ver constantes `LS_*` no script.

---

## 7. Login (`login.html`)

- Branding: **`/imagens/logo_empresarial_daily.png`** (correto em PNG; não usar `.jpeg` no HTML).
- Fundo minimalista: **hexágonos grandes** nos cantos (sem padrão repetitivo antigo).
- Login: `POST /api/auth/login` JSON; tema claro/escuro alinhado ao app.

---

## 8. PWA (`manifest.json` + `sw.js`)

- Nome curto/long **DAILY**; `theme_color` / `background_color` alinhados ao tema claro.
- **`sw.js`:** precache de shell + logos; nome do cache em **`po-diary-shell-v10`** (incrementar ao mudar lista de precache para invalidar clientes antigos).
- **`/api/*`:** no SW, fetch direto (não cachear como shell); offline devolve JSON 503 genérico.

---

## 9. O que foi evoluído ao longo do tempo (checklist histórico)

- Rebrand para **DAILY**, paleta e logos em **`imagens/`**.
- Rota **`/imagens/`** pública com sanitização de path.
- **`criar_banco`:** empresas/projetos reais; remoção de seed de logs/agenda fictícios.
- Login: fundo com hexágonos grandes; troca **jpeg → png** corporativo; SW atualizado.
- **Avatar:** API `tem_avatar` robusta; header com foto grande; depois reorganização (foto acima do nome); painel notificações à direita (fixed + JS); redução ~17% do avatar e sidebar **236px**; avatar recolhido **38px**.

---

## 10. Como retomar trabalho num chat novo

1. Anexar ou colar trechos deste **`CONTEXTO_PROJETO.md`** + arquivos que for mexer (`app.py`, `index.html`, etc.).
2. Dizer: porta (`run.py`), nome do banco, usuário de teste **`cadu`**, e se o ambiente é local ou deploy.
3. Se o problema for **PWA antigo**, lembrar de **subir versão do `CACHE` em `sw.js`** e hard refresh.

---

## 11. Melhorias futuras (não implementadas aqui)

- README alinhado 100% ao nome **DAILY** e ao manifest atual.
- Remover arquivo **`logo_empresarial_daily.jpeg`** da pasta se não for mais usado (evitar confusão).
- Testes automatizados (API + E2E).
- `FLASK_SECRET_KEY` obrigatório fora de dev.

---

*Documento gerado para preservação de contexto do repositório **PM Controller** (produto **DAILY**).*
