"""Build the Styles Court case file from Project Gutenberg #863.

Sealed chapters (XII, XIII) are written only under data/sealed/ and never
into the retrievable chunk index.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from extract_entities import extract_entities, merge_ontology

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "styles.txt"
PLANTED = ROOT / "data" / "planted" / "DOC-ANON-TIP.md"
ONTOLOGY = ROOT / "data" / "ontology" / "styles.yaml"
OUT_DOCS = ROOT / "data" / "processed" / "documents.jsonl"
OUT_CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
OUT_MANIFEST = ROOT / "data" / "processed" / "manifest.json"
SEALED_DIR = ROOT / "data" / "sealed" / "chapters"

ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
}
CHAPTER_RE = re.compile(r"^CHAPTER ([IVX]+)\.\s*$", re.M)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
SEALED_CHAPTERS = {12, 13}
TARGET_WORDS = 160
OVERLAP_WORDS = 40


def load_ontology() -> dict:
    text = ONTOLOGY.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except Exception:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict:
    """Tiny fallback so preprocess does not require PyYAML at runtime."""
    # The committed ontology is the source of truth; this parser is only a
    # last resort and is not used if PyYAML is installed.
    suspects = []
    for line in text.splitlines():
        if line.strip().startswith("- id:"):
            suspects.append({"id": line.split(":", 1)[1].strip(), "aliases": []})
    return {"suspects": suspects, "other_people": [], "places": [], "objects": []}


def alias_index(onto: dict) -> list[tuple[str, str, str]]:
    """Return (alias_lower, entity_id, kind) longest-first."""
    rows: list[tuple[str, str, str]] = []

    def add(ent: dict, kind: str) -> None:
        names = [ent.get("name", "")] + list(ent.get("aliases") or [])
        for n in names:
            n = (n or "").strip()
            if n:
                rows.append((n.lower(), ent["id"], kind))

    add(onto["victim"], "victim")
    for s in onto.get("suspects") or []:
        add(s, "suspect")
    for p in onto.get("other_people") or []:
        add(p, "person")
    for p in onto.get("places") or []:
        add(p, "place")
    for o in onto.get("objects") or []:
        add(o, "object")
    rows.sort(key=lambda r: len(r[0]), reverse=True)
    return rows


def tag_text(text: str, aliases: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    low = text.lower()
    found: dict[str, set[str]] = {"characters": set(), "places": set(), "objects": set()}
    for alias, eid, kind in aliases:
        if alias and alias in low:
            if kind in {"victim", "suspect", "person"}:
                found["characters"].add(eid)
            elif kind == "place":
                found["places"].add(eid)
            elif kind == "object":
                found["objects"].add(eid)
    return {k: sorted(v) for k, v in found.items()}


def extract_body(raw: str) -> str:
    start = raw.find("*** START OF THE PROJECT GUTENBERG")
    if start != -1:
        raw = raw[start:]
        nl = raw.find("\n")
        raw = raw[nl + 1 :]
    end = raw.find("*** END OF THE PROJECT GUTENBERG")
    if end != -1:
        raw = raw[:end]
    return raw.replace("\r\n", "\n")


def split_chapters(body: str) -> list[dict]:
    matches = list(CHAPTER_RE.finditer(body))
    chapters = []
    for i, m in enumerate(matches):
        roman = m.group(1)
        num = ROMAN[roman]
        start = m.end()
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:stop].strip()
        lines = block.split("\n", 1)
        title = lines[0].strip().strip('"“”')
        text = lines[1].strip() if len(lines) > 1 else ""
        text = re.sub(r"\n{3,}", "\n\n", text)
        chapters.append(
            {
                "number": num,
                "roman": roman,
                "title": title,
                "text": text,
            }
        )
    return chapters


def chunk_words(text: str, doc_id: str) -> list[dict]:
    words = text.split()
    if not words:
        return []
    chunks = []
    i = 0
    n = 0
    while i < len(words):
        piece = words[i : i + TARGET_WORDS]
        n += 1
        chunks.append(
            {
                "chunk_id": f"{doc_id}-C{n:03d}",
                "text": " ".join(piece),
            }
        )
        if i + TARGET_WORDS >= len(words):
            break
        i += TARGET_WORDS - OVERLAP_WORDS
    return chunks


def parse_planted(md: str) -> dict:
    m = FRONTMATTER_RE.match(md.strip())
    if not m:
        raise ValueError("Planted letter missing YAML frontmatter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return {**meta, "text": m.group(2).strip()}


def main() -> int:
    if not RAW.exists():
        print(f"Missing {RAW}. Download Gutenberg 863 first.", file=sys.stderr)
        return 1
    onto = load_ontology()
    body = extract_body(RAW.read_text(encoding="utf-8"))
    onto = merge_ontology(onto, extract_entities(body))
    aliases = alias_index(onto)
    chapters = split_chapters(body)
    if len(chapters) < 13:
        print(f"Expected 13 chapters, got {len(chapters)}", file=sys.stderr)
        return 1

    SEALED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DOCS.parent.mkdir(parents=True, exist_ok=True)

    documents = []
    chunks = []
    sealed_docs = []

    for ch in chapters:
        doc_id = f"DOC-CH{ch['number']:02d}"
        doc = {
            "document_id": doc_id,
            "title": f"Chapter {ch['roman']}. {ch['title']}",
            "doc_type": "chapter",
            "chapter": ch["number"],
            "verification_status": "verified",
            "text": ch["text"],
        }
        if ch["number"] in SEALED_CHAPTERS:
            (SEALED_DIR / f"{doc_id}.txt").write_text(ch["text"], encoding="utf-8")
            sealed_docs.append(doc_id)
            continue
        documents.append(doc)
        for c in chunk_words(ch["text"], doc_id):
            tags = tag_text(c["text"], aliases)
            chunks.append(
                {
                    **c,
                    "document_id": doc_id,
                    "title": doc["title"],
                    "doc_type": "chapter",
                    "verification_status": "verified",
                    "characters": tags["characters"],
                    "places": tags["places"],
                    "objects": tags["objects"],
                }
            )

    planted = parse_planted(PLANTED.read_text(encoding="utf-8"))
    pdoc = {
        "document_id": planted["document_id"],
        "title": planted["title"],
        "doc_type": planted.get("doc_type", "letter"),
        "chapter": None,
        "verification_status": "unverified",
        "text": planted["text"],
        "chain_of_custody": planted.get("chain_of_custody", "broken"),
    }
    documents.append(pdoc)
    for c in chunk_words(planted["text"], pdoc["document_id"]):
        tags = tag_text(c["text"], aliases)
        chunks.append(
            {
                **c,
                "document_id": pdoc["document_id"],
                "title": pdoc["title"],
                "doc_type": pdoc["doc_type"],
                "verification_status": "unverified",
                "characters": tags["characters"],
                "places": tags["places"],
                "objects": tags["objects"],
            }
        )

    with OUT_DOCS.open("w", encoding="utf-8") as f:
        for d in documents:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with OUT_CHUNKS.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    sealed_snippets = []
    for p in SEALED_DIR.glob("*.txt"):
        sealed_snippets.append(p.read_text(encoding="utf-8")[:400])

    manifest = {
        "case_id": "styles_court",
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "sealed_document_ids": sealed_docs,
        "unverified_document_ids": [pdoc["document_id"]],
        "indexed_document_ids": [d["document_id"] for d in documents],
        "suspect_ids": [s["id"] for s in onto.get("suspects") or []],
        "extraction": onto.get("extraction") or {},
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ROOT / "data" / "processed" / "ontology.json").write_text(
        json.dumps(onto, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
