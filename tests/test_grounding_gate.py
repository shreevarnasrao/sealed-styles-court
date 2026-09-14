from app.grounding.gate import apply_unverified_cap, ground_citations, support_score
from app.models.schemas import Citation, EvidenceHit, InvestigationResult


def test_support_score_overlap():
    s = support_score("strychnine in the cocoa", "the cocoa contained strychnine crystals")
    assert s > 0.2


def test_citation_must_be_in_retrieved_set():
    hits = [
        EvidenceHit(
            document_id="DOC-CH05",
            chunk_id="DOC-CH05-C001",
            text="The cocoa was taken to her room.",
            score=1.0,
            source="hybrid",
            verification_status="verified",
        )
    ]
    claims = [
        ("cocoa taken up", "DOC-CH05", "DOC-CH05-C001"),
        ("secret German powder", "DOC-ANON-TIP", "DOC-ANON-TIP-C001"),
    ]
    cites = ground_citations(claims, hits)
    assert len(cites) == 1
    assert cites[0].document_id == "DOC-CH05"


def test_unverified_caps_confidence():
    result = InvestigationResult(
        run_id="x",
        theory="Bauerstein did it with a German powder",
        primary_suspect="dr_bauerstein",
        confidence=0.9,
        citations=[
            Citation(
                document_id="DOC-ANON-TIP",
                chunk_id="DOC-ANON-TIP-C001",
                claim="Dr Bauerstein used a German powder",
                quote="Dr Bauerstein put a German powder in the cocoa",
                verification_status="unverified",
                support_score=0.5,
            )
        ],
        needs_more_evidence=False,
        retries_used=1,
        unverified_cited=False,
    )
    capped = apply_unverified_cap(result)
    assert capped.unverified_cited
    assert capped.confidence <= 0.45
    assert capped.needs_more_evidence
