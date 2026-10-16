from fastapi.testclient import TestClient

from app.main import app


def test_api_metadata_uses_papiro_brand():
    assert app.title == "PAPIRO"


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
        assert "location.replace('/ui/workspace')" in client.get("/ui/assets/index.js").text
        assert 'id="investigationList"' not in response.text


def test_workspace_has_own_dashboard_and_optional_investigation_creation():
    with TestClient(app) as client:
        response = client.get("/ui/workspace")
        assert response.status_code == 200
        assert 'id="investigationList"' in response.text
        assert 'id="totalInvestigations"' in response.text
        assert 'id="newInvestigationButton"' in response.text
        assert 'id="investigationForm" hidden' in response.text
        assert "it is not required to access your workspace." in response.text
        assert 'id="logoutModal"' in response.text
        assert 'id="investigationName"' in response.text
        assert 'id="investigationNotes"' in response.text
        assert "request('/investigations'" in client.get("/ui/assets/workspace.js").text
        assert "request('/ingest/name'" not in client.get("/ui/assets/workspace.js").text


def test_investigation_ui_has_autosave_exit_and_logout_confirmation():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        assert response.status_code == 200
        assert "<title>PAPIRO · Investigation workspace</title>" in response.text
        assert 'property="og:title" content="PAPIRO"' in response.text
        assert 'id="saveStatus"' in response.text
        assert 'id="saveExitBtn"' not in response.text
        assert 'id="workspaceLink"' in response.text
        assert 'id="sessionModal"' in response.text
        assert 'id="saveAndLogout"' in response.text
        assert 'id="logoutWithoutViewSave"' in response.text
        assert 'id="cancelSessionExit"' in response.text
        assert 'id="leaveWithoutSaving"' in response.text
        assert 'id="saveAndLeave"' in response.text
        script = client.get("/ui/assets/graph.js").text
        assert "DOMContentLoaded" in script
        assert "Autosave is on" in script
        assert "/checkpoint" in script
        assert "/checkpoint/restore" in script
        assert "/checkpoint/commit" in script
        assert "Save and exit" in script
        assert "rememberLocalBaseline" in script
        assert "papiro:access-token" in script
        assert "kami:access-token" in script
        assert "papiro:hidden:" in script
        assert "kami:hidden:" in script
        assert "papiro:positions:" in script
        assert "kami:positions:" in script
        assert "papiro:session-baseline:" in script
        assert "kami:session-baseline:" in script


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
        graph_script = client.get("/ui/assets/graph.js").text

    for response in pages:
        assert response.status_code == 200
        assert '<html lang="en-US">' in response.text
        assert 'property="og:title" content="PAPIRO"' in response.text
        assert 'aria-label="PAPIRO"' in response.text
        assert "Kami-no-Eye" not in response.text
        assert "Kami no Eye" not in response.text
        assert "Investigación:" not in response.text
        assert "Acceso de solo lectura" not in response.text

    for phrase in (
        "Investigation:",
        "Searching configured sources…",
        "Relationship type and basis are required.",
        "Read-only access",
        "Select findings to create a candidate profile.",
        "Calculating differences…",
        "Derived indicators",
    ):
        assert phrase in graph_script
    for phrase in ("Ocultar del grafo", "Centrar en grafo", "Indicador</div>", "details panel..", "Indicators derivados", "Mark as belongs"):
        assert phrase not in graph_script


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
        script = client.get("/ui/assets/graph.js").text

    assert response.status_code == 200
    assert "getComputedStyle(document.documentElement)" in script
    assert "const graphColors=" in script
    assert "'text-background-color':graphColors.bg" in script
    assert "'line-color':graphColors.border" in script
    assert "'label':'data(edge_type)'" in script



def test_graph_scroll_zoom_and_responsive_layout_are_separated():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        css = client.get("/ui/assets/graph.css").text
        script = client.get("/ui/assets/graph.js").text

    assert response.status_code == 200
    for fragment in (
        "userZoomingEnabled:true",
        "addEventListener('wheel',event=>{if(!event.ctrlKey)event.stopImmediatePropagation();},{capture:true})",
        "document.getElementById('showIndicators').checked=true;document.getElementById('showCorrelations').checked=true;document.getElementById('showMemberships').checked=true",
        "document.getElementById('workspaceLink').onclick=e=>{e.preventDefault();openSessionModal();};",
        "function zoomGraphBy(factor)",
        "cy.zoom({level,renderedPosition:{x:cy.width()/2,y:cy.height()/2}})",
        '<div class="entity-actions"><button class="btn small view-entity">View profile</button></div>',
        "showEntity(id,true);toggleEntitySelection(id);",
        "selectedEntityIds=new Set([id])",
        "Select for relationship",
        "data-entity-selection-button",
        'aria-pressed="${selectedEntityIds.has(id)}"',
        "Remove from relationship selection",
    ):
        assert fragment in script

    for fragment in (
        "height:100dvh",
        "grid-template-rows:64px minmax(0,1fr)",
        "overscroll-behavior:contain",
        "height:auto; min-height:100vh; min-height:100dvh; overflow:visible",
        "grid-template-rows:auto minmax(55vh,65dvh) auto",
        "header { height:auto; min-height:64px; padding:10px 12px; align-items:flex-start; flex-wrap:wrap; gap:8px; }",
        ".header-actions { width:100%; gap:6px; }",
    ):
        assert fragment in css
    for fragment in ('id="zoomOutBtn"', 'aria-label="Zoom out"', 'id="zoomInBtn"', 'aria-label="Zoom in"', "Reset filters &amp; view"):
        assert fragment in response.text

    for element_id in ("fitBtn", "resetGraphBtn", "hideSelectedBtn", "showHiddenBtn", "nodeTypeFilter", "showIndicators", "showCorrelations", "showMemberships", "zoomInBtn", "zoomOutBtn"):
        assert f'id="{element_id}"' in response.text



def test_graph_uses_soft_node_colors_and_readable_label_backgrounds():
    with TestClient(app) as client:
        response = client.get("/ui/job/example-job")
        script = client.get("/ui/assets/graph.js").text

    assert response.status_code == 200
    assert "accentPale:'#F8EBDD'" in script
    assert "successPale:'#E7F2E9'" in script
    assert "'text-background-color':graphColors.bg" in script
    assert "'text-outline-width':2" not in script
    assert "'background-color':graphColors.accentHover" not in script


def test_page_assets_are_served_separately():
    with TestClient(app) as client:
        for page in ("index", "workspace", "graph"):
            html = client.get("/ui" if page == "index" else ("/ui/workspace" if page == "workspace" else "/ui/job/example-job"))
            css = client.get(f"/ui/assets/{page}.css")
            js = client.get(f"/ui/assets/{page}.js")
            assert html.status_code == 200
            assert f"/ui/assets/{page}.css" in html.text
            assert f"/ui/assets/{page}.js" in html.text
            assert css.status_code == 200
            assert js.status_code == 200
            assert "<style" not in html.text.lower()
            assert "<script>" not in html.text.lower()
