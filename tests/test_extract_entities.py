"""Entity extraction must come from the text, not only from styles.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "preprocess"))

from extract_entities import extract_entities, merge_ontology  # noqa: E402

SAMPLE = """
Mr. Inglethorp had married Mrs. Inglethorp that summer at Styles Court in Essex.
John Cavendish and Lawrence Cavendish were in the house. Miss Howard quarrelled
and left for the village. Mary Cavendish walked in the garden. Cynthia Murdoch
worked at the dispensary. Dr. Bauerstein of London called in the evening.
Cocoa was taken up to her room. Later she died of strychnine. The will had been
signed. Captain Hastings and Monsieur Poirot discussed the bromide powders.
"""


def test_extracts_people_places_objects_from_prose():
    ents = extract_entities(SAMPLE)
    people = {p["id"] for p in ents["people"]}
    assert "john_cavendish" in people
    assert "lawrence_cavendish" in people
    assert "dr_bauerstein" in people
    places = {p["id"] for p in ents["places"]}
    assert "styles_court" in places or "essex" in places
    objects = {o["id"] for o in ents["objects"]}
    assert "cocoa" in objects
    assert "strychnine" in objects


def test_merge_keeps_yaml_suspects_and_adds_extracted_people():
    seed = {
        "suspects": [{"id": "john_cavendish", "name": "John Cavendish", "aliases": ["John"]}],
        "other_people": [],
        "places": [],
        "objects": [],
        "victim": {"id": "emily_inglethorp", "name": "Emily Inglethorp", "aliases": []},
    }
    merged = merge_ontology(seed, extract_entities(SAMPLE))
    ids = {s["id"] for s in merged["suspects"]}
    assert "john_cavendish" in ids
    extra = {p["id"] for p in merged["other_people"]}
    assert "dr_bauerstein" in extra or "dr_bauerstein" in ids
    assert merged.get("extraction", {}).get("method") == "ingest_text"


def test_extracts_from_gutenberg_body():
    raw = ROOT / "data" / "raw" / "styles.txt"
    if not raw.exists():
        return
    text = raw.read_text(encoding="utf-8")[:80_000]
    ents = extract_entities(text)
    people = {p["id"] for p in ents["people"]}
    assert "john_cavendish" in people
    assert "evelyn_howard" in people or "miss_howard" in people
