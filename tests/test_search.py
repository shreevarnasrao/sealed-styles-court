def test_strychnine_retrieves_something(retriever):
    hits = retriever.search("strychnine", k=8)
    assert hits
    blob = " ".join(h.text.lower() for h in hits)
    assert "strychnine" in blob


def test_cocoa_retrieves_something(retriever):
    hits = retriever.search("cocoa night of the tragedy", k=8)
    assert hits
    blob = " ".join(h.text.lower() for h in hits)
    assert "cocoa" in blob


def test_never_returns_sealed_ids(retriever, store):
    hits = retriever.search("Poirot explains the murderer", k=10)
    sealed = store.sealed_ids()
    assert all(h.document_id not in sealed for h in hits)


def test_cocoa_query_does_not_inject_planted_letter(retriever):
    hits = retriever.search("cocoa salt tray bedtime", k=8)
    assert not any(h.document_id == "DOC-ANON-TIP" for h in hits)


def test_planted_letter_retrieved_by_its_own_text(retriever):
    hits = retriever.search("Berlin chemical works nerve agent unsigned", k=8)
    assert any(h.document_id == "DOC-ANON-TIP" for h in hits)


def test_no_force_injected_rumour_score(retriever):
    """Rumour keywords must not append DOC-ANON-TIP at the magic score 0.05."""
    hits = retriever.search("Dr Bauerstein German spy letter rumour", k=8)
    for h in hits:
        if h.document_id == "DOC-ANON-TIP":
            assert abs(float(h.score) - 0.05) > 1e-6
