import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["DATA_DIR"] = os.path.join(os.path.dirname(__file__), "_test_data")

import database as db
import bundles
import store
from auth import hash_password, verify_password


def setup_module():
    import shutil
    if os.path.isdir(os.environ["DATA_DIR"]):
        shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
    db.init_db()


def test_auth_password():
    h = hash_password("test123")
    assert verify_password("test123", h)


def test_bundle_home():
    b = bundles.bundle_home()
    assert "kpis" in b and "schools" in b and "ops" in b


def test_attendance_session():
    schools = store.list_schools()
    session = store.create_attendance_session(schools[0]["id"], 1, 30, 40)
    assert session["att"] == 75


def test_payment_create_and_paid():
    schools = store.list_schools()
    p = store.create_payment(schools[0]["id"], 500000, "2099-01-01", "Test")
    assert p["status"] == "pending"
    assert store.mark_payment_paid(p["id"]) is True


def test_attendance_csv():
    schools = store.list_schools()
    csv = store.attendance_export_csv(schools[0]["id"])
    assert "school,date" in csv


def test_notifications_paginated():
    items, total = store.list_notifications_paginated(limit=10)
    assert total >= 0 and isinstance(items, list)


def test_ceo_live():
    r = store.ceo_report_live()
    assert "sections" in r and r["pipeline_health"]["data_source"] == "live"
