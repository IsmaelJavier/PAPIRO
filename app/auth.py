import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import select

from app.config import settings
from app.db import db_session
from app.models import (
    Correlation, Entity, Finding, Job, MembershipRole, Organization,
    OrganizationMembership, Relationship, User, UserRole,
)

auth_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    global_role: str
    is_active: bool


def _secret() -> str:
    if not settings.auth_secret_key or len(settings.auth_secret_key) < 32:
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured: set AUTH_SECRET_KEY to a random secret of at least 32 characters.",
        )
    return settings.auth_secret_key


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def hash_password(plain_password: str) -> str:
    if len(plain_password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return password_hash.hash(plain_password)


def create_access_token(user: User) -> tuple[str, int]:
    ttl = max(1, settings.auth_token_ttl_minutes) * 60
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": user.id, "iat": now, "exp": now + timedelta(seconds=ttl)},
        _secret(),
        algorithm="HS256",
    )
    return token, ttl


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("missing subject")
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})

    with db_session() as session:
        user = session.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Inactive or unknown account", headers={"WWW-Authenticate": "Bearer"})
        # Detach a small identity snapshot from the session; request authz reloads
        # persisted memberships and resource ownership on its own session.
        session.expunge(user)
        return user


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    _secret()
    with db_session() as session:
        user = session.scalar(select(User).where(User.email == str(payload.email).lower()))
        if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
        token, ttl = create_access_token(user)
        return TokenResponse(access_token=token, expires_in=ttl)


@auth_router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, global_role=user.global_role.value, is_active=user.is_active)


def authorize_api_request(request: Request, user: User = Depends(get_current_user)) -> None:
    request.state.current_user_id = user.id
    method = request.method.upper()
    params = request.path_params
    path = request.url.path

    with db_session() as session:
        actor = session.get(User, user.id)
        if not actor or not actor.is_active:
            raise HTTPException(status_code=401, detail="Inactive account")
        if actor.global_role == UserRole.superuser:
            return

        # Organization membership management is a separate capability: entity
        # managers can administer membership, but not investigation content.
        if path == "/api/v1/organizations" and method == "POST":
            if actor.global_role not in (UserRole.investigator, UserRole.user):
                raise HTTPException(status_code=403, detail="Forbidden")
            return
        if "organization_id" in params and path.endswith("/members"):
            org_id = params["organization_id"]
            membership = session.scalar(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == actor.id,
                OrganizationMembership.is_active.is_(True),
            ))
            if method in ("GET", "POST", "DELETE") and membership and membership.role == MembershipRole.entity:
                return
            raise HTTPException(status_code=403, detail="Only the organization's entity manager may manage memberships")

        job_id = params.get("job_id")
        if not job_id:
            for key, model in (
                ("entity_id", Entity), ("finding_id", Finding),
                ("correlation_id", Correlation), ("relationship_id", Relationship),
            ):
                resource_id = params.get(key)
                if resource_id:
                    resource = session.get(model, resource_id)
                    if not resource:
                        raise HTTPException(status_code=404, detail="Resource not found")
                    job_id = resource.job_id
                    break

        if job_id:
            job = session.get(Job, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Investigation not found")
            if job.owner_user_id is None:
                raise HTTPException(status_code=404, detail="Investigation not found")
            if job.owner_user_id == actor.id:
                if method != "GET" and actor.global_role == UserRole.user:
                    raise HTTPException(status_code=403, detail="This account is read-only")
                return
            if job.organization_id:
                membership = session.scalar(select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == job.organization_id,
                    OrganizationMembership.user_id == actor.id,
                    OrganizationMembership.is_active.is_(True),
                ))
                if membership and membership.role == MembershipRole.entity and method == "GET":
                    return
            raise HTTPException(status_code=404, detail="Investigation not found")

        # All other API routes require an authenticated investigator. The
        # handler still has to scope creation to the current user/organization.
        if actor.global_role == UserRole.user and method != "GET":
            raise HTTPException(status_code=403, detail="This account is read-only")
