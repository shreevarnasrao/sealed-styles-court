from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    DeskCommand,
    FactCheckRequest,
    InterrogateRequest,
    InvestigateRequest,
    LockPredictionRequest,
    SearchRequest,
    SealedEnvelope,
    VerdictSubmission,
)
from app.runtime import Runtime

router = APIRouter()
rt = Runtime()


def _need() -> None:
    if not rt.ready:
        raise HTTPException(503, "Corpus not ingested. POST /ingest first.")


def _maybe_seal(session, payload):
    if session.prediction_locked:
        return payload
    return SealedEnvelope()


@router.get("/health")
def health():
    return {"ok": True, "ready": rt.ready, "llm": rt.llm.available}


@router.post("/ingest")
def ingest():
    try:
        return rt.ingest()
    except FileNotFoundError as e:
        raise HTTPException(500, str(e)) from e


@router.get("/brief")
def brief():
    _need()
    return rt.desk.brief()


@router.get("/dossier/{session_id}")
def dossier(session_id: str):
    _need()
    return rt.desk.snapshot(session_id)


@router.post("/desk")
async def desk(cmd: DeskCommand):
    _need()
    return await rt.desk.handle(cmd.session_id, cmd)


@router.get("/case")
def case_file():
    _need()
    onto = rt.store.ontology
    return {
        "case_id": "styles_court",
        "title": onto.get("title", "The Styles Court Case File"),
        "setting": onto.get("setting"),
        "victim": onto.get("victim"),
        "suspects": rt.store.suspects(),
        "documents": [
            {
                "document_id": d["document_id"],
                "title": d.get("title"),
                "doc_type": d.get("doc_type"),
                "verification_status": d.get("verification_status"),
            }
            for d in rt.store.documents
        ],
        "manifest": rt.store.manifest,
        "brief": rt.desk.brief().model_dump(),
    }


@router.get("/graph")
def graph():
    _need()
    return rt.graph.payload()


@router.post("/search_evidence")
async def search_evidence(req: SearchRequest):
    _need()
    snap = await rt.desk.handle(
        req.session_id,
        DeskCommand(session_id=req.session_id, action="look", query=req.query, k=req.k),
    )
    return {
        "query": req.query,
        "hits": [h.model_dump() for h in snap.hits],
        "contradictions": snap.contradictions,
    }


@router.post("/interrogate")
async def interrogate(req: InterrogateRequest):
    _need()
    snap = await rt.desk.handle(
        req.session_id,
        DeskCommand(
            session_id=req.session_id,
            action="ask",
            candidate_id=req.candidate_id,
            question=req.question,
        ),
    )
    if snap.last_answer is None:
        raise HTTPException(500, "Interrogation produced no statement.")
    return snap.last_answer


@router.post("/lock_prediction")
async def lock_prediction(req: LockPredictionRequest):
    _need()
    snap = await rt.desk.handle(
        req.session_id,
        DeskCommand(
            session_id=req.session_id,
            action="lock",
            suspect_id=req.suspect_id,
            evidence_ids=req.evidence_ids,
            rationale=req.rationale,
        ),
    )
    return {"locked": True, "prediction": snap.locked_prediction}


@router.get("/session/{session_id}")
def get_session(session_id: str):
    _need()
    snap = rt.desk.snapshot(session_id)
    return {
        "session_id": snap.session_id,
        "prediction_locked": snap.locked,
        "locked_prediction": snap.locked_prediction,
        "searches": snap.searches,
        "interrogations": snap.interrogations,
        "has_investigation": snap.investigation is not None,
        "has_fact_check": snap.fact_check is not None,
        "phase": snap.phase,
        "pins": len(snap.pins),
    }


@router.post("/investigate")
async def investigate(req: InvestigateRequest):
    _need()
    session = rt.sessions.get(req.session_id)
    snap = await rt.desk.handle(
        req.session_id,
        DeskCommand(session_id=req.session_id, action="prosecute", focus=req.focus, rerun=req.rerun),
    )
    payload = _maybe_seal(session, session.investigation)
    if isinstance(payload, SealedEnvelope):
        return payload
    from app.grounding.gate import faithfulness_report

    data = payload.model_dump()
    data["faithfulness"] = faithfulness_report(payload.citations)
    data["cached"] = bool(snap.investigation and snap.investigation.cached)
    return data


@router.post("/fact_check")
async def fact_check(req: FactCheckRequest):
    _need()
    session = rt.sessions.get(req.session_id)
    await rt.desk.handle(
        req.session_id,
        DeskCommand(
            session_id=req.session_id,
            action="defend",
            theory=req.theory,
            suspect_id=req.primary_suspect,
            rerun=req.rerun,
        ),
    )
    return _maybe_seal(session, session.fact_check)


@router.get("/timeline")
def timeline():
    _need()
    return {
        "events": rt.graph.timeline_notes(),
        "structured": rt.store.ontology.get("key_events") or [],
        "delay": rt.desk.brief().delay,
    }


@router.get("/communities")
def communities():
    _need()
    try:
        groups = rt.graph.communities()
    except Exception:
        groups = []
    try:
        pagerank = rt.graph.suspect_pagerank()
    except Exception:
        pagerank = {}
    return {"communities": groups, "suspect_pagerank": pagerank}


@router.get("/faithfulness/{run_id}")
def faithfulness(run_id: str, session_id: str = "default"):
    _need()
    from app.grounding.gate import faithfulness_report

    session = rt.sessions.get(session_id)
    if not session.prediction_locked:
        return SealedEnvelope(message="Lock a prediction to unseal faithfulness.")
    inv = session.investigation
    if inv and inv.run_id == run_id:
        return faithfulness_report(inv.citations)
    raise HTTPException(404, "Unknown run_id")


@router.get("/traces/{run_id}")
def traces(run_id: str, session_id: str = "default"):
    _need()
    session = rt.sessions.get(session_id)
    if not session.prediction_locked:
        return SealedEnvelope(message="Lock a prediction to unseal agent traces.")
    if session.investigation and session.investigation.run_id == run_id:
        return session.investigation.trace
    if session.fact_check and session.fact_check.run_id == run_id:
        return session.fact_check.trace
    raise HTTPException(404, "Unknown run_id")


@router.post("/submit_verdict")
async def submit_verdict(req: VerdictSubmission):
    _need()
    snap = await rt.desk.handle(
        req.session_id,
        DeskCommand(
            session_id=req.session_id,
            action="stamp",
            suspect_id=req.suspect_id,
            evidence_ids=req.evidence_ids,
            rationale=req.rationale,
        ),
    )
    receipt = snap.receipt
    if receipt is None:
        raise HTTPException(500, "Stamp produced no docket.")
    return {
        "correct_suspect": receipt.correct_suspect,
        "evidence_overlap": receipt.evidence_overlap,
        "notes": receipt.notes,
        "locked_prediction_matched": (
            (snap.locked_prediction or {}).get("suspect_id") == req.suspect_id if snap.locked_prediction else None
        ),
        "receipt": receipt.model_dump(),
    }
