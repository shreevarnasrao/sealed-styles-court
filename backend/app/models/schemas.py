from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VerificationStatus = Literal["verified", "unverified", "disputed"]
HitSource = Literal["bm25", "semantic", "hybrid", "graph"]


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    claim: str
    quote: str
    verification_status: VerificationStatus
    support_score: float = 0.0


class EvidenceHit(BaseModel):
    document_id: str
    chunk_id: str
    text: str
    score: float
    source: HitSource
    verification_status: VerificationStatus
    title: str = ""
    characters: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    step: int
    action: str
    thought: str
    queries: list[str] = Field(default_factory=list)
    hit_ids: list[str] = Field(default_factory=list)
    decision: str


class AtomicClaim(BaseModel):
    claim_id: str
    text: str
    document_id: str = ""
    chunk_id: str = ""
    verification_status: VerificationStatus = "verified"
    support_score: float = 0.0


class InvestigationResult(BaseModel):
    run_id: str
    theory: str
    primary_suspect: str
    confidence: float
    citations: list[Citation]
    needs_more_evidence: bool
    retries_used: int
    unverified_cited: bool
    trace: list[AgentStep] = Field(default_factory=list)
    claims: list[AtomicClaim] = Field(default_factory=list)
    cached: bool = False


class ClaimAttack(BaseModel):
    claim_id: str
    claim: str
    attack: str
    chunk_ids: list[str] = Field(default_factory=list)


class FactCheckResult(BaseModel):
    run_id: str
    target_theory: str
    contradictions: list[Citation] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    timeline_conflicts: list[str] = Field(default_factory=list)
    rival_suspects: list[str] = Field(default_factory=list)
    theory_weaknesses: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    trace: list[AgentStep] = Field(default_factory=list)
    claim_attacks: list[ClaimAttack] = Field(default_factory=list)
    temporal_notes: list[str] = Field(default_factory=list)
    cached: bool = False


class InterrogateRequest(BaseModel):
    candidate_id: str
    question: str
    session_id: str = "default"


class InterrogateResponse(BaseModel):
    candidate_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False


class SearchRequest(BaseModel):
    query: str
    session_id: str = "default"
    k: int = 8


class InvestigateRequest(BaseModel):
    session_id: str = "default"
    focus: str | None = None
    rerun: bool = False


class FactCheckRequest(BaseModel):
    session_id: str = "default"
    theory: str | None = None
    primary_suspect: str | None = None
    rerun: bool = False


class LockPredictionRequest(BaseModel):
    session_id: str = "default"
    suspect_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class VerdictSubmission(BaseModel):
    session_id: str = "default"
    suspect_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class VerdictScore(BaseModel):
    correct_suspect: bool
    evidence_overlap: float
    notes: str
    locked_prediction_matched: bool | None = None


class GraphPayload(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class SealedEnvelope(BaseModel):
    status: Literal["sealed"] = "sealed"
    message: str = "Lock a prediction to unseal the prosecution and defence files."


class CaseBrief(BaseModel):
    case_id: str
    headline: str
    wound: str
    honesty: str
    clock: str
    hero_query: str
    hero_question: str
    hero_suspect_id: str
    victim: str
    setting: str
    suspects: list[dict] = Field(default_factory=list)
    delay: dict = Field(default_factory=dict)
    mocked: str
    llm_available: bool = False


class DeskCommand(BaseModel):
    session_id: str = "default"
    action: Literal["look", "ask", "pin", "unpin", "lock", "prosecute", "defend", "stamp", "reset"]
    query: str | None = None
    k: int = 8
    candidate_id: str | None = None
    question: str | None = None
    hit: EvidenceHit | None = None
    chunk_id: str | None = None
    suspect_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    focus: str | None = None
    theory: str | None = None
    rerun: bool = False


class Receipt(BaseModel):
    title: str
    prediction: str
    evidence: list[str] = Field(default_factory=list)
    investigator_theory: str
    fact_checker_attack: str
    stamp: Literal["supports", "does_not_show", "too_weak"]
    notes: str
    next_action: str
    honesty: str
    correct_suspect: bool | None = None
    evidence_overlap: float = 0.0


class DebateLine(BaseModel):
    claim_id: str
    claim: str
    attack: str
    verified: bool = True


class DeskSnapshot(BaseModel):
    session_id: str
    phase: str
    brief: CaseBrief
    hits: list[EvidenceHit] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)
    pins: list[EvidenceHit] = Field(default_factory=list)
    last_answer: InterrogateResponse | None = None
    locked: bool = False
    locked_prediction: dict | None = None
    investigation: InvestigationResult | None = None
    fact_check: FactCheckResult | None = None
    debate: list[DebateLine] = Field(default_factory=list)
    receipt: Receipt | None = None
    agents_sealed: bool = True
    cached_agents: bool = False
    searches: int = 0
    interrogations: int = 0
