"""C code emitter: turns an analyzed AUJava AST into C source text.

Layout of the generated C file:

    #includes
    typedef struct X X;          (forward declarations, so any class order works)
    struct X { [P super;] fields; method-function-pointers; };
    prototypes for new_X() and every X_function_m()
    constructor bodies new_X()
    method bodies X_function_m(void *caller, ...)
    int main(void) { ... }       (the entry class's main)

Object model (per the spec):
* a class becomes a struct: its parent embedded as the first field `super`,
  then its own fields, then a function pointer per method it declares/overrides;
* `new C()` mallocs, zero/NULL-initializes every field at every inheritance
  level, and assigns each method function pointer -- propagating an override to
  the child level AND to every ancestor level that declares the method, so
  polymorphism works through an upcast pointer;
* a method call `obj.m(a)` -> `obj->[super...]function_m(obj, a)`, where the
  `super.` depth is chosen from the static type so the call lands on a struct
  level that actually holds the pointer;
* `this` is the caller pointer; a field access is `caller->[super...]field`,
  again with the depth chosen by where the field is declared.
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

        for c in classes:
            out.append(f"typedef struct {c.name} {c.name};")
        out.append("")

        # Struct bodies must be emitted parent-before-child: a child embeds its
        # parent by value (`A super;`), which needs the parent's complete type.
        # (Object-typed fields are pointers, so the forward typedefs above cover
        # any remaining ordering; only the embedded `super` needs this sort.)
        for c in sorted(classes, key=lambda cl: len(self._ancestry(cl.name))):
            out.append(self._render_struct(c))
            out.append("")

        for c in classes:
            out.append(f"{c.name} *new_{c.name}(void);")
            for m in c.methods:
                out.append(self._method_signature(c, m) + ";")
        out.append("")

        for c in classes:
            out.append(self._render_constructor(c))
            out.append("")

        for c in classes:
            for m in c.methods:
                out.append(self._render_method(c, m))
                out.append("")

        out.append(self._render_main(entry_class, main))
        return "\n".join(out) + "\n"

    # ------------------------------------------------------------------ inheritance helpers

    def _ancestry(self, name):
        """[name, parent, grandparent, ..., root]."""
        chain = []
        while name is not None:
            chain.append(name)
            name = self.ct.get(name).superclass
        return chain

    def _hops(self, from_name, to_name):
        """Number of `super` steps from class `from_name` up to `to_name`."""
        depth, name = 0, from_name
        while name is not None:
            if name == to_name:
                return depth
            name = self.ct.get(name).superclass
            depth += 1
        raise CodeGenError(f"{to_name} is not an ancestor of {from_name}")

    def _declarer_depth(self, from_name, method):
        """`super` steps from `from_name` to the nearest class declaring `method`."""
        depth, name = 0, from_name
        while name is not None:
            if method in self.ct.get(name).methods:
                return depth
            name = self.ct.get(name).superclass
            depth += 1
        raise CodeGenError(f"method {method} not found from {from_name}")

    def _effective_impl(self, from_name, method):
        """Nearest class (from `from_name` upward) that declares `method`."""
        name = from_name
        while name is not None:
            if method in self.ct.get(name).methods:
                return name
            name = self.ct.get(name).superclass
        raise CodeGenError(f"method {method} not found from {from_name}")

    def _field_member(self, static_name, fi, base_c):
        prefix = "super." * self._hops(static_name, fi.owner)
        return f"{base_c}->{prefix}{fi.name}"

    def _coerce(self, op, sem_type):
        """Insert a C pointer cast for object-typed slots (makes upcasts clean)."""
        if isinstance(sem_type, ClassType):
            return ir.Raw(f"({sem_type.name} *){op.c}")
        return op

    # ------------------------------------------------------------------ structs

    def _method_ptr_field(self, mi):
        ret = c_type(mi.return_type)
        params = ["void *"] + [c_type(pt) for pt in mi.param_types]
        return f"{ret} (*function_{mi.name})({', '.join(params)})"

    def _render_struct(self, c):
        ci = self.ct.get(c.name)
        lines = [f"struct {c.name} {{"]
        if c.superclass:
            lines.append(f"    {c.superclass} super;")   # embedded parent, first
        for fname, fi in ci.fields.items():
            lines.append(f"    {c_type(fi.type)} {fname};")
        for mi in ci.methods.values():
            lines.append(f"    {self._method_ptr_field(mi)};")
        lines.append("};")
        return "\n".join(lines)

    # ------------------------------------------------------------------ constructors

    def _render_constructor(self, c):
        ancestry = self._ancestry(c.name)
        lines = [f"{c.name} *new_{c.name}(void) {{"]
        lines.append(f"    {c.name} *instance = ({c.name} *)malloc(sizeof({c.name}));")

        # default-initialize every field at every inheritance level
        for depth, cls in enumerate(ancestry):
            prefix = "super." * depth
            for fname, fi in self.ct.get(cls).fields.items():
                init = "NULL" if isinstance(fi.type, ClassType) else "0"
                lines.append(f"    instance->{prefix}{fname} = {init};")

        # wire up method pointers; an override is propagated to the child level
        # AND to every ancestor level that declares the method.
        for depth, cls in enumerate(ancestry):
            prefix = "super." * depth
            for mname in self.ct.get(cls).methods:
                impl = self._effective_impl(c.name, mname)
                lines.append(
                    f"    instance->{prefix}function_{mname} = {impl}_function_{mname};"
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
        mi = ci.methods[m.name]
        for idx, pinfo in enumerate(getattr(m, "param_infos", [])):
            if pinfo is not None:
                pinfo.c_name = self._param_c_name(m, idx)

        self.current_class = ci
        self.self_name = "_self"
        self.current_return_type = mi.return_type
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
        self.self_name = None
        self.current_return_type = VOID
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
        self.temp_types = {}
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
            value = self._coerce(self._flatten(s.init), s.var_info.type)
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
            value = self._coerce(self._flatten(s.value), self.current_return_type)
            self._emit(ir.Return(value))

    # ------------------------------------------------------------------ object operands
    # (hooks that ir.flatten_expr calls back into via ctx=self)

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
            return ir.Raw(self._field_member(expr.receiver_type.name, expr.field_info, recv.c))
        if isinstance(expr, ast.MethodCall):
            return self._flatten_call(expr, out)
        raise CodeGenError(f"cannot lower expression {type(expr).__name__}")

    def flatten_field_operand(self, identifier, out):
        fi = identifier.binding[1]
        return ir.Raw(self._field_member(self.current_class.name, fi, self.self_name))

    def flatten_assignment(self, target, value, out):
        if isinstance(target, ast.Identifier):
            kind, info = target.binding
            if kind == "local":
                dst = ir.Name(info.c_name)
                out.append(ir.Assign(dst, self._coerce(value, info.type)))
                return dst
            member = self._field_member(self.current_class.name, info, self.self_name)
            out.append(ir.Assign(ir.Raw(member), self._coerce(value, info.type)))
            return ir.Raw(member)
        if isinstance(target, ast.FieldAccess):
            recv = ir.flatten_expr(target.receiver, out, self.namer, ctx=self)
            fi = target.field_info
            member = self._field_member(target.receiver_type.name, fi, recv.c)
            out.append(ir.Assign(ir.Raw(member), self._coerce(value, fi.type)))
            return ir.Raw(member)
        raise CodeGenError("invalid assignment target")

    def _flatten_call(self, e, out):
        if e.receiver is None:
            recv = ir.Name(self.self_name)
            static_name = self.current_class.name
        else:
            recv = ir.flatten_expr(e.receiver, out, self.namer, ctx=self)
            static_name = e.receiver_type.name
        depth = self._declarer_depth(static_name, e.name)
        method_c = ("super." * depth) + f"function_{e.name}"
        mi = e.method_info
        args = [
            self._coerce(ir.flatten_expr(a, out, self.namer, ctx=self), pt)
            for a, pt in zip(e.args, mi.param_types)
        ]
        if mi.return_type == VOID:
            out.append(ir.MethodCallInstr(None, recv, method_c, args))
            return None
        t = self.namer.new_temp()
        self.temp_types[t.id] = c_type(mi.return_type)
        out.append(ir.MethodCallInstr(t, recv, method_c, args))
        return t

    # ------------------------------------------------------------------ rendering

    def _temp_decls(self, instrs):
        seen, found = [], set()

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
