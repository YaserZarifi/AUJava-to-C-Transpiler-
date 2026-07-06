"""End-to-end tests for inheritance & polymorphism (Phase 8, bonus)."""

import pytest

from src.codegen.c_emitter import generate
from src.parser import parse
from src.semantic.analyzer import analyze
from tests.gcc_utils import compile_and_run, find_gcc


requires_gcc = pytest.mark.skipif(find_gcc() is None, reason="gcc not installed")


def run_program(src):
    program = parse(src)
    errors = analyze(program)
    assert errors == [], "; ".join(str(e) for e in errors)
    return compile_and_run(generate(program))


@requires_gcc
def test_inherited_field():
    src = (
        "class A { int a; } "
        "class B extends A { int b; } "
        "public class Main { public static void main(String[] args) { "
        "  B x = new B(); x.a = 3; x.b = 4; System.out.println(x.a + x.b); } }"
    )
    assert run_program(src) == "7\n"


@requires_gcc
def test_inherited_method_not_overridden():
    # getA is declared in A and reached through the super chain from a B object.
    src = (
        "class A { int a; int getA() { return a; } } "
        "class B extends A { } "
        "public class Main { public static void main(String[] args) { "
        "  B x = new B(); x.a = 9; System.out.println(x.getA()); } }"
    )
    assert run_program(src) == "9\n"


@requires_gcc
def test_two_level_override_and_polymorphism():
    # The spec's A/B example plus an upcast that must dispatch dynamically.
    src = (
        "class A { int a; int test(int d) { return a * d; } } "
        "class B extends A { int test(int d) { return a + d; } } "
        "public class Main { public static void main(String[] args) { "
        "  B b = new B(); b.a = 10; System.out.println(b.test(5)); "   # 15
        "  A up = b; System.out.println(up.test(5)); "                  # 15 (polymorphic)
        "  A a = new A(); a.a = 10; System.out.println(a.test(5)); } }"  # 50
    )
    assert run_program(src) == "15\n15\n50\n"


@requires_gcc
def test_three_level_override_propagation():
    # C overrides a method declared in A; B does not override. Calling through
    # A* / B* / C* views of a C object must all reach C's override.
    src = (
        "class A { int a; int test(int d) { return a + d; } } "
        "class B extends A { } "
        "class C extends B { int test(int d) { return a * d; } } "
        "public class Main { public static void main(String[] args) { "
        "  C c = new C(); c.a = 10; "
        "  A viewA = c; B viewB = c; "
        "  System.out.println(viewA.test(5)); "   # 50 via A*
        "  System.out.println(viewB.test(5)); "   # 50 via B*
        "  System.out.println(c.test(5)); } }"    # 50 via C*
    )
    assert run_program(src) == "50\n50\n50\n"


@requires_gcc
def test_inherited_method_operates_on_subclass_object():
    # A's method (not overridden) runs on a B object and sees B's inherited field.
    src = (
        "class A { int a; int doubleA() { return a + a; } } "
        "class B extends A { int b; } "
        "public class Main { public static void main(String[] args) { "
        "  B x = new B(); x.a = 21; System.out.println(x.doubleA()); } }"
    )
    assert run_program(src) == "42\n"


@requires_gcc
def test_equality_across_hierarchy_is_pointer_identity():
    src = (
        "class A {} class B extends A {} "
        "public class Main { public static void main(String[] args) { "
        "  B b = new B(); A a = b; System.out.println(a == b); "        # true
        "  A other = new A(); System.out.println(a == other); } }"      # false
    )
    assert run_program(src) == "true\nfalse\n"


@requires_gcc
def test_extends_forward_declared_class():
    src = (
        "class B extends A {} "
        "class A { int who() { return 7; } } "
        "public class Main { public static void main(String[] args) { "
        "  B b = new B(); System.out.println(b.who()); } }"
    )
    assert run_program(src) == "7\n"
