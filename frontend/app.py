"""
RoboClub Data Pipeline – Flask Frontend
"""

import os
from flask import Flask, render_template, abort

app = Flask(__name__)
API_URL = os.getenv("API_URL", "http://localhost:8000")

VALID_PAGES = [
    "pipeline", "kafka", "docker", "ingestion",
    "dashboard", "attendance", "checkin", "school", "payments", "admin",
    "inventory", "trainers", "ceo", "notifications", "login",
]

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


def _ctx(page: str):
    return dict(
        api_url=API_URL,
        nav=NAV,
        ops_nav=OPS_NAV,
        demo_nav=DEMO_NAV,
        current_page=page,
        use_polling=False,
    )


@app.route("/")
def index():
    return render_template("pipeline.html", **_ctx("pipeline"))


@app.route("/<page>")
def page_view(page):
    if page not in VALID_PAGES:
        abort(404)
    return render_template(f"{page}.html", **_ctx(page))


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", **_ctx("")), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
