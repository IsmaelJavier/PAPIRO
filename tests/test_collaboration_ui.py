from fastapi.testclient import TestClient

from app.main import app


def test_registration_offers_non_admin_roles_and_preserves_public_role():
    with TestClient(app) as client:
        response = client.get("/ui")
    assert response.status_code == 200
    assert 'id="registerRole"' in response.text
    assert 'value="investigator"' in response.text
    assert 'value="user"' in response.text
    assert 'value="superuser"' not in response.text


def test_investigation_workspace_exposes_share_and_merge_controls():
    with TestClient(app) as client:
        response = client.get("/ui/job/example")
    assert response.status_code == 200
    assert 'id="shareInvestigationBtn"' in response.text
    assert 'id="mergeInvestigationBtn"' in response.text
    assert 'id="sharePermission"' in response.text
    assert "/shares/" in response.text

def test_collaboration_and_deletion_routes_are_registered():
    from app.main import app

    routes = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/api/v1/jobs/{job_id}", "DELETE") in routes
    assert ("/api/v1/jobs/{job_id}/shares", "POST") in routes
    assert ("/api/v1/jobs/{job_id}/shares/{share_id}/merge", "POST") in routes
    assert ("/api/v1/shares/{share_id}/comments", "POST") in routes

def test_sharing_creates_an_independent_copy(monkeypatch):
    from contextlib import contextmanager
    from fastapi import FastAPI, Request
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import api
    from app.db import Base
    from app.models import InvestigationShare, Job, JobStatus, User, UserRole

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    owner = User(email="owner@example.com", password_hash="test", global_role=UserRole.investigator)
    collaborator = User(email="collaborator@example.com", password_hash="test", global_role=UserRole.investigator)
    session.add_all([owner, collaborator])
    session.flush()
    original = Job(
        input_value="Example investigation",
        investigation_title="Example investigation",
        input_type="investigation",
        status=JobStatus.draft,
        owner_user_id=owner.id,
    )
    session.add(original)
    session.flush()
    original_id = original.id

    @contextmanager
    def fake_db_session():
        yield session

    def fake_auth(request: Request):
        request.state.current_user_id = owner.id

    monkeypatch.setattr(api, "db_session", fake_db_session)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.authorize_api_request] = fake_auth
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/jobs/{original_id}/shares",
            json={"email": "collaborator@example.com", "permission": "edit"},
        )
    assert response.status_code == 201, response.text
    share = session.scalar(select(InvestigationShare))
    assert share is not None
    assert share.original_job_id == original_id
    assert share.shared_job_id != original_id
    assert share.permission == "edit"
    copy = session.get(Job, share.shared_job_id)
    assert copy is not None
    assert copy.owner_user_id == collaborator.id
    assert session.get(Job, original_id).owner_user_id == owner.id

    session.close()
    engine.dispose()

def test_read_only_shared_copy_can_exit_without_checkpoint_or_restore():
    with TestClient(app) as client:
        response = client.get("/ui/job/example")
    assert response.status_code == 200
    html = response.text
    # A read-only copy must be detected before opening an editing checkpoint.
    assert "const isReadOnly=await detectReadOnlySession();" in html
    assert "if(!isReadOnly)await beginInvestigationEditingSession();" in html
    # Exit/logout must bypass server-side commit/restore for read-only sessions.
    assert "if(readOnlySession||!checkpointReady){restoreLocalBaseline();location.href='/ui/workspace';return;}" in html
    assert "if(readOnlySession||!checkpointReady){restoreLocalBaseline();localStorage.removeItem(TOKEN_KEY);location.replace('/ui');return;}" in html
    # Editing remains unavailable in the UI; server-side authorization remains authoritative.
    assert "activateReadOnlyMode" in html
    assert "This shared copy does not grant editing permission" not in html
