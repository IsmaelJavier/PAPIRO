"""Create the first superuser interactively after migration 004.

Run from the repository root:
    python -m scripts.bootstrap_superuser

This refuses to bootstrap if any account already exists.
"""
from getpass import getpass

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import User, UserRole


def main() -> None:
    email = input("Superuser email: ").strip().lower()
    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Repeat password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    try:
        hashed = hash_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with SessionLocal() as session:
        count = session.scalar(select(func.count(User.id))) or 0
        if count:
            raise SystemExit("Bootstrap refused: users already exist.")
        user = User(email=email, password_hash=hashed, global_role=UserRole.superuser, is_active=True)
        session.add(user)
        session.commit()
        print(f"Created initial superuser: {user.email}")


if __name__ == "__main__":
    main()
