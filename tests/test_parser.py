"""Tests for the parser (Phase 2)."""

import pytest

from src import ast_nodes as ast
from src.errors import ParserError
from src.parser import parse


def parse_stmt(src):
    """Parse a single statement by wrapping it in a throwaway method body."""
    program = parse("class C { void m() { " + src + " } }")
    return program.classes[0].methods[0].body.statements[0]


def parse_expr(src):
    """Parse a single expression via an expression statement."""
    stmt = parse_stmt(src + ";")
    return stmt.expr


# --- program structure ---

def test_empty_class():
    prog = parse("class A {}")
    assert len(prog.classes) == 1
    assert prog.classes[0].name == "A"
    assert prog.classes[0].superclass is None


def test_public_class_and_extends():
    prog = parse("public class Main {} class B extends A {}")
    assert prog.classes[0].is_public is True
    assert prog.classes[1].name == "B"
    assert prog.classes[1].superclass == "A"


def test_multiple_classes_any_order():
    # A field referencing a class defined later must still parse fine.
    prog = parse("class B { A a; } class A {}")
    assert [c.name for c in prog.classes] == ["B", "A"]
    assert prog.classes[0].fields[0].type.name == "A"


def test_field_and_method_members():
    prog = parse("class A { int a; static boolean flag; int test(int d) { return a; } }")
    cls = prog.classes[0]
    assert [f.name for f in cls.fields] == ["a", "flag"]
    assert cls.fields[1].is_static is True
    assert cls.methods[0].name == "test"
    assert cls.methods[0].params[0].name == "d"
    assert cls.methods[0].return_type.name == "int"


def test_main_signature_parses():
    src = "public class Main { public static void main(String[] args) { } }"
    m = parse(src).classes[0].methods[0]
    assert m.is_public and m.is_static
    assert m.return_type.name == "void"
    assert m.params[0].is_array and m.params[0].name == "args"


# --- operator precedence ---

def test_precedence_mul_over_add():
    # 1 + 2 * 3  ->  (+  1  (*  2 3))
    e = parse_expr("1 + 2 * 3")
    assert isinstance(e, ast.BinaryOp) and e.op == "+"
    assert isinstance(e.left, ast.IntLiteral) and e.left.value == 1
    assert isinstance(e.right, ast.BinaryOp) and e.right.op == "*"


def test_precedence_full_ladder():
    # a = b || c && d == e < f + g * h
    e = parse_expr("a = b || c && d == e < f + g * h")
    assert isinstance(e, ast.Assignment)          # '=' is lowest
    assert isinstance(e.value, ast.BinaryOp) and e.value.op == "||"


def test_assignment_right_associative():
    # a = b = c  ->  a = (b = c)
    e = parse_expr("a = b = c")
    assert isinstance(e, ast.Assignment)
    assert isinstance(e.value, ast.Assignment)


def test_unary_minus_and_not():
    e = parse_expr("!a")
    assert isinstance(e, ast.UnaryOp) and e.op == "!"
    e2 = parse_expr("-x")
    assert isinstance(e2, ast.UnaryOp) and e2.op == "-"


def test_parentheses_override_precedence():
    # (1 + 2) * 3  ->  (*  (+ 1 2)  3)
    e = parse_expr("(1 + 2) * 3")
    assert isinstance(e, ast.BinaryOp) and e.op == "*"
    assert isinstance(e.left, ast.BinaryOp) and e.left.op == "+"


# --- primary expressions ---

def test_new_object():
    e = parse_expr("new Student()")
    assert isinstance(e, ast.NewObject) and e.class_name == "Student"


def test_field_access_and_this():
    e = parse_expr("this.i")
    assert isinstance(e, ast.FieldAccess) and e.name == "i"
    assert isinstance(e.receiver, ast.This)


def test_method_call_on_receiver():
    e = parse_expr("a.test(1, 2)")
    assert isinstance(e, ast.MethodCall)
    assert e.name == "test" and len(e.args) == 2
    assert isinstance(e.receiver, ast.Identifier) and e.receiver.name == "a"


def test_bare_call_is_implicit_this():
    e = parse_expr("bar(n)")
    assert isinstance(e, ast.MethodCall)
    assert e.receiver is None and e.name == "bar"


def test_chained_access():
    e = parse_expr("a.b.c()")
    assert isinstance(e, ast.MethodCall) and e.name == "c"
    assert isinstance(e.receiver, ast.FieldAccess) and e.receiver.name == "b"


# --- statements ---

def test_if_else():
    s = parse_stmt("if (x) { return 1; } else { return 2; }")
    assert isinstance(s, ast.If)
    assert s.else_branch is not None


def test_while_with_break_continue():
    s = parse_stmt("while (true) { break; }")
    assert isinstance(s, ast.While)
    assert isinstance(s.body.statements[0], ast.Break)


def test_println_statement():
    s = parse_stmt("System.out.println(1 + 2);")
    assert isinstance(s, ast.Println)
    assert isinstance(s.arg, ast.BinaryOp)


def test_vardecl_class_typed_vs_exprstmt():
    decl = parse_stmt("A a = new A();")
    assert isinstance(decl, ast.VarDecl) and decl.type.name == "A"
    expr_stmt = parse_stmt("a.test();")
    assert isinstance(expr_stmt, ast.ExprStmt)
    assign_stmt = parse_stmt("a = 5;")
    assert isinstance(assign_stmt, ast.ExprStmt)
    assert isinstance(assign_stmt.expr, ast.Assignment)


def test_return_with_and_without_value():
    assert parse_stmt("return;").value is None
    assert parse_stmt("return 5;").value is not None


# --- error handling ---

def test_syntax_error_reports_position():
    with pytest.raises(ParserError) as exc:
        parse("class A { int x = ; }")   # missing expression
    err = exc.value
    assert err.line >= 1 and err.column >= 1


def test_missing_semicolon_errors():
    with pytest.raises(ParserError):
        parse("class A { void m() { int x = 5 } }")


def test_missing_brace_errors():
    with pytest.raises(ParserError):
        parse("class A {")
