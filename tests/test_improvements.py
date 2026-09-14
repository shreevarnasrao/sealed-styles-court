from app.grounding.gate import faithfulness_report
from app.models.schemas import Citation


def _cit(doc, chunk, claim, quote, status, score):
    return Citation(
        document_id=doc, chunk_id=chunk, claim=claim, quote=quote,
        verification_status=status, support_score=score,
    )


def test_rerank_does_not_lead_with_unverified_on_mixed_query(retriever):
    hits = retriever.search("Dr Bauerstein German spy", k=8)
    assert hits
    assert hits[0].document_id != "DOC-ANON-TIP"
    planted = [h for h in hits if h.document_id == "DOC-ANON-TIP"]
    assert all(h.verification_status == "unverified" for h in planted)


def test_rerank_deterministic(retriever):
    a = [h.chunk_id for h in retriever.search("cocoa strychnine", k=8)]
    b = [h.chunk_id for h in retriever.search("cocoa strychnine", k=8)]
    assert a == b


def test_graph_expand_scored(graph, retriever):
    hits = retriever.search("cocoa", k=4)
    expanded = graph.expand_hits(hits, cap=4)
    assert len(expanded) >= len(hits)
    assert len(expanded) <= len(hits) + 4
    graph_sources = [h for h in expanded if h.source == "graph"]
    for h in graph_sources:
        assert h.score >= 0.15


def test_communities_and_pagerank(graph, store):
    groups = graph.communities()
    assert isinstance(groups, list)
    pr = graph.suspect_pagerank()
    assert set(pr.keys()) == store.suspect_ids()
    assert all(v >= 0 for v in pr.values())


def test_contradiction_detector_flags_negation(graph, store):
    from app.models.schemas import EvidenceHit
    a = EvidenceHit(document_id="DOC-CH01", chunk_id="A", text="Evelyn Howard was not in the house that night, she had left for the village.", score=1.0, source="hybrid", verification_status="verified", characters=["evelyn_howard"])
    b = EvidenceHit(document_id="DOC-CH02", chunk_id="B", text="Evelyn Howard was seen in the house quarrelling with Mrs Inglethorp.", score=1.0, source="hybrid", verification_status="verified", characters=["evelyn_howard"])
    flags = graph.detect_contradictions([a, b])
    assert flags
    assert flags[0]["entity"] == "evelyn_howard"


def test_faithfulness_report():
    cites = [
        _cit("DOC-CH05", "DOC-CH05-C001", "cocoa taken up", "cocoa was taken to her room", "verified", 0.6),
        _cit("DOC-CH06", "DOC-CH06-C001", "unrelated claim xyz", "completely different text about will", "verified", 0.05),
    ]
    rep = faithfulness_report(cites)
    assert rep["total_citations"] == 2
    assert rep["supported"] == 1
    assert rep["faithfulness"] == 0.5
    assert rep["checklist"]["has_three_citations"] is False


def test_session_persistence(tmp_path):
    from app.api.session import SessionBook
    p = tmp_path / "sessions.json"
    book = SessionBook(path=p)
    s = book.get("demo")
    s.prediction_locked = True
    s.locked_prediction = {"suspect_id": "alfred_inglethorp"}
    book.save()
    book2 = SessionBook(path=p)
    s2 = book2.get("demo")
    assert s2.prediction_locked is True
    assert s2.locked_prediction["suspect_id"] == "alfred_inglethorp"
