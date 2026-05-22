"""Persistent schools, trainers, attendance, payments, users, alert rules."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from contextlib import contextmanager

import database as db_mod
from database import create_notification, get_db, _now_iso, sync_inventory_alerts
from auth import hash_password

APP_VERSION = "4.0.0"


@contextmanager
def get_db_ctx():
    with get_db() as conn:
        yield conn

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
        _migrate_extra(conn)
        _seed_if_empty(conn)
        _create_indexes(conn)


def _migrate_extra(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        );
        """
    )


def _create_indexes(conn) -> None:
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_sessions_school_date ON attendance_sessions(school_id, session_date)",
        "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_inbox ON notifications(resolved, read)",
        "CREATE INDEX IF NOT EXISTS idx_schools_name ON schools(name)",
    ]:
        conn.execute(stmt)


def log_audit(user_id: Optional[int], action: str, entity: str, detail: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, entity, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, action, entity, detail, _now_iso()),
        )


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
        if trainer_id:
            conn.execute(
                "UPDATE trainers SET sessions = sessions + 1 WHERE id = ?", (trainer_id,)
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


def _rule_enabled(rules: Dict[str, bool], key: str) -> bool:
    return rules.get(key, True)


def sync_ops_alerts() -> int:
    """Fire alert rules into the notification inbox (deduped by ref_key)."""
    rules = {r["rule_key"]: r["enabled"] for r in list_alert_rules()}
    created = 0
    if _rule_enabled(rules, "inventory_low"):
        created += sync_inventory_alerts()
    if _rule_enabled(rules, "payment_overdue"):
        for p in list_payments(status="overdue"):
            ref = f"payment:overdue:{p['id']}"
            create_notification(
                ntype="error",
                title="Payment overdue",
                body=f"{p['school_name']} — {p['amount_display']} ({p['days_overdue']}d)",
                ref_key=ref,
                category="payment",
            )
            created += 1
    if _rule_enabled(rules, "mou_renewal"):
        for s in list_schools():
            if s.get("mou_status") not in ("renewal", "pending", "draft"):
                continue
            label = "renewal due" if s["mou_status"] == "renewal" else "MOU pending"
            create_notification(
                ntype="warn",
                title=f"MOU {label}",
                body=f"{s['name']} — status {s['mou_status']}, next {s.get('next', 'TBD')}",
                ref_key=f"mou:{s['id']}",
                category="general",
            )
            created += 1
    if _rule_enabled(rules, "no_checkin"):
        today = date.today().isoformat()
        with get_db() as conn:
            for s in conn.execute("SELECT id, name FROM schools WHERE enrolled > 0").fetchall():
                hit = conn.execute(
                    "SELECT 1 FROM attendance_sessions WHERE school_id = ? AND session_date = ?",
                    (s["id"], today),
                ).fetchone()
                if not hit:
                    create_notification(
                        ntype="warn",
                        title="No check-in today",
                        body=f"{s['name']} — no session recorded yet",
                        ref_key=f"nocheckin:{s['id']}:{today}",
                        category="attendance",
                    )
                    created += 1
    return created


def mark_notification_read(notif_id: int) -> bool:
    return db_mod.mark_notification_read(notif_id)


def mark_all_notifications_read() -> int:
    return db_mod.mark_all_notifications_read()


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
        "dashboard": "live",
        "attendance": "live",
        "inventory": "live",
        "trainers": "live",
        "payments": "live",
        "notifications": "live",
        "ceo": "live",
        "checkin": "live",
        "school": "live",
        "login": "live",
    }


def list_notifications_paginated(
    category: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple:
    with get_db() as conn:
        q = "SELECT * FROM notifications WHERE 1=1"
        count_q = "SELECT COUNT(*) FROM notifications WHERE 1=1"
        args: List[Any] = []
        if not include_resolved:
            clause = " AND resolved = 0 AND (snoozed_until IS NULL OR snoozed_until < ?)"
            q += clause
            count_q += clause
            args.append(_now_iso())
        if category:
            q += " AND category = ?"
            count_q += " AND category = ?"
            args.append(category)
        total = conn.execute(count_q, args).fetchone()[0]
        q += " ORDER BY resolved ASC, read ASC, id DESC LIMIT ? OFFSET ?"
        rows = conn.execute(q, args + [limit, offset]).fetchall()
    return [_notif_row(r) for r in rows], total


def list_payments_paginated(
    status: Optional[str] = None, limit: int = 50, offset: int = 0
) -> tuple:
    all_items = list_payments(status)
    return all_items[offset : offset + limit], len(all_items)


def create_payment(
    school_id: int,
    amount_pkr: int,
    due_date: str,
    description: str = "",
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO payments (school_id, amount_pkr, status, due_date, paid_at, description, created_at)
               VALUES (?, ?, 'pending', ?, NULL, ?, ?)""",
            (school_id, amount_pkr, due_date, description, _now_iso()),
        )
        pid = cur.lastrowid
        row = conn.execute(
            """SELECT p.*, s.name AS school_name FROM payments p
               JOIN schools s ON s.id = p.school_id WHERE p.id = ?""",
            (pid,),
        ).fetchone()
        conn.execute(
            "INSERT INTO audit_log (user_id, action, entity, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, "create", "payment", f"id={pid}", _now_iso()),
        )
    return {
        "id": row["id"],
        "school_id": row["school_id"],
        "school_name": row["school_name"],
        "amount_pkr": row["amount_pkr"],
        "amount_display": f"₨{row['amount_pkr']:,}",
        "status": row["status"],
        "due_date": row["due_date"],
        "paid_at": row["paid_at"],
        "description": row["description"],
        "days_overdue": 0,
        "data_source": "live",
    }


def mark_payment_paid(payment_id: int, user_id: Optional[int] = None) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE payments SET status = 'paid', paid_at = ? WHERE id = ?",
            (_now_iso(), payment_id),
        )
        if cur.rowcount:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, entity, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, "paid", "payment", f"id={payment_id}", _now_iso()),
            )
        return cur.rowcount > 0


def update_school(
    school_id: int,
    *,
    enrolled: Optional[int] = None,
    mou_status: Optional[str] = None,
    next_session: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    fields, values = [], []
    if enrolled is not None:
        fields.append("enrolled = ?")
        values.append(enrolled)
    if mou_status is not None:
        fields.append("mou_status = ?")
        values.append(mou_status)
    if next_session is not None:
        fields.append("next_session = ?")
        values.append(next_session)
    if not fields:
        return get_school(school_id)
    fields.append("updated_at = ?")
    values.append(_now_iso())
    values.append(school_id)
    with get_db() as conn:
        conn.execute(f"UPDATE schools SET {', '.join(fields)} WHERE id = ?", values)
    log_audit(user_id, "update", "school", f"id={school_id}")
    return get_school(school_id)


def attendance_export_csv(school_id: int) -> str:
    school = get_school(school_id)
    name = school["name"] if school else f"School {school_id}"
    lines = ["school,date,present,total,attendance_pct"]
    for s in list_sessions(school_id, limit=500):
        lines.append(
            f'"{name}",{s["session_date"]},{s["present"]},{s["total"]},{s["att"]}'
        )
    return "\n".join(lines) + "\n"


def ceo_report_live() -> Dict[str, Any]:
    schools = list_schools()
    pay = payments_summary()
    trainers = list_trainers()
    import database as db_mod

    actions = []
    for p in list_payments("overdue"):
        actions.append(f"Overdue: {p['school_name']} — {p['amount_display']} ({p['days_overdue']}d)")
    for s in schools:
        if s.get("mou_status") == "renewal":
            actions.append(f"MOU renewal: {s['name']}")
    for inv in db_mod.list_inventory():
        if inv["status"] in ("low", "critical"):
            actions.append(f"Stock {inv['status']}: {inv['name']} — {inv['quantity']}/{inv['threshold']}")

    return {
        "subject": f"RoboClub Ops Digest — {date.today().isoformat()}",
        "from_addr": "ops@roboclub.pk",
        "to_addr": "ceo@roboclub.de",
        "generated": _now_iso(),
        "sections": {
            "business_summary": [
                f"{len(schools)} schools · avg attendance {avg_attendance_today()}%",
                f"Outstanding: {pay['outstanding_display']}",
                f"{len(trainers)} trainers in system",
            ],
            "action_required": actions[:8] or ["No critical actions"],
            "wins": [
                p["school_name"] + " paid " + p["amount_display"]
                for p in list_payments() if p["status"] == "paid"
            ][:5],
            "team_update": [f"Active trainers: {sum(1 for t in trainers if t['status']=='active')}"],
        },
        "pipeline_health": {"data_source": "live", "database": "sqlite"},
        "schedule": [
            {"freq": "Daily", "time": "8:00 AM PKT", "content": "Attendance + payments"},
            {"freq": "Weekly", "time": "Mon 9:00 AM PKT", "content": "Full ops digest"},
        ],
    }


