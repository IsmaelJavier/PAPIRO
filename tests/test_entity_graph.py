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


def test_entity_can_group_findings_without_identity_conclusion():
    session = _repo()
    repo = Repository(session)
    job = repo.create_job("John Smith", "person_name")
    finding = repo.add_finding(
        job.id,
        CanonicalFinding(
            module="source_a", source="source_a", source_url="https://a.example/john",
            input_value="John Smith", input_type="person_name", finding_type="profile",
            value="https://a.example/john", evidence_strength=0.8,
            match_reason="test_match", raw_evidence={},
        ),
        [ExtractedIndicator("username", "johnsmith", "johnsmith", "username")],
    )
    entity = repo.create_entity(job.id, "Candidato 1", description="Agrupación de investigación")
    repo.attach_finding_to_entity(entity, finding, role="perfil")
    session.commit()

    loaded = repo.get_entity(entity.id)
    assert loaded.label == "Candidato 1"
    assert loaded.entity_type == EntityType.person_candidate
    assert len(loaded.findings) == 1
    assert loaded.findings[0].finding_id == finding.id
    assert finding.identity_assessment.value == "indeterminado"


def test_graph_exposes_traceable_findings_indicators_and_correlations():
    session = _repo()
    repo = Repository(session)
    job = repo.create_job("John Smith", "person_name")

    findings = []
    for source, url in [("source_a", "https://a.example/john"), ("source_b", "https://b.example/john")]:
        findings.append(repo.add_finding(
            job.id,
            CanonicalFinding(
                module=f"{source}_module", source=source, source_url=url,
                input_value="John Smith", input_type="person_name", finding_type="profile",
                value=url, evidence_strength=0.8, match_reason="test_match", raw_evidence={},
            ),
            [ExtractedIndicator("username", "@JohnSmith", "johnsmith", "username")],
        ))
    session.commit()
    correlations = repo.correlate_job(job.id)
    session.commit()
    graph = repo.get_graph(job.id)

    assert graph["summary"]["findings"] == 2
    assert graph["summary"]["indicators"] == 2
    assert graph["summary"]["correlations"] == 1
    assert any(edge["edge_type"] == "correlation" for edge in graph["edges"])
    assert any(node["node_type"] == "indicator" for node in graph["nodes"])

    entity_a = repo.create_entity(job.id, "Candidato A")
    entity_b = repo.create_entity(job.id, "Candidato B")
    repo.attach_finding_to_entity(entity_a, findings[0])
    repo.attach_finding_to_entity(entity_b, findings[1])
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
