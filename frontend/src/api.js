const j = async (path, opts = {}) => {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json();
};

export const api = {
  health: () => j("/health"),
  ingest: () => j("/ingest", { method: "POST" }),
  brief: () => j("/brief"),
  dossier: (session_id) => j(`/dossier/${session_id}`),
  desk: (payload) => j("/desk", { method: "POST", body: JSON.stringify(payload) }),
  getCase: () => j("/case"),
  graph: () => j("/graph"),
  timeline: () => j("/timeline"),
  communities: () => j("/communities"),
  search: (query, session_id, k = 8) =>
    j("/search_evidence", { method: "POST", body: JSON.stringify({ query, session_id, k }) }),
  interrogate: (candidate_id, question, session_id) =>
    j("/interrogate", {
      method: "POST",
      body: JSON.stringify({ candidate_id, question, session_id }),
    }),
  lock: (payload) => j("/lock_prediction", { method: "POST", body: JSON.stringify(payload) }),
  investigate: (session_id, rerun = false) =>
    j("/investigate", { method: "POST", body: JSON.stringify({ session_id, rerun }) }),
  factCheck: (session_id, rerun = false) =>
    j("/fact_check", { method: "POST", body: JSON.stringify({ session_id, rerun }) }),
  verdict: (payload) => j("/submit_verdict", { method: "POST", body: JSON.stringify(payload) }),
  session: (id) => j(`/session/${id}`),
};
