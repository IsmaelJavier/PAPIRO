from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api, auth
from app.db import Base
from app.models import Job, MembershipRole, Organization, OrganizationMembership, User, UserRole


def test_entity_manager_cannot_enqueue_search_but_can_read_org_job(monkeypatch):
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
    monkeypatch.setattr(auth.settings, "auth_secret_key", "test-only-secret-key-at-least-32-characters")

    manager = User(
        email="manager@example.test",
        password_hash="unused",
        global_role=UserRole.investigator,
        is_active=True,
    )
    owner = User(
        email="owner@example.test",
        password_hash="unused",
        global_role=UserRole.investigator,
        is_active=True,
    )
    session.add_all([manager, owner])
    session.flush()
    org = Organization(name="Org", slug="org", created_by_user_id=manager.id)
    session.add(org)
    session.flush()
    session.add(OrganizationMembership(
        organization_id=org.id,
        user_id=manager.id,
        role=MembershipRole.entity,
        is_active=True,
    ))
    job = Job(input_value="Alice", owner_user_id=owner.id, organization_id=org.id)
    session.add(job)
    session.flush()
    job_id = job.id
    token, _ = auth.create_access_token(manager)

    app = FastAPI()
    app.include_router(auth.auth_router)
    app.include_router(api.router)
    client = TestClient(app)
    calls = []
    monkeypatch.setattr(
        api.process_manual_person_name_search,
        "delay",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    headers = {"Authorization": f"Bearer {token}"}
    read_response = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    denied_response = client.post(
        f"/api/v1/jobs/{job_id}/search/name",
        headers=headers,
        json={"query": "Alice"},
    )

    assert read_response.status_code == 200
    assert denied_response.status_code == 403
    assert calls == []

    client.close()
    session.close()
    engine.dispose()
