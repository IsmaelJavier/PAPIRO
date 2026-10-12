from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import router
from app.auth import admin_router, auth_router, organization_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="OSINT MVP", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(organization_router)
app.include_router(router)


@app.get("/", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
def access_ui():
    """Serve the authentication and personal investigation landing page."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/ui/workspace", include_in_schema=False)
def workspace_ui():
    """Serve the authenticated workspace dashboard as a dedicated page."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "workspace.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/ui/job/{job_id}", include_in_schema=False)
@app.get("/ui/graph/{job_id}", include_in_schema=False)
def investigator_ui(job_id: str):
    """Serve the investigator workspace for an OSINT job."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "graph.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
