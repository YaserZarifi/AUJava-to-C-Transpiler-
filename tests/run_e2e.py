"""End-to-end test harness.

Runs every program in tests/inputs/ through the full compiler pipeline:

* Files named `err_*.aujava` are EXPECTED to fail compilation (a lexical,
  syntactic, or semantic error) and to produce no C output.
* Every other `*.aujava` is expected to compile cleanly; its generated C is
  compiled with gcc, executed, and its stdout compared against the matching
  file in tests/expected/.

Run standalone:   python tests/run_e2e.py
It prints a PASS/FAIL line per program and exits non-zero if anything failed.
"""

import os
import sys

# allow running directly as `python tests/run_e2e.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import compile_source
from tests.gcc_utils import compile_and_run, find_gcc


HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "inputs")
EXPECTED = os.path.join(HERE, "expected")


def _norm(text):
    return text.replace("\r\n", "\n")


def _check_one(path, have_gcc):
    """Return (status, message) where status is 'pass', 'fail', or 'skip'."""
    name = os.path.basename(path)
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    c_code, errors = compile_source(source)

    if name.startswith("err_"):
        if errors and c_code is None:
            return "pass", f"correctly rejected ({errors[0].message})"
        return "fail", "expected a compile error but compilation succeeded"

    # a program that should compile
    if errors:
        return "fail", f"unexpected compile error: {errors[0].message}"
    if not have_gcc:
        return "skip", "compiled to C ok; gcc unavailable to run it"

    stem = os.path.splitext(name)[0]
    expected_path = os.path.join(EXPECTED, stem + ".txt")
    if not os.path.exists(expected_path):
        return "fail", f"missing expected output file {stem}.txt"
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = _norm(f.read())

    try:
        actual = _norm(compile_and_run(c_code))
    except RuntimeError as exc:
        return "fail", f"gcc/run failed: {exc}"

    if actual == expected:
        return "pass", "output matches"
    return "fail", f"output mismatch: expected {expected!r}, got {actual!r}"


def run_all():
    have_gcc = find_gcc() is not None
    results = []
    for name in sorted(os.listdir(INPUTS)):
        if not name.endswith(".aujava"):
            continue
        results.append((name, *_check_one(os.path.join(INPUTS, name), have_gcc)))
    return results


def main():
    results = run_all()
    passed = failed = skipped = 0
    for name, status, message in results:
        symbol = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
        print(f"[{symbol}] {name:32} {message}")
        passed += status == "pass"
        failed += status == "fail"
        skipped += status == "skip"
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
