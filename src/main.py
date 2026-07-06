"""AUJava -> C transpiler: command-line entry point.

Pipeline:  read source -> lex -> parse -> semantic analysis -> generate C.

On any lexical, syntactic, or semantic error, every detected error is printed to
stderr and the program exits with a non-zero status WITHOUT writing a C file. On
success, the generated C is written to the output path (default: the input path
with a `.c` extension).

Usage:
    python src/main.py <input.aujava> [-o <output.c>]
"""

import argparse
import os
import sys

# Allow running directly as `python src/main.py ...` by putting the project root
# (the parent of this file's `src/` directory) on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.codegen.c_emitter import generate
from src.errors import CompilerError
from src.lexer import tokenize
from src.parser import Parser
from src.semantic.analyzer import analyze


def _default_output(input_path):
    root, _ = os.path.splitext(input_path)
    return root + ".c"


def compile_source(source):
    """Compile AUJava source text to C.

    Returns (c_code, errors). If `errors` is non-empty, `c_code` is None and no
    output should be written.
    """
    try:
        tokens = tokenize(source)                 # may raise LexerError
        program = Parser(tokens).parse()          # may raise ParserError
    except CompilerError as e:
        return None, [e]

    errors = analyze(program)                     # returns a list (may be empty)
    if errors:
        return None, errors

    return generate(program), []


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="aujavac",
        description="Transpile an AUJava source file to C.",
    )
    parser.add_argument("input", help="path to the .aujava source file")
    parser.add_argument(
        "-o", "--output", default=None,
        help="path for the generated .c file (default: <input>.c)",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        print(f"error: cannot read '{args.input}': {exc}", file=sys.stderr)
        return 1

    try:
        c_code, errors = compile_source(source)
    except Exception as exc:  # noqa: BLE001 - guard against leaking a raw traceback
        print(f"internal compiler error: {exc}", file=sys.stderr)
        return 2

    if errors:
        for e in errors:
            message = e.format() if isinstance(e, CompilerError) else str(e)
            print(message, file=sys.stderr)
        print(f"compilation failed with {len(errors)} error(s)", file=sys.stderr)
        return 1

    output_path = args.output or _default_output(args.input)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(c_code)
    except OSError as exc:
        print(f"error: cannot write '{output_path}': {exc}", file=sys.stderr)
        return 1

    print(f"wrote {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
