"""Tests for the semantic analyzer (Phase 4)."""

from src.parser import parse
from src.semantic.analyzer import analyze


VALID_MAIN = "public class Main { public static void main(String[] args) {} }"


def errors_of(src):
    return analyze(parse(src))


def texts(errors):
    return " || ".join(e.message for e in errors)


def in_method(body, members="", classes=""):
    """Wrap a statement body inside an instance method A.test(), plus a valid Main."""
    src = (
        "class A { " + members + " void test() { " + body + " } } "
        + classes + " " + VALID_MAIN
    )
    return errors_of(src)


# ------------------------------------------------------------------ valid program

def test_valid_program_has_no_errors():
    assert in_method("int x = 1 + 2 * 3; System.out.println(x);") == []


# ------------------------------------------------------------------ variables / scope

def test_undefined_variable():
    errs = in_method("System.out.println(x);")
    assert "'x' is not defined" in texts(errs)


def test_shadowing_is_allowed():
    body = (
        "int i = 100;"
        "{ boolean i = true; System.out.println(i); }"
        "System.out.println(i);"
    )
    assert in_method(body) == []


def test_use_before_declaration_in_initializer():
    # `int x = x;` -- the right-hand x is not yet in scope.
    errs = in_method("int x = x;")
    assert "'x' is not defined" in texts(errs)


def test_same_scope_redeclaration():
    errs = in_method("int x = 1; int x = 2;")
    assert "already defined in this scope" in texts(errs)


# ------------------------------------------------------------------ type checking

def test_assign_boolean_to_int_errors():
    assert "cannot assign boolean to int" in texts(in_method("int i = true;"))


def test_arithmetic_requires_int():
    assert "expects int operands" in texts(in_method("int x = true + 1;"))


def test_comparison_yields_boolean_and_requires_int():
    assert in_method("boolean b = 1 < 2;") == []
    assert "expects int operands" in texts(in_method("boolean b = true < false;"))


def test_boolean_ops_require_boolean():
    assert in_method("boolean b = true && false;") == []
    assert "expects boolean operands" in texts(in_method("boolean b = 1 && 2;"))


def test_unary_ops():
    assert in_method("boolean b = !false; int x = -5;") == []
    assert "'!' expects a boolean" in texts(in_method("boolean b = !5;"))
    assert "unary '-' expects an int" in texts(in_method("int x = -true;"))


def test_equality_rules():
    assert in_method("boolean b = 1 == 2;") == []
    assert in_method("boolean b = true != false;") == []
    assert "cannot compare" in texts(in_method("boolean b = 1 == true;"))


def test_equality_between_related_objects_ok():
    classes = "class P {} class Q extends P {}"
    body = "P p = new P(); Q q = new Q(); boolean b = p == q;"
    assert in_method(body, classes=classes) == []


# ------------------------------------------------------------------ assignment compatibility

def test_upcast_assignment_allowed():
    classes = "class P {} class Q extends P {}"
    assert in_method("P p = new Q();", classes=classes) == []


def test_downcast_assignment_rejected():
    classes = "class P {} class Q extends P {}"
    assert "cannot assign P to Q" in texts(in_method("Q q = new P();", classes=classes))


# ------------------------------------------------------------------ method calls

def test_method_argument_count():
    errs = in_method("needsOne(1, 2);", members="void needsOne(int a) {}")
    assert "expects 1 argument(s) but got 2" in texts(errs)


def test_method_argument_type():
    errs = in_method("needsInt(true);", members="void needsInt(int a) {}")
    assert "expects int but got boolean" in texts(errs)


def test_method_call_ok():
    assert in_method("needsInt(5);", members="void needsInt(int a) {}") == []


def test_unknown_method():
    assert "is not defined" in texts(in_method("ghost();"))


def test_method_call_on_receiver_and_inherited():
    classes = "class P { int m(int a) { return a; } } class Q extends P {}"
    body = "Q q = new Q(); int r = q.m(5);"   # m inherited from P
    assert in_method(body, classes=classes) == []


# ------------------------------------------------------------------ this

def test_this_in_instance_method_ok():
    src = "class A { int i; void test() { this.i = 5; } } " + VALID_MAIN
    assert errors_of(src) == []


def test_this_in_static_method_errors():
    src = "class A { static void s() { A a = this; } } " + VALID_MAIN
    assert "'this' cannot be used in a static method" in texts(errors_of(src))


def test_instance_field_from_static_errors():
    src = "class A { int f; static void s() { int x = f; } } " + VALID_MAIN
    assert "cannot access instance field 'f' from a static method" in texts(errors_of(src))


# ------------------------------------------------------------------ break / continue

def test_break_continue_inside_loop_ok():
    assert in_method("while (true) { break; } while (true) { continue; }") == []


def test_break_outside_loop_errors():
    assert "'break' used outside of a loop" in texts(in_method("break;"))


def test_continue_outside_loop_errors():
    assert "'continue' used outside of a loop" in texts(in_method("continue;"))


# ------------------------------------------------------------------ return

def test_void_method_returning_value_errors():
    src = "class A { void m() { return 5; } } " + VALID_MAIN
    assert "void method cannot return a value" in texts(errors_of(src))


def test_return_type_mismatch_errors():
    src = "class A { int m() { return true; } } " + VALID_MAIN
    assert "cannot return boolean" in texts(errors_of(src))


def test_return_ok():
    src = "class A { int m() { return 5; } } " + VALID_MAIN
    assert errors_of(src) == []


# ------------------------------------------------------------------ println

def test_println_int_and_boolean_ok():
    assert in_method("System.out.println(5); System.out.println(true);") == []


def test_println_object_errors():
    classes = "class P {}"
    errs = in_method("P p = new P(); System.out.println(p);", classes=classes)
    assert "println expects an int or boolean" in texts(errs)


# ------------------------------------------------------------------ if / while conditions

def test_if_condition_must_be_boolean():
    assert "'if' condition must be boolean" in texts(in_method("if (5) { }"))


def test_while_condition_must_be_boolean():
    assert "'while' condition must be boolean" in texts(in_method("while (5) { }"))


# ------------------------------------------------------------------ entry point

def test_no_main_errors():
    assert "no entry point" in texts(errors_of("class A {}"))


def test_exactly_one_main_ok():
    assert errors_of(VALID_MAIN) == []


def test_two_mains_errors():
    src = (
        "public class Main { public static void main(String[] args) {} } "
        "class B { public static void main(String[] args) {} }"
    )
    assert "more than one 'main'" in texts(errors_of(src))


def test_entry_class_with_field_errors():
    src = "public class Main { int x; public static void main(String[] args) {} }"
    assert "must not declare fields" in texts(errors_of(src))


def test_entry_class_with_extra_method_errors():
    src = (
        "public class Main { public static void main(String[] args) {} "
        "void other() {} }"
    )
    assert "must contain only 'main'" in texts(errors_of(src))


# ------------------------------------------------------------------ forward references

def test_forward_reference_method_and_class():
    src = (
        "class B { int foo(int n) { return bar(n); } int bar(int m) { return m; } "
        "A make() { A a = new A(); return a; } } "
        "class A {} " + VALID_MAIN
    )
    assert errors_of(src) == []


# ------------------------------------------------------------------ structural (from class table)

def test_duplicate_class_reported():
    assert "already defined" in texts(errors_of("class A {} class A {} " + VALID_MAIN))


def test_cyclic_inheritance_reported():
    src = "class A extends B {} class B extends A {} " + VALID_MAIN
    assert "cyclic" in texts(errors_of(src))
