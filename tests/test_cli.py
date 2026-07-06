"""Tests for the command-line interface / full pipeline (Phase 10)."""

import os

from src.main import compile_source, main


VALID = (
    "public class Main { public static void main(String[] args) { "
    "System.out.println(1 + 2 * 3); } }"
)


def test_compile_source_valid():
    c_code, errors = compile_source(VALID)
    assert errors == []
    assert c_code is not None
    assert "int main(void)" in c_code


def test_compile_source_syntax_error():
    c_code, errors = compile_source("class A {")     # missing brace
    assert c_code is None
    assert len(errors) == 1


def test_compile_source_semantic_error():
    c_code, errors = compile_source("class A {}")     # no main
    assert c_code is None
    assert any("entry point" in e.message for e in errors)


def test_cli_writes_output_on_success(tmp_path):
    src = tmp_path / "prog.aujava"
    src.write_text(VALID, encoding="utf-8")
    out = tmp_path / "prog.c"
    rc = main([str(src), "-o", str(out)])
    assert rc == 0
    assert out.exists()
    assert "int main(void)" in out.read_text(encoding="utf-8")


def test_cli_default_output_path(tmp_path):
    src = tmp_path / "hello.aujava"
    src.write_text(VALID, encoding="utf-8")
    rc = main([str(src)])
    assert rc == 0
    assert (tmp_path / "hello.c").exists()


def test_cli_no_output_file_on_error(tmp_path):
    src = tmp_path / "bad.aujava"
    src.write_text("class A {}", encoding="utf-8")   # no main -> semantic error
    out = tmp_path / "bad.c"
    rc = main([str(src), "-o", str(out)])
    assert rc == 1
    assert not out.exists()          # crucial: no C file when the input is invalid


def test_cli_missing_input_file(tmp_path):
    rc = main([str(tmp_path / "does_not_exist.aujava")])
    assert rc == 1
