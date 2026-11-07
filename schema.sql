-- FALCON FITNESS — database schema
-- Generated from SCHEMA in app.py. Reference only; app.py creates and
-- migrates this itself on startup.

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
