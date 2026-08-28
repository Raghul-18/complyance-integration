import importlib
import json
import os
import sys
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

    with TestClient(fresh_app) as c:
        yield c


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def load_sample(name: str) -> dict:
    path = SAMPLES / name if name.startswith("valid") else SAMPLES / "invalid-invoices" / name
    with open(path) as f:
        return json.load(f)
