"""
API Flask para o Diário de Bordo de P.O.: projetos, logs, relatório diário,
dashboard agregado e agenda. Serve arquivos estáticos a partir de frontend/.

Rodar pelo IDE neste arquivo ou com `python backend/app.py` exige colocar a raiz
do repositório em sys.path (feito abaixo). Preferível na raiz: `python run.py`.
"""

from __future__ import annotations

import calendar
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FRONTEND_DIR = PROJECT_ROOT / "frontend"
ICONS_DIR = FRONTEND_DIR / "icons"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
IMAGENS_DIR = PROJECT_ROOT / "imagens"

try:
    import mysql.connector
    from flask import Flask, jsonify, redirect, request, Response, send_from_directory, session
    from flask_cors import CORS
    from mysql.connector import Error
except ModuleNotFoundError:
    print(
        "Dependências ausentes (Flask, flask-cors e/ou mysql-connector-python).\n"
        "Na raiz do projeto \"PM Controller\" execute:\n"
        "  pip install -r requirements.txt\n"
        "Use o mesmo interpretador Python que está rodando este arquivo.",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

from werkzeug.security import check_password_hash, generate_password_hash

from backend.config import DB_CONFIG_BASE, DB_NAME

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pm-controller-dev-secret-altere-em-producao")
app.permanent_session_lifetime = timedelta(days=14)
CORS(app, supports_credentials=True)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.before_request
def _require_login_api() -> Any:
    path = request.path or ""
    if path.startswith("/uploads/") and not session.get("user_id"):
        return jsonify({"erro": "Não autenticado", "auth": True}), 401
    if not path.startswith("/api/"):
        return None
    if path == "/api/auth/login" and request.method == "POST":
        return None
    if not session.get("user_id"):
        return jsonify({"erro": "Não autenticado", "auth": True}), 401
    return None


@app.route("/")
def index_page():
    if not session.get("user_id"):
        return redirect("/login.html")
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/index.html")
def index_html_alias():
    if not session.get("user_id"):
        return redirect("/login.html")
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/login.html")
@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/manifest.json")
def manifest_json():
    return send_from_directory(
        FRONTEND_DIR,
        "manifest.json",
        mimetype="application/manifest+json",
    )


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(FRONTEND_DIR, "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/icons/<path:filename>")
def icons(filename: str):
    return send_from_directory(ICONS_DIR, filename, mimetype="image/png")


@app.route("/imagens/<path:filename>")
def imagens(filename: str) -> Any:
    if ".." in filename or filename.startswith(("/", "\\")):
        return jsonify({"erro": "caminho inválido"}), 400
    return send_from_directory(IMAGENS_DIR, filename)


LOG_CATEGORIAS = frozenset(
    {"reuniao", "desenvolvimento", "planejamento", "suporte", "documentacao", "outro"}
)
AGENDA_STATUS = frozenset({"pendente", "concluido", "cancelado", "adiado"})
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def connect_db() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**DB_CONFIG_BASE, database=DB_NAME)


def parse_mes_ano(args: dict[str, str]) -> tuple[int, int]:
    today = date.today()
    mes_raw = args.get("mes")
    ano_raw = args.get("ano")
    mes = int(mes_raw) if mes_raw not in (None, "") else today.month
    ano = int(ano_raw) if ano_raw not in (None, "") else today.year
    if not (1 <= mes <= 12):
        raise ValueError("mes deve estar entre 1 e 12")
    if ano < 1970 or ano > 2100:
        raise ValueError("ano inválido")
    return mes, ano


def evolution_date_range(mes: int | None, ano: int | None) -> tuple[date, date]:
    """Últimos 7 dias: janela fixa até hoje; com mes/ano, últimos 7 dias dentro desse mês."""
    today = date.today()
    if mes is None or ano is None:
        end = today
        start = end - timedelta(days=6)
        return start, end

    first = date(ano, mes, 1)
    last_day_n = calendar.monthrange(ano, mes)[1]
    last = date(ano, mes, last_day_n)
    if ano == today.year and mes == today.month:
        end = min(last, today)
    else:
        end = last
    start = end - timedelta(days=6)
    if start < first:
        start = first
    return start, end


def minutes_to_hours(minutes: int | float) -> float:
    return round(float(minutes) / 60.0, 2)


def fmt_minutes_label(total_minutes: int) -> str:
    h, m = divmod(int(total_minutes), 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}min")
    return "".join(parts) if parts else "0min"


def categoria_label(categoria: str) -> str:
    labels = {
        "reuniao": "Reunião",
        "desenvolvimento": "Desenvolvimento",
        "planejamento": "Planejamento",
        "suporte": "Suporte",
        "documentacao": "Documentação",
        "outro": "Outro",
    }
    return labels.get(categoria, categoria)


def parse_datetime_log(value: Any) -> datetime:
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    s = str(value).strip().removesuffix("Z").replace("T", " ", 1)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:16] if fmt == "%Y-%m-%d %H:%M" else s[:19], fmt)
        except ValueError:
            continue
    try:
        d_only = date.fromisoformat(s[:10])
        return datetime(d_only.year, d_only.month, d_only.day, 9, 0, 0)
    except ValueError as e:
        raise ValueError("data_hora inválida; use ISO ou YYYY-MM-DD HH:MM:SS") from e


def parse_datetime_optional(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    return parse_datetime_log(value)


def _as_datetime(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val
    return parse_datetime_log(val)


def log_interval_end(start: datetime, fim_raw: Any, duracao_minutos: int) -> datetime:
    if fim_raw is not None:
        return _as_datetime(fim_raw)
    return start + timedelta(minutes=int(duracao_minutos))


def intervals_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Sobreposição se intervalos se cruzam (contíguos 12:00–13:00 e 13:00–14:00 não sobrepõem)."""
    return start_a < end_b and start_b < end_a


def resolve_log_interval_from_payload(
    payload: dict[str, Any],
) -> tuple[datetime, datetime, int]:
    """
    Retorna (início, fim, duração em minutos).
    Aceita data_hora + data_hora_fim (preferencial) ou data_hora + duracao_minutos (legado).
    """
    try:
        start = parse_datetime_log(payload.get("data_hora"))
    except ValueError as e:
        raise ValueError(str(e)) from e

    fim_raw = payload.get("data_hora_fim")
    dur_raw = payload.get("duracao_minutos")

    if fim_raw not in (None, ""):
        end = parse_datetime_log(fim_raw)
        if end <= start:
            raise ValueError("data_hora_fim deve ser posterior ao início")
        if start.date() != end.date():
            raise ValueError("início e fim devem ser no mesmo dia")
        delta_min = int((end - start).total_seconds() // 60)
        if delta_min < 1:
            raise ValueError("intervalo deve ter pelo menos 1 minuto")
        return start, end, delta_min

    if dur_raw is None:
        raise ValueError("informe data_hora_fim (término) ou duracao_minutos")
    try:
        duracao_minutos = int(dur_raw)
    except (TypeError, ValueError) as e:
        raise ValueError("duracao_minutos deve ser inteiro") from e
    if duracao_minutos < 1:
        raise ValueError("duração deve ser de pelo menos 1 minuto")
    end = start + timedelta(minutes=duracao_minutos)
    return start, end, duracao_minutos


def log_overlaps_existing(
    cur: Any,
    day_str: str,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> bool:
    cur.execute(
        """
        SELECT id, data_hora, data_hora_fim, duracao_minutos
        FROM logs_diarios
        WHERE DATE(data_hora) = %s
        """,
        (day_str,),
    )
    for r in cur.fetchall():
        rid = int(r["id"])
        if exclude_id is not None and rid == exclude_id:
            continue
        s = r["data_hora"]
        if not isinstance(s, datetime):
            s = parse_datetime_log(str(s))
        e = r["data_hora_fim"]
        if e is not None and not isinstance(e, datetime):
            e = parse_datetime_log(str(e))
        e_dt = log_interval_end(s, e, int(r["duracao_minutos"]))
        if intervals_overlap(start, end, s, e_dt):
            return True
    return False


def last_end_same_projeto_same_day(
    cur: Any, projeto_id: int, day_str: str, exclude_id: int | None
) -> datetime | None:
    """Maior data_hora_fim (fim do intervalo) entre logs do mesmo projeto no mesmo dia."""
    cur.execute(
        """
        SELECT id, data_hora, data_hora_fim, duracao_minutos
        FROM logs_diarios
        WHERE projeto_id = %s AND DATE(data_hora) = %s
        """,
        (projeto_id, day_str),
    )
    best: datetime | None = None
    for r in cur.fetchall():
        rid = int(r["id"])
        if exclude_id is not None and rid == exclude_id:
            continue
        s = r["data_hora"]
        if not isinstance(s, datetime):
            s = parse_datetime_log(str(s))
        e_raw = r.get("data_hora_fim")
        e_dt = log_interval_end(s, e_raw, int(r["duracao_minutos"]))
        if best is None or e_dt > best:
            best = e_dt
    return best


@app.route("/api/clientes", methods=["GET", "POST"])
def api_clientes() -> Any:
    if request.method == "GET":
        conn = connect_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, nome FROM clientes ORDER BY nome")
            return jsonify({"clientes": cur.fetchall()})
        except Error as e:
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400
    nome = str(payload.get("nome", "")).strip()
    if not nome:
        return jsonify({"erro": "nome é obrigatório"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("INSERT INTO clientes (nome) VALUES (%s)", (nome,))
        conn.commit()
        novo_id = cur.lastrowid
        return jsonify({"id": novo_id, "nome": nome}), 201
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/projetos", methods=["GET", "POST"])
def api_projetos() -> Any:
    if request.method == "GET":
        conn = connect_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    p.id,
                    p.cliente_id,
                    p.nome AS projeto_nome,
                    p.ativo,
                    c.nome AS cliente_nome
                FROM projetos p
                INNER JOIN clientes c ON c.id = p.cliente_id
                ORDER BY c.nome, p.nome
                """
            )
            rows = cur.fetchall()
            for r in rows:
                if "ativo" in r and r["ativo"] is not None:
                    r["ativo"] = bool(r["ativo"])
            return jsonify({"projetos": rows})
        except Error as e:
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400
    cliente_raw = payload.get("cliente_id")
    nome_raw = payload.get("nome")
    if cliente_raw is None or nome_raw is None:
        return jsonify({"erro": "cliente_id e nome são obrigatórios"}), 400
    try:
        cliente_id = int(cliente_raw)
    except (TypeError, ValueError):
        return jsonify({"erro": "cliente_id deve ser inteiro"}), 400
    nome = str(nome_raw).strip()
    if not nome:
        return jsonify({"erro": "nome não pode ser vazio"}), 400
    ativo = payload.get("ativo", True)
    if isinstance(ativo, str):
        ativo = ativo.lower() in ("1", "true", "yes", "sim")
    ativo = bool(ativo)

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM clientes WHERE id = %s", (cliente_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "cliente_id não encontrado"}), 404
        cur.execute(
            """
            INSERT INTO projetos (cliente_id, nome, ativo)
            VALUES (%s, %s, %s)
            """,
            (cliente_id, nome, ativo),
        )
        conn.commit()
        novo_id = cur.lastrowid
        cur.execute(
            """
            SELECT
                p.id,
                p.cliente_id,
                p.nome AS projeto_nome,
                p.ativo,
                c.nome AS cliente_nome
            FROM projetos p
            INNER JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
            """,
            (novo_id,),
        )
        row = cur.fetchone()
        if row and row.get("ativo") is not None:
            row["ativo"] = bool(row["ativo"])
        return jsonify(row), 201
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/projetos/<int:projeto_id>", methods=["GET", "PUT", "DELETE"])
def api_projeto_item(projeto_id: int) -> Any:
    if request.method == "GET":
        conn = connect_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    p.id,
                    p.cliente_id,
                    p.nome AS projeto_nome,
                    p.ativo,
                    c.nome AS cliente_nome,
                    (
                        SELECT COUNT(*) FROM logs_diarios l WHERE l.projeto_id = p.id
                    ) AS total_atividades,
                    (
                        SELECT COALESCE(SUM(l.duracao_minutos), 0)
                        FROM logs_diarios l WHERE l.projeto_id = p.id
                    ) AS total_minutos
                FROM projetos p
                INNER JOIN clientes c ON c.id = p.cliente_id
                WHERE p.id = %s
                """,
                (projeto_id,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"erro": "projeto não encontrado"}), 404
            if row.get("ativo") is not None:
                row["ativo"] = bool(row["ativo"])
            return jsonify({"projeto": row})
        except Error as e:
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    if request.method == "DELETE":
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM projetos WHERE id = %s", (projeto_id,))
            if cur.rowcount == 0:
                conn.rollback()
                return jsonify({"erro": "projeto não encontrado"}), 404
            conn.commit()
            return jsonify({"ok": True, "id": projeto_id})
        except Error as e:
            conn.rollback()
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400
    cliente_raw = payload.get("cliente_id")
    nome_raw = payload.get("nome")
    if cliente_raw is None or nome_raw is None:
        return jsonify({"erro": "cliente_id e nome são obrigatórios"}), 400
    try:
        cliente_id = int(cliente_raw)
    except (TypeError, ValueError):
        return jsonify({"erro": "cliente_id deve ser inteiro"}), 400
    nome = str(nome_raw).strip()
    if not nome:
        return jsonify({"erro": "nome não pode ser vazio"}), 400
    ativo = payload.get("ativo", True)
    if isinstance(ativo, str):
        ativo = ativo.lower() in ("1", "true", "yes", "sim")
    ativo = bool(ativo)

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto não encontrado"}), 404
        cur.execute("SELECT id FROM clientes WHERE id = %s", (cliente_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "cliente_id não encontrado"}), 404
        cur.execute(
            """
            UPDATE projetos SET cliente_id = %s, nome = %s, ativo = %s WHERE id = %s
            """,
            (cliente_id, nome, ativo, projeto_id),
        )
        conn.commit()
        cur.execute(
            """
            SELECT
                p.id,
                p.cliente_id,
                p.nome AS projeto_nome,
                p.ativo,
                c.nome AS cliente_nome
            FROM projetos p
            INNER JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
            """,
            (projeto_id,),
        )
        row = cur.fetchone()
        if row and row.get("ativo") is not None:
            row["ativo"] = bool(row["ativo"])
        return jsonify(row)
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/projetos/<int:projeto_id>/atividades", methods=["GET"])
def api_projeto_atividades(projeto_id: int) -> Any:
    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto não encontrado"}), 404
        cur.execute(
            """
            SELECT
                l.id,
                l.projeto_id,
                l.data_hora,
                l.data_hora_fim,
                l.categoria,
                l.descricao,
                l.duracao_minutos,
                p.nome AS projeto_nome,
                c.nome AS cliente_nome
            FROM logs_diarios l
            INNER JOIN projetos p ON p.id = l.projeto_id
            INNER JOIN clientes c ON c.id = p.cliente_id
            WHERE l.projeto_id = %s
            ORDER BY l.data_hora ASC, l.id ASC
            """,
            (projeto_id,),
        )
        rows = cur.fetchall()
        return jsonify({"atividades": rows})
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/projetos/<int:projeto_id>/anexos", methods=["GET", "POST"])
def api_projeto_anexos(projeto_id: int) -> Any:
    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto não encontrado"}), 404

        if request.method == "GET":
            cur.execute(
                """
                SELECT id, nome_original, nome_armazenado, mime_type, tamanho_bytes, criado_em
                FROM projeto_anexos
                WHERE projeto_id = %s
                ORDER BY criado_em DESC, id DESC
                """,
                (projeto_id,),
            )
            rows = cur.fetchall()
            base = request.host_url.rstrip("/") if request.host_url else ""
            for r in rows:
                r["url"] = f"{base}/uploads/projetos/{projeto_id}/{r['nome_armazenado']}"
            return jsonify({"anexos": rows})

        if "arquivo" not in request.files:
            return jsonify({"erro": "campo de arquivo 'arquivo' é obrigatório"}), 400
        up = request.files["arquivo"]
        if up.filename is None or str(up.filename).strip() == "":
            return jsonify({"erro": "selecione um arquivo"}), 400
        orig = secure_filename(up.filename) or "arquivo"
        suffix = Path(orig).suffix[:48]
        stored = f"{uuid.uuid4().hex}{suffix}"
        dest_dir = UPLOADS_DIR / str(projeto_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / stored
        up.save(str(dest_path))
        try:
            size = int(dest_path.stat().st_size)
        except OSError:
            size = 0
        mime = up.mimetype or "application/octet-stream"

        cur.execute(
            """
            INSERT INTO projeto_anexos (projeto_id, nome_original, nome_armazenado, mime_type, tamanho_bytes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (projeto_id, orig[:255], stored[:255], mime[:127] if mime else None, size),
        )
        conn.commit()
        novo_id = cur.lastrowid
        base = request.host_url.rstrip("/") if request.host_url else ""
        return (
            jsonify(
                {
                    "id": novo_id,
                    "nome_original": orig[:255],
                    "nome_armazenado": stored,
                    "mime_type": mime,
                    "tamanho_bytes": size,
                    "url": f"{base}/uploads/projetos/{projeto_id}/{stored}",
                }
            ),
            201,
        )
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/uploads/projetos/<int:projeto_id>/<path:stored_name>")
def serve_projeto_upload(projeto_id: int, stored_name: str) -> Any:
    if ".." in stored_name or "/" in stored_name or "\\" in stored_name:
        return jsonify({"erro": "caminho inválido"}), 400
    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT nome_armazenado, mime_type, nome_original
            FROM projeto_anexos
            WHERE projeto_id = %s AND nome_armazenado = %s
            LIMIT 1
            """,
            (projeto_id, stored_name),
        )
        row = cur.fetchone()
        if row is None:
            return jsonify({"erro": "anexo não encontrado"}), 404
        folder = UPLOADS_DIR / str(projeto_id)
        resp = send_from_directory(folder, stored_name, as_attachment=False)
        if row.get("mime_type"):
            resp.headers["Content-Type"] = str(row["mime_type"])
        return resp
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/logs", methods=["POST"])
def api_logs_post() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400

    projeto_id = payload.get("projeto_id")
    categoria = payload.get("categoria", "outro")
    descricao = payload.get("descricao")

    if projeto_id is None or descricao is None:
        return jsonify({"erro": "projeto_id e descricao são obrigatórios"}), 400
    try:
        projeto_id = int(projeto_id)
    except (TypeError, ValueError):
        return jsonify({"erro": "projeto_id deve ser inteiro"}), 400

    categoria = str(categoria).lower().strip()
    if categoria not in LOG_CATEGORIAS:
        return jsonify({"erro": f"categoria deve ser uma de: {sorted(LOG_CATEGORIAS)}"}), 400

    try:
        data_hora, data_hora_fim, duracao_minutos = resolve_log_interval_from_payload(payload)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    day_str = data_hora.date().isoformat()

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto_id não encontrado"}), 404

        if log_overlaps_existing(cur, day_str, data_hora, data_hora_fim, None):
            return jsonify(
                {"erro": "Este horário se sobrepõe a outra ocorrência do dia. Ajuste início ou fim."}
            ), 409

        last_same = last_end_same_projeto_same_day(cur, projeto_id, day_str, None)
        if last_same is not None and data_hora < last_same:
            return jsonify(
                {
                    "erro": "O início deve ser no ou após o término da última atividade deste projeto neste dia."
                }
            ), 400

        cur.execute(
            """
            INSERT INTO logs_diarios (projeto_id, data_hora, data_hora_fim, categoria, descricao, duracao_minutos)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (projeto_id, data_hora, data_hora_fim, categoria, descricao, duracao_minutos),
        )
        conn.commit()
        novo_id = cur.lastrowid
        return jsonify(
            {
                "id": novo_id,
                "projeto_id": projeto_id,
                "data_hora": data_hora.isoformat(sep=" "),
                "data_hora_fim": data_hora_fim.isoformat(sep=" "),
                "categoria": categoria,
                "descricao": descricao,
                "duracao_minutos": duracao_minutos,
            }
        ), 201
    except Error as e:
        conn.rollback()
        err = str(e)
        if "Unknown column" in err and "data_hora_fim" in err:
            return jsonify(
                {
                    "erro": "Coluna data_hora_fim ausente no banco. Execute: python -m backend.criar_banco",
                }
            ),
            500
        return jsonify({"erro": err}), 500
    finally:
        conn.close()


@app.route("/api/logs/dia/<data>", methods=["GET"])
def api_logs_dia(data: str) -> Any:
    """Lista logs do dia (ordenados por horário) para o módulo Diário."""
    if not DATE_RE.match(data):
        return jsonify({"erro": "data deve ser YYYY-MM-DD"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                l.id,
                l.projeto_id,
                l.data_hora,
                l.data_hora_fim,
                l.categoria,
                l.descricao,
                l.duracao_minutos,
                p.nome AS projeto_nome,
                c.nome AS cliente_nome
            FROM logs_diarios l
            INNER JOIN projetos p ON p.id = l.projeto_id
            INNER JOIN clientes c ON c.id = p.cliente_id
            WHERE DATE(l.data_hora) = %s
            ORDER BY l.data_hora ASC, l.id ASC
            """,
            (data,),
        )
        rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            dh = r["data_hora"]
            dh_f = r.get("data_hora_fim")
            out.append(
                {
                    "id": r["id"],
                    "projeto_id": r["projeto_id"],
                    "projeto_nome": r["projeto_nome"],
                    "cliente_nome": r["cliente_nome"],
                    "data_hora": dh.isoformat(sep=" ") if isinstance(dh, datetime) else str(dh),
                    "data_hora_fim": dh_f.isoformat(sep=" ")
                    if dh_f is not None and isinstance(dh_f, datetime)
                    else (str(dh_f) if dh_f is not None else None),
                    "categoria": str(r["categoria"]),
                    "descricao": r["descricao"],
                    "duracao_minutos": int(r["duracao_minutos"]),
                }
            )
        return jsonify({"data": data, "logs": out})
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/logs/<int:log_id>", methods=["GET", "PUT", "DELETE"])
def api_log_item(log_id: int) -> Any:
    if request.method == "GET":
        conn = connect_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    l.id,
                    l.projeto_id,
                    l.data_hora,
                    l.data_hora_fim,
                    l.categoria,
                    l.descricao,
                    l.duracao_minutos,
                    p.nome AS projeto_nome,
                    c.nome AS cliente_nome
                FROM logs_diarios l
                INNER JOIN projetos p ON p.id = l.projeto_id
                INNER JOIN clientes c ON c.id = p.cliente_id
                WHERE l.id = %s
                """,
                (log_id,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"erro": "registro não encontrado"}), 404
            dh = row["data_hora"]
            dh_f = row.get("data_hora_fim")
            return jsonify(
                {
                    "id": row["id"],
                    "projeto_id": row["projeto_id"],
                    "projeto_nome": row["projeto_nome"],
                    "cliente_nome": row["cliente_nome"],
                    "data_hora": dh.isoformat(sep=" ") if isinstance(dh, datetime) else str(dh),
                    "data_hora_fim": dh_f.isoformat(sep=" ")
                    if dh_f is not None and isinstance(dh_f, datetime)
                    else (str(dh_f) if dh_f is not None else None),
                    "categoria": str(row["categoria"]),
                    "descricao": row["descricao"],
                    "duracao_minutos": int(row["duracao_minutos"]),
                }
            )
        except Error as e:
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    if request.method == "DELETE":
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM logs_diarios WHERE id = %s", (log_id,))
            if cur.rowcount == 0:
                conn.rollback()
                return jsonify({"erro": "registro não encontrado"}), 404
            conn.commit()
            return jsonify({"ok": True, "id": log_id})
        except Error as e:
            conn.rollback()
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400

    projeto_id = payload.get("projeto_id")
    categoria = payload.get("categoria", "outro")
    descricao = payload.get("descricao")

    if projeto_id is None or descricao is None:
        return jsonify({"erro": "projeto_id e descricao são obrigatórios"}), 400
    try:
        projeto_id = int(projeto_id)
    except (TypeError, ValueError):
        return jsonify({"erro": "projeto_id deve ser inteiro"}), 400

    categoria = str(categoria).lower().strip()
    if categoria not in LOG_CATEGORIAS:
        return jsonify({"erro": f"categoria deve ser uma de: {sorted(LOG_CATEGORIAS)}"}), 400

    try:
        data_hora, data_hora_fim, duracao_minutos = resolve_log_interval_from_payload(payload)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    day_str = data_hora.date().isoformat()

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM logs_diarios WHERE id = %s", (log_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "registro não encontrado"}), 404
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto_id não encontrado"}), 404

        if log_overlaps_existing(cur, day_str, data_hora, data_hora_fim, log_id):
            return jsonify(
                {"erro": "Este horário se sobrepõe a outra ocorrência do dia. Ajuste início ou fim."}
            ), 409

        last_same = last_end_same_projeto_same_day(cur, projeto_id, day_str, log_id)
        if last_same is not None and data_hora < last_same:
            return jsonify(
                {
                    "erro": "O início deve ser no ou após o término da última atividade deste projeto neste dia."
                }
            ), 400

        cur.execute(
            """
            UPDATE logs_diarios
            SET projeto_id = %s, data_hora = %s, data_hora_fim = %s, categoria = %s, descricao = %s, duracao_minutos = %s
            WHERE id = %s
            """,
            (projeto_id, data_hora, data_hora_fim, categoria, descricao, duracao_minutos, log_id),
        )
        conn.commit()
        return jsonify(
            {
                "id": log_id,
                "projeto_id": projeto_id,
                "data_hora": data_hora.isoformat(sep=" "),
                "data_hora_fim": data_hora_fim.isoformat(sep=" "),
                "categoria": categoria,
                "descricao": descricao,
                "duracao_minutos": duracao_minutos,
            }
        )
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/relatorio_diario/<data>", methods=["GET"])
def api_relatorio_diario(data: str) -> Any:
    if not DATE_RE.match(data):
        return jsonify({"erro": "data deve ser YYYY-MM-DD"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                l.data_hora,
                l.categoria,
                l.descricao,
                l.duracao_minutos,
                p.nome AS projeto_nome
            FROM logs_diarios l
            INNER JOIN projetos p ON p.id = l.projeto_id
            WHERE DATE(l.data_hora) = %s
            ORDER BY l.data_hora
            """,
            (data,),
        )
        rows = cur.fetchall()

        bullets: list[str] = []
        for r in rows:
            dh = r["data_hora"]
            if isinstance(dh, datetime):
                hora = dh.strftime("%H:%M")
            else:
                hora = str(dh)[:5]
            cat = categoria_label(str(r["categoria"]))
            tempo = fmt_minutes_label(int(r["duracao_minutos"]))
            projeto = r["projeto_nome"]
            desc = (r["descricao"] or "").strip().replace("\n", " ")
            bullets.append(f"• [{hora}] {projeto} — {cat} — {tempo} — {desc}")

        return jsonify({"data": data, "bullets": bullets, "total_registros": len(bullets)})
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/dashboard/stats", methods=["GET"])
def api_dashboard_stats() -> Any:
    try:
        mes, ano = parse_mes_ano(request.args)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    mes_q = request.args.get("mes")
    ano_q = request.args.get("ano")
    ev_mes = int(mes_q) if mes_q not in (None, "") else None
    ev_ano = int(ano_q) if ano_q not in (None, "") else None
    try:
        ev_start, ev_end = evolution_date_range(ev_mes, ev_ano)
    except ValueError:
        return jsonify({"erro": "mes/ano inválidos para evolução"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT
                p.id AS projeto_id,
                p.nome AS projeto_nome,
                c.nome AS cliente_nome,
                COALESCE(SUM(l.duracao_minutos), 0) AS minutos_total
            FROM projetos p
            INNER JOIN clientes c ON c.id = p.cliente_id
            LEFT JOIN logs_diarios l
                ON l.projeto_id = p.id
                AND YEAR(l.data_hora) = %s
                AND MONTH(l.data_hora) = %s
            GROUP BY p.id, p.nome, c.nome
            ORDER BY minutos_total DESC, p.nome
            """,
            (ano, mes),
        )
        por_projeto_raw = cur.fetchall()
        horas_por_projeto = [
            {
                "projeto_id": r["projeto_id"],
                "projeto_nome": r["projeto_nome"],
                "cliente_nome": r["cliente_nome"],
                "minutos_total": int(r["minutos_total"]),
                "horas": minutes_to_hours(r["minutos_total"]),
            }
            for r in por_projeto_raw
        ]

        cur.execute(
            """
            SELECT categoria, COALESCE(SUM(duracao_minutos), 0) AS minutos
            FROM logs_diarios
            WHERE YEAR(data_hora) = %s AND MONTH(data_hora) = %s
            GROUP BY categoria
            """,
            (ano, mes),
        )
        cat_rows = cur.fetchall()
        por_categoria_min: dict[str, int] = {str(r["categoria"]): int(r["minutos"]) for r in cat_rows}

        reuniao_m = por_categoria_min.get("reuniao", 0)
        dev_m = por_categoria_min.get("desenvolvimento", 0)
        outros_m = sum(m for k, m in por_categoria_min.items() if k not in ("reuniao", "desenvolvimento"))

        distribuicao = {
            "reuniao_vs_desenvolvimento": {
                "reuniao_horas": minutes_to_hours(reuniao_m),
                "desenvolvimento_horas": minutes_to_hours(dev_m),
                "reuniao_minutos": reuniao_m,
                "desenvolvimento_minutos": dev_m,
            },
            "outros_horas": minutes_to_hours(outros_m),
            "outros_minutos": outros_m,
            "detalhe_por_categoria": {
                k: {"minutos": v, "horas": minutes_to_hours(v)} for k, v in sorted(por_categoria_min.items())
            },
        }

        cur.execute(
            """
            SELECT DATE(data_hora) AS dia, COALESCE(SUM(duracao_minutos), 0) AS minutos
            FROM logs_diarios
            WHERE DATE(data_hora) BETWEEN %s AND %s
            GROUP BY DATE(data_hora)
            ORDER BY dia
            """,
            (ev_start, ev_end),
        )
        ev_rows = cur.fetchall()
        by_day: dict[date, int] = {}
        for r in ev_rows:
            d = r["dia"]
            if isinstance(d, datetime):
                d = d.date()
            by_day[d] = int(r["minutos"])

        evolucao: list[dict[str, Any]] = []
        d = ev_start
        while d <= ev_end:
            m = by_day.get(d, 0)
            evolucao.append({"data": d.isoformat(), "minutos": m, "horas": minutes_to_hours(m)})
            d += timedelta(days=1)

        return jsonify(
            {
                "filtro": {"mes": mes, "ano": ano},
                "horas_por_projeto": horas_por_projeto,
                "distribuicao_tempo": distribuicao,
                "evolucao_ultimos_7_dias": {
                    "inicio": ev_start.isoformat(),
                    "fim": ev_end.isoformat(),
                    "serie_diaria": evolucao,
                },
            }
        )
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/agenda", methods=["GET", "POST"])
def api_agenda() -> Any:
    if request.method == "GET":
        try:
            mes, ano = parse_mes_ano(request.args)
        except ValueError as e:
            return jsonify({"erro": str(e)}), 400

        conn = connect_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    a.id,
                    a.projeto_id,
                    a.titulo,
                    a.descricao,
                    a.data_hora_agendada,
                    a.notificar_em,
                    a.status,
                    p.nome AS projeto_nome,
                    c.nome AS cliente_nome
                FROM agenda a
                INNER JOIN projetos p ON p.id = a.projeto_id
                INNER JOIN clientes c ON c.id = p.cliente_id
                WHERE YEAR(a.data_hora_agendada) = %s AND MONTH(a.data_hora_agendada) = %s
                ORDER BY a.data_hora_agendada
                """,
                (ano, mes),
            )
            rows = cur.fetchall()
            for r in rows:
                for key in ("data_hora_agendada", "notificar_em"):
                    if isinstance(r.get(key), datetime):
                        r[key] = r[key].isoformat(sep=" ")
            return jsonify({"filtro": {"mes": mes, "ano": ano}, "agenda": rows})
        except Error as e:
            return jsonify({"erro": str(e)}), 500
        finally:
            conn.close()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400

    projeto_id = payload.get("projeto_id")
    titulo = payload.get("titulo")
    data_hora_agendada = payload.get("data_hora_agendada")
    if projeto_id is None or titulo is None or data_hora_agendada is None:
        return jsonify({"erro": "projeto_id, titulo e data_hora_agendada são obrigatórios"}), 400
    try:
        projeto_id = int(projeto_id)
        dh_ag = parse_datetime_log(data_hora_agendada)
    except (TypeError, ValueError) as e:
        return jsonify({"erro": str(e)}), 400

    descricao = payload.get("descricao")
    notificar_em = parse_datetime_optional(payload.get("notificar_em"))
    status = str(payload.get("status", "pendente")).lower().strip()
    if status not in AGENDA_STATUS:
        return jsonify({"erro": f"status deve ser um de: {sorted(AGENDA_STATUS)}"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM projetos WHERE id = %s", (projeto_id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "projeto_id não encontrado"}), 404

        cur.execute(
            """
            INSERT INTO agenda (projeto_id, titulo, descricao, data_hora_agendada, notificar_em, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (projeto_id, titulo, descricao, dh_ag, notificar_em, status),
        )
        conn.commit()
        novo_id = cur.lastrowid
        return jsonify(
            {
                "id": novo_id,
                "projeto_id": projeto_id,
                "titulo": titulo,
                "descricao": descricao,
                "data_hora_agendada": dh_ag.isoformat(sep=" "),
                "notificar_em": notificar_em.isoformat(sep=" ") if notificar_em else None,
                "status": status,
            }
        ), 201
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


def _user_public_dict(row: dict[str, Any]) -> dict[str, Any]:
    raw_tem = row.get("tem_avatar")
    if raw_tem is None:
        ab = row.get("avatar_blob")
        if isinstance(ab, (bytes, bytearray, memoryview)):
            tem = len(bytes(ab)) > 0
        else:
            tem = False
    elif isinstance(raw_tem, bool):
        tem = raw_tem
    elif isinstance(raw_tem, (bytes, bytearray, memoryview)):
        tem = len(bytes(raw_tem)) > 0
    else:
        try:
            tem = int(raw_tem) != 0
        except (TypeError, ValueError):
            s = str(raw_tem).strip().lower()
            tem = s in ("1", "true", "yes")
    return {
        "id": int(row["id"]),
        "username": row.get("username") or "",
        "nome_exibicao": row.get("nome_exibicao") or "",
        "email": row.get("email") or "",
        "telefone": row.get("telefone") or "",
        "cargo": row.get("cargo") or "",
        "bio": row.get("bio") or "",
        "tem_avatar": bool(tem),
    }


_USER_ROW_SELECT = """
    SELECT id, username, nome_exibicao, email, telefone, cargo, bio,
           (IFNULL(LENGTH(avatar_blob), 0) > 0) AS tem_avatar
    FROM usuarios WHERE id = %s
"""

_USER_LOGIN_SELECT = """
    SELECT id, username, senha_hash, nome_exibicao, email, telefone, cargo, bio,
           (IFNULL(LENGTH(avatar_blob), 0) > 0) AS tem_avatar
    FROM usuarios WHERE username = %s
"""


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not username or not password:
        return jsonify({"erro": "Informe usuário e senha."}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_USER_LOGIN_SELECT, (username,))
        row = cur.fetchone()
        if row is None or not check_password_hash(str(row["senha_hash"]), password):
            return jsonify({"erro": "Usuário ou senha incorretos."}), 401
        session.clear()
        session["user_id"] = int(row["id"])
        session.permanent = True
        return jsonify({"ok": True, "user": _user_public_dict(row)})
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout() -> Any:
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def api_auth_me() -> Any:
    uid = session.get("user_id")
    if not uid:
        return jsonify({"erro": "Não autenticado"}), 401
    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_USER_ROW_SELECT, (int(uid),))
        row = cur.fetchone()
        if row is None:
            session.clear()
            return jsonify({"erro": "Usuário não encontrado"}), 401
        return jsonify({"user": _user_public_dict(row)})
    except Error as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/auth/profile", methods=["PUT"])
def api_auth_profile() -> Any:
    uid = session.get("user_id")
    if not uid:
        return jsonify({"erro": "Não autenticado"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400

    nome_exibicao = str(payload.get("nome_exibicao", "")).strip()
    email = str(payload.get("email", "")).strip()
    telefone = str(payload.get("telefone", "")).strip()
    cargo = str(payload.get("cargo", "")).strip()
    bio = str(payload.get("bio", "")).strip()
    if not nome_exibicao:
        return jsonify({"erro": "nome_exibicao é obrigatório"}), 400
    if email and "@" not in email:
        return jsonify({"erro": "E-mail inválido"}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE usuarios
            SET nome_exibicao = %s, email = NULLIF(%s,''), telefone = NULLIF(%s,''),
                cargo = NULLIF(%s,''), bio = NULLIF(%s,'')
            WHERE id = %s
            """,
            (nome_exibicao, email, telefone, cargo, bio, int(uid)),
        )
        conn.commit()
        cur.execute(_USER_ROW_SELECT, (int(uid),))
        row = cur.fetchone()
        return jsonify({"ok": True, "user": _user_public_dict(row or {})})
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/auth/avatar", methods=["GET", "POST", "DELETE"])
def api_auth_avatar() -> Any:
    uid = session.get("user_id")
    if not uid:
        return jsonify({"erro": "Não autenticado"}), 401

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        if request.method == "GET":
            cur.execute(
                "SELECT avatar_blob, avatar_mime FROM usuarios WHERE id = %s",
                (int(uid),),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"erro": "Usuário não encontrado"}), 404
            blob = row.get("avatar_blob")
            if not blob or not isinstance(blob, (bytes, bytearray)) or len(blob) == 0:
                return jsonify({"erro": "Sem foto de perfil"}), 404
            mime = str(row.get("avatar_mime") or "image/jpeg").strip() or "image/jpeg"
            resp = Response(bytes(blob), mimetype=mime)
            resp.headers["Cache-Control"] = "private, max-age=120"
            return resp

        if request.method == "DELETE":
            cur.execute(
                "UPDATE usuarios SET avatar_blob = NULL, avatar_mime = NULL WHERE id = %s",
                (int(uid),),
            )
            conn.commit()
            return jsonify({"ok": True, "tem_avatar": False})

        up = request.files.get("arquivo")
        if up is None or up.filename is None or str(up.filename).strip() == "":
            return jsonify({"erro": "Envie um arquivo no campo \"arquivo\"."}), 400
        raw = up.read()
        if len(raw) > AVATAR_MAX_BYTES:
            return jsonify({"erro": "Imagem muito grande (máximo 2 MB)."}), 400
        mime = (up.mimetype or "").strip().lower() or "application/octet-stream"
        if mime not in AVATAR_MIMES:
            return jsonify({"erro": "Use JPEG, PNG, WebP ou GIF."}), 400
        cur.execute(
            "UPDATE usuarios SET avatar_blob = %s, avatar_mime = %s WHERE id = %s",
            (raw, mime[:127], int(uid)),
        )
        conn.commit()
        return jsonify({"ok": True, "tem_avatar": True})
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/auth/password", methods=["PUT"])
def api_auth_password() -> Any:
    uid = session.get("user_id")
    if not uid:
        return jsonify({"erro": "Não autenticado"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"erro": "JSON inválido"}), 400
    atual = str(payload.get("senha_atual", ""))
    nova = str(payload.get("senha_nova", ""))
    conf = str(payload.get("senha_nova_confirma", ""))
    if len(nova) < 6:
        return jsonify({"erro": "A nova senha deve ter pelo menos 6 caracteres."}), 400
    if nova != conf:
        return jsonify({"erro": "A confirmação da nova senha não confere."}), 400

    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT senha_hash FROM usuarios WHERE id = %s", (int(uid),))
        row = cur.fetchone()
        if row is None:
            return jsonify({"erro": "Usuário não encontrado"}), 404
        if not check_password_hash(str(row["senha_hash"]), atual):
            return jsonify({"erro": "Senha atual incorreta."}), 400
        cur.execute(
            "UPDATE usuarios SET senha_hash = %s WHERE id = %s",
            (generate_password_hash(nova), int(uid)),
        )
        conn.commit()
        return jsonify({"ok": True})
    except Error as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=True,
    )
