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
