"""Compiler error types.

Every user-facing compiler error reports the exact source position (line and
column) where the problem was detected, in a consistent format:

    Error at line L, col C: <message>

The spec requires that lexical, syntactic, and semantic errors all point at the
offending line/character of the input program. Sharing one base class keeps the
message format identical across all compiler stages.
"""


class CompilerError(Exception):
    """Base class for all errors raised while compiling an AUJava program."""

    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(self.format())

    def format(self):
        return f"Error at line {self.line}, col {self.column}: {self.message}"


class LexerError(CompilerError):
    """Raised by the lexer for illegal characters or unterminated comments."""


class ParserError(CompilerError):
    """Raised by the parser for syntactically invalid programs."""


class SemanticError(CompilerError):
    """Raised by the semantic analyzer for type/scope/rule violations."""
