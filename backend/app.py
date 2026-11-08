"""Ship Registration Portal - Flask REST API.

Database: SQLite locally (auto-created file), PostgreSQL when DATABASE_URL is set (Render).
"""
import os
import re
import sqlite3
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)

# Allowed frontend origins, e.g. "https://my-site.netlify.app"
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": origins}})

SHIP_TYPES = ["Cargo Ship", "Passenger Ship", "Container Ship", "Tanker", "Naval Ship", "Other"]
SHIP_STATUSES = ["Ready", "In Service", "Docked", "Under Maintenance", "Inactive"]
MAINT_STATUSES = ["Scheduled", "In Progress", "Completed", "Delayed"]
ROLES = ["admin", "staff", "viewer"]  # admin: all; staff: create/edit; viewer: read-only
TOKEN_MAX_AGE = 8 * 3600  # login session length (seconds)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="shipyard-auth")

# Columns returned to the frontend (date converted to plain text)
COLUMNS = """id, ship_id, ship_name, ship_type,
             CAST(registration_date AS TEXT) AS registration_date,
             status, berth_number"""


# ---------- Database layer ----------
# DATABASE_URL set  -> PostgreSQL (production / Render)
# DATABASE_URL empty -> SQLite file (local development, no install needed)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)
SQLITE_PATH = os.environ.get(
    "SQLITE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shipyard.db")
)

if USE_POSTGRES:
    import psycopg2
    from psycopg2 import errors as pg_errors
    from psycopg2.extras import RealDictCursor

    UNIQUE_ERROR = pg_errors.UniqueViolation
    DB_ERROR = psycopg2.Error
else:
    UNIQUE_ERROR = sqlite3.IntegrityError
    DB_ERROR = sqlite3.Error


def get_connection():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(SQLITE_PATH)  # file is created automatically
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def to_sqlite_sql(sql):
    """Queries are written in PostgreSQL style; convert them for SQLite."""
    sql = re.sub(r"%\((\w+)\)s", r":\1", sql)  # %(name)s -> :name
    sql = sql.replace("%s", "?")                  # %s       -> ?
    return sql.replace("ILIKE", "LIKE")           # SQLite LIKE is case-insensitive


def run_query(sql, params=(), fetch="all"):
    """Run one SQL statement on either database. fetch: 'all', 'one' or None."""
    conn = get_connection()
    try:
        with conn:  # commits on success, rolls back on error
            if USE_POSTGRES:
                cur = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cur = conn.cursor()
                sql = to_sqlite_sql(sql)
            try:
                cur.execute(sql, params)
                if fetch == "all":
                    return [dict(r) for r in cur.fetchall()]
                if fetch == "one":
                    row = cur.fetchone()
                    return dict(row) if row else None
                return cur.rowcount
            finally:
                cur.close()
    finally:
        conn.close()


POSTGRES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS ships (
        id SERIAL PRIMARY KEY,
        ship_id VARCHAR(50) NOT NULL UNIQUE,
        ship_name VARCHAR(100) NOT NULL,
        ship_type VARCHAR(50) NOT NULL,
        registration_date DATE NOT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'Ready',
        berth_number VARCHAR(30),
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )"""

SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS ships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ship_id TEXT NOT NULL UNIQUE,
        ship_name TEXT NOT NULL,
        ship_type TEXT NOT NULL,
        registration_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Ready',
        berth_number TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""


EXTRA_SCHEMA = {
    "pg": [
        """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMP NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS maintenance (
            id SERIAL PRIMARY KEY, ship_pk INTEGER NOT NULL REFERENCES ships(id) ON DELETE CASCADE,
            description TEXT NOT NULL, start_date DATE NOT NULL, end_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'Scheduled', created_at TIMESTAMP NOT NULL DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS movements (
            id SERIAL PRIMARY KEY, ship_pk INTEGER NOT NULL REFERENCES ships(id) ON DELETE CASCADE,
            movement_type VARCHAR(20) NOT NULL, movement_date DATE NOT NULL, berth_number VARCHAR(30),
            notes TEXT, created_at TIMESTAMP NOT NULL DEFAULT NOW())""",
    ],
    "sqlite": [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ship_pk INTEGER NOT NULL REFERENCES ships(id) ON DELETE CASCADE,
            description TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT,
            status TEXT NOT NULL DEFAULT 'Scheduled', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ship_pk INTEGER NOT NULL REFERENCES ships(id) ON DELETE CASCADE,
            movement_type TEXT NOT NULL, movement_date TEXT NOT NULL, berth_number TEXT,
            notes TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    ],
}


def init_db():
    """Create tables if missing (existing tables and data are never touched)."""
    run_query(POSTGRES_SCHEMA if USE_POSTGRES else SQLITE_SCHEMA, fetch=None)
    for stmt in EXTRA_SCHEMA["pg" if USE_POSTGRES else "sqlite"]:
        run_query(stmt, fetch=None)
    ensure_admin()


def ensure_admin():
    """Create the first admin from ADMIN_USERNAME / ADMIN_PASSWORD when no users exist."""
    if run_query("SELECT COUNT(*) AS n FROM users", fetch="one")["n"]:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        password = "admin123"
        print("WARNING: ADMIN_PASSWORD not set - created default login admin / admin123. "
              "Set ADMIN_PASSWORD (and SECRET_KEY) before deploying.")
    run_query("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
              (username, generate_password_hash(password)), fetch=None)


# ---------- Authentication ----------
def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        uid = serializer.loads(auth[7:], max_age=TOKEN_MAX_AGE)["uid"]
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return None
    return run_query("SELECT id, username, role FROM users WHERE id = %s", (uid,), fetch="one")


@app.before_request
def require_login():
    """Every /api route needs a valid login except /api/auth/login; role limits writes."""
    if request.method == "OPTIONS" or not request.path.startswith("/api/") or request.path == "/api/auth/login":
        return None
    user = current_user()
    if not user:
        return error("Authentication required.", 401)
    g.user = user
    if request.method != "GET" and user["role"] == "viewer":
        return error("Your role is read-only.", 403)
    if request.method == "DELETE" and user["role"] != "admin":
        return error("Only admins can delete records.", 403)
    return None


# ---------- Validation ----------
def validate_ship(data):
    """Return (clean_data, error_message)."""
    if not isinstance(data, dict):
        return None, "Invalid request body."

    ship_id = str(data.get("ship_id", "")).strip()
    name = str(data.get("ship_name", "")).strip()
    ship_type = str(data.get("ship_type", "")).strip()
    reg_date = str(data.get("registration_date", "")).strip()
    status = str(data.get("status", "")).strip()
    berth = str(data.get("berth_number") or "").strip()

    if not ship_id or not name or not ship_type or not reg_date or not status:
        return None, "Ship ID, name, type, registration date and status are required."
    if len(ship_id) > 50 or len(name) > 100 or len(berth) > 30:
        return None, "One of the fields is too long."
    if ship_type not in SHIP_TYPES:
        return None, "Invalid ship type."
    if status not in SHIP_STATUSES:
        return None, "Invalid ship status."
    try:
        date.fromisoformat(reg_date)
    except ValueError:
        return None, "Registration date must be a valid date (YYYY-MM-DD)."

    return {
        "ship_id": ship_id, "ship_name": name, "ship_type": ship_type,
        "registration_date": reg_date, "status": status, "berth_number": berth or None,
    }, None


def parse_date(value, label, required=True):
    value = str(value or "").strip()
    if not value:
        return (None, None) if not required else (None, f"{label} is required.")
    try:
        date.fromisoformat(value)
    except ValueError:
        return None, f"{label} must be a valid date (YYYY-MM-DD)."
    return value, None


def validate_maintenance(data):
    if not isinstance(data, dict):
        return None, "Invalid request body."
    try:
        ship_pk = int(data.get("ship_pk"))
    except (TypeError, ValueError):
        return None, "Please select a vessel."
    desc = str(data.get("description", "")).strip()
    status = str(data.get("status", "Scheduled")).strip()
    if not desc:
        return None, "Description is required."
    if len(desc) > 1000:
        return None, "Description is too long (max 1000 characters)."
    if status not in MAINT_STATUSES:
        return None, "Invalid maintenance status."
    start, err = parse_date(data.get("start_date"), "Start date")
    if err:
        return None, err
    end, err = parse_date(data.get("end_date"), "End date", required=False)
    if err:
        return None, err
    if end and end < start:
        return None, "End date cannot be before the start date."
    if not run_query("SELECT id FROM ships WHERE id = %s", (ship_pk,), fetch="one"):
        return None, "Selected vessel does not exist."
    return {"ship_pk": ship_pk, "description": desc, "start_date": start, "end_date": end, "status": status}, None


def error(message, code):
    return jsonify({"error": message}), code


# ---------- Routes ----------
@app.route("/")
def health():
    return jsonify({"message": "Ship Registration Portal API is running"})


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")


@app.route("/portal/")
@app.route("/portal/<path:filename>")
def portal(filename="index.html"):
    """Serve the frontend at /portal/ so the whole app runs with one command (local convenience)."""
    if not os.path.isdir(FRONTEND_DIR):
        return error("Frontend folder not found.", 404)
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/api/ships", methods=["GET"])
def list_ships():
    search = request.args.get("search", "").strip()
    ship_type = request.args.get("type", "").strip()
    status = request.args.get("status", "").strip()

    sql = f"SELECT {COLUMNS} FROM ships WHERE 1=1"
    params = []
    if search:
        sql += " AND (ship_name ILIKE %s OR ship_id ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if ship_type:
        sql += " AND ship_type = %s"
        params.append(ship_type)
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY id"

    return jsonify(run_query(sql, params))


@app.route("/api/ships/<int:ship_pk>", methods=["GET"])
def get_ship(ship_pk):
    ship = run_query(f"SELECT {COLUMNS} FROM ships WHERE id = %s", (ship_pk,), fetch="one")
    if not ship:
        return error("Ship not found.", 404)
    return jsonify(ship)


@app.route("/api/ships", methods=["POST"])
def create_ship():
    clean, err = validate_ship(request.get_json(silent=True))
    if err:
        return error(err, 400)
    try:
        ship = run_query(
            f"""INSERT INTO ships (ship_id, ship_name, ship_type, registration_date, status, berth_number)
                VALUES (%(ship_id)s, %(ship_name)s, %(ship_type)s, %(registration_date)s, %(status)s, %(berth_number)s)
                RETURNING {COLUMNS}""",
            clean, fetch="one",
        )
    except UNIQUE_ERROR:
        return error(f"Ship ID '{clean['ship_id']}' already exists.", 409)
    return jsonify(ship), 201


@app.route("/api/ships/<int:ship_pk>", methods=["PUT"])
def update_ship(ship_pk):
    clean, err = validate_ship(request.get_json(silent=True))
    if err:
        return error(err, 400)
    clean["pk"] = ship_pk
    try:
        ship = run_query(
            f"""UPDATE ships SET ship_id=%(ship_id)s, ship_name=%(ship_name)s, ship_type=%(ship_type)s,
                registration_date=%(registration_date)s, status=%(status)s, berth_number=%(berth_number)s
                WHERE id=%(pk)s RETURNING {COLUMNS}""",
            clean, fetch="one",
        )
    except UNIQUE_ERROR:
        return error(f"Ship ID '{clean['ship_id']}' already exists.", 409)
    if not ship:
        return error("Ship not found.", 404)
    return jsonify(ship)


@app.route("/api/ships/<int:ship_pk>", methods=["DELETE"])
def delete_ship(ship_pk):
    deleted = run_query("DELETE FROM ships WHERE id = %s", (ship_pk,), fetch=None)
    if not deleted:
        return error("Ship not found.", 404)
    return jsonify({"message": "Ship deleted."})


@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    row = run_query(
        """SELECT COUNT(*) AS total,
                  COUNT(CASE WHEN status = 'Under Maintenance' THEN 1 END) AS under_maintenance,
                  COUNT(CASE WHEN status = 'Ready' THEN 1 END) AS ready,
                  COUNT(CASE WHEN status = 'In Service' THEN 1 END) AS in_service,
                  COUNT(CASE WHEN status = 'Inactive' THEN 1 END) AS inactive
           FROM ships""",
        fetch="one",
    )
    row["docked"] = run_query("SELECT COUNT(*) AS n FROM ships WHERE status = 'Docked'", fetch="one")["n"]
    row["active"] = row["in_service"]  # "Active" = vessels currently In Service
    row["recent_ships"] = run_query(
        f"SELECT {COLUMNS} FROM ships ORDER BY id DESC LIMIT 5")
    row["maintenance_by_status"] = {s_: 0 for s_ in MAINT_STATUSES}
    for r in run_query("SELECT status, COUNT(*) AS n FROM maintenance GROUP BY status"):
        row["maintenance_by_status"][r["status"]] = r["n"]
    row["recent_movements"] = run_query(MOVEMENT_SQL + " ORDER BY m.id DESC LIMIT 5")
    row["by_type"] = run_query(
        "SELECT ship_type, COUNT(*) AS count FROM ships GROUP BY ship_type ORDER BY count DESC"
    )
    return jsonify(row)


# ---------- Auth routes ----------
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = run_query("SELECT * FROM users WHERE username = %s", (username,), fetch="one")
    if not user or not check_password_hash(user["password_hash"], password):
        return error("Invalid username or password.", 401)
    token = serializer.dumps({"uid": user["id"]})
    return jsonify({"token": token, "user": {"username": user["username"], "role": user["role"]}})


@app.route("/api/auth/me", methods=["GET"])
def me():
    return jsonify({"username": g.user["username"], "role": g.user["role"]})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    # Tokens are stateless; the client discards its token. They also expire automatically.
    return jsonify({"message": "Logged out."})


# ---------- Maintenance ----------
MAINT_SQL = """SELECT mt.id, mt.ship_pk, s.ship_id, s.ship_name, mt.description,
                      CAST(mt.start_date AS TEXT) AS start_date, CAST(mt.end_date AS TEXT) AS end_date, mt.status
               FROM maintenance mt JOIN ships s ON s.id = mt.ship_pk WHERE 1=1"""


def sync_ship_status(ship_pk):
    """Keep vessel status consistent with maintenance: In Progress/Delayed -> Under Maintenance."""
    active = run_query("SELECT COUNT(*) AS n FROM maintenance WHERE ship_pk = %s AND status IN ('In Progress','Delayed')",
                       (ship_pk,), fetch="one")["n"]
    ship = run_query("SELECT status FROM ships WHERE id = %s", (ship_pk,), fetch="one")
    if not ship:
        return
    if active and ship["status"] != "Under Maintenance":
        run_query("UPDATE ships SET status = 'Under Maintenance' WHERE id = %s", (ship_pk,), fetch=None)
    elif not active and ship["status"] == "Under Maintenance":
        run_query("UPDATE ships SET status = 'Ready' WHERE id = %s", (ship_pk,), fetch=None)


@app.route("/api/maintenance", methods=["GET"])
def list_maintenance():
    sql, params = MAINT_SQL, []
    if request.args.get("status"):
        sql += " AND mt.status = %s"; params.append(request.args["status"].strip())
    if request.args.get("ship_pk", "").isdigit():
        sql += " AND mt.ship_pk = %s"; params.append(int(request.args["ship_pk"]))
    return jsonify(run_query(sql + " ORDER BY mt.start_date DESC, mt.id DESC", params))


@app.route("/api/maintenance", methods=["POST"])
def create_maintenance():
    clean, err = validate_maintenance(request.get_json(silent=True))
    if err:
        return error(err, 400)
    new = run_query(
        """INSERT INTO maintenance (ship_pk, description, start_date, end_date, status)
           VALUES (%(ship_pk)s, %(description)s, %(start_date)s, %(end_date)s, %(status)s) RETURNING id""",
        clean, fetch="one")
    sync_ship_status(clean["ship_pk"])
    return jsonify(run_query(MAINT_SQL + " AND mt.id = %s", (new["id"],), fetch="one")), 201


@app.route("/api/maintenance/<int:mid>", methods=["PUT"])
def update_maintenance(mid):
    old = run_query("SELECT ship_pk FROM maintenance WHERE id = %s", (mid,), fetch="one")
    if not old:
        return error("Maintenance record not found.", 404)
    clean, err = validate_maintenance(request.get_json(silent=True))
    if err:
        return error(err, 400)
    clean["id"] = mid
    run_query("""UPDATE maintenance SET ship_pk=%(ship_pk)s, description=%(description)s, start_date=%(start_date)s,
                 end_date=%(end_date)s, status=%(status)s WHERE id=%(id)s""", clean, fetch=None)
    for pk in {old["ship_pk"], clean["ship_pk"]}:
        sync_ship_status(pk)
    return jsonify(run_query(MAINT_SQL + " AND mt.id = %s", (mid,), fetch="one"))


@app.route("/api/maintenance/<int:mid>", methods=["DELETE"])
def delete_maintenance(mid):
    old = run_query("SELECT ship_pk FROM maintenance WHERE id = %s", (mid,), fetch="one")
    if not old:
        return error("Maintenance record not found.", 404)
    run_query("DELETE FROM maintenance WHERE id = %s", (mid,), fetch=None)
    sync_ship_status(old["ship_pk"])
    return jsonify({"message": "Maintenance record deleted."})


# ---------- Vessel movement ----------
MOVEMENT_SQL = """SELECT m.id, m.ship_pk, s.ship_id, s.ship_name, m.movement_type,
                         CAST(m.movement_date AS TEXT) AS movement_date, m.berth_number, m.notes
                  FROM movements m JOIN ships s ON s.id = m.ship_pk"""


@app.route("/api/movements", methods=["GET"])
def list_movements():
    sql, params = MOVEMENT_SQL, []
    if request.args.get("ship_pk", "").isdigit():
        sql += " WHERE m.ship_pk = %s"; params.append(int(request.args["ship_pk"]))
    return jsonify(run_query(sql + " ORDER BY m.movement_date DESC, m.id DESC", params))


@app.route("/api/movements", methods=["POST"])
def create_movement():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Invalid request body.", 400)
    try:
        ship_pk = int(data.get("ship_pk"))
    except (TypeError, ValueError):
        return error("Please select a vessel.", 400)
    mtype = str(data.get("movement_type", "")).strip()
    berth = str(data.get("berth_number") or "").strip()
    notes = str(data.get("notes") or "").strip()
    if mtype not in ("Arrival", "Departure"):
        return error("Movement type must be Arrival or Departure.", 400)
    mdate, err = parse_date(data.get("movement_date"), "Date")
    if err:
        return error(err, 400)
    if len(berth) > 30 or len(notes) > 500:
        return error("Berth or notes too long.", 400)
    ship = run_query("SELECT id, berth_number, status FROM ships WHERE id = %s", (ship_pk,), fetch="one")
    if not ship:
        return error("Selected vessel does not exist.", 404)
    last = run_query("SELECT movement_type FROM movements WHERE ship_pk = %s ORDER BY movement_date DESC, id DESC LIMIT 1",
                     (ship_pk,), fetch="one")
    # Docked = last recorded movement was an arrival, or (no history yet) the vessel is marked Docked
    docked = (last["movement_type"] == "Arrival") if last else ship["status"] == "Docked"
    if mtype == "Arrival":
        if not berth:
            return error("Berth is required for an arrival.", 400)
        if docked:
            return error("Vessel has already arrived and is docked. Record a departure first.", 409)
    else:
        if not docked:
            return error("Vessel is not currently docked, so a departure cannot be recorded.", 409)
        berth = berth or ship["berth_number"] or ""
    run_query("""INSERT INTO movements (ship_pk, movement_type, movement_date, berth_number, notes)
                 VALUES (%s, %s, %s, %s, %s)""", (ship_pk, mtype, mdate, berth or None, notes or None), fetch=None)
    # A vessel that is under maintenance keeps that status; only the berth changes.
    in_maint = ship["status"] == "Under Maintenance"
    if mtype == "Arrival":
        run_query("UPDATE ships SET status = %s, berth_number = %s WHERE id = %s",
                  ("Under Maintenance" if in_maint else "Docked", berth, ship_pk), fetch=None)
    else:
        run_query("UPDATE ships SET status = %s, berth_number = NULL WHERE id = %s",
                  ("Under Maintenance" if in_maint else "In Service", ship_pk), fetch=None)
    return jsonify({"message": f"{mtype} recorded."}), 201


@app.errorhandler(DB_ERROR)
def handle_db_error(e):
    app.logger.error("Database error: %s", e)
    return error("Database error. Please try again later.", 500)


@app.errorhandler(404)
def not_found(_):
    return error("Route not found.", 404)


@app.errorhandler(405)
def bad_method(_):
    return error("Method not allowed.", 405)


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=int(os.environ.get("PORT", 5001)))
