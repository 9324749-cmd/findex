"""Рекурсивний спуск: AST-вузли та Boolean-парсер."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .index import Index
import re
from .tokenize import tokenize

def _merge_sorted(left: set[str], right: set[str], *, union: bool = False) -> set[str]:
    a, b = sorted(left), sorted(right)
    i = j = 0; result = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            result.append(a[i]); i += 1; j += 1
        elif a[i] < b[j]:
            if union: result.append(a[i])
            i += 1
        else:
            if union: result.append(b[j])
            j += 1
    if union:
        result.extend(a[i:]); result.extend(b[j:])
    return set(result)

class QueryNode:
    def __and__(self, other: QueryNode) -> QueryNode: return And(self, other)
    def __or__(self, other: QueryNode) -> QueryNode: return Or(self, other)
    def __invert__(self) -> QueryNode: return Not(self)

@dataclass(frozen=True)
class Term(QueryNode):
    value: str
    def evaluate(self, index: Index, engine: Literal["merge", "set"] = "set") -> set[str]: return {p.doc_id for p in index.get(self.value.casefold(), ())}

@dataclass(frozen=True)
class Phrase(QueryNode):
    value: str
    def evaluate(self, index: Index, engine: Literal["merge", "set"] = "set") -> set[str]:
        terms = list(tokenize(self.value))
        if not terms: return set()
        if len(terms) == 1: return Term(terms[0]).evaluate(index, engine)
        lists = [index.get(t, ()) for t in terms]
        if any(not x for x in lists): return set()
        maps = [{p.doc_id: set(p.positions) for p in postings} for postings in lists]
        common = set(maps[0]).intersection(*(set(m) for m in maps[1:]))
        result = set()
        for doc_id in common:
            starts = maps[0][doc_id]
            if any(all(start+i in maps[i][doc_id] for i in range(1, len(terms))) for start in starts):
                result.add(doc_id)
        return result

@dataclass(frozen=True)
class And(QueryNode):
    left: QueryNode; right: QueryNode
    def evaluate(self, index: Index, engine: Literal["merge", "set"] = "set") -> set[str]:
        left, right = self.left.evaluate(index, engine), self.right.evaluate(index, engine)
        return _merge_sorted(left, right) if engine == "merge" else left & right

@dataclass(frozen=True)
class Or(QueryNode):
    left: QueryNode; right: QueryNode
    def evaluate(self, index: Index, engine: Literal["merge", "set"] = "set") -> set[str]:
        left, right = self.left.evaluate(index, engine), self.right.evaluate(index, engine)
        return _merge_sorted(left, right, union=True) if engine == "merge" else left | right

@dataclass(frozen=True)
class Not(QueryNode):
    child: QueryNode
    def evaluate(self, index: Index, engine: Literal["merge", "set"] = "set") -> set[str]: return set(index.documents) - self.child.evaluate(index, engine)

_TOKEN_RE = re.compile(r'\s*(AND\b|OR\b|NOT\b|\(|\)|"[^"]*"|[^\s()"]+)', re.IGNORECASE)
class QuerySyntaxError(ValueError): pass

class _Parser:
    def __init__(self, source: str):
        self.tokens = [m.group(1) for m in _TOKEN_RE.finditer(source)]
        self.pos = 0
    def peek(self): return self.tokens[self.pos] if self.pos < len(self.tokens) else None
    def take(self):
        token = self.peek()
        if token is None: raise QuerySyntaxError("Неочікуваний кінець запиту")
        self.pos += 1; return token
    def parse(self):
        if not self.tokens: raise QuerySyntaxError("Порожній запит")
        node = self.parse_or()
        if self.peek() is not None: raise QuerySyntaxError(f"Зайвий токен: {self.peek()}")
        return node
    def parse_or(self):
        node = self.parse_and()
        while self.peek() and self.peek().upper() == "OR":
            self.take(); node = Or(node, self.parse_and())
        return node
    def parse_and(self):
        node = self.parse_not()
        while self.peek() is not None and self.peek().upper() not in {"OR", ")"}:
            if self.peek().upper() == "AND": self.take()
            node = And(node, self.parse_not())
        return node
    def parse_not(self):
        if self.peek() and self.peek().upper() == "NOT":
            self.take(); return Not(self.parse_not())
        return self.parse_atom()
    def parse_atom(self):
        token = self.take()
        if token == "(":
            node = self.parse_or()
            if self.take() != ")": raise QuerySyntaxError("Очікувалася закривальна дужка")
            return node
        if token == ")": raise QuerySyntaxError("Зайва закривальна дужка")
        if token.startswith('"') and token.endswith('"'): return Phrase(token[1:-1])
        upper = token.upper()
        if upper in {"AND", "OR", "NOT"}: raise QuerySyntaxError(f"Оператор без операнда: {token}")
        terms = list(tokenize(token))
        if len(terms) != 1: raise QuerySyntaxError(f"Некоректний терм: {token}")
        return Term(terms[0])

def parse(source: str) -> QueryNode:
    return _Parser(source).parse()
