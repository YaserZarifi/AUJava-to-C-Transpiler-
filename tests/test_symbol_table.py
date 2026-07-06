"""Tests for the symbol table and class table (Phase 3)."""

import pytest

from src.errors import SemanticError
from src.parser import parse
from src.semantic.symbol_table import ClassTable, ScopeStack
from src.semantic.types import BOOLEAN, INT, ClassType


def build(src):
    return ClassTable.build(parse(src))


# --- class table construction ---

def test_collects_classes_fields_methods():
    ct = build("class A { int a; boolean b; int test(int d) {} }")
    ci = ct.get("A")
    assert set(ci.fields) == {"a", "b"}
    assert ci.fields["a"].type == INT
    assert ci.fields["b"].type == BOOLEAN
    assert ci.methods["test"].param_types == [INT]
    assert ci.methods["test"].return_type == INT


def test_forward_reference_field_type():
    # B has a field of type A, but A is declared later -- must resolve.
    ct = build("class B { A a; } class A {}")
    assert ct.get("B").fields["a"].type == ClassType("A")


def test_duplicate_class_name_errors():
    with pytest.raises(SemanticError, match="already defined"):
        build("class A {} class A {}")


def test_duplicate_field_errors():
    with pytest.raises(SemanticError, match="already defined"):
        build("class A { int x; boolean x; }")


def test_unknown_type_errors():
    with pytest.raises(SemanticError, match="unknown type"):
        build("class A { Nope x; }")


# --- inheritance graph ---

def test_unknown_superclass_errors():
    with pytest.raises(SemanticError, match="unknown class"):
        build("class B extends Ghost {}")


def test_extends_later_defined_class_ok():
    ct = build("class B extends A {} class A {}")
    assert ct.get("B").superclass == "A"


def test_cyclic_inheritance_two_level_errors():
    with pytest.raises(SemanticError, match="cyclic"):
        build("class A extends B {} class B extends A {}")


def test_cyclic_inheritance_three_level_errors():
    with pytest.raises(SemanticError, match="cyclic"):
        build("class A extends B {} class B extends C {} class C extends A {}")


def test_self_inheritance_errors():
    with pytest.raises(SemanticError, match="cyclic"):
        build("class A extends A {}")


# --- inheritance-aware lookup ---

def test_lookup_inherited_field_and_method():
    ct = build("class A { int a; int m() {} } class B extends A { int b; }")
    assert ct.lookup_field("B", "a").owner == "A"      # inherited
    assert ct.lookup_field("B", "b").owner == "B"      # own
    assert ct.lookup_method("B", "m").owner == "A"     # inherited
    assert ct.lookup_field("B", "nope") is None


def test_is_subclass_and_assignable():
    ct = build("class A {} class B extends A {} class C extends B {}")
    assert ct.is_subclass("C", "A")       # transitive
    assert ct.is_subclass("A", "A")       # reflexive
    assert not ct.is_subclass("A", "C")
    # upcast allowed: a C value fits an A-typed slot; not the reverse
    assert ct.is_assignable(ClassType("A"), ClassType("C"))
    assert not ct.is_assignable(ClassType("C"), ClassType("A"))


# --- scope stack ---

def test_scope_lookup_innermost_first():
    s = ScopeStack()
    s.push()
    s.define("i", INT, 1, 1)
    s.push()
    s.define("i", BOOLEAN, 2, 1)          # shadows outer i
    assert s.lookup("i").type == BOOLEAN  # innermost wins
    s.pop()
    assert s.lookup("i").type == INT      # outer visible again


def test_same_scope_redeclaration_errors():
    s = ScopeStack()
    s.push()
    s.define("x", INT, 1, 1)
    with pytest.raises(SemanticError, match="already defined in this scope"):
        s.define("x", INT, 2, 1)


def test_lookup_missing_returns_none():
    s = ScopeStack()
    s.push()
    assert s.lookup("ghost") is None
