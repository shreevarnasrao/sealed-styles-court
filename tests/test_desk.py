import asyncio

from app.desk.case_desk import CaseDesk, CLOCK, HEADLINE, HERO_QUERY
from app.models.schemas import DeskCommand
from app.runtime import Runtime


def _ready_rt():
    rt = Runtime()
    rt.ingest()
    return rt


def test_brief_is_the_job(store):
    rt = _ready_rt()
    brief = rt.desk.brief()
    assert brief.headline == HEADLINE
    assert brief.hero_query == HERO_QUERY
    assert "Bauerstein" in brief.headline
    assert "sealed" in brief.honesty.lower()
    assert "rumour" in brief.honesty.lower()
    assert brief.clock == CLOCK
    assert brief.delay["from_event"] == "cocoa_evening"


def test_look_pin_lock_advances_phase():
    rt = _ready_rt()
    desk: CaseDesk = rt.desk
    sid = "desk-test-fresh"
    asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="reset")))

    snap = asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="look", query="cocoa")))
    assert snap.phase == "looking"
    assert snap.hits
    assert all(h.document_id not in {"DOC-CH12", "DOC-CH13"} for h in snap.hits)
    assert all(h.source != "graph" for h in snap.hits)

    hit = snap.hits[0]
    snap = asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="pin", hit=hit)))
    assert snap.pins
    assert snap.pins[0].chunk_id == hit.chunk_id

    snap = asyncio.run(
        desk.handle(sid, DeskCommand(session_id=sid, action="lock", suspect_id="alfred_inglethorp"))
    )
    assert snap.phase == "locked"
    assert snap.locked
    assert "DOC-" in " ".join(snap.locked_prediction["evidence_ids"])


def test_agents_sealed_until_lock():
    rt = _ready_rt()
    desk = rt.desk
    sid = "seal-test-fresh"
    asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="reset")))
    asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="look", query="cocoa")))
    snap = asyncio.run(desk.handle(sid, DeskCommand(session_id=sid, action="prosecute")))
    assert snap.agents_sealed
    assert snap.investigation is None


def test_stamp_requires_lock():
    rt = _ready_rt()
    sid = "stamp-no-lock"
    asyncio.run(rt.desk.handle(sid, DeskCommand(session_id=sid, action="reset")))
    try:
        asyncio.run(rt.desk.handle(sid, DeskCommand(session_id=sid, action="stamp", suspect_id="alfred_inglethorp")))
        raise AssertionError("stamp without lock should fail")
    except Exception as e:
        assert "Lock" in str(e) or getattr(e, "status_code", None) == 400
