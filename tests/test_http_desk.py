from fastapi.testclient import TestClient

from app.main import app


def test_http_lock_then_agents_then_stamp():
    client = TestClient(app)
    sid = "http-flow"
    if not client.get("/health").json().get("ready"):
        ingested = client.post("/ingest")
        assert ingested.status_code == 200, ingested.text
    assert client.get("/health").json()["ready"] is True
    client.post("/desk", json={"session_id": sid, "action": "reset"})
    look = client.post("/desk", json={"session_id": sid, "action": "look", "query": "Bauerstein German powder"}).json()
    assert look["hits"]
    lock = client.post(
        "/lock_prediction",
        json={"session_id": sid, "suspect_id": "dr_bauerstein", "evidence_ids": [look["hits"][0]["document_id"]]},
    ).json()
    assert lock["locked"] is True
    inv = client.post("/investigate", json={"session_id": sid}).json()
    assert inv.get("status") != "sealed"
    assert inv.get("theory")
    fc = client.post("/fact_check", json={"session_id": sid}).json()
    assert fc.get("status") != "sealed"
    inv_q = {q for step in inv.get("trace") or [] for q in step.get("queries") or []}
    fc_q = {q for step in fc.get("trace") or [] for q in step.get("queries") or []}
    assert inv_q and fc_q and inv_q != fc_q
    verdict = client.post(
        "/submit_verdict",
        json={"session_id": sid, "suspect_id": "dr_bauerstein", "evidence_ids": [look["hits"][0]["document_id"]]},
    ).json()
    assert "receipt" in verdict
    assert verdict["receipt"]["stamp"] in {"supports", "does_not_show", "too_weak"}
