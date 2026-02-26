#!/usr/bin/env python3
"""
Flux — a programming language with time travel and parallel universes.

STATEMENTS
  x = expr               assign variable
  PRINT expr             print to stdout
  INPUT var              read line from stdin into var
  ROLL lo hi var         store random integer in [lo, hi] in var
  IF cond THEN ... END   conditional (optional ELSE branch)
  LOOP n ... END         repeat n times
  WHILE cond ... END     repeat while condition is true
  ANCHOR name            save named snapshot of variable state
  REWIND n               undo last n statements AND jump back n steps (one-shot)
  REWIND TO name         restore variable state to a named anchor
  BRANCH                 open parallel branch (repeat for each branch)
    ...
  BRANCH
    ...
  MERGE MAX var          keep branch where var is greatest
  MERGE MIN var          keep branch where var is smallest
  MERGE FIRST            keep first branch that ran without error

EXPRESSIONS
  literals: 42  3.14  "hello"  TRUE  FALSE
  variables: x
  arithmetic: + - * / %
  comparison: == != < > <= >=
  logic: AND OR NOT
  grouping: ( expr )

NOTES
  - REWIND n restores state to what it was n steps ago and replays from there.
    It fires exactly once; re-encountering it on the replay skips it.
  - ROLL generates a new random value each time it executes, so rewinding
    past a ROLL gives you a different random number.
  - Each BRANCH runs in its own universe (copy of state); MERGE picks the
    winner and merges its state back.
  - Comments start with #

USAGE
  python3 flux.py <program.flux>
"""

import sys
import copy
import random

# ── Lexer ─────────────────────────────────────────────────────────────────────

KEYWORDS = {
    'PRINT', 'INPUT', 'ROLL',
    'IF', 'THEN', 'ELSE', 'END',
    'LOOP', 'WHILE',
    'ANCHOR', 'REWIND', 'TO',
    'BRANCH', 'MERGE', 'MAX', 'MIN', 'FIRST',
    'AND', 'OR', 'NOT', 'TRUE', 'FALSE',
}


def tokenize(src):
    toks, line, i = [], 1, 0
    while i < len(src):
        c = src[i]

        if c == '\n':
            line += 1; i += 1; continue
        if c in ' \t\r':
            i += 1; continue
        if c == '#':
            while i < len(src) and src[i] != '\n':
                i += 1
            continue

        if c == '"':
            j = i + 1
            while j < len(src) and src[j] != '"':
                if src[j] == '\\':
                    j += 1
                j += 1
            val = (src[i+1:j]
                   .replace('\\n', '\n')
                   .replace('\\t', '\t')
                   .replace('\\"', '"'))
            toks.append(('STR', val, line))
            i = j + 1
            continue

        if c.isdigit():
            j = i
            while j < len(src) and src[j].isdigit():
                j += 1
            if (j < len(src) and src[j] == '.'
                    and j + 1 < len(src) and src[j+1].isdigit()):
                j += 1
                while j < len(src) and src[j].isdigit():
                    j += 1
                toks.append(('NUM', float(src[i:j]), line))
            else:
                toks.append(('NUM', int(src[i:j]), line))
            i = j
            continue

        if c.isalpha() or c == '_':
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == '_'):
                j += 1
            word = src[i:j]
            toks.append((word if word in KEYWORDS else 'ID', word, line))
            i = j
            continue

        if src[i:i+2] in ('==', '!=', '<=', '>='):
            toks.append((src[i:i+2], src[i:i+2], line))
            i += 2
            continue

        if c in '=+-*/%<>()':
            toks.append((c, c, line))
            i += 1
            continue

        raise SyntaxError(f"line {line}: unexpected character {c!r}")

    toks.append(('EOF', None, line))
    return toks


# ── Parser ────────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def cur(self):
        return self.t[self.i]

    def peek(self, n=0):
        return self.t[self.i + n]

    def eat(self, *types):
        tok = self.cur()
        if tok[0] not in types:
            raise SyntaxError(
                f"line {tok[2]}: expected {list(types)}, "
                f"got {tok[0]!r} ({tok[1]!r})"
            )
        self.i += 1
        return tok

    def parse(self):
        stmts = self.block('EOF')
        return stmts

    def block(self, *stops):
        stmts = []
        while self.cur()[0] not in stops and self.cur()[0] != 'EOF':
            stmts.append(self.stmt())
        return stmts

    def stmt(self):
        t = self.cur()
        k = t[0]

        if k == 'PRINT':
            self.eat('PRINT')
            return ('print', self.expr())

        if k == 'INPUT':
            self.eat('INPUT')
            return ('input', self.eat('ID')[1])

        if k == 'ROLL':
            self.eat('ROLL')
            lo = self.expr()
            hi = self.expr()
            var = self.eat('ID')[1]
            return ('roll', lo, hi, var)

        if k == 'IF':
            self.eat('IF')
            cond = self.expr()
            self.eat('THEN')
            then = self.block('ELSE', 'END')
            els = []
            if self.cur()[0] == 'ELSE':
                self.eat('ELSE')
                els = self.block('END')
            self.eat('END')
            return ('if', cond, then, els)

        if k == 'LOOP':
            self.eat('LOOP')
            n = self.expr()
            body = self.block('END')
            self.eat('END')
            return ('loop', n, body)

        if k == 'WHILE':
            self.eat('WHILE')
            cond = self.expr()
            body = self.block('END')
            self.eat('END')
            return ('while', cond, body)

        if k == 'ANCHOR':
            self.eat('ANCHOR')
            return ('anchor', self.eat('ID')[1])

        if k == 'REWIND':
            self.eat('REWIND')
            if self.cur()[0] == 'TO':
                self.eat('TO')
                return ('rewind_to', self.eat('ID')[1])
            return ('rewind', self.expr())

        if k == 'BRANCH':
            branches = []
            while self.cur()[0] == 'BRANCH':
                self.eat('BRANCH')
                body = self.block('BRANCH', 'MERGE')
                branches.append(body)
            self.eat('MERGE')
            strat = self.eat('MAX', 'MIN', 'FIRST')[0].lower()
            var = self.eat('ID')[1] if strat in ('max', 'min') else None
            return ('branch', branches, strat, var)

        if k == 'ID' and self.peek(1)[0] == '=':
            name = self.eat('ID')[1]
            self.eat('=')
            return ('assign', name, self.expr())

        raise SyntaxError(f"line {t[2]}: unexpected token {k!r} ({t[1]!r})")

    # Expression parsing — precedence climbing

    def expr(self):   return self.or_()

    def or_(self):
        n = self.and_()
        while self.cur()[0] == 'OR':
            self.eat('OR')
            n = ('or', n, self.and_())
        return n

    def and_(self):
        n = self.not_()
        while self.cur()[0] == 'AND':
            self.eat('AND')
            n = ('and', n, self.not_())
        return n

    def not_(self):
        if self.cur()[0] == 'NOT':
            self.eat('NOT')
            return ('not', self.not_())
        return self.cmp()

    def cmp(self):
        n = self.add()
        OPS = ('==', '!=', '<', '>', '<=', '>=')
        while self.cur()[0] in OPS:
            op = self.eat(*OPS)[0]
            n = ('cmp', op, n, self.add())
        return n

    def add(self):
        n = self.mul()
        while self.cur()[0] in ('+', '-'):
            op = self.eat('+', '-')[0]
            n = ('bin', op, n, self.mul())
        return n

    def mul(self):
        n = self.unary()
        while self.cur()[0] in ('*', '/', '%'):
            op = self.eat('*', '/', '%')[0]
            n = ('bin', op, n, self.unary())
        return n

    def unary(self):
        if self.cur()[0] == '-':
            self.eat('-')
            return ('neg', self.unary())
        return self.primary()

    def primary(self):
        t = self.cur()
        if t[0] == 'NUM':   self.eat('NUM');   return ('num',  t[1])
        if t[0] == 'STR':   self.eat('STR');   return ('str',  t[1])
        if t[0] == 'TRUE':  self.eat('TRUE');  return ('bool', True)
        if t[0] == 'FALSE': self.eat('FALSE'); return ('bool', False)
        if t[0] == 'ID':    self.eat('ID');    return ('var',  t[1])
        if t[0] == '(':
            self.eat('(')
            e = self.expr()
            self.eat(')')
            return e
        raise SyntaxError(f"line {t[2]}: expected value, got {t[0]!r}")


# ── Evaluator ─────────────────────────────────────────────────────────────────

class FluxError(Exception):
    pass


def ev(node, env):
    k = node[0]
    if k == 'num':  return node[1]
    if k == 'str':  return node[1]
    if k == 'bool': return node[1]
    if k == 'var':
        name = node[1]
        if name not in env['v']:
            raise FluxError(f"undefined variable '{name}'")
        return env['v'][name]
    if k == 'neg':  return -ev(node[1], env)
    if k == 'not':  return not ev(node[1], env)
    if k == 'and':  return bool(ev(node[1], env)) and bool(ev(node[2], env))
    if k == 'or':   return bool(ev(node[1], env)) or  bool(ev(node[2], env))
    if k == 'cmp':
        a, b = ev(node[2], env), ev(node[3], env)
        return {
            '==': a == b, '!=': a != b,
            '<':  a < b,  '>':  a > b,
            '<=': a <= b, '>=': a >= b,
        }[node[1]]
    if k == 'bin':
        a, b = ev(node[2], env), ev(node[3], env)
        op = node[1]
        if op == '+': return a + b          # also works for string concat
        if op == '-': return a - b
        if op == '*': return a * b
        if op == '/':
            if b == 0:
                raise FluxError("division by zero")
            return a / b if (isinstance(a, float) or isinstance(b, float)) else a // b
        if op == '%':
            if b == 0:
                raise FluxError("modulo by zero")
            return a % b
    raise FluxError(f"unknown expression node {k!r}")


def fmt(v):
    """Format a value for PRINT."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


# ── Interpreter ───────────────────────────────────────────────────────────────

def new_env():
    return {'v': {}, 'a': {}}   # v = variables, a = anchors


def run_block(stmts, env, fired):
    """
    Execute a list of statements.

    env   — dict with 'v' (variables) and 'a' (anchors)
    fired — set of statement object ids already consumed by REWIND
    """
    history = []   # history[k] = deep copy of env['v'] BEFORE stmts[k] ran
    i = 0

    while i < len(stmts):
        s = stmts[i]
        k = s[0]

        # Snapshot state before executing this step
        history.append(copy.deepcopy(env['v']))

        # ── REWIND n ──────────────────────────────────────────────────────
        if k == 'rewind':
            sid = id(s)
            if sid in fired:
                i += 1          # already fired in a previous pass, skip it
                continue
            fired.add(sid)
            n = int(ev(s[1], env))
            target = max(0, i - n)
            env['v'] = copy.deepcopy(history[target])   # undo state
            history = history[:target]                  # trim history
            i = target                                  # jump back
            continue

        # ── REWIND TO name ────────────────────────────────────────────────
        if k == 'rewind_to':
            name = s[1]
            if name not in env['a']:
                raise FluxError(f"unknown anchor '{name}'")
            env['v'] = copy.deepcopy(env['a'][name])
            i += 1
            continue

        # ── ANCHOR name ───────────────────────────────────────────────────
        if k == 'anchor':
            env['a'][s[1]] = copy.deepcopy(env['v'])
            i += 1
            continue

        # ── ASSIGN ────────────────────────────────────────────────────────
        if k == 'assign':
            env['v'][s[1]] = ev(s[2], env)
            i += 1
            continue

        # ── PRINT ─────────────────────────────────────────────────────────
        if k == 'print':
            print(fmt(ev(s[1], env)))
            i += 1
            continue

        # ── INPUT ─────────────────────────────────────────────────────────
        if k == 'input':
            raw = input().strip()
            try:
                env['v'][s[1]] = int(raw)
            except ValueError:
                try:
                    env['v'][s[1]] = float(raw)
                except ValueError:
                    env['v'][s[1]] = raw
            i += 1
            continue

        # ── ROLL lo hi var ────────────────────────────────────────────────
        if k == 'roll':
            lo = int(ev(s[1], env))
            hi = int(ev(s[2], env))
            env['v'][s[3]] = random.randint(lo, hi)
            i += 1
            continue

        # ── IF ────────────────────────────────────────────────────────────
        if k == 'if':
            branch = s[2] if ev(s[1], env) else s[3]
            run_block(branch, env, fired)
            i += 1
            continue

        # ── LOOP ──────────────────────────────────────────────────────────
        if k == 'loop':
            for _ in range(int(ev(s[1], env))):
                run_block(s[2], env, fired)
            i += 1
            continue

        # ── WHILE ─────────────────────────────────────────────────────────
        if k == 'while':
            while ev(s[1], env):
                run_block(s[2], env, fired)
            i += 1
            continue

        # ── BRANCH / MERGE ────────────────────────────────────────────────
        if k == 'branch':
            _, branches, strat, var = s
            results = []
            for body in branches:
                u = {'v': copy.deepcopy(env['v']), 'a': copy.deepcopy(env['a'])}
                try:
                    run_block(body, u, set())   # each branch gets its own fired set
                    results.append(u)
                except FluxError:
                    if strat != 'first':
                        raise
            if not results:
                raise FluxError("all branches collapsed — no universe survived")
            if strat == 'first':
                winner = results[0]
            elif strat == 'max':
                winner = max(
                    results,
                    key=lambda u: u['v'].get(var, float('-inf'))
                )
            elif strat == 'min':
                winner = min(
                    results,
                    key=lambda u: u['v'].get(var, float('inf'))
                )
            env['v'].update(winner['v'])
            env['a'].update(winner['a'])
            i += 1
            continue

        raise FluxError(f"unknown statement kind {k!r}")


def run(src):
    toks = tokenize(src)
    ast  = Parser(toks).parse()
    env  = new_env()
    run_block(ast, env, set())


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    try:
        run(open(sys.argv[1]).read())
    except (FluxError, SyntaxError) as e:
        print(f"flux error: {e}", file=sys.stderr)
        sys.exit(1)
