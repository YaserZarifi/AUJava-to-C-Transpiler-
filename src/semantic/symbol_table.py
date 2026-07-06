"""Symbol tables for AUJava semantic analysis.

Two cooperating structures:

* `ClassTable` -- the program-wide table of classes, built in the FIRST pass so
  that forward references (a class using another class defined later) work. It
  detects duplicate class names, unknown/undefined types, unknown superclasses,
  and cyclic inheritance, and provides inheritance-aware field/method lookup.

* `ScopeStack` -- a stack of block scopes used in the SECOND pass to track local
  variables, with innermost-first lookup so that shadowing resolves correctly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.errors import SemanticError
from src.semantic.types import (
    BOOLEAN, INT, STRING_ARRAY, VOID, ClassType, Type,
)


# --------------------------------------------------------------------------
# Descriptors
# --------------------------------------------------------------------------

@dataclass
class FieldInfo:
    name: str
    type: Type
    is_static: bool
    owner: str            # class that declares this field
    line: int
    col: int


@dataclass
class MethodInfo:
    name: str
    return_type: Type
    param_types: List[Type]
    param_names: List[str]
    is_static: bool
    is_public: bool
    owner: str            # class that declares this method
    node: object          # the ast.Method (for later body analysis / codegen)
    line: int
    col: int


@dataclass
class ClassInfo:
    name: str
    superclass: Optional[str]
    fields: Dict[str, FieldInfo] = field(default_factory=dict)
    methods: Dict[str, MethodInfo] = field(default_factory=dict)
    is_public: bool = False
    node: object = None
    line: int = 0
    col: int = 0


@dataclass
class VarInfo:
    name: str
    type: Type
    line: int
    col: int
    c_name: str = ""      # unique C name, assigned during code generation


# --------------------------------------------------------------------------
# Class table (first pass)
# --------------------------------------------------------------------------

class ClassTable:
    def __init__(self):
        self.classes: Dict[str, ClassInfo] = {}

    @classmethod
    def build(cls, program):
        self = cls()
        # (1) collect class names, detecting duplicates.
        for c in program.classes:
            if c.name in self.classes:
                raise SemanticError(
                    f"class {c.name} is already defined", c.line, c.col
                )
            self.classes[c.name] = None  # placeholder; filled in below
        known = set(self.classes.keys())

        # (2) build each ClassInfo, resolving field/method types now that every
        #     class name is known (so forward references resolve).
        for c in program.classes:
            self.classes[c.name] = self._build_class_info(c, known)

        # (3) validate the inheritance graph: known parents, no cycles.
        self._check_inheritance()
        return self

    def _resolve_type(self, typeref, known):
        n = typeref.name
        if n == "int":
            return INT
        if n == "boolean":
            return BOOLEAN
        if n == "void":
            return VOID
        if n in known:
            return ClassType(n)
        raise SemanticError(f"unknown type '{n}'", typeref.line, typeref.col)

    def _build_class_info(self, c, known):
        fields: Dict[str, FieldInfo] = {}
        for f in c.fields:
            if f.name in fields:
                raise SemanticError(
                    f"field '{f.name}' is already defined in class {c.name}",
                    f.line, f.col,
                )
            ftype = self._resolve_type(f.type, known)
            if ftype == VOID:
                raise SemanticError("a field cannot have type 'void'", f.line, f.col)
            fields[f.name] = FieldInfo(f.name, ftype, f.is_static, c.name, f.line, f.col)

        methods: Dict[str, MethodInfo] = {}
        for m in c.methods:
            if m.name in methods:
                raise SemanticError(
                    f"method '{m.name}' is already defined in class {c.name}",
                    m.line, m.col,
                )
            rtype = self._resolve_type(m.return_type, known)
            ptypes = []
            for p in m.params:
                if p.is_array:
                    ptypes.append(STRING_ARRAY)   # only main's `String[] args`
                else:
                    ptypes.append(self._resolve_type(p.type, known))
            pnames = [p.name for p in m.params]
            methods[m.name] = MethodInfo(
                m.name, rtype, ptypes, pnames, m.is_static, m.is_public,
                c.name, m, m.line, m.col,
            )

        return ClassInfo(
            c.name, c.superclass, fields, methods, c.is_public, c, c.line, c.col
        )

    def _check_inheritance(self):
        # every named superclass must exist
        for ci in self.classes.values():
            if ci.superclass is not None and ci.superclass not in self.classes:
                raise SemanticError(
                    f"class {ci.name} extends unknown class {ci.superclass}",
                    ci.line, ci.col,
                )

        # cycle detection via DFS three-coloring (white/gray/black)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in self.classes}

        def dfs(name):
            color[name] = GRAY
            parent = self.classes[name].superclass
            if parent is not None:
                if color[parent] == GRAY:
                    ci = self.classes[name]
                    raise SemanticError(
                        f"cyclic inheritance detected involving class {name}",
                        ci.line, ci.col,
                    )
                if color[parent] == WHITE:
                    dfs(parent)
            color[name] = BLACK

        for name in self.classes:
            if color[name] == WHITE:
                dfs(name)

    # --- lookups (inheritance-aware) ---

    def get(self, name) -> Optional[ClassInfo]:
        return self.classes.get(name)

    def exists(self, name) -> bool:
        return name in self.classes

    def lookup_field(self, class_name, field_name) -> Optional[FieldInfo]:
        ci = self.classes.get(class_name)
        while ci is not None:
            if field_name in ci.fields:
                return ci.fields[field_name]
            ci = self.classes.get(ci.superclass) if ci.superclass else None
        return None

    def lookup_method(self, class_name, method_name) -> Optional[MethodInfo]:
        ci = self.classes.get(class_name)
        while ci is not None:
            if method_name in ci.methods:
                return ci.methods[method_name]
            ci = self.classes.get(ci.superclass) if ci.superclass else None
        return None

    def is_subclass(self, a, b) -> bool:
        """True if class `a` is `b` or a (transitive) subclass of `b`."""
        name = a
        while name is not None:
            if name == b:
                return True
            ci = self.classes.get(name)
            name = ci.superclass if ci else None
        return False

    def is_assignable(self, target: Type, value: Type) -> bool:
        """Can a value of type `value` be assigned to a slot of type `target`?"""
        if target == value:
            return True
        if isinstance(target, ClassType) and isinstance(value, ClassType):
            # a subclass instance may be stored in a parent-typed slot (upcast)
            return self.is_subclass(value.name, target.name)
        return False


# --------------------------------------------------------------------------
# Scope stack (second pass, per method)
# --------------------------------------------------------------------------

class ScopeStack:
    def __init__(self):
        self.scopes: List[Dict[str, VarInfo]] = []

    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    @property
    def depth(self):
        return len(self.scopes)

    def define(self, name, type, line, col) -> VarInfo:
        # Redeclaring a name in the SAME scope is an error; shadowing an outer
        # scope is allowed.
        if name in self.scopes[-1]:
            raise SemanticError(
                f"variable '{name}' is already defined in this scope", line, col
            )
        info = VarInfo(name, type, line, col)
        self.scopes[-1][name] = info
        return info

    def lookup(self, name) -> Optional[VarInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None
