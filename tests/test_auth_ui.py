from fastapi.testclient import TestClient

from app.main import app


def test_ui_landing_is_only_for_login_and_registration():
    with TestClient(app) as client:
        response = client.get("/ui")
        assert response.status_code == 200
        assert "loginForm" in response.text
        assert "registerForm" in response.text
        assert "/auth/register" in response.text
        assert "location.replace('/ui/workspace')" in response.text
        assert 'id="investigationList"' not in response.text


def test_workspace_has_own_dashboard_and_optional_investigation_creation():
    with TestClient(app) as client:
        response = client.get("/ui/workspace")
        assert response.status_code == 200
        assert 'id="investigationList"' in response.text
        assert 'id="totalInvestigations"' in response.text
        assert 'id="newInvestigationButton"' in response.text
        assert 'id="investigationForm" hidden' in response.text
        assert "no es necesario hacerlo para entrar" in response.text
        assert 'id="logoutModal"' in response.text
        assert 'id="investigationName"' in response.text
        assert 'id="investigationNotes"' in response.text
        assert "request('/investigations'" in response.text
        assert "request('/ingest/name'" not in response.text


def test_investigation_ui_has_autosave_exit_and_logout_confirmation():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        assert response.status_code == 200
        assert "Kami-no-Eye · Espacio de investigación" in response.text
        assert 'id="saveStatus"' in response.text
        assert 'id="saveExitBtn"' in response.text
        assert 'id="sessionModal"' in response.text
        assert 'id="saveAndLogout"' in response.text
        assert 'id="logoutWithoutViewSave"' in response.text
        assert 'id="cancelSessionExit"' in response.text
        assert 'id="leaveWithoutSaving"' in response.text
        assert 'id="saveAndLeave"' in response.text
        assert "DOMContentLoaded" in response.text
        assert "Vista guardada automáticamente" in response.text
        assert "/checkpoint" in response.text
        assert "/checkpoint/restore" in response.text
        assert "/checkpoint/commit" in response.text
        assert "revierte los cambios de esta sesión" in response.text
        assert "rememberLocalBaseline" in response.text
