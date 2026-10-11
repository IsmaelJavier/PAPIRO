from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import auth
from app.db import Base
from app.models import (
    Job, MembershipRole, Organization, OrganizationMembership, User, UserRole,
)


@pytest.fixture
def auth_db(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    @contextmanager
    def fake_db_session():
        yield session

    monkeypatch.setattr(auth, "db_session", fake_db_session)
    yield session
    session.close()
    engine.dispose()


def _user(session, email, role=UserRole.investigator):
    user = User(email=email, password_hash="not-used", global_role=role, is_active=True)
    session.add(user)
    session.flush()
    return user


def _request(path, method="GET", path_params=None):
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "path_params": path_params or {},
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
    })


def test_owner_can_read_and_modify_own_investigation(auth_db):
    owner = _user(auth_db, "owner@example.test")
    job = Job(input_value="Alice", owner_user_id=owner.id, organization_id=None)
    auth_db.add(job)
    auth_db.flush()

    auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}", path_params={"job_id": job.id}), owner)
    auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}/entities", "POST", {"job_id": job.id}), owner)


def test_other_investigator_cannot_read_or_modify_investigation(auth_db):
    owner = _user(auth_db, "owner@example.test")
    other = _user(auth_db, "other@example.test")
    job = Job(input_value="Alice", owner_user_id=owner.id, organization_id=None)
    auth_db.add(job)
    auth_db.flush()

    with pytest.raises(HTTPException) as exc:
        auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}", path_params={"job_id": job.id}), other)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}/search/name", "POST", {"job_id": job.id}), other)
    assert exc.value.status_code == 404


def test_entity_manager_can_read_but_cannot_modify_org_investigation(auth_db):
    manager = _user(auth_db, "manager@example.test")
    investigator = _user(auth_db, "investigator@example.test")
    org = Organization(name="Org", slug="org", created_by_user_id=manager.id)
    auth_db.add(org)
    auth_db.flush()
    auth_db.add(OrganizationMembership(
        organization_id=org.id, user_id=manager.id, role=MembershipRole.entity, is_active=True
    ))
    job = Job(input_value="Alice", owner_user_id=investigator.id, organization_id=org.id)
    auth_db.add(job)
    auth_db.flush()

    auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}", path_params={"job_id": job.id}), manager)
    with pytest.raises(HTTPException) as exc:
        auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}/search/name", "POST", {"job_id": job.id}), manager)
    assert exc.value.status_code == 403


def test_superuser_can_access_other_users_investigation(auth_db):
    owner = _user(auth_db, "owner@example.test")
    admin = _user(auth_db, "admin@example.test", UserRole.superuser)
    job = Job(input_value="Alice", owner_user_id=owner.id, organization_id=None)
    auth_db.add(job)
    auth_db.flush()

    auth.authorize_api_request(_request(f"/api/v1/jobs/{job.id}", path_params={"job_id": job.id}), admin)
