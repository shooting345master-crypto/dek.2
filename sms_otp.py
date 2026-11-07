"""
FALCON FITNESS — one-time codes and SMS delivery
================================================

HOW THIS BEHAVES TODAY
----------------------
No SMS provider is configured, so `send_otp()` puts the code on screen and
records it for the owner, and says loudly in the admin panel that it did so.
The moment you fill in `FALCON_SMS_PROVIDER` and its key, the same function
posts a real SMS through the provider and the on-screen copy disappears.

WHAT YOU MUST KNOW ABOUT SMS IN INDIA
-------------------------------------
Transactional SMS to Indian numbers legally requires DLT registration: you
register your business, your sender ID (a 6-letter header) and each message
template on a TRAI-mandated portal, and the provider will reject traffic that
is not registered. That registration is against your business and is not
something this code can do for you. Budget a few days.

Until then, the on-screen code path works everywhere and is genuinely useful:
it proves the person registering is the person sitting at the keyboard holding
the receipt, which is the main thing it is for.
"""

from __future__ import annotations

import json
import os
import random
import secrets
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from hashlib import sha256

from werkzeug.security import check_password_hash, generate_password_hash

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_LENGTH = 6


# ---------------------------------------------------------------------------
#  configuration
# ---------------------------------------------------------------------------
def sms_config():
    return {
        "provider": (os.environ.get("FALCON_SMS_PROVIDER") or "").strip().lower(),
        "key": (os.environ.get("FALCON_SMS_KEY") or "").strip(),
        "sender": (os.environ.get("FALCON_SMS_SENDER") or "").strip(),
        "template": (os.environ.get("FALCON_SMS_TEMPLATE") or "").strip(),
        # Fast2SMS uses "route"; MSG91 uses "country".
        "route": (os.environ.get("FALCON_SMS_ROUTE") or "otp").strip(),
        "country": (os.environ.get("FALCON_SMS_COUNTRY") or "91").strip(),
    }


def sms_ready():
    c = sms_config()
    return c["provider"] in ("fast2sms", "msg91", "custom") and bool(c["key"])


# ---------------------------------------------------------------------------
#  codes
# ---------------------------------------------------------------------------
def new_code():
    """A 6-digit numeric code, from the system CSPRNG."""
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


def hash_code(code):
    """Salted one-way hash, so a database leak does not expose live codes."""
    salt = os.environ.get("FALCON_OTP_SALT") or "falcon-otp"
    return sha256((salt + ":" + code).encode()).hexdigest()


def verify_code(code, stored_hash):
    salt = os.environ.get("FALCON_OTP_SALT") or "falcon-otp"
    return secrets.compare_digest(
        sha256((salt + ":" + code).encode()).hexdigest(), stored_hash or "")


def issue(con, user_id, purpose, phone, channel="onscreen"):
    """
    Create a fresh code, invalidating any earlier unused one for this purpose.
    Returns (code, expires_at_datetime). The plaintext code is returned to the
    caller exactly once so it can be shown or sent — it is never stored.
    """
    now = datetime.now()
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)
    con.execute(
        "UPDATE otps SET consumed_at=? WHERE user_id=? AND purpose=? AND consumed_at IS NULL",
        (now.isoformat(timespec="seconds"), user_id, purpose))
    code = new_code()
    con.execute(
        "INSERT INTO otps (user_id,purpose,code_hash,channel,sent_to,created_at,expires_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (user_id, purpose, hash_code(code), channel, phone or "",
         now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")))
    con.commit()
    return code, expires


def check(con, user_id, purpose, code):
    """
    Validate a submitted code. Returns (ok, reason).
    Single-use, attempt-limited, time-limited.
    """
    row = con.execute(
        "SELECT * FROM otps WHERE user_id=? AND purpose=? AND consumed_at IS NULL"
        " ORDER BY id DESC LIMIT 1", (user_id, purpose)).fetchone()
    if not row:
        return False, "No code is waiting. Ask for a new one."
    now = datetime.now()
    if now > datetime.fromisoformat(row["expires_at"]):
        return False, "That code has expired. Ask for a new one."
    if row["attempts"] >= OTP_MAX_ATTEMPTS:
        con.execute("UPDATE otps SET consumed_at=? WHERE id=?",
                    (now.isoformat(timespec="seconds"), row["id"]))
        con.commit()
        return False, "Too many wrong codes. Ask for a new one."
    if not verify_code((code or "").strip(), row["code_hash"]):
        con.execute("UPDATE otps SET attempts=attempts+1 WHERE id=?", (row["id"],))
        con.commit()
        left = OTP_MAX_ATTEMPTS - row["attempts"] - 1
        return False, f"That code is not right. {max(0, left)} attempt(s) left."
    con.execute("UPDATE otps SET consumed_at=? WHERE id=?",
                (now.isoformat(timespec="seconds"), row["id"]))
    con.commit()
    return True, "verified"


# ---------------------------------------------------------------------------
#  delivery
# ---------------------------------------------------------------------------
def send_sms(phone, message):
    """
    Post a real SMS if a provider is configured.
    Returns (ok, detail). Never raises — a dead SMS gateway must not break a
    registration, it just falls back to the on-screen code.
    """
    c = sms_config()
    if not sms_ready():
        return False, "no-provider"

    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) != 10:
        return False, "bad-phone"

    try:
        if c["provider"] == "fast2sms":
            data = urllib.parse.urlencode({
                "route": c["route"],
                "authorization": c["key"],
                "sender_id": c["sender"] or "FALCON",
                "message": message,
                "language": "english",
                "flash": "0",
                "numbers": digits,
            }).encode()
            req = urllib.request.Request(
                "https://www.fast2sms.com/dev/bulkV2", data=data,
                headers={"authorization": c["key"],
                         "Content-Type": "application/x-www-form-urlencoded"})
        elif c["provider"] == "msg91":
            payload = json.dumps({
                "sender": c["sender"] or "FALCON",
                "route": "4",
                "country": c["country"],
                "sms": [{"message": message, "to": [c["country"] + digits]}],
            }).encode()
            req = urllib.request.Request(
                "https://api.msg91.com/api/v2/sendsms", data=payload,
                headers={"authkey": c["key"], "Content-Type": "application/json"})
        else:                                   # "custom": your own endpoint
            url = os.environ.get("FALCON_SMS_URL") or ""
            if not url:
                return False, "no-url"
            payload = json.dumps({"to": digits, "message": message,
                                  "sender": c["sender"]}).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Authorization": "Bearer " + c["key"],
                         "Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=12,
                                    context=ssl.create_default_context()) as r:
            body = r.read(400).decode("utf-8", "replace")
        return True, body[:200]
    except Exception as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:140]


def deliver(code, phone, purpose_label):
    """
    Try SMS; report honestly whether it went out.

    Returns dict(channel='sms'|'onscreen', detail=str).
    """
    if sms_ready():
        msg = (f"{code} is your Falcon Fitness code for {purpose_label}. "
               f"Valid {OTP_TTL_MINUTES} minutes. Do not share it.")
        ok, detail = send_sms(phone, msg)
        if ok:
            return {"channel": "sms", "detail": "sent"}
        return {"channel": "onscreen",
                "detail": f"SMS failed ({detail}) — showing the code instead."}
    return {"channel": "onscreen", "detail": "No SMS provider configured."}
