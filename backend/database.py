"""
SQLite persistence for inventory and notifications.
Data file: DATA_DIR/roboclub.db (default: ./data)
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

def _default_data_dir() -> str:
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        return "/tmp/roboclub-data"
    return os.path.join(os.path.dirname(__file__), "data")


DATA_DIR = os.getenv("DATA_DIR", _default_data_dir())
DB_PATH = os.path.join(DATA_DIR, "roboclub.db")

INVENTORY_SEED = [
    {"sku": "SRV-001", "name": "Servo Motor Pack",      "quantity": 6,  "threshold": 10, "unit": "pcs"},
    {"sku": "CHS-020", "name": "Robot Chassis Set",     "quantity": 45, "threshold": 15, "unit": "sets"},
    {"sku": "ARD-UNO", "name": "Arduino UNO R3",        "quantity": 28, "threshold": 20, "unit": "pcs"},
    {"sku": "SNS-US",  "name": "Ultrasonic Sensor",     "quantity": 12, "threshold": 15, "unit": "pcs"},
    {"sku": "BAT-LI",  "name": "LiPo Battery 3.7V",     "quantity": 8,  "threshold": 10, "unit": "pcs"},
    {"sku": "MTR-DC",  "name": "DC Motor 6V",           "quantity": 22, "threshold": 12, "unit": "pcs"},
]

NOTIFICATIONS_SEED = [
    {"type": "error",   "title": "Payment Overdue",  "body": "Karachi Grammar School — ₨2,800,000 overdue by 5 days", "read": 0},
    {"type": "warn",    "title": "MOU Renewal Due",  "body": "Karachi Grammar School MOU expires in 7 days",            "read": 0},
    {"type": "info",    "title": "Session Started",  "body": "Fatima Khan checked in @ Beacon House 3PM",               "read": 1},
    {"type": "success", "title": "Payment Received", "body": "PAF College — ₨1,400,000 received",                     "read": 1},
    {"type": "success", "title": "CEO Report Sent",  "body": "Weekly digest delivered to CEO in Germany",              "read": 1},
    {"type": "info",    "title": "New Lead",         "body": "Aitchison College inquiry via Google Ads",              "read": 1},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
    qty, thresh = row["quantity"], row["threshold"]
    if qty <= 0:
        status = "critical"
    elif qty <= thresh // 2:
        status = "critical"
    elif qty <= thresh:
        status = "low"
    else:
        status = "ok"
    return {
        "id": row["id"],
        "sku": row["sku"],
        "name": row["name"],
        "quantity": qty,
        "threshold": thresh,
        "unit": row["unit"],
        "status": status,
        "updated_at": row["updated_at"],
    }


@contextmanager
def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sku         TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL,
                quantity    INTEGER NOT NULL DEFAULT 0,
                threshold   INTEGER NOT NULL DEFAULT 10,
                unit        TEXT NOT NULL DEFAULT 'pcs',
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT NOT NULL,
                title       TEXT NOT NULL,
                body        TEXT NOT NULL,
                time_label  TEXT NOT NULL,
                read        INTEGER NOT NULL DEFAULT 0,
                ref_key     TEXT UNIQUE,
                created_at  TEXT NOT NULL
            );
            """
        )

        n = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        if n == 0:
            ts = _now_iso()
            for item in INVENTORY_SEED:
                conn.execute(
                    """INSERT INTO inventory (sku, name, quantity, threshold, unit, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (item["sku"], item["name"], item["quantity"], item["threshold"], item["unit"], ts),
                )

        n = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        if n == 0:
            for item in NOTIFICATIONS_SEED:
                conn.execute(
                    """INSERT INTO notifications (type, title, body, time_label, read, ref_key, created_at)
                       VALUES (?, ?, ?, ?, ?, NULL, ?)""",
                    (item["type"], item["title"], item["body"], "Earlier", item["read"], _now_iso()),
                )

    sync_inventory_alerts()


def list_inventory() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM inventory ORDER BY name").fetchall()
    return [_row_to_item(r) for r in rows]


def get_inventory(item_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def create_inventory(sku: str, name: str, quantity: int, threshold: int, unit: str) -> Dict[str, Any]:
    ts = _now_iso()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO inventory (sku, name, quantity, threshold, unit, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku.strip().upper(), name.strip(), quantity, threshold, unit, ts),
        )
        item_id = cur.lastrowid
    sync_inventory_alerts()
    return get_inventory(item_id)  # type: ignore


def update_inventory(
    item_id: int,
    *,
    name: Optional[str] = None,
    quantity: Optional[int] = None,
    threshold: Optional[int] = None,
    unit: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    item = get_inventory(item_id)
    if not item:
        return None
    fields: List[str] = []
    values: List[Any] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name.strip())
    if quantity is not None:
        fields.append("quantity = ?")
        values.append(max(0, quantity))
    if threshold is not None:
        fields.append("threshold = ?")
        values.append(max(1, threshold))
    if unit is not None:
        fields.append("unit = ?")
        values.append(unit.strip())
    if not fields:
        return item
    fields.append("updated_at = ?")
    values.append(_now_iso())
    values.append(item_id)
    with get_db() as conn:
        conn.execute(f"UPDATE inventory SET {', '.join(fields)} WHERE id = ?", values)
    sync_inventory_alerts()
    return get_inventory(item_id)


def adjust_inventory(item_id: int, delta: int) -> Optional[Dict[str, Any]]:
    item = get_inventory(item_id)
    if not item:
        return None
    new_qty = max(0, item["quantity"] + delta)
    return update_inventory(item_id, quantity=new_qty)


def count_inventory_alerts() -> int:
    return sum(1 for i in list_inventory() if i["status"] in ("low", "critical"))


def sync_inventory_alerts() -> int:
    """Create/update low-stock notifications; clear when stock is OK."""
    created = 0
    items = list_inventory()
    with get_db() as conn:
        for item in items:
            ref = f"inventory:{item['id']}"
            if item["status"] in ("low", "critical"):
                level = "CRITICAL" if item["status"] == "critical" else "LOW"
                ntype = "error" if item["status"] == "critical" else "warn"
                title = f"Stock {level}: {item['name']}"
                body = (
                    f"{item['name']} — qty {item['quantity']} {item['unit']}, "
                    f"reorder at {item['threshold']} {item['unit']}"
                )
                existing = conn.execute(
                    "SELECT id FROM notifications WHERE ref_key = ?", (ref,)
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE notifications SET type = ?, title = ?, body = ?,
                           time_label = 'Just now', read = 0 WHERE ref_key = ?""",
                        (ntype, title, body, ref),
                    )
                else:
                    conn.execute(
                        """INSERT INTO notifications
                           (type, title, body, time_label, read, ref_key, created_at)
                           VALUES (?, ?, ?, 'Just now', 0, ?, ?)""",
                        (ntype, title, body, ref, _now_iso()),
                    )
                    created += 1
            else:
                conn.execute(
                    "UPDATE notifications SET read = 1 WHERE ref_key = ? AND read = 0",
                    (ref,),
                )
    return created


def list_notifications() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications ORDER BY read ASC, id DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "body": r["body"],
            "time": r["time_label"],
            "read": bool(r["read"]),
        }
        for r in rows
    ]


def mark_notification_read(notif_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?", (notif_id,)
        )
        return cur.rowcount > 0


def mark_all_notifications_read() -> int:
    with get_db() as conn:
        cur = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return cur.rowcount


def unread_notification_count() -> int:
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE read = 0"
        ).fetchone()[0]


def _row_to_notification(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "time": row["time_label"],
        "read": bool(row["read"]),
    }


def create_notification(
    *,
    ntype: str,
    title: str,
    body: str,
    ref_key: Optional[str] = None,
    time_label: str = "Just now",
) -> Dict[str, Any]:
    """Insert or refresh a notification; returns the row as API dict."""
    with get_db() as conn:
        if ref_key:
            existing = conn.execute(
                "SELECT id FROM notifications WHERE ref_key = ?", (ref_key,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE notifications SET type = ?, title = ?, body = ?,
                       time_label = ?, read = 0 WHERE ref_key = ?""",
                    (ntype, title, body, time_label, ref_key),
                )
                row = conn.execute(
                    "SELECT * FROM notifications WHERE ref_key = ?", (ref_key,)
                ).fetchone()
                return _row_to_notification(row)

        cur = conn.execute(
            """INSERT INTO notifications
               (type, title, body, time_label, read, ref_key, created_at)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (ntype, title, body, time_label, ref_key, _now_iso()),
        )
        row = conn.execute(
            "SELECT * FROM notifications WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_notification(row)
