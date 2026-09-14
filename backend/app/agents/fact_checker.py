from __future__ import annotations

import uuid
from typing import Any

from app.agents.claims import extract_claims
from app.corpus.store import CorpusStore
from app.graph.evidence_graph import EvidenceGraph
from app.grounding.gate import citations_from_hits, ground_citations
from app.llm.client import LLMClient, LLMError
from app.models.schemas import AgentStep, AtomicClaim, ClaimAttack, EvidenceHit, FactCheckResult, InvestigationResult
from app.rag.retrieve import HybridRetriever

FACT_SYS = """You are the Fact-Checker (defence) on a 1916 poisoning case.
Your job is to ATTACK the Investigator's theory. Search for contradictions, alibis,
rival suspects, timeline conflicts, and weak links.
Do not restate the theory as if you agreed with it.
Use ONLY the evidence passages provided. Unverified documents are rumour, not proof.
Return JSON only.
"""


class FactChecker:
    def __init__(self, store: CorpusStore, retriever: HybridRetriever, graph: EvidenceGraph, llm: LLMClient):
        self.store = store
        self.retriever = retriever
        self.graph = graph
        self.llm = llm

    async def run(self, investigation: InvestigationResult | None, theory: str | None, suspect: str | None) -> FactCheckResult:
        run_id = uuid.uuid4().hex[:12]
        target = theory or (investigation.theory if investigation else "No theory yet")
        primary = suspect or (investigation.primary_suspect if investigation else "")
        atoms = extract_claims(investigation) if investigation else [AtomicClaim(claim_id="T0", text=target)]
        if investigation and investigation.claims:
            atoms = investigation.claims
        queries = self._counter_queries(primary, atoms)
        trace = [
            AgentStep(
                step=1,
                action="adversarial_queries",
                thought="Generate queries that would disprove or rival the current theory.",
                queries=queries,
                decision="retrieve_against_theory",
            )
        ]
        hits = await self._retrieve(queries)
        hits = self.graph.expand_hits(hits)
        trace.append(
            AgentStep(
                step=2,
                action="retrieve_against",
                thought="Hits from counter-queries, not the investigator's original queries.",
                queries=queries,
                hit_ids=[h.chunk_id for h in hits],
                decision="classify",
            )
        )
        classified = await self._classify(target, primary, hits, atoms)
        claim_tuples = []
        for c in classified.get("citations") or []:
            claim_tuples.append((c.get("claim", ""), c.get("document_id", ""), c.get("chunk_id", "")))
        citations = ground_citations(claim_tuples, hits) if claim_tuples else citations_from_hits(target, hits, limit=5)
        marked = set(classified.get("contradiction_chunk_ids") or [])
        if marked:
            contradictions = [c for c in citations if c.chunk_id in marked]
        else:
            flags = self.graph.detect_contradictions(hits)
            flagged = {p for f in flags for p in (f.get("pair") or [])}
            contradictions = [c for c in citations if c.chunk_id in flagged][:3]
        contradictions = [c for c in contradictions if c.verification_status != "unverified"]
        rivals = [r for r in (classified.get("rival_suspects") or []) if r in self.store.suspect_ids() and r != primary]
        delay_note = "Cocoa in the evening and convulsions hours later — access after the tray was left is still open."
        timeline = classified.get("timeline_conflicts") or self.graph.timeline_notes()[:3]
        if delay_note not in timeline:
            timeline = [delay_note] + list(timeline)
        attacks = self._claim_attacks(atoms, classified, hits)
        return FactCheckResult(
            run_id=run_id,
            target_theory=target,
            contradictions=contradictions,
            alternative_explanations=list(classified.get("alternative_explanations") or []),
            timeline_conflicts=list(timeline),
            rival_suspects=rivals,
            theory_weaknesses=list(classified.get("theory_weaknesses") or []),
            citations=citations,
            trace=trace,
            claim_attacks=attacks,
            temporal_notes=[delay_note],
        )

    def _counter_queries(self, primary: str, claims: list[AtomicClaim]) -> list[str]:
        """Adversarial queries aimed at investigator atoms, not a second summary."""
        name = self.store.name_for(primary) if primary else "the accused"
        queries: list[str] = []
        for claim in claims[:4]:
            text = (claim.text or "")[:120]
            if text:
                q = f"evidence against claim: {text}"
                if q not in queries:
                    queries.append(q)
        queries += [
            "hours between cocoa and convulsions who had access to the tray",
            f"alibi for {name} night of the tragedy",
            "another suspect strychnine dispensary cocoa",
            "unverified anonymous letter German spy rumour not proof",
        ]
        return queries[:8]

    def _claim_attacks(self, atoms: list[AtomicClaim], classified: dict[str, Any], hits: list[EvidenceHit]) -> list[ClaimAttack]:
        raw = classified.get("claim_attacks") or []
        by_id = {str(a.get("claim_id")): a for a in raw if isinstance(a, dict)}
        weaknesses = list(classified.get("theory_weaknesses") or [])
        out: list[ClaimAttack] = []
        for i, atom in enumerate(atoms):
            row = by_id.get(atom.claim_id) or {}
            attack = str(row.get("attack") or (weaknesses[i] if i < len(weaknesses) else "") or "Counter-retrieval did not close this claim.")
            chunk_ids = list(row.get("chunk_ids") or [h.chunk_id for h in hits[:2]])
            out.append(ClaimAttack(claim_id=atom.claim_id, claim=atom.text, attack=attack, chunk_ids=chunk_ids[:4]))
        return out

    async def _retrieve(self, queries: list[str]) -> list[EvidenceHit]:
        import asyncio

        async def one(q: str) -> list[EvidenceHit]:
            return self.retriever.search(q, k=5)

        batches = await asyncio.gather(*[one(q) for q in queries[:6]])
        seen: set[str] = set()
        merged: list[EvidenceHit] = []
        for batch in batches:
            for h in batch:
                if h.chunk_id not in seen:
                    seen.add(h.chunk_id)
                    merged.append(h)
        return merged[:12]

    async def _classify(self, theory: str, primary: str, hits: list[EvidenceHit], atoms: list[AtomicClaim]) -> dict[str, Any]:
        evidence = "\n\n".join(
            f"[{h.verification_status}] {h.document_id} / {h.chunk_id}\n{h.text[:450]}" for h in hits
        )
        suspects = ", ".join(s["id"] for s in self.store.suspects())
        claim_block = "\n".join(f"- {a.claim_id}: {a.text}" for a in atoms)
        user = f"""Investigator theory: {theory}
Accused: {primary}
Atomic claims to attack:
{claim_block}
Allowed suspect ids: {suspects}

Counter-evidence:
{evidence}

JSON schema:
{{
  "contradiction_chunk_ids": ["chunk_id"],
  "alternative_explanations": ["string"],
  "timeline_conflicts": ["string"],
  "rival_suspects": ["suspect_id"],
  "theory_weaknesses": ["string"],
  "claim_attacks": [{{"claim_id": "C1", "attack": "string", "chunk_ids": ["chunk_id"]}}],
  "citations": [{{"claim": "string", "document_id": "DOC-...", "chunk_id": "..."}}]
}}
Attack each atomic claim. Do not restate the theory as if you agreed.
Flag unverified documents as rumour, not as disproof.
"""
        if not self.llm.available:
            return self._heuristic(primary, hits, atoms)
        try:
            return await self.llm.complete_json(FACT_SYS, user)
        except (LLMError, Exception):
            return self._heuristic(primary, hits, atoms)

    def _heuristic(self, primary: str, hits: list[EvidenceHit], atoms: list[AtomicClaim]) -> dict[str, Any]:
        rivals = [s["id"] for s in self.store.suspects() if s["id"] != primary][:3]
        unverified = [h for h in hits if h.verification_status == "unverified"]
        weaknesses = [
            "The Investigator has not closed the delay between cocoa and convulsions.",
            "Multiple household members had access to the cocoa tray.",
        ]
        if unverified:
            weaknesses.append(
                f"Document {unverified[0].document_id} is unverified (broken chain of custody) and cannot carry the case."
            )
        flags = self.graph.detect_contradictions(hits)
        flagged = [p for f in flags for p in (f.get("pair") or [])]
        attacks = [
            {
                "claim_id": a.claim_id,
                "attack": weaknesses[i % len(weaknesses)],
                "chunk_ids": [h.chunk_id for h in hits[:2]],
            }
            for i, a in enumerate(atoms)
        ]
        return {
            "contradiction_chunk_ids": flagged[:4],
            "alternative_explanations": [
                "A different member of the household handled the cocoa.",
                "The arrest of Dr Bauerstein may be a wartime panic, not proof.",
            ],
            "timeline_conflicts": self.graph.timeline_notes()[:3],
            "rival_suspects": rivals,
            "theory_weaknesses": weaknesses,
            "claim_attacks": attacks,
            "citations": [],
        }
