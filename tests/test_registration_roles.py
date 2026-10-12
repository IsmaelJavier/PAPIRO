from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager

from app import auth
from app.db import Base
from app.models import User, UserRole


def test_registration_accepts_public_role_but_never_admin(monkeypatch):
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

    public = client.post("/api/v1/auth/register", json={
        "email": "public@example.com",
        "password": "a-strong-password-123",
        "global_role": "user",
    })
    assert public.status_code == 201
    assert session.query(User).filter_by(email="public@example.com").one().global_role == UserRole.user

    admin = client.post("/api/v1/auth/register", json={
        "email": "admin-attempt@example.com",
        "password": "a-strong-password-123",
        "global_role": "superuser",
    })
    assert admin.status_code == 422
    assert session.query(User).filter_by(email="admin-attempt@example.com").first() is None

    client.close()
    session.close()
    engine.dispose()
