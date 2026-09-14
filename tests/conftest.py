from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.store import CorpusStore
from app.graph.evidence_graph import EvidenceGraph
from app.rag.retrieve import HybridRetriever


@pytest.fixture(scope="session")
def processed_dir() -> Path:
    p = ROOT / "data" / "processed"
    if not (p / "chunks.jsonl").exists():
        pytest.skip("Run python preprocess/build_corpus.py first")
    return p


@pytest.fixture(scope="session")
def store(processed_dir: Path) -> CorpusStore:
    s = CorpusStore()
    s.load(processed_dir)
    return s


@pytest.fixture(scope="session")
def retriever(store: CorpusStore) -> HybridRetriever:
    return HybridRetriever(store)


@pytest.fixture(scope="session")
def graph(store: CorpusStore) -> EvidenceGraph:
    return EvidenceGraph(store)


@pytest.fixture(scope="session")
def manifest(processed_dir: Path) -> dict:
    return json.loads((processed_dir / "manifest.json").read_text(encoding="utf-8"))
