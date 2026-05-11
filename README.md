# PM Controller

Sistema web para **controle e registro das atividades diárias** de um gerente de projetos / Product Owner, com foco em **métricas de tempo** para alimentar um dashboard.

Repositório: [github.com/carloseduardo-pg/PM-Controller](https://github.com/carloseduardo-pg/PM-Controller)

## Objetivo do aplicativo

O **Diário de Bordo de P.O.** (planejado como PWA) centraliza:

- **Clientes** e **projetos** vinculados
- **Logs diários** por projeto: data/hora, categoria, descrição e **duração em minutos** (campo essencial para gráficos e indicadores no dashboard)
- **Agenda**: compromissos por projeto, lembrete (`notificar_em`) e status

Este repositório inclui, nesta fase, o script que **cria o banco MariaDB** e opcionalmente **popula dados de teste** para validar o dashboard.

## Requisitos

- Python 3.10+
- MariaDB (ou MySQL compatível) acessível na rede local ou remota
- Pacote Python: `mysql-connector-python` (veja `requirements.txt`)

## Instalação rápida

```bash
cd "PM Controller"
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

## Banco de dados

- **Nome do banco:** `po_diary_db`
- **Charset:** `utf8mb4`

### Tabelas

| Tabela        | Descrição |
|---------------|-----------|
| `clientes`    | Cadastro de clientes (`id`, `nome`) |
| `projetos`    | Projetos por cliente (`cliente_id`, `nome`, `ativo`) |
| `logs_diarios`| Registros do dia (`projeto_id`, `data_hora`, `categoria`, `descricao`, `duracao_minutos`) |
| `agenda`      | Compromissos (`projeto_id`, `titulo`, `descricao`, `data_hora_agendada`, `notificar_em`, `status`) |

**Categorias de log (ENUM):** `reuniao`, `desenvolvimento`, `planejamento`, `suporte`, `documentacao`, `outro`

**Status da agenda (ENUM):** `pendente`, `concluido`, `cancelado`, `adiado`

### Criar esquema e dados de teste

```bash
python3 criar_banco.py
```

O script:

1. Cria o banco `po_diary_db` (se não existir) e as tabelas com chaves estrangeiras e índices úteis para consultas do dashboard.
2. Insere dados de exemplo **somente se** a tabela `clientes` estiver vazia (evita duplicar ao executar de novo).

### Variáveis de ambiente (opcional)

Sobrescrevem os padrões do script:

| Variável           | Padrão no código |
|--------------------|------------------|
| `MARIADB_HOST`     | `localhost`      |
| `MARIADB_PORT`     | `3306`           |
| `MARIADB_USER`     | `cadu`           |
| `MARIADB_PASSWORD` | `root`           |

Exemplo:

```bash
export MARIADB_USER=outro_usuario
export MARIADB_PASSWORD=segredo
python3 criar_banco.py
```

O usuário do MariaDB precisa de permissão para criar o banco (ou o banco já deve existir com permissões adequadas nas tabelas).

## Estrutura do repositório

```
PM Controller/
├── criar_banco.py    # Criação do BD + seed de teste
├── requirements.txt
└── README.md
```

## Roadmap sugerido

- API/backend consumindo este esquema
- Frontend PWA (dashboard com agregações por `duracao_minutos`, período e projeto)
- Autenticação e backup

## Licença

Uso pessoal / projeto próprio — defina uma licença quando publicar de forma ampla.
