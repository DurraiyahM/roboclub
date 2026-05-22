"""Persistent schools, trainers, attendance, payments, users, alert rules."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import create_notification, get_db, _now_iso
from auth import hash_password

SCHOOLS_SEED = [
    {"name": "Beacon House School", "city": "Karachi", "mou_status": "active", "enrolled": 42, "next_session": "Today 3PM"},
    {"name": "PAF College", "city": "Islamabad", "mou_status": "active", "enrolled": 40, "next_session": "Tomorrow"},
    {"name": "Karachi Grammar School", "city": "Karachi", "mou_status": "renewal", "enrolled": 44, "next_session": "Wed"},
    {"name": "Lahore Grammar School", "city": "Lahore", "mou_status": "pending", "enrolled": 40, "next_session": "Fri"},
    {"name": "IBA Karachi", "city": "Karachi", "mou_status": "active", "enrolled": 41, "next_session": "Thu"},
    {"name": "Aitchison College", "city": "Lahore", "mou_status": "draft", "enrolled": 0, "next_session": "TBD"},
]

TRAINERS_SEED = [
    (1, "Fatima Khan", "Karachi", "Beacon House School", "fatima.khan@roboclub.pk"),
    (2, "Ahmed Ali", "Islamabad", "PAF College", "ahmed.ali@roboclub.pk"),
    (3, "Ayesha Malik", "Karachi", "Karachi Grammar School", "ayesha.malik@roboclub.pk"),
    (4, "Hassan Malik", "Lahore", "Lahore Grammar School", "hassan.malik@roboclub.pk"),
    (5, "Zainab Ahmed", "Karachi", "IBA Karachi", "zainab.ahmed@roboclub.pk"),
]

PAYMENTS_SEED = [
    ("Karachi Grammar School", 2800000, "overdue", 5),
    ("Lahore Grammar School", 1400000, "pending", 0),
    ("PAF College", 1400000, "paid", -3),
]

USERS_SEED = [
    ("ops@roboclub.pk", "ops123", "ops", "Operations Lead", None),
    ("trainer@roboclub.pk", "trainer123", "trainer", "Fatima Khan", 1),
    ("ceo@roboclub.de", "ceo123", "ceo", "CEO Germany", None),
]

ALERT_RULES_SEED = [
    ("payment_overdue", "Payment overdue > 3 days", "email,push", "error", 1),
    ("inventory_low", "Inventory below threshold", "push", "warn", 1),
    ("mou_renewal", "MOU renewal < 10 days", "email,push", "warn", 1),
    ("attendance_low", "Attendance < 75%", "push", "warn", 1),
    ("no_checkin", "No check-in by 3 PM", "push", "warn", 1),
]


def init_store() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                city TEXT NOT NULL,
                mou_status TEXT NOT NULL DEFAULT 'active',
                next_session TEXT,
                enrolled INTEGER DEFAULT 0,
                present INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trainers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                school_id INTEGER,
                email TEXT,
                status TEXT DEFAULT 'active',
                rating REAL DEFAULT 4.7,
                sessions INTEGER DEFAULT 0,
                FOREIGN KEY (school_id) REFERENCES schools(id)
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                trainer_id INTEGER,
                FOREIGN KEY (trainer_id) REFERENCES trainers(id)
            );
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER NOT NULL,
                trainer_id INTEGER,
                batch_name TEXT DEFAULT 'Main',
                present INTEGER NOT NULL,
                total INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (school_id) REFERENCES schools(id)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER NOT NULL,
                amount_pkr INTEGER NOT NULL,
                status TEXT NOT NULL,
                due_date TEXT NOT NULL,
                paid_at TEXT,
                description TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (school_id) REFERENCES schools(id)
            );
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_key TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                channels TEXT NOT NULL,
                severity TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                threshold INTEGER
            );
            """
        )
        _migrate_notifications(conn)
        _seed_if_empty(conn)


def _migrate_notifications(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notifications)").fetchall()}
    for col, ddl in [
        ("category", "ALTER TABLE notifications ADD COLUMN category TEXT DEFAULT 'general'"),
        ("resolved", "ALTER TABLE notifications ADD COLUMN resolved INTEGER DEFAULT 0"),
        ("snoozed_until", "ALTER TABLE notifications ADD COLUMN snoozed_until TEXT"),
    ]:
        if col not in cols:
            conn.execute(ddl)


def _seed_if_empty(conn) -> None:
    if conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0] == 0:
        ts = _now_iso()
        for s in SCHOOLS_SEED:
            conn.execute(
                """INSERT INTO schools (name, city, mou_status, next_session, enrolled, present, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?)""",
                (s["name"], s["city"], s["mou_status"], s["next_session"], s["enrolled"], ts),
            )
    if conn.execute("SELECT COUNT(*) FROM trainers").fetchone()[0] == 0:
        for tid, name, city, school_name, email in TRAINERS_SEED:
            sid = conn.execute(
                "SELECT id FROM schools WHERE name = ?", (school_name,)
            ).fetchone()
            conn.execute(
                """INSERT INTO trainers (id, name, city, school_id, email, status, rating, sessions)
                   VALUES (?, ?, ?, ?, ?, 'active', 4.8, 120)""",
                (tid, name, city, sid[0] if sid else None, email),
            )
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for email, pw, role, name, trainer_id in USERS_SEED:
            conn.execute(
                """INSERT INTO users (email, password_hash, role, name, trainer_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (email, hash_password(pw), role, name, trainer_id),
            )
    if conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0:
        today = date.today()
        for school_name, amount, status, days_offset in PAYMENTS_SEED:
            sid = conn.execute("SELECT id FROM schools WHERE name = ?", (school_name,)).fetchone()
            if not sid:
                continue
            due = (today + timedelta(days=days_offset)).isoformat()
            paid = _now_iso() if status == "paid" else None
            conn.execute(
                """INSERT INTO payments (school_id, amount_pkr, status, due_date, paid_at, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid[0], amount, status, due, paid, f"Term fee — {school_name}", _now_iso()),
            )
    if conn.execute("SELECT COUNT(*) FROM alert_rules").fetchone()[0] == 0:
        for key, label, channels, sev, en in ALERT_RULES_SEED:
            conn.execute(
                """INSERT INTO alert_rules (rule_key, label, channels, severity, enabled)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, label, channels, sev, en),
            )


def _school_row(r) -> Dict[str, Any]:
    att = round(100 * r["present"] / r["enrolled"]) if r["enrolled"] else 0
    mou_map = {
        "active": "✓", "renewal": "⚠ Renewal", "pending": "⏳ Pending", "draft": "📄 Draft"
    }
    status = "muted" if att <= 0 else "yellow" if att < 75 else "cyan" if att < 85 else "green"
    if r["mou_status"] == "renewal":
        status = "yellow"
    return {
        "id": r["id"],
        "name": r["name"],
        "city": r["city"],
        "att": att,
        "present": r["present"],
        "total": r["enrolled"],
        "mou": mou_map.get(r["mou_status"], r["mou_status"]),
        "mou_status": r["mou_status"],
        "next": r["next_session"],
        "status": status,
        "updated_at": r["updated_at"],
        "data_source": "live",
    }


def list_schools() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM schools ORDER BY name").fetchall()
    return [_school_row(r) for r in rows]


def get_school(school_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
    return _school_row(r) if r else None


def get_school_by_name(name: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM schools WHERE name = ?", (name,)).fetchone()
    return _school_row(r) if r else None


def update_school_present(school_id: int, present: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute("SELECT enrolled FROM schools WHERE id = ?", (school_id,)).fetchone()
        if not r:
            return None
        present = max(0, min(r["enrolled"], present))
        conn.execute(
            "UPDATE schools SET present = ?, updated_at = ? WHERE id = ?",
            (present, _now_iso(), school_id),
        )
    school = get_school(school_id)
    if school and school["att"] < 75 and school["att"] > 0:
        create_notification(
            ntype="warn",
            title="Low Attendance Alert",
            body=f"{school['name']} — {school['att']}% ({school['present']}/{school['total']})",
            ref_key=f"attendance:{school['name']}",
            category="attendance",
        )
    return school


def create_attendance_session(
    school_id: int,
    trainer_id: Optional[int],
    present: int,
    total: int,
    batch_name: str = "Main",
    notes: str = "",
) -> Dict[str, Any]:
    today = date.today().isoformat()
    ts = _now_iso()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO attendance_sessions
               (school_id, trainer_id, batch_name, present, total, session_date, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (school_id, trainer_id, batch_name, present, total, today, notes, ts),
        )
        session_id = cur.lastrowid
        conn.execute(
            "UPDATE schools SET present = ?, enrolled = MAX(enrolled, ?), updated_at = ? WHERE id = ?",
            (present, total, ts, school_id),
        )
    school = get_school(school_id)
    if school:
        create_notification(
            ntype="info",
            title="Session recorded",
            body=f"{school['name']} — {present}/{total} ({school['att']}%)",
            ref_key=f"session:{session_id}",
            category="attendance",
        )
        if school["att"] < 75 and school["att"] > 0:
            create_notification(
                ntype="warn",
                title="Low Attendance Alert",
                body=f"{school['name']} — {school['att']}%",
                ref_key=f"attendance:{school['name']}",
                category="attendance",
            )
    return get_session(session_id)  # type: ignore


def get_session(session_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute(
            """SELECT s.*, sc.name AS school_name, t.name AS trainer_name
               FROM attendance_sessions s
               JOIN schools sc ON sc.id = s.school_id
               LEFT JOIN trainers t ON t.id = s.trainer_id
               WHERE s.id = ?""",
            (session_id,),
        ).fetchone()
    if not r:
        return None
    pct = round(100 * r["present"] / r["total"]) if r["total"] else 0
    return {
        "id": r["id"],
        "school_id": r["school_id"],
        "school_name": r["school_name"],
        "trainer_name": r["trainer_name"],
        "batch_name": r["batch_name"],
        "present": r["present"],
        "total": r["total"],
        "att": pct,
        "session_date": r["session_date"],
        "notes": r["notes"],
        "created_at": r["created_at"],
    }


def list_sessions(school_id: Optional[int] = None, limit: int = 30) -> List[Dict[str, Any]]:
    q = """SELECT s.*, sc.name AS school_name, t.name AS trainer_name
           FROM attendance_sessions s
           JOIN schools sc ON sc.id = s.school_id
           LEFT JOIN trainers t ON t.id = s.trainer_id"""
    args: tuple = ()
    if school_id:
        q += " WHERE s.school_id = ?"
        args = (school_id,)
    q += " ORDER BY s.created_at DESC LIMIT ?"
    args = args + (limit,)
    with get_db() as conn:
        rows = conn.execute(q, args).fetchall()
    out = []
    for r in rows:
        pct = round(100 * r["present"] / r["total"]) if r["total"] else 0
        out.append({
            "id": r["id"],
            "school_id": r["school_id"],
            "school_name": r["school_name"],
            "trainer_name": r["trainer_name"],
            "present": r["present"],
            "total": r["total"],
            "att": pct,
            "session_date": r["session_date"],
            "created_at": r["created_at"],
        })
    return out


def attendance_history(school_id: int, days: int = 7) -> List[Dict[str, Any]]:
    since = (date.today() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT session_date, present, total FROM attendance_sessions
               WHERE school_id = ? AND session_date >= ?
               ORDER BY session_date""",
            (school_id, since),
        ).fetchall()
    return [
        {
            "date": r["session_date"],
            "att": round(100 * r["present"] / r["total"]) if r["total"] else 0,
            "present": r["present"],
            "total": r["total"],
        }
        for r in rows
    ]


def list_trainers() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, s.name AS school FROM trainers t
               LEFT JOIN schools s ON s.id = t.school_id ORDER BY t.name"""
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "city": r["city"],
            "school": r["school"] or "—",
            "school_id": r["school_id"],
            "status": r["status"],
            "rating": r["rating"],
            "sessions": r["sessions"],
            "email": r["email"],
            "data_source": "live",
        }
        for r in rows
    ]


def list_payments(status: Optional[str] = None) -> List[Dict[str, Any]]:
    q = """SELECT p.*, s.name AS school_name FROM payments p
           JOIN schools s ON s.id = p.school_id"""
    args: tuple = ()
    if status:
        q += " WHERE p.status = ?"
        args = (status,)
    q += " ORDER BY CASE p.status WHEN 'overdue' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, p.due_date"
    with get_db() as conn:
        rows = conn.execute(q, args).fetchall()
    today = date.today()
    out = []
    for r in rows:
        due = date.fromisoformat(r["due_date"])
        days_overdue = (today - due).days if r["status"] == "overdue" else 0
        out.append({
            "id": r["id"],
            "school_id": r["school_id"],
            "school_name": r["school_name"],
            "amount_pkr": r["amount_pkr"],
            "amount_display": f"₨{r['amount_pkr']:,}",
            "status": r["status"],
            "due_date": r["due_date"],
            "paid_at": r["paid_at"],
            "description": r["description"],
            "days_overdue": max(0, days_overdue),
            "data_source": "live",
        })
    return out


def payments_summary() -> Dict[str, Any]:
    payments = list_payments()
    overdue = [p for p in payments if p["status"] == "overdue"]
    pending = [p for p in payments if p["status"] == "pending"]
    total_out = sum(p["amount_pkr"] for p in overdue + pending)
    return {
        "overdue_count": len(overdue),
        "overdue_total_pkr": sum(p["amount_pkr"] for p in overdue),
        "outstanding_display": f"₨{total_out // 100000}L" if total_out >= 100000 else f"₨{total_out:,}",
        "overdue_schools": [p["school_name"] for p in overdue],
    }


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "email": r["email"],
        "role": r["role"],
        "name": r["name"],
        "trainer_id": r["trainer_id"],
    }


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "email": r["email"],
        "password_hash": r["password_hash"],
        "role": r["role"],
        "name": r["name"],
        "trainer_id": r["trainer_id"],
    }


def list_notifications_filtered(
    category: Optional[str] = None,
    include_resolved: bool = False,
) -> List[Dict[str, Any]]:
    with get_db() as conn:
        q = "SELECT * FROM notifications WHERE 1=1"
        args: List[Any] = []
        if not include_resolved:
            q += " AND resolved = 0 AND (snoozed_until IS NULL OR snoozed_until < ?)"
            args.append(_now_iso())
        if category:
            q += " AND category = ?"
            args.append(category)
        q += " ORDER BY resolved ASC, read ASC, id DESC"
        rows = conn.execute(q, args).fetchall()
    return [_notif_row(r) for r in rows]


def _notif_row(r) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "type": r["type"],
        "title": r["title"],
        "body": r["body"],
        "time": r["time_label"],
        "read": bool(r["read"]),
        "category": r["category"] if "category" in r.keys() else "general",
        "resolved": bool(r["resolved"]) if "resolved" in r.keys() else False,
        "snoozed_until": r["snoozed_until"] if "snoozed_until" in r.keys() else None,
    }


def resolve_notification(notif_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE notifications SET resolved = 1, read = 1 WHERE id = ?", (notif_id,)
        )
        return cur.rowcount > 0


def snooze_notification(notif_id: int, hours: int = 24) -> bool:
    until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE notifications SET snoozed_until = ?, read = 1 WHERE id = ?",
            (until, notif_id),
        )
        return cur.rowcount > 0


def critical_notifications() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM notifications
               WHERE resolved = 0 AND read = 0 AND type IN ('error', 'warn')
               AND (snoozed_until IS NULL OR snoozed_until < ?)
               ORDER BY id DESC LIMIT 3""",
            (_now_iso(),),
        ).fetchall()
    return [_notif_row(r) for r in rows]


def list_alert_rules() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
    return [
        {
            "id": r["id"],
            "rule_key": r["rule_key"],
            "label": r["label"],
            "channels": r["channels"],
            "severity": r["severity"],
            "enabled": bool(r["enabled"]),
            "threshold": r["threshold"],
        }
        for r in rows
    ]


def toggle_alert_rule(rule_key: str, enabled: bool) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE alert_rules SET enabled = ? WHERE rule_key = ?",
            (1 if enabled else 0, rule_key),
        )
        return cur.rowcount > 0


def global_search(q: str) -> Dict[str, Any]:
    q = f"%{q.strip().lower()}%"
    with get_db() as conn:
        schools = conn.execute(
            "SELECT id, name, city FROM schools WHERE lower(name) LIKE ? OR lower(city) LIKE ? LIMIT 8",
            (q, q),
        ).fetchall()
        trainers = conn.execute(
            "SELECT id, name, city FROM trainers WHERE lower(name) LIKE ? OR lower(email) LIKE ? LIMIT 8",
            (q, q),
        ).fetchall()
        inv = conn.execute(
            "SELECT id, sku, name FROM inventory WHERE lower(name) LIKE ? OR lower(sku) LIKE ? LIMIT 8",
            (q, q),
        ).fetchall()
    return {
        "schools": [{"id": r[0], "name": r[1], "city": r[2], "href": f"/school?id={r[0]}"} for r in schools],
        "trainers": [{"id": r[0], "name": r[1], "city": r[2], "href": "/trainers"} for r in trainers],
        "inventory": [{"id": r[0], "sku": r[1], "name": r[2], "href": "/inventory"} for r in inv],
    }


def school_detail(school_id: int) -> Optional[Dict[str, Any]]:
    school = get_school(school_id)
    if not school:
        return None
    with get_db() as conn:
        trainers = conn.execute(
            "SELECT id, name, email FROM trainers WHERE school_id = ?", (school_id,)
        ).fetchall()
        pay = conn.execute(
            "SELECT * FROM payments WHERE school_id = ? ORDER BY due_date DESC", (school_id,)
        ).fetchall()
    return {
        **school,
        "trainers": [{"id": t[0], "name": t[1], "email": t[2]} for t in trainers],
        "payments": [
            {
                "id": p["id"],
                "amount_display": f"₨{p['amount_pkr']:,}",
                "status": p["status"],
                "due_date": p["due_date"],
                "paid_at": p["paid_at"],
            }
            for p in pay
        ],
        "attendance_history": attendance_history(school_id, 14),
        "recent_sessions": list_sessions(school_id, 5),
    }


def avg_attendance_today() -> int:
    schools = list_schools()
    live = [s for s in schools if s["total"] > 0]
    if not live:
        return 0
    return round(sum(s["att"] for s in live) / len(live))


def page_meta() -> Dict[str, Any]:
    return {
        "pipeline": "demo",
        "kafka": "demo",
        "docker": "demo",
        "ingestion": "demo",
        "dashboard": "mixed",
        "attendance": "live",
        "inventory": "live",
        "trainers": "live",
        "payments": "live",
        "notifications": "live",
        "ceo": "mixed",
        "checkin": "live",
        "school": "live",
    }
