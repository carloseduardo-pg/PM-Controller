#!/usr/bin/env python3
"""
Script de criação do banco MariaDB para o Diário de Bordo de P.O. (PWA).
Requer: pip install mysql-connector-python
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Protocol

import mysql.connector
from mysql.connector import Error


class _SqlCursor(Protocol):
    def execute(self, operation: str, params: Any | None = None, multi: bool = False) -> Any: ...

    def executemany(self, operation: str, seq_params: list) -> None: ...

    def fetchone(self) -> dict[str, Any] | None: ...


DB_NAME = "po_diary_db"

# Conexão — padrão alinhado ao MariaDB local; sobrescreva com MARIADB_* se precisar
DB_CONFIG_BASE: dict[str, Any] = {
    "host": os.environ.get("MARIADB_HOST", "localhost"),
    "port": int(os.environ.get("MARIADB_PORT", "3306")),
    "user": os.environ.get("MARIADB_USER", "cadu"),
    "password": os.environ.get("MARIADB_PASSWORD", "root"),
}


def get_connection(*, database: str | None = None) -> mysql.connector.MySQLConnection:
    cfg = {**DB_CONFIG_BASE}
    if database:
        cfg["database"] = database
    return mysql.connector.connect(**cfg)


def criar_esquema(cursor: _SqlCursor) -> None:
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.execute(f"USE `{DB_NAME}`")

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


def popular_dados_teste(cursor: _SqlCursor) -> None:
    """Insere pelo menos 2 clientes, 3 projetos e vários logs com durações variadas."""
    cursor.execute(f"USE `{DB_NAME}`")

    cursor.execute("SELECT COUNT(*) AS n FROM clientes")
    row = cursor.fetchone()
    if row and int(row["n"]) > 0:
        return

    cursor.execute(
        """
        INSERT INTO clientes (nome) VALUES
            ('Acme Corp'),
            ('Beta Solutions Ltda')
        """
    )

    cursor.execute(
        """
        INSERT INTO projetos (cliente_id, nome, ativo) VALUES
            (1, 'Portal do Cliente', TRUE),
            (1, 'Integração ERP', TRUE),
            (2, 'App Mobile MVP', TRUE)
        """
    )

    base = datetime(2026, 5, 5, 9, 0, 0)
    logs: list[tuple[Any, ...]] = [
        (1, base + timedelta(days=0, hours=2), "planejamento", "Kickoff e escopo do portal.", 120),
        (1, base + timedelta(days=0, hours=5), "reuniao", "Alinhamento com stakeholders.", 90),
        (1, base + timedelta(days=1, hours=1), "desenvolvimento", "Revisão de PRs e backlog.", 45),
        (2, base + timedelta(days=1, hours=4), "suporte", "Esclarecimento de regra de negócio.", 30),
        (2, base + timedelta(days=2, hours=0), "documentacao", "Atualização do RFC da integração.", 180),
        (3, base + timedelta(days=2, hours=4), "reuniao", "Demo interna do MVP.", 60),
        (3, base + timedelta(days=3, hours=2), "desenvolvimento", "Testes E2E e ajustes finais.", 240),
        (1, base + timedelta(days=3, hours=8), "outro", "Retrospectiva rápida.", 15),
        (2, base + timedelta(days=4, hours=1), "planejamento", "Planejamento da próxima sprint.", 75),
    ]

    cursor.executemany(
        """
        INSERT INTO logs_diarios (projeto_id, data_hora, categoria, descricao, duracao_minutos)
        VALUES (%s, %s, %s, %s, %s)
        """,
        logs,
    )

    agenda_rows: list[tuple[Any, ...]] = [
        (
            1,
            "Review com cliente",
            "Validar wireframes da home.",
            base + timedelta(days=5, hours=14),
            base + timedelta(days=5, hours=13, minutes=30),
            "pendente",
        ),
        (
            2,
            "Go-live ERP",
            "Checklist de deploy.",
            base + timedelta(days=7, hours=10),
            None,
            "pendente",
        ),
        (
            3,
            "Publicação beta",
            "Release para grupo piloto.",
            base + timedelta(days=6, hours=16),
            base + timedelta(days=6, hours=15),
            "adiado",
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO agenda (projeto_id, titulo, descricao, data_hora_agendada, notificar_em, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        agenda_rows,
    )


def main() -> int:
    conn = None
    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        try:
            criar_esquema(cursor)
            popular_dados_teste(cursor)
            conn.commit()
        except Error:
            conn.rollback()
            raise
        finally:
            cursor.close()

        print(f"Banco `{DB_NAME}` criado/atualizado com sucesso.")
        print("Dados de teste inseridos (se o banco estava vazio).")
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
