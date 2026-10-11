from fastapi.testclient import TestClient

from app.main import app


def test_ui_landing_exposes_login_register_and_personal_investigation_flow():
    with TestClient(app) as client:
        response = client.get("/ui")
        assert response.status_code == 200
        assert "loginForm" in response.text
        assert "registerForm" in response.text
        assert "/auth/register" in response.text
        assert "/ingest/name" in response.text


def test_investigation_ui_still_serves_graph_workspace():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        assert response.status_code == 200
        assert "Kami-no-Eye · Espacio de investigación" in response.text
        assert 'id="loginModal"' in response.text
        assert 'id="registerForm"' in response.text
