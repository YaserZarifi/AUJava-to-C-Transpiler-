"""Tests for the lexer (Phase 1)."""

import pytest

from src.errors import LexerError
from src.lexer import tokenize
from src.tokens import TokenType


def types(source):
    """Helper: list of TokenType for a source string, excluding the final EOF."""
    return [t.type for t in tokenize(source)[:-1]]


def test_ends_with_eof():
    toks = tokenize("")
    assert len(toks) == 1
    assert toks[0].type == TokenType.EOF


def test_keywords_vs_identifiers():
    toks = tokenize("class Student classes _x9")
    assert toks[0].type == TokenType.CLASS      # exact keyword
    assert toks[1].type == TokenType.IDENT      # "Student"
    assert toks[2].type == TokenType.IDENT      # "classes" is NOT the keyword
    assert toks[3].type == TokenType.IDENT      # "_x9" underscore + digits ok


def test_identifier_with_digits_and_underscore():
    toks = tokenize("my_var2 x1_")
    assert [t.value for t in toks[:-1]] == ["my_var2", "x1_"]
    assert all(t.type == TokenType.IDENT for t in toks[:-1])


def test_integer_literal():
    toks = tokenize("0 42 100")
    assert [t.type for t in toks[:-1]] == [TokenType.INT] * 3
    assert [t.value for t in toks[:-1]] == ["0", "42", "100"]


def test_number_glued_to_operator():
    # "3+4" with no spaces must split into three tokens.
    assert types("3+4") == [TokenType.INT, TokenType.PLUS, TokenType.INT]


def test_two_char_operators_beat_one_char():
    assert types("== != <= >= && ||") == [
        TokenType.EQ, TokenType.NEQ, TokenType.LE,
        TokenType.GE, TokenType.AND, TokenType.OR,
    ]
    # a lone "=" and "!" and "<" are still their single-char tokens
    assert types("= ! < >") == [
        TokenType.ASSIGN, TokenType.NOT, TokenType.LT, TokenType.GT,
    ]


def test_all_punctuation():
    assert types(". , ; ( ) { } [ ]") == [
        TokenType.DOT, TokenType.COMMA, TokenType.SEMICOLON,
        TokenType.LPAREN, TokenType.RPAREN, TokenType.LBRACE,
        TokenType.RBRACE, TokenType.LBRACKET, TokenType.RBRACKET,
    ]


def test_line_comment_is_ignored():
    toks = tokenize("int x // this is a comment\n= 5")
    assert types("int x // this is a comment\n= 5") == [
        TokenType.INT_TYPE, TokenType.IDENT, TokenType.ASSIGN, TokenType.INT,
    ]


def test_line_comment_at_eof_without_newline():
    # A comment with no trailing newline at end of file must not error.
    toks = tokenize("int x // trailing comment no newline")
    assert types("int x // trailing comment no newline") == [
        TokenType.INT_TYPE, TokenType.IDENT,
    ]


def test_block_comment_is_ignored_and_counts_lines():
    source = "int a;\n/* comment\nspanning\nlines */\nint b;"
    toks = tokenize(source)
    # tokens: int(0) a(1) ;(2)  <block comment, no token>  int(3) b(4) ;(5) EOF(6)
    # The second "int" must report the correct line (5) after the 3-line comment.
    second_int = toks[3]
    assert second_int.type == TokenType.INT_TYPE
    assert second_int.value == "int"
    assert second_int.line == 5


def test_unterminated_block_comment_errors():
    with pytest.raises(LexerError):
        tokenize("int a; /* never closed")


def test_unexpected_character_errors():
    with pytest.raises(LexerError):
        tokenize("int x = 5 @ 6;")


def test_line_and_column_tracking():
    # "  x" -> x is on line 1, column 3
    toks = tokenize("  x\n  y")
    x = toks[0]
    y = toks[1]
    assert (x.line, x.column) == (1, 3)
    assert (y.line, y.column) == (2, 3)


def test_small_program_token_sequence():
    source = (
        "class Main {\n"
        "  public static void main(String[] args) {\n"
        "    System.out.println(1 + 2 * 3);\n"
        "  }\n"
        "}\n"
    )
    seq = types(source)
    # spot-check the shape: starts with `class Main {`
    assert seq[:3] == [TokenType.CLASS, TokenType.IDENT, TokenType.LBRACE]
    # contains the arithmetic expression tokens in order
    assert TokenType.PLUS in seq and TokenType.STAR in seq
