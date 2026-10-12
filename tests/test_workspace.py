from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api, auth
from app.db import Base
from app.models import Job, User, UserRole


def test_workspace_lists_only_investigations_owned_by_current_user(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    @contextmanager
    def fake_db_session():
        yield session

    monkeypatch.setattr(auth, "db_session", fake_db_session)
    monkeypatch.setattr(api, "db_session", fake_db_session)
    monkeypatch.setattr(
        auth.settings,
        "auth_secret_key",
        "test-only-secret-key-at-least-32-characters",
    )

    owner = User(
        email="owner@example.test",
        password_hash="unused",
        global_role=UserRole.investigator,
        is_active=True,
    )
    other = User(
        email="other@example.test",
        password_hash="unused",
        global_role=UserRole.investigator,
        is_active=True,
    )
    session.add_all([owner, other])
    session.flush()
    owned_job = Job(input_value="Investigación propia", owner_user_id=owner.id)
    other_job = Job(input_value="Investigación ajena", owner_user_id=other.id)
    session.add_all([owned_job, other_job])
    session.flush()
    owned_job_id = owned_job.id
    token, _ = auth.create_access_token(owner)

    app = FastAPI()
    app.include_router(auth.auth_router)
    app.include_router(api.router)
    client = TestClient(app)

    response = client.get(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [owned_job_id]
    assert response.json()[0]["input_value"] == "Investigación propia"
    assert client.get("/api/v1/jobs").status_code == 401

    client.close()
    session.close()
    engine.dispose()
