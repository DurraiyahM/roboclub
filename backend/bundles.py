"""Single-request page payloads — fewer round trips."""
from __future__ import annotations

from typing import Any, Dict, Optional

import database as db
import store


def _kpis() -> Dict[str, Any]:
    schools = store.list_schools()
    trainers = store.list_trainers()
    pay = store.payments_summary()
    active = sum(1 for t in trainers if t["status"] == "active")
    students = sum(s["total"] for s in schools)
    return {
        "active_schools": len(schools),
        "students_live": students,
        "trainers_online": f"{active}/{len(trainers)}",
        "revenue_apr": "₨91L",
        "inventory_alerts": db.count_inventory_alerts(),
        "pending_mous": sum(1 for s in schools if s.get("mou_status") in ("pending", "renewal")),
        "outstanding_pkr": pay["outstanding_display"],
        "new_leads": 73,
        "attendance_avg": store.avg_attendance_today(),
        "overdue_count": pay["overdue_count"],
    }


def bundle_home() -> Dict[str, Any]:
    pay = store.payments_summary()
    return {
        "ops": {
            "attendance_avg": store.avg_attendance_today(),
            "overdue_total_display": f"₨{pay['overdue_total_pkr']:,}",
            "overdue_count": pay["overdue_count"],
            "inventory_alerts": db.count_inventory_alerts(),
        },
        "kpis": _kpis(),
        "schools": store.list_schools(),
        "critical": store.critical_notifications(),
        "unread_count": db.unread_notification_count(),
        "meta": store.page_meta(),
    }


def bundle_attendance() -> Dict[str, Any]:
    return {
        "schools": store.list_schools(),
        "sessions": store.list_sessions(limit=20),
        "avg": store.avg_attendance_today(),
    }


def bundle_notifications(category: Optional[str] = None) -> Dict[str, Any]:
    items, total = store.list_notifications_paginated(category=category, limit=50)
    return {
        "items": items,
        "total": total,
        "rules": store.list_alert_rules(),
        "unread_count": db.unread_notification_count(),
    }


def bundle_inventory() -> Dict[str, Any]:
    data = db.list_inventory()
    return {
        "items": data,
        "alerts": db.count_inventory_alerts(),
        "summary": {
            "total": len(data),
            "ok": sum(1 for i in data if i["status"] == "ok"),
            "low": sum(1 for i in data if i["status"] == "low"),
            "critical": sum(1 for i in data if i["status"] == "critical"),
        },
    }


def bundle_payments() -> Dict[str, Any]:
    items, total = store.list_payments_paginated(limit=50)
    return {"items": items, "total": total, "summary": store.payments_summary(), "schools": store.list_schools()}


def bundle_checkin(user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    schools = store.list_schools()
    if user and user.get("role") == "trainer" and user.get("trainer_id"):
        with store.get_db_ctx() as conn:
            row = conn.execute(
                "SELECT school_id FROM trainers WHERE id = ?", (user["trainer_id"],)
            ).fetchone()
        if row and row["school_id"]:
            schools = [s for s in schools if s["id"] == row["school_id"]] or schools
    return {"schools": schools, "trainers": store.list_trainers()}


def bundle_ceo() -> Dict[str, Any]:
    return store.ceo_report_live()


def bundle_trainers() -> Dict[str, Any]:
    trainers = store.list_trainers()
    active = sum(1 for t in trainers if t["status"] == "active")
    return {
        "trainers": trainers,
        "stats": {
            "total_trainers": len(trainers),
            "active_trainers": active,
            "inactive_trainers": len(trainers) - active,
            "average_rating": round(sum(t["rating"] for t in trainers) / len(trainers), 2) if trainers else 0,
            "total_sessions_conducted": sum(t["sessions"] for t in trainers),
        },
    }


def bundle_school(school_id: int) -> Optional[Dict[str, Any]]:
    d = store.school_detail(school_id)
    if not d:
        return None
    d["export_url"] = f"/api/v1/schools/{school_id}/attendance/export"
    return d


def bundle_app_shell() -> Dict[str, Any]:
    import os

    ops_mode = os.getenv("ROBOCLUB_OPS", "1") not in ("0", "false", "False")
    return {
        "critical": store.critical_notifications(),
        "unread_count": db.unread_notification_count(),
        "meta": store.page_meta(),
        "version": store.APP_VERSION,
        "ops_mode": ops_mode,
    }
