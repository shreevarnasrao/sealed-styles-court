"""Discover people, places, and objects from case-file text at ingest time.

YAML remains a thin case seed (who may be charged, public motives). Mentions
in the corpus are extracted here and merged into the ontology used to tag
chunks and build the evidence graph.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

HONORIFIC_RE = re.compile(
    r"\b(Mr|Mrs|Miss|Dr|Monsieur|Inspector|Captain)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)
TWO_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b")
STOP_SURFACES = {
    "project gutenberg", "gutenberg ebook", "this ebook", "the project",
    "united states", "new york", "chapter i", "chapter ii",
}
STOP_FIRST = {
    "the", "this", "that", "then", "when", "what", "which", "your", "their",
    "chapter", "project", "ebook", "contents", "produced", "illustrated",
}

PLACE_LEXICON = [
    ("styles court", "styles_court", "Styles Court", ["Styles", "Styles Court", "the house"]),
    ("styles st. mary", "village", "Styles St. Mary", ["Styles St. Mary", "the village"]),
    ("essex", "essex", "Essex", ["Essex"]),
    ("london", "london", "London", ["London"]),
    ("dispensary", "dispensary", "Hospital dispensary", ["dispensary", "Red Cross Hospital"]),
    ("red cross hospital", "dispensary", "Hospital dispensary", ["Red Cross Hospital"]),
]

OBJECT_LEXICON = [
    ("cocoa", "cocoa", "Cocoa", ["cocoa", "the cocoa"]),
    ("strychnine", "strychnine", "Strychnine", ["strychnine", "nux vomica"]),
    ("nux vomica", "strychnine", "Strychnine", ["nux vomica"]),
    ("bromide", "bromide", "Bromide powders", ["bromide", "bromide powders"]),
    ("despatch-case", "despatch_case", "Despatch case", ["despatch-case", "despatch case"]),
    ("despatch case", "despatch_case", "Despatch case", ["despatch case"]),
    ("coffee", "coffee", "Coffee", ["coffee"]),
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def extract_entities(text: str) -> dict:
    people = _people(text)
    places = _from_lexicon(text, PLACE_LEXICON)
    objects = _from_lexicon(text, OBJECT_LEXICON)
    if re.search(r"\bwill\b", text, re.I) and re.search(r"\b(signed|burnt|grate|testament)\b", text, re.I):
        objects.append({"id": "will", "name": "Will", "aliases": ["will", "the will", "new will"]})
    if re.search(r"\bsalt\b", text, re.I) and re.search(r"\b(cocoa|tray|poison)\b", text, re.I):
        objects.append({"id": "salt", "name": "Salt", "aliases": ["salt"]})
    # de-dupe objects/places by id, keep first
    places = _unique(places)
    objects = _unique(objects)
    return {"people": people, "places": places, "objects": objects}


def merge_ontology(seed: dict, extracted: dict) -> dict:
    out = dict(seed or {})
    out.setdefault("suspects", [])
    out.setdefault("other_people", [])
    out.setdefault("places", [])
    out.setdefault("objects", [])
    victim = out.get("victim") or {}
    known_people = [victim] + list(out["suspects"]) + list(out["other_people"])
    for person in extracted.get("people") or []:
        match = _match_entity(person, known_people)
        if match is not None:
            _absorb_aliases(match, person)
            continue
        out["other_people"].append(person)
        known_people.append(person)
    for place in extracted.get("places") or []:
        match = _match_entity(place, out["places"])
        if match is not None:
            _absorb_aliases(match, place)
        else:
            out["places"].append(place)
    for obj in extracted.get("objects") or []:
        match = _match_entity(obj, out["objects"])
        if match is not None:
            _absorb_aliases(match, obj)
        else:
            out["objects"].append(obj)
    out["extraction"] = {
        "method": "ingest_text",
        "people": len(extracted.get("people") or []),
        "places": len(extracted.get("places") or []),
        "objects": len(extracted.get("objects") or []),
    }
    return out


def _people(text: str) -> list[dict]:
    counts: Counter[str] = Counter()
    aliases: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}

    for hon, rest in HONORIFIC_RE.findall(text):
        eid, label, extra = _honorific_id(hon, rest)
        counts[eid] += 1
        display.setdefault(eid, label)
        aliases[eid].add(label)
        aliases[eid].update(extra)

    for first, last in TWO_NAME_RE.findall(text):
        if first.lower() in STOP_FIRST:
            continue
        surface = f"{first} {last}"
        if surface.lower() in STOP_SURFACES:
            continue
        eid = slug(surface)
        counts[eid] += 1
        display.setdefault(eid, surface)
        aliases[eid].add(surface)
        aliases[eid].add(first)
        aliases[eid].add(f"{first} {last}")

    # Prefer full names over honorific+lastname when both exist.
    last_to_full: dict[str, str] = {}
    for eid in list(counts):
        parts = eid.split("_")
        if len(parts) >= 2 and parts[0] not in {"mr", "mrs", "miss", "dr", "monsieur", "inspector", "captain"}:
            last_to_full[parts[-1]] = eid
    merged: dict[str, str] = {}
    for eid in list(counts):
        parts = eid.split("_")
        if parts[0] in {"mr", "mrs", "miss", "dr"} and len(parts) == 2 and parts[1] in last_to_full:
            merged[eid] = last_to_full[parts[1]]
        elif parts[0] == "dr" and len(parts) == 2:
            # keep dr_bauerstein even if Bauerstein appears alone
            pass

    people = []
    seen: set[str] = set()
    for eid, n in counts.most_common():
        canon = merged.get(eid, eid)
        if canon in seen:
            if eid != canon:
                aliases[canon].update(aliases.get(eid) or [])
                aliases[canon].add(display.get(eid, eid))
            continue
        if n < 1:
            continue
        seen.add(canon)
        name = display.get(canon) or display.get(eid) or canon.replace("_", " ").title()
        al = sorted({a for a in aliases.get(canon, set()) | aliases.get(eid, set()) if a and a.lower() != name.lower()})
        people.append({"id": canon, "name": name, "aliases": al, "mentions": int(n)})
    return people[:40]


def _honorific_id(hon: str, rest: str) -> tuple[str, str, list[str]]:
    hon_l = hon.lower().rstrip(".")
    rest = rest.strip()
    if hon_l == "dr":
        return f"dr_{slug(rest.split()[-1])}", f"Dr {rest}", [rest, f"Dr. {rest}", f"Dr {rest}"]
    if hon_l == "monsieur":
        return slug(rest), f"Monsieur {rest}", [rest, f"Monsieur {rest}"]
    if hon_l == "miss" and " " not in rest:
        return f"miss_{slug(rest)}", f"Miss {rest}", [f"Miss {rest}", rest]
    if hon_l in {"mr", "mrs"} and " " not in rest:
        return f"{hon_l}_{slug(rest)}", f"{hon}. {rest}", [f"{hon}. {rest}", f"{hon} {rest}", rest]
    return slug(rest), f"{hon} {rest}".replace("..", "."), [rest, f"{hon} {rest}", f"{hon}. {rest}"]


def _from_lexicon(text: str, lexicon: list[tuple[str, str, str, list[str]]]) -> list[dict]:
    low = text.lower()
    out = []
    seen: set[str] = set()
    for needle, eid, name, aliases in lexicon:
        if needle in low and eid not in seen:
            seen.add(eid)
            out.append({"id": eid, "name": name, "aliases": aliases})
    return out


def _unique(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def _surfaces(ent: dict) -> set[str]:
    names = {ent.get("id", ""), slug(ent.get("name", ""))}
    names.update(slug(a) for a in (ent.get("aliases") or []) if a)
    labels = {str(ent.get("name", "")).lower()}
    labels.update(str(a).lower() for a in (ent.get("aliases") or []) if a)
    return {n for n in names if n} | {l for l in labels if l}


def _match_entity(ent: dict, pool: list[dict]) -> dict | None:
    want = _surfaces(ent)
    for other in pool:
        if not other:
            continue
        if want & _surfaces(other):
            return other
    return None


def _absorb_aliases(dst: dict, src: dict) -> None:
    have = {str(a).lower() for a in (dst.get("aliases") or [])}
    have.add(str(dst.get("name", "")).lower())
    aliases = list(dst.get("aliases") or [])
    for a in [src.get("name", "")] + list(src.get("aliases") or []):
        if a and str(a).lower() not in have:
            aliases.append(a)
            have.add(str(a).lower())
    dst["aliases"] = aliases
