"""The AUJava lexer (a.k.a. tokenizer / scanner).

It walks the source text one character at a time and produces a list of
`Token`s, skipping whitespace and comments while keeping accurate line/column
information. The final token is always an EOF marker so the parser has a clean
sentinel to stop on.

Usage:
    from src.lexer import Lexer
    tokens = Lexer(source_text).tokenize()
"""

from src.errors import LexerError
from src.tokens import KEYWORDS, Token, TokenType


# Two-character operators must be tried before their one-character prefixes,
# otherwise "==" would be read as two separate "=" tokens.
_TWO_CHAR = {
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
    "&&": TokenType.AND,
    "||": TokenType.OR,
}

_ONE_CHAR = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "!": TokenType.NOT,
    ".": TokenType.DOT,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
}


class Lexer:
    def __init__(self, source):
        self.source = source
        self.pos = 0            # index into source
        self.line = 1           # current 1-based line
        self.column = 1         # current 1-based column
        self.tokens = []

    # --- low-level cursor helpers ---

    def _at_end(self):
        return self.pos >= len(self.source)

    def _peek(self, offset=0):
        """Return the character `offset` ahead without consuming it, or '' at EOF."""
        i = self.pos + offset
        if i < len(self.source):
            return self.source[i]
        return ""

    def _advance(self):
        """Consume and return the current character, updating line/column."""
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    # --- main entry point ---

    def tokenize(self):
        while not self._at_end():
            ch = self._peek()

            # whitespace
            if ch in " \t\r\n":
                self._advance()
                continue

            # comments
            if ch == "/" and self._peek(1) == "/":
                self._skip_line_comment()
                continue
            if ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
                continue

            # identifiers / keywords
            if ch.isalpha() or ch == "_":
                self._read_identifier()
                continue

            # integer literals
            if ch.isdigit():
                self._read_number()
                continue

            # operators & punctuation
            self._read_symbol()

        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens

    # --- comment handling (produce no tokens, but keep line counting correct) ---

    def _skip_line_comment(self):
        # consume "//" then everything up to (but not including) the newline
        self._advance()
        self._advance()
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self):
        start_line, start_col = self.line, self.column
        self._advance()  # '/'
        self._advance()  # '*'
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()  # '*'
                self._advance()  # '/'
                return
            self._advance()
        # reached EOF without closing the comment
        raise LexerError("unterminated block comment", start_line, start_col)

    # --- token readers ---

    def _read_identifier(self):
        start_line, start_col = self.line, self.column
        chars = []
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            chars.append(self._advance())
        text = "".join(chars)
        ttype = KEYWORDS.get(text, TokenType.IDENT)
        self.tokens.append(Token(ttype, text, start_line, start_col))

    def _read_number(self):
        start_line, start_col = self.line, self.column
        chars = []
        while not self._at_end() and self._peek().isdigit():
            chars.append(self._advance())
        self.tokens.append(Token(TokenType.INT, "".join(chars), start_line, start_col))

    def _read_symbol(self):
        start_line, start_col = self.line, self.column
        two = self._peek() + self._peek(1)
        if two in _TWO_CHAR:
            self._advance()
            self._advance()
            self.tokens.append(Token(_TWO_CHAR[two], two, start_line, start_col))
            return

        one = self._peek()
        if one in _ONE_CHAR:
            self._advance()
            self.tokens.append(Token(_ONE_CHAR[one], one, start_line, start_col))
            return

        raise LexerError(f"unexpected character {one!r}", start_line, start_col)


def tokenize(source):
    """Convenience wrapper: return the token list for a source string."""
    return Lexer(source).tokenize()
