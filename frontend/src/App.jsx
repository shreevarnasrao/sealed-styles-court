import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Network } from "vis-network/standalone";
import { api } from "./api.js";

function jurySession() {
  try {
    const key = "sealed-jury";
    let id = localStorage.getItem(key);
    if (!id) {
      id = `jury-${crypto.randomUUID()}`;
      localStorage.setItem(key, id);
    }
    return id;
  } catch {
    return `jury-${Date.now()}`;
  }
}
const SESSION = jurySession();
const STEPS = [
  { id: "search", label: "Search" },
  { id: "ask", label: "Ask" },
  { id: "board", label: "Board" },
  { id: "investigate", label: "Investigator" },
  { id: "factcheck", label: "Fact-checker" },
  { id: "verdict", label: "Verdict" },
];

const springSoft = { type: "spring", stiffness: 200, damping: 30, mass: 0.9 };
const springSnappy = { type: "spring", stiffness: 400, damping: 32, mass: 0.8 };
const tweenOut = { duration: 0.22, ease: [0.23, 1, 0.32, 1] };

function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .filter((w) => !["Dr", "Miss", "Mr", "Mrs"].includes(w))
    .map((w) => w[0])
    .join("")
    .slice(0, 2);
}

function Badge({ status }) {
  const s = status || "verified";
  return <span className={`badge ${s}`}>{s}</span>;
}

function useTypewriter(fullText, active) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(fullText);
  const [streaming, setStreaming] = useState(false);
  useEffect(() => {
    if (!active) {
      setShown(fullText);
      setStreaming(false);
      return;
    }
    if (reduce || !fullText || fullText.length < 40) {
      setShown(fullText);
      setStreaming(false);
      return;
    }
    setShown("");
    setStreaming(true);
    let i = 0;
    const id = setInterval(() => {
      i += 6;
      setShown(fullText.slice(0, i));
      if (i >= fullText.length) {
        clearInterval(id);
        setStreaming(false);
      }
    }, 24);
    return () => clearInterval(id);
  }, [fullText, active, reduce]);
  const stop = useCallback(() => {
    setShown(fullText);
    setStreaming(false);
  }, [fullText]);
  return { shown, streaming, stop };
}

function InterrogationBubble({ who, q, a }) {
  const { shown, streaming, stop } = useTypewriter(a, true);
  return (
    <motion.div className="bubble" initial={{ opacity: 0, transform: "translateY(8px)" }} animate={{ opacity: 1, transform: "translateY(0px)" }} transition={tweenOut}>
      <div className="q">{who}: “{q}”</div>
      <div className="a">
        {shown}
        {streaming ? <span className="caret" aria-hidden /> : null}
      </div>
      {streaming ? (
        <button className="linkbtn" onClick={stop}>
          Show full statement
        </button>
      ) : null}
    </motion.div>
  );
}

function ConfidenceMeter({ value }) {
  const pct = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  const label = pct >= 70 ? "High" : pct >= 45 ? "Medium" : "Low";
  return (
    <div className="meter" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Confidence ${label} ${pct} percent`}>
      <div className="meter-track">
        <motion.div className="meter-fill" initial={false} animate={{ width: `${pct}%` }} transition={springSoft} />
      </div>
      <div className="meter-label">conf {pct}% · {label}</div>
    </div>
  );
}

function Skeleton({ lines = 3 }) {
  return (
    <div className="skel" aria-label="Agents at work">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skel-line" style={{ width: `${92 - i * 14}%` }} />
      ))}
      <div className="skel-note">Cross-referencing statements… checking the delay…</div>
    </div>
  );
}

function Corkboard({ graph, highlight, pinned }) {
  const ref = useRef(null);
  const net = useRef(null);
  const [focused, setFocused] = useState(null);
  useEffect(() => {
    if (!ref.current || !graph) return;
    const nodes = (graph.nodes || []).map((n) => ({
      id: n.id,
      label: n.label,
      group: n.kind,
      color:
        n.verification_status === "unverified"
          ? { background: "#7c1828", border: "#4c0e16" }
          : n.kind === "suspect"
            ? { background: "#3d5c56", border: "#24332d" }
            : n.kind === "document"
              ? { background: "#c6a45a", border: "#8a6a3d" }
              : n.kind === "event"
                ? { background: "#7a4b2a", border: "#4a2c17" }
                : { background: "#efe0c4", border: "#c3aa80" },
      font: { color: n.kind === "document" || n.kind === "suspect" ? "#f3e6cf" : "#1a120c", size: 11 },
      borderWidth: highlight && highlight.includes(n.id) ? 3 : 1,
      size: highlight && highlight.includes(n.id) ? 26 : 18,
    }));
    const edges = (graph.edges || []).map((e, i) => ({
      id: `e${i}`,
      from: e.from,
      to: e.to,
      color: e.relation === "BEFORE" || e.relation === "CONTRADICTS" ? "#7c1828" : "#5c4630",
      width: Math.min(4, 0.4 + (e.weight || 1) * 0.15),
      dashes: e.relation === "CONTRADICTS",
    }));
    net.current?.destroy();
    net.current = new Network(ref.current, { nodes, edges }, {
      physics: { stabilization: true, barnesHut: { gravitationalConstant: -2200, springLength: 110 } },
      interaction: { hover: true, tooltipDelay: 80 },
      nodes: { shape: "box", margin: 6 },
    });
    net.current.on("click", (p) => setFocused(p.nodes?.[0] || null));
    void pinned;
    return () => net.current?.destroy();
  }, [graph, highlight, pinned]);
  return (
    <div className="cork-wrap">
      <div className="cork" ref={ref} />
      <div className={`node-preview ${focused ? "" : "dim"}`}>
        {focused ? <><strong>{focused}</strong> — drag to rearrange.</> : "Lab board · drag nodes · scroll to zoom"}
      </div>
    </div>
  );
}

function Palette({ open, onClose, actions }) {
  const [f, setF] = useState("");
  const inputRef = useRef(null);
  useEffect(() => {
    if (open) {
      setF("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);
  const items = (actions || []).filter((a) => a.label.toLowerCase().includes(f.toLowerCase()));
  return (
    <AnimatePresence>
      {open ? (
        <motion.div className="palette-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            className="palette"
            role="dialog"
            aria-label="Case-file commands"
            initial={{ opacity: 0, transform: "translateY(-8px) scale(0.98)" }}
            animate={{ opacity: 1, transform: "translateY(0px) scale(1)" }}
            exit={{ opacity: 0, transform: "translateY(-6px) scale(0.98)" }}
            transition={springSnappy}
            onClick={(e) => e.stopPropagation()}
          >
            <input ref={inputRef} placeholder="Search papers… summon… stamp…" value={f} onChange={(e) => setF(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") onClose(); if (e.key === "Enter" && items[0]) { items[0].run(); onClose(); } }} />
            <div className="palette-list">
              {items.map((a) => (
                <button key={a.label} onClick={() => { a.run(); onClose(); }}>
                  <span>{a.label}</span>
                  <small>{a.hint || ""}</small>
                </button>
              ))}
              {!items.length ? <div className="dim">No matching command.</div> : null}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function ReceiptCard({ receipt }) {
  if (!receipt) return null;
  const word = receipt.stamp === "supports" ? "Supports this name" : receipt.stamp === "does_not_show" ? "Does not show this name" : "Too weak to decide";
  return (
    <div className={`receipt stamp-${receipt.stamp}`} role="status">
      <div className="docket">Jury docket · take this with you</div>
      <h3>{word}</h3>
      <p className="receipt-pred">You named <strong>{receipt.prediction}</strong>.</p>
      <p>{receipt.notes}</p>
      <p className="receipt-next"><strong>Tonight:</strong> {receipt.next_action}</p>
      <div className="receipt-meta">
        Papers: {(receipt.evidence || []).join(" · ") || "none pinned"}
        {receipt.evidence_overlap != null ? ` · overlap ${Math.round((receipt.evidence_overlap || 0) * 100)}%` : ""}
      </div>
      <p className="dim">{receipt.honesty}</p>
    </div>
  );
}

export default function App() {
  const reduce = useReducedMotion();
  const [brief, setBrief] = useState(null);
  const [caseFile, setCaseFile] = useState(null);
  const [graph, setGraph] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [pagerank, setPagerank] = useState({});
  const [started, setStarted] = useState(false);
  const [step, setStep] = useState("search");
  const [suspect, setSuspect] = useState(null);
  const [question, setQuestion] = useState("");
  const [log, setLog] = useState([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState([]);
  const [contradictions, setContradictions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [asking, setAsking] = useState(false);
  const [pinned, setPinned] = useState([]);
  const [locked, setLocked] = useState(false);
  const [prediction, setPrediction] = useState("");
  const [rationale, setRationale] = useState("");
  const [investigation, setInvestigation] = useState(null);
  const [fact, setFact] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [cachedAgents, setCachedAgents] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [palette, setPalette] = useState(false);
  const searchRef = useRef(null);
  const searchTimer = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const h = await api.health();
        if (!h.ready) await api.ingest();
        const [b, c, g] = await Promise.all([api.brief(), api.getCase(), api.graph()]);
        setBrief(b);
        setCaseFile(c);
        setGraph(g);
        setSuspect(b.hero_suspect_id || c.suspects?.[0]?.id || null);
        setQuestion(b.hero_question || "Where were you when the cocoa was taken up?");
        setQuery(b.hero_query || "cocoa strychnine");
        try {
          const t = await api.timeline();
          setTimeline(t.events || []);
        } catch { /* optional */ }
        try {
          const com = await api.communities();
          setPagerank(com.suspect_pagerank || {});
        } catch { /* optional */ }
        try {
          const d = await api.dossier(SESSION);
          if (d.pins?.length) setPinned(d.pins);
          if (d.locked) {
            setLocked(true);
            setPrediction(d.locked_prediction?.suspect_id || "");
            setRationale(d.locked_prediction?.rationale || "");
            setStarted(true);
            setStep(d.receipt ? "verdict" : d.investigation ? "investigate" : "search");
          }
          if (d.investigation) setInvestigation(d.investigation);
          if (d.fact_check) setFact(d.fact_check);
          if (d.receipt) setReceipt(d.receipt);
          if (d.hits?.length) setHits(d.hits);
        } catch { /* new jury */ }
      } catch (e) {
        setErr(String(e.message || e));
      }
    })();
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      } else if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        setStarted(true);
        setStep("search");
        setTimeout(() => searchRef.current?.focus(), 40);
      } else if (e.key === "Escape") {
        setPalette(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const selected = useMemo(
    () => caseFile?.suspects?.find((s) => s.id === suspect),
    [caseFile, suspect]
  );
  const evidenceIds = useMemo(() => {
    const ids = [];
    for (const p of pinned) {
      if (p.document_id && !ids.includes(p.document_id)) ids.push(p.document_id);
    }
    return ids;
  }, [pinned]);

  async function runSearch(q) {
    const qq = (q ?? query).trim();
    if (!qq) return;
    setErr("");
    setSearching(true);
    try {
      const r = await api.search(qq, SESSION, 8);
      setHits(r.hits || []);
      setContradictions(r.contradictions || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSearching(false);
    }
  }

  async function openNight(q) {
    setStarted(true);
    setStep("search");
    const queryText = q || brief?.hero_query || "Bauerstein German powder cocoa 17 July";
    setQuery(queryText);
    if (brief?.hero_suspect_id) setPrediction(brief.hero_suspect_id);
    await runSearch(queryText);
  }

  function onQueryChange(v) {
    setQuery(v);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      if (v.trim().length > 2) runSearch(v);
    }, 450);
  }

  async function doAsk(e) {
    e?.preventDefault();
    if (!suspect) return;
    setErr("");
    setAsking(true);
    try {
      const r = await api.interrogate(suspect, question, SESSION);
      setLog((prev) => [...prev.slice(-5), { q: question, a: r.answer, refused: r.refused, who: selected?.name, cites: r.citations || [] }]);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setAsking(false);
    }
  }

  async function doLock() {
    if (!prediction) return;
    setErr("");
    setBusy("lock");
    try {
      await api.lock({
        session_id: SESSION,
        suspect_id: prediction,
        evidence_ids: evidenceIds,
        rationale,
      });
      setLocked(true);
      setStep("investigate");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy("");
    }
  }

  async function runAgents(rerun = false) {
    setErr("");
    setBusy("agents");
    try {
      const inv = await api.investigate(SESSION, rerun);
      if (inv.status === "sealed") {
        setErr(inv.message);
        return;
      }
      const fc = await api.factCheck(SESSION, rerun);
      setInvestigation(inv);
      setFact(fc.status === "sealed" ? null : fc);
      setCachedAgents(Boolean(inv.cached));
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy("");
    }
  }

  async function doVerdict() {
    setErr("");
    setBusy("verdict");
    try {
      const r = await api.verdict({
        session_id: SESSION,
        suspect_id: prediction,
        evidence_ids: evidenceIds,
        rationale,
      });
      setReceipt(r.receipt || null);
      setStep("verdict");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy("");
    }
  }

  function pinHit(h) {
    setPinned((p) => (p.some((x) => x.chunk_id === h.chunk_id) ? p : [...p.slice(-11), h]));
  }

  function jumpTo(id) {
    setStarted(true);
    setStep(id);
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    });
  }

  const faith = investigation?.faithfulness;
  const debate = useMemo(() => {
    const attacks = fact?.claim_attacks || [];
    const claims = investigation?.claims || [];
    if (claims.length) {
      return claims.map((c, i) => ({
        claim: c.text,
        attack: attacks[i]?.attack || fact?.theory_weaknesses?.[i] || "No counter-claim retrieved.",
        verified: c.verification_status === "verified",
      }));
    }
    return (fact?.theory_weaknesses || []).slice(0, 4).map((w) => ({
      claim: investigation?.theory?.slice(0, 160) || "",
      attack: w,
      verified: true,
    }));
  }, [investigation, fact]);

  const paletteActions = [
    { label: "Check this letter against the file", hint: "hero path", run: () => openNight() },
    { label: "Search the papers", hint: "/", run: () => { setStarted(true); jumpTo("search"); setTimeout(() => searchRef.current?.focus(), 40); } },
    { label: "Ask the selected suspect", hint: selected?.name || "", run: () => { setStarted(true); jumpTo("ask"); doAsk(); } },
    { label: "Show the board", hint: "graph", run: () => { setStarted(true); jumpTo("board"); } },
    { label: "Run investigator + fact-checker", hint: locked ? "unsealed" : "lock first", run: () => runAgents() },
    { label: "Submit the docket", hint: prediction || "pick a name", run: () => doVerdict() },
    ...(caseFile?.suspects || []).slice(0, 7).map((s) => ({ label: `Summon ${s.name}`, hint: s.motive_public?.slice(0, 40) || "", run: () => { setSuspect(s.id); jumpTo("ask"); } })),
  ];

  return (
    <div className="app">
      <div className="honesty" role="note">
        {brief?.honesty || "Independent recruitment demo. Not a court. Chapters XII–XIII are sealed. One planted letter is rumour."}
      </div>

      <header className="mast glass">
        <motion.div initial={reduce ? false : { opacity: 0, transform: "translateY(-6px)" }} animate={{ opacity: 1, transform: "translateY(0px)" }} transition={tweenOut}>
          <div className="docket">HO / ESSEX / 1916 / STYLES-COURT / FILE 17-JUL</div>
          <h1>{started ? "SEALED" : (brief?.headline || "Who put the strychnine in the cocoa?")}</h1>
          <p>{started ? (brief?.clock || "Cocoa in the evening. Convulsions hours later. That delay is the case.") : (brief?.wound || "")}</p>
        </motion.div>
        <div className="docket mast-right">
          <div>{brief?.llm_available ? "LLM live" : "Heuristics carrying"}{caseFile ? ` · ${caseFile.manifest?.chunk_count || 0} chunks` : ""}</div>
          <div className="mast-btns">
            <button className="ghostbtn" onClick={() => jumpTo("board")}>Evidence board</button>
            <button className="ghostbtn" onClick={() => setPalette(true)}>⌘K</button>
          </div>
        </div>
      </header>

      {!started ? (
        <section className="cover">
          <div className="cover-card">
            <div className="clock-chip">{brief?.clock || "Cocoa in the evening. Convulsions hours later."}</div>
            <p className="cover-wound">{brief?.wound}</p>
            <p className="dim">{brief?.mocked}</p>
            <blockquote className="letter-quote">
              “Dr Bauerstein … put a fine white powder into the cup — a nerve agent prepared in Berlin, not English strychnine from the village. John Cavendish is innocent.”
              <footer>DOC-ANON-TIP · unverified · broken chain of custody</footer>
            </blockquote>
            <motion.button className="ink big" onClick={() => openNight()} whileTap={reduce ? {} : { scale: 0.98 }}>
              Check this letter against the file
            </motion.button>
            <button className="linkbtn cover-lab" onClick={() => openNight("cocoa strychnine hours delay")}>
              The letter may be the decoy — try the cocoa
            </button>
            <button className="linkbtn cover-lab" onClick={() => { setStarted(true); jumpTo("board"); }}>Open the evidence board</button>
          </div>
        </section>
      ) : (
        <>
          <nav className="stepper desk-nav" aria-label="Investigation panels">
            {STEPS.map((s) => (
              <button key={s.id} className={`step ${step === s.id ? "on" : ""}`} onClick={() => jumpTo(s.id)}>
                {s.label}
              </button>
            ))}
          </nav>

          {timeline.length ? (
            <div className="timeline" role="list" aria-label="Case timeline">
              {timeline.slice(0, 6).map((t, i) => (
                <button key={i} className="tick" onClick={() => { const s = typeof t === "string" ? t : t.label; setQuery(s.slice(0, 60)); jumpTo("search"); runSearch(s.slice(0, 60)); }}>
                  <span className="dot" />
                  <span className="tlabel">{typeof t === "string" ? t.slice(0, 42) : t.label}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className="folder">
            {err ? <div className="err" role="alert">{err}</div> : null}
            <div className="desk-grid">
              <section id="search" className="panel">
                <h2>Evidence search</h2>
                <div className="panel-body">
                  <form className="search-row" onSubmit={(e) => { e.preventDefault(); runSearch(query); }}>
                    <input ref={searchRef} value={query} onChange={(e) => onQueryChange(e.target.value)} aria-label="Search evidence" placeholder="cocoa strychnine…" />
                    <motion.button className="ink" disabled={searching} whileTap={reduce ? {} : { scale: 0.96 }} type="submit">
                      {searching ? "…" : "Find"}
                    </motion.button>
                  </form>
                  {searching ? <Skeleton lines={2} /> : null}
                  <AnimatePresence initial={false}>
                    {hits.slice(0, 5).map((h) => (
                      <motion.div key={h.chunk_id} className="hit" layout initial={reduce ? false : { opacity: 0, transform: "translateY(6px)" }} animate={{ opacity: 1, transform: "translateY(0px)" }} transition={tweenOut}>
                        <div className="meta">
                          <Badge status={h.verification_status} />
                          {h.document_id} · {h.chunk_id}
                          {h.source === "graph" ? <span className="badge verified">graph</span> : null}
                          <button className="linkbtn" onClick={() => pinHit(h)}>Pin to docket</button>
                        </div>
                        <div>{h.text.slice(0, 220)}…</div>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  {!!contradictions.length && (
                    <div className="contra">
                      <strong>Conflicting accounts ({contradictions.length}):</strong>
                      {contradictions.slice(0, 3).map((c, i) => (
                        <div key={i} className="dim">{c.note}</div>
                      ))}
                    </div>
                  )}
                  {!!pinned.length && (
                    <div className="pintray">
                      <h2 style={{ border: 0, padding: 0 }}>Pinned for the docket</h2>
                      {pinned.map((p) => (
                        <div key={p.chunk_id} className="pin">
                          <Badge status={p.verification_status} /> {p.document_id}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <section id="ask" className="panel">
                <h2>Candidate interrogation</h2>
                <div className="panel-body ask-grid">
                  <div>
                    {(caseFile?.suspects || []).map((s) => (
                      <button key={s.id} className={`suspect ${suspect === s.id ? "selected" : ""}`} onClick={() => setSuspect(s.id)}>
                        <span className="initials">{initials(s.name)}</span>
                        <span className="suspect-text">
                          {s.name}
                          <small>{s.motive_public}</small>
                          {pagerank[s.id] != null ? <small className="rank">graph {Math.round(pagerank[s.id] * 1000) / 10}‰</small> : null}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div>
                    <form onSubmit={doAsk}>
                      <textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question for suspect" />
                      <div style={{ height: 8 }} />
                      <motion.button className="ink" disabled={asking} whileTap={reduce ? {} : { scale: 0.97 }} type="submit">
                        {asking ? "Taking statement…" : `Ask ${selected?.name || "suspect"}`}
                      </motion.button>
                    </form>
                    <div className="transcript" aria-live="polite">
                      {log.slice(-3).map((t, i) => (
                        <InterrogationBubble key={`${i}-${t.q}`} who={t.who} q={t.q} a={t.a} />
                      ))}
                      {!log.length ? <div className="dim">Ask about the cocoa tray, the delay, the will. Gossip from the planted letter is rumour.</div> : null}
                    </div>
                  </div>
                </div>
              </section>

              <section id="board" className="panel span-2">
                <h2>Evidence board</h2>
                <div className="panel-body board-body">
                  <Corkboard graph={graph} highlight={prediction ? [prediction] : []} pinned={pinned} />
                </div>
              </section>

              <section id="investigate" className="panel">
                <h2>Investigator</h2>
                <div className="panel-body">
                  {!locked ? (
                    <div className="folder-card sealed-file">Lock a name in Verdict first</div>
                  ) : (
                    <>
                      {!investigation ? (
                        <motion.button className="ink" onClick={() => runAgents(false)} disabled={busy === "agents"} whileTap={reduce ? {} : { scale: 0.97 }}>
                          {busy === "agents" ? "Agents at work…" : "Run investigator + fact-checker"}
                        </motion.button>
                      ) : (
                        <button className="linkbtn" onClick={() => runAgents(true)} disabled={busy === "agents"}>
                          {cachedAgents ? "This run was cached — run again live" : "Run again"}
                        </button>
                      )}
                      {busy === "agents" && !investigation ? <Skeleton /> : null}
                      {investigation ? (
                        <div className="folder-card">
                          <div className="docket">Prosecution</div>
                          <strong>{investigation.primary_suspect}</strong>
                          <ConfidenceMeter value={investigation.confidence} />
                          <p>{investigation.theory}</p>
                          {faith ? <div className="faith">faithfulness {Math.round(faith.faithfulness * 100)}% ({faith.supported}/{faith.total_citations})</div> : null}
                          {investigation.unverified_cited ? <div className="err">Unverified evidence was cited — confidence capped.</div> : null}
                          <div className="trace">{(investigation.trace || []).map((s) => `#${s.step} ${s.action}: ${s.decision}`).join("\n")}</div>
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </section>

              <section id="factcheck" className="panel">
                <h2>Fact-checker</h2>
                <div className="panel-body">
                  {!locked ? (
                    <div className="folder-card sealed-file">Sealed until you lock a name</div>
                  ) : fact ? (
                    <>
                      <div className="folder-card">
                        <div className="docket">Defence</div>
                        <div>Rivals: {(fact.rival_suspects || []).join(", ") || "—"}</div>
                        {(fact.temporal_notes || []).map((t, i) => <div key={i} className="dim">{t}</div>)}
                        <div className="trace">{(fact.trace || []).map((s) => `${s.action}: ${(s.queries || []).join(" | ")}`).join("\n")}</div>
                      </div>
                      {debate.length ? (
                        <div className="debate-lines">
                          {debate.map((d, i) => (
                            <div key={i} className="debate-line">
                              <div><span className="docket">Claim</span><p>{d.claim}</p></div>
                              <div><span className="docket">Attack</span><p>{d.attack}</p></div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="dim">Run the investigator to unseal the defence file.</p>
                  )}
                </div>
              </section>

              <section id="verdict" className="panel span-2">
                <h2>Lock a name, then submit the verdict</h2>
                <div className="panel-body">
                  <p className="dim">Make a prediction before the agents speak. Pins become the evidence list. The sealed file scores the name; it does not publish the method.</p>
                  <div className="seal-wrap lock-row">
                    <motion.button className={`seal ${locked ? "locked" : ""}`} onClick={doLock} disabled={!prediction || locked || busy === "lock"} whileTap={reduce ? {} : { scale: 0.9 }} transition={springSnappy} aria-label={locked ? "Prediction locked" : "Lock prediction"}>
                      {locked ? "WAX\nSET" : "LOCK\nNAME"}
                    </motion.button>
                    <div className="lockform">
                      <label className="docket">Your prediction</label>
                      <select value={prediction} onChange={(e) => setPrediction(e.target.value)}>
                        <option value="">Select a name</option>
                        {(caseFile?.suspects || []).map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                      <div style={{ height: 6 }} />
                      <input placeholder="Why this name?" value={rationale} onChange={(e) => setRationale(e.target.value)} />
                      <div className="pin-chips">
                        {pinned.length ? pinned.map((p) => (
                          <span key={p.chunk_id} className="chip"><Badge status={p.verification_status} /> {p.document_id}</span>
                        )) : <span className="dim">Pin papers from Search if you want evidence on the docket.</span>}
                      </div>
                      <div style={{ height: 10 }} />
                      <motion.button className="ink big" onClick={doVerdict} disabled={!locked || !prediction || busy === "verdict"} whileTap={reduce ? {} : { scale: 0.98 }}>
                        {busy === "verdict" ? "Consulting sealed file…" : "Stamp the jury docket"}
                      </motion.button>
                    </div>
                  </div>
                  <AnimatePresence>
                    {receipt ? (
                      <motion.div initial={reduce ? false : { opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={springSoft}>
                        <ReceiptCard receipt={receipt} />
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              </section>
            </div>
          </div>
        </>
      )}

      <Palette open={palette} onClose={() => setPalette(false)} actions={paletteActions} />
      <footer className="foot dim">Search, ask, board, investigator, fact-checker, verdict — all on the desk. Lock a name before the agents speak.</footer>
    </div>
  );
}
