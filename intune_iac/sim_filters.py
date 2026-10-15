"""A bounded filter grammar compiled to an AST and evaluated in three values.

Grammar (operators are case-insensitive, properties come from the semantics profile):

    or      := and ('-or' and)*
    and     := unary ('-and' unary)*
    unary   := '-not' unary | primary
    primary := '(' or ')' | device.<property> <operator> <value>
    value   := "text" | ["text", ...]

Nothing is ever executed: the text is tokenized and parsed by this module only. An operator, a property, a type or a
syntax the profile does not admit yields an expression that evaluates to U with the reason, never a guess. T and F
are known results; U is missing knowledge and is not an observed null (SIMULATOR_MODEL.md section 4).
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .io import digest

T, F, U = 'T', 'F', 'U'
MAX_TEXT = 4096
MAX_DEPTH = 32
MAX_NODES = 256
_STRING_OPS = ('-eq', '-ne', '-contains', '-notcontains', '-startswith', '-in', '-notin')
_VERSION_OPS = ('-eq', '-ne', '-gt', '-ge', '-lt', '-le')
_CANON_OP = {'-notcontains': '-notContains', '-startswith': '-startsWith', '-notin': '-notIn'}
_TOKEN = re.compile(r'\s*(?:(?P<str>"(?:[^"\\]|\\.)*")|(?P<prop>device\.[A-Za-z][A-Za-z0-9]*)|(?P<op>-[A-Za-z]+)'
                    r'|(?P<punct>[()\[\],]))')
_VERSION = re.compile(r'^\d+(\.\d+)*$')


def not3(a):
    return {T: F, F: T, U: U}[a]


def and3(a, b):
    return F if F in (a, b) else (U if U in (a, b) else T)


def or3(a, b):
    return T if T in (a, b) else (U if U in (a, b) else F)


class _Syntax(ValueError):
    pass


@dataclass(frozen=True)
class ParsedFilter:
    ast: object
    reason: str | None
    sha256: str | None


def _tokens(text):
    out, pos = [], 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return out
        match = _TOKEN.match(text, pos)
        if not match or match.end() == pos:
            raise _Syntax('syntax:unrecognized_input')
        kind = match.lastgroup
        raw = match.group(kind)
        out.append((kind, raw.lower() if kind == 'op' else raw))
        pos = match.end()


class _Parser:
    def __init__(self, tokens, profile):
        self.tokens, self.pos, self.profile, self.nodes = tokens, 0, profile, 0
        self.properties = {name.lower(): name for name in profile.filter_properties}

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def node(self, value):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise _Syntax('syntax:too_many_terms')
        return value

    def parse(self):
        if not self.tokens:
            raise _Syntax('syntax:empty')
        tree = self.or_(0)
        if self.pos != len(self.tokens):
            raise _Syntax('syntax:trailing_input')
        return tree

    def or_(self, depth):
        left = self.and_(depth)
        while self.peek() == ('op', '-or'):
            self.take()
            left = self.node(('or', left, self.and_(depth)))
        return left

    def and_(self, depth):
        left = self.unary(depth)
        while self.peek() == ('op', '-and'):
            self.take()
            left = self.node(('and', left, self.unary(depth)))
        return left

    def unary(self, depth):
        if self.peek() == ('op', '-not'):
            self.take()
            return self.node(('not', self.unary(depth + 1)))
        return self.primary(depth)

    def primary(self, depth):
        if depth > MAX_DEPTH:
            raise _Syntax('syntax:too_deep')
        kind, raw = self.take()
        if (kind, raw) == ('punct', '('):
            inner = self.or_(depth + 1)
            if self.take() != ('punct', ')'):
                raise _Syntax('syntax:unbalanced_parenthesis')
            return inner
        if kind != 'prop':
            raise _Syntax('syntax:expected_property')
        name = self.properties.get(raw[len('device.'):].lower())
        if name is None:
            raise _Syntax('unsupported_property:' + raw[len('device.'):])
        op_kind, op = self.take()
        if op_kind != 'op':
            raise _Syntax('syntax:expected_operator')
        allowed = _VERSION_OPS if self.profile.filter_properties[name] == 'version' else _STRING_OPS
        if op not in allowed:
            raise _Syntax('unsupported_operator:' + op)
        op = _CANON_OP.get(op, op)
        return self.node(('cmp', name, op, self.value(op)))

    def value(self, op):
        kind, raw = self.take()
        if op in ('-in', '-notIn'):
            if (kind, raw) != ('punct', '['):
                raise _Syntax('syntax:list_required')
            values = []
            while True:
                k, r = self.take()
                if k != 'str':
                    raise _Syntax('syntax:string_required')
                values.append(_unquote(r))
                k, r = self.take()
                if (k, r) == ('punct', ']'):
                    return tuple(values)
                if (k, r) != ('punct', ','):
                    raise _Syntax('syntax:list_unterminated')
        if kind != 'str':
            raise _Syntax('syntax:string_required')
        return _unquote(raw)


def _unquote(raw):
    return re.sub(r'\\(.)', r'\1', raw[1:-1])


def _listed(node):
    if node[0] == 'cmp':
        return ['cmp', node[1], node[2], list(node[3]) if isinstance(node[3], tuple) else node[3]]
    return [node[0], *[_listed(child) for child in node[1:]]]


def parse_filter(text, profile, presence='known'):
    """Compile an expression; a failure is recorded as a reason and the filter then evaluates to U."""
    if presence != 'known':
        return ParsedFilter(None, 'filter_expression_' + presence, None)
    if type(text) is not str or len(text) > MAX_TEXT:
        return ParsedFilter(None, 'syntax:missing_or_oversized', None)
    try:
        tree = _Parser(_tokens(text), profile).parse()
    except _Syntax as problem:
        return ParsedFilter(None, str(problem), None)
    except RecursionError:
        return ParsedFilter(None, 'syntax:too_deep', None)
    return ParsedFilter(tree, None, digest(_listed(tree)))


def _version(text):
    text = str(text)
    if not _VERSION.match(text):
        return None
    parts = [int(p) for p in text.split('.')]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _compare(op, left, right, kind):
    if kind == 'version':
        a, b = _version(left), _version(right)
        if a is None or b is None:
            return None
        return {'-eq': a == b, '-ne': a != b, '-gt': a > b, '-ge': a >= b, '-lt': a < b, '-le': a <= b}[op]
    a = str(left).casefold()
    if op in ('-in', '-notIn'):
        hit = a in {str(v).casefold() for v in right}
        return hit if op == '-in' else not hit
    b = str(right).casefold()
    return {'-eq': a == b, '-ne': a != b, '-contains': b in a, '-notContains': b not in a, '-startsWith': a.startswith(b)}[op]


def _eval(node, device, profile, reasons):
    kind = node[0]
    if kind == 'not':
        return not3(_eval(node[1], device, profile, reasons))
    if kind in ('and', 'or'):
        left = _eval(node[1], device, profile, reasons)
        right = _eval(node[2], device, profile, reasons)
        return and3(left, right) if kind == 'and' else or3(left, right)
    _, prop, op, wanted = node
    fact = device.properties.get(prop)
    if fact is None:
        reasons.add('property_absent:' + prop)
        return U
    if fact.presence == 'observed_null':
        reasons.add('property_observed_null:' + prop)
        return profile.null_truth.get(op, U)
    if fact.presence != 'known':
        reasons.add(f'property_{fact.presence}:{prop}')
        return U
    outcome = _compare(op, fact.value, wanted, profile.filter_properties[prop])
    if outcome is None:
        reasons.add('version_unparseable:' + prop)
        return U
    return T if outcome else F


def evaluate(parsed, device, profile):
    """Return (T|F|U, reasons) for one device; reasons are sorted codes naming each unknown or null read."""
    if parsed.ast is None:
        return U, (parsed.reason,)
    reasons = set()
    value = _eval(parsed.ast, device, profile, reasons)
    return value, tuple(sorted(reasons))
