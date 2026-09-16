from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain import CanonicalFinding, ExtractedIndicator
from app.models import EntityType, RelationshipAssessment
from app.repository import Repository


def _repo():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _finding(repo, job, source, username):
    return repo.add_finding(
        job.id,
        CanonicalFinding(
            module=f"{source}_module", source=source, source_url=f"https://{source}.example/{username}",
            input_value=job.input_value, input_type="person_name", finding_type="profile",
            value=f"https://{source}.example/{username}", evidence_strength=0.8,
            match_reason="test_match", raw_evidence={},
        ),
        [ExtractedIndicator("username", username, username, "username")],
    )


def test_entity_can_group_findings_without_identity_conclusion():
    session = _repo()
    repo = Repository(session)
    job = repo.create_job("John Smith", "person_name")
    finding = _finding(repo, job, "source_a", "johnsmith")
    entity = repo.create_entity(job.id, "Candidato 1", description="Agrupación de investigación")
    repo.attach_finding_to_entity(entity, finding, role="perfil")
    session.commit()

    loaded = repo.get_entity(entity.id)
    assert loaded.label == "Candidato 1"
    assert loaded.entity_type == EntityType.person_candidate
    assert len(loaded.findings) == 1
    assert loaded.findings[0].finding_id == finding.id
    assert finding.identity_assessment.value == "indeterminado"


def test_entity_creation_can_include_multiple_selected_findings():
    session = _repo()
    repo = Repository(session)
    job = repo.create_job("John Smith", "person_name")
    finding_a = _finding(repo, job, "source_a", "johnsmith")
    finding_b = _finding(repo, job, "source_b", "johnsmith2")

    entity = repo.create_entity(
        job.id,
        "Candidato A",
        description="Perfil construido por el investigador",
        finding_ids=[finding_a.id, finding_b.id],
    )
    session.commit()

    loaded = repo.get_entity(entity.id)
    assert {x.finding_id for x in loaded.findings} == {finding_a.id, finding_b.id}
    assert all(x.role == "evidencia" for x in loaded.findings)


def test_entity_creation_rejects_findings_from_another_job():
    session = _repo()
    repo = Repository(session)
    job_a = repo.create_job("John Smith", "person_name")
    job_b = repo.create_job("Jane Smith", "person_name")
    foreign = _finding(repo, job_b, "source_b", "janesmith")

    try:
        repo.create_entity(job_a.id, "Candidato", finding_ids=[foreign.id])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "belong to the job" in str(exc)


def test_graph_exposes_traceable_findings_indicators_and_correlations():
    session = _repo()
    repo = Repository(session)
    job = repo.create_job("John Smith", "person_name")

    findings = [
        _finding(repo, job, "source_a", "johnsmith"),
        _finding(repo, job, "source_b", "johnsmith"),
    ]
    session.commit()
    correlations = repo.correlate_job(job.id)
    session.commit()
    graph = repo.get_graph(job.id)

    assert graph["summary"]["findings"] == 2
    assert graph["summary"]["indicators"] == 2
    assert graph["summary"]["correlations"] == 1
    assert any(edge["edge_type"] == "correlation" for edge in graph["edges"])
    assert any(node["node_type"] == "indicator" for node in graph["nodes"])
    assert all(node.get("source") == "source_a" or node.get("source") == "source_b" for node in graph["nodes"] if node["node_type"] == "indicator")

    entity_a = repo.create_entity(job.id, "Candidato A", finding_ids=[findings[0].id])
    entity_b = repo.create_entity(job.id, "Candidato B", finding_ids=[findings[1].id])
    relationship = repo.create_relationship(
        job.id, entity_a, entity_b,
        relationship_type="associated_with",
        basis="shared_username:johnsmith",
        assessment=RelationshipAssessment.undetermined,
        correlation_id=correlations[0].id,
        finding_a_id=findings[0].id,
        finding_b_id=findings[1].id,
    )
    session.commit()
    graph = repo.get_graph(job.id)

    assert graph["summary"]["entities"] == 2
    assert graph["summary"]["relationships"] == 1
    assert any(edge["edge_type"] == "relationship" for edge in graph["edges"])
    assert relationship.assessment.value == "indeterminado"
