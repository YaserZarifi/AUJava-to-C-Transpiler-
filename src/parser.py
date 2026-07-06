"""Recursive-descent parser for AUJava.

Turns the token list produced by the lexer into an AST (see `ast_nodes.py`).
Each grammar rule in `docs/grammar.md` corresponds to one `parse_*` method.
Expressions are parsed with a precedence-climbing loop so that operators bind
with the correct Java precedence.
"""

from src import ast_nodes as ast
from src.errors import ParserError
from src.lexer import tokenize
from src.tokens import Token, TokenType as T


# Binary operators mapped to (precedence, source-text). Higher precedence binds
# tighter. Assignment and the unary/postfix levels are handled separately.
_BINARY = {
    T.OR: (1, "||"),
    T.AND: (2, "&&"),
    T.EQ: (3, "=="),
    T.NEQ: (3, "!="),
    T.LT: (4, "<"),
    T.GT: (4, ">"),
    T.LE: (4, "<="),
    T.GE: (4, ">="),
    T.PLUS: (5, "+"),
    T.MINUS: (5, "-"),
    T.STAR: (6, "*"),
    T.SLASH: (6, "/"),
    T.PERCENT: (6, "%"),
}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # --- token cursor helpers ---

    def _peek(self, offset=0):
        i = self.pos + offset
        if i >= len(self.tokens):
            return self.tokens[-1]  # EOF sentinel
        return self.tokens[i]

    def _check(self, ttype):
        return self._peek().type == ttype

    def _advance(self):
        tok = self._peek()
        if tok.type != T.EOF:
            self.pos += 1
        return tok

    def _match(self, *ttypes):
        if self._peek().type in ttypes:
            return self._advance()
        return None

    def _expect(self, ttype, what=None):
        tok = self._peek()
        if tok.type == ttype:
            return self._advance()
        what = what or ttype.name
        raise ParserError(
            f"expected {what} but found {tok.value!r}", tok.line, tok.column
        )

    def _expect_ident_value(self, value):
        tok = self._peek()
        if tok.type == T.IDENT and tok.value == value:
            return self._advance()
        raise ParserError(
            f"expected {value!r} but found {tok.value!r}", tok.line, tok.column
        )

    # --- program & declarations ---

    def parse(self):
        classes = []
        while not self._check(T.EOF):
            classes.append(self.parse_class())
        return ast.Program(classes, 1, 1)

    def parse_class(self):
        is_public = bool(self._match(T.PUBLIC))
        kw = self._expect(T.CLASS)
        name = self._expect(T.IDENT, "class name")
        superclass = None
        if self._match(T.EXTENDS):
            superclass = self._expect(T.IDENT, "superclass name").value
        self._expect(T.LBRACE)
        fields, methods = [], []
        while not self._check(T.RBRACE) and not self._check(T.EOF):
            member = self.parse_member()
            if isinstance(member, ast.Field):
                fields.append(member)
            else:
                methods.append(member)
        self._expect(T.RBRACE)
        return ast.ClassDecl(
            name.value, superclass, fields, methods, is_public, kw.line, kw.column
        )

    def parse_member(self):
        # modifiers in any order (public / static)
        is_public = is_static = False
        while True:
            if self._match(T.PUBLIC):
                is_public = True
            elif self._match(T.STATIC):
                is_static = True
            else:
                break

        rtype = self.parse_type_or_void()
        name = self._expect(T.IDENT, "member name")

        if self._check(T.LPAREN):
            params = self.parse_params()
            body = self.parse_block()
            return ast.Method(
                name.value, rtype, params, body, is_static, is_public,
                rtype.line, rtype.col,
            )

        # otherwise it's a field
        if rtype.name == "void":
            raise ParserError("fields cannot have type 'void'", rtype.line, rtype.col)
        init = None
        if self._match(T.ASSIGN):
            init = self.parse_expression()
        self._expect(T.SEMICOLON)
        return ast.Field(name.value, rtype, is_static, init, rtype.line, rtype.col)

    def parse_type_or_void(self):
        tok = self._peek()
        if self._match(T.VOID):
            return ast.TypeRef("void", tok.line, tok.column)
        return self.parse_type()

    def parse_type(self):
        tok = self._peek()
        if self._match(T.INT_TYPE):
            return ast.TypeRef("int", tok.line, tok.column)
        if self._match(T.BOOLEAN):
            return ast.TypeRef("boolean", tok.line, tok.column)
        if self._check(T.IDENT):
            self._advance()
            return ast.TypeRef(tok.value, tok.line, tok.column)
        raise ParserError(f"expected a type but found {tok.value!r}", tok.line, tok.column)

    def parse_params(self):
        self._expect(T.LPAREN)
        params = []
        if not self._check(T.RPAREN):
            params.append(self.parse_param())
            while self._match(T.COMMA):
                params.append(self.parse_param())
        self._expect(T.RPAREN)
        return params

    def parse_param(self):
        ptype = self.parse_type()
        is_array = False
        if self._match(T.LBRACKET):
            self._expect(T.RBRACKET)
            is_array = True
        name = self._expect(T.IDENT, "parameter name")
        return ast.Param(name.value, ptype, is_array, ptype.line, ptype.col)

    # --- statements ---

    def parse_block(self):
        lb = self._expect(T.LBRACE)
        stmts = []
        while not self._check(T.RBRACE) and not self._check(T.EOF):
            stmts.append(self.parse_statement())
        self._expect(T.RBRACE)
        return ast.Block(stmts, lb.line, lb.column)

    def parse_statement(self):
        tok = self._peek()

        if self._check(T.LBRACE):
            return self.parse_block()
        if self._check(T.IF):
            return self.parse_if()
        if self._check(T.WHILE):
            return self.parse_while()
        if self._check(T.BREAK):
            self._advance()
            self._expect(T.SEMICOLON)
            return ast.Break(tok.line, tok.column)
        if self._check(T.CONTINUE):
            self._advance()
            self._expect(T.SEMICOLON)
            return ast.Continue(tok.line, tok.column)
        if self._check(T.RETURN):
            return self.parse_return()
        if self._check(T.INT_TYPE) or self._check(T.BOOLEAN):
            return self.parse_vardecl()
        if self._check(T.IDENT):
            # Disambiguate: println / class-typed varDecl / expression statement.
            if tok.value == "System" and self._peek(1).type == T.DOT:
                return self.parse_println()
            if self._peek(1).type == T.IDENT:
                return self.parse_vardecl()   # `ClassName varName ...`
            return self.parse_exprstmt()
        return self.parse_exprstmt()

    def parse_if(self):
        kw = self._expect(T.IF)
        self._expect(T.LPAREN)
        cond = self.parse_expression()
        self._expect(T.RPAREN)
        then_branch = self.parse_statement()
        else_branch = None
        if self._match(T.ELSE):
            else_branch = self.parse_statement()
        return ast.If(cond, then_branch, else_branch, kw.line, kw.column)

    def parse_while(self):
        kw = self._expect(T.WHILE)
        self._expect(T.LPAREN)
        cond = self.parse_expression()
        self._expect(T.RPAREN)
        body = self.parse_statement()
        return ast.While(cond, body, kw.line, kw.column)

    def parse_return(self):
        kw = self._expect(T.RETURN)
        value = None
        if not self._check(T.SEMICOLON):
            value = self.parse_expression()
        self._expect(T.SEMICOLON)
        return ast.Return(value, kw.line, kw.column)

    def parse_println(self):
        start = self._peek()
        self._expect_ident_value("System")
        self._expect(T.DOT)
        self._expect_ident_value("out")
        self._expect(T.DOT)
        self._expect_ident_value("println")
        self._expect(T.LPAREN)
        arg = self.parse_expression()
        self._expect(T.RPAREN)
        self._expect(T.SEMICOLON)
        return ast.Println(arg, start.line, start.column)

    def parse_vardecl(self):
        vtype = self.parse_type()
        name = self._expect(T.IDENT, "variable name")
        init = None
        if self._match(T.ASSIGN):
            init = self.parse_expression()
        self._expect(T.SEMICOLON)
        return ast.VarDecl(name.value, vtype, init, vtype.line, vtype.col)

    def parse_exprstmt(self):
        expr = self.parse_expression()
        self._expect(T.SEMICOLON)
        return ast.ExprStmt(expr, expr.line, expr.col)

    # --- expressions ---

    def parse_expression(self):
        return self.parse_assignment()

    def parse_assignment(self):
        left = self.parse_binary(1)
        if self._check(T.ASSIGN):
            eq = self._advance()
            value = self.parse_assignment()   # right-associative
            return ast.Assignment(left, value, eq.line, eq.column)
        return left

    def parse_binary(self, min_prec):
        left = self.parse_unary()
        while True:
            info = _BINARY.get(self._peek().type)
            if info is None or info[0] < min_prec:
                break
            prec, text = info
            op_tok = self._advance()
            right = self.parse_binary(prec + 1)   # left-associative
            left = ast.BinaryOp(text, left, right, op_tok.line, op_tok.column)
        return left

    def parse_unary(self):
        tok = self._peek()
        if self._check(T.NOT) or self._check(T.MINUS):
            self._advance()
            operand = self.parse_unary()
            op = "!" if tok.type == T.NOT else "-"
            return ast.UnaryOp(op, operand, tok.line, tok.column)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while self._check(T.DOT):
            self._advance()
            name = self._expect(T.IDENT, "member name after '.'")
            if self._check(T.LPAREN):
                args = self.parse_args()
                expr = ast.MethodCall(expr, name.value, args, name.line, name.column)
            else:
                expr = ast.FieldAccess(expr, name.value, name.line, name.column)
        return expr

    def parse_args(self):
        self._expect(T.LPAREN)
        args = []
        if not self._check(T.RPAREN):
            args.append(self.parse_expression())
            while self._match(T.COMMA):
                args.append(self.parse_expression())
        self._expect(T.RPAREN)
        return args

    def parse_primary(self):
        tok = self._peek()

        if self._match(T.INT):
            return ast.IntLiteral(int(tok.value), tok.line, tok.column)
        if self._match(T.TRUE):
            return ast.BoolLiteral(True, tok.line, tok.column)
        if self._match(T.FALSE):
            return ast.BoolLiteral(False, tok.line, tok.column)
        if self._match(T.THIS):
            return ast.This(tok.line, tok.column)
        if self._match(T.NEW):
            cname = self._expect(T.IDENT, "class name after 'new'")
            self._expect(T.LPAREN)
            self._expect(T.RPAREN)   # only the default constructor is supported
            return ast.NewObject(cname.value, tok.line, tok.column)
        if self._match(T.IDENT):
            if self._check(T.LPAREN):
                args = self.parse_args()
                # bare call => implicit `this` receiver
                return ast.MethodCall(None, tok.value, args, tok.line, tok.column)
            return ast.Identifier(tok.value, tok.line, tok.column)
        if self._match(T.LPAREN):
            expr = self.parse_expression()
            self._expect(T.RPAREN)
            return expr

        raise ParserError(f"unexpected token {tok.value!r}", tok.line, tok.column)


def parse(source):
    """Lex and parse a source string, returning the Program AST."""
    return Parser(tokenize(source)).parse()


def parse_tokens(tokens):
    """Parse an existing token list, returning the Program AST."""
    return Parser(tokens).parse()
