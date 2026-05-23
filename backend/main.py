import asyncio
import copy
import json
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import database as db
import store
from models import InventoryAdjust, InventoryCreate, InventoryUpdate
from routers.v1 import router as v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _init_schools_state()
    yield


app = FastAPI(title="RoboClub Pipeline API - Pakistan", version=store.APP_VERSION, lifespan=lifespan)
app.include_router(v1_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



EVENT_TEMPLATES = [
    {"topic": "attendance.events", "source": "SchoolSvc",    "msg": "Student check-in: Beacon House Batch A (38/42)",        "type": "info"},
    {"topic": "inventory.alerts",  "source": "InventorySvc", "msg": "⚠ Servo Motor stock CRITICAL — qty 6, threshold 10",    "type": "warn"},
    {"topic": "finance.payments",  "source": "FinanceSvc",   "msg": "Payment received ₨1,400,000 — Lahore Grammar School",    "type": "success"},
    {"topic": "hr.leaves",         "source": "HRSvc",        "msg": "Leave request submitted: Ahmed Ali (May 22–23)",         "type": "info"},
    {"topic": "school.mou",        "source": "SchoolSvc",    "msg": "MOU renewal due: Karachi Grammar School — 7 days left",  "type": "warn"},
    {"topic": "marketing.leads",   "source": "MarketingSvc", "msg": "New lead captured: Aitchison College, Lahore",            "type": "success"},
    {"topic": "trainer.session",   "source": "TrainerSvc",   "msg": "Session started: Fatima Khan @ Beacon House 3:00 PM",    "type": "info"},
    {"topic": "finance.overdue",   "source": "FinanceSvc",   "msg": "🔴 Overdue: Karachi Grammar School ₨2,800,000 — 5 days",  "type": "error"},
    {"topic": "inventory.restock", "source": "InventorySvc", "msg": "Restock order placed: Robot Chassis Set x20",             "type": "success"},
    {"topic": "attendance.events", "source": "SchoolSvc",    "msg": "Session ended: Ayesha Malik @ PAF College — 87%",        "type": "info"},
    {"topic": "ceo.report",        "source": "ReportSvc",    "msg": "Weekly CEO digest generated — sending to Germany",             "type": "success"},
    {"topic": "hr.salary",         "source": "HRSvc",        "msg": "Salary processed: ₨1,810,000 — 5 trainers ✓",            "type": "success"},
    {"topic": "marketing.competition","source":"MarketingSvc","msg": "TechBot Academy spotted targeting IBA Karachi",          "type": "warn"},
]

DOCKER_SERVICES_SEED = [
    {"name": "kafka-broker",       "image": "confluentinc/cp-kafka:7.5",       "port": "9092", "status": "running", "cpu": 18, "mem": 512, "uptime": "14d 3h"},
    {"name": "zookeeper",          "image": "confluentinc/cp-zookeeper:7.5",   "port": "2181", "status": "running", "cpu": 4,  "mem": 128, "uptime": "14d 3h"},
    {"name": "school-service",     "image": "roboclub/school-svc:1.4",         "port": "8001", "status": "running", "cpu": 12, "mem": 256, "uptime": "6d 2h"},
    {"name": "finance-service",    "image": "roboclub/finance-svc:1.2",        "port": "8002", "status": "running", "cpu": 9,  "mem": 192, "uptime": "6d 2h"},
    {"name": "hr-service",         "image": "roboclub/hr-svc:1.1",             "port": "8003", "status": "running", "cpu": 7,  "mem": 160, "uptime": "6d 2h"},
    {"name": "inventory-service",  "image": "roboclub/inventory-svc:1.3",      "port": "8004", "status": "running", "cpu": 6,  "mem": 144, "uptime": "6d 2h"},
    {"name": "trainer-service",    "image": "roboclub/trainer-svc:1.0",        "port": "8005", "status": "running", "cpu": 8,  "mem": 176, "uptime": "3d 1h"},
    {"name": "marketing-service",  "image": "roboclub/marketing-svc:0.9",      "port": "8006", "status": "running", "cpu": 5,  "mem": 128, "uptime": "2d 4h"},
    {"name": "report-service",     "image": "roboclub/report-svc:1.1",         "port": "8007", "status": "running", "cpu": 11, "mem": 224, "uptime": "6d 2h"},
    {"name": "dashboard-api",      "image": "roboclub/dashboard:2.1",          "port": "3000", "status": "running", "cpu": 14, "mem": 288, "uptime": "6d 2h"},
    {"name": "postgres-db",        "image": "postgres:15-alpine",              "port": "5432", "status": "running", "cpu": 22, "mem": 640, "uptime": "14d 3h"},
    {"name": "redis-cache",        "image": "redis:7-alpine",                  "port": "6379", "status": "running", "cpu": 3,  "mem": 64,  "uptime": "14d 3h"},
]

KAFKA_TOPICS_SEED = [
    {"name": "attendance.events", "partitions": 3, "msgs": 4821, "rate": 12,  "consumers": ["DashboardSvc", "ReportSvc"]},
    {"name": "finance.payments",  "partitions": 2, "msgs": 1203, "rate": 3,   "consumers": ["DashboardSvc", "ReportSvc", "AlertSvc"]},
    {"name": "inventory.alerts",  "partitions": 2, "msgs": 342,  "rate": 1,   "consumers": ["DashboardSvc", "AlertSvc"]},
    {"name": "hr.leaves",         "partitions": 1, "msgs": 89,   "rate": 0.5, "consumers": ["DashboardSvc", "HRSvc"]},
    {"name": "school.mou",        "partitions": 2, "msgs": 611,  "rate": 2,   "consumers": ["DashboardSvc", "ReportSvc"]},
    {"name": "trainer.session",   "partitions": 3, "msgs": 2104, "rate": 8,   "consumers": ["DashboardSvc", "ReportSvc"]},
    {"name": "marketing.leads",   "partitions": 1, "msgs": 447,  "rate": 1.5, "consumers": ["DashboardSvc", "MarketingSvc"]},
    {"name": "ceo.report",        "partitions": 1, "msgs": 52,   "rate": 0.1, "consumers": ["EmailSvc", "ReportSvc"]},
]

INGESTION_SOURCES = [
    {"name": "School Attendance",     "icon": "🏫", "format": "JSON",    "freq": "Real-time", "producer": "SchoolSvc",    "topic": "attendance.events", "records": 4821, "color": "#2563eb"},
    {"name": "Finance Transactions",  "icon": "💰", "format": "JSON",    "freq": "On event",  "producer": "FinanceSvc",   "topic": "finance.payments",  "records": 1203, "color": "#22d3a5"},
    {"name": "HR & Leaves",           "icon": "👥", "format": "JSON",    "freq": "On submit", "producer": "HRSvc",        "topic": "hr.leaves",         "records": 89,   "color": "#a78bfa"},
    {"name": "Inventory Levels",      "icon": "📦", "format": "JSON",    "freq": "Every 5min","producer": "InventorySvc", "topic": "inventory.alerts",  "records": 342,  "color": "#fbbf24"},
    {"name": "Trainer Sessions",      "icon": "👨‍🏫","format": "JSON",    "freq": "Real-time", "producer": "TrainerSvc",   "topic": "trainer.session",   "records": 2104, "color": "#38bdf8"},
    {"name": "Marketing Leads",       "icon": "📣", "format": "Webhook", "freq": "On event",  "producer": "MarketingSvc", "topic": "marketing.leads",   "records": 447,  "color": "#f87171"},
]

SCHOOLS_SEED = [
    {"name": "Beacon House School",    "city": "Karachi",    "att": 91, "mou": "✓",         "next": "Today 3PM", "status": "green",  "present": 38, "total": 42},
    {"name": "PAF College",            "city": "Islamabad",  "att": 87, "mou": "✓",         "next": "Tomorrow",  "status": "green",  "present": 35, "total": 40},
    {"name": "Karachi Grammar School", "city": "Karachi",    "att": 94, "mou": "⚠ Renewal", "next": "Wed",       "status": "yellow", "present": 41, "total": 44},
    {"name": "Lahore Grammar School",  "city": "Lahore",     "att": 78, "mou": "⏳ Pending", "next": "Fri",       "status": "cyan",   "present": 31, "total": 40},
    {"name": "IBA Karachi",            "city": "Karachi",    "att": 89, "mou": "✓",         "next": "Thu",       "status": "green",  "present": 36, "total": 41},
    {"name": "Aitchison College",      "city": "Lahore",     "att": 0,  "mou": "📄 Draft",  "next": "TBD",       "status": "muted",  "present": 0,  "total": 0},
]

ATTENDANCE_SCENARIOS = [
    {"school": "Beacon House School",    "delta_present": 1,  "trainer": "Fatima Khan"},
    {"school": "PAF College",            "delta_present": 1,  "trainer": "Ahmed Ali"},
    {"school": "Karachi Grammar School", "delta_present": 0,  "trainer": "Ayesha Malik"},
    {"school": "Lahore Grammar School",  "delta_present": -1, "trainer": "Hassan Malik"},
    {"school": "IBA Karachi",            "delta_present": 1,  "trainer": "Zainab Ahmed"},
    {"school": "Beacon House School",    "delta_present": 2,  "trainer": "Ali Raza"},
    {"school": "PAF College",            "delta_present": -1, "trainer": "Sara Khan"},
    {"school": "Lahore Grammar School",  "delta_present": 1,  "trainer": "Hira Nasir"},
]

TRAINERS = [
    {"id": 1,  "name": "Fatima Khan",        "city": "Karachi",    "school": "Beacon House School",    "status": "active",   "rating": 4.8, "sessions": 156, "email": "fatima.khan@roboclub.pk"},
    {"id": 2,  "name": "Ahmed Ali",          "city": "Islamabad",  "school": "PAF College",            "status": "active",   "rating": 4.7, "sessions": 143, "email": "ahmed.ali@roboclub.pk"},
    {"id": 3,  "name": "Ayesha Malik",       "city": "Karachi",    "school": "Karachi Grammar School", "status": "active",   "rating": 4.9, "sessions": 178, "email": "ayesha.malik@roboclub.pk"},
    {"id": 4,  "name": "Hassan Malik",       "city": "Lahore",     "school": "Lahore Grammar School",  "status": "active",   "rating": 4.6, "sessions": 124, "email": "hassan.malik@roboclub.pk"},
    {"id": 5,  "name": "Zainab Ahmed",       "city": "Karachi",    "school": "IBA Karachi",            "status": "active",   "rating": 4.8, "sessions": 165, "email": "zainab.ahmed@roboclub.pk"},
    {"id": 6,  "name": "Muhammad Hassan",    "city": "Lahore",     "school": "Aitchison College",      "status": "inactive", "rating": 4.5, "sessions": 98,  "email": "m.hassan@roboclub.pk"},
    {"id": 7,  "name": "Sara Khan",          "city": "Islamabad",  "school": "PAF College",            "status": "active",   "rating": 4.7, "sessions": 137, "email": "sara.khan@roboclub.pk"},
    {"id": 8,  "name": "Ali Raza",           "city": "Karachi",    "school": "Beacon House School",    "status": "active",   "rating": 4.6, "sessions": 142, "email": "ali.raza@roboclub.pk"},
    {"id": 9,  "name": "Hira Nasir",         "city": "Lahore",     "school": "Lahore Grammar School",  "status": "active",   "rating": 4.8, "sessions": 151, "email": "hira.nasir@roboclub.pk"},
    {"id": 10, "name": "Usman Khan",         "city": "Karachi",    "school": "Karachi Grammar School", "status": "active",   "rating": 4.7, "sessions": 146, "email": "usman.khan@roboclub.pk"},
    {"id": 11, "name": "Iqra Siddiqui",      "city": "Islamabad",  "school": "PAF College",            "status": "active",   "rating": 4.9, "sessions": 168, "email": "iqra.siddiqui@roboclub.pk"},
    {"id": 12, "name": "Bilal Ahmed",        "city": "Lahore",     "school": "Aitchison College",      "status": "active",   "rating": 4.6, "sessions": 135, "email": "bilal.ahmed@roboclub.pk"},
    {"id": 13, "name": "Maryam Hussain",     "city": "Karachi",    "school": "IBA Karachi",            "status": "active",   "rating": 4.8, "sessions": 159, "email": "maryam.hussain@roboclub.pk"},
    {"id": 14, "name": "Tariq Mahmood",      "city": "Lahore",     "school": "Lahore Grammar School",  "status": "active",   "rating": 4.7, "sessions": 148, "email": "tariq.mahmood@roboclub.pk"},
    {"id": 15, "name": "Nida Khan",          "city": "Karachi",    "school": "Beacon House School",    "status": "active",   "rating": 4.9, "sessions": 172, "email": "nida.khan@roboclub.pk"},
    {"id": 16, "name": "Faisal Aziz",        "city": "Islamabad",  "school": "PAF College",            "status": "active",   "rating": 4.6, "sessions": 139, "email": "faisal.aziz@roboclub.pk"},
    {"id": 17, "name": "Amina Malik",        "city": "Lahore",     "school": "Aitchison College",      "status": "active",   "rating": 4.8, "sessions": 154, "email": "amina.malik@roboclub.pk"},
    {"id": 18, "name": "Samir Hussain",      "city": "Karachi",    "school": "Karachi Grammar School", "status": "inactive", "rating": 4.5, "sessions": 112, "email": "samir.hussain@roboclub.pk"},
    {"id": 19, "name": "Leila Shafiq",       "city": "Islamabad",  "school": "PAF College",            "status": "active",   "rating": 4.7, "sessions": 144, "email": "leila.shafiq@roboclub.pk"},
    {"id": 20, "name": "Raees Ahmad",        "city": "Karachi",    "school": "IBA Karachi",            "status": "active",   "rating": 4.8, "sessions": 161, "email": "raees.ahmad@roboclub.pk"},
]

# ─── Mutable runtime state ────────────────────────────────────────────────────

_msg_counts    = {t["name"]: t["msgs"]   for t in KAFKA_TOPICS_SEED}
_cpu_state     = {s["name"]: float(s["cpu"]) for s in DOCKER_SERVICES_SEED}
_tick          = {"val": 0}   # simulates live KPI drift
_schools_state: List[Dict[str, Any]] = []
_sse_queues: List[asyncio.Queue] = []
_recent_events: List[Dict[str, Any]] = []
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def _init_schools_state() -> None:
    global _schools_state
    try:
        schools = store.list_schools()
        if schools:
            _schools_state = schools
            return
    except Exception:
        pass
    _schools_state = [copy.deepcopy(s) for s in SCHOOLS_SEED]
    for s in _schools_state:
        s["updated_at"] = datetime.utcnow().isoformat() + "Z"
        s.setdefault("data_source", "demo")


def _attendance_status(pct: int) -> str:
    if pct <= 0:
        return "muted"
    if pct < 75:
        return "yellow"
    if pct < 85:
        return "cyan"
    return "green"


def _school_by_name(name: str) -> Optional[Dict[str, Any]]:
    for s in _schools_state:
        if s["name"] == name:
            return s
    return None


def _apply_attendance_update(scenario: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db_school = store.get_school_by_name(scenario["school"])
    if db_school and db_school["total"] > 0:
        new_present = max(
            0, min(db_school["total"], db_school["present"] + scenario["delta_present"])
        )
        updated = store.update_school_present(db_school["id"], new_present)
        if updated:
            global _schools_state
            _schools_state = store.list_schools()
            return {
                "school": updated["name"],
                "city": updated["city"],
                "present": updated["present"],
                "total": updated["total"],
                "att": updated["att"],
                "status": updated["status"],
                "trainer": scenario["trainer"],
                "updated_at": updated["updated_at"],
            }
    school = _school_by_name(scenario["school"])
    if not school or school.get("total", 0) <= 0:
        return None
    school["present"] = max(0, min(school["total"], school["present"] + scenario["delta_present"]))
    school["att"] = round(100 * school["present"] / school["total"])
    school["status"] = _attendance_status(school["att"])
    school["updated_at"] = datetime.utcnow().isoformat() + "Z"
    school["trainer"] = scenario["trainer"]
    return {
        "school": school["name"],
        "city": school["city"],
        "present": school["present"],
        "total": school["total"],
        "att": school["att"],
        "status": school["status"],
        "trainer": scenario["trainer"],
        "updated_at": school["updated_at"],
    }


def _maybe_attendance_notification(school: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if school["att"] <= 0 or school["att"] >= 75:
        return None
    ref = f"attendance:{school['name']}"
    return db.create_notification(
        ntype="warn",
        title="Low Attendance Alert",
        body=f"{school['name']} — {school['att']}% ({school['present']}/{school['total']} present)",
        ref_key=ref,
    )


def _broadcast_sse(payload: Dict[str, Any]) -> None:
    for q in list(_sse_queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def _remember_event(event: Dict[str, Any]) -> Dict[str, Any]:
    global _recent_events
    _recent_events = [event, *_recent_events][:40]
    return event


def _run_live_tick() -> Dict[str, Any]:
    """One simulation step — used by SSE locally and polling on Vercel."""
    result: Dict[str, Any] = {"event": None, "attendance": None, "notification": None, "count": None}

    if random.random() < 0.45:
        scenario = random.choice(ATTENDANCE_SCENARIOS)
        update = _apply_attendance_update(scenario)
        if update:
            school = _school_by_name(scenario["school"])
            msg = (
                f"Check-in: {update['present']}/{update['total']} @ "
                f"{scenario['school']} ({update['att']}%)"
            )
            event = _remember_event({
                "topic": "attendance.events",
                "source": "SchoolSvc",
                "msg": msg,
                "type": "warn" if update["att"] < 75 else "info",
                "id": int(time.time() * 1000),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "attendance": update,
            })
            result["event"] = event
            global _schools_state
            _schools_state = store.list_schools()
            result["attendance"] = {
                "event": "attendance",
                "schools": copy.deepcopy(_schools_state),
                "update": update,
            }
            _broadcast_sse(result["attendance"])
            if school:
                notif = _maybe_attendance_notification(school)
                if notif:
                    result["notification"] = notif
                    result["count"] = db.unread_notification_count()
                    _broadcast_sse({
                        "event": "notification",
                        "notification": notif,
                        "count": result["count"],
                    })
        else:
            event = _remember_event({
                **random.choice(EVENT_TEMPLATES),
                "id": int(time.time() * 1000),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
            result["event"] = event
    else:
        event = _remember_event({
            **random.choice(EVENT_TEMPLATES),
            "id": int(time.time() * 1000),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        result["event"] = event

    return result


@app.get("/api/live/tick", tags=["Live"])
def live_tick():
    """Single live update — use for polling when SSE is unavailable (e.g. Vercel)."""
    if not _schools_state:
        _init_schools_state()
    return _run_live_tick()


@app.get("/api/events/recent", tags=["Events"])
def events_recent():
    return {"events": _recent_events}


# ─── SSE: Live event stream ───────────────────────────────────────────────────

@app.get("/api/events/stream", tags=["Events"])
async def event_stream():
    """Server-Sent Events — pipeline events; attendance updates schools live."""
    if IS_SERVERLESS:
        raise HTTPException(
            status_code=501,
            detail="SSE not supported on serverless. Use GET /api/live/tick polling.",
        )

    async def generate():
        while True:
            tick = _run_live_tick()
            if tick["event"]:
                yield f"data: {json.dumps(tick['event'])}\n\n"
            await asyncio.sleep(3.5)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/attendance/live", tags=["Attendance"])
def attendance_live():
    """Current live attendance for all schools."""
    return {"schools": _schools_state, "updated_at": datetime.utcnow().isoformat() + "Z"}


@app.get("/api/attendance/stream", tags=["Attendance"])
async def attendance_stream():
    """SSE — school attendance snapshots whenever check-ins occur."""
    if IS_SERVERLESS:
        raise HTTPException(
            status_code=501,
            detail="SSE not supported on serverless. Use GET /api/attendance/live or /api/live/tick.",
        )

    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    _sse_queues.append(queue)

    async def generate():
        try:
            yield f"data: {json.dumps({'event': 'snapshot', 'schools': _schools_state})}\n\n"
            while True:
                payload = await queue.get()
                if payload.get("event") in ("attendance", "snapshot"):
                    yield f"data: {json.dumps(payload)}\n\n"
        finally:
            if queue in _sse_queues:
                _sse_queues.remove(queue)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/notifications/stream", tags=["Notifications"])
async def notifications_stream():
    """SSE — pushes new notifications and unread count updates."""
    if IS_SERVERLESS:
        raise HTTPException(
            status_code=501,
            detail="SSE not supported on serverless. Poll GET /api/notifications and /api/live/tick.",
        )

    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    _sse_queues.append(queue)

    async def generate():
        try:
            yield f"data: {json.dumps({'event': 'init', 'count': db.unread_notification_count()})}\n\n"
            while True:
                payload = await queue.get()
                if payload.get("event") == "notification":
                    yield f"data: {json.dumps(payload)}\n\n"
        finally:
            if queue in _sse_queues:
                _sse_queues.remove(queue)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ─── Kafka ────────────────────────────────────────────────────────────────────

@app.get("/api/kafka/topics", tags=["Kafka"])
def kafka_topics():
    """Return Kafka topics with live-drifting message counts."""
    for t in KAFKA_TOPICS_SEED:
        _msg_counts[t["name"]] += random.randint(0, max(1, int(t["rate"] * 2)))
    return [
        {**t, "msgs": _msg_counts[t["name"]]}
        for t in KAFKA_TOPICS_SEED
    ]


@app.get("/api/kafka/cluster", tags=["Kafka"])
def kafka_cluster():
    total = sum(_msg_counts.values())
    return {
        "brokers":         "3 / 3",
        "topics":          len(KAFKA_TOPICS_SEED),
        "total_messages":  total,
        "consumer_groups": 5,
        "health":          "healthy",
    }


@app.get("/api/kafka/consumers", tags=["Kafka"])
def kafka_consumers():
    return [
        {"name": svc, "lag": 0, "status": "healthy"}
        for svc in ["DashboardSvc", "ReportSvc", "AlertSvc", "HRSvc", "MarketingSvc"]
    ]


# ─── Docker ───────────────────────────────────────────────────────────────────

@app.get("/api/docker/services", tags=["Docker"])
def docker_services():
    """Container list with slightly drifting CPU values."""
    for name in _cpu_state:
        _cpu_state[name] = max(1.0, min(95.0, _cpu_state[name] + random.uniform(-3, 3)))
    return [
        {**s, "cpu": round(_cpu_state[s["name"]], 1)}
        for s in DOCKER_SERVICES_SEED
    ]


# ─── Notifications ────────────────────────────────────────────────────────────

@app.get("/api/notifications", tags=["Notifications"])
def get_notifications(
    category: Optional[str] = None,
    include_resolved: bool = False,
):
    return db.list_notifications(category, include_resolved)


@app.put("/api/notifications/{notif_id}/read", tags=["Notifications"])
def mark_read(notif_id: int):
    if db.mark_notification_read(notif_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Notification not found")


@app.put("/api/notifications/all/read", tags=["Notifications"])
def mark_all_read():
    count = db.mark_all_notifications_read()
    return {"ok": True, "count": count}


@app.get("/api/notifications/unread-count", tags=["Notifications"])
def unread_count():
    return {"count": db.unread_notification_count()}


@app.put("/api/notifications/{notif_id}/resolve", tags=["Notifications"])
def resolve_notification(notif_id: int):
    if store.resolve_notification(notif_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Notification not found")


@app.put("/api/notifications/{notif_id}/snooze", tags=["Notifications"])
def snooze_notification(notif_id: int, hours: int = 24):
    if store.snooze_notification(notif_id, hours):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Notification not found")


@app.get("/api/notifications/critical", tags=["Notifications"])
def critical_notifications():
    return store.critical_notifications()


@app.get("/api/search", tags=["Search"])
def search(q: str):
    return store.global_search(q)


@app.get("/api/meta/pages", tags=["Meta"])
def meta_pages():
    return store.page_meta()


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/kpis", tags=["Dashboard"])
def dashboard_kpis():
    _tick["val"] += 1
    t = _tick["val"]
    trainers = store.list_trainers()
    active_trainers = sum(1 for tr in trainers if tr["status"] == "active")
    pay = store.payments_summary()
    schools = store.list_schools()
    students = sum(s["total"] for s in schools)
    return {
        "active_schools":    len(schools),
        "students_live":     students + t,
        "trainers_online":   f"{active_trainers}/{len(trainers)}",
        "revenue_apr":       f"₨{(9100000 + t * 5000) // 100000}L",
        "inventory_alerts":  db.count_inventory_alerts(),
        "pending_mous":      sum(1 for s in schools if s.get("mou_status") in ("pending", "renewal")),
        "outstanding_pkr":   pay["outstanding_display"],
        "new_leads":         73,
        "attendance_avg":    store.avg_attendance_today(),
        "overdue_count":     pay["overdue_count"],
    }


@app.get("/api/dashboard/ops", tags=["Dashboard"])
def dashboard_ops():
    pay = store.payments_summary()
    return {
        "attendance_avg": store.avg_attendance_today(),
        "overdue_total_display": f"₨{pay['overdue_total_pkr']:,}",
        "overdue_count": pay["overdue_count"],
        "inventory_alerts": db.count_inventory_alerts(),
    }


@app.get("/api/dashboard/schools", tags=["Dashboard"])
def dashboard_schools():
    return store.list_schools()


# ─── Trainers ─────────────────────────────────────────────────────────────────

@app.get("/api/trainers", tags=["Trainers"])
def get_all_trainers():
    return store.list_trainers()


@app.get("/api/trainers/stats", tags=["Trainers"])
def get_trainers_stats():
    """Get trainer statistics."""
    trainers = store.list_trainers()
    active_trainers = sum(1 for t in trainers if t["status"] == "active")
    inactive_trainers = sum(1 for t in trainers if t["status"] == "inactive")
    avg_rating = sum(t["rating"] for t in trainers) / len(trainers) if trainers else 0
    total_sessions = sum(t["sessions"] for t in trainers)

    return {
        "total_trainers": len(trainers),
        "active_trainers": active_trainers,
        "inactive_trainers": inactive_trainers,
        "average_rating": round(avg_rating, 2),
        "total_sessions_conducted": total_sessions,
        "trainers_by_city": {
            "Karachi": sum(1 for t in trainers if t["city"] == "Karachi"),
            "Lahore": sum(1 for t in trainers if t["city"] == "Lahore"),
            "Islamabad": sum(1 for t in trainers if t["city"] == "Islamabad"),
        },
    }


@app.get("/api/trainers/{trainer_id}", tags=["Trainers"])
def get_trainer(trainer_id: int):
    """Get specific trainer by ID."""
    for trainer in TRAINERS:
        if trainer["id"] == trainer_id:
            return trainer
    raise HTTPException(status_code=404, detail="Trainer not found")


@app.get("/api/trainers/city/{city}", tags=["Trainers"])
def get_trainers_by_city(city: str):
    """Get all trainers in a specific city."""
    return [t for t in TRAINERS if t["city"].lower() == city.lower()]


@app.get("/api/trainers/school/{school_name}", tags=["Trainers"])
def get_trainers_by_school(school_name: str):
    """Get all trainers assigned to a specific school."""
    return [t for t in TRAINERS if school_name.lower() in t["school"].lower()]


@app.get("/api/trainers/status/{status_filter}", tags=["Trainers"])
def get_trainers_by_status(status_filter: str):
    """Get trainers by status (active/inactive)."""
    return [t for t in TRAINERS if t["status"].lower() == status_filter.lower()]


# ─── Inventory (live data) ──────────────────────────────────────────────────────

@app.get("/api/inventory", tags=["Inventory"])
def inventory_list():
    """All stock items with ok / low / critical status."""
    items = db.list_inventory()
    return {
        "items": items,
        "alerts": db.count_inventory_alerts(),
        "summary": {
            "total": len(items),
            "ok": sum(1 for i in items if i["status"] == "ok"),
            "low": sum(1 for i in items if i["status"] == "low"),
            "critical": sum(1 for i in items if i["status"] == "critical"),
        },
    }


@app.get("/api/inventory/{item_id}", tags=["Inventory"])
def inventory_get(item_id: int):
    item = db.get_inventory(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _require_ops(authorization: Optional[str] = Header(None)):
    from auth import parse_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    user = parse_token(authorization[7:])
    if not user or user["role"] not in ("ops",):
        raise HTTPException(403, "Ops role required")
    return user


@app.post("/api/inventory", tags=["Inventory"])
def inventory_create(body: InventoryCreate, _user=Depends(_require_ops)):
    try:
        return db.create_inventory(
            body.sku, body.name, body.quantity, body.threshold, body.unit
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="SKU already exists") from e
        raise


@app.put("/api/inventory/{item_id}", tags=["Inventory"])
def inventory_update(item_id: int, body: InventoryUpdate, _user=Depends(_require_ops)):
    item = db.update_inventory(
        item_id,
        name=body.name,
        quantity=body.quantity,
        threshold=body.threshold,
        unit=body.unit,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/api/inventory/{item_id}/adjust", tags=["Inventory"])
def inventory_adjust(item_id: int, body: InventoryAdjust, _user=Depends(_require_ops)):
    item = db.adjust_inventory(item_id, body.delta)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/api/inventory/sync-alerts", tags=["Inventory"])
def inventory_sync_alerts():
    created = db.sync_inventory_alerts()
    return {"ok": True, "created": created, "alerts": db.count_inventory_alerts()}


# ─── Ingestion ────────────────────────────────────────────────────────────────

@app.get("/api/ingestion/sources", tags=["Ingestion"])
def ingestion_sources():
    return INGESTION_SOURCES


# ─── CEO Report ───────────────────────────────────────────────────────────────

def _ceo_action_items() -> List[str]:
    items = [
        "🔴 Karachi Grammar School — ₨28,00,000 overdue 5 days",
        "📄 MOU renewal due — Karachi Grammar School (7 days)",
        "🤝 Aitchison College — MOU draft pending",
    ]
    for inv in db.list_inventory():
        if inv["status"] in ("low", "critical"):
            icon = "🔴" if inv["status"] == "critical" else "📦"
            items.insert(
                2,
                f"{icon} {inv['name']} — qty {inv['quantity']}/{inv['threshold']} {inv['unit']} — reorder",
            )
    return items


@app.get("/api/ceo/report", tags=["CEO"])
def ceo_report():
    return {
        "subject":    "RoboClub Weekly Ops Digest — Week 20, 2025",
        "from_addr":  "ops@roboclub.pk",
        "to_addr":    "ceo@roboclub.de",
        "generated":  datetime.utcnow().isoformat() + "Z",
        "sections": {
            "business_summary": [
                "5 active schools · 239 students enrolled",
                "Revenue: ₨91,00,000 (Apr) — ↑34% vs March",
                "Net margin: 31% · Expenses: ₨63,00,000",
                "73 marketing leads this month",
            ],
            "action_required": _ceo_action_items(),
            "wins": [
                "PAF College payment received — ₨14,00,000",
                "Fatima Khan onboarded as Islamabad trainer",
                "Instagram followers up 12% — 4,820 total",
                "New lead: Aitchison College, Lahore",
            ],
            "team_update": [
                "All 20 trainers active · Salaries paid ✓",
                "Ahmed Ali leave request pending (May 22)",
                "Hassan Malik annual leave request (Jun 1–5)",
                "Average trainer session rating: 4.7 ⭐",
            ],
        },
        "pipeline_health": {
            "kafka_uptime":       "99.9%",
            "docker_containers":  "12/12 ✓",
            "events_per_day":     "~9,200",
            "data_freshness":     "< 2s",
        },
        "schedule": [
            {"freq": "Daily",   "time": "8:00 AM PKT",      "content": "Attendance + payments"},
            {"freq": "Weekly",  "time": "Mon 9:00 AM PKT",  "content": "Full ops digest"},
            {"freq": "Monthly", "time": "1st of month",     "content": "P&L + growth report"},
        ],
    }


@app.post("/api/ceo/send", tags=["CEO"])
async def send_ceo_report():
    await asyncio.sleep(2)          # simulate email dispatch
    return {"sent": True, "timestamp": datetime.utcnow().isoformat() + "Z", "to": "ceo@roboclub.de"}


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "service": "roboclub-api-pakistan",
        "database": db.DB_PATH,
        "inventory_alerts": db.count_inventory_alerts(),
        "ts": datetime.utcnow().isoformat(),
    }
