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

def flatten_expr(expr, out, namer):
    """Flatten `expr` into TAC, appending instructions to `out`.

    Returns the Operand holding the expression's result. Every literal and every
    operation produces its own temporary, matching the spec's TAC example.
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
        operand = flatten_expr(expr.operand, out, namer)
        t = namer.new_temp()
        out.append(UnOp(t, expr.op, operand))
        return t

    if isinstance(expr, ast.BinaryOp):
        left = flatten_expr(expr.left, out, namer)
        right = flatten_expr(expr.right, out, namer)
        t = namer.new_temp()
        out.append(BinOp(t, expr.op, left, right))
        return t

    raise NotImplementedError(
        f"flatten_expr does not yet handle {type(expr).__name__} "
        "(added in the code-generator phases)"
    )
