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
    OrganizationMembership, Relationship, User, UserRole, InvestigationShare,
    EntityRegistrationRequest,
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


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    global_role: str = "investigator"


class EntityRegistrationCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EntityRequestDecision(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=2000)


class UserResponse(BaseModel):
    id: str
    email: str
    global_role: str
    is_active: bool


def _secret() -> str:
    if (
        not settings.auth_secret_key
        or len(settings.auth_secret_key) < 32
        or settings.auth_secret_key.startswith("replace-with-")
    ):
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured: set AUTH_SECRET_KEY to a random secret of at least 32 characters.",
        )
    return settings.auth_secret_key


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except Exception:
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


@auth_router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest):
    """Create a personal account; elevated roles require explicit verification."""
    _secret()
    if payload.global_role not in {UserRole.investigator.value, UserRole.user.value}:
        raise HTTPException(status_code=422, detail="Registration role must be investigator or user")
    email = str(payload.email).strip().lower()
    with db_session() as session:
        if session.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            global_role=UserRole(payload.global_role),
            is_active=True,
        )
        session.add(user)
        session.flush()
        token, ttl = create_access_token(user)
        return TokenResponse(access_token=token, expires_in=ttl)


@auth_router.post("/register-entity", status_code=202)
def register_entity(payload: EntityRegistrationCreateRequest):
    """Record a pending entity account request; it grants no login or privileges."""
    _secret()
    email = str(payload.email).strip().lower()
    slug = payload.organization_slug.strip().lower()
    with db_session() as session:
        if session.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        if session.scalar(select(EntityRegistrationRequest.id).where(
            EntityRegistrationRequest.email == email,
            EntityRegistrationRequest.status == "pending",
        )):
            raise HTTPException(status_code=409, detail="There is already a pending request for this email")
        if session.scalar(select(Organization.id).where(Organization.slug == slug)):
            raise HTTPException(status_code=409, detail="This organization identifier is already in use")
        if session.scalar(select(EntityRegistrationRequest.id).where(
            EntityRegistrationRequest.organization_slug == slug,
            EntityRegistrationRequest.status == "pending",
        )):
            raise HTTPException(status_code=409, detail="There is already a pending request for this organization identifier")
        item = EntityRegistrationRequest(
            email=email,
            password_hash=hash_password(payload.password),
            organization_name=payload.organization_name.strip(),
            organization_slug=slug,
            status="pending",
        )
        session.add(item)
        session.flush()
        return {"request_id": item.id, "status": item.status, "message": "Solicitud recibida. La cuenta se habilitará solo después de la verificación administrativa."}


def authorize_api_request(request: Request, user: User = Depends(get_current_user)) -> None:
    request.state.current_user_id = user.id
    method = request.method.upper()
    params = request.path_params
    path = request.url.path

    with db_session() as session:
        actor = session.get(User, user.id)
        if not actor or not actor.is_active:
            raise HTTPException(status_code=401, detail="Inactive account")
        # Disable the legacy self-service organization route for every role,
        # including superusers. Provisioning must go through the audited admin path.
        if path == "/api/v1/organizations" and method == "POST":
            raise HTTPException(
                status_code=403,
                detail="Organization registration requires verified administrative provisioning",
            )
        if actor.global_role == UserRole.superuser:
            return

        # Organization identity is provisioned only through /api/v1/admin/organizations.
        if path.startswith("/api/v1/admin/"):
            raise HTTPException(status_code=403, detail="Superuser role required")
        if "organization_id" in params:
            org_id = params["organization_id"]
            organization = session.get(Organization, org_id)
            if not organization or not organization.is_active or organization.verified_at is None:
                raise HTTPException(status_code=404, detail="Verified organization not found")
            membership = session.scalar(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == actor.id,
                OrganizationMembership.is_active.is_(True),
            ))
            if method in ("GET", "POST", "DELETE", "PATCH") and membership and membership.role == MembershipRole.entity:
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
            shared_copy = session.scalar(select(InvestigationShare).where(InvestigationShare.shared_job_id == job.id))
            if shared_copy and shared_copy.owner_user_id == actor.id:
                checkpoint_route = path.endswith("/checkpoint") or path.endswith("/checkpoint/commit") or path.endswith("/checkpoint/restore")
                if method == "GET" or (method == "POST" and checkpoint_route):
                    return
                raise HTTPException(status_code=403, detail="The original investigator can review this copy but cannot edit it directly")
            if job.organization_id:
                organization = session.get(Organization, job.organization_id)
                membership = session.scalar(select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == job.organization_id,
                    OrganizationMembership.user_id == actor.id,
                    OrganizationMembership.is_active.is_(True),
                ))
                if organization and organization.is_active and organization.verified_at is not None and membership and membership.role == MembershipRole.entity:
                    if method == "GET":
                        return
                    raise HTTPException(status_code=403, detail="Entity managers cannot modify investigation content")
            if job.owner_user_id == actor.id:
                if method != "GET" and actor.global_role == UserRole.user:
                    raise HTTPException(status_code=403, detail="This account is read-only")
                if shared_copy and method != "GET" and shared_copy.permission != "edit":
                    raise HTTPException(status_code=403, detail="This shared copy does not grant editing permission")
                return
            raise HTTPException(status_code=404, detail="Investigation not found")

        # All other API routes require an authenticated investigator. The
        # handler still has to scope creation to the current user/organization.
        if path.startswith("/api/v1/shares/") and path.endswith("/comments"):
            # The comment handler verifies share participation and the selected
            # permission; entity accounts may comment only when they are a party.
            return
        if actor.global_role in {UserRole.user, UserRole.entity} and method != "GET":
            detail = (
                "Entity accounts cannot create or modify investigation content"
                if actor.global_role == UserRole.entity
                else "This account is read-only"
            )
            raise HTTPException(status_code=403, detail=detail)


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    global_role: str = "investigator"


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AdminOrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    manager_email: EmailStr


class MembershipCreateRequest(BaseModel):
    email: EmailStr
    role: str = "investigator"


class MembershipInvitationDecision(BaseModel):
    decision: str


admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["administration"],
    dependencies=[Depends(authorize_api_request)],
)
organization_router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
    dependencies=[Depends(authorize_api_request)],
)


@admin_router.post("/users", response_model=UserResponse, status_code=201)
def admin_create_user(payload: AdminUserCreateRequest, request: Request):
    # The central dependency guarantees only superusers can pass admin paths.
    role = payload.global_role
    if role == UserRole.superuser.value:
        raise HTTPException(status_code=403, detail="The platform administrator is unique and cannot be created from this endpoint")
    if role not in {UserRole.investigator.value, UserRole.user.value}:
        raise HTTPException(status_code=422, detail="Invalid global role")
    email = str(payload.email).lower()
    with db_session() as session:
        if session.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(email=email, password_hash=hash_password(payload.password), global_role=UserRole(role))
        session.add(user)
        session.flush()
        return UserResponse(id=user.id, email=user.email, global_role=user.global_role.value, is_active=user.is_active)


@admin_router.get("/entity-requests")
def list_entity_registration_requests():
    """List pending entity requests for the sole platform administrator."""
    with db_session() as session:
        rows = session.scalars(
            select(EntityRegistrationRequest)
            .where(EntityRegistrationRequest.status == "pending")
            .order_by(EntityRegistrationRequest.requested_at.asc())
        ).all()
        return [{
            "id": row.id,
            "email": row.email,
            "organization_name": row.organization_name,
            "organization_slug": row.organization_slug,
            "requested_at": row.requested_at,
            "status": row.status,
        } for row in rows]


@admin_router.post("/entity-requests/{request_id}/approve", status_code=201)
def approve_entity_registration_request(request_id: str, request: Request):
    """Atomically create the verified entity account and organization after review."""
    administrator_id = request.state.current_user_id
    with db_session() as session:
        item = session.scalar(
            select(EntityRegistrationRequest)
            .where(EntityRegistrationRequest.id == request_id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Entity registration request not found")
        if item.status != "pending":
            raise HTTPException(status_code=409, detail="This request has already been reviewed")
        if session.scalar(select(User.id).where(User.email == item.email)):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        if session.scalar(select(Organization.id).where(Organization.slug == item.organization_slug)):
            raise HTTPException(status_code=409, detail="This organization identifier is already in use; review it separately")
        now = datetime.now(timezone.utc)
        user = User(email=item.email, password_hash=item.password_hash, global_role=UserRole.entity, is_active=True)
        session.add(user)
        session.flush()
        org = Organization(
            name=item.organization_name,
            slug=item.organization_slug,
            contact_email=user.email,
            verified_at=now,
            verified_by_user_id=administrator_id,
            created_by_user_id=administrator_id,
            is_active=True,
        )
        session.add(org)
        session.flush()
        session.add(OrganizationMembership(
            organization_id=org.id, user_id=user.id, role=MembershipRole.entity, is_active=True
        ))
        item.status = "approved"
        item.reviewed_at = now
        item.reviewed_by_user_id = administrator_id
        item.organization_id = org.id
        item.rejection_reason = None
        item.password_hash = ""  # Avoid retaining a second copy of the account credential hash.
        session.flush()
        return {"request_id": item.id, "status": item.status, "email": user.email, "organization_id": org.id, "organization_name": org.name, "verified_by_user_id": administrator_id}


@admin_router.post("/entity-requests/{request_id}/reject")
def reject_entity_registration_request(request_id: str, payload: EntityRequestDecision, request: Request):
    """Reject a pending request without creating an account or organization."""
    administrator_id = request.state.current_user_id
    with db_session() as session:
        item = session.scalar(
            select(EntityRegistrationRequest)
            .where(EntityRegistrationRequest.id == request_id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Entity registration request not found")
        if item.status != "pending":
            raise HTTPException(status_code=409, detail="This request has already been reviewed")
        item.status = "rejected"
        item.reviewed_at = datetime.now(timezone.utc)
        item.reviewed_by_user_id = administrator_id
        item.rejection_reason = (payload.rejection_reason or "").strip() or None
        item.password_hash = ""  # A rejected request must not retain credential material.
        return {"request_id": item.id, "status": item.status}


@admin_router.post("/organizations", status_code=201)
def admin_create_organization(payload: AdminOrganizationCreateRequest, request: Request):
    """Provision an organization only after an administrator verifies its identity."""
    email = str(payload.manager_email).strip().lower()
    with db_session() as session:
        org = session.scalar(select(Organization).where(Organization.slug == payload.slug))
        if org and org.verified_at is not None:
            raise HTTPException(status_code=409, detail="Organization identifier is already verified")
        manager = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not manager:
            raise HTTPException(status_code=404, detail="The verified entity manager must have an active account")
        if manager.global_role != UserRole.entity:
            raise HTTPException(status_code=422, detail="The organization account must have the entity role")
        administrator_id = request.state.current_user_id
        now = datetime.now(timezone.utc)
        if org is None:
            org = Organization(
                name=payload.name.strip(),
                slug=payload.slug,
                contact_email=manager.email,
                verified_at=now,
                verified_by_user_id=administrator_id,
                created_by_user_id=administrator_id,
            )
            session.add(org)
            session.flush()
        else:
            # Explicit admin verification may activate an existing legacy org.
            # Preserve its identifier, creator and all attached investigations.
            org.name = payload.name.strip()
            org.contact_email = manager.email
            org.verified_at = now
            org.verified_by_user_id = administrator_id
        membership = session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == manager.id,
        ))
        if membership is None:
            membership = OrganizationMembership(
                organization_id=org.id,
                user_id=manager.id,
                role=MembershipRole.entity,
                is_active=True,
            )
            session.add(membership)
        else:
            membership.role = MembershipRole.entity
            membership.is_active = True
        session.flush()
        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "entity_identifier": org.slug,
            "contact_email": org.contact_email,
            "verified_at": org.verified_at,
            "verified_by_user_id": org.verified_by_user_id,
            "manager_email": manager.email,
            "role": membership.role.value,
        }


@organization_router.get("")
def list_organizations(request: Request):
    """List only organizations in which the authenticated user has an active membership."""
    user_id = request.state.current_user_id
    with db_session() as session:
        rows = session.execute(
            select(Organization, OrganizationMembership.role)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
                OrganizationMembership.invitation_status == "accepted",
                Organization.is_active.is_(True),
                Organization.verified_at.is_not(None),
            )
            .order_by(Organization.name.asc())
        ).all()
        return [
            {
                "id": organization.id,
                "name": organization.name,
                "identifier": organization.slug,
                "role": role.value,
            }
            for organization, role in rows
        ]


@organization_router.post("", status_code=201)
def create_organization(payload: OrganizationCreateRequest, request: Request):
    creator_id = request.state.current_user_id
    with db_session() as session:
        if session.scalar(select(Organization).where(Organization.slug == payload.slug)):
            raise HTTPException(status_code=409, detail="Organization slug already exists")
        org = Organization(name=payload.name.strip(), slug=payload.slug, created_by_user_id=creator_id)
        session.add(org)
        session.flush()
        # Creator initially manages membership. They can add investigators who
        # own and edit their own organizational investigations.
        membership = OrganizationMembership(
            organization_id=org.id, user_id=creator_id, role=MembershipRole.entity
        )
        session.add(membership)
        session.flush()
        return {"id": org.id, "name": org.name, "slug": org.slug, "role": membership.role.value}


@organization_router.get("/invitations/mine")
def list_my_organization_invitations(request: Request):
    user_id = request.state.current_user_id
    with db_session() as session:
        rows = session.execute(
            select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.role == MembershipRole.investigator,
                OrganizationMembership.invitation_status == "pending",
                Organization.is_active.is_(True),
                Organization.verified_at.is_not(None),
            )
            .order_by(OrganizationMembership.created_at.asc())
        ).all()
        return [{
            "invitation_id": membership.id,
            "organization_id": organization.id,
            "organization_name": organization.name,
            "organization_identifier": organization.slug,
            "invited_at": membership.created_at,
            "invited_by_user_id": membership.invited_by_user_id,
        } for membership, organization in rows]


@organization_router.post("/invitations/{invitation_id}/respond")
def respond_to_organization_invitation(
    invitation_id: str, payload: MembershipInvitationDecision, request: Request
):
    decision = payload.decision.strip().lower()
    if decision not in {"accept", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be accept or reject")
    user_id = request.state.current_user_id
    with db_session() as session:
        membership = session.scalar(
            select(OrganizationMembership)
            .where(OrganizationMembership.id == invitation_id)
            .with_for_update()
        )
        if not membership or membership.user_id != user_id:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if membership.role != MembershipRole.investigator or membership.invitation_status != "pending":
            raise HTTPException(status_code=409, detail="This invitation has already been answered or is not valid")
        organization = session.get(Organization, membership.organization_id)
        if not organization or not organization.is_active or organization.verified_at is None:
            raise HTTPException(status_code=404, detail="Verified organization not found")
        membership.invitation_status = "accepted" if decision == "accept" else "rejected"
        membership.is_active = decision == "accept"
        membership.responded_at = datetime.now(timezone.utc)
        session.flush()
        return {
            "invitation_id": membership.id,
            "status": membership.invitation_status,
            "organization_id": organization.id,
            "organization_name": organization.name,
        }


@organization_router.get("/{organization_id}/members")
def list_organization_members(organization_id: str):
    with db_session() as session:
        org = session.get(Organization, organization_id)
        if not org or not org.is_active or org.verified_at is None:
            raise HTTPException(status_code=404, detail="Verified organization not found")
        rows = session.scalars(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            (
                OrganizationMembership.is_active.is_(True)
                | (OrganizationMembership.invitation_status == "pending")
            ),
        )).all()
        return [
            {
                "user_id": row.user_id,
                "email": row.user.email,
                "role": row.role.value,
                "invitation_status": row.invitation_status,
                "is_active": row.is_active,
                "invited_at": row.created_at,
                "responded_at": row.responded_at,
            }
            for row in rows
        ]


@organization_router.post("/{organization_id}/members", status_code=201)
def add_organization_member(organization_id: str, payload: MembershipCreateRequest, request: Request):
    # Entity managers can add investigator accounts, but cannot promote another
    # account to entity status; that capability remains with verified admin provisioning.
    if payload.role != MembershipRole.investigator.value:
        raise HTTPException(status_code=403, detail="Only administrators can assign the entity role")
    email = str(payload.email).lower()
    with db_session() as session:
        org = session.get(Organization, organization_id)
        if not org or not org.is_active or org.verified_at is None:
            raise HTTPException(status_code=404, detail="Verified organization not found")
        user = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not user:
            raise HTTPException(status_code=404, detail="Active user not found; an administrator must create the account first")
        if user.global_role != UserRole.investigator:
            raise HTTPException(status_code=422, detail="Only investigator accounts can be added as investigators")
        existing = session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
        ))
        if existing:
            if existing.is_active and existing.invitation_status == "accepted":
                raise HTTPException(status_code=409, detail="User is already a member")
            if existing.invitation_status == "pending":
                raise HTTPException(status_code=409, detail="An invitation is already pending")
            existing.is_active = False
            existing.role = MembershipRole(payload.role)
            existing.invitation_status = "pending"
            existing.invited_by_user_id = request.state.current_user_id
            existing.responded_at = None
            session.flush()
            return {"user_id": user.id, "email": user.email, "role": existing.role.value, "invitation_status": existing.invitation_status}
        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=user.id,
            role=MembershipRole(payload.role),
            is_active=False,
            invitation_status="pending",
            invited_by_user_id=request.state.current_user_id,
        )
        session.add(membership)
        session.flush()
        return {"user_id": user.id, "email": user.email, "role": membership.role.value, "invitation_status": membership.invitation_status}


@organization_router.delete("/{organization_id}/members/{user_id}", status_code=204)
def remove_organization_member(organization_id: str, user_id: str):
    with db_session() as session:
        membership = session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        ))
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found")
        if membership.user_id == membership.organization.created_by_user_id:
            raise HTTPException(status_code=409, detail="Transfer organization ownership before removing its creator")
        if membership.role == MembershipRole.entity:
            other_entity_manager = session.scalar(select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active.is_(True),
                OrganizationMembership.role == MembershipRole.entity,
                OrganizationMembership.user_id != user_id,
            ))
            if not other_entity_manager:
                raise HTTPException(status_code=409, detail="An organization must retain at least one active entity manager")
        membership.is_active = False


class MembershipRoleUpdateRequest(BaseModel):
    role: str


@organization_router.patch("/{organization_id}/members/{user_id}")
def update_organization_member_role(
    organization_id: str, user_id: str, payload: MembershipRoleUpdateRequest
):
    if payload.role != MembershipRole.investigator.value:
        raise HTTPException(status_code=403, detail="Only administrators can assign the entity role")
    with db_session() as session:
        membership = session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        ))
        if not membership:
            raise HTTPException(status_code=404, detail="Active membership not found")
        if membership.role == MembershipRole.entity and payload.role != MembershipRole.entity:
            other_entity = session.scalar(select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active.is_(True),
                OrganizationMembership.role == MembershipRole.entity,
                OrganizationMembership.user_id != user_id,
            ))
            if not other_entity:
                raise HTTPException(status_code=409, detail="An organization must retain at least one active entity manager")
        membership.role = MembershipRole(payload.role)
        session.flush()
        return {"user_id": membership.user_id, "role": membership.role.value}
