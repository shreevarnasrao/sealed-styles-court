import asyncio

from app.agents.fact_checker import FactChecker
from app.agents.investigator import Investigator
from app.llm.client import LLMClient


def test_investigator_loop_retries(store, retriever, graph):
    inv = Investigator(store, retriever, graph, LLMClient())
    result = asyncio.run(inv.run())
    assert result.retries_used >= 1
    assert result.primary_suspect
    assert result.trace
    actions = [s.action for s in result.trace]
    assert "retrieve" in actions
    assert "evaluate" in actions


def test_fact_checker_uses_different_queries(store, retriever, graph):
    llm = LLMClient()
    inv = Investigator(store, retriever, graph, llm)
    investigation = asyncio.run(inv.run())
    fc = FactChecker(store, retriever, graph, llm)
    report = asyncio.run(fc.run(investigation, None, None))
    inv_q = {q for step in investigation.trace for q in step.queries}
    fc_q = {q for step in report.trace for q in step.queries}
    assert fc_q
    assert inv_q
    assert fc_q != inv_q
    assert report.theory_weaknesses or report.rival_suspects
