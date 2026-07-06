"""Tests for code generation.

Phase 5 (this file for now): the Three-Address Code IR and expression
flattening. Later phases add gcc-backed end-to-end code-generation tests.
"""

import pytest

from src.codegen import ir
from src.codegen.c_emitter import generate
from src.parser import parse
from src.semantic.analyzer import analyze
from tests.gcc_utils import compile_and_run, find_gcc


requires_gcc = pytest.mark.skipif(find_gcc() is None, reason="gcc not installed")


def run_main(body):
    """Transpile a Main program with the given body, compile & run it, return stdout."""
    src = "public class Main { public static void main(String[] args) { " + body + " } }"
    program = parse(src)
    errors = analyze(program)
    assert errors == [], "; ".join(str(e) for e in errors)
    return compile_and_run(generate(program))


def flatten(expr_src):
    """Parse a single expression and flatten it to TAC."""
    program = parse("class C { void m() { int _ = " + expr_src + "; } }")
    vardecl = program.classes[0].methods[0].body.statements[0]
    out = []
    result = ir.flatten_expr(vardecl.init, out, ir.Namer())
    return out, result


def test_int_literal_gets_a_temp():
    out, result = flatten("42")
    assert out == [ir.Assign(ir.Temp(1), ir.Const(42))]
    assert result == ir.Temp(1)


def test_bool_literal_becomes_zero_or_one():
    out, _ = flatten("true")
    assert out == [ir.Assign(ir.Temp(1), ir.Const(1))]
    out2, _ = flatten("false")
    assert out2 == [ir.Assign(ir.Temp(1), ir.Const(0))]


def test_spec_example_1_plus_2_times_3():
    # The exact example from the project spec: five temporaries.
    out, result = flatten("1 + 2 * 3")
    assert out == [
        ir.Assign(ir.Temp(1), ir.Const(1)),
        ir.Assign(ir.Temp(2), ir.Const(2)),
        ir.Assign(ir.Temp(3), ir.Const(3)),
        ir.BinOp(ir.Temp(4), "*", ir.Temp(2), ir.Temp(3)),
        ir.BinOp(ir.Temp(5), "+", ir.Temp(1), ir.Temp(4)),
    ]
    assert result == ir.Temp(5)


def test_unary_operator():
    out, result = flatten("-5")
    assert out == [
        ir.Assign(ir.Temp(1), ir.Const(5)),
        ir.UnOp(ir.Temp(2), "-", ir.Temp(1)),
    ]
    assert result == ir.Temp(2)


def test_nested_expression_temp_order():
    # (1 + 2) * 3 : temps for 1,2 then their sum, then 3, then product
    out, result = flatten("(1 + 2) * 3")
    assert out == [
        ir.Assign(ir.Temp(1), ir.Const(1)),
        ir.Assign(ir.Temp(2), ir.Const(2)),
        ir.BinOp(ir.Temp(3), "+", ir.Temp(1), ir.Temp(2)),
        ir.Assign(ir.Temp(4), ir.Const(3)),
        ir.BinOp(ir.Temp(5), "*", ir.Temp(3), ir.Temp(4)),
    ]
    assert result == ir.Temp(5)


def test_namer_unique_temps_and_labels():
    n = ir.Namer()
    assert n.new_temp() == ir.Temp(1)
    assert n.new_temp() == ir.Temp(2)
    assert n.new_label("if_end") == "if_end_1"
    assert n.new_label("loop_start") == "loop_start_2"


# ------------------------------------------------------------ end-to-end (gcc) tests

@requires_gcc
def test_e2e_hello_arithmetic():
    assert run_main("System.out.println(1 + 2 * 3);") == "7\n"


@requires_gcc
def test_e2e_precedence_and_parens():
    assert run_main("System.out.println((1 + 2) * 3);") == "9\n"
    assert run_main("System.out.println(10 - 2 - 3);") == "5\n"        # left-assoc
    assert run_main("System.out.println(7 % 3 + 1);") == "2\n"


@requires_gcc
def test_e2e_variables_and_assignment():
    body = "int x = 5; int y = x + 10; x = x + 1; System.out.println(x); System.out.println(y);"
    assert run_main(body) == "6\n15\n"


@requires_gcc
def test_e2e_boolean_println():
    assert run_main("System.out.println(true);") == "true\n"
    assert run_main("System.out.println(1 < 2);") == "true\n"
    assert run_main("System.out.println(2 < 1);") == "false\n"
    assert run_main("System.out.println(!(1 == 1));") == "false\n"


@requires_gcc
def test_e2e_if_else():
    body = "int x = 5; if (x < 10) { System.out.println(1); } else { System.out.println(2); }"
    assert run_main(body) == "1\n"
    body2 = "int x = 50; if (x < 10) { System.out.println(1); } else { System.out.println(2); }"
    assert run_main(body2) == "2\n"


@requires_gcc
def test_e2e_while_counter():
    body = "int i = 0; while (i < 3) { System.out.println(i); i = i + 1; }"
    assert run_main(body) == "0\n1\n2\n"


@requires_gcc
def test_e2e_shadowing_spec_example():
    # The spec's exact shadowing example: inner boolean i, outer int i.
    body = (
        "int i = 100;"
        "{ boolean i = true; System.out.println(i); }"
        "System.out.println(i);"
    )
    assert run_main(body) == "true\n100\n"


@requires_gcc
def test_e2e_nested_break_continue_affect_innermost_only():
    body = (
        "int i = 0;"
        "while (i < 2) {"
        "  i = i + 1;"
        "  int j = 0;"
        "  while (true) {"
        "    j = j + 1;"
        "    if (j == 1) { continue; }"
        "    if (j >= 3) { break; }"
        "    System.out.println(j);"
        "  }"
        "  System.out.println(0 - i);"
        "}"
    )
    assert run_main(body) == "2\n-1\n2\n-2\n"


# ------------------------------------------------------- Phase 7: classes / objects

def run_program(src):
    """Transpile a full program source, compile & run it, return stdout."""
    program = parse(src)
    errors = analyze(program)
    assert errors == [], "; ".join(str(e) for e in errors)
    return compile_and_run(generate(program))


@requires_gcc
def test_e2e_object_field_and_method():
    src = (
        "class A { int a; int test(int d) { return a * d; } } "
        "public class Main { public static void main(String[] args) { "
        "  A obj = new A(); obj.a = 5; System.out.println(obj.test(10)); } }"
    )
    assert run_program(src) == "50\n"


@requires_gcc
def test_e2e_this_field_vs_local_spec_example():
    # The spec's exact `this` example: field i=100, local i=200.
    src = (
        "class A { int i; void test() { "
        "  i = 100; int i = 200; "
        "  System.out.println(i); System.out.println(this.i); } } "
        "public class Main { public static void main(String[] args) { "
        "  A a = new A(); a.test(); } }"
    )
    assert run_program(src) == "200\n100\n"


@requires_gcc
def test_e2e_method_calls_another_method_forward():
    # foo calls bar, which is declared later (implicit-this call).
    src = (
        "class B { int foo(int n) { return bar(n); } int bar(int m) { return m + 1; } } "
        "public class Main { public static void main(String[] args) { "
        "  B b = new B(); System.out.println(b.foo(41)); } }"
    )
    assert run_program(src) == "42\n"


@requires_gcc
def test_e2e_object_reference_field_and_forward_class():
    # Node.next is an object reference to a class; chained field access.
    src = (
        "class Node { int val; Node next; } "
        "public class Main { public static void main(String[] args) { "
        "  Node a = new Node(); a.val = 7; "
        "  Node b = new Node(); b.val = 9; "
        "  a.next = b; System.out.println(a.next.val); } }"
    )
    assert run_program(src) == "9\n"


@requires_gcc
def test_e2e_object_equality_is_pointer_comparison():
    src = (
        "class P {} "
        "public class Main { public static void main(String[] args) { "
        "  P x = new P(); P y = x; P z = new P(); "
        "  System.out.println(x == y); System.out.println(x == z); } }"
    )
    assert run_program(src) == "true\nfalse\n"


@requires_gcc
def test_e2e_class_used_before_defined():
    # Main uses class Helper before it is textually defined -- any order allowed.
    src = (
        "public class Main { public static void main(String[] args) { "
        "  Helper h = new Helper(); System.out.println(h.twice(21)); } } "
        "class Helper { int twice(int n) { return n + n; } }"
    )
    assert run_program(src) == "42\n"
