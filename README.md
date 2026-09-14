# SEALED — Who put the strychnine in the cocoa?

Interactive **agentic RAG investigation** for the 180DC ML recruitment task.

An unsigned letter names Dr Bauerstein. Chapters **XII–XIII** of Agatha Christie’s *The Mysterious Affair at Styles* (Gutenberg #863, public domain) are **sealed** — they never enter the retriever. You check the tip against the file, **lock a name**, then unseal the prosecution Investigator and the adversarial Fact-Checker. You leave with a **jury docket**, not a toast.

- **GitHub:** https://github.com/shreevarnasrao/sealed-styles-court
- **Live URL:** click Deploy to Render, add `OPENAI_API_KEY`, then replace this line with the `*.onrender.com` URL

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://dashboard.render.com/blueprint/new?repo=https://github.com/shreevarnasrao/sealed-styles-court)

**This is an independent recruitment demo, not a court.** The planted letter (`DOC-ANON-TIP`) is rumour. Agents may run on heuristics if no LLM key is set.

## Hero path (90 seconds)

1. Open the live URL. Read the letter. Press **Check this letter against the file**.
2. See the **unverified** badge. Pin papers. (Alternate: *The letter may be the decoy — try the cocoa.*)
3. **Lock a name** (Bauerstein is preselected so you can reject the tip). Prosecution and defence stay sealed until you do.
4. Unseal the agents. Read claim versus attack. Stamp the docket.

The evidence board, PageRank, and traces are behind **Show the board**. That is the lab.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python preprocess/build_corpus.py
copy .env.example .env   # then add GROQ_API_KEY (optional; search/graph work without it)
cd backend
set PYTHONPATH=.
uvicorn app.main:app --reload --port 8000
```

Frontend (dev):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (proxies the API). Or open http://localhost:8000 after `npm run build`.

Tests:

```bash
pytest -q
```

## What is different (v2)

- **Six panels on one desk:** evidence search, interrogation, evidence board, Investigator, Fact-Checker, verdict. The graph is not hidden.
- **Entities extracted at ingest** from the novel text, then merged with the thin YAML case seed (who may be charged).
- **No rumour injection:** the planted letter is retrieved only when the query matches its wording.
- **Case Desk:** one module (`brief`, `snapshot`, `handle`) owns the journey. Routes are thin adapters. Mandatory APIs are unchanged.
- **Fact-Checker attacks atomic claims** from the Investigator. It does not re-summarise the same hits.
- **Honesty in code:** citations must be retrieved documents; unverified evidence cannot carry a high-confidence theory.

## API

| Method | Path | Role |
|--------|------|------|
| GET | `/brief` | Wound, clock, honesty, hero query |
| GET | `/dossier/{session}` | Full desk snapshot |
| POST | `/desk` | One command: look / ask / pin / lock / prosecute / defend / stamp |
| POST | `/ingest` | Load corpus, BM25 + semantic index, evidence graph |
| POST | `/search_evidence` | Hybrid retrieval + rerank + graph expand + contradiction flags |
| POST | `/interrogate` | Character-conditioned RAG |
| POST | `/lock_prediction` | Unseal agent files (persisted) |
| POST | `/investigate` | Investigator loop (max 3 retries) + faithfulness; `rerun` to regenerate |
| POST | `/fact_check` | Adversarial retrieval against investigator claims |
| POST | `/submit_verdict` | Score vs sealed solution + **receipt** (does not leak the method) |
| GET | `/graph` | Evidence graph (lab) |
| GET | `/timeline` | Ordered case events + delay |
| GET | `/communities` | Graph communities + suspect PageRank |
| GET | `/health` | Liveness |

## Architecture

See [REPORT.md](REPORT.md). Hybrid RAG is BM25 + dense MiniLM (TF-IDF cosine if the encoder is unavailable), fused with reciprocal rank fusion (k=60), ontology query expansion, heuristic rerank, scored graph expansion, then a grounding gate.

## AI tools used

Grok (xAI) / Cursor was used to plan the Case Desk, reshape the journey, and draft the UI. Retrieval, grounding, sealed-chapter isolation, and agent loops were specified and then verified with pytest. I can explain every module in `backend/app/`.

## Bonus features (honest)

Shipped because they serve the core: visual graph (lab), agent traces, graph-aware retrieval, reranking, contradiction detection, temporal delay notes, parallel query retrieval, faithfulness report, persistent lock + pins, claim-versus-attack debate, jury docket.

Not shipped: multiple cases, persistent user accounts, a separate vector database.
