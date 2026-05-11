"""Configuração compartilhada do MariaDB (script de schema e API)."""

from __future__ import annotations

import os
from typing import Any

import mysql.connector

DB_NAME = "po_diary_db"

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
