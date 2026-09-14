# Case Desk — architecture (v2)

**Room:** 180DC ML recruitment. Noisy 90-second scan of a live URL and video, then a deep panel on GitHub + REPORT. Deadline 13 Sep, noon.

**Job:** Name who poisoned Emily Inglethorp, then unseal the prosecution and the defence, then leave with a docket.

**They start at** the night of 17 July (cocoa, delay, sealed chapters) **and leave with** a stamped case docket (observation + next action), not a toast.

## What we refused

- A new RAG stack, vector DB, LangChain, extra NLI models, multiple cases, auth.
- Rebuilding the costume. Manila / wax stay. The *shape* changes.
- Playing court: the system reports what it saw (`supports` / `does not show` / `too weak`), not a legal fate.

## Hybrid of four approaches

1. **Journey-first (playbook):** cover → papers → ask → lock → unseal → stamp. Graph / traces / PageRank live behind “Show the board”.
2. **CaseDesk (deep module):** three entry points — `brief()`, `snapshot()`, `handle(command)`. FastAPI routes are thin adapters. Complexity (state machine, grounding, both agents, dossier) stays behind the seam.
3. **Adversarial RAG:** fact-checker attacks *atomic claims* from the investigator; temporal delay is first-class; `or True` contradiction lie is removed; Bauerstein special-case is removed.
4. **Honesty:** cached agent runs are labelled; planted letter stays rumour; sealed chapters stay sealed.

## State machine

`opened → looking → locked → argued → stamped`

- Look / ask / pin advance to `looking`.
- Lock requires a household id; pins become evidence ids.
- Prosecute / defend may compute before lock (existing contract) but the snapshot seals agent files until lock.
- Stamp writes a receipt. No method leak from `solution.json`.

## Interface

```
CaseDesk.brief() -> CaseBrief
CaseDesk.snapshot(session_id) -> DeskSnapshot
CaseDesk.handle(session_id, DeskCommand) -> DeskSnapshot
```

Commands: `look | ask | pin | unpin | lock | prosecute | defend | stamp | reset`.

## Receipt

A docket the video can screenshot: prediction, pinned papers, investigator theory, fact-checker attack, stamp word, next action, one-line honesty.
