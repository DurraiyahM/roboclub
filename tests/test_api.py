import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["DATA_DIR"] = os.path.join(os.path.dirname(__file__), "_test_data")

import database as db  # noqa: E402
import store  # noqa: E402
from auth import create_token, hash_password, verify_password  # noqa: E402


def setup_module():
    if os.path.isdir(os.environ["DATA_DIR"]):
        import shutil
        shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
    db.init_db()


def test_auth_password():
    h = hash_password("test123")
    assert verify_password("test123", h)
    assert not verify_password("wrong", h)


def test_schools_seeded():
    schools = store.list_schools()
    assert len(schools) >= 6
    assert schools[0]["data_source"] == "live"


def test_attendance_session():
    schools = store.list_schools()
    s = schools[0]
    session = store.create_attendance_session(s["id"], 1, 30, 40)
    assert session["att"] == 75
    updated = store.get_school(s["id"])
    assert updated["present"] == 30


def test_payments_summary():
    summary = store.payments_summary()
    assert "outstanding_display" in summary


def test_search():
    r = store.global_search("beacon")
    assert len(r["schools"]) >= 1


def test_notification_resolve():
    n = db.create_notification(
        ntype="info", title="T", body="B", category="general", ref_key="test:1"
    )
    assert store.resolve_notification(n["id"])
