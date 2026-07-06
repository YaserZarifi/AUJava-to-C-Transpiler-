"""AUJava -> C transpiler: command-line entry point.

Phase 0 stub: for now this only reads the input file and prints its contents,
so we can confirm the CLI wiring works. Later phases replace the body with the
real pipeline: lexer -> parser -> semantic analyzer -> code generator.

Usage:
    python src/main.py <input.aujava> [-o <output.c>]
"""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="aujavac",
        description="Transpile an AUJava source file to C.",
    )
    parser.add_argument("input", help="path to the .aujava source file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="path for the generated .c file (default: <input>.c)",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        print(f"error: cannot read '{args.input}': {exc}", file=sys.stderr)
        return 1

    # Phase 0: just echo the source so we can see the CLI works end to end.
    print(f"--- read {len(source)} characters from {args.input} ---")
    print(source, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
