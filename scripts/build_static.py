"""
Build static HTML for Vercel from Flask/Jinja templates.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "frontend" / "templates"
PUBLIC = ROOT / "public"

OPS_NAV = [
    {"id": "dashboard", "label": "Dashboard", "icon": "📊"},
    {"id": "attendance", "label": "Attendance", "icon": "🏫"},
    {"id": "checkin", "label": "Check-in", "icon": "✓"},
    {"id": "payments", "label": "Payments", "icon": "💰"},
    {"id": "inventory", "label": "Inventory", "icon": "📦"},
    {"id": "trainers", "label": "Trainers", "icon": "👨‍🏫"},
    {"id": "notifications", "label": "Alerts", "icon": "🔔"},
    {"id": "ceo", "label": "CEO Report", "icon": "🇩🇪"},
    {"id": "admin", "label": "Admin", "icon": "⚙"},
]
DEMO_NAV = [
    {"id": "pipeline", "label": "Pipeline", "icon": "⚡"},
    {"id": "kafka", "label": "Kafka", "icon": "🌊"},
    {"id": "docker", "label": "Docker", "icon": "🐳"},
    {"id": "ingestion", "label": "Ingestion", "icon": "🔄"},
]
NAV = OPS_NAV + DEMO_NAV

PAGES = [
    ("pipeline", "pipeline.html"),
    ("kafka", "kafka.html"),
    ("docker", "docker.html"),
    ("ingestion", "ingestion.html"),
    ("dashboard", "dashboard.html"),
    ("attendance", "attendance.html"),
    ("checkin", "checkin.html"),
    ("school", "school.html"),
    ("payments", "payments.html"),
    ("inventory", "inventory.html"),
    ("trainers", "trainers.html"),
    ("ceo", "ceo.html"),
    ("notifications", "notifications.html"),
    ("login", "login.html"),
    ("admin", "admin.html"),
]


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    ctx_base = {
        "api_url": "",
        "nav": NAV,
        "ops_nav": OPS_NAV,
        "demo_nav": DEMO_NAV,
        "use_polling": True,
    }

    for page_id, template_name in PAGES:
        tpl = env.get_template(template_name)
        (PUBLIC / template_name).write_text(
            tpl.render(**ctx_base, current_page=page_id),
            encoding="utf-8",
        )
        print(f"  built {template_name}")

    (PUBLIC / "404.html").write_text(
        env.get_template("404.html").render(**ctx_base, current_page=""),
        encoding="utf-8",
    )
    shutil.copy(PUBLIC / "pipeline.html", PUBLIC / "index.html")

    js_dir = PUBLIC / "js"
    js_dir.mkdir(exist_ok=True)
    for f in (ROOT / "frontend" / "static").glob("*.js"):
        shutil.copy(f, js_dir / f.name)

    print(f"Done — {len(list(PUBLIC.glob('*.html')))} HTML files")


if __name__ == "__main__":
    main()
