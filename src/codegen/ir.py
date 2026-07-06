"""Three-Address Code (TAC) intermediate representation.

Method bodies are lowered into a flat list of tiny `Instr` objects before being
emitted as C. Expressions are flattened post-order so that every operation reads
already-computed operands, exactly as the spec illustrates:

    int x = 1 + 2 * 3;   ==>   _t_1 = 1
                               _t_2 = 2
                               _t_3 = 3
                               _t_4 = _t_2 * _t_3
                               _t_5 = _t_1 + _t_4
                               x    = _t_5

`Namer` hands out globally-unique temporaries (`_t_N`) and labels so that names
never collide within the generated C file.

This module implements the expression-flattening core (literals, unary and
binary operators). Statement lowering and object/field/call operands are layered
on top in the code-generator phases.
"""

from dataclasses import dataclass
from typing import Optional

from src import ast_nodes as ast


# --------------------------------------------------------------------------
# Operands -- the values that instructions read/write
# --------------------------------------------------------------------------

class Operand:
    pass


@dataclass(frozen=True)
class Const(Operand):
    value: int            # integers, or 0/1 for booleans

    @property
    def c(self):
        return str(self.value)


@dataclass(frozen=True)
class Temp(Operand):
    id: int

    @property
    def c(self):
        return f"_t_{self.id}"


@dataclass(frozen=True)
class Name(Operand):
    """A reference to a named C variable (its already-uniquified C name)."""
    c_name: str

    @property
    def c(self):
        return self.c_name


@dataclass(frozen=True)
class Raw(Operand):
    """Arbitrary C text used as a value, e.g. a field access `obj->field`."""
    text: str

    @property
    def c(self):
        return self.text


# --------------------------------------------------------------------------
# Instructions
# --------------------------------------------------------------------------

class Instr:
    pass


@dataclass
class Assign(Instr):
    dst: Operand
    src: Operand


@dataclass
class BinOp(Instr):
    dst: Temp
    op: str
    left: Operand
    right: Operand


@dataclass
class UnOp(Instr):
    dst: Temp
    op: str
    operand: Operand


@dataclass
class Label(Instr):
    name: str


@dataclass
class Goto(Instr):
    label: str


@dataclass
class IfFalse(Instr):
    """if (!cond) goto label"""
    cond: Operand
    label: str


@dataclass
class Print(Instr):
    value: Operand
    is_bool: bool


@dataclass
class Return(Instr):
    value: Optional[Operand]


@dataclass
class NewInstr(Instr):
    """dst = new_ClassName();  -- allocate & initialize an object."""
    dst: Operand
    class_name: str


@dataclass
class MethodCallInstr(Instr):
    """[dst =] receiver->method_c(receiver, args...);"""
    dst: Optional[Operand]        # None for a void call used as a statement
    receiver: Operand
    method_c: str                 # e.g. "function_test"
    args: list


# --------------------------------------------------------------------------
# Name/label allocation
# --------------------------------------------------------------------------

class Namer:
    """Hands out globally-unique temporary and label names."""

    def __init__(self):
        self._temp = 0
        self._label = 0

    def new_temp(self) -> Temp:
        self._temp += 1
        return Temp(self._temp)

    def new_label(self, base) -> str:
        self._label += 1
        return f"{base}_{self._label}"


# --------------------------------------------------------------------------
# Expression flattening
# --------------------------------------------------------------------------

def flatten_expr(expr, out, namer, ctx=None):
    """Flatten `expr` into TAC, appending instructions to `out`.

    Returns the Operand holding the expression's result. Every literal and every
    operation produces its own temporary, matching the spec's TAC example. `ctx`
    is an optional code-generation context used by later phases to lower object
    operands (fields, calls, `new`, `this`); the pure arithmetic core does not
    need it.
    """
    if isinstance(expr, ast.IntLiteral):
        t = namer.new_temp()
        out.append(Assign(t, Const(expr.value)))
        return t

    if isinstance(expr, ast.BoolLiteral):
        t = namer.new_temp()
        out.append(Assign(t, Const(1 if expr.value else 0)))
        return t

    if isinstance(expr, ast.UnaryOp):
        operand = flatten_expr(expr.operand, out, namer, ctx)
        t = namer.new_temp()
        out.append(UnOp(t, expr.op, operand))
        return t

    if isinstance(expr, ast.BinaryOp):
        left = flatten_expr(expr.left, out, namer, ctx)
        right = flatten_expr(expr.right, out, namer, ctx)
        t = namer.new_temp()
        out.append(BinOp(t, expr.op, left, right))
        return t

    if isinstance(expr, ast.Identifier):
        kind, info = expr.binding
        if kind == "local":
            return Name(info.c_name)
        if ctx is not None:
            return ctx.flatten_field_operand(expr, out)   # implicit-this field
        raise NotImplementedError("field identifier needs a codegen context")

    if isinstance(expr, ast.Assignment):
        value = flatten_expr(expr.value, out, namer, ctx)
        target = expr.target
        if isinstance(target, ast.Identifier) and target.binding[0] == "local":
            dst = Name(target.binding[1].c_name)
            out.append(Assign(dst, value))
            return dst
        if ctx is not None:
            return ctx.flatten_assign_target(target, value, out)
        raise NotImplementedError("non-local assignment needs a codegen context")

    if ctx is not None:
        return ctx.flatten_object_expr(expr, out)   # This/New/FieldAccess/MethodCall

    raise NotImplementedError(
        f"flatten_expr does not yet handle {type(expr).__name__} "
        "(added in the code-generator phases)"
    )
