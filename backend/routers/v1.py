"""API v1 — auth, schools, attendance, payments, search."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

import store
from auth import create_token, parse_token, verify_password
from models import AlertRuleToggle, AttendanceSessionCreate, LoginRequest, SnoozeRequest

router = APIRouter(prefix="/api/v1", tags=["v1"])


def get_optional_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return parse_token(authorization[7:])


def require_role(*roles):
    def dep(authorization: Optional[str] = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Login required")
        user = parse_token(authorization[7:])
        if not user:
            raise HTTPException(401, "Invalid token")
        if roles and user["role"] not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return user

    return dep


@router.post("/auth/login")
def login(body: LoginRequest):
    row = store.get_user_by_email(body.email)
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_token(row["id"], row["role"])
    return {
        "token": token,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
            "name": row["name"],
            "trainer_id": row["trainer_id"],
        },
    }


@router.get("/auth/me")
def me(user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(401, "Not logged in")
    return user


@router.get("/meta/pages")
def pages_meta():
    return store.page_meta()


@router.get("/search")
def search(q: str = Query(..., min_length=1)):
    return store.global_search(q)


@router.get("/schools")
def schools():
    return store.list_schools()


@router.get("/schools/{school_id}")
def school_detail(school_id: int):
    d = store.school_detail(school_id)
    if not d:
        raise HTTPException(404, "School not found")
    return d


@router.get("/trainers")
def trainers():
    return store.list_trainers()


@router.get("/payments")
def payments(status: Optional[str] = None):
    return {"items": store.list_payments(status), "summary": store.payments_summary()}


@router.get("/attendance/sessions")
def sessions(school_id: Optional[int] = None, limit: int = 30):
    return store.list_sessions(school_id, limit)


@router.post("/attendance/sessions")
def create_session(
    body: AttendanceSessionCreate,
    user=Depends(require_role("trainer", "ops")),
):
    trainer_id = body.trainer_id or user.get("trainer_id")
    session = store.create_attendance_session(
        body.school_id, trainer_id, body.present, body.total, body.batch_name, body.notes
    )
    return {"session": session, "schools": store.list_schools()}


@router.get("/dashboard/ops")
def ops_dashboard():
    pay = store.payments_summary()
    return {
        "attendance_avg": store.avg_attendance_today(),
        "overdue_total_display": f"₨{pay['overdue_total_pkr']:,}",
        "overdue_count": pay["overdue_count"],
        "inventory_alerts": __import__("database").count_inventory_alerts(),
        "critical_alerts": store.critical_notifications(),
    }


@router.get("/notifications")
def notifications(
    category: Optional[str] = None,
    include_resolved: bool = False,
):
    return store.list_notifications_filtered(category, include_resolved)


@router.put("/notifications/{notif_id}/resolve")
def resolve_notif(notif_id: int, _user=Depends(require_role("ops", "ceo"))):
    if store.resolve_notification(notif_id):
        return {"ok": True}
    raise HTTPException(404, "Not found")


@router.put("/notifications/{notif_id}/snooze")
def snooze_notif(notif_id: int, body: SnoozeRequest, _user=Depends(require_role("ops"))):
    if store.snooze_notification(notif_id, body.hours):
        return {"ok": True}
    raise HTTPException(404, "Not found")


@router.get("/notifications/critical")
def critical():
    return store.critical_notifications()


@router.get("/alert-rules")
def alert_rules():
    return store.list_alert_rules()


@router.put("/alert-rules/{rule_key}")
def toggle_rule(rule_key: str, body: AlertRuleToggle, _user=Depends(require_role("ops"))):
    if store.toggle_alert_rule(rule_key, body.enabled):
        return {"ok": True}
    raise HTTPException(404, "Rule not found")
