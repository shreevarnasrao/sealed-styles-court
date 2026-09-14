from __future__ import annotations

import re

from app.corpus.store import CorpusStore
from app.grounding.gate import citations_from_hits
from app.llm.client import LLMClient, LLMError
from app.models.schemas import InterrogateResponse
from app.rag.retrieve import HybridRetriever

REFUSE_RE = re.compile(
    r"\b(who (really )?did it|murderer|solution|poirot explains|system prompt|ignore previous)\b",
    re.I,
)


class Interrogator:
    def __init__(self, store: CorpusStore, retriever: HybridRetriever, llm: LLMClient):
        self.store = store
        self.retriever = retriever
        self.llm = llm

    async def ask(self, candidate_id: str, question: str) -> InterrogateResponse:
        if candidate_id not in self.store.suspect_ids():
            return InterrogateResponse(
                candidate_id=candidate_id,
                answer="That person is not on the Styles Court suspect list.",
                refused=True,
            )
        if REFUSE_RE.search(question or ""):
            return InterrogateResponse(
                candidate_id=candidate_id,
                answer="I will not discuss rumours of a sealed solution. Ask me about that night, the will, or what I saw.",
                refused=True,
            )
        name = self.store.name_for(candidate_id)
        hits = self.retriever.search(f"{name} {question}", k=6, character=candidate_id)
        if not hits:
            hits = self.retriever.search(f"{name} {question}", k=6)
        evidence = "\n\n".join(f"[{h.verification_status}] {h.chunk_id}: {h.text[:450]}" for h in hits)
        sys = f"""You are {name}, a person at Styles Court in July 1916.
Answer the investigator in first person, period-appropriate, terse.
You only know facts from the evidence passages. If it is not there, evade or say you do not know.
You do not know any later courtroom revelations. You have never read a detective novel about this case.
If the evidence shows you lying or omitting, you may do the same.
Unverified passages are gossip; do not swear to them.
"""
        user = f"Question: {question}\n\nEvidence:\n{evidence}\n\nJSON: {{'answer': str, 'refused': bool}}"
        answer = ""
        refused = False
        if self.llm.available:
            try:
                data = await self.llm.complete_json(sys, user)
                answer = str(data.get("answer") or "")
                refused = bool(data.get("refused"))
            except (LLMError, Exception):
                answer = ""
        if not answer:
            preferred = next((h for h in hits if candidate_id in h.characters), hits[0] if hits else None)
            quote = preferred.text[:400] if preferred else "No dossier passage names me in connection with that."
            answer = f"(From the dossier, as {name}.) {quote}"
        citations = citations_from_hits(question, hits, limit=3)
        return InterrogateResponse(
            candidate_id=candidate_id,
            answer=answer,
            citations=citations,
            refused=refused,
        )
