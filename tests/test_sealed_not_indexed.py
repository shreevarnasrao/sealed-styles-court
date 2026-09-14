from __future__ import annotations

from pathlib import Path


def test_sealed_chapters_not_in_chunks(store, manifest):
    sealed = set(manifest["sealed_document_ids"])
    assert sealed, "expected sealed documents"
    indexed = {c.document_id for c in store.chunks}
    assert sealed.isdisjoint(indexed)


def test_sealed_text_not_in_index(store):
    root = Path(__file__).resolve().parents[1]
    sealed_dir = root / "data" / "sealed" / "chapters"
    assert sealed_dir.exists()
    corpus = " ".join(c.text for c in store.chunks)
    for p in sealed_dir.glob("*.txt"):
        sample = " ".join(p.read_text(encoding="utf-8").split()[40:80])
        assert sample
        assert sample not in corpus


def test_unverified_planted_letter_present(manifest, store):
    assert "DOC-ANON-TIP" in manifest["unverified_document_ids"]
    unverified = [c for c in store.chunks if c.verification_status == "unverified"]
    assert unverified
    assert any("Bauerstein" in c.text for c in unverified)
