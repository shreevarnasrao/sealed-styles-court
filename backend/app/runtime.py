from __future__ import annotations

from app.agents.fact_checker import FactChecker
from app.agents.investigator import Investigator
from app.agents.interrogate import Interrogator
from app.api.session import SessionBook
from app.corpus.store import CorpusStore
from app.desk.case_desk import CaseDesk
from app.graph.evidence_graph import EvidenceGraph
from app.llm.client import LLMClient
from app.rag.retrieve import HybridRetriever


class Runtime:
    def __init__(self) -> None:
        self.store = CorpusStore()
        self.retriever: HybridRetriever | None = None
        self.graph: EvidenceGraph | None = None
        self.llm = LLMClient()
        self.sessions = SessionBook()
        self.investigator: Investigator | None = None
        self.fact_checker: FactChecker | None = None
        self.interrogator: Interrogator | None = None
        self.desk = CaseDesk(self)
        self.ready = False

    def ingest(self) -> dict:
        self.store.load()
        self.retriever = HybridRetriever(self.store)
        self.graph = EvidenceGraph(self.store)
        self.investigator = Investigator(self.store, self.retriever, self.graph, self.llm)
        self.fact_checker = FactChecker(self.store, self.retriever, self.graph, self.llm)
        self.interrogator = Interrogator(self.store, self.retriever, self.llm)
        self.ready = True
        return {
            "ok": True,
            "documents": self.store.manifest.get("document_count"),
            "chunks": self.store.manifest.get("chunk_count"),
            "sealed": self.store.manifest.get("sealed_document_ids"),
            "unverified": self.store.manifest.get("unverified_document_ids"),
            "llm": self.llm.available,
            "semantic": "dense" if self.retriever.embeddings is not None else "tfidf",
        }
