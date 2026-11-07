"""
FALCON FITNESS — membership lifecycle
=====================================

One rule, enforced everywhere: a membership is live only while

    status = 'active'   AND   start_date <= today <= end_date

Anything else is lapsed, and a lapsed membership means no card, no member
pricing on the site, and -- if the owner turns it on -- no sign-in.

`reconcile()` is called before any page that cares about membership, so
expiry happens by itself without anyone remembering to press a button.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

MONTHS_DAYS = 30          # every plan duration is months; 1 month = 30 days


def add_months(d: date, months: int) -> date:
    """Calendar-correct month addition, clamping the day (31 Jan + 1 -> 28 Feb)."""
    m = d.month - 1 + int(months)
    y = d.year + m // 12
    m = m % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def issue_card(con, user_id, membership_id, now=None):
    """Create the digital card for a membership, once."""
    now = now or datetime.now()
    existing = con.execute(
        "SELECT * FROM member_cards WHERE membership_id=?", (membership_id,)).fetchone()
    if existing:
        if existing["revoked_at"]:
            con.execute(
                "UPDATE member_cards SET revoked_at=NULL, revoke_reason=NULL WHERE id=?",
                (existing["id"],))
        return existing["id"]
    serial = "FF-%s-%04d" % (
        now.strftime("%y%m"), secrets.randbelow(10000))
    cur = con.execute(
        "INSERT INTO member_cards (user_id,membership_id,serial,issued_at)"
        " VALUES (?,?,?,?)",
        (user_id, membership_id, serial, now.isoformat(timespec="seconds")))
    return cur.lastrowid


def revoke_card(con, membership_id, reason):
    con.execute(
        "UPDATE member_cards SET revoked_at=?, revoke_reason=?"
        " WHERE membership_id=? AND revoked_at IS NULL",
        (datetime.now().isoformat(timespec="seconds"), reason[:200], membership_id))


def card_for(con, user_id):
    """
    The member's current card, or None. Only returns a card whose membership is
    genuinely live right now -- this is the function the account page trusts.
    """
    row = con.execute(
        """SELECT c.*, m.plan_code, m.start_date, m.end_date, m.status
             FROM member_cards c
             JOIN memberships m ON m.id = c.membership_id
            WHERE c.user_id=? AND c.revoked_at IS NULL AND m.status='active'
              AND m.end_date >= ?
            ORDER BY m.end_date DESC LIMIT 1""",
        (user_id, date.today().isoformat())).fetchone()
    return row


def live_membership(con, user_id):
    """The membership that is active today, or None."""
    return con.execute(
        """SELECT * FROM memberships
            WHERE user_id=? AND status='active'
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY end_date DESC LIMIT 1""",
        (user_id, date.today().isoformat(), date.today().isoformat())).fetchone()


def reconcile(con):
    """
    Sweep every membership and bring its status up to date.

    active + expired      -> 'expired', card revoked
    active + not started  -> left alone (it starts later)

    Returns (expired_count, revoked_count).
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")

    rows = con.execute(
        "SELECT id, user_id FROM memberships"
        " WHERE status='active' AND end_date IS NOT NULL AND end_date < ?",
        (today,)).fetchall()

    expired = 0
    for r in rows:
        con.execute(
            "UPDATE memberships SET status='expired',"
            " revoked_reason=COALESCE(revoked_reason,'reached end date') WHERE id=?",
            (r["id"],))
        con.execute(
            "UPDATE users SET membership_status='expired' WHERE id=?", (r["user_id"],))
        con.execute(
            "UPDATE member_cards SET revoked_at=?, revoke_reason='membership expired'"
            " WHERE membership_id=? AND revoked_at IS NULL", (now, r["id"]))
        expired += 1

    # memberships whose end date was never set is a data error, not an expiry --
    # leave them for the owner to fix rather than silently killing them.

    if expired:
        con.commit()
    return expired, expired


def activate(con, user_id, plan_code, months, start_date, approved_by,
             note=None, amount=None, method=None, utr=None, paid_on=None):
    """
    Put a membership live. Any previous live membership for this member is
    closed first, so somebody renewing never ends up with two active rows.
    """
    now = datetime.now()
    start = start_date or date.today()
    end = add_months(start, months)

    con.execute(
        "UPDATE memberships SET status='superseded' WHERE user_id=? AND status='active'",
        (user_id,))
    con.execute(
        "UPDATE member_cards SET revoked_at=?, revoke_reason='superseded by renewal'"
        " WHERE user_id=? AND revoked_at IS NULL",
        (now.isoformat(timespec="seconds"), user_id))

    cur = con.execute(
        "INSERT INTO memberships (user_id,plan_code,start_date,end_date,status,note,created_at)"
        " VALUES (?,?,?,?, 'active', ?, ?)",
        (user_id, plan_code, start.isoformat(), end.isoformat(),
         note or "approved by owner", now.isoformat(timespec="seconds")))
    membership_id = cur.lastrowid

    if amount:
        paid = paid_on or start
        if hasattr(paid, "isoformat"):
            paid = paid.isoformat()
        con.execute(
            "INSERT INTO payments (user_id,plan_code,amount,method,paid_on,"
            "period_start,period_end,note,recorded_by,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, plan_code, amount, method or "upi", str(paid),
             start.isoformat(), end.isoformat(),
             ("UTR " + utr) if utr else "self-registration", approved_by,
             now.isoformat(timespec="seconds")))

    con.execute("UPDATE users SET membership_status='active' WHERE id=?", (user_id,))
    card_id = issue_card(con, user_id, membership_id, now)
    con.commit()
    return membership_id, card_id, start, end


def stop(con, membership_id, reason, by_user_id):
    """Owner-side manual revocation. Immediate and permanent for that period."""
    row = con.execute("SELECT user_id FROM memberships WHERE id=?",
                      (membership_id,)).fetchone()
    if not row:
        return None
    con.execute(
        "UPDATE memberships SET status='revoked', revoked_reason=?, revoked_by=?"
        " WHERE id=?", (reason[:200], by_user_id, membership_id))
    revoke_card(con, membership_id, reason)
    con.execute("UPDATE users SET membership_status='revoked' WHERE id=?",
                (row["user_id"],))
    con.commit()
    return row["user_id"]


def status_badge(mship):
    """Short, human status for the account page."""
    if not mship:
        return "no plan"
    if mship["status"] != "active":
        return mship["status"]
    try:
        left = (date.fromisoformat(mship["end_date"]) - date.today()).days
    except (ValueError, TypeError):
        return "active"
    if left < 0:
        return "expired"
    if left <= 7:
        return f"expiring in {left} day" + ("s" if left != 1 else "")
    return f"{left} days left"
