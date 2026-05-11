#!/usr/bin/env python3
"""
Inicia o servidor Flask. Execute na raiz do projeto:

    python run.py

Variável opcional: FLASK_PORT (padrão 5000).
"""

from __future__ import annotations

import os

from backend.app import app

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=True,
    )
