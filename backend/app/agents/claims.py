"""Atomic claims — the seam between Investigator output and Fact-Checker attack.

A citation is already a claim. Theory sentences fill gaps when the agent
returned prose without structured citations. The Fact-Checker queries these
atoms; it does not re-summarise the theory.
"""

from __future__ import annotations

import re

from app.models.schemas import AtomicClaim, InvestigationResult

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def extract_claims(result: InvestigationResult) -> list[AtomicClaim]:
    out: list[AtomicClaim] = []
    seen: set[str] = set()
    for i, c in enumerate(result.citations):
        text = (c.claim or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(
            AtomicClaim(
                claim_id=f"C{i + 1}",
                text=text,
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                verification_status=c.verification_status,
                support_score=c.support_score,
            )
        )
    if len(out) < 2:
        for j, sent in enumerate(_SENTENCE.split(result.theory or "")):
            text = sent.strip()
            if len(text) < 24 or text.lower() in seen:
                continue
            seen.add(text.lower())
            out.append(
                AtomicClaim(
                    claim_id=f"T{j + 1}",
                    text=text[:240],
                )
            )
            if len(out) >= 6:
                break
    return out[:6]


def attach_claims(result: InvestigationResult) -> InvestigationResult:
    result.claims = extract_claims(result)
    return result
