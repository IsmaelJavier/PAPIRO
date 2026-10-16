from fastapi.testclient import TestClient

from app.main import app


def test_ui_landing_is_only_for_login_and_registration():
    with TestClient(app) as client:
        response = client.get("/ui")
        assert response.status_code == 200
        assert "loginForm" in response.text
        assert '<html lang="en-US">' in response.text
        assert "<title>PAPIRO · Sign in</title>" in response.text
        assert 'property="og:title" content="PAPIRO"' in response.text
        assert '<strong class="brand">PAPIRO</strong>' in response.text
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
        assert "Creating an investigation is optional." in response.text
        assert 'id="logoutModal"' in response.text
        assert 'id="investigationName"' in response.text
        assert 'id="investigationNotes"' in response.text
        assert "request('/investigations'" in response.text
        assert "request('/ingest/name'" not in response.text


def test_investigation_ui_has_autosave_exit_and_logout_confirmation():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        assert response.status_code == 200
        assert "<title>PAPIRO · Investigation workspace</title>" in response.text
        assert 'property="og:title" content="PAPIRO"' in response.text
        assert 'id="saveStatus"' in response.text
        assert 'id="saveExitBtn"' in response.text
        assert 'id="sessionModal"' in response.text
        assert 'id="saveAndLogout"' in response.text
        assert 'id="logoutWithoutViewSave"' in response.text
        assert 'id="cancelSessionExit"' in response.text
        assert 'id="leaveWithoutSaving"' in response.text
        assert 'id="saveAndLeave"' in response.text
        assert "DOMContentLoaded" in response.text
        assert "Autosave is on" in response.text
        assert "/checkpoint" in response.text
        assert "/checkpoint/restore" in response.text
        assert "/checkpoint/commit" in response.text
        assert "Save and exit" in response.text
        assert "rememberLocalBaseline" in response.text


def test_papiro_brand_assets_are_served():
    with TestClient(app) as client:
        css = client.get("/ui/papiro.css")
        image = client.get("/ui/papiro-og.svg")
    assert css.status_code == 200
    assert "--accent: #B45309" in css.text
    assert image.status_code == 200
    assert 'aria-label="PAPIRO"' in image.text

def test_all_ui_routes_use_papiro_brand_and_english_copy():
    with TestClient(app) as client:
        pages = [
            client.get("/ui"),
            client.get("/ui/workspace"),
            client.get("/ui/job/example-job"),
        ]

    for response in pages:
        assert response.status_code == 200
        assert '<html lang="en-US">' in response.text
        assert 'property="og:title" content="PAPIRO"' in response.text
        assert 'aria-label="PAPIRO"' in response.text
        assert "Kami-no-Eye" not in response.text
        assert "Kami no Eye" not in response.text
        assert "Investigación:" not in response.text
        assert "Acceso de solo lectura" not in response.text

    graph = pages[2].text
    assert "Investigation:" in graph
    assert "Searching configured sources…" in graph
    assert "Relationship type and basis are required." in graph
    assert "Read-only access" in graph


def test_papiro_styles_include_accessible_shared_tokens():
    with TestClient(app) as client:
        response = client.get("/ui/papiro.css")

    assert response.status_code == 200
    for token in (
        "--bg: #FAFAF8",
        "--surface: #FFFFFF",
        "--border: #E7E5E0",
        "--text: #1C1B19",
        "--text-muted: #6B6962",
        "--accent: #B45309",
        "--accent-hover: #92400E",
        "--danger: #B91C1C",
        "--success: #15803D",
        "letter-spacing: 0.12em",
        "outline: 2px solid var(--accent)",
        "prefers-reduced-motion: reduce",
    ):
        assert token in response.text
    assert "linear-gradient(" not in response.text

def test_graph_resolves_papiro_tokens_for_cytoscape_canvas():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")

    assert response.status_code == 200
    assert "getComputedStyle(document.documentElement)" in response.text
    assert "const graphColors=" in response.text
    assert "'text-outline-color':graphColors.surface" in response.text
    assert "'line-color':graphColors.border" in response.text
    assert "'label':'data(edge_type)'" in response.text


# Regression coverage for graph interaction and viewport layout.
def test_graph_scroll_zoom_and_responsive_layout_are_separated():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")

    assert response.status_code == 200
    for fragment in (
        "height:100dvh",
        "grid-template-rows:64px minmax(0,1fr)",
        "overscroll-behavior:contain",
        "userZoomingEnabled:false",
        'id="zoomOutBtn"',
        'aria-label="Zoom out"',
        'id="zoomInBtn"',
        'aria-label="Zoom in"',
        "function zoomGraphBy(factor)",
        "cy.zoom({level,renderedPosition:{x:cy.width()/2,y:cy.height()/2}})",
        "height:auto; min-height:100vh; min-height:100dvh; overflow:visible",
        "grid-template-rows:auto minmax(55vh,65dvh) auto",
    ):
        assert fragment in response.text

    # Existing graph actions and filters must remain available.
    for element_id in (
        "fitBtn",
        "resetGraphBtn",
        "hideSelectedBtn",
        "showHiddenBtn",
        "nodeTypeFilter",
        "showIndicators",
        "showCorrelations",
        "showMemberships",
    ):
        assert f'id="{element_id}"' in response.text


def test_graph_uses_soft_node_colors_and_readable_label_backgrounds():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")

    assert response.status_code == 200
    assert "accentPale:'#F8EBDD'" in response.text
    assert "successPale:'#E7F2E9'" in response.text
    assert "'text-background-color':graphColors.bg" in response.text
    assert "'text-outline-width':2" not in response.text
    assert "'background-color':graphColors.accentHover" not in response.text
