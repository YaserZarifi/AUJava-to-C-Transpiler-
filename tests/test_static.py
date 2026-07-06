"""Tests for static fields & methods (Phase 9, bonus)."""

import pytest

from src.codegen.c_emitter import generate
from src.parser import parse
from src.semantic.analyzer import analyze
from tests.gcc_utils import compile_and_run, find_gcc


requires_gcc = pytest.mark.skipif(find_gcc() is None, reason="gcc not installed")


def errors_of(src):
    return analyze(parse(src))


def texts(errors):
    return " || ".join(e.message for e in errors)


def run_program(src):
    program = parse(src)
    errors = analyze(program)
    assert errors == [], "; ".join(str(e) for e in errors)
    return compile_and_run(generate(program))


VALID_MAIN = "public class Main { public static void main(String[] args) {} }"


# ---------------------------------------------------------------- end-to-end (gcc)

@requires_gcc
def test_static_field_and_methods_counter():
    src = (
        "class Counter { static int count; "
        "  static void increment() { count = count + 1; } "
        "  static int get() { return count; } } "
        "public class Main { public static void main(String[] args) { "
        "  Counter.increment(); Counter.increment(); Counter.increment(); "
        "  System.out.println(Counter.get()); "
        "  System.out.println(Counter.count); } }"
    )
    assert run_program(src) == "3\n3\n"


@requires_gcc
def test_static_method_with_args_and_return():
    src = (
        "class MathUtil { static int add(int a, int b) { return a + b; } } "
        "public class Main { public static void main(String[] args) { "
        "  System.out.println(MathUtil.add(20, 22)); } }"
    )
    assert run_program(src) == "42\n"


@requires_gcc
def test_instance_method_reads_and_writes_static_field():
    src = (
        "class Reg { static int total; void add(int n) { total = total + n; } } "
        "public class Main { public static void main(String[] args) { "
        "  Reg r = new Reg(); r.add(5); r.add(7); "
        "  System.out.println(Reg.total); } }"
    )
    assert run_program(src) == "12\n"


@requires_gcc
def test_static_methods_are_independent_across_inheritance():
    # A child's static method with the same name does NOT override; both exist.
    src = (
        "class A { static int who() { return 1; } } "
        "class B extends A { static int who() { return 2; } } "
        "public class Main { public static void main(String[] args) { "
        "  System.out.println(A.who()); System.out.println(B.who()); } }"
    )
    assert run_program(src) == "1\n2\n"


@requires_gcc
def test_static_field_initialized_to_zero():
    src = (
        "class Config { static int value; } "
        "public class Main { public static void main(String[] args) { "
        "  System.out.println(Config.value); } }"
    )
    assert run_program(src) == "0\n"


# ---------------------------------------------------------------- semantic rules

def test_static_method_via_instance_is_error():
    src = (
        "class A { static int who() { return 1; } } "
        "public class Main { public static void main(String[] args) { "
        "  A a = new A(); System.out.println(a.who()); } }"
    )
    assert "must be called via the class name" in texts(errors_of(src))


def test_static_field_via_instance_is_error():
    src = (
        "class A { static int v; } "
        "public class Main { public static void main(String[] args) { "
        "  A a = new A(); System.out.println(a.v); } }"
    )
    assert "must be accessed via the class name" in texts(errors_of(src))


def test_static_method_can_call_static_method_bare():
    src = (
        "class A { static int a() { return b(); } static int b() { return 5; } } "
        + VALID_MAIN
    )
    assert errors_of(src) == []


def test_instance_field_from_static_method_still_errors():
    src = "class A { int f; static void s() { int x = f; } } " + VALID_MAIN
    assert "cannot access instance field" in texts(errors_of(src))
