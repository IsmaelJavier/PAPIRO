"""Apply the identity/authorization migration to the configured PostgreSQL database.

Back up the database first. Confirm migrations 002 and 003 are already applied.
This script applies only migration 004 and is safe to rerun.
"""
from pathlib import Path

from app.db import engine


def main() -> None:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "004_identity_and_authorization.sql"
    sql = migration.read_text(encoding="utf-8")
    connection = engine.raw_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(sql, prepare=False)
        connection.commit()
        print("Migration 004 applied successfully.")
    except Exception:
        connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
