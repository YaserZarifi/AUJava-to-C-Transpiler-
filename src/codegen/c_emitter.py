"""C code emitter.

Turns an analyzed AUJava AST into C source text. This phase (Phase 6) handles
the entry `main` method and the non-object features: local variables, arithmetic
and boolean expressions, `if`/`else` and `while` lowered to `goto`+labels,
`break`/`continue`, and `println`. Class/object support is layered on in Phase 7.

Key techniques (per the spec):
* every local and temporary is declared once, hoisted to the top of the C
  function, so `goto`s never jump over a declaration;
* variables that share a name across different AUJava scopes are given distinct,
  unique C names (`i__1`, `i__2`), which is what makes shadowing work in the flat
  goto-style function body.
"""

from src import ast_nodes as ast
from src.codegen import ir
from src.semantic.types import BOOLEAN


class CodeGenError(Exception):
    pass


def find_entry_main(program):
    for c in program.classes:
        for m in c.methods:
            if (
                m.name == "main"
                and m.is_static
                and m.return_type.name == "void"
                and len(m.params) == 1
                and m.params[0].is_array
            ):
                return c, m
    raise CodeGenError("program has no 'main' entry point")


class Emitter:
    def __init__(self):
        self.namer = ir.Namer()
        self._local_id = 0

    # --- public entry ---

    def generate(self, program):
        _, main = find_entry_main(program)
        instrs, decls = self._lower_body(main, is_main=True)
        return self._render_main(instrs, decls)

    # --- lowering: AST statements -> IR ---

    def _new_local(self, base):
        self._local_id += 1
        return f"{base}__{self._local_id}"

    def _lower_body(self, method, is_main):
        self.instrs = []
        self.decls = []            # list of (c_name, c_type)
        self.loop_stack = []       # list of (start_label, end_label)
        self.is_main = is_main
        self._lower_stmt(method.body)
        return self.instrs, self.decls

    def _emit(self, instr):
        self.instrs.append(instr)

    def _flatten(self, expr):
        return ir.flatten_expr(expr, self.instrs, self.namer, ctx=self)

    def _lower_stmt(self, s):
        if isinstance(s, ast.Block):
            for st in s.statements:
                self._lower_stmt(st)
        elif isinstance(s, ast.VarDecl):
            self._lower_vardecl(s)
        elif isinstance(s, ast.ExprStmt):
            self._flatten(s.expr)          # evaluated for side effects
        elif isinstance(s, ast.If):
            self._lower_if(s)
        elif isinstance(s, ast.While):
            self._lower_while(s)
        elif isinstance(s, ast.Break):
            self._emit(ir.Goto(self.loop_stack[-1][1]))
        elif isinstance(s, ast.Continue):
            self._emit(ir.Goto(self.loop_stack[-1][0]))
        elif isinstance(s, ast.Println):
            self._lower_println(s)
        elif isinstance(s, ast.Return):
            self._lower_return(s)
        else:
            raise CodeGenError(f"cannot lower statement {type(s).__name__}")

    def _lower_vardecl(self, s):
        c_name = self._new_local(s.name)
        s.var_info.c_name = c_name
        self.decls.append((c_name, "int"))    # int and boolean are both C int here
        if s.init is not None:
            value = self._flatten(s.init)
            self._emit(ir.Assign(ir.Name(c_name), value))

    def _lower_if(self, s):
        cond = self._flatten(s.condition)
        end = self.namer.new_label("if_end")
        if s.else_branch is not None:
            els = self.namer.new_label("if_else")
            self._emit(ir.IfFalse(cond, els))
            self._lower_stmt(s.then_branch)
            self._emit(ir.Goto(end))
            self._emit(ir.Label(els))
            self._lower_stmt(s.else_branch)
            self._emit(ir.Label(end))
        else:
            self._emit(ir.IfFalse(cond, end))
            self._lower_stmt(s.then_branch)
            self._emit(ir.Label(end))

    def _lower_while(self, s):
        start = self.namer.new_label("loop_start")
        end = self.namer.new_label("loop_end")
        self._emit(ir.Label(start))
        cond = self._flatten(s.condition)
        self._emit(ir.IfFalse(cond, end))
        self.loop_stack.append((start, end))
        self._lower_stmt(s.body)
        self.loop_stack.pop()
        self._emit(ir.Goto(start))
        self._emit(ir.Label(end))

    def _lower_println(self, s):
        value = self._flatten(s.arg)
        is_bool = getattr(s, "arg_type", None) == BOOLEAN
        self._emit(ir.Print(value, is_bool))

    def _lower_return(self, s):
        if self.is_main:
            self._emit(ir.Return(ir.Const(0)))   # C main returns int
        elif s.value is None:
            self._emit(ir.Return(None))
        else:
            self._emit(ir.Return(self._flatten(s.value)))

    # --- rendering: IR -> C text ---

    def _render_main(self, instrs, decls):
        lines = [
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "",
            "int main(void) {",
        ]
        for c_name, c_type in decls:
            lines.append(f"    {c_type} {c_name};")
        for tid in _temp_ids(instrs):
            lines.append(f"    int _t_{tid};")
        lines.append("")
        for ins in instrs:
            lines.append("    " + render_instr(ins))
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines) + "\n"


def _temp_ids(instrs):
    """Collect the ids of every temporary defined in the instruction list."""
    ids, seen = [], set()
    for ins in instrs:
        dst = None
        if isinstance(ins, (ir.BinOp, ir.UnOp)):
            dst = ins.dst
        elif isinstance(ins, ir.Assign) and isinstance(ins.dst, ir.Temp):
            dst = ins.dst
        if dst is not None and dst.id not in seen:
            seen.add(dst.id)
            ids.append(dst.id)
    return ids


def render_instr(ins):
    if isinstance(ins, ir.Assign):
        return f"{ins.dst.c} = {ins.src.c};"
    if isinstance(ins, ir.BinOp):
        return f"{ins.dst.c} = {ins.left.c} {ins.op} {ins.right.c};"
    if isinstance(ins, ir.UnOp):
        return f"{ins.dst.c} = {ins.op}{ins.operand.c};"
    if isinstance(ins, ir.Label):
        return f"{ins.name}: ;"
    if isinstance(ins, ir.Goto):
        return f"goto {ins.label};"
    if isinstance(ins, ir.IfFalse):
        return f"if (!({ins.cond.c})) goto {ins.label};"
    if isinstance(ins, ir.Print):
        if ins.is_bool:
            return f'printf(({ins.value.c}) ? "true\\n" : "false\\n");'
        return f'printf("%d\\n", {ins.value.c});'
    if isinstance(ins, ir.Return):
        if ins.value is None:
            return "return;"
        return f"return {ins.value.c};"
    raise CodeGenError(f"cannot render instruction {type(ins).__name__}")


def generate(program):
    """Generate C source text for an analyzed AUJava program."""
    return Emitter().generate(program)
