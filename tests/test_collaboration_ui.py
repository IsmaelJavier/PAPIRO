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
    assert "const isReadOnly=await window.detectReadOnlySession();" in html
    assert "if(!isReadOnly)await beginInvestigationEditingSession();" in html
    # Exit/logout must bypass server-side commit/restore for read-only sessions.
    assert "if(readOnlySession||!checkpointReady){restoreLocalBaseline();location.href='/ui/workspace';return;}" in html
    assert "if(readOnlySession||!checkpointReady){restoreLocalBaseline();localStorage.removeItem(TOKEN_KEY);location.replace('/ui');return;}" in html
    # Editing remains unavailable in the UI; server-side authorization remains authoritative.
    assert "activateReadOnlyMode" in html
    assert "assessFinding|assessRelationship|assessCorrelation|saveEntity|saveRelationship|openEntityEdit|openRelationshipEdit|attachSelectedFindingsToEntity" in html
    from pathlib import Path
    auth_source = (Path(__file__).resolve().parents[1] / "app" / "auth.py").read_text(encoding="utf-8")
    assert "This shared copy does not grant editing permission" in auth_source


def test_entity_organization_requires_administrative_provisioning(monkeypatch):
    from contextlib import contextmanager
    from fastapi import HTTPException, Request
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import auth
    from app.db import Base
    from app.models import User, UserRole

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    investigator = User(
        email="investigator@example.com",
        password_hash="test",
        global_role=UserRole.investigator,
    )
    superuser = User(
        email="admin@example.com",
        password_hash="test",
        global_role=UserRole.superuser,
    )
    session.add_all([investigator, superuser])
    session.flush()

    @contextmanager
    def fake_db_session():
        yield session

    monkeypatch.setattr(auth, "db_session", fake_db_session)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/organizations",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
        "path_params": {},
        "root_path": "",
    }
    try:
        for actor in (investigator, superuser):
            request = Request(dict(scope))
            try:
                auth.authorize_api_request(request, actor)
                assert False, "Legacy organization creation must be forbidden for every role"
            except HTTPException as error:
                assert error.status_code == 403
                assert "verified administrative provisioning" in error.detail
    finally:
        session.close()
        engine.dispose()


def test_administrative_entity_provisioning_binds_verified_manager_and_identifier(monkeypatch):
    from contextlib import contextmanager
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import auth
    from app.db import Base
    from app.models import Organization, OrganizationMembership, MembershipRole, User, UserRole

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    manager = User(
        email="manager@institution.example",
        password_hash="test",
        global_role=UserRole.investigator,
    )
    session.add(manager)
    session.flush()

    @contextmanager
    def fake_db_session():
        yield session

    monkeypatch.setattr(auth, "db_session", fake_db_session)
    payload = auth.AdminOrganizationCreateRequest(
        name="Instituto de Investigación",
        slug="instituto-investigacion-001",
        manager_email="manager@institution.example",
    )
    result = auth.admin_create_organization(payload)
    organization = session.scalar(
        select(Organization).where(Organization.slug == "instituto-investigacion-001")
    )
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == manager.id,
        )
    )
    assert result["entity_identifier"] == "instituto-investigacion-001"
    assert result["manager_email"] == manager.email
    assert membership is not None
    assert membership.role == MembershipRole.entity
    session.close()
    engine.dispose()


def test_entity_provisioning_is_admin_only_and_exposed_in_admin_workspace():
    from app.main import app

    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/api/v1/admin/organizations"
        and "POST" in (getattr(route, "methods", None) or set())
    )
    assert route is not None
    with TestClient(app) as client:
        login = client.get("/ui")
        workspace = client.get("/ui/workspace")
    assert login.status_code == 200
    assert 'value="entity"' not in login.text
    assert workspace.status_code == 200
    assert 'id="adminCreateOrganizationForm"' in workspace.text
    assert 'id="adminOrganizationIdentifier"' in workspace.text
    assert 'id="adminOrganizationEmail"' in workspace.text
    assert "/admin/organizations" in workspace.text


def test_organization_scoped_investigation_creation_is_available_to_members():
    from app.main import app

    routes = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/api/v1/organizations", "GET") in routes
    assert ("/api/v1/investigations", "POST") in routes
    with TestClient(app) as client:
        response = client.get("/ui/workspace")
    assert response.status_code == 200
    assert 'id="investigationOrganization"' in response.text
    assert "loadInvestigationOrganizations" in response.text
    assert "organization_id" in response.text
