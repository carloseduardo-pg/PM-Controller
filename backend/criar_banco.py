#!/usr/bin/env python3
"""
Script de criação do banco MariaDB para o Diário de Bordo de P.O. (PWA).

Cria também a tabela **usuarios** (login na API Flask), com foto de perfil opcional
(**avatar_blob** / **avatar_mime** no MariaDB), e o usuário inicial **cadu**
(senha **senha123**), se ainda não existir. Em produção, altere a senha pelo perfil
na interface ou diretamente no banco após o primeiro acesso.

Formas de executar (na raiz do projeto "PM Controller"):
  python -m backend.criar_banco

Ou pelo IDE em cima deste arquivo (Run Python File) — o caminho do projeto é ajustado abaixo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Protocol

# Rodar `python .../backend/criar_banco.py` não coloca a raiz do repo em sys.path; corrigimos aqui.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import mysql.connector
    from mysql.connector import Error
except ModuleNotFoundError:
    print(
        "Dependência ausente: mysql-connector-python.\n"
        "Na raiz do projeto execute:\n"
        "  pip install -r requirements.txt\n"
        "ou:\n"
        "  pip install mysql-connector-python",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

from backend.config import DB_NAME, get_connection


def garantir_usuario_padrao(cursor: _SqlCursor) -> None:
    """Um único usuário inicial: cadu / senha123 (werkzeug, mesmo algoritmo da API)."""
    try:
        from werkzeug.security import generate_password_hash
    except ModuleNotFoundError:
        print(
            "Dependência ausente: Werkzeug (use `pip install Werkzeug` ou `pip install -r requirements.txt`).",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    cursor.execute(f"USE `{DB_NAME}`")
    cursor.execute("SELECT id FROM usuarios WHERE username = %s", ("cadu",))
    if cursor.fetchone():
        return
    h = generate_password_hash("senha123")
    cursor.execute(
        """
        INSERT INTO usuarios (username, senha_hash, nome_exibicao, email)
        VALUES (%s, %s, %s, %s)
        """,
        ("cadu", h, "Nome do Usuário", None),
    )


class _SqlCursor(Protocol):
    def execute(self, operation: str, params: Any | None = None, multi: bool = False) -> Any: ...

    def executemany(self, operation: str, seq_params: list) -> None: ...

    def fetchone(self) -> dict[str, Any] | None: ...


def criar_esquema(cursor: _SqlCursor) -> None:
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.execute(f"USE `{DB_NAME}`")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            username VARCHAR(64) NOT NULL,
            senha_hash VARCHAR(255) NOT NULL,
            nome_exibicao VARCHAR(255) NOT NULL DEFAULT '',
            email VARCHAR(255) NULL,
            telefone VARCHAR(64) NULL,
            cargo VARCHAR(128) NULL,
            bio TEXT NULL,
            avatar_mime VARCHAR(127) NULL,
            avatar_blob MEDIUMBLOB NULL,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_usuarios_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    for col_sql in (
        "ADD COLUMN avatar_mime VARCHAR(127) NULL AFTER bio",
        "ADD COLUMN avatar_blob MEDIUMBLOB NULL AFTER avatar_mime",
    ):
        cursor.execute(
            """
            SELECT COUNT(*) AS c FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'usuarios'
              AND COLUMN_NAME = %s
            """,
            (col_sql.split()[2],),
        )
        col_row = cursor.fetchone()
        n = int(col_row["c"]) if col_row and col_row.get("c") is not None else 0
        if n == 0:
            cursor.execute(f"ALTER TABLE usuarios {col_sql}")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            nome VARCHAR(255) NOT NULL,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS projetos (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            cliente_id INT UNSIGNED NOT NULL,
            nome VARCHAR(255) NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            PRIMARY KEY (id),
            CONSTRAINT fk_projetos_cliente
                FOREIGN KEY (cliente_id) REFERENCES clientes (id)
                ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs_diarios (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            projeto_id INT UNSIGNED NOT NULL,
            data_hora DATETIME NOT NULL,
            data_hora_fim DATETIME NULL,
            categoria ENUM(
                'reuniao',
                'desenvolvimento',
                'planejamento',
                'suporte',
                'documentacao',
                'outro'
            ) NOT NULL DEFAULT 'outro',
            descricao TEXT NOT NULL,
            duracao_minutos INT UNSIGNED NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_logs_projeto
                FOREIGN KEY (projeto_id) REFERENCES projetos (id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            KEY idx_logs_projeto_data (projeto_id, data_hora),
            KEY idx_logs_duracao (duracao_minutos)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'logs_diarios'
          AND COLUMN_NAME = 'data_hora_fim'
        """
    )
    col_row = cursor.fetchone()
    n = int(col_row["c"]) if col_row and col_row.get("c") is not None else 0
    if n == 0:
        cursor.execute(
            """
            ALTER TABLE logs_diarios
            ADD COLUMN data_hora_fim DATETIME NULL
            AFTER data_hora
            """
        )
        cursor.execute(
            """
            UPDATE logs_diarios
            SET data_hora_fim = DATE_ADD(data_hora, INTERVAL duracao_minutos MINUTE)
            WHERE data_hora_fim IS NULL
            """
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agenda (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            projeto_id INT UNSIGNED NOT NULL,
            titulo VARCHAR(255) NOT NULL,
            descricao TEXT,
            data_hora_agendada DATETIME NOT NULL,
            notificar_em DATETIME NULL,
            status ENUM('pendente', 'concluido', 'cancelado', 'adiado')
                NOT NULL DEFAULT 'pendente',
            PRIMARY KEY (id),
            CONSTRAINT fk_agenda_projeto
                FOREIGN KEY (projeto_id) REFERENCES projetos (id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            KEY idx_agenda_projeto (projeto_id),
            KEY idx_agenda_data (data_hora_agendada)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS projeto_anexos (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            projeto_id INT UNSIGNED NOT NULL,
            nome_original VARCHAR(255) NOT NULL,
            nome_armazenado VARCHAR(255) NOT NULL,
            mime_type VARCHAR(127) NULL,
            tamanho_bytes INT UNSIGNED NOT NULL DEFAULT 0,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_anexos_projeto (projeto_id),
            CONSTRAINT fk_anexos_projeto
                FOREIGN KEY (projeto_id) REFERENCES projetos (id)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def popular_dados_iniciais(cursor: _SqlCursor) -> None:
    """Se não houver clientes, insere suas empresas e projetos atuais (sem dados fictícios de diário/agenda)."""
    cursor.execute(f"USE `{DB_NAME}`")

    cursor.execute("SELECT COUNT(*) AS n FROM clientes")
    row = cursor.fetchone()
    if row and int(row["n"]) > 0:
        return

    cursor.execute(
        """
        INSERT INTO clientes (nome) VALUES
            ('João Barbosa Advocacia'),
            ('FB Minerios')
        """
    )

    cursor.execute(
        """
        INSERT INTO projetos (cliente_id, nome, ativo) VALUES
            (1, 'Protótipo SAJ 2026', TRUE),
            (2, 'BA Santana - Manus Breno', TRUE)
        """
    )


def main() -> int:
    conn = None
    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        try:
            criar_esquema(cursor)
            garantir_usuario_padrao(cursor)
            popular_dados_iniciais(cursor)
            conn.commit()
        except Error:
            conn.rollback()
            raise
        finally:
            cursor.close()

        print(f"Banco `{DB_NAME}` criado/atualizado com sucesso.")
        print("Login da aplicação: usuário cadu (criado se não existia; senha inicial senha123).")
        print("Empresas e projetos iniciais inseridos (somente se ainda não havia clientes no banco).")
        return 0

    except Error as e:
        print(f"Erro MariaDB/MySQL: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Erro de rede ou socket: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Configuração inválida (ex.: MARIADB_PORT): {e}", file=sys.stderr)
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
