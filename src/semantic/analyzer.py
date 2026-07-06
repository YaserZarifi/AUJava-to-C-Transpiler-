"""Semantic analyzer for AUJava (Phase 4).

Walks the AST (the "second pass") and enforces the language's static-semantic
rules, reporting `SemanticError`s with precise line/column info. It also
annotates AST nodes with resolved type/binding information that the code
generator reuses later:

    expr.resolved_type          the semantic Type of every expression
    Identifier.binding          ("local", VarInfo) or ("field", FieldInfo)
    FieldAccess.field_info       the resolved FieldInfo (+ .receiver_type)
    MethodCall.method_info       the resolved MethodInfo (+ .receiver_type)
    VarDecl.var_info             the VarInfo created for the declaration
    Println.arg_type             INT or BOOLEAN

Errors are accumulated (not raised on the first one) so the compiler can report
all problems it finds; `analyze` returns the list of errors (empty == valid).

Design decision (documented in docs/report.md): `println` accepts BOTH `int`
and `boolean` arguments (per the language intro).
"""

from src import ast_nodes as ast
from src.errors import SemanticError
from src.semantic.symbol_table import ClassTable, ScopeStack
from src.semantic.types import BOOLEAN, INT, VOID, ClassType


ARITH_OPS = {"+", "-", "*", "/", "%"}
REL_OPS = {"<", ">", "<=", ">="}
EQ_OPS = {"==", "!="}
BOOL_OPS = {"&&", "||"}


class Analyzer:
    def __init__(self):
        self.errors = []
        self.ct = None
        self.current_class = None
        self.current_method = None
        self.scopes = None
        self.loop_depth = 0

    # --- entry point ---

    def analyze(self, program):
        self.errors = []
        try:
            self.ct = ClassTable.build(program)
        except SemanticError as e:
            # Structural errors (dup class, unknown type/superclass, cycles) are
            # fatal -- without a class table we cannot analyze bodies.
            self.errors.append(e)
            return self.errors

        self._check_entry_point(program)
        for c in program.classes:
            self._analyze_class(c)
        return self.errors

    def _record(self, fn, *args):
        try:
            fn(*args)
        except SemanticError as e:
            self.errors.append(e)

    # --- entry-point rule: exactly one `public static void main(String[] args)` ---

    @staticmethod
    def _is_main(m):
        return (
            m.name == "main"
            and m.is_static
            and m.is_public
            and m.return_type.name == "void"
            and len(m.params) == 1
            and m.params[0].is_array
        )

    def _check_entry_point(self, program):
        mains = [
            (c, m) for c in program.classes for m in c.methods if self._is_main(m)
        ]
        if not mains:
            self.errors.append(SemanticError(
                "program has no entry point "
                "(expected exactly one 'public static void main(String[] args)')",
                1, 1,
            ))
            return
        if len(mains) > 1:
            _, m = mains[1]
            self.errors.append(SemanticError(
                "program has more than one 'main' entry point", m.line, m.col
            ))
        entry_class, _ = mains[0]
        # The entry class must contain only `main` -- no fields, no other methods.
        for f in entry_class.fields:
            self.errors.append(SemanticError(
                f"the entry class '{entry_class.name}' must not declare fields",
                f.line, f.col,
            ))
        for m in entry_class.methods:
            if not self._is_main(m):
                self.errors.append(SemanticError(
                    f"the entry class '{entry_class.name}' must contain only 'main'",
                    m.line, m.col,
                ))

    # --- class / method traversal ---

    def _analyze_class(self, c):
        ci = self.ct.get(c.name)
        for method_node in c.methods:
            self._analyze_method(ci, method_node)

    def _analyze_method(self, ci, method_node):
        self.current_class = ci
        self.current_method = ci.methods[method_node.name]
        self.loop_depth = 0
        self.scopes = ScopeStack()
        self.scopes.push()   # method-level scope holds the parameters
        mi = self.current_method
        param_infos = []
        for pname, ptype in zip(mi.param_names, mi.param_types):
            try:
                param_infos.append(
                    self.scopes.define(pname, ptype, method_node.line, method_node.col)
                )
            except SemanticError as e:
                self.errors.append(e)
                param_infos.append(None)
        # Expose the parameters' VarInfo objects so the code generator can assign
        # them unique C names (identifiers referencing a param share these objects).
        method_node.param_infos = param_infos
        self._record(self._stmt, method_node.body)
        self.scopes.pop()

    # --- statements ---

    def _stmt(self, s):
        if isinstance(s, ast.Block):
            self.scopes.push()
            for st in s.statements:
                self._record(self._stmt, st)
            self.scopes.pop()
        elif isinstance(s, ast.VarDecl):
            self._stmt_vardecl(s)
        elif isinstance(s, ast.If):
            self._stmt_if(s)
        elif isinstance(s, ast.While):
            self._stmt_while(s)
        elif isinstance(s, ast.Break):
            if self.loop_depth == 0:
                raise SemanticError("'break' used outside of a loop", s.line, s.col)
        elif isinstance(s, ast.Continue):
            if self.loop_depth == 0:
                raise SemanticError("'continue' used outside of a loop", s.line, s.col)
        elif isinstance(s, ast.Return):
            self._stmt_return(s)
        elif isinstance(s, ast.Println):
            self._stmt_println(s)
        elif isinstance(s, ast.ExprStmt):
            self._expr(s.expr)
        else:
            raise SemanticError(f"unsupported statement {type(s).__name__}", s.line, s.col)

    def _stmt_vardecl(self, s):
        vtype = self.ct.resolve_type(s.type)
        if vtype == VOID:
            raise SemanticError("a variable cannot have type 'void'", s.line, s.col)
        # Analyze the initializer BEFORE defining the name, so `int x = x;` sees
        # no in-scope `x` (declaration-before-use for locals).
        if s.init is not None:
            itype = self._expr(s.init)
            if not self.ct.is_assignable(vtype, itype):
                raise SemanticError(
                    f"cannot assign {itype} to {vtype}", s.init.line, s.init.col
                )
        s.var_info = self.scopes.define(s.name, vtype, s.line, s.col)

    def _stmt_if(self, s):
        ctype = self._expr(s.condition)
        if ctype != BOOLEAN:
            self.errors.append(SemanticError(
                "'if' condition must be boolean", s.condition.line, s.condition.col
            ))
        self._record(self._stmt, s.then_branch)
        if s.else_branch is not None:
            self._record(self._stmt, s.else_branch)

    def _stmt_while(self, s):
        ctype = self._expr(s.condition)
        if ctype != BOOLEAN:
            self.errors.append(SemanticError(
                "'while' condition must be boolean", s.condition.line, s.condition.col
            ))
        self.loop_depth += 1
        self._record(self._stmt, s.body)
        self.loop_depth -= 1

    def _stmt_return(self, s):
        rt = self.current_method.return_type
        if s.value is None:
            if rt != VOID:
                raise SemanticError(
                    f"missing return value; method returns {rt}", s.line, s.col
                )
            return
        vtype = self._expr(s.value)
        if rt == VOID:
            raise SemanticError("a void method cannot return a value", s.line, s.col)
        if not self.ct.is_assignable(rt, vtype):
            raise SemanticError(
                f"cannot return {vtype} from a method declared to return {rt}",
                s.value.line, s.value.col,
            )

    def _stmt_println(self, s):
        atype = self._expr(s.arg)
        if atype not in (INT, BOOLEAN):
            raise SemanticError(
                f"println expects an int or boolean argument but got {atype}",
                s.arg.line, s.arg.col,
            )
        s.arg_type = atype

    # --- expressions (returns a Type, annotates node.resolved_type) ---

    def _expr(self, e):
        t = self._expr_type(e)
        e.resolved_type = t
        return t

    def _expr_type(self, e):
        if isinstance(e, ast.IntLiteral):
            return INT
        if isinstance(e, ast.BoolLiteral):
            return BOOLEAN
        if isinstance(e, ast.This):
            return self._expr_this(e)
        if isinstance(e, ast.Identifier):
            return self._expr_identifier(e)
        if isinstance(e, ast.NewObject):
            return self._expr_new(e)
        if isinstance(e, ast.FieldAccess):
            return self._expr_field(e)
        if isinstance(e, ast.MethodCall):
            return self._expr_call(e)
        if isinstance(e, ast.UnaryOp):
            return self._expr_unary(e)
        if isinstance(e, ast.BinaryOp):
            return self._expr_binary(e)
        if isinstance(e, ast.Assignment):
            return self._expr_assignment(e)
        raise SemanticError(f"unsupported expression {type(e).__name__}", e.line, e.col)

    def _expr_this(self, e):
        if self.current_method.is_static:
            raise SemanticError("'this' cannot be used in a static method", e.line, e.col)
        return ClassType(self.current_class.name)

    def _is_class_ref(self, ident):
        """True if a bare identifier names a class (not shadowed by a var/field)."""
        name = ident.name
        if self.scopes.lookup(name) is not None:
            return False
        if self.ct.lookup_field(self.current_class.name, name) is not None:
            return False
        return self.ct.exists(name)

    def _expr_identifier(self, e):
        info = self.scopes.lookup(e.name)
        if info is not None:
            e.binding = ("local", info)
            return info.type
        fi = self.ct.lookup_field(self.current_class.name, e.name)
        if fi is not None:
            if fi.is_static:
                e.binding = ("static_field", fi)
                return fi.type
            if self.current_method.is_static:
                raise SemanticError(
                    f"cannot access instance field '{e.name}' from a static method",
                    e.line, e.col,
                )
            e.binding = ("field", fi)
            return fi.type
        raise SemanticError(f"'{e.name}' is not defined", e.line, e.col)

    def _expr_new(self, e):
        if not self.ct.exists(e.class_name):
            raise SemanticError(f"unknown class '{e.class_name}'", e.line, e.col)
        return ClassType(e.class_name)

    def _expr_field(self, e):
        # static field access: ClassName.field
        if isinstance(e.receiver, ast.Identifier) and self._is_class_ref(e.receiver):
            cname = e.receiver.name
            fi = self.ct.lookup_field(cname, e.name)
            if fi is None or not fi.is_static:
                raise SemanticError(
                    f"class {cname} has no static field '{e.name}'", e.line, e.col
                )
            e.field_info = fi
            e.receiver_type = ClassType(cname)
            return fi.type

        rtype = self._expr(e.receiver)
        if not isinstance(rtype, ClassType):
            raise SemanticError(f"type {rtype} has no fields", e.line, e.col)
        fi = self.ct.lookup_field(rtype.name, e.name)
        if fi is None:
            raise SemanticError(
                f"class {rtype.name} has no field '{e.name}'", e.line, e.col
            )
        if fi.is_static:
            raise SemanticError(
                f"static field '{e.name}' must be accessed via the class name",
                e.line, e.col,
            )
        e.field_info = fi
        e.receiver_type = rtype
        return fi.type

    def _check_args(self, e, mi):
        if len(e.args) != len(mi.param_types):
            raise SemanticError(
                f"method '{e.name}' expects {len(mi.param_types)} argument(s) "
                f"but got {len(e.args)}",
                e.line, e.col,
            )
        for i, (arg, pt) in enumerate(zip(e.args, mi.param_types), start=1):
            at = self._expr(arg)
            if not self.ct.is_assignable(pt, at):
                raise SemanticError(
                    f"argument {i} of '{e.name}' expects {pt} but got {at}",
                    arg.line, arg.col,
                )

    def _expr_call(self, e):
        # static method call: ClassName.method(args)
        if (
            e.receiver is not None
            and isinstance(e.receiver, ast.Identifier)
            and self._is_class_ref(e.receiver)
        ):
            cname = e.receiver.name
            mi = self.ct.lookup_method(cname, e.name)
            if mi is None or not mi.is_static:
                raise SemanticError(
                    f"class {cname} has no static method '{e.name}'", e.line, e.col
                )
            self._check_args(e, mi)
            e.method_info = mi
            e.receiver_type = ClassType(cname)
            return mi.return_type

        if e.receiver is None:
            # bare call => implicit `this`, or a static method of the current class
            mi = self.ct.lookup_method(self.current_class.name, e.name)
            if mi is None:
                raise SemanticError(f"method '{e.name}' is not defined", e.line, e.col)
            if not mi.is_static and self.current_method.is_static:
                raise SemanticError(
                    f"cannot call instance method '{e.name}' from a static method",
                    e.line, e.col,
                )
            recv_type = ClassType(self.current_class.name)
        else:
            recv_type = self._expr(e.receiver)
            if not isinstance(recv_type, ClassType):
                raise SemanticError(f"type {recv_type} has no methods", e.line, e.col)
            mi = self.ct.lookup_method(recv_type.name, e.name)
            if mi is None:
                raise SemanticError(
                    f"class {recv_type.name} has no method '{e.name}'", e.line, e.col
                )
            if mi.is_static:
                raise SemanticError(
                    f"static method '{e.name}' must be called via the class name",
                    e.line, e.col,
                )

        self._check_args(e, mi)
        e.method_info = mi
        e.receiver_type = recv_type
        return mi.return_type

    def _expr_unary(self, e):
        ot = self._expr(e.operand)
        if e.op == "!":
            if ot != BOOLEAN:
                raise SemanticError("operator '!' expects a boolean", e.line, e.col)
            return BOOLEAN
        # '-'
        if ot != INT:
            raise SemanticError("unary '-' expects an int", e.line, e.col)
        return INT

    def _expr_binary(self, e):
        lt = self._expr(e.left)
        rt = self._expr(e.right)
        op = e.op
        if op in ARITH_OPS:
            if lt != INT or rt != INT:
                raise SemanticError(f"operator '{op}' expects int operands", e.line, e.col)
            return INT
        if op in REL_OPS:
            if lt != INT or rt != INT:
                raise SemanticError(f"operator '{op}' expects int operands", e.line, e.col)
            return BOOLEAN
        if op in BOOL_OPS:
            if lt != BOOLEAN or rt != BOOLEAN:
                raise SemanticError(
                    f"operator '{op}' expects boolean operands", e.line, e.col
                )
            return BOOLEAN
        if op in EQ_OPS:
            if (lt == INT and rt == INT) or (lt == BOOLEAN and rt == BOOLEAN):
                return BOOLEAN
            if isinstance(lt, ClassType) and isinstance(rt, ClassType):
                if self.ct.is_subclass(lt.name, rt.name) or self.ct.is_subclass(rt.name, lt.name):
                    return BOOLEAN
            raise SemanticError(
                f"operator '{op}' cannot compare {lt} and {rt}", e.line, e.col
            )
        raise SemanticError(f"unknown operator '{op}'", e.line, e.col)

    def _expr_assignment(self, e):
        if not isinstance(e.target, (ast.Identifier, ast.FieldAccess)):
            raise SemanticError("invalid assignment target", e.line, e.col)
        ttype = self._expr(e.target)
        vtype = self._expr(e.value)
        if not self.ct.is_assignable(ttype, vtype):
            raise SemanticError(f"cannot assign {vtype} to {ttype}", e.line, e.col)
        return ttype


def analyze(program):
    """Analyze a Program AST; return a list of SemanticError (empty == valid)."""
    return Analyzer().analyze(program)
