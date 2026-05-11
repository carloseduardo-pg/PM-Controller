# PM Controller · Diário de P.O.

Sistema web (**PWA**) para **controle e registro das atividades diárias** de um gerente de projetos / Product Owner, com **métricas de tempo**, **dashboard interativo**, **relatório em bullet points** e **agenda com lembretes** integrados a um banco **MariaDB**.

Repositório: [github.com/carloseduardo-pg/PM-Controller](https://github.com/carloseduardo-pg/PM-Controller)

---

## Organização das pastas

| Pasta / arquivo | Função |
|-----------------|--------|
| **`backend/`** | Python: API Flask, configuração do MariaDB e script que cria o schema |
| **`frontend/`** | PWA servido na raiz da URL: `index.html`, `manifest.json`, `sw.js`, ícones |
| **`run.py`** | Ponto de entrada para subir o servidor (execute na **raiz** do projeto) |
| **`requirements.txt`** | Dependências pip |
| **`README.md`** | Esta documentação |

Configuração do banco (**`MARIADB_*`**) fica centralizada em **`backend/config.py`** e é usada tanto pelo script de criação do banco quanto pela API.

---

## Visão geral técnica

| Camada | Tecnologia | Função |
|--------|------------|--------|
| Dados | MariaDB (`po_diary_db`) | Clientes, projetos, logs diários (com **duração em minutos**), agenda |
| Backend | Python · Flask · `mysql-connector-python` | API REST JSON + CORS + arquivos em `frontend/` |
| Frontend | `frontend/index.html` (HTML/CSS/JS) + Chart.js (CDN) | UI estilo Notion/Asana clara, gráficos, registro e relatório |
| PWA | `manifest.json` · `sw.js` · ícones PNG | Instalação no Chrome/Edge, cache da interface, uso offline básico |
| Alertas | Notification API (navegador) | Consulta `/api/agenda` e dispara notificação no horário de `notificar_em` |

---

## Funcionalidades

- **Registro rápido de atividades** — projeto, categoria, descrição, **duração em minutos**, data/hora opcional (`POST /api/logs`).
- **Relatório diário** — texto em bullets para copiar (`GET /api/relatorio_diario/<YYYY-MM-DD>`).
- **Agenda** — lista por mês/ano com cards e status em pills (`GET /api/agenda`).
- **Dashboard** — doughnut (tempo por projeto) e barras (horas por dia na janela de 7 dias da API), com filtros **mês** e **ano** (`GET /api/dashboard/stats`).
- **PWA** — nome de exibição **PO Diary**, tema escuro no manifest (`#1e1f21`), modo **standalone**.
- **Notificações** — após conceder permissão no navegador, o front consulta a agenda periodicamente e usa **`notificar_em`** para alertas no sistema.

---

## Requisitos

- **Python** 3.10+
- **MariaDB** (ou MySQL compatível)
- Navegador recente (**Chrome** ou **Edge** recomendados para instalar o PWA)

Dependências: `requirements.txt` (`Flask`, `flask-cors`, `mysql-connector-python`).  
Se você rodar `backend/app.py` ou `backend/criar_banco.py` pelo botão **Run** do IDE, use um interpretador que já tenha recebido `pip install -r requirements.txt` (menu **Python: Select Interpreter** no VS Code/Cursor).

---

## Instalação e primeiro uso

Sempre trabalhe a partir da **raiz** do repositório (`PM Controller/`), para o pacote `backend` ser encontrado.

```bash
cd "PM Controller"
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS — no Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1. Banco de dados

```bash
python -m backend.criar_banco
```

- Cria o banco **`po_diary_db`** (se não existir), tabelas, FKs e índices.
- Insere dados de teste **somente se** a tabela `clientes` estiver vazia.

### 2. Subir a aplicação

```bash
python run.py
```

Equivalente (na raiz do projeto):

```bash
python -m backend.app
```

Por padrão o servidor escuta em **`0.0.0.0:5000`**. Porta alternativa:

```bash
FLASK_PORT=8080 python run.py
```

### 3. Acessar o app

Abra **http://localhost:5000/** ou **http://127.0.0.1:5000/**

- A mesma origem serve o HTML e os arquivos estáticos (`manifest.json`, `sw.js` e ícones continuam disponíveis nas rotas do Flask se precisar).

**Notificações no navegador:** o front pode solicitar permissão automaticamente e consultar a `/api/agenda` para lembretes com `notificar_em`.

> Use sempre o endereço do servidor (ex.: `http://localhost:5000` ou o IP da sua máquina na rede), não `file://`.

---

## Variáveis de ambiente (MariaDB)

Definidas em **`backend/config.py`** (variáveis `MARIADB_*`):

| Variável | Padrão no repositório |
|----------|------------------------|
| `MARIADB_HOST` | `localhost` |
| `MARIADB_PORT` | `3306` |
| `MARIADB_USER` | `cadu` |
| `MARIADB_PASSWORD` | `root` |

```bash
export MARIADB_USER=seu_usuario
export MARIADB_PASSWORD=sua_senha
python -m backend.criar_banco
python run.py
```

**Não commite senhas** em repositório público; use `.env` local (ignorado pelo `.gitignore`).

---

## Modelo de dados (resumo)

| Tabela | Campos principais |
|--------|-------------------|
| `clientes` | `id`, `nome` |
| `projetos` | `id`, `cliente_id`, `nome`, `ativo` |
| `logs_diarios` | `projeto_id`, `data_hora`, `categoria`, `descricao`, **`duracao_minutos`** |
| `agenda` | `projeto_id`, `titulo`, `descricao`, `data_hora_agendada`, **`notificar_em`**, `status` |

**Categorias de log (ENUM):** `reuniao`, `desenvolvimento`, `planejamento`, `suporte`, `documentacao`, `outro`

**Status da agenda (ENUM):** `pendente`, `concluido`, `cancelado`, `adiado`

Charset: **utf8mb4**.

---

## API REST (JSON)

Base: mesma origem (ex.: `http://localhost:5000`).

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/projetos` | Lista projetos com nome do cliente |
| `POST` | `/api/logs` | Corpo: `projeto_id`, `descricao`, `duracao_minutos`; opcionais: `categoria`, `data_hora` |
| `GET` | `/api/logs/dia/<data>` | `YYYY-MM-DD` — lista de logs do dia ordenada por horário (módulo Diário) |
| `GET` | `/api/relatorio_diario/<data>` | `data` = `YYYY-MM-DD`; retorna `bullets` |
| `GET` | `/api/dashboard/stats` | Query: `?mes=&ano=` |
| `GET` | `/api/agenda` | Query: `?mes=&ano=` |
| `POST` | `/api/agenda` | Novo item de agenda |

Detalhes em **`backend/app.py`**.

---

## Estrutura do repositório

```
PM Controller/
├── run.py                 # Inicia o Flask (use na raiz: python run.py)
├── requirements.txt
├── README.md
├── .gitignore
├── backend/
│   ├── __init__.py
│   ├── config.py          # DB_NAME, DB_CONFIG_BASE, get_connection()
│   ├── app.py             # Rotas /api/* e entrega de frontend/
│   └── criar_banco.py     # Schema + seed (python -m backend.criar_banco)
└── frontend/
    ├── index.html
    ├── manifest.json
    ├── sw.js
    └── icons/
        ├── icon-192.png
        └── icon-512.png
```

---

## Service Worker e offline

- Precache de `/`, `/index.html`, `manifest.json` e ícones (ver `frontend/sw.js`).
- **`/api/*`** em geral só por rede; em falha, resposta JSON de indisponibilidade.
- Após mudar **`sw.js`**, faça hard refresh ou **Unregister** do worker em DevTools se algo parecer “preso”.

---

## Próximos passos sugeridos

- Autenticação e multiusuário
- HTTPS em produção
- Backup do MariaDB
- Testes automatizados

---

## Licença

Uso pessoal / projeto próprio — defina uma licença explícita se for publicar de forma ampla.
