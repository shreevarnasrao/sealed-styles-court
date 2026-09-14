from __future__ import annotations

import uuid
from typing import Any

from app.agents.claims import attach_claims
from app.config import MAX_RETRIES
from app.corpus.store import CorpusStore
from app.graph.evidence_graph import EvidenceGraph
from app.grounding.gate import apply_unverified_cap, citations_from_hits, ground_citations
from app.llm.client import LLMClient, LLMError
from app.models.schemas import AgentStep, EvidenceHit, InvestigationResult
from app.rag.retrieve import HybridRetriever

INVESTIGATOR_SYS = """You are the Investigator (prosecution) on a 1916 poisoning case at Styles Court.
You may ONLY use the evidence passages provided. Do not use outside knowledge of any novel or famous solution.
If a passage is marked unverified, you may discuss it only as unverified rumour. It must not raise your confidence.
Every claim needs a citation to a document_id and chunk_id from the evidence list.
Return JSON only.
"""


class Investigator:
    def __init__(self, store: CorpusStore, retriever: HybridRetriever, graph: EvidenceGraph, llm: LLMClient):
        self.store = store
        self.retriever = retriever
        self.graph = graph
        self.llm = llm

    async def run(self, focus: str | None = None) -> InvestigationResult:
        run_id = uuid.uuid4().hex[:12]
        trace: list[AgentStep] = []
        theory = "An open poisoning at Styles Court; several household members had motive and access."
        suspect = ""
        queries = [
            "strychnine poison convulsions Mrs Inglethorp",
            "who prepared the cocoa on the night of the tragedy",
            "will of Mrs Inglethorp Alfred Inglethorp",
            "hours delay cocoa bedtime convulsions",
        ]
        if focus:
            queries.append(focus)
            theory = f"Working theory focused on: {focus}"

        hits: list[EvidenceHit] = []
        last: dict[str, Any] = {}
        for attempt in range(1, MAX_RETRIES + 1):
            hits = await self._retrieve(queries)
            hits = self.graph.expand_hits(hits)
            evidence_block = _format_hits(hits)
            trace.append(
                AgentStep(
                    step=attempt,
                    action="retrieve",
                    thought=f"Testing theory: {theory[:180]}",
                    queries=queries,
                    hit_ids=[h.chunk_id for h in hits],
                    decision="evaluate_sufficiency",
                )
            )
            last = await self._evaluate(theory, hits, evidence_block, attempt)
            theory = last.get("theory") or theory
            suspect = last.get("primary_suspect") or suspect
            sufficient = bool(last.get("sufficient"))
            gaps = last.get("gaps") or []
            queries = last.get("next_queries") or queries
            trace.append(
                AgentStep(
                    step=attempt,
                    action="evaluate",
                    thought=last.get("reasoning") or "",
                    queries=queries,
                    hit_ids=[h.chunk_id for h in hits],
                    decision="accept" if sufficient else f"retry gaps={gaps}",
                )
            )
            if sufficient:
                break
            theory = last.get("reformulated_theory") or theory

        claim_tuples = []
        for c in last.get("citations") or []:
            claim_tuples.append((c.get("claim", theory), c.get("document_id", ""), c.get("chunk_id", "")))
        if claim_tuples:
            citations = ground_citations(claim_tuples, hits)
        else:
            verified_hits = [h for h in hits if h.verification_status == "verified"]
            citations = citations_from_hits(theory, verified_hits or hits)
        result = InvestigationResult(
            run_id=run_id,
            theory=theory,
            primary_suspect=_normalize_suspect(suspect, self.store),
            confidence=float(last.get("confidence") or 0.4),
            citations=citations,
            needs_more_evidence=not bool(last.get("sufficient")),
            retries_used=min(MAX_RETRIES, max(1, len([t for t in trace if t.action == "evaluate"]))),
            unverified_cited=False,
            trace=trace,
        )
        return attach_claims(apply_unverified_cap(result))

    async def _retrieve(self, queries: list[str]) -> list[EvidenceHit]:
        import asyncio

        async def one(q: str) -> list[EvidenceHit]:
            return self.retriever.search(q, k=6)

        batches = await asyncio.gather(*[one(q) for q in queries[:6]])
        seen: set[str] = set()
        merged: list[EvidenceHit] = []
        for batch in batches:
            for h in batch:
                if h.chunk_id not in seen:
                    seen.add(h.chunk_id)
                    merged.append(h)
        return merged[:12]

    async def _evaluate(self, theory: str, hits: list[EvidenceHit], evidence_block: str, attempt: int) -> dict[str, Any]:
        suspects = ", ".join(f"{s['id']} ({s['name']})" for s in self.store.suspects())
        user = f"""Attempt {attempt} of {MAX_RETRIES}.
Current theory: {theory}
Suspect ids: {suspects}

Evidence (each item shows verification_status, document_id, chunk_id):
{evidence_block}

JSON schema:
{{
  "theory": "string",
  "primary_suspect": "suspect id from the list",
  "confidence": 0.0,
  "sufficient": false,
  "gaps": ["string"],
  "reasoning": "string",
  "reformulated_theory": "string",
  "next_queries": ["search query"],
  "citations": [{{"claim": "string", "document_id": "DOC-...", "chunk_id": "DOC-...-C001"}}]
}}
If evidence is thin, set sufficient=false and propose next_queries that would fill the gaps.
Never cite a document_id that is not in the evidence list.
Never treat unverified evidence as proof.
"""
        if not self.llm.available:
            return self._heuristic(theory, hits, attempt)
        try:
            return await self.llm.complete_json(INVESTIGATOR_SYS, user)
        except (LLMError, Exception):
            return self._heuristic(theory, hits, attempt)

    def _heuristic(self, theory: str, hits: list[EvidenceHit], attempt: int) -> dict[str, Any]:
        """Retrieval-only fallback: hit-score + verification weight + PageRank prior.

        Each retrieved hit votes its RRF score for the suspects it mentions;
        unverified hits vote at 0.25 weight. No suspect is special-cased.
        """
        scores: dict[str, float] = {s["id"]: 0.0 for s in self.store.suspects()}
        known = self.store.suspect_ids()
        for h in hits:
            weight = 0.25 if h.verification_status == "unverified" else 1.0
            for sid in h.characters:
                if sid in scores:
                    scores[sid] += float(h.score) * weight
        try:
            pr = self.graph.suspect_pagerank()
            for sid, v in pr.items():
                if sid in scores:
                    scores[sid] += float(v) * 1.0
        except Exception:
            pass
        named = [sid for sid, sc in scores.items() if sc > 0 and sid in known]
        if not named:
            return {
                "theory": "Evidence is too thin to name a person. The delay after the cocoa is still open.",
                "primary_suspect": "unknown",
                "confidence": 0.2,
                "sufficient": False,
                "gaps": ["Need a verified link from a household member to the cocoa tray or the delay"],
                "reasoning": "Heuristic fallback: no suspect tagged on retrieved hits.",
                "reformulated_theory": "Re-check who had the tray and the hours between cocoa and convulsions.",
                "next_queries": [
                    "hours between cocoa and convulsions delay",
                    "who prepared the cocoa tray salt",
                    "will signed burnt grate",
                ],
                "citations": _heuristic_citations(hits),
            }
        suspect = max(named, key=lambda sid: scores[sid])
        delay_closed = any(
            h.verification_status == "verified"
            and any(w in h.text.lower() for w in ("hour", "o'clock", "oclock", "delay"))
            and any(w in h.text.lower() for w in ("cocoa", "strychnine", "convuls"))
            for h in hits
        )
        sufficient = attempt >= 2 and delay_closed and scores[suspect] > 0
        return {
            "theory": f"Circumstantial case currently leans toward {self.store.name_for(suspect)}. {theory}",
            "primary_suspect": suspect,
            "confidence": 0.35 if not sufficient else 0.55,
            "sufficient": sufficient,
            "gaps": [] if sufficient else ["Need tighter link between suspect, the cocoa tray, and the delay"],
            "reasoning": "Heuristic fallback (no LLM key): character-tagged hit votes, unverified down-weighted, small PageRank prior.",
            "reformulated_theory": f"Re-check access to cocoa, the delay after bedtime, and the will for {suspect}",
            "next_queries": [
                f"{self.store.name_for(suspect)} cocoa",
                "hours between cocoa and convulsions delay",
                "will signed burnt grate",
            ],
            "citations": _heuristic_citations(hits),
        }


def _heuristic_citations(hits: list[EvidenceHit]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for h in hits:
        if h.verification_status != "verified":
            continue
        claim = h.text.split(".")[0].strip()
        if len(claim) < 12:
            continue
        out.append({"claim": claim[:160], "document_id": h.document_id, "chunk_id": h.chunk_id})
        if len(out) >= 3:
            break
    return out


def _format_hits(hits: list[EvidenceHit]) -> str:
    parts = []
    for h in hits:
        parts.append(
            f"[{h.verification_status}] {h.document_id} / {h.chunk_id} ({h.title})\n{h.text[:500]}"
        )
    return "\n\n".join(parts)


def _normalize_suspect(raw: str, store: CorpusStore) -> str:
    raw_l = (raw or "").lower().replace(" ", "_")
    ids = store.suspect_ids()
    if raw_l in ids:
        return raw_l
    for s in store.suspects():
        if s["name"].lower() in (raw or "").lower():
            return s["id"]
        for al in s.get("aliases") or []:
            if al.lower() in (raw or "").lower():
                return s["id"]
    return raw_l or "unknown"
