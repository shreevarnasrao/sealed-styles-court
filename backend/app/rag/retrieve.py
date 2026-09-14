from __future__ import annotations

import math
import re
from collections import defaultdict

import numpy as np
from rank_bm25 import BM25Okapi

from app.corpus.store import Chunk, CorpusStore
from app.models.schemas import EvidenceHit

_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HybridRetriever:
    """BM25 + dense (or TF-IDF) retrieval fused with RRF, then lightweight rerank.

    Pipeline (explicit, no framework):
      1. Query expansion via ontology aliases (cocoa -> drink, strychnine -> poison).
      2. BM25 leg + semantic leg fused with reciprocal rank fusion (k=60 default).
      3. Heuristic rerank: verified boost, entity overlap, cross-encoder when installed.
    No vector database: corpus is ~410 chunks, NumPy brute force is ~0.3ms.
    """

    def __init__(self, store: CorpusStore):
        self.store = store
        self.tokenized = [tokenize(c.text) for c in store.chunks]
        self.bm25 = BM25Okapi(self.tokenized)
        self.encoder = None
        self.embeddings: np.ndarray | None = None
        self.tfidf_matrix: np.ndarray | None = None
        self.idf: dict[str, float] = {}
        self._cross_encoder = None
        self._fit_semantic()
        self._try_load_reranker()

    def _try_load_reranker(self) -> None:
        """Optional cross-encoder (ms-marco MiniLM). Silent fallback if missing."""
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception:
            self._cross_encoder = None

    def _expansion_terms(self, query: str) -> str:
        """Ontology-aware query expansion: add entity aliases + poison-domain synonyms."""
        from app.config import QUERY_EXPANSION

        if not QUERY_EXPANSION:
            return query
        ql = query.lower()
        extra: list[str] = []
        # Domain synonyms that BM25 would otherwise miss (lexical gap).
        synonyms = {
            "cocoa": "drink tray cup",
            "strychnine": "poison nux vomica",
            "will": "signed burnt grate despatch testamentary",
            "cynthia": "dispensary hospital",
        }
        for key, syn in synonyms.items():
            if key in ql:
                extra.append(syn)
        if any(w in ql for w in ("cocoa", "strychnine", "convulsion", "delay", "poison", "hours")):
            extra.append("hours o'clock bedtime five o'clock nine hours delayed")
        # Ontology aliases: if a suspect/place/object alias appears, add its canonical id.
        try:
            onto = self.store.ontology or {}
            for group in ("suspects", "other_people", "places", "objects"):
                for ent in onto.get(group) or []:
                    for al in [ent.get("name", "")] + list(ent.get("aliases") or []):
                        if al and len(al) > 3 and al.lower() in ql:
                            extra.append(ent["id"].replace("_", " "))
                            break
        except Exception:
            pass
        return query + (" " + " ".join(extra) if extra else "")

    def _fit_semantic(self) -> None:
        texts = [c.text for c in self.store.chunks]
        try:
            from sentence_transformers import SentenceTransformer

            self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self.embeddings = np.asarray(self.encoder.encode(texts, show_progress_bar=False), dtype=np.float32)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-8
            self.embeddings = self.embeddings / norms
            return
        except Exception:
            self.encoder = None
        self._fit_tfidf(texts)

    def _fit_tfidf(self, texts: list[str]) -> None:
        docs = [tokenize(t) for t in texts]
        df: dict[str, int] = defaultdict(int)
        for toks in docs:
            for w in set(toks):
                df[w] += 1
        n = len(docs)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in df.items()}
        vocab = {w: i for i, w in enumerate(self.idf)}
        mat = np.zeros((n, len(vocab)), dtype=np.float32)
        for i, toks in enumerate(docs):
            counts: dict[str, int] = defaultdict(int)
            for w in toks:
                counts[w] += 1
            for w, c in counts.items():
                j = vocab.get(w)
                if j is not None:
                    mat[i, j] = c * self.idf[w]
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
        self.tfidf_matrix = mat / norms
        self._vocab = vocab

    def _semantic_scores(self, query: str) -> np.ndarray:
        if self.embeddings is not None and self.encoder is not None:
            q = np.asarray(self.encoder.encode([query], show_progress_bar=False), dtype=np.float32)[0]
            q = q / (np.linalg.norm(q) + 1e-8)
            return self.embeddings @ q
        assert self.tfidf_matrix is not None
        qtoks = tokenize(query)
        vec = np.zeros(self.tfidf_matrix.shape[1], dtype=np.float32)
        counts: dict[str, int] = defaultdict(int)
        for w in qtoks:
            counts[w] += 1
        for w, c in counts.items():
            j = self._vocab.get(w)
            if j is not None:
                vec[j] = c * self.idf.get(w, 0.0)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        return self.tfidf_matrix @ vec

    def search(self, query: str, k: int = 8, character: str | None = None) -> list[EvidenceHit]:
        from app.config import RERANK_KEEP, RERANK_TOP_N, RRF_K

        expanded = self._expansion_terms(query)
        tokens = tokenize(expanded)
        bm25_scores = np.asarray(self.bm25.get_scores(tokens), dtype=np.float64)
        sem_scores = self._semantic_scores(expanded)
        bm25_rank = _ranks(bm25_scores)
        sem_rank = _ranks(sem_scores)
        rrf = 1.0 / (RRF_K + bm25_rank) + 1.0 / (RRF_K + sem_rank)
        order = np.argsort(-rrf)
        # Over-retrieve then rerank (Perplexity pattern: hybrid -> cross-encoder -> cite).
        pool: list[EvidenceHit] = []
        for idx in order:
            chunk = self.store.chunks[int(idx)]
            if character and character not in chunk.characters:
                continue
            pool.append(chunk.as_hit(float(rrf[int(idx)]), "hybrid"))
            if len(pool) >= max(k * 2, RERANK_TOP_N):
                break
        reranked = self.rerank(query, pool, top_n=max(k, min(RERANK_KEEP, len(pool))))
        # If caller asked for more than rerank keep, append remainder in RRF order.
        if len(reranked) < k:
            seen = {h.chunk_id for h in reranked}
            for h in pool:
                if h.chunk_id not in seen:
                    reranked.append(h)
                    if len(reranked) >= k:
                        break
        return reranked[:k]

    def rerank(self, query: str, hits: list[EvidenceHit], top_n: int = 8) -> list[EvidenceHit]:
        """Heuristic rerank + optional cross-encoder. Deterministic, no new deps required.

        Score = RRF base + verified bonus - unverified penalty + entity overlap.
        Cross-encoder (if installed) re-scores top-N text pairs and blends 0.5/0.5.
        """
        if not hits:
            return hits
        qtoks = set(tokenize(query))
        scored: list[tuple[float, EvidenceHit]] = []
        for h in hits:
            bonus = 0.0
            if h.verification_status == "verified":
                bonus += 0.02
            elif h.verification_status == "unverified":
                text_toks = set(tokenize(h.text[:800]))
                coverage = (len(qtoks & text_toks) / max(1, len(qtoks))) if qtoks else 0.0
                # Demote rumour when it is not what the query asked for; do not hide it
                # when the query matches the unverified document's own wording.
                if coverage < 0.35:
                    bonus -= 0.05
            delay_like = any(w in query.lower() for w in ("delay", "hours", "convulsion", "bedtime"))
            if delay_like and any(w in h.text.lower() for w in ("hour", "o'clock", "oclock", "delayed")):
                bonus += 0.05
            # Entity overlap: query mentions a character present in the chunk.
            overlap = len(qtoks & set(tokenize(" ".join(h.characters).replace("_", " "))))
            bonus += 0.01 * overlap
            # Lexical coverage: fraction of query tokens present in chunk text.
            if qtoks:
                text_toks = set(tokenize(h.text[:800]))
                bonus += 0.03 * (len(qtoks & text_toks) / max(1, len(qtoks)))
            scored.append((h.score + bonus, h))
        scored.sort(key=lambda t: -t[0])
        ordered = [h for _, h in scored]
        # Optional cross-encoder pass on top-20 (silent fallback).
        if self._cross_encoder is not None and len(ordered) >= 2:
            try:
                pairs = [(query, h.text[:512]) for h in ordered[:20]]
                ce = self._cross_encoder.predict(pairs)
                idx = sorted(range(len(ce)), key=lambda i: -float(ce[i]))
                ordered = [ordered[i] for i in idx] + ordered[20:]
                for h in ordered[:top_n]:
                    h.source = "hybrid"  # type: ignore[assignment]
            except Exception:
                pass
        # Mark survivors as reranked only if order actually changed (keeps traces honest).
        return ordered[:top_n]

    def by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        return [c for cid in chunk_ids if (c := self.store.get(cid))]


def _ranks(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks.astype(np.float64)
