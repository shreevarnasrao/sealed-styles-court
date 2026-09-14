from app.agents.claims import extract_claims
from app.models.schemas import Citation, InvestigationResult


def _result(theory, cites):
    return InvestigationResult(
        run_id="t",
        theory=theory,
        primary_suspect="alfred_inglethorp",
        confidence=0.5,
        citations=cites,
        needs_more_evidence=False,
        retries_used=1,
        unverified_cited=False,
    )


def test_extract_claims_from_citations():
    cites = [
        Citation(
            document_id="DOC-CH05",
            chunk_id="DOC-CH05-C001",
            claim="The cocoa was taken to her room that evening.",
            quote="cocoa was taken",
            verification_status="verified",
            support_score=0.6,
        ),
        Citation(
            document_id="DOC-ANON-TIP",
            chunk_id="DOC-ANON-TIP-C001",
            claim="A German powder was used.",
            quote="German powder",
            verification_status="unverified",
            support_score=0.4,
        ),
    ]
    claims = extract_claims(_result("Unused theory.", cites))
    assert [c.claim_id for c in claims] == ["C1", "C2"]
    assert claims[1].verification_status == "unverified"


def test_extract_claims_falls_back_to_theory_sentences():
    theory = "Alfred stood to inherit. The cocoa sat in the room for hours. Someone had the tray."
    claims = extract_claims(_result(theory, []))
    assert len(claims) >= 2
    assert all(c.claim_id.startswith("T") for c in claims)
