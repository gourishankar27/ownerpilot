import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("RFQ_AUTH_SECRET", secrets.token_hex(32))
os.environ.setdefault("RFQ_REDIS_URL", "redis://localhost:6380/0")


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("RFQ_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RFQ_TEST_DATABASE_URL to a disposable PostgreSQL database.")
    from urllib.parse import urlparse

    if not any(word in urlparse(url).path.lower() for word in ("test", "validation")):
        pytest.fail(
            "Integration suite requires a disposable database named test or validation."
        )
    os.environ["DATABASE_URL"] = url
    from api.config import get_settings

    get_settings.cache_clear()
    from api.rfq.db import connection, migrate
    from api.services.demo_data import ensure_operational_schema

    with connection() as conn:
        ensure_operational_schema(conn.cursor())
        conn.execute(
            "create table if not exists workspace_members(id uuid primary key default gen_random_uuid(),workspace_id uuid not null references business_workspaces(id),user_id text not null,role varchar(32) not null,created_at timestamptz not null default now())"
        )
    migrate()
    yield url


@pytest.fixture
def api(database, tmp_path, monkeypatch):
    from api.rfq.config import settings

    monkeypatch.setenv("RFQ_STORAGE_ROOT", str(tmp_path))
    settings.cache_clear()
    from api.main import app
    from api.rfq.db import connection

    workspace = str(uuid4())
    other = str(uuid4())
    user = "test-" + str(uuid4())
    with connection() as conn:
        for identifier in (workspace, other):
            conn.execute(
                "insert into business_workspaces(id,name,slug) values(%s,%s,%s)",
                (identifier, "Synthetic test workspace", identifier),
            )
        conn.execute(
            "insert into workspace_members(workspace_id,user_id,role) values(%s,%s,'owner')",
            (workspace, user),
        )
    from api.rfq.worker import process

    monkeypatch.setattr(process, "apply_async", lambda **kwargs: None)
    with TestClient(app) as client:
        yield client, workspace, other, user
    settings.cache_clear()


def authorization(method, path, workspace, user, expired=False, age=0):
    import base64
    import hashlib
    import hmac
    import json
    import time

    now = int(time.time()) - 1000 if expired else int(time.time()) - age
    claims = {
        "sub": user,
        "workspace": workspace,
        "iat": now,
        "exp": now + 60,
        "method": method,
        "path": path,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    signature = hmac.new(
        os.environ["RFQ_AUTH_SECRET"].encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return {"Authorization": "Bearer " + payload + "." + signature}
