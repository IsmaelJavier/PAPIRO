from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api import (
    _decode_snapshot_value,
    _encode_snapshot_value,
    _investigation_tables,
    _make_investigation_snapshot,
    _restore_investigation_snapshot,
)
from app.db import Base
from app.main import app
from app.models import Entity, Job, JobStatus


def test_checkpoint_endpoints_are_registered():
    paths = app.openapi()["paths"]
    assert "/api/v1/jobs/{job_id}/checkpoint" in paths
    assert "/api/v1/jobs/{job_id}/checkpoint/commit" in paths
    assert "/api/v1/jobs/{job_id}/checkpoint/restore" in paths


def test_investigation_snapshot_table_order_respects_foreign_keys():
    tables = _investigation_tables()
    names = [table.name for table in tables]
    positions = {name: index for index, name in enumerate(names)}

    assert names[0] == "jobs"
    assert "investigation_checkpoints" not in names
    assert "users" not in names
    assert "organizations" not in names

    for table in tables:
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            if parent_name in positions:
                assert positions[parent_name] < positions[table.name]


def test_snapshot_values_round_trip_datetime_and_enum():
    original_time = datetime(2026, 10, 11, 12, 30, tzinfo=timezone.utc)
    encoded_time = _encode_snapshot_value(original_time)
    encoded_status = _encode_snapshot_value(JobStatus.draft)

    assert _decode_snapshot_value(encoded_time) == original_time
    assert _decode_snapshot_value(encoded_status, Job.__table__.c.status) is JobStatus.draft


def test_restore_returns_investigation_data_to_the_session_baseline():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as session:
        job = Job(
            input_value="persona de prueba",
            investigation_title="Estado inicial",
            notes="Notas originales",
            input_type="person_name",
            status=JobStatus.draft,
        )
        session.add(job)
        session.flush()

        original_entity = Entity(
            job_id=job.id,
            label="Entidad original",
            description="Descripción inicial",
        )
        session.add(original_entity)
        session.flush()
        original_entity_id = original_entity.id

        snapshot = _make_investigation_snapshot(session, job.id)

        original_entity.label = "Entidad modificada"
        session.add(Entity(job_id=job.id, label="Entidad nueva"))
        job.notes = "Notas editadas"
        session.flush()

        _restore_investigation_snapshot(session, job.id, snapshot)
        session.flush()
        session.expire_all()

        restored_job = session.get(Job, job.id)
        restored_entities = session.scalars(
            select(Entity).where(Entity.job_id == job.id)
        ).all()

        assert restored_job.notes == "Notas originales"
        assert restored_job.investigation_title == "Estado inicial"
        assert len(restored_entities) == 1
        assert restored_entities[0].id == original_entity_id
        assert restored_entities[0].label == "Entidad original"
        assert restored_entities[0].description == "Descripción inicial"
