from __future__ import annotations

from collections import defaultdict

import networkx as nx

from app.corpus.store import CorpusStore
from app.models.schemas import EvidenceHit


class EvidenceGraph:
    def __init__(self, store: CorpusStore):
        self.store = store
        self.g = nx.Graph()
        self.chunk_entities: dict[str, set[str]] = {}
        self._build()

    def _add_node(self, nid: str, kind: str, label: str, extra: dict | None = None) -> None:
        if nid not in self.g:
            data = {"id": nid, "kind": kind, "label": label}
            if extra:
                data.update(extra)
            self.g.add_node(nid, **data)

    def _build(self) -> None:
        onto = self.store.ontology
        self._add_node(onto["victim"]["id"], "victim", onto["victim"]["name"])
        for s in onto.get("suspects") or []:
            self._add_node(s["id"], "suspect", s["name"], {"motive": s.get("motive_public", "")})
        for p in onto.get("other_people") or []:
            self._add_node(p["id"], "person", p["name"])
        for p in onto.get("places") or []:
            self._add_node(p["id"], "place", p["name"])
        for o in onto.get("objects") or []:
            self._add_node(o["id"], "object", o["name"])
        for ev in onto.get("key_events") or []:
            self._add_node(ev["id"], "event", ev["label"], {"time": ev.get("time", "")})
            for a in ev.get("actors") or []:
                if a in self.g:
                    self.g.add_edge(a, ev["id"], relation="PRESENT_AT", weight=2)
            if ev.get("place") in self.g:
                self.g.add_edge(ev["id"], ev["place"], relation="AT", weight=2)
            for obj in ev.get("objects") or []:
                if obj in self.g:
                    self.g.add_edge(ev["id"], obj, relation="INVOLVES", weight=2)

        for doc in self.store.documents:
            did = doc["document_id"]
            status = doc.get("verification_status", "verified")
            self._add_node(
                did,
                "document",
                doc.get("title", did),
                {"verification_status": status, "doc_type": doc.get("doc_type")},
            )

        co: dict[tuple[str, str], int] = defaultdict(int)
        for chunk in self.store.chunks:
            ents = set(chunk.characters + chunk.places + chunk.objects)
            self.chunk_entities[chunk.chunk_id] = ents
            for e in ents:
                if e in self.g:
                    self.g.add_edge(e, chunk.document_id, relation="MENTIONED_IN", weight=1)
            el = sorted(ents)
            for i, a in enumerate(el):
                for b in el[i + 1 :]:
                    if a in self.g and b in self.g:
                        co[(a, b)] += 1
        for (a, b), w in co.items():
            if self.g.has_edge(a, b):
                self.g[a][b]["weight"] = self.g[a][b].get("weight", 1) + w
                self.g[a][b]["relation"] = self.g[a][b].get("relation", "MENTIONED_WITH")
            else:
                self.g.add_edge(a, b, relation="MENTIONED_WITH", weight=w)

        # Temporal edges from ontology event order
        events = onto.get("key_events") or []
        for a, b in zip(events, events[1:]):
            if a["id"] in self.g and b["id"] in self.g:
                self.g.add_edge(a["id"], b["id"], relation="BEFORE", weight=1)

    def expand_hits(self, hits: list[EvidenceHit], cap: int = 4) -> list[EvidenceHit]:
        """Graph-aware retrieval: rank candidates by shared-entity overlap + co-occurrence weight.

        Previously: first-come chunks sharing any entity, fixed score 0.15.
        Now: score = overlap count + co-occurrence edge weight, sorted, deterministic.
        """
        from app.config import GRAPH_EXPAND_SCORED

        seed: set[str] = set()
        seen = {h.chunk_id for h in hits}
        for h in hits[:4]:
            seed |= self.chunk_entities.get(h.chunk_id, set())
        if not seed:
            return hits
        scored: list[tuple[float, object]] = []
        for chunk in self.store.chunks:
            if chunk.chunk_id in seen:
                continue
            ents = set(chunk.characters + chunk.places + chunk.objects)
            overlap = seed & ents
            if not overlap:
                continue
            # Co-occurrence weight: sum of existing edge weights between seed and candidate entities.
            w = 0.0
            for e in overlap:
                for s in seed:
                    if s != e and self.g.has_edge(s, e):
                        w += float(self.g[s][e].get("weight", 1))
            score = len(overlap) + 0.1 * w
            if not GRAPH_EXPAND_SCORED:
                score = 0.15
            scored.append((score, chunk))
        scored.sort(key=lambda t: (-t[0], t[1].chunk_id))  # type: ignore[attr-defined]
        extra: list[EvidenceHit] = []
        for score, chunk in scored[:cap]:  # type: ignore[misc]
            extra.append(chunk.as_hit(0.15 + 0.05 * float(score), "graph"))  # type: ignore[attr-defined]
            seen.add(chunk.chunk_id)  # type: ignore[attr-defined]
        return hits + extra

    def suspect_pagerank(self) -> dict[str, float]:
        """PageRank prior over suspects: who the graph structure centres on."""
        try:
            pr = nx.pagerank(self.g, weight="weight")
        except Exception:
            return {}
        return {s["id"]: float(pr.get(s["id"], 0.0)) for s in self.store.suspects()}

    def communities(self) -> list[list[str]]:
        """GraphRAG-lite: greedy modularity communities over entity subgraph."""
        try:
            from networkx.algorithms.community import greedy_modularity_communities

            ents = [n for n, d in self.g.nodes(data=True) if d.get("kind") in {"suspect", "victim", "person", "place", "object", "event"}]
            sub = self.g.subgraph(ents)
            return [sorted(list(c)) for c in greedy_modularity_communities(sub, weight="weight")]
        except Exception:
            return []

    def detect_contradictions(self, hits: list[EvidenceHit], limit: int = 5) -> list[dict]:
        """Lightweight contradiction detector (lexicon + alibi patterns, no NLI dep).

        Flags pairs sharing an entity where one side carries negation/alibi language
        and the other asserts presence/action. High precision, low recall by design:
        better to miss a subtle conflict than to invent one (see 2025 RAG contradiction study).
        """
        import re

        neg = re.compile(r"\b(not|never|no |none|denies|denied|alibi|elsewhere|was not|were not|did not|could not)\b", re.I)
        out: list[dict] = []
        for i, a in enumerate(hits):
            for b in hits[i + 1 :]:
                shared = set(a.characters) & set(b.characters)
                if not shared:
                    continue
                a_neg, b_neg = bool(neg.search(a.text)), bool(neg.search(b.text))
                if a_neg != b_neg:
                    out.append(
                        {
                            "pair": [a.chunk_id, b.chunk_id],
                            "entity": sorted(shared)[0],
                            "note": f"Conflicting accounts involving {sorted(shared)[0].replace('_', ' ')}: {a.chunk_id} vs {b.chunk_id}",
                        }
                    )
                if len(out) >= limit:
                    return out
        return out

    def payload(self) -> dict:
        nodes = []
        for nid, data in self.g.nodes(data=True):
            nodes.append(
                {
                    "id": nid,
                    "label": data.get("label", nid),
                    "kind": data.get("kind", "entity"),
                    "verification_status": data.get("verification_status"),
                    "motive": data.get("motive"),
                }
            )
        edges = []
        for a, b, data in self.g.edges(data=True):
            if data.get("relation") == "SELF":
                continue
            edges.append(
                {
                    "from": a,
                    "to": b,
                    "relation": data.get("relation", "RELATED"),
                    "weight": data.get("weight", 1),
                }
            )
        return {"nodes": nodes, "edges": edges}

    def timeline_notes(self) -> list[str]:
        notes = []
        for ev in self.store.ontology.get("key_events") or []:
            notes.append(f"{ev.get('time', '?')}: {ev['label']}")
        return notes

    def neighbors(self, nid: str) -> list[str]:
        if nid not in self.g:
            return []
        return list(self.g.neighbors(nid))
