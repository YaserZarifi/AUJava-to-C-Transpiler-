"""Tests for code generation.

Phase 5 (this file for now): the Three-Address Code IR and expression
flattening. Later phases add gcc-backed end-to-end code-generation tests.
"""

from src.codegen import ir
from src.parser import parse


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
