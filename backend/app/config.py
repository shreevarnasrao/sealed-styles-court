from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
SEALED = DATA / "sealed"
ONTOLOGY = DATA / "ontology" / "styles.yaml"

LLM_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
if os.getenv("LLM_BASE_URL"):
    LLM_BASE_URL = os.getenv("LLM_BASE_URL")
elif os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
else:
    LLM_BASE_URL = "https://api.openai.com/v1"
if os.getenv("LLM_MODEL"):
    LLM_MODEL = os.getenv("LLM_MODEL")
elif "openai.com" in LLM_BASE_URL:
    LLM_MODEL = "gpt-4o"
else:
    LLM_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = int(os.getenv("INVESTIGATOR_MAX_RETRIES", "3"))
UNVERIFIED_CONFIDENCE_CAP = 0.45
SUPPORT_THRESHOLD = 0.35
HYBRID_K = 8
GRAPH_EXPAND = 4
# Rerank + expansion tuning (small, defensible defaults).
# RRF k=60 is the literature default (Cormack et al. SIGIR'09); do not tune without judged queries.
RRF_K = int(os.getenv("RRF_K", "60"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "20"))
RERANK_KEEP = int(os.getenv("RERANK_KEEP", "8"))
QUERY_EXPANSION = os.getenv("QUERY_EXPANSION", "1") == "1"
GRAPH_EXPAND_SCORED = os.getenv("GRAPH_EXPAND_SCORED", "1") == "1"
