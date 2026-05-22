"""
Build static HTML for Vercel from Flask/Jinja templates.
API calls use same origin (empty api_url).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "frontend" / "templates"
PUBLIC = ROOT / "public"

NAV = [
    {"id": "pipeline", "label": "Pipeline", "icon": "⚡"},
    {"id": "kafka", "label": "Kafka", "icon": "🌊"},
    {"id": "docker", "label": "Docker", "icon": "🐳"},
    {"id": "ingestion", "label": "Ingestion", "icon": "🔄"},
    {"id": "dashboard", "label": "Dashboard", "icon": "📊"},
    {"id": "attendance", "label": "Attendance", "icon": "🏫"},
    {"id": "inventory", "label": "Inventory", "icon": "📦"},
    {"id": "trainers", "label": "Trainers", "icon": "👨‍🏫"},
    {"id": "ceo", "label": "CEO Report", "icon": "🇩🇪"},
    {"id": "notifications", "label": "Alerts", "icon": "🔔"},
]

PAGES = [
    ("pipeline", "pipeline.html"),
    ("kafka", "kafka.html"),
    ("docker", "docker.html"),
    ("ingestion", "ingestion.html"),
    ("dashboard", "dashboard.html"),
    ("attendance", "attendance.html"),
    ("inventory", "inventory.html"),
    ("trainers", "trainers.html"),
    ("ceo", "ceo.html"),
    ("notifications", "notifications.html"),
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
        "use_polling": True,
    }

    for page_id, template_name in PAGES:
        tpl = env.get_template(template_name)
        html = tpl.render(**ctx_base, current_page=page_id)
        out = PUBLIC / template_name
        out.write_text(html, encoding="utf-8")
        print(f"  built {out.name}")

    tpl = env.get_template("404.html")
    (PUBLIC / "404.html").write_text(
        tpl.render(**ctx_base, current_page=""),
        encoding="utf-8",
    )

    # Default entry
    shutil.copy(PUBLIC / "pipeline.html", PUBLIC / "index.html")
    print(f"Done — {len(list(PUBLIC.glob('*.html')))} files in public/")


if __name__ == "__main__":
    main()
