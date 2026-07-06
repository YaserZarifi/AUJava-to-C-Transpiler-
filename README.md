# AUJava-to-C Transpiler

A transpiler that translates a subset of Java ("AUJava") into C, written in pure Python.

Compiler course project — Amirkabir University of Technology.

## Pipeline

```
AUJava (.aujava)  ->  Lexer  ->  Parser  ->  Semantic Analyzer  ->  Code Generator  ->  C (.c)
```

## Requirements

- Python 3.11+ (developed on 3.13)
- A C compiler (`gcc`) — used to compile and run the generated C for testing
- `pytest` (dev/testing): `python -m pip install pytest`

## Usage

```bash
# Transpile AUJava to C
python src/main.py input.aujava -o output.c

# Compile the generated C
gcc output.c -o output.exe

# Run it
./output.exe
```

## Running the tests

```bash
python -m pytest -v            # unit tests per compiler stage
python tests/run_e2e.py        # end-to-end: transpile + gcc compile + compare output
```

## Project layout

```
src/
  tokens.py          token type definitions
  lexer.py           source text -> tokens
  ast_nodes.py       AST node classes
  parser.py          recursive-descent parser (+ expression precedence)
  errors.py          error types ("Error at line L, col C: ...")
  semantic/          two-pass symbol table + semantic analyzer
  codegen/           IR (three-address code), struct layout, C emitter
  main.py            CLI entry point
tests/               per-stage unit tests + end-to-end harness
docs/                grammar (EBNF) and project report
```

## Status

Under active development, built in phases. See progress in the git history.
