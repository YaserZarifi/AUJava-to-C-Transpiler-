"""The AUJava type system.

AUJava has only two primitive types (`int`, `boolean`), plus `void` for methods
that return nothing, and *class types* (one per declared class). `String[]` is a
special marker used only by the `main(String[] args)` signature; `args` is never
actually used in a program, so this type never participates in real checks.
"""


class Type:
    """Base class for all AUJava types."""


class PrimitiveType(Type):
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, PrimitiveType) and other.name == self.name

    def __hash__(self):
        return hash(("prim", self.name))

    def __repr__(self):
        return self.name


class ClassType(Type):
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, ClassType) and other.name == self.name

    def __hash__(self):
        return hash(("class", self.name))

    def __repr__(self):
        return self.name


class SpecialType(Type):
    """A type that exists only structurally (e.g. String[] for main's args)."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, SpecialType) and other.name == self.name

    def __hash__(self):
        return hash(("special", self.name))

    def __repr__(self):
        return self.name


# Singletons for the fixed types.
INT = PrimitiveType("int")
BOOLEAN = PrimitiveType("boolean")
VOID = PrimitiveType("void")
STRING_ARRAY = SpecialType("String[]")


def is_class_type(t):
    return isinstance(t, ClassType)
