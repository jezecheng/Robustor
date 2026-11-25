import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="mb-test-"))
os.environ.setdefault("RB_DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("RB_DB_PATH", str(_TMP / "data" / "app.db"))

import pytest  # noqa: E402


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
