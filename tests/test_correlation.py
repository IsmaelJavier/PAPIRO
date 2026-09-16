from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain import CanonicalFinding, ExtractedIndicator
from app.models import CorrelationAssessment, IdentityAssessment, RelevanceAssessment
from app.repository import Repository


def test_correlate_job_matches_shared_normalized_username():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        repo = Repository(session)
        job = repo.create_job("John Smith", "person_name")

        finding_a = CanonicalFinding(
            module="source_a",
            source="source_a",
            source_url="https://a.example/john",
            input_value="John Smith",
            input_type="person_name",
            finding_type="social_profile",
            value="https://a.example/john",
            evidence_strength=0.8,
            match_reason="test_match",
            raw_evidence={},
        )
        finding_b = CanonicalFinding(
            module="source_b",
            source="source_b",
            source_url="https://b.example/john",
            input_value="John Smith",
            input_type="person_name",
            finding_type="social_profile",
            value="https://b.example/john",
            evidence_strength=0.8,
            match_reason="test_match",
            raw_evidence={},
        )

        a = repo.add_finding(
            job.id,
            finding_a,
            [ExtractedIndicator("username", "JohnSmith", "johnsmith", "username")],
        )
        b = repo.add_finding(
            job.id,
            finding_b,
            [ExtractedIndicator("username", "@JohnSmith", "johnsmith", "handle")],
        )
        session.commit()

        correlations = repo.correlate_job(job.id)
        session.commit()

        assert len(correlations) == 1
        assert correlations[0].correlation_type == "shared_username"
        assert correlations[0].assessment == CorrelationAssessment.undetermined
        assert "shared_username:johnsmith" in correlations[0].basis
        assert {correlations[0].finding_a_id, correlations[0].finding_b_id} == {a.id, b.id}


def test_name_alone_does_not_create_correlation():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        repo = Repository(session)
        job = repo.create_job("John Smith", "person_name")

        for source, url in [
            ("source_a", "https://a.example/john"),
            ("source_b", "https://b.example/john"),
        ]:
            repo.add_finding(
                job.id,
                CanonicalFinding(
                    module=f"{source}_module",
                    source=source,
                    source_url=url,
                    input_value="John Smith",
                    input_type="person_name",
                    finding_type="profile",
                    value=url,
                    evidence_strength=0.95,
                    match_reason="exact_name",
                    raw_evidence={},
                ),
                [],
            )

        session.commit()
        assert repo.correlate_job(job.id) == []
