from __future__ import annotations

import re

from app.config import SUPPORT_THRESHOLD, UNVERIFIED_CONFIDENCE_CAP
from app.models.schemas import Citation, EvidenceHit, InvestigationResult

_WORD = re.compile(r"[a-z0-9']+")


def token_set(text: str) -> set[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "was", "were",
        "is", "be", "that", "this", "with", "as", "at", "by", "it", "her", "his",
        "she", "he", "from", "not",
    }
    return {w for w in _WORD.findall(text.lower()) if w not in stop and len(w) > 2}


def support_score(claim: str, quote: str) -> float:
    a, b = token_set(claim), token_set(quote)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ground_citations(
    claims: list[tuple[str, str, str]],
    hits: list[EvidenceHit],
) -> list[Citation]:
    """claims: (claim_text, document_id, chunk_id) as proposed by the agent."""
    retrieved_docs = {h.document_id for h in hits}
    retrieved_chunks = {h.chunk_id: h for h in hits}
    out: list[Citation] = []
    for claim, doc_id, chunk_id in claims:
        hit = retrieved_chunks.get(chunk_id)
        if hit is None or doc_id not in retrieved_docs:
            continue
        score = support_score(claim, hit.text)
        status = hit.verification_status
        if score < SUPPORT_THRESHOLD and status == "verified":
            status = "unverified"
        out.append(
            Citation(
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                claim=claim,
                quote=hit.text[:400],
                verification_status=status,  # type: ignore[arg-type]
                support_score=round(score, 4),
            )
        )
    return out


def apply_unverified_cap(result: InvestigationResult) -> InvestigationResult:
    unverified = [c for c in result.citations if c.verification_status == "unverified"]
    result.unverified_cited = bool(unverified)
    if not unverified:
        return result
    # If the primary suspect is only carried by unverified citations, cap confidence.
    name = result.primary_suspect.lower()
    needles = {name, name.replace("_", " "), name.replace("dr_", "dr ")}

    def _mentions(text: str) -> bool:
        t = text.lower()
        return any(n in t for n in needles if n)

    unverified_supports_suspect = any(_mentions(c.claim) or _mentions(c.quote) for c in unverified)
    verified_supports = any(
        c.verification_status == "verified" and (_mentions(c.claim) or _mentions(c.quote))
        for c in result.citations
    )
    if unverified_supports_suspect and not verified_supports:
        result.confidence = min(result.confidence, UNVERIFIED_CONFIDENCE_CAP)
        result.needs_more_evidence = True
    elif unverified:
        result.confidence = min(result.confidence, max(result.confidence, 0.0) * 0.85)
    return result


def citations_from_hits(claim: str, hits: list[EvidenceHit], limit: int = 4) -> list[Citation]:
    proposed = [(claim, h.document_id, h.chunk_id) for h in hits[:limit]]
    return ground_citations(proposed, hits)


def faithfulness_report(citations: list[Citation]) -> dict:
    """RAGAS/FActScore-lite: atomic-claim faithfulness over grounded citations.

    faithfulness = supported / total where supported = support_score >= SUPPORT_THRESHOLD.
    Returns a small JSON blob the UI can render as a grounding checklist.
    """
    total = len(citations)
    supported = sum(1 for c in citations if (c.support_score or 0.0) >= SUPPORT_THRESHOLD)
    verified = sum(1 for c in citations if c.verification_status == "verified")
    unverified = sum(1 for c in citations if c.verification_status == "unverified")
    return {
        "total_citations": total,
        "supported": supported,
        "faithfulness": round(supported / total, 3) if total else 0.0,
        "verified": verified,
        "unverified": unverified,
        "checklist": {
            "has_three_citations": total >= 3,
            "acknowledges_unverified": unverified > 0 or total == 0,
            "all_supported": total > 0 and supported == total,
        },
    }
