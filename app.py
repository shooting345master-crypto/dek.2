"""
FALCON FITNESS — Kestopur, Kolkata
==================================
Flask service layer.

    browser ──▶ Flask ──subprocess──▶ C++ training engine
                  │
                  ├──▶ SQLite (data/falcon.db)
                  │      users · plans · memberships · payments · attendance
                  │      reviews · leads · checkins · form_events
                  └──▶ email notifier (optional, via .env)

ROLES
  anonymous — sees the site, but NOT a single price
  member    — sees prices, own membership, own payments & attendance, can leave a review
  admin     — everything, plus can edit prices, members, payments, attendance, enquiries

Public prices are gated on the server. An anonymous visitor never receives the
price numbers in the HTML at all — they are not hidden with CSS.

Run    :  python3 app.py
Prod   :  gunicorn -b 0.0.0.0:$PORT app:app
"""

import csv
import hmac
import io
import json
import os
import re
import secrets
import shutil
import smtplib
import socket
import sqlite3
import receipt_check
import membership as mship_mod
import sms_otp
import subprocess
import threading
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(ROOT, "bin", "falcon-engine")
SRC = os.path.join(ROOT, "engine", "main.cpp")
DB_PATH = os.environ.get("FALCON_DB_PATH", os.path.join(ROOT, "data", "falcon.db"))
DATA_DIR = os.path.dirname(DB_PATH) or "."

def _load_dotenv(path):
    """
    Read a .env file into the environment, without needing python-dotenv.

    Every guide in this project tells you to put settings in .env, so the app has
    to actually read it -- it did not, which was a real bug. This is deliberately
    tiny and has no dependency: KEY=value per line, # comments, optional quotes.
    Existing real environment variables always win, so `set PORT=8080` still
    overrides the file, which is what you want when debugging in VS Code.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.lower().startswith("export "):
                    line = line[7:]
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_dotenv(os.path.join(ROOT, ".env"))

# Flask prints "Tip: There are .env files present. Install python-dotenv to use
# them." That is misleading here: we read .env ourselves, above, before Flask
# starts. Silence the advice so it does not send you looking for a problem that
# does not exist.
os.environ["FLASK_SKIP_DOTENV"] = "1"


app = Flask(__name__, static_folder="static", template_folder="templates")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@app.template_filter("fromjson")
def _fromjson(value):
    """Decode a JSON column for the templates. Never raises."""
    try:
        return json.loads(value) if value else []
    except (ValueError, TypeError):
        return []


# ---------------------------------------------------------------------------
#  CONFIGURATION
# ---------------------------------------------------------------------------
def env(key, default=""):
    return os.environ.get(key, default).strip()


def load_secret_key():
    """Persist a generated key so logins survive a restart."""
    if env("FALCON_SECRET_KEY"):
        return env("FALCON_SECRET_KEY")
    path = os.path.join(DATA_DIR, "secret.key")
    try:
        if os.path.exists(path):
            with open(path) as fh:
                return fh.read().strip()
        os.makedirs(DATA_DIR, exist_ok=True)
        key = secrets.token_urlsafe(48)
        with open(path, "w") as fh:
            fh.write(key)
        os.chmod(path, 0o600)
        return key
    except OSError:
        return secrets.token_urlsafe(48)   # read-only FS: sessions die on restart


app.secret_key = load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env("FALCON_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)

CFG = {
    "SMTP_HOST": env("FALCON_SMTP_HOST"),
    "SMTP_PORT": int(env("FALCON_SMTP_PORT", "587") or 587),
    "SMTP_USER": env("FALCON_SMTP_USER"),
    "SMTP_PASS": env("FALCON_SMTP_PASS"),
    "SMS_PROVIDER": env("FALCON_SMS_PROVIDER"),
    "SMS_KEY": env("FALCON_SMS_KEY"),
    "MAX_RECEIPT_MB": float(env("FALCON_MAX_RECEIPT_MB", "8") or 8),
    "REQUIRE_LIVE_MEMBERSHIP": (env("FALCON_REQUIRE_LIVE_MEMBERSHIP", "0") or "0") == "1",
    "MAIL_FROM": env("FALCON_MAIL_FROM"),
    "MAIL_TO": env("FALCON_MAIL_TO"),
    "EXPORT_TOKEN": env("FALCON_EXPORT_TOKEN"),
    "MIN_FORM_SECONDS": int(env("FALCON_MIN_FORM_SECONDS", "3") or 3),
    "RATE_PER_HOUR": int(env("FALCON_RATE_PER_HOUR", "12") or 12),
    "ADMIN_EMAIL": env("FALCON_ADMIN_EMAIL"),
    "ADMIN_PASSWORD": env("FALCON_ADMIN_PASSWORD"),
}

# Your choice, set in the code so a fresh install always uses it.
# Change it here and restart, or run reset-password.py.
DEFAULT_ADMIN_PASSWORD = "Falcon.fitness29"


def member_password(first_name):
    """Member login password: member_FF_<first name, lower case>."""
    first = (first_name or "").strip().split(" ")[0].lower()
    first = re.sub(r"[^a-z0-9]", "", first)
    return f"member_FF_{first}"


BUSINESS = {
    "name": "Falcon Fitness",
    "phone": "+91 98746 05022",
    "phone2": "+91 70037 24906",
    "whatsapp": "919874605022",
    "instagram": "falconfitness.kolkata",
    "address": ("Belabhumi, 1st Floor, AC-204, Prafullakanan (E), "
                "Opp. Mio Amore, Beside Axis Bank, Kestopur, Kolkata 700101"),
    "established": "2020-08-15",
    "trainer": "Sourav Das",
    "trainer_email": "dinoalvez42@gmail.com",
    "maps": "https://www.google.com/maps/search/?api=1&query=Falcon+Fitness+Kestopur+Kolkata",
}


# ---------------------------------------------------------------------------
#  C++ ENGINE BRIDGE
# ---------------------------------------------------------------------------
ENGINE_OK = False
ENGINE_MSG = ""


def build_engine():
    # A binary that shipped inside a .zip often arrives without its execute bit
    # (zip stores it, unzip on Windows/macOS often drops it). Without this the
    # engine() call below silently falls back to the Python mirror while the
    # banner still claims "C++ live". Fix the bit instead of lying about it.
    if os.path.exists(BIN) and not os.access(BIN, os.X_OK):
        try:
            os.chmod(BIN, 0o755)
        except OSError:
            pass
    if (os.path.exists(BIN) and os.access(BIN, os.X_OK)
            and os.path.exists(SRC) and os.path.getmtime(BIN) >= os.path.getmtime(SRC)):
        return True, "prebuilt binary found"
    cxx = next((c for c in ("g++", "clang++", "c++") if shutil.which(c)), None)
    if not cxx:
        return False, "no C++ compiler on PATH — using the Python mirror"
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    try:
        res = subprocess.run([cxx, "-O3", "-std=c++17", "-o", BIN, SRC],
                             capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            return False, "compile failed: " + res.stderr[-300:]
        return True, f"compiled with {cxx}"
    except Exception as exc:
        return False, f"compile error: {exc}"


def engine(cmd, **flags):
    if os.path.exists(BIN) and os.access(BIN, os.X_OK):
        args = [BIN, cmd]
        for k, v in flags.items():
            args += [f"--{k}", str(v)]
        try:
            res = subprocess.run(args, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
    from fallback_engine import emulate
    return emulate(cmd, **flags)


# ---------------------------------------------------------------------------
#  SCHEMA
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    active INTEGER NOT NULL DEFAULT 1,
    must_change_pw INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    grp TEXT NOT NULL,
    label TEXT NOT NULL,
    months INTEGER NOT NULL DEFAULT 1,
    price REAL NOT NULL,
    admission REAL NOT NULL DEFAULT 0,
    sessions INTEGER,
    note TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_code TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mship_user ON memberships(user_id);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_code TEXT,
    amount REAL NOT NULL,
    method TEXT,
    paid_on TEXT,
    period_start TEXT,
    period_end TEXT,
    note TEXT,
    recorded_by INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pay_user ON payments(user_id);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    checkin_at TEXT NOT NULL,
    marked_by INTEGER,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_att_user ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_att_time ON attendance(checkin_at);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    rating INTEGER NOT NULL DEFAULT 5,
    body TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'website',
    status TEXT NOT NULL DEFAULT 'pending',
    user_id INTEGER,
    created_at TEXT NOT NULL,
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    goal TEXT,
    message TEXT,
    source TEXT,
    consent INTEGER NOT NULL DEFAULT 0,
    ip_hash TEXT,
    created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member TEXT NOT NULL,
    kind TEXT NOT NULL,
    load REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS form_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_lookup ON form_events(ip_hash, created_at);

-- ---------------------------------------------------------------------------
--  SELF-SERVICE MEMBERSHIP REGISTRATION
--  Someone pays the owner in person, then registers here with a photo of the
--  receipt. Nothing is activated until the owner approves.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_code TEXT NOT NULL,
    declared_amount REAL NOT NULL,
    declared_paid_on TEXT,
    method TEXT,
    utr TEXT,
    receipt_path TEXT,
    receipt_sha256 TEXT,
    screen_json TEXT,
    screen_score INTEGER,
    screen_verdict TEXT,
    ocr_amount REAL,
    ocr_date TEXT,
    ocr_status TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_note TEXT,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    membership_id INTEGER,
    created_at TEXT NOT NULL,
    ip_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_reg_status ON registrations(status);
CREATE INDEX IF NOT EXISTS idx_reg_user ON registrations(user_id);

-- One-time codes, used for phone verification at registration and before any
-- password change. Stored hashed, single-use, time-limited.
CREATE TABLE IF NOT EXISTS otps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    channel TEXT,
    sent_to TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_otp_user ON otps(user_id, purpose);

-- Digital membership cards. A card is valid only while its membership row is
-- 'active' and the end date has not passed; the sweep below enforces that.
CREATE TABLE IF NOT EXISTS member_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    membership_id INTEGER NOT NULL,
    serial TEXT NOT NULL UNIQUE,
    issued_at TEXT NOT NULL,
    revoked_at TEXT,
    revoke_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_card_user ON member_cards(user_id);
"""

# Columns added after their table was first created. CREATE TABLE IF NOT EXISTS
# will not add these to an existing database, so each is applied explicitly.
MIGRATIONS = [
    ("leads", "email", "TEXT"), ("leads", "goal", "TEXT"), ("leads", "message", "TEXT"),
    ("leads", "source", "TEXT"), ("leads", "consent", "INTEGER NOT NULL DEFAULT 0"),
    ("leads", "ip_hash", "TEXT"), ("leads", "created_at", "TEXT"),
    ("leads", "notified", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "phone_verified", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "membership_status", "TEXT"),
    ("users", "self_registered", "INTEGER NOT NULL DEFAULT 0"),
    ("memberships", "revoked_reason", "TEXT"),
    ("memberships", "revoked_by", "INTEGER"),
]

# The real price sheet, from the club's own poster.
SEED_PLANS = [
    ("general_m",  "general",  "Monthly",   1,  999,  500, None, "Everyday offer"),
    ("general_3",  "general",  "3 months",  3, 2599,    0, None, None),
    ("general_4",  "general",  "4 months",  4, 3399,    0, None, None),
    ("general_6",  "general",  "6 months",  6, 4699,    0, None, None),
    ("general_12", "general",  "1 year",   12, 7999,    0, None, None),
    ("pt_1",   "pt",      "1 month",   1,  2500, 0, 16,  None),
    ("pt_3",   "pt",      "3 months",  3,  7000, 0, 48,  None),
    ("pt_6",   "pt",      "6 months",  6, 12000, 0, 100, None),
    ("pt_12",  "pt",      "12 months", 12, 20000, 0, 200, None),
    ("ptd_3",  "pt_duo",  "3 months",  3,  7000, 0, 48,  None),
    ("ptd_6",  "pt_duo",  "6 months",  6, 12000, 0, 100, None),
    ("ptd_12", "pt_duo",  "12 months", 12, 20000, 0, 200, None),
    ("cpl_3",  "couple",  "3 months",  3,  2400, 0, None, "per person, two members"),
    ("cpl_6",  "couple",  "6 months",  6,  4000, 0, None, "per person, two members"),
    ("cpl_12", "couple",  "12 months", 12, 7000, 0, None, "per person, two members"),
    ("stu_3",  "student", "3 months",  3,  2500, 0, None, "ID required"),
    ("stu_6",  "student", "6 months",  6,  4500, 0, None, "ID required"),
    ("stu_12", "student", "12 months", 12, 6500, 0, None, "ID required"),
    ("fr3_3",  "friends3", "3 months",  3,  7200, 0, None, "group of 3"),
    ("fr3_6",  "friends3", "6 months",  6, 13500, 0, None, "group of 3"),
    ("fr3_12", "friends3", "12 months", 12, 20100, 0, None, "group of 3"),
    ("fr4_3",  "friends4", "3 months",  3,  9200, 0, None, "group of 4"),
    ("fr4_6",  "friends4", "6 months",  6, 17200, 0, None, "group of 4"),
    ("fr4_12", "friends4", "12 months", 12, 26000, 0, None, "group of 4"),
    ("day",    "daypass",  "1 day",     0,   150, 0, None, "2 hours only"),
]


def init_db():
    """Idempotent: new file, deleted file, or an older schema."""
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        # Workers boot together; wait for the write lock instead of failing.
        con.execute("PRAGMA busy_timeout=30000")
        con.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if cols and column not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        con.commit()
        seed_plans(con)
        seed_admin(con)
    finally:
        con.close()


def seed_plans(con):
    if con.execute("SELECT COUNT(*) FROM plans").fetchone()[0]:
        return
    now = datetime.now().isoformat(timespec="seconds")
    for i, (code, grp, label, months, price, adm, sess, note) in enumerate(SEED_PLANS):
        con.execute(
            "INSERT INTO plans (code,grp,label,months,price,admission,sessions,note,"
            "active,sort,updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (code, grp, label, months, price, adm, sess, note, i, now))
    con.commit()


_ADMIN_SEEDED = False


def seed_admin(con):
    """Create the first admin exactly once per process."""
    global _ADMIN_SEEDED
    if _ADMIN_SEEDED:
        return
    if con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]:
        _ADMIN_SEEDED = True
        return

    email = CFG["ADMIN_EMAIL"] or BUSINESS["trainer_email"]
    password = CFG["ADMIN_PASSWORD"] or DEFAULT_ADMIN_PASSWORD
    now = datetime.now().isoformat(timespec="seconds")

    # Several gunicorn workers start at the same instant, and each one has its
    # own copy of the _ADMIN_SEEDED flag. They all see "no admin yet" and all
    # try to insert -- the email is UNIQUE, so every worker but the winner dies
    # with an IntegrityError and gunicorn refuses to boot at all. INSERT OR
    # IGNORE makes losing that race harmless, which is what we want: the second
    # worker simply notices the account is already there.
    try:
        cur = con.execute(
            "INSERT OR IGNORE INTO users (name,email,phone,password_hash,role,"
            "active,must_change_pw,created_at)"
            " VALUES (?,?,?,?,'admin',1,1,?)",
            (BUSINESS["trainer"], email, BUSINESS["phone"].replace(" ", ""),
             generate_password_hash(password), now))
        con.commit()
        created = cur.rowcount == 1
    except sqlite3.IntegrityError:
        con.rollback()
        created = False
    _ADMIN_SEEDED = True
    if not created:
        return          # another worker created it first; say nothing

    line = "=" * 66
    note = (
        f"\n{line}\n"
        f"  FALCON FITNESS — ADMIN ACCOUNT CREATED\n"
        f"{line}\n"
        f"  Sign in  : http://127.0.0.1:{os.environ.get('PORT', '5000')}/admin/login\n"
        f"  Email    : {email}\n"
        f"  Password : {password}\n"
        f"\n  Change this from My account -> Change password.\n"
        f"{line}\n"
    )
    print(note)
    try:
        with open(os.path.join(DATA_DIR, "ADMIN-FIRST-LOGIN.txt"), "w") as fh:
            fh.write(note)
    except OSError:
        pass

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def ip_hash(ip):
    salt = env("FALCON_IP_SALT", "falcon-local-salt")
    return hmac.new(salt.encode(), (ip or "0.0.0.0").encode(), "sha256").hexdigest()[:32]


def recent_events(con, ih, kind, minutes):
    since = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    return con.execute(
        "SELECT COUNT(*) FROM form_events WHERE ip_hash=? AND kind=? AND created_at>=?",
        (ih, kind, since)).fetchone()[0]


def record_event(con, ih, kind):
    con.execute("INSERT INTO form_events (ip_hash,kind,created_at) VALUES (?,?,?)",
                (ih, kind, datetime.now().isoformat(timespec="seconds")))
    con.commit()


def valid_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def valid_email(raw):
    if not raw:
        return True
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", raw.strip()))


def money(v):
    """Indian digit grouping: 20000 -> 20,000"""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return "—"
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s


app.jinja_env.filters["money"] = money


# ---------------------------------------------------------------------------
#  AUTH
# ---------------------------------------------------------------------------
def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid:
        row = db().execute(
            "SELECT id,name,email,phone,role,active,must_change_pw FROM users WHERE id=?",
            (uid,)).fetchone()
        if row and row["active"]:
            g.user = dict(row)
        else:
            session.clear()
    return g.user


def is_admin():
    u = current_user()
    return bool(u and u["role"] == "admin")


def login_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if not current_user():
            # Name the door explicitly: url_for("login") resolves to whichever
            # rule was registered last, which is /admin/login -- and sending a
            # member to the owner's door is both confusing and wrong.
            return redirect("/login?next=" + request.path)
        return fn(*a, **kw)
    return inner


def admin_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        u = current_user()
        if not u:
            return redirect("/admin/login?next=" + request.path)
        if u["role"] != "admin":
            abort(403)
        return fn(*a, **kw)
    return inner


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_ok():
    tok = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    return bool(tok) and hmac.compare_digest(tok, session.get("_csrf", ""))


def require_csrf():
    if not csrf_ok():
        abort(400, description="Session expired. Please reload the page and try again.")


@app.route("/login", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    """One implementation, two doors.

    /login        -> members (and the owner, if they use the admin email)
    /admin/login  -> owner only; a member email is refused here
    """
    admin_door = request.path.startswith("/admin/")
    if current_user():
        return redirect(url_for("admin_home") if is_admin() else url_for("account"))
    error = None
    if request.method == "POST":
        require_csrf()
        con = db()
        ih = ip_hash(request.remote_addr)
        if recent_events(con, ih, "login", 15) >= 10:
            error = "Too many attempts. Wait 15 minutes and try again."
        else:
            record_event(con, ih, "login")
            email = (request.form.get("email") or "").strip().lower()
            pw = request.form.get("password") or ""
            row = con.execute("SELECT * FROM users WHERE lower(email)=?", (email,)).fetchone()
            wrong_door = bool(admin_door and row and row["role"] != "admin")
            if wrong_door:
                row = None          # members must use the member door
            if (row and row["active"] and row["role"] != "admin"
                    and CFG["REQUIRE_LIVE_MEMBERSHIP"]
                    and not mship_mod.live_membership(con, row["id"])):
                error = ("Your membership has ended, so sign-in is switched off for "
                         "lapsed members. Call the club to renew.")
                row = None
            if row and row["active"] and check_password_hash(row["password_hash"], pw):
                session.clear()
                session["uid"] = row["id"]
                session.permanent = True
                csrf_token()
                con.execute("UPDATE users SET last_login=? WHERE id=?",
                            (datetime.now().isoformat(timespec="seconds"), row["id"]))
                con.commit()
                nxt = request.args.get("next") or ""
                if not nxt.startswith("/"):
                    nxt = url_for("admin_home") if row["role"] == "admin" else url_for("account")
                return redirect(nxt)
            error = ("That is a member account — use the member sign-in."
                     if wrong_door else "Email or password is incorrect.")
    return render_template("login.html", error=error, csrf=csrf_token(),
                           admin_door=admin_door)


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
#  SECURITY HEADERS
# ---------------------------------------------------------------------------
@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'")
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
    elif resp.mimetype == "text/html":
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def asset_v(filename):
    """Cache-busting stamp: mtime of the file, so a changed stylesheet gets a new URL."""
    path = os.path.join(ROOT, "static", filename)
    try:
        return str(int(os.path.getmtime(path)))
    except OSError:
        return "0"


@app.context_processor
def inject():
    u = current_user()
    return {
        "av": asset_v,
        "today": date.today().strftime("%d %B %Y"),
        "now_date": date.today(),
        "b": BUSINESS,
        "user": u,
        "is_admin": bool(u and u["role"] == "admin"),
        "prices_unlocked": bool(u),
        "csrf": csrf_token(),
        "engine_ok": ENGINE_OK,
        "today_iso": date.today().isoformat(),
        "sms_ready": sms_otp.sms_ready(),
    }


# ---------------------------------------------------------------------------
#  PUBLIC PAGES
# ---------------------------------------------------------------------------
def plan_groups(include_inactive=False):
    q = "SELECT * FROM plans"
    if not include_inactive:
        q += " WHERE active=1"
    q += " ORDER BY sort, id"
    rows = [dict(r) for r in db().execute(q).fetchall()]
    groups = {}
    for r in rows:
        groups.setdefault(r["grp"], []).append(r)
    return groups


@app.route("/")
def index():
    con = db()
    try:
        con.execute("SELECT 1 FROM plans LIMIT 1")
    except sqlite3.OperationalError:
        # database file was deleted while the app was running
        init_db()
        con = db()

    approved = [dict(r) for r in con.execute(
        "SELECT name,rating,body,created_at FROM reviews WHERE status='approved'"
        " ORDER BY id DESC LIMIT 12").fetchall()]

    return render_template(
        "index.html",
        groups=plan_groups(),
        unlocked=bool(current_user()),
        reviews=approved,
        avg_rating=(round(sum(r["rating"] for r in approved) / len(approved), 1)
                    if approved else None),
        form_ts=datetime.now().isoformat(timespec="seconds"),
        engine_msg=ENGINE_MSG,
    )


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Not found"}), 404
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(_e):
    return render_template("403.html"), 403


@app.errorhandler(400)
def bad_request(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": str(e.description)}), 400
    return render_template("400.html", message=e.description), 400


@app.get("/healthz")
def healthz():
    db_ok = True
    try:
        con = sqlite3.connect(DB_PATH, timeout=5)
        con.execute("SELECT 1 FROM plans LIMIT 1").fetchone()
        con.close()
    except Exception:
        db_ok = False
    # Report the engine honestly: on disk AND actually executable.
    live = ENGINE_OK and os.path.exists(BIN) and os.access(BIN, os.X_OK)
    return jsonify({
        "ok": db_ok,
        "engine": "c++" if live else "python-mirror",
        "engine_msg": ENGINE_MSG if live else "binary missing — running the Python mirror",
        "email": "configured" if (CFG["SMTP_HOST"] and CFG["MAIL_TO"]) else "not-configured",
        "db": db_ok,
    }), (200 if db_ok else 503)


# ---------------------------------------------------------------------------
#  PUBLIC API — ENGINE
# ---------------------------------------------------------------------------
@app.post("/api/plan")
def api_plan():
    p = request.get_json(force=True, silent=True) or {}
    out = engine("plan",
                 goal=str(p.get("goal", "hypertrophy"))[:20],
                 days=int(p.get("days", 4) or 4),
                 level=str(p.get("level", "beginner"))[:20],
                 age=int(p.get("age", 30) or 30),
                 sex="f" if p.get("sex") == "f" else "m",
                 weight=float(p.get("weight", 75) or 75),
                 height=float(p.get("height", 175) or 175),
                 activity=float(p.get("activity", 1.55) or 1.55))
    out["engine_live"] = ENGINE_OK and os.path.exists(BIN)
    return jsonify(out)


@app.post("/api/plates")
def api_plates():
    p = request.get_json(force=True, silent=True) or {}
    return jsonify(engine("plates", total=float(p.get("total", 100) or 100),
                          bar=float(p.get("bar", 20) or 20)))


@app.post("/api/e1rm")
def api_e1rm():
    p = request.get_json(force=True, silent=True) or {}
    return jsonify(engine("e1rm", weight=float(p.get("weight", 100) or 100),
                          reps=float(p.get("reps", 5) or 5)))


@app.post("/api/standards")
def api_standards():
    p = request.get_json(force=True, silent=True) or {}
    return jsonify(engine("standards", lift=str(p.get("lift", "squat"))[:12],
                          weight=float(p.get("weight", 100) or 100),
                          bw=float(p.get("bw", 75) or 75),
                          sex="f" if p.get("sex") == "f" else "m"))


@app.post("/api/acwr")
def api_acwr():
    p = request.get_json(force=True, silent=True) or {}
    hist = str(p.get("history", ""))[:400]
    return jsonify(engine("acwr", history=re.sub(r"[^0-9.,]", "", hist)))


@app.get("/api/engine/status")
def api_engine_status():
    live = ENGINE_OK and os.path.exists(BIN)
    info = engine("version") if live else {"engine": "python-mirror", "version": "1.4.0"}
    info.update({"live": live,
                 "detail": ENGINE_MSG if live else "binary missing — running the Python mirror"})
    return jsonify(info)


# ---------------------------------------------------------------------------
#  PUBLIC API — LEAD
# ---------------------------------------------------------------------------
def send_lead_email(row):
    c = CFG
    if not (c["SMTP_HOST"] and c["MAIL_TO"] and c["MAIL_FROM"]):
        return False, "email not configured"
    try:
        msg = EmailMessage()
        msg["Subject"] = f"New enquiry — {row['name']}"
        msg["From"] = c["MAIL_FROM"]
        msg["To"] = c["MAIL_TO"]
        if row["email"]:
            msg["Reply-To"] = row["email"]
        msg.set_content(
            f"New enquiry from the Falcon Fitness website\n{'-' * 46}\n"
            f"Name      : {row['name']}\nPhone     : {row['phone']}\n"
            f"Email     : {row['email'] or '—'}\nInterested: {row['goal']}\n"
            f"Message   : {row['message'] or '—'}\nReceived  : {row['created_at']}\n"
            f"Source    : {row['source']}\n{'-' * 46}\n"
            f"Call them back: tel:{row['phone']}\n")
        with smtplib.SMTP(c["SMTP_HOST"], c["SMTP_PORT"], timeout=12) as s:
            s.starttls()
            if c["SMTP_USER"]:
                s.login(c["SMTP_USER"], c["SMTP_PASS"])
            s.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)[:160]


def notify_async(row, lead_id):
    def work():
        ok, info = send_lead_email(row)
        if ok:
            try:
                con = sqlite3.connect(DB_PATH, timeout=10)
                con.execute("UPDATE leads SET notified=1 WHERE id=?", (lead_id,))
                con.commit()
                con.close()
            except Exception:
                pass
        else:
            app.logger.info("lead %s not emailed: %s", lead_id, info)
    threading.Thread(target=work, daemon=True).start()


@app.post("/api/lead")
def api_lead():
    p = request.get_json(force=True, silent=True) or {}
    con = db()

    if (p.get("website") or "").strip():
        return jsonify({"ok": True, "message": "Thanks."}), 200

    try:
        started = datetime.fromisoformat(p.get("t") or "")
        if (datetime.now() - started).total_seconds() < CFG["MIN_FORM_SECONDS"]:
            return jsonify({"ok": False, "error": "That was a little too quick — please try again."}), 429
    except Exception:
        pass

    ih = ip_hash(request.remote_addr)
    if recent_events(con, ih, "lead", 60) >= CFG["RATE_PER_HOUR"]:
        return jsonify({"ok": False,
                        "error": "Too many enquiries from this connection. Please call us instead."}), 429

    name = (p.get("name") or "").strip()[:80]
    phone = valid_phone(p.get("phone"))
    email = (p.get("email") or "").strip().lower()[:120]

    if not name or len(name) < 2:
        return jsonify({"ok": False, "error": "Please tell us your name."}), 400
    if not phone:
        return jsonify({"ok": False, "error": "Please enter a valid 10-digit Indian mobile number."}), 400
    if not valid_email(email):
        return jsonify({"ok": False, "error": "That email address does not look right."}), 400
    if not p.get("consent"):
        return jsonify({"ok": False,
                        "error": "Please tick the box so we know it's okay to contact you."}), 400

    row = {"name": name, "phone": phone, "email": email or "",
           "goal": (p.get("goal") or "General membership").strip()[:60],
           "message": (p.get("message") or "").strip()[:600],
           "source": (p.get("source") or "website").strip()[:60],
           "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p")}

    cur = con.execute(
        "INSERT INTO leads (name,phone,email,goal,message,source,consent,ip_hash,created_at)"
        " VALUES (?,?,?,?,?,?,1,?,?)",
        (row["name"], row["phone"], row["email"], row["goal"], row["message"],
         row["source"], ih, datetime.now().isoformat(timespec="seconds")))
    con.commit()
    record_event(con, ih, "lead")
    notify_async(row, cur.lastrowid)

    emailed = bool(CFG["SMTP_HOST"] and CFG["MAIL_TO"])
    return jsonify({
        "ok": True,
        "message": ("Thanks — we've got your details and will call you back today."
                    if emailed else
                    "Thanks — we've saved your details. Please call us on "
                    + BUSINESS["phone"] + " to confirm your slot."),
        "stored": True, "notified": emailed,
    })


@app.post("/api/checkin")
def api_checkin():
    p = request.get_json(force=True, silent=True) or {}
    con = db()
    ih = ip_hash(request.remote_addr)
    if recent_events(con, ih, "checkin", 60) > 60:
        return jsonify({"ok": False, "error": "Slow down a moment."}), 429
    try:
        load = max(0.0, min(200000.0, float(p.get("load", 0) or 0)))
    except (TypeError, ValueError):
        load = 0.0
    con.execute("INSERT INTO checkins (member,kind,load,created_at) VALUES (?,?,?,?)",
                (str(p.get("member", "Local"))[:40], str(p.get("kind", "session"))[:20],
                 load, datetime.now().isoformat(timespec="seconds")))
    con.commit()
    record_event(con, ih, "checkin")
    week = (date.today() - timedelta(days=6)).isoformat()
    total = con.execute("SELECT COUNT(*) FROM checkins").fetchone()[0]
    recent = con.execute("SELECT COUNT(*) FROM checkins WHERE date(created_at) >= ?",
                         (week,)).fetchone()[0]
    return jsonify({"ok": True, "total": total, "this_week": recent,
                    "message": "Logged. Consistency is the whole game."})


@app.get("/api/leads/export.csv")
def api_leads_export():
    token = request.args.get("token", "")
    if not CFG["EXPORT_TOKEN"]:
        return jsonify({"ok": False,
                        "error": "Export is disabled. Set FALCON_EXPORT_TOKEN in your .env"}), 403
    if not hmac.compare_digest(token, CFG["EXPORT_TOKEN"]):
        return jsonify({"ok": False, "error": "Invalid token"}), 403
    rows = db().execute("SELECT id,name,phone,email,goal,message,source,created_at"
                        " FROM leads ORDER BY id DESC").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "phone", "email", "interested_in", "message", "source", "received"])
    for r in rows:
        w.writerow([r["id"], r["name"], r["phone"], r["email"], r["goal"],
                    (r["message"] or "").replace("\n", " "), r["source"], r["created_at"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=falcon-leads.csv"})


# ---------------------------------------------------------------------------
#  MEMBER PORTAL
# ---------------------------------------------------------------------------
def active_membership(uid):
    return db().execute(
        "SELECT * FROM memberships WHERE user_id=? AND status='active'"
        " ORDER BY end_date DESC LIMIT 1", (uid,)).fetchone()


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    u = current_user()
    con = db()
    msg = None
    err = None

    if request.method == "POST":
        require_csrf()
        action = request.form.get("action")
        if action == "password_request":
            # Step 1: check the current password, then send a one-time code.
            cur_pw = request.form.get("current_password") or ""
            row = con.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
            if not check_password_hash(row["password_hash"], cur_pw):
                err = "Your current password is not correct."
            elif not row["phone"]:
                err = ("There is no phone number on your account, so a code cannot be "
                       "sent. Ask the owner to add one.")
            else:
                code, expires = sms_otp.issue(con, u["id"], "change_password", row["phone"])
                sent = sms_otp.deliver(code, row["phone"], "password change")
                con.execute(
                    "UPDATE otps SET channel=? WHERE user_id=? AND purpose='change_password'"
                    " AND consumed_at IS NULL", (sent["channel"], u["id"]))
                con.commit()
                session["pw_code"] = code if sent["channel"] == "onscreen" else None
                session["pw_stage"] = "verify"
                msg = ("A 6-digit code has been sent to the phone ending "
                       f"{row['phone'][-4:]}." if sent["channel"] == "sms"
                       else "No SMS provider is configured yet, so here is your code: "
                            + code)

        elif action == "password_confirm":
            # Step 2: the code plus the new password.
            new_pw = request.form.get("new_password") or ""
            ok, why = sms_otp.check(con, u["id"], "change_password",
                                    request.form.get("code"))
            if not ok:
                err = why
                session["pw_stage"] = "verify"
            elif len(new_pw) < 8:
                err = "Use at least 8 characters for the new password."
                session["pw_stage"] = "verify"
            elif new_pw != request.form.get("confirm_password"):
                err = "The two new passwords do not match."
                session["pw_stage"] = "verify"
            else:
                con.execute("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?",
                            (generate_password_hash(new_pw), u["id"]))
                con.commit()
                session.pop("pw_stage", None)
                session.pop("pw_code", None)
                # reload the row so the "please change your password" banner goes
                u = con.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
                g.pop("user", None)
                msg = "Password updated. Use the new one next time you sign in."
        elif action == "review":
            text = (request.form.get("body") or "").strip()
            rating = max(1, min(5, int(request.form.get("rating") or 5)))
            if len(text) < 15:
                err = "Please write at least a sentence or two."
            else:
                con.execute(
                    "INSERT INTO reviews (name,email,rating,body,source,status,user_id,created_at)"
                    " VALUES (?,?,?,?,'website','pending',?,?)",
                    (u["name"], u["email"], rating, text[:1200], u["id"],
                     datetime.now().isoformat(timespec="seconds")))
                con.commit()
                msg = "Thank you — your review is with the owner for approval."

    # bring expiry up to date before showing anything
    try:
        mship_mod.reconcile(con)
    except Exception:
        app.logger.exception("membership reconcile failed")
    mship = mship_mod.live_membership(con, u["id"])
    card = mship_mod.card_for(con, u["id"])
    reg = current_registration(con, u["id"])
    plan_label = None
    if mship and mship["plan_code"]:
        pr = con.execute("SELECT grp,label FROM plans WHERE code=?",
                         (mship["plan_code"],)).fetchone()
        if pr:
            plan_label = f"{pr['grp'].replace('_',' ').title()} · {pr['label']}"
    days_left = None
    if mship and mship["end_date"]:
        try:
            days_left = (date.fromisoformat(mship["end_date"]) - date.today()).days
        except ValueError:
            pass

    return render_template(
        "account.html", msg=msg, err=err, mship=mship, days_left=days_left,
        plan_label=plan_label, card=card, reg=reg,
        mship_state=mship_mod.status_badge(mship),
        pw_stage=session.get("pw_stage"),
        pw_code=session.get("pw_code"),
        plans_all=con.execute("SELECT * FROM plans WHERE active=1 ORDER BY grp, months").fetchall(),
        phone=u["phone"],
        payments=con.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 24",
                             (u["id"],)).fetchall(),
        attendance=con.execute("SELECT * FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 24",
                               (u["id"],)).fetchall(),
        my_reviews=con.execute("SELECT * FROM reviews WHERE user_id=? ORDER BY id DESC",
                               (u["id"],)).fetchall(),
        groups=plan_groups())


# ---------------------------------------------------------------------------
#  SELF-SERVICE MEMBERSHIP REGISTRATION
#
#  The member pays the owner in person, then registers here with a photo of the
#  receipt. The receipt is screened automatically; nothing goes live until the
#  owner approves it in the admin panel.
# ---------------------------------------------------------------------------
RECEIPT_DIR = os.path.join(DATA_DIR, "receipts")
ALLOWED_RECEIPT = {"jpg", "jpeg", "png", "webp", "heic", "heif", "bmp", "gif", "tif", "tiff"}


def _clean_phone(raw):
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _phone_ok(raw):
    d = _clean_phone(raw)
    return len(d) == 10 and d[0] in "6789"


def _save_receipt(file_storage, user_id):
    """
    Store the uploaded receipt privately under data/receipts/.

    Returns (path, error). The filename is generated, never taken from the
    upload, so a crafted name cannot escape the directory. The extension is
    checked against an allow-list and the bytes are confirmed to actually be an
    image by receipt_check.examine(). Nothing is served from this directory to
    anyone but the owner and the member who uploaded it.
    """
    if not file_storage or not file_storage.filename:
        return None, "Please attach a photo or screenshot of your receipt."
    name = file_storage.filename.lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_RECEIPT:
        return None, ("That file type is not supported. Please upload a JPG, PNG, "
                      "WEBP or HEIC image — a screenshot or a photo is fine.")
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    safe = "%d-%s.%s" % (user_id, secrets.token_hex(12), ext)
    path = os.path.join(RECEIPT_DIR, safe)
    file_storage.save(path)
    size = os.path.getsize(path)
    if size > int(CFG["MAX_RECEIPT_MB"] * 1024 * 1024):
        os.unlink(path)
        return None, f"That image is too large. Please keep it under {CFG['MAX_RECEIPT_MB']:.0f} MB."
    if size < 1024:
        os.unlink(path)
        return None, "That file looks empty. Please upload the receipt again."
    return path, None


def current_registration(con, user_id):
    return con.execute(
        "SELECT * FROM registrations WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,)).fetchone()


def pending_registration(con, user_id):
    return con.execute(
        "SELECT * FROM registrations WHERE user_id=? AND status='pending'"
        " ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Step 1 of self-registration: who are you, what did you buy, and here is the
    receipt. Creates the account (unverified) and the pending registration.
    """
    if current_user():
        return redirect(url_for("account"))
    con = db()
    err = None
    form = {}

    if request.method == "POST":
        require_csrf()
        ih = ip_hash(request.remote_addr)
        if recent_events(con, ih, "register", 60) >= 6:
            err = "Too many registration attempts. Wait an hour and try again."
        else:
            record_event(con, ih, "register")
            form = {k: (request.form.get(k) or "").strip()
                    for k in ("name", "email", "phone", "plan_code",
                              "amount", "paid_on", "method", "utr")}
            name = form["name"]
            email = form["email"].lower()
            phone = _clean_phone(form["phone"])
            plan = con.execute("SELECT * FROM plans WHERE code=? AND active=1",
                               (form["plan_code"],)).fetchone()

            if len(name) < 3:
                err = "Please give your full name."
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", email):
                err = "That email address does not look right."
            elif not _phone_ok(form["phone"]):
                err = "Please give a 10-digit Indian mobile number."
            elif not plan:
                err = "Please choose the plan you paid for."
            elif con.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
                err = "There is already an account with that email. Sign in instead."
            else:
                try:
                    amount = float(form["amount"] or 0)
                except ValueError:
                    amount = 0
                if amount <= 0:
                    err = "Please enter the amount you actually paid."
                else:
                    # A monthly General plan carries a one-time admission fee, so
                    # the honest total is either the plan price (joiner paid the
                    # admission separately) or price + admission. Both are fine.
                    adm = plan["admission"] or 0
                    options = [round(plan["price"]), round(plan["price"] + adm)]
                    ok_amt = any(abs(amount - o) <= max(1, o * 0.02) for o in options)
                    if not ok_amt:
                        want = f"₹{options[0]:,}" + (f" or ₹{options[1]:,}" if len(set(options)) > 1 else "")
                        err = (f"You chose {plan['label']}, which is {want} "
                               f"(including the one-time admission fee if it applies) — "
                               f"but you entered ₹{amount:,.0f}. Please check the amount, "
                               f"or pick the plan you actually paid for.")
            if not err:
                path, ferr = _save_receipt(request.files.get("receipt"), user_id=0)
                if ferr:
                    err = ferr
                else:
                    screen = receipt_check.examine(path)
                    if not screen.get("available", True):
                        # We cannot examine the image on this machine. Do not
                        # pretend we did, and do not punish the member for the
                        # owner's missing library -- accept it and mark it
                        # loudly for a manual look.
                        app.logger.warning("receipt screening unavailable: %s",
                                           receipt_check.unavailable_reason())
                    if screen["verdict"] == "likely-not-genuine":
                        os.unlink(path)
                        err = ("That image could not be read as a receipt. Please upload "
                               "a clear photo or screenshot showing the amount and the "
                               "payment reference.")
                    else:
                        # create the account, using the standard password scheme
                        pw = member_password(name)
                        now = datetime.now().isoformat(timespec="seconds")
                        cur = con.execute(
                            "INSERT INTO users (name,email,phone,password_hash,role,active,"
                            "must_change_pw,created_at,phone_verified,membership_status,"
                            "self_registered) VALUES (?,?,?,?,'member',1,1,?,0,'pending',1)",
                            (name, email, phone, generate_password_hash(pw), now))
                        uid = cur.lastrowid
                        con.commit()

                        # move the file to its per-user name
                        final = os.path.join(RECEIPT_DIR, "%d-%s.%s" % (
                            uid, secrets.token_hex(12), path.rsplit(".", 1)[-1]))
                        shutil.move(path, final)

                        ocr_text, ocr_status = receipt_check.ocr_text(final)
                        ocr_amount, ocr_date = (None, None)
                        if ocr_status == "ok":
                            ocr_amount, ocr_date = receipt_check.scrape_amount_date(ocr_text)

                        con.execute(
                            "INSERT INTO registrations (user_id,plan_code,declared_amount,"
                            "declared_paid_on,method,utr,receipt_path,receipt_sha256,"
                            "screen_json,screen_score,screen_verdict,ocr_amount,ocr_date,"
                            "ocr_status,status,created_at,ip_hash)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
                            (uid, plan["code"], amount, form["paid_on"] or None,
                             form["method"] or "upi", form["utr"] or None,
                             os.path.basename(final), screen["meta"]["sha256"],
                             json.dumps(screen["notes"]), screen["score"],
                             screen["verdict"],
                             ocr_amount,
                             ocr_date.isoformat() if ocr_date else None,
                             ocr_status, now, ih))
                        con.commit()

                        # verify the phone right away -- this is the first OTP
                        code, expires = sms_otp.issue(con, uid, "verify_phone", phone)
                        sent = sms_otp.deliver(code, phone, "membership registration")
                        con.execute("UPDATE otps SET channel=? WHERE user_id=? AND"
                                    " purpose='verify_phone' AND consumed_at IS NULL",
                                    (sent["channel"], uid))
                        con.commit()
                        session["reg_uid"] = uid
                        session["reg_code"] = code if sent["channel"] == "onscreen" else None
                        session["reg_pw"] = pw
                        return redirect(url_for("register_verify"))
    groups = plan_groups()
    return render_template("register.html", err=err, form=form, groups=groups,
                           csrf=csrf_token(), phone_ok=_phone_ok)


@app.route("/register/verify", methods=["GET", "POST"])
def register_verify():
    """Step 2: type the one-time code. Proves the phone is really theirs."""
    uid = session.get("reg_uid")
    if not uid:
        return redirect(url_for("register"))
    con = db()
    err = None
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        session.pop("reg_uid", None)
        return redirect(url_for("register"))

    if request.method == "POST":
        require_csrf()
        if (request.form.get("action") or "") == "resend":
            code, expires = sms_otp.issue(con, uid, "verify_phone", row["phone"])
            sent = sms_otp.deliver(code, row["phone"], "membership registration")
            session["reg_code"] = code if sent["channel"] == "onscreen" else None
            err = None
            flash("A new code has been sent." if sent["channel"] == "sms"
                  else "No SMS provider is configured, so here is a fresh code.",
                  "ok")
        else:
            ok, why = sms_otp.check(con, uid, "verify_phone", request.form.get("code"))
            if ok:
                con.execute("UPDATE users SET phone_verified=1 WHERE id=?", (uid,))
                con.commit()
                session.pop("reg_code", None)
                session["uid"] = uid
                session.permanent = True
                csrf_token()
                session.pop("reg_uid", None)
                flash("Phone verified. Your receipt is with the owner for approval.", "ok")
                return redirect(url_for("account"))
            err = why

    return render_template("register_verify.html", err=err, user=row,
                           show_code=session.get("reg_code"),
                           csrf=csrf_token(), sms_ready=sms_otp.sms_ready())


# ---------------------------------------------------------------------------
#  RECEIPT VIEWING (private)
# ---------------------------------------------------------------------------
@app.route("/receipt/<int:reg_id>")
@login_required
def receipt_image(reg_id):
    """
    Serve a receipt to exactly two people: the owner, and the member who
    uploaded it. Everything else is a 403. The file never enters /static.
    """
    u = current_user()
    con = db()
    reg = con.execute("SELECT * FROM registrations WHERE id=?", (reg_id,)).fetchone()
    if not reg:
        abort(404)
    if not (is_admin() or reg["user_id"] == u["id"]):
        abort(403)
    path = os.path.join(RECEIPT_DIR, reg["receipt_path"] or "")
    if not reg["receipt_path"] or not os.path.isfile(path):
        abort(404)
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
            "tif": "image/tiff", "tiff": "image/tiff",
            "heic": "image/heic", "heif": "image/heif"}.get(ext, "application/octet-stream")
    resp = Response(open(path, "rb").read(), mimetype=mime)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Content-Disposition"] = "inline; filename=receipt." + ext
    return resp


# ---------------------------------------------------------------------------
#  ADMIN: registration approvals, memberships, OTP channel status
# ---------------------------------------------------------------------------
@app.post("/admin/registrations/<int:reg_id>/<action>")
@admin_required
def admin_registration_action(reg_id, action):
    require_csrf()
    con = db()
    u = current_user()
    reg = con.execute("SELECT * FROM registrations WHERE id=?", (reg_id,)).fetchone()
    if not reg:
        abort(404)
    plan = con.execute("SELECT * FROM plans WHERE code=?", (reg["plan_code"],)).fetchone()
    member = con.execute("SELECT * FROM users WHERE id=?", (reg["user_id"],)).fetchone()
    now = datetime.now().isoformat(timespec="seconds")

    if action == "approve":
        if reg["status"] == "approved":
            flash("That registration was already approved.", "ok")
            return redirect(url_for("admin_home", tab="registrations"))
        if not plan:
            flash("That plan no longer exists, so it cannot be activated.", "err")
            return redirect(url_for("admin_home", tab="registrations"))

        # start date: the receipt date if the owner left the field alone
        start_raw = (request.form.get("start_date") or "").strip()
        try:
            from datetime import date as _d
            start = _d.fromisoformat(start_raw) if start_raw else _d.today()
        except ValueError:
            start = date.today()

        mid, card_id, s_date, e_date = mship_mod.activate(
            con, reg["user_id"], plan["code"], plan["months"], start, u["id"],
            note="self-registration approved", amount=reg["declared_amount"],
            method=reg["method"], utr=reg["utr"],
            paid_on=reg["declared_paid_on"] or start)
        con.execute(
            "UPDATE registrations SET status='approved', reviewed_by=?, reviewed_at=?,"
            " membership_id=?, admin_note=? WHERE id=?",
            (u["id"], now, mid, (request.form.get("admin_note") or "")[:300], reg_id))
        con.commit()
        flash(f"{member['name']} is now an active member from {s_date} to {e_date}. "
              f"A digital card has been issued.", "ok")

    elif action == "reject":
        con.execute(
            "UPDATE registrations SET status='rejected', reviewed_by=?, reviewed_at=?,"
            " admin_note=? WHERE id=?",
            (u["id"], now, (request.form.get("admin_note") or "not approved")[:300], reg_id))
        con.commit()
        flash(f"Registration for {member['name']} rejected. Their login still works, "
              f"but they get no membership.", "err")

    else:
        abort(404)
    return redirect(url_for("admin_home", tab="registrations"))


@app.post("/admin/memberships/<int:mid>/<action>")
@admin_required
def admin_membership_action(mid, action):
    """Owner-side manual revocation and reinstatement."""
    require_csrf()
    con = db()
    u = current_user()
    m = con.execute("SELECT * FROM memberships WHERE id=?", (mid,)).fetchone()
    if not m:
        abort(404)
    if m["user_id"] != int(request.form.get("user_id") or m["user_id"]):
        abort(400)

    if action == "revoke":
        reason = (request.form.get("reason") or "revoked by owner").strip()
        mship_mod.stop(con, mid, reason, u["id"])
        flash(f"Membership #{mid} revoked. The digital card is now void. Reason: {reason}", "ok")
    elif action == "reinstate":
        con.execute("UPDATE memberships SET status='active', revoked_reason=NULL,"
                    " revoked_by=NULL WHERE id=?", (mid,))
        mship_mod.issue_card(con, m["user_id"], mid)
        con.execute("UPDATE users SET membership_status='active' WHERE id=?",
                    (m["user_id"],))
        con.commit()
        flash(f"Membership #{mid} reinstated and the card is valid again.", "ok")
    else:
        abort(404)
    return redirect(url_for("admin_home", tab="memberships"))


@app.post("/admin/sweep")
@admin_required
def admin_sweep():
    """Run the expiry sweep on demand (it also runs automatically)."""
    require_csrf()
    expired, _ = mship_mod.reconcile(db())
    flash(f"Sweep complete — {expired} membership(s) had reached their end date and "
          f"were expired, with their cards voided.", "ok")
    return redirect(url_for("admin_home", tab="memberships"))


@app.post("/admin/registrations/<int:reg_id>/rescreen")
@admin_required
def admin_rescreen(reg_id):
    """Re-run the image examiner, e.g. after installing the OCR engine."""
    require_csrf()
    con = db()
    reg = con.execute("SELECT * FROM registrations WHERE id=?", (reg_id,)).fetchone()
    if not reg:
        abort(404)
    path = os.path.join(RECEIPT_DIR, reg["receipt_path"] or "")
    if not os.path.isfile(path):
        flash("The receipt file is missing from disk.", "err")
        return redirect(url_for("admin_home", tab="registrations"))
    screen = receipt_check.examine(path)
    text, status = receipt_check.ocr_text(path)
    amount, dt = (None, None)
    if status == "ok":
        amount, dt = receipt_check.scrape_amount_date(text)
    con.execute("UPDATE registrations SET screen_json=?, screen_score=?,"
                " screen_verdict=?, ocr_amount=?, ocr_date=?, ocr_status=? WHERE id=?",
                (json.dumps(screen["notes"]), screen["score"], screen["verdict"],
                 amount, dt.isoformat() if dt else None, status, reg_id))
    con.commit()
    if screen.get("available", True):
        flash(f"Re-screened: {screen['verdict']} ({screen['score']}/100).", "ok")
    else:
        flash("Could not screen: the image library (Pillow) is not installed on "
              "this machine. Run:  pip install Pillow", "err")
    return redirect(url_for("admin_home", tab="registrations"))


# ---------------------------------------------------------------------------
#  ADMIN PANEL
# ---------------------------------------------------------------------------
@app.route("/admin")
@app.route("/admin/<tab>")
@admin_required
def admin_home(tab="overview"):
    con = db()
    q = con.execute

    # expire anything that has run out before the owner looks at the panel
    try:
        mship_mod.reconcile(con)
    except Exception:
        app.logger.exception("membership reconcile failed")

    stats = {
        "members": q("SELECT COUNT(*) FROM users WHERE role='member'").fetchone()[0],
        "active": q("SELECT COUNT(*) FROM memberships WHERE status='active'").fetchone()[0],
        "leads": q("SELECT COUNT(*) FROM leads").fetchone()[0],
        "pending_reviews": q("SELECT COUNT(*) FROM reviews WHERE status='pending'").fetchone()[0],
        "today_att": q("SELECT COUNT(*) FROM attendance WHERE date(checkin_at)=?",
                       (date.today().isoformat(),)).fetchone()[0],
        "month_rev": q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE strftime('%Y-%m',paid_on)=?",
                       (date.today().strftime("%Y-%m"),)).fetchone()[0],
        "pending_regs": q("SELECT COUNT(*) FROM registrations WHERE status='pending'").fetchone()[0],
        "expiring": q("SELECT COUNT(*) FROM memberships WHERE status='active' AND end_date"
                      " BETWEEN ? AND ?", (date.today().isoformat(),
                                           (date.today() + timedelta(days=7)).isoformat())).fetchone()[0],
    }

    members = q("""
        SELECT u.id,u.name,u.email,u.phone,u.active,u.created_at,u.last_login,
               m.plan_code,m.end_date,m.status AS mstatus
        FROM users u
        LEFT JOIN memberships m ON m.id = (
            SELECT id FROM memberships WHERE user_id=u.id ORDER BY id DESC LIMIT 1)
        WHERE u.role='member' ORDER BY u.id DESC""").fetchall()

    return render_template(
        "admin.html", tab=tab, stats=stats,
        plans=q("SELECT * FROM plans ORDER BY grp, sort, id").fetchall(),
        members=members,
        payments=q("""SELECT p.*, u.name FROM payments p
                      LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 80""").fetchall(),
        attendance=q("""SELECT a.*, u.name FROM attendance a
                        LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 80""").fetchall(),
        leads=q("SELECT * FROM leads ORDER BY id DESC LIMIT 100").fetchall(),
        reviews=q("""SELECT r.*, u.name AS member FROM reviews r
                     LEFT JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 100""").fetchall(),
        groups=plan_groups(include_inactive=True),
        registrations=q("""
            SELECT r.*, u.name, u.email, u.phone, u.phone_verified,
                   p.grp AS plan_grp, p.label AS plan_label, p.months AS plan_months,
                   p.price AS plan_price, p.admission AS plan_admission
              FROM registrations r
              JOIN users u ON u.id = r.user_id
              LEFT JOIN plans p ON p.code = r.plan_code
             ORDER BY (r.status='pending') DESC, r.id DESC LIMIT 200""").fetchall(),
        memberships=q("""
            SELECT m.*, u.name, u.email, u.phone, u.membership_status,
                   c.serial AS card_serial, c.revoked_at AS card_revoked
              FROM memberships m
              JOIN users u ON u.id = m.user_id
              LEFT JOIN member_cards c ON c.membership_id = m.id AND c.revoked_at IS NULL
             ORDER BY (m.status='active') DESC, m.end_date DESC LIMIT 300""").fetchall(),
        rec_dir=RECEIPT_DIR,
        deadline=(date.today() + timedelta(days=7)).isoformat(),
    )


@app.post("/admin/plans/save")
@admin_required
def admin_plan_save():
    require_csrf()
    f = request.form
    pid = f.get("id") or ""
    try:
        price = float(f.get("price") or 0)
        admission = float(f.get("admission") or 0)
        months = int(f.get("months") or 1)
        sessions = f.get("sessions")
        sessions = int(sessions) if sessions not in (None, "") else None
    except ValueError:
        flash("Prices and months must be numbers.", "err")
        return redirect(url_for("admin_home", tab="prices"))

    now = datetime.now().isoformat(timespec="seconds")
    con = db()
    if pid:
        con.execute("""UPDATE plans SET label=?,months=?,price=?,admission=?,sessions=?,
                       note=?,active=?,sort=?,updated_at=? WHERE id=?""",
                    (f.get("label"), months, price, admission, sessions, f.get("note"),
                     1 if f.get("active") else 0, int(f.get("sort") or 0), now, pid))
        flash("Price updated. The change is live immediately.", "ok")
    else:
        code = re.sub(r"[^a-z0-9_]", "", (f.get("code") or "").lower())[:40]
        if not code:
            flash("Give the plan a short code, e.g. general_2.", "err")
            return redirect(url_for("admin_home", tab="prices"))
        try:
            con.execute("""INSERT INTO plans (code,grp,label,months,price,admission,sessions,
                           note,active,sort,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (code, f.get("grp") or "general", f.get("label") or code, months,
                         price, admission, sessions, f.get("note"),
                         1 if f.get("active") else 0, int(f.get("sort") or 0), now))
            flash("New plan added.", "ok")
        except sqlite3.IntegrityError:
            flash("That plan code already exists.", "err")
    con.commit()
    return redirect(url_for("admin_home", tab="prices"))


@app.post("/admin/members/add")
@admin_required
def admin_member_add():
    require_csrf()
    f = request.form
    name = (f.get("name") or "").strip()
    email = (f.get("email") or "").strip().lower()
    phone = valid_phone(f.get("phone"))
    if not name or not valid_email(email) or "@" not in (email or ""):
        flash("Name and a valid email are required.", "err")
        return redirect(url_for("admin_home", tab="members"))
    pw = f.get("password") or member_password(name)

    con = db()
    try:
        cur = con.execute(
            "INSERT INTO users (name,email,phone,password_hash,role,active,must_change_pw,created_at)"
            " VALUES (?,?,?,?,'member',1,1,?)",
            (name, email, phone, generate_password_hash(pw),
             datetime.now().isoformat(timespec="seconds")))
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        flash("A member with that email already exists.", "err")
        return redirect(url_for("admin_home", tab="members"))

    plan_code = f.get("plan_code") or ""
    plan = con.execute("SELECT * FROM plans WHERE code=?", (plan_code,)).fetchone()
    if plan:
        start = date.today()
        end = start + timedelta(days=int(plan["months"] * 30)) if plan["months"] else start
        con.execute("INSERT INTO memberships (user_id,plan_code,start_date,end_date,status,created_at)"
                    " VALUES (?,?,?,?,'active',?)",
                    (uid, plan_code, start.isoformat(), end.isoformat(),
                     datetime.now().isoformat(timespec="seconds")))
    con.commit()
    flash(f"Member {name} created. Their login password is: {pw}", "ok")
    return redirect(url_for("admin_home", tab="members"))


@app.post("/admin/members/toggle")
@admin_required
def admin_member_toggle():
    require_csrf()
    uid = request.form.get("user_id")
    con = db()
    row = con.execute("SELECT active,role FROM users WHERE id=?", (uid,)).fetchone()
    if row and row["role"] != "admin":
        con.execute("UPDATE users SET active=? WHERE id=?", (0 if row["active"] else 1, uid))
        con.commit()
        flash("Member access updated.", "ok")
    return redirect(url_for("admin_home", tab="members"))


@app.post("/admin/attendance/mark")
@admin_required
def admin_attendance_mark():
    require_csrf()
    uid = request.form.get("user_id")
    if not uid:
        flash("Pick a member first.", "err")
        return redirect(url_for("admin_home", tab="attendance"))
    con = db()
    exists = con.execute("SELECT id FROM users WHERE id=? AND role='member'", (uid,)).fetchone()
    if not exists:
        flash("That member does not exist.", "err")
        return redirect(url_for("admin_home", tab="attendance"))
    con.execute("INSERT INTO attendance (user_id,checkin_at,marked_by,note) VALUES (?,?,?,?)",
                (uid, datetime.now().isoformat(timespec="seconds"),
                 current_user()["id"], (request.form.get("note") or "")[:120]))
    con.commit()
    flash("Check-in recorded.", "ok")
    return redirect(url_for("admin_home", tab="attendance"))


@app.post("/admin/payments/add")
@admin_required
def admin_payment_add():
    require_csrf()
    f = request.form
    try:
        amount = float(f.get("amount") or 0)
    except ValueError:
        amount = 0
    if not f.get("user_id") or amount <= 0:
        flash("Pick a member and enter an amount greater than zero.", "err")
        return redirect(url_for("admin_home", tab="payments"))
    con = db()
    con.execute("""INSERT INTO payments (user_id,plan_code,amount,method,paid_on,
                   period_start,period_end,note,recorded_by,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (f.get("user_id"), f.get("plan_code"), amount, f.get("method") or "cash",
                 f.get("paid_on") or date.today().isoformat(),
                 f.get("period_start"), f.get("period_end"), (f.get("note") or "")[:200],
                 current_user()["id"], datetime.now().isoformat(timespec="seconds")))
    con.commit()
    flash("Payment recorded.", "ok")
    return redirect(url_for("admin_home", tab="payments"))


@app.post("/admin/reviews/<int:rid>/<action>")
@admin_required
def admin_review(rid, action):
    require_csrf()
    con = db()
    if action == "approve":
        con.execute("UPDATE reviews SET status='approved', approved_at=? WHERE id=?",
                    (datetime.now().isoformat(timespec="seconds"), rid))
    elif action == "reject":
        con.execute("UPDATE reviews SET status='rejected' WHERE id=?", (rid,))
    elif action == "delete":
        con.execute("DELETE FROM reviews WHERE id=?", (rid,))
    con.commit()
    flash("Review updated.", "ok")
    return redirect(url_for("admin_home", tab="reviews"))


@app.get("/admin/export/<what>.csv")
@admin_required
def admin_export(what):
    con = db()
    buf = io.StringIO()
    w = csv.writer(buf)
    if what == "leads":
        w.writerow(["id", "name", "phone", "email", "goal", "message", "created_at"])
        for r in con.execute("SELECT id,name,phone,email,goal,message,created_at FROM leads ORDER BY id DESC"):
            w.writerow([r[0], r[1], r[2], r[3], r[4], (r[5] or "").replace("\n", " "), r[6]])
    elif what == "payments":
        w.writerow(["id", "member", "amount", "method", "paid_on", "plan", "note"])
        for r in con.execute("""SELECT p.id,u.name,p.amount,p.method,p.paid_on,p.plan_code,p.note
                                FROM payments p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC"""):
            w.writerow(list(r))
    elif what == "members":
        w.writerow(["id", "name", "email", "phone", "active", "plan", "end_date"])
        for r in con.execute("""SELECT u.id,u.name,u.email,u.phone,u.active,m.plan_code,m.end_date
                                FROM users u LEFT JOIN memberships m
                                ON m.id=(SELECT id FROM memberships WHERE user_id=u.id ORDER BY id DESC LIMIT 1)
                                WHERE u.role='member'"""):
            w.writerow(list(r))
    elif what == "attendance":
        w.writerow(["id", "member", "checkin_at", "note"])
        for r in con.execute("""SELECT a.id,u.name,a.checkin_at,a.note FROM attendance a
                                LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC"""):
            w.writerow(list(r))
    else:
        abort(404)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=falcon-{what}.csv"})


# ---------------------------------------------------------------------------
#  LAUNCHER
# ---------------------------------------------------------------------------
def lan_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


init_db()
ENGINE_OK, ENGINE_MSG = build_engine()

if __name__ == "__main__":
    port = int(env("PORT", "5000") or 5000)
    ip = lan_address()
    bar = "─" * 66
    print(bar)
    print("  FALCON FITNESS  ·  local instance")
    print("  engine : %s  (%s)" % ("C++ live" if ENGINE_OK else "python mirror",
                                  ENGINE_MSG.splitlines()[0]))
    print("  email  : %s" % ("configured" if (CFG['SMTP_HOST'] and CFG['MAIL_TO'])
                             else "not configured (leads saved locally only)"))
    print("  data   : %s" % DB_PATH)
    print("")
    print("  On this computer   http://127.0.0.1:%d" % port)
    if ip:
        print("  On your phone      http://%s:%d   (same Wi-Fi)" % (ip, port))
    print("  Admin login        http://127.0.0.1:%d/admin/login" % port)
    print("  Member login       http://127.0.0.1:%d/login" % port)
    if receipt_check.available():
        print("  Receipts   : automatic screening ON")
    else:
        print("  Receipts   : screening OFF (%s)" % receipt_check.unavailable_reason())
        print("               receipts will be marked NOT SCREENED for manual review")
        print("               fix with:  pip install --only-binary=:all: Pillow")
    print(bar)
    app.run(host="0.0.0.0", port=port, debug=False)
