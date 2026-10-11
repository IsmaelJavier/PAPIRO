from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.db import Base
from app.models import User, UserRole


def test_register_creates_investigator_and_returns_access_token(monkeypatch):
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
    monkeypatch.setattr(auth.settings, "auth_secret_key", "test-only-secret-key-at-least-32-characters")
    app = FastAPI()
    app.include_router(auth.auth_router)
    client = TestClient(app)

    response = client.post("/api/v1/auth/register", json={
        "email": "New.Investigator@example.test",
        "password": "a-strong-password-123",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    user = session.query(User).one()
    assert user.email == "new.investigator@example.test"
    assert user.global_role == UserRole.investigator
    assert user.password_hash != "a-strong-password-123"

    duplicate = client.post("/api/v1/auth/register", json={
        "email": "new.investigator@example.test",
        "password": "another-strong-password-123",
    })
    assert duplicate.status_code == 409

    short_password = client.post("/api/v1/auth/register", json={
        "email": "short@example.test",
        "password": "short",
    })
    assert short_password.status_code == 422

    client.close()
    session.close()
    engine.dispose()
