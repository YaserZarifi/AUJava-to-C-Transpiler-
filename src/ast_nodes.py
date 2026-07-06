"""Abstract Syntax Tree (AST) node definitions.

The parser builds a tree out of these nodes. Each node records the source
position (`line`, `col`) of where it starts, so later stages can report precise
errors. Nodes are grouped under three marker base classes -- `Node`,
`Statement`, and `Expression` -- which make `isinstance(...)` checks in the
semantic analyzer and code generator convenient.
"""

from dataclasses import dataclass, field
from typing import List, Optional


class Node:
    """Base marker class for every AST node."""


class Statement(Node):
    """Base marker class for statements."""


class Expression(Node):
    """Base marker class for expressions."""


# --------------------------------------------------------------------------
# Types & top-level declarations
# --------------------------------------------------------------------------

@dataclass
class TypeRef(Node):
    name: str                 # 'int' | 'boolean' | 'void' | a class name
    line: int = 0
    col: int = 0


@dataclass
class Param(Node):
    name: str
    type: TypeRef
    is_array: bool = False    # true only for `String[] args`
    line: int = 0
    col: int = 0


@dataclass
class Field(Node):
    name: str
    type: TypeRef
    is_static: bool = False
    init: Optional[Expression] = None
    line: int = 0
    col: int = 0


@dataclass
class Method(Node):
    name: str
    return_type: TypeRef      # TypeRef('void') for void methods
    params: List[Param]
    body: "Block"
    is_static: bool = False
    is_public: bool = False
    line: int = 0
    col: int = 0


@dataclass
class ClassDecl(Node):
    name: str
    superclass: Optional[str]        # name of parent class, or None
    fields: List[Field] = field(default_factory=list)
    methods: List[Method] = field(default_factory=list)
    is_public: bool = False
    line: int = 0
    col: int = 0


@dataclass
class Program(Node):
    classes: List[ClassDecl] = field(default_factory=list)
    line: int = 0
    col: int = 0


# --------------------------------------------------------------------------
# Statements
# --------------------------------------------------------------------------

@dataclass
class Block(Statement):
    statements: List[Statement] = field(default_factory=list)
    line: int = 0
    col: int = 0


@dataclass
class If(Statement):
    condition: Expression = None
    then_branch: Statement = None
    else_branch: Optional[Statement] = None
    line: int = 0
    col: int = 0


@dataclass
class While(Statement):
    condition: Expression = None
    body: Statement = None
    line: int = 0
    col: int = 0


@dataclass
class Break(Statement):
    line: int = 0
    col: int = 0


@dataclass
class Continue(Statement):
    line: int = 0
    col: int = 0


@dataclass
class Return(Statement):
    value: Optional[Expression] = None
    line: int = 0
    col: int = 0


@dataclass
class Println(Statement):
    arg: Expression = None
    line: int = 0
    col: int = 0


@dataclass
class VarDecl(Statement):
    name: str = ""
    type: TypeRef = None
    init: Optional[Expression] = None
    line: int = 0
    col: int = 0


@dataclass
class ExprStmt(Statement):
    expr: Expression = None
    line: int = 0
    col: int = 0


# --------------------------------------------------------------------------
# Expressions
# --------------------------------------------------------------------------

@dataclass
class IntLiteral(Expression):
    value: int = 0
    line: int = 0
    col: int = 0


@dataclass
class BoolLiteral(Expression):
    value: bool = False
    line: int = 0
    col: int = 0


@dataclass
class This(Expression):
    line: int = 0
    col: int = 0


@dataclass
class Identifier(Expression):
    name: str = ""
    line: int = 0
    col: int = 0


@dataclass
class NewObject(Expression):
    class_name: str = ""
    line: int = 0
    col: int = 0


@dataclass
class FieldAccess(Expression):
    receiver: Expression = None
    name: str = ""
    line: int = 0
    col: int = 0


@dataclass
class MethodCall(Expression):
    receiver: Optional[Expression]   # None => implicit `this` (bare call)
    name: str = ""
    args: List[Expression] = field(default_factory=list)
    line: int = 0
    col: int = 0


@dataclass
class UnaryOp(Expression):
    op: str = ""                      # '!' or '-'
    operand: Expression = None
    line: int = 0
    col: int = 0


@dataclass
class BinaryOp(Expression):
    op: str = ""                      # '+', '-', '*', '/', '%', '==', ... '&&', '||'
    left: Expression = None
    right: Expression = None
    line: int = 0
    col: int = 0


@dataclass
class Assignment(Expression):
    target: Expression = None         # Identifier or FieldAccess (checked in semantics)
    value: Expression = None
    line: int = 0
    col: int = 0
