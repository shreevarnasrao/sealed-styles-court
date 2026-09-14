from app.models.schemas import VerdictSubmission
from app.verdict.score import score


def test_correct_primary():
    r = score(VerdictSubmission(suspect_id="alfred_inglethorp", evidence_ids=["DOC-CH05"]), None)
    assert r.correct_suspect
    assert "method" not in r.notes.lower()
    assert "strychnine" not in r.notes.lower()


def test_accomplice_also_counts():
    r = score(VerdictSubmission(suspect_id="evelyn_howard", evidence_ids=[]), None)
    assert r.correct_suspect


def test_wrong_suspect():
    r = score(VerdictSubmission(suspect_id="dr_bauerstein", evidence_ids=[]), None)
    assert not r.correct_suspect


def test_does_not_leak_solution_method():
    r = score(VerdictSubmission(suspect_id="john_cavendish", evidence_ids=["DOC-CH11"]), None)
    blob = r.model_dump_json().lower()
    assert "bromide" not in blob
    assert "precipit" not in blob
