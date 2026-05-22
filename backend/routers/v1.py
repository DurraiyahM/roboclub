"""API v1 — bundled pages, auth, CRUD."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

import bundles
import database as db
import store
from auth import create_token, parse_token, verify_password
from models import (
    AlertRuleToggle,
    AttendanceSessionCreate,
    LoginRequest,
    PaymentCreate,
    PaymentPaid,
    SchoolUpdate,
    SnoozeRequest,
)

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


# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/login")
def login(body: LoginRequest):
    row = store.get_user_by_email(body.email)
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_token(row["id"], row["role"])
    home = "/checkin" if row["role"] == "trainer" else "/dashboard" if row["role"] == "ops" else "/ceo"
    return {
        "token": token,
        "home": home,
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


# ─── Bundled pages (1 request per screen) ─────────────────────────────────────

@router.get("/bundle/shell")
def bundle_shell():
    return bundles.bundle_app_shell()


@router.get("/bundle/home")
def bundle_home():
    return bundles.bundle_home()


@router.get("/bundle/attendance")
def bundle_attendance():
    return bundles.bundle_attendance()


@router.get("/bundle/notifications")
def bundle_notifications(category: Optional[str] = None):
    return bundles.bundle_notifications(category)


@router.get("/bundle/inventory")
def bundle_inventory():
    return bundles.bundle_inventory()


@router.get("/bundle/payments")
def bundle_payments():
    return bundles.bundle_payments()


@router.get("/bundle/checkin")
def bundle_checkin(user=Depends(get_optional_user)):
    return bundles.bundle_checkin(user)


@router.get("/bundle/ceo")
def bundle_ceo():
    return bundles.bundle_ceo()


@router.get("/bundle/trainers")
def bundle_trainers():
    return bundles.bundle_trainers()


@router.get("/bundle/school/{school_id}")
def bundle_school(school_id: int):
    d = bundles.bundle_school(school_id)
    if not d:
        raise HTTPException(404, "School not found")
    return d


# ─── Live (single poll replaces multiple SSE on Vercel) ───────────────────────

@router.get("/live")
def live_global():
    """One poll: tick simulation + shell data for badge/banner."""
    import importlib

    store.sync_ops_alerts()
    main_mod = importlib.import_module("main")
    if not main_mod._schools_state:
        main_mod._init_schools_state()
    tick = main_mod._run_live_tick()
    shell = bundles.bundle_app_shell()
    return {**tick, **shell, "schools": store.list_schools()}


@router.get("/version")
def version():
    import os

    return {
        "version": store.APP_VERSION,
        "ops_mode": os.getenv("ROBOCLUB_OPS", "1") not in ("0", "false", "False"),
    }


# ─── CRUD ─────────────────────────────────────────────────────────────────────

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


@router.put("/schools/{school_id}")
def school_update(
    school_id: int,
    body: SchoolUpdate,
    user=Depends(require_role("ops")),
):
    s = store.update_school(
        school_id,
        enrolled=body.enrolled,
        mou_status=body.mou_status,
        next_session=body.next_session,
        user_id=user["id"],
    )
    if not s:
        raise HTTPException(404, "School not found")
    return s


@router.get("/schools/{school_id}/attendance/export")
def export_attendance(school_id: int):
    csv_data = store.attendance_export_csv(school_id)
    return PlainTextResponse(
        csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=school-{school_id}-attendance.csv"},
    )


@router.get("/trainers")
def trainers():
    return store.list_trainers()


@router.get("/payments")
def payments(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    items, total = store.list_payments_paginated(status, limit, offset)
    return {"items": items, "total": total, "summary": store.payments_summary()}


@router.post("/payments")
def payment_create(body: PaymentCreate, user=Depends(require_role("ops"))):
    return store.create_payment(
        body.school_id, body.amount_pkr, body.due_date, body.description, user["id"]
    )


@router.put("/payments/{payment_id}/paid")
def payment_paid(payment_id: int, user=Depends(require_role("ops"))):
    if store.mark_payment_paid(payment_id, user["id"]):
        return {"ok": True}
    raise HTTPException(404, "Payment not found")


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
    store.log_audit(user["id"], "checkin", "session", f"school={body.school_id}")
    return {"session": session, "schools": store.list_schools()}


@router.get("/notifications")
def notifications(
    category: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    items, total = store.list_notifications_paginated(category, include_resolved, limit, offset)
    return {"items": items, "total": total}


@router.put("/notifications/{notif_id}/read")
def read_notif(notif_id: int):
    if store.mark_notification_read(notif_id):
        return {"ok": True, "unread_count": db.unread_notification_count()}
    raise HTTPException(404, "Not found")


@router.post("/notifications/read-all")
def read_all_notifs():
    count = store.mark_all_notifications_read()
    return {"ok": True, "marked": count, "unread_count": 0}


@router.put("/notifications/{notif_id}/resolve")
def resolve_notif(notif_id: int, user=Depends(require_role("ops", "ceo"))):
    if store.resolve_notification(notif_id):
        store.log_audit(user["id"], "resolve", "notification", str(notif_id))
        return {"ok": True}
    raise HTTPException(404, "Not found")


@router.put("/notifications/{notif_id}/snooze")
def snooze_notif(notif_id: int, body: SnoozeRequest, user=Depends(require_role("ops"))):
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
def toggle_rule(rule_key: str, body: AlertRuleToggle, user=Depends(require_role("ops"))):
    if store.toggle_alert_rule(rule_key, body.enabled):
        return {"ok": True}
    raise HTTPException(404, "Rule not found")
