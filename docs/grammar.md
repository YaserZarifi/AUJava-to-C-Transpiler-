# AUJava Grammar (EBNF)

Notation: `*` = zero or more, `?` = optional, `|` = alternative, `'x'` = literal
token, `UPPER` = terminal token class from the lexer (`IDENT`, `INT`).

## Program & declarations

```
program     := classDecl* EOF

classDecl   := 'public'? 'class' IDENT ( 'extends' IDENT )? '{' member* '}'

member      := modifier* ( methodDecl | fieldDecl )
modifier    := 'public' | 'static'

fieldDecl   := type IDENT ( '=' expr )? ';'
methodDecl  := ( type | 'void' ) IDENT '(' params? ')' block

params      := param ( ',' param )*
param       := type '[' ']'? IDENT      // '[]' only used by `String[] args` in main

type        := 'int' | 'boolean' | IDENT   // IDENT = a class name
```

## Statements

```
block       := '{' stmt* '}'

stmt        := block
             | ifStmt
             | whileStmt
             | 'break' ';'
             | 'continue' ';'
             | 'return' expr? ';'
             | printlnStmt
             | varDecl
             | exprStmt

ifStmt      := 'if' '(' expr ')' stmt ( 'else' stmt )?
whileStmt   := 'while' '(' expr ')' stmt
printlnStmt := 'System' '.' 'out' '.' 'println' '(' expr ')' ';'
varDecl     := type IDENT ( '=' expr )? ';'
exprStmt    := expr ';'
```

Disambiguation of `varDecl` vs `exprStmt` (both can start with an IDENT):
- `int`/`boolean` first  → varDecl.
- `IDENT IDENT` (class-type name followed by variable name) → varDecl.
- otherwise → exprStmt.

## Expressions (lowest → highest precedence)

```
expr        := assignment
assignment  := logicOr ( '=' assignment )?          // right-associative
logicOr     := logicAnd ( '||' logicAnd )*
logicAnd    := equality ( '&&' equality )*
equality    := comparison ( ( '==' | '!=' ) comparison )*
comparison  := additive  ( ( '<' | '>' | '<=' | '>=' ) additive )*
additive    := multiplic ( ( '+' | '-' ) multiplic )*
multiplic   := unary     ( ( '*' | '/' | '%' ) unary )*
unary       := ( '!' | '-' ) unary | postfix
postfix     := primary ( '.' IDENT ( '(' args? ')' )? )*
primary     := INT
             | 'true' | 'false'
             | 'this'
             | 'new' IDENT '(' ')'                  // default constructor only
             | IDENT ( '(' args? ')' )?             // bare call = implicit-this method call
             | '(' expr ')'
args        := expr ( ',' expr )*
```

This precedence ladder matches Java: `*` `/` `%` bind tighter than `+` `-`, which
bind tighter than comparisons, then equality, then `&&`, then `||`, then `=`.
