from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.models.schemas import FactCheckResult, InvestigationResult


@dataclass
class Session:
    session_id: str
    prediction_locked: bool = False
    locked_prediction: dict | None = None
    investigation: InvestigationResult | None = None
    fact_check: FactCheckResult | None = None
    searches: int = 0
    interrogations: int = 0
    pins: list = field(default_factory=list)
    phase: str = "opened"
    verdict: dict | None = None
    last_hits: list = field(default_factory=list)
    last_contradictions: list = field(default_factory=list)
    last_answer: dict | None = None
    last_query: str = ""


class SessionBook:
    """In-memory sessions with JSON-file persistence (persistent agent memory bonus).

    Persists only lock state + counters (not full traces) so a restart keeps the
    jury lock. Traces are re-runnable via /investigate. File lives outside git.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._data: dict[str, Session] = {}
        self._path = path
        self._loaded = False

    def _file(self) -> Path:
        if self._path is not None:
            return self._path
        from app.config import PROCESSED

        return PROCESSED / "sessions.json"

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            p = self._file()
            if not p.exists():
                return
            raw = json.loads(p.read_text(encoding="utf-8"))
            for sid, d in raw.items():
                self._data[sid] = Session(
                    session_id=sid,
                    prediction_locked=bool(d.get("prediction_locked")),
                    locked_prediction=d.get("locked_prediction"),
                    searches=int(d.get("searches", 0)),
                    interrogations=int(d.get("interrogations", 0)),
                    pins=list(d.get("pins") or []),
                    phase=str(d.get("phase") or "opened"),
                )
        except Exception:
            pass

    def _save(self) -> None:
        try:
            p = self._file()
            p.parent.mkdir(parents=True, exist_ok=True)
            raw = {
                sid: {
                    "prediction_locked": s.prediction_locked,
                    "locked_prediction": s.locked_prediction,
                    "searches": s.searches,
                    "interrogations": s.interrogations,
                    "pins": s.pins,
                    "phase": s.phase,
                }
                for sid, s in self._data.items()
            }
            p.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, session_id: str) -> Session:
        self._ensure_loaded()
        if session_id not in self._data:
            self._data[session_id] = Session(session_id=session_id)
        return self._data[session_id]

    def save(self) -> None:
        self._ensure_loaded()
        self._save()
