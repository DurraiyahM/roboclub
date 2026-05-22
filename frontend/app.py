"""
RoboClub Data Pipeline – Flask Frontend
Runs on: http://localhost:5000
"""

import os
from flask import Flask, render_template, abort

app = Flask(__name__)

# The FastAPI backend URL — override via env in Docker
API_URL = os.getenv("API_URL", "http://localhost:8000")

VALID_PAGES = [
    "pipeline", "kafka", "docker", "ingestion", "dashboard", "attendance",
    "checkin", "school", "payments", "inventory", "trainers", "ceo",
    "notifications", "login",
]

NAV = [
    {"id": "pipeline",      "label": "Pipeline",    "icon": "⚡"},
    {"id": "kafka",         "label": "Kafka",       "icon": "🌊"},
    {"id": "docker",        "label": "Docker",      "icon": "🐳"},
    {"id": "ingestion",     "label": "Ingestion",   "icon": "🔄"},
    {"id": "dashboard",     "label": "Dashboard",   "icon": "📊"},
    {"id": "attendance",    "label": "Attendance",  "icon": "🏫"},
    {"id": "checkin",       "label": "Check-in",    "icon": "✓"},
    {"id": "payments",      "label": "Payments",    "icon": "💰"},
    {"id": "inventory",     "label": "Inventory",   "icon": "📦"},
    {"id": "trainers",      "label": "Trainers",    "icon": "👨‍🏫"},
    {"id": "ceo",           "label": "CEO Report",  "icon": "🇩🇪"},
    {"id": "notifications", "label": "Alerts",      "icon": "🔔"},
]


@app.route("/")
def index():
    return render_template(
        "pipeline.html", api_url=API_URL, nav=NAV, current_page="pipeline", use_polling=False
    )


@app.route("/<page>")
def page_view(page):
    if page not in VALID_PAGES:
        abort(404)
    return render_template(
        f"{page}.html", api_url=API_URL, nav=NAV, current_page=page, use_polling=False
    )


@app.errorhandler(404)
def not_found(e):
    return render_template(
        "404.html", api_url=API_URL, nav=NAV, current_page="", use_polling=False
    ), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
