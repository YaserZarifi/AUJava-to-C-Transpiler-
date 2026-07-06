"""Pytest wrapper around the end-to-end harness (tests/run_e2e.py)."""

from tests.run_e2e import run_all


def test_all_e2e_programs_pass():
    results = run_all()
    failures = [(name, msg) for name, status, msg in results if status == "fail"]
    assert not failures, "e2e failures:\n" + "\n".join(f"{n}: {m}" for n, m in failures)
    # sanity: we actually discovered a reasonable number of programs
    assert len(results) >= 15
