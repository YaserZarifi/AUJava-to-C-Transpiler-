# AUJava → C Transpiler — Project Report

Course: Principles of Compiler Design — Amirkabir University of Technology.
A transpiler that translates **AUJava** (a subset of Java) into **C**.

---

## 1. Language and tool choice

**AUJava** supports classes/fields/methods, object creation, single inheritance
(bonus), `static` members (bonus), `if/else`, `while` with `break`/`continue`,
the `int` and `boolean` types, `System.out.println`, method calls, the arithmetic
(`+ - * / %`), comparison (`< > <= >= == !=`) and boolean (`&& || !`) operators,
and assignment. The whole program lives in one file; exactly one entry class
holds `public static void main(String[] args)`.

**Implementation:** a hand-written compiler in **Python 3**, with a regex-free
character-level lexer and a recursive-descent parser. The project spec permits
Lex/Yacc, ANTLR, or a from-scratch implementation in any language; we chose a
from-scratch Python implementation for its fast edit–test loop, transparent
debuggability, and zero external build tooling. **Target language:** C
(compiled and verified with `gcc`).

The compiler is a classic pipeline:

```
AUJava source → Lexer → Parser → Semantic Analyzer → Code Generator → C source
   (.aujava)    tokens   AST        (checks+types)     (TAC → C text)     (.c)
```

## 2. Lexer (`src/lexer.py`, `src/tokens.py`)

The lexer scans the source character by character, producing a list of `Token`s
(each carrying its `line`/`column`). It recognizes:

* **keywords:** `class extends public static void int boolean if else while
  break continue return new this true false`;
* **identifiers** `[A-Za-z_][A-Za-z0-9_]*` and **integer literals** `[0-9]+`;
* **operators/punctuation:** `+ - * / % = == != < > <= >= && || ! . , ; ( ) { }
  [ ]` (two-character operators are matched before their one-character prefixes);
* **comments:** `// line` and `/* block */`, which are discarded while still
  advancing the line counter; an unterminated block comment is a lexical error.

`System`, `out`, `println`, and `String` are deliberately ordinary identifiers,
recognized structurally by the parser.

## 3. Grammar, AST and parser (`docs/grammar.md`, `src/ast_nodes.py`, `src/parser.py`)

The full EBNF grammar is in `docs/grammar.md`. The parser is recursive descent
(one method per rule) with a precedence-climbing loop for expressions, giving
Java operator precedence: `=` (right-assoc) < `||` < `&&` < `== !=` <
`< > <= >=` < `+ -` < `* / %` < unary `! -` < postfix `.`/call < primary.

Two small look-ahead decisions:
* `System.out.println(e)` is parsed as a dedicated statement;
* a statement starting with an identifier is a variable declaration when it is
  `IDENT IDENT` (class-typed local), otherwise an expression statement.

Every AST node stores its source position for later error messages. Syntax
errors report the offending token's line/column.

## 4. Semantic analysis (`src/semantic/`)

A **two-pass** design over a **symbol table**:

* **Pass 1 (`ClassTable`)** collects every class, field and method signature, so
  classes and members may be referenced in any order (forward references). It
  detects duplicate class names, unknown types, unknown superclasses, and
  **cyclic inheritance** (DFS three-coloring).
* **Pass 2 (`Analyzer`)** walks method bodies with a **scope stack** (each block
  pushes a frame; lookup goes innermost → outer → class fields), enforcing:
  declaration-before-use for locals, correct shadowing, type rules for every
  operator, assignment compatibility (incl. subclass → parent upcasts), method
  argument count/types (inheritance-aware), `this` only in instance methods,
  `break`/`continue` only inside loops, exactly one `main` (whose class holds
  only `main`), and `println` argument typing. Each violation is reported as
  `Error at line L, col C: <message>`; errors are accumulated so several can be
  reported at once. The analyzer also annotates the AST with resolved
  types/bindings that the code generator reuses.

## 5. Code generation (`src/codegen/`)

Method bodies are first lowered to **Three-Address Code** (`ir.py`): expressions
are flattened post-order into `_t_N` temporaries (e.g. `1 + 2 * 3` → five temps),
and control flow becomes labels and gotos. The emitter (`c_emitter.py`) then
renders C:

* **Control flow** → `goto`+labels exactly as the spec prescribes; `break`/
  `continue` use a stack of `(start,end)` labels so they affect the innermost
  loop only. `println(int)` → `printf("%d\n", …)`, `println(boolean)` →
  `printf(x ? "true\n" : "false\n")`.
* **Flat function scope:** all locals and temporaries are declared once, hoisted
  to the top of the C function, so `goto`s never jump over a declaration.
  Variables that share a name across AUJava scopes get distinct C names
  (`i__1`, `i__2`), which is what makes shadowing work.
* **Classes** → C `struct`s; each method is a function pointer in the struct plus
  a standalone `X_function_m(void *caller, …)` that casts `caller` back to the
  object. `new C()` → `new_C()` which `malloc`s, zero/NULL-initializes fields,
  and assigns the method pointers. A call `obj.m(a)` → `obj->function_m(obj, a)`.
  Forward `typedef struct X X;` declarations plus a prototype block let classes
  be defined in any order; struct bodies are emitted parent-before-child because
  a child embeds its parent by value.
* **Inheritance** → the parent is embedded as the first field `super`, so a child
  pointer and parent pointer share an address (upcasts are pointer casts). An
  override is written into the child's function pointer **and every ancestor
  level** that declares the method, so a call through an upcast pointer dispatches
  dynamically — verified for 2- and 3-level chains. Field/method access chooses
  the correct `super.` depth from the static type.
* **Static members** → a static field becomes a global `Class_field`; a static
  method becomes a plain function `Class_method(…)` with no `caller`; access is
  via the class name and static methods are not dispatched/overridden.

## 6. Documented design decisions (spec ambiguities)

1. **`println` accepts both `int` and `boolean`** (intro lists both); `boolean`
   prints `true`/`false`. Can be narrowed to int-only if required by the TA.
2. **Upcast assignment is allowed** (subclass → parent variable/field/parameter);
   the reverse is rejected.
3. **Object `==`/`!=`** is allowed between related class types and compiles to
   pointer comparison.
4. **The entry class** must contain only `main`; exactly one `main` must exist.
5. **Fields** are default-initialized (`0`/`false`/`NULL`) by the constructor;
   field initializers are not part of the required feature set.
6. **Overrides** must keep the same signature.

## 7. Sample input/output

Sample programs live in `tests/inputs/` with expected output in
`tests/expected/`. For example, `tests/inputs/inheritance3.aujava`
(`C extends B extends A`, C overrides a method declared in A) prints `3\n3\n`
whether called through an `A*`, `B*`, or `C*` view — demonstrating polymorphism.

## 8. Building and running

```bash
python -m pip install pytest        # test dependency
# gcc must be on PATH (used to compile the generated C)

python src/main.py input.aujava -o output.c   # transpile
gcc output.c -o output && ./output            # compile & run the C
```

On any error the compiler prints all errors and exits non-zero **without**
producing a `.c` file.

## 9. Testing

```bash
python -m pytest -v          # ~136 unit tests across all stages
python tests/run_e2e.py      # end-to-end: transpile + gcc compile + compare output
```

Coverage: lexer, parser, symbol table, semantic rules (a positive and negative
case each), IR flattening, and gcc-backed code-generation tests for control flow,
objects, inheritance (2- and 3-level), and statics, plus negative programs that
must be rejected.

## 10. Known limitations

* No short-circuit evaluation for `&&`/`||` (both operands are always evaluated),
  matching the flatten-everything TAC model; observable only with side-effecting
  operands.
* Fields named after C keywords are emitted verbatim as struct members (AUJava
  keywords already exclude the common cases).
* Unsupported by design (per spec): `for`, `do-while`, `switch`, `++`/`--`,
  compound assignment, interfaces, abstract classes, custom constructors, and
  access modifiers beyond the entry class's `public`.
