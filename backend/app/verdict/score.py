from __future__ import annotations

import json
from pathlib import Path

from app.config import SEALED
from app.models.schemas import VerdictScore, VerdictSubmission


def load_solution(path: Path | None = None) -> dict:
    p = path or (SEALED / "solution.json")
    return json.loads(p.read_text(encoding="utf-8"))


def score(submission: VerdictSubmission, locked: dict | None) -> VerdictScore:
    sol = load_solution()
    accepted = set(sol.get("accepted_suspect_ids") or [])
    correct = submission.suspect_id in accepted
    canonical = set(sol.get("canonical_evidence_ids") or [])
    given = set(submission.evidence_ids or [])
    overlap = (len(canonical & given) / len(canonical)) if canonical else 0.0
    notes = []
    if correct:
        notes.append("The sealed file lists this person among those responsible.")
        if submission.suspect_id == sol.get("primary_suspect_id") and sol.get("accomplice_id"):
            notes.append("The file also records that this was not a lone act. Look again at who left the house after the quarrel.")
        elif submission.suspect_id == sol.get("accomplice_id"):
            notes.append("This person is on the sealed list. The other name is the one who stood to inherit.")
    else:
        notes.append("That name is not the one in the sealed file.")
        notes.append("Re-open the will, the cocoa, and who benefited from being loudly suspected.")
    matched = None
    if locked:
        matched = locked.get("suspect_id") == submission.suspect_id
        if matched is False:
            notes.append("Your final verdict differs from the prediction you locked.")
    return VerdictScore(
        correct_suspect=correct,
        evidence_overlap=round(overlap, 3),
        notes=" ".join(notes),
        locked_prediction_matched=matched,
    )
