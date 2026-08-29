import importlib
import json
import os
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = REPO_ROOT / "samples"
API_KEY = "test-key-123"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("TRAINING_API_KEY", API_KEY)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("PROCESSING_DELAY_SECONDS", "0.05")

    # Reload modules that cache settings at import time.
    for mod_name in ["src.config", "src.persistence", "src.main"]:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
        else:
            importlib.import_module(mod_name)

    from src.main import app as fresh_app

    # src.main._finalize_processing runs on a fire-and-forget daemon
    # thread. Because this fixture reload()s src.config/src.persistence
    # in place for every test, a thread from THIS test that's still
    # sleeping when the NEXT test's client fixture runs will pick up the
    # next test's reloaded `settings` (module globals are looked up
    # dynamically, and reload() mutates the same module object rather
    # than replacing it) -- pointing it at a DB path that hasn't been
    # init_db()'d yet, or no longer exists. That surfaces as
    # PytestUnhandledThreadExceptionWarning: sqlite3.OperationalError:
    # no such table: documents, attributed to whichever test happens to
    # be running when the stale thread wakes up, not the test that
    # actually started it. Track and join any thread spawned during this
    # test before tearing down, so each test's background work finishes
    # against ITS OWN settings before the next test reloads them.
    baseline_threads = set(threading.enumerate())

    with TestClient(fresh_app) as c:
        yield c

    for t in threading.enumerate():
        if t not in baseline_threads and t.is_alive():
            t.join(timeout=5)


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def load_sample(name: str) -> dict:
    path = SAMPLES / name if name.startswith("valid") else SAMPLES / "invalid-invoices" / name
    with open(path) as f:
        return json.load(f)