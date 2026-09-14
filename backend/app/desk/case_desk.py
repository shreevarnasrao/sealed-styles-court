"""CaseDesk — one deep module for the investigation journey.

Callers (FastAPI routes, tests, the UI) learn three entry points:
  brief()     — wound, clock, honesty, hero query. No session.
  snapshot()  — full desk view for a session.
  handle()    — every mutation (look, ask, pin, lock, prosecute, defend, stamp).

State, grounding, both agents, and the docket live behind this seam.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

from app.models.schemas import (
    CaseBrief,
    DebateLine,
    DeskCommand,
    DeskSnapshot,
    EvidenceHit,
    FactCheckResult,
    InterrogateResponse,
    InvestigationResult,
    Receipt,
    VerdictScore,
    VerdictSubmission,
)
from app.verdict.score import score as score_verdict

PHASES = ("opened", "looking", "locked", "argued", "stamped")

HONESTY = (
    "Independent recruitment demo. Not a court. "
    "Chapters XII–XIII are sealed. One planted letter is rumour."
)
HEADLINE = "This letter names Dr Bauerstein."
WOUND = (
    "An unsigned tip says he put a German powder in the cocoa. "
    "The chain of custody is broken. Chapters XII–XIII are not in this file."
)
CLOCK = "Cocoa in the evening. Convulsions hours later. That delay is the case."
HERO_QUERY = "Bauerstein German powder cocoa 17 July"
HERO_QUESTION = "Where were you when the cocoa was taken up, and who had the tray after that?"
HERO_SUSPECT = "dr_bauerstein"
COCOA_QUERY = "cocoa strychnine hours delay"
MOCKED = (
    "This file is a public-domain novel recomposed as a case. "
    "Agents may run on heuristics if no LLM key is set. We do not file anything."
)
DELAY = {
    "from_event": "cocoa_evening",
    "to_event": "death",
    "note": CLOCK,
}


def _advance(current: str, target: str) -> str:
    try:
        if PHASES.index(target) > PHASES.index(current):
            return target
    except ValueError:
        return target
    return current


def _hit_from_raw(raw: dict | EvidenceHit) -> EvidenceHit:
    if isinstance(raw, EvidenceHit):
        return raw
    return EvidenceHit.model_validate(raw)


class CaseDesk:
    def __init__(self, runtime: Any) -> None:
        self.rt = runtime
        self._locks: dict[str, asyncio.Lock] = {}

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def brief(self) -> CaseBrief:
        onto = self.rt.store.ontology if self.rt.ready else {}
        victim = (onto.get("victim") or {}).get("name", "Emily Inglethorp")
        setting = onto.get("setting", "Styles Court, Essex, July 1916")
        suspects = self.rt.store.suspects() if self.rt.ready else []
        return CaseBrief(
            case_id=onto.get("case_id", "styles_court"),
            headline=HEADLINE,
            wound=WOUND,
            honesty=HONESTY,
            clock=CLOCK,
            hero_query=HERO_QUERY,
            hero_question=HERO_QUESTION,
            hero_suspect_id=HERO_SUSPECT,
            victim=victim,
            setting=setting,
            suspects=suspects,
            delay=DELAY,
            mocked=MOCKED,
            llm_available=bool(self.rt.llm.available),
        )

    def snapshot(self, session_id: str) -> DeskSnapshot:
        session = self.rt.sessions.get(session_id)
        locked = bool(session.prediction_locked)
        inv = session.investigation
        fc = session.fact_check
        if inv and not locked:
            inv = None
        if fc and not locked:
            fc = None
        pins = [_hit_from_raw(p) for p in (session.pins or [])]
        hits = [_hit_from_raw(h) for h in (getattr(session, "last_hits", None) or [])]
        last_answer = None
        if getattr(session, "last_answer", None):
            last_answer = InterrogateResponse.model_validate(session.last_answer)
        receipt = None
        if session.verdict:
            receipt = Receipt.model_validate(session.verdict)
        return DeskSnapshot(
            session_id=session_id,
            phase=session.phase or "opened",
            brief=self.brief(),
            hits=hits,
            contradictions=list(getattr(session, "last_contradictions", None) or []),
            pins=pins,
            last_answer=last_answer,
            locked=locked,
            locked_prediction=session.locked_prediction,
            investigation=inv,
            fact_check=fc,
            debate=_debate(inv, fc) if inv and fc else [],
            receipt=receipt,
            agents_sealed=not locked,
            cached_agents=bool((inv and inv.cached) or (fc and fc.cached)),
            searches=session.searches,
            interrogations=session.interrogations,
        )

    async def handle(self, session_id: str, cmd: DeskCommand) -> DeskSnapshot:
        if not self.rt.ready:
            raise HTTPException(503, "Corpus not ingested. POST /ingest first.")
        async with self._session_lock(session_id):
            return await self._handle_locked(session_id, cmd)

    async def _handle_locked(self, session_id: str, cmd: DeskCommand) -> DeskSnapshot:
        session = self.rt.sessions.get(session_id)
        action = cmd.action
        if action == "reset":
            session.prediction_locked = False
            session.locked_prediction = None
            session.investigation = None
            session.fact_check = None
            session.pins = []
            session.phase = "opened"
            session.verdict = None
            session.last_hits = []
            session.last_contradictions = []
            session.last_answer = None
            session.searches = 0
            session.interrogations = 0
            self.rt.sessions.save()
            return self.snapshot(session_id)
        if action == "look":
            self._look(session, cmd.query or HERO_QUERY, cmd.k)
        elif action == "ask":
            if not cmd.candidate_id:
                raise HTTPException(400, "candidate_id required")
            session.interrogations += 1
            result = await self.rt.interrogator.ask(cmd.candidate_id, cmd.question or HERO_QUESTION)
            session.last_answer = result.model_dump()
            session.phase = _advance(session.phase, "looking")
        elif action == "pin":
            if cmd.hit is None:
                raise HTTPException(400, "hit required")
            self._pin(session, cmd.hit)
        elif action == "unpin":
            if not cmd.chunk_id:
                raise HTTPException(400, "chunk_id required")
            session.pins = [p for p in session.pins if _hit_from_raw(p).chunk_id != cmd.chunk_id]
        elif action == "lock":
            self._lock(session, cmd)
        elif action == "prosecute":
            await self._prosecute(session, cmd.focus, cmd.rerun)
        elif action == "defend":
            await self._defend(session, cmd.theory, cmd.rerun, cmd.suspect_id)
        elif action == "stamp":
            self._stamp(session, cmd)
        else:
            raise HTTPException(400, f"Unknown action {action}")
        self.rt.sessions.save()
        return self.snapshot(session_id)

    def _look(self, session: Any, query: str, k: int) -> None:
        hits = self.rt.retriever.search(query, k=k)
        sealed = self.rt.store.sealed_ids()
        hits = [h for h in hits if h.document_id not in sealed]
        try:
            contradictions = self.rt.graph.detect_contradictions(hits)
        except Exception:
            contradictions = []
        session.last_hits = [h.model_dump() for h in hits]
        session.last_contradictions = contradictions
        session.last_query = query
        session.searches += 1
        session.phase = _advance(session.phase, "looking")

    def _pin(self, session: Any, hit: EvidenceHit) -> None:
        pins = [_hit_from_raw(p) for p in session.pins]
        if any(p.chunk_id == hit.chunk_id for p in pins):
            return
        pins.append(hit)
        session.pins = [p.model_dump() for p in pins[-12:]]
        session.phase = _advance(session.phase, "looking")

    def _lock(self, session: Any, cmd: DeskCommand) -> None:
        if not cmd.suspect_id or cmd.suspect_id not in self.rt.store.suspect_ids():
            raise HTTPException(400, "Unknown suspect_id")
        evidence = list(cmd.evidence_ids)
        if not evidence:
            evidence = [_hit_from_raw(p).document_id for p in session.pins]
            # unique, keep order
            seen: set[str] = set()
            ordered: list[str] = []
            for e in evidence:
                if e not in seen:
                    seen.add(e)
                    ordered.append(e)
            evidence = ordered
        session.prediction_locked = True
        session.locked_prediction = {
            "suspect_id": cmd.suspect_id,
            "evidence_ids": evidence,
            "rationale": cmd.rationale,
        }
        session.phase = _advance(session.phase, "locked")

    async def _prosecute(self, session: Any, focus: str | None, rerun: bool) -> None:
        if session.investigation is None or rerun:
            session.investigation = await self.rt.investigator.run(focus=focus)
            session.fact_check = None
            if session.investigation:
                session.investigation.cached = False
        elif session.investigation:
            session.investigation.cached = True
        if session.prediction_locked:
            session.phase = _advance(session.phase, "argued")

    async def _defend(self, session: Any, theory: str | None, rerun: bool, suspect: str | None = None) -> None:
        if session.investigation is None:
            await self._prosecute(session, None, False)
        if session.fact_check is None or rerun:
            session.fact_check = await self.rt.fact_checker.run(
                session.investigation,
                theory,
                suspect or (session.locked_prediction or {}).get("suspect_id"),
            )
            if session.fact_check:
                session.fact_check.cached = False
        elif session.fact_check:
            session.fact_check.cached = True
        if session.prediction_locked:
            session.phase = _advance(session.phase, "argued")

    def _stamp(self, session: Any, cmd: DeskCommand) -> None:
        if not session.prediction_locked:
            raise HTTPException(400, "Lock a prediction before you stamp.")
        locked = session.locked_prediction or {}
        suspect = cmd.suspect_id or locked.get("suspect_id")
        if not suspect or suspect not in self.rt.store.suspect_ids():
            raise HTTPException(400, "Unknown suspect_id")
        evidence = cmd.evidence_ids or locked.get("evidence_ids") or [
            _hit_from_raw(p).document_id for p in session.pins
        ]
        submission = VerdictSubmission(
            session_id=session.session_id,
            suspect_id=suspect,
            evidence_ids=list(evidence),
            rationale=cmd.rationale or locked.get("rationale") or "",
        )
        scored = score_verdict(submission, session.locked_prediction)
        receipt = _receipt(scored, session, self.rt.store.name_for(suspect), list(evidence))
        session.verdict = receipt.model_dump()
        session.phase = _advance(session.phase, "stamped")


def _debate(inv: InvestigationResult | None, fc: FactCheckResult | None) -> list[DebateLine]:
    if not inv or not fc:
        return []
    attacks = {a.claim_id: a for a in (fc.claim_attacks or [])}
    by_text = {a.claim.lower(): a for a in (fc.claim_attacks or [])}
    lines: list[DebateLine] = []
    for c in inv.claims or []:
        a = attacks.get(c.claim_id) or by_text.get(c.text.lower())
        lines.append(
            DebateLine(
                claim_id=c.claim_id,
                claim=c.text,
                attack=(a.attack if a else (fc.theory_weaknesses[0] if fc.theory_weaknesses else "No counter-claim retrieved.")),
                verified=c.verification_status == "verified",
            )
        )
    if not lines:
        for i, w in enumerate((fc.theory_weaknesses or [])[:4]):
            lines.append(DebateLine(claim_id=f"W{i+1}", claim=inv.theory[:180], attack=w, verified=True))
    return lines[:6]


def _receipt(scored: VerdictScore, session: Any, name: str, evidence: list[str]) -> Receipt:
    inv = session.investigation
    fc = session.fact_check
    if inv is None or fc is None:
        stamp: str = "too_weak"
        next_action = "Unseal the prosecution and defence before you treat this as a finished night."
    elif scored.correct_suspect:
        stamp = "supports"
        next_action = "Keep the docket. Re-open the delay and the will if you need the other name."
    else:
        stamp = "does_not_show"
        next_action = "Re-open the cocoa, the will, and who benefited from being loudly suspected."
    attack = ""
    if fc:
        attack = (fc.theory_weaknesses[0] if fc.theory_weaknesses else "") or (
            fc.alternative_explanations[0] if fc.alternative_explanations else ""
        )
    return Receipt(
        title="Styles Court — jury docket",
        prediction=name,
        evidence=evidence,
        investigator_theory=(inv.theory if inv else "Prosecution file not opened."),
        fact_checker_attack=attack or "Defence file not opened.",
        stamp=stamp,  # type: ignore[arg-type]
        notes=scored.notes,
        next_action=next_action,
        honesty=HONESTY,
        correct_suspect=scored.correct_suspect,
        evidence_overlap=scored.evidence_overlap,
    )
