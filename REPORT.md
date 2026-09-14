# SEALED — Technical report (v2)

**Styles Court case file · 180DC ML recruitment**

## Problem and corpus

The brief asks for a multi-document investigation with two adversarial agents, hybrid retrieval, an evidence graph, grounded citations, and a human verdict. Most corpora have no hidden ground truth, so `/submit_verdict` becomes a toast.

We recomposed a public-domain closed-circle mystery — *The Mysterious Affair at Styles* (Gutenberg #863) — into a case file. Chapters I–XI plus a planted anonymous letter are indexed. Chapters XII–XIII live only under `data/sealed/` and never enter BM25 or the vector index. The user is the jury; the Investigator is prosecution; the Fact-Checker is defence.

The product job is one verb: **name who poisoned her, then leave with a docket.** The engine serves that journey. It is not the homepage.

## Architecture (v2 — what changed and why)

```
UI (cover → papers → ask → lock → unseal → docket)
  GET /brief        CaseDesk.brief()   wound, clock, honesty, hero query
  POST /desk        CaseDesk.handle()  look | ask | pin | lock | prosecute | defend | stamp
  Mandatory APIs    thin adapters over the same module

  look           HybridRetriever + scored graph expand + contradiction flags
  prosecute      Investigator: retrieve → evaluate → retry (max 3) → atomic claims → grounding gate
  defend         Fact-Checker: claim-derived counter-queries (not a second summary)
  stamp          SealedVault score + Receipt (supports / does not show / too weak)

GroundingGate strips citations whose document_id was not retrieved.
Unverified chunks cannot raise confidence above 0.45 if they are the sole support.
Faithfulness = supported/total is returned with /investigate.
Cached agent runs are labelled; `rerun=true` regenerates.
```

Ingest now extracts people, places, and objects from the novel text (`preprocess/extract_entities.py`) and merges them into the ontology used to tag chunks and build the graph. YAML stays a thin case seed (charged persons and public motives), not the only source of entities.

Retrieval no longer force-injects `DOC-ANON-TIP` on rumour keywords. The letter is unverified; it appears when the query matches its wording.

v1.1 already had hybrid RRF, query expansion, rerank, graph expansion, PageRank, communities, planted letter, sealed vault. v2 changes the *shape*:

- **CaseDesk** (three entry points) hides the state machine, both agents, and the docket. Routes stopped being the orchestrator.
- **Journey UI** puts the object-in-hand on `/` (the night of 17 July). After that, all six mandatory panels sit on one desk, including the evidence board.
- **Atomic claims** are the seam between Investigator and Fact-Checker. Defence queries those atoms.
- **Temporal delay** is first-class (cocoa → convulsions hours later) in the brief, investigator queries, and fact-check notes.
- **Honesty bugs fixed:** Fact-Checker no longer marked every citation as a contradiction (`or True`). Heuristic investigator no longer special-cases Dr Bauerstein. Pins, not typed `DOC-` IDs, become evidence.

No LangChain. The loops are ordinary Python, which is what we have to explain in an interview.

## Agents

**Investigator.** Draft a theory, emit search queries (including the delay), retrieve in parallel, expand one hop on the entity graph, ask “is this sufficient?”, retry on gaps, emit atomic claims. Traces are returned.

**Fact-Checker.** Does not re-summarise the same hits. It generates counter-queries from those claims (alibis, rivals, tray access, planted letter) and returns a claim-versus-attack list.

## Grounding

A citation is kept only if its `document_id` is in that turn’s retrieved set. Token-overlap support below 0.35 marks the citation unverified. `DOC-ANON-TIP` is ingested with `verification_status: unverified`. Tests fail the build if sealed chapter text appears in the index, if a non-retrieved id is cited, or if unverified-only support stays at high confidence.

## What we refused

A vector database, a multi-case platform, an agent framework, and a lab-as-homepage. Hybrid retrieval does not need Pinecone. Two named prompts with the same query set would fail the “genuine agentic behaviour” axis, so the Fact-Checker’s query generator is a different function aimed at different claims. The UI does not issue a legal fate.

## Limitations

LLM providers have read Christie; the sealed index and citation gate are the real controls, not the prompt. Dense embeddings need `sentence-transformers`; without it we fall back to TF-IDF cosine. Without an LLM key the Investigator uses the heuristic fallback and correctly reports low faithfulness when citations are thin. Sessions persist lock, pins, and counters to `data/processed/sessions.json` (git-ignored); full traces are re-runnable.

## UI

First screen: the job, one honesty strip, one control (`Open the night of 17 July`). Then papers (prefilled search, pin, contradiction flags) → ask → lock → claim-versus-attack → stamped docket (`supports` / `does not show` / `too weak` + next action). Reduced motion and reduced transparency are respected. Keyboard: `/` search, `⌘K` commands, `Esc` close.
