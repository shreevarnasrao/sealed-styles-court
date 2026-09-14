from __future__ import annotations

import json
from pathlib import Path

from app.config import ONTOLOGY, PROCESSED
from app.models.schemas import EvidenceHit

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


class Chunk:
    __slots__ = (
        "chunk_id",
        "document_id",
        "title",
        "doc_type",
        "text",
        "verification_status",
        "characters",
        "places",
        "objects",
    )

    def __init__(self, raw: dict):
        self.chunk_id = raw["chunk_id"]
        self.document_id = raw["document_id"]
        self.title = raw.get("title", "")
        self.doc_type = raw.get("doc_type", "chapter")
        self.text = raw["text"]
        self.verification_status = raw.get("verification_status", "verified")
        self.characters = list(raw.get("characters") or [])
        self.places = list(raw.get("places") or [])
        self.objects = list(raw.get("objects") or [])

    def as_hit(self, score: float, source: str) -> EvidenceHit:
        return EvidenceHit(
            document_id=self.document_id,
            chunk_id=self.chunk_id,
            text=self.text,
            score=float(score),
            source=source,  # type: ignore[arg-type]
            verification_status=self.verification_status,  # type: ignore[arg-type]
            title=self.title,
            characters=self.characters,
        )


class CorpusStore:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.by_id: dict[str, Chunk] = {}
        self.documents: list[dict] = []
        self.ontology: dict = {}
        self.manifest: dict = {}
        self.loaded = False

    def load(self, processed: Path | None = None) -> None:
        root = processed or PROCESSED
        chunks_path = root / "chunks.jsonl"
        docs_path = root / "documents.jsonl"
        if not chunks_path.exists():
            raise FileNotFoundError(f"Run preprocess first: missing {chunks_path}")
        self.chunks = [Chunk(json.loads(line)) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.documents = [
            json.loads(line) for line in docs_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        man = root / "manifest.json"
        self.manifest = json.loads(man.read_text(encoding="utf-8")) if man.exists() else {}
        self.ontology = _load_ontology()
        self.loaded = True

    def get(self, chunk_id: str) -> Chunk | None:
        return self.by_id.get(chunk_id)

    def sealed_ids(self) -> set[str]:
        return set(self.manifest.get("sealed_document_ids") or [])

    def suspects(self) -> list[dict]:
        return list(self.ontology.get("suspects") or [])

    def suspect_ids(self) -> set[str]:
        return {s["id"] for s in self.suspects()}

    def name_for(self, sid: str) -> str:
        for s in self.suspects():
            if s["id"] == sid:
                return s["name"]
        return sid


def _load_ontology() -> dict:
    processed_json = PROCESSED / "ontology.json"
    if processed_json.exists():
        return json.loads(processed_json.read_text(encoding="utf-8"))
    if yaml is None:
        raise RuntimeError("Ontology not available")
    return yaml.safe_load(ONTOLOGY.read_text(encoding="utf-8"))
