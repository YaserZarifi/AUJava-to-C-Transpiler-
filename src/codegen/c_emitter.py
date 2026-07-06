"""C code emitter: turns an analyzed AUJava AST into C source text.

Layout of the generated C file:

    #includes
    typedef struct X X;          (forward declarations, so any class order works)
    struct X { fields; method-function-pointers; };
    prototypes for new_X() and every X_function_m()
    constructor bodies new_X()
    method bodies X_function_m(void *caller, ...)
    int main(void) { ... }       (the entry class's main)

Object model (per the spec):
* a class becomes a struct whose members are its fields plus a function pointer
  per method;
* `new C()` -> `new_C()` mallocs, zero/NULL-initializes fields, and assigns the
  method function pointers;
* a method call `obj.m(a)` -> `obj->function_m(obj, a)` -- the receiver is passed
  as the first argument (`void *caller`) and cast back inside the function;
* `this` is the caller pointer; field access is `caller->field`.

Control-flow, expressions, locals (hoisted + uniquely renamed) and println work
exactly as in the previous phase.
"""

from src import ast_nodes as ast
from src.codegen import ir
from src.semantic.symbol_table import ClassTable
from src.semantic.types import BOOLEAN, INT, VOID, ClassType


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


def c_type(sem_type):
    """Map a semantic Type to its C spelling."""
    if sem_type == INT or sem_type == BOOLEAN:
        return "int"
    if sem_type == VOID:
        return "void"
    if isinstance(sem_type, ClassType):
        return f"{sem_type.name} *"
    raise CodeGenError(f"no C type for {sem_type!r}")


class Emitter:
    def __init__(self, program):
        self.program = program
        self.ct = ClassTable.build(program)
        self.namer = ir.Namer()
        self._local_id = 0

    # ------------------------------------------------------------------ top level

    def generate(self):
        entry_class, main = find_entry_main(self.program)
        classes = [c for c in self.program.classes if c is not entry_class]

        out = ["#include <stdio.h>", "#include <stdlib.h>", ""]

        # forward typedefs so classes can reference each other in any order
        for c in classes:
            out.append(f"typedef struct {c.name} {c.name};")
        out.append("")

        # struct definitions
        for c in classes:
            out.append(self._render_struct(c))
            out.append("")

        # prototypes (constructors + methods) before any body
        for c in classes:
            out.append(f"{c.name} *new_{c.name}(void);")
            for m in c.methods:
                out.append(self._method_signature(c, m) + ";")
        out.append("")

        # constructor bodies
        for c in classes:
            out.append(self._render_constructor(c))
            out.append("")

        # method bodies
        for c in classes:
            for m in c.methods:
                out.append(self._render_method(c, m))
                out.append("")

        # entry point
        out.append(self._render_main(entry_class, main))
        return "\n".join(out) + "\n"

    # ------------------------------------------------------------------ structs

    def _method_ptr_field(self, mi):
        ret = c_type(mi.return_type)
        params = ["void *"] + [c_type(pt) for pt in mi.param_types]
        return f"{ret} (*function_{mi.name})({', '.join(params)})"

    def _render_struct(self, c):
        ci = self.ct.get(c.name)
        lines = [f"struct {c.name} {{"]
        for fname, fi in ci.fields.items():
            lines.append(f"    {c_type(fi.type)} {fname};")
        for mi in ci.methods.values():
            lines.append(f"    {self._method_ptr_field(mi)};")
        lines.append("};")
        return "\n".join(lines)

    # ------------------------------------------------------------------ constructors

    def _render_constructor(self, c):
        ci = self.ct.get(c.name)
        lines = [f"{c.name} *new_{c.name}(void) {{"]
        lines.append(f"    {c.name} *instance = ({c.name} *)malloc(sizeof({c.name}));")
        for fname, fi in ci.fields.items():
            init = "NULL" if isinstance(fi.type, ClassType) else "0"
            lines.append(f"    instance->{fname} = {init};")
        for mi in ci.methods.values():
            lines.append(
                f"    instance->function_{mi.name} = {c.name}_function_{mi.name};"
            )
        lines.append("    return instance;")
        lines.append("}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ methods

    def _method_signature(self, c, m):
        mi = self.ct.get(c.name).methods[m.name]
        ret = c_type(mi.return_type)
        params = ["void *_caller"]
        for idx, pt in enumerate(mi.param_types):
            params.append(f"{c_type(pt)} {self._param_c_name(m, idx)}")
        return f"{ret} {c.name}_function_{m.name}({', '.join(params)})"

    @staticmethod
    def _param_c_name(m, idx):
        return f"{m.params[idx].name}__a{idx + 1}"

    def _render_method(self, c, m):
        ci = self.ct.get(c.name)
        # assign parameter C names onto their shared VarInfo objects
        for idx, pinfo in enumerate(getattr(m, "param_infos", [])):
            if pinfo is not None:
                pinfo.c_name = self._param_c_name(m, idx)

        self.current_class = ci
        self.self_name = "_self"
        instrs, decls = self._lower_body(m, is_main=False)

        lines = [self._method_signature(c, m) + " {"]
        lines.append(f"    {c.name} *_self = ({c.name} *)_caller;")
        lines.extend(self._decl_lines(instrs, decls))
        lines.append("")
        for ins in instrs:
            lines.append("    " + self._render_instr(ins))
        lines.append("}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ main

    def _render_main(self, entry_class, main):
        self.current_class = self.ct.get(entry_class.name)
        self.self_name = None      # main is static: no `this`
        instrs, decls = self._lower_body(main, is_main=True)

        lines = ["int main(void) {"]
        lines.extend(self._decl_lines(instrs, decls))
        lines.append("")
        for ins in instrs:
            lines.append("    " + self._render_instr(ins))
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines)

    def _decl_lines(self, instrs, decls):
        lines = [f"    {ctype} {cname};" for cname, ctype in decls]
        for tid, ctype in self._temp_decls(instrs):
            lines.append(f"    {ctype} _t_{tid};")
        return lines

    # ------------------------------------------------------------------ lowering

    def _new_local(self, base):
        self._local_id += 1
        return f"{base}__{self._local_id}"

    def _lower_body(self, method, is_main):
        self.instrs = []
        self.decls = []
        self.loop_stack = []
        self.temp_types = {}       # temp id -> C type (default int)
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
            self._flatten(s.expr)
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
        self.decls.append((c_name, c_type(s.var_info.type)))
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
            self._emit(ir.Return(ir.Const(0)))
        elif s.value is None:
            self._emit(ir.Return(None))
        else:
            self._emit(ir.Return(self._flatten(s.value)))

    # ------------------------------------------------------------------ object operands
    # (these are the hooks ir.flatten_expr calls back into via ctx=self)

    def flatten_object_expr(self, expr, out):
        if isinstance(expr, ast.This):
            return ir.Name(self.self_name)
        if isinstance(expr, ast.NewObject):
            t = self.namer.new_temp()
            self.temp_types[t.id] = f"{expr.class_name} *"
            out.append(ir.NewInstr(t, expr.class_name))
            return t
        if isinstance(expr, ast.FieldAccess):
            recv = ir.flatten_expr(expr.receiver, out, self.namer, ctx=self)
            return ir.Raw(f"{recv.c}->{expr.name}")
        if isinstance(expr, ast.MethodCall):
            return self._flatten_call(expr, out)
        raise CodeGenError(f"cannot lower expression {type(expr).__name__}")

    def flatten_field_operand(self, identifier, out):
        # a bare identifier that resolved to an (implicit-this) field
        return ir.Raw(f"{self.self_name}->{identifier.name}")

    def flatten_assign_target(self, target, value, out):
        if isinstance(target, ast.Identifier):        # implicit-this field
            member = f"{self.self_name}->{target.name}"
        elif isinstance(target, ast.FieldAccess):
            recv = ir.flatten_expr(target.receiver, out, self.namer, ctx=self)
            member = f"{recv.c}->{target.name}"
        else:
            raise CodeGenError("invalid assignment target")
        out.append(ir.Assign(ir.Raw(member), value))
        return ir.Raw(member)

    def _flatten_call(self, e, out):
        if e.receiver is None:
            recv = ir.Name(self.self_name)            # implicit `this`
        else:
            recv = ir.flatten_expr(e.receiver, out, self.namer, ctx=self)
        args = [ir.flatten_expr(a, out, self.namer, ctx=self) for a in e.args]
        mi = e.method_info
        method_c = f"function_{e.name}"
        if mi.return_type == VOID:
            out.append(ir.MethodCallInstr(None, recv, method_c, args))
            return None
        t = self.namer.new_temp()
        self.temp_types[t.id] = c_type(mi.return_type)
        out.append(ir.MethodCallInstr(t, recv, method_c, args))
        return t

    # ------------------------------------------------------------------ rendering

    def _temp_decls(self, instrs):
        """Yield (temp_id, c_type) for every temporary defined in `instrs`."""
        seen = []
        found = set()

        def note(op):
            if isinstance(op, ir.Temp) and op.id not in found:
                found.add(op.id)
                seen.append((op.id, self.temp_types.get(op.id, "int")))

        for ins in instrs:
            if isinstance(ins, (ir.BinOp, ir.UnOp)):
                note(ins.dst)
            elif isinstance(ins, ir.Assign) and isinstance(ins.dst, ir.Temp):
                note(ins.dst)
            elif isinstance(ins, ir.NewInstr):
                note(ins.dst)
            elif isinstance(ins, ir.MethodCallInstr) and ins.dst is not None:
                note(ins.dst)
        return seen

    def _render_instr(self, ins):
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
            return "return;" if ins.value is None else f"return {ins.value.c};"
        if isinstance(ins, ir.NewInstr):
            return f"{ins.dst.c} = new_{ins.class_name}();"
        if isinstance(ins, ir.MethodCallInstr):
            call_args = ", ".join([ins.receiver.c] + [a.c for a in ins.args])
            call = f"{ins.receiver.c}->{ins.method_c}({call_args})"
            return f"{ins.dst.c} = {call};" if ins.dst is not None else f"{call};"
        raise CodeGenError(f"cannot render instruction {type(ins).__name__}")


def generate(program):
    """Generate C source text for an analyzed AUJava program."""
    return Emitter(program).generate()
