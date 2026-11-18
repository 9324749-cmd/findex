"""Boolean retrieval with two-pointer merge and set-based engines."""
from __future__ import annotations

import argparse
import re
import time
import tracemalloc
from pathlib import Path

from findex.models import IndexData, Posting
from findex.store import load_index

_TOKEN = re.compile(r"\(|\)|[^\s()]+")


def _doc_ids(index: IndexData, term: str) -> list[int]:
    return [posting.doc_id for posting in index.postings.get(term.casefold(), [])]


def merge_and(left: list[int], right: list[int]) -> list[int]:
    """Intersection of two sorted ID lists in O(n + m)."""
    i = j = 0
    result: list[int] = []
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            result.append(left[i])
            i += 1
            j += 1
        elif left[i] < right[j]:
            i += 1
        else:
            j += 1
    return result


def merge_or(left: list[int], right: list[int]) -> list[int]:
    """Union of two sorted ID lists without duplicates."""
    i = j = 0
    result: list[int] = []
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            result.append(left[i])
            i += 1
            j += 1
        elif left[i] < right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def _prepare_tokens(query: str) -> list[str]:
    raw = _TOKEN.findall(query)
    tokens: list[str] = []
    for token in raw:
        upper = token.upper()
        token = upper if upper in {"AND", "OR", "NOT"} or token in {"(", ")"} else token.casefold()
        if tokens:
            prev = tokens[-1]
            # Adjacent terms, and term/parenthesis boundaries, imply AND.
            prev_ends_operand = prev not in {"AND", "OR", "NOT", "("}
            current_starts_operand = token not in {"AND", "OR", ")"}
            if prev_ends_operand and current_starts_operand:
                tokens.append("AND")
            elif prev == ")" and token not in {"AND", "OR", ")"}:
                tokens.append("AND")
            elif prev not in {"AND", "OR", "NOT", "("} and token == "(":
                tokens.append("AND")
        tokens.append(token)
    return tokens


def _to_rpn(query: str) -> list[str]:
    tokens = _prepare_tokens(query)
    output: list[str] = []
    operators: list[str] = []
    precedence = {"OR": 1, "AND": 2, "NOT": 3}
    for token in tokens:
        if token == "(":
            operators.append(token)
        elif token == ")":
            while operators and operators[-1] != "(":
                output.append(operators.pop())
            if not operators:
                raise ValueError("Unmatched closing parenthesis")
            operators.pop()
        elif token in precedence:
            while (operators and operators[-1] in precedence
                   and precedence[operators[-1]] > precedence[token]):
                output.append(operators.pop())
            operators.append(token)
        else:
            output.append(token)
    while operators:
        op = operators.pop()
        if op == "(":
            raise ValueError("Unmatched opening parenthesis")
        output.append(op)
    if not output:
        raise ValueError("Query is empty")
    return output


def search(index: IndexData, query: str, *, engine: str = "merge") -> list[int]:
    """Evaluate terms, implicit/explicit AND, OR, and unary NOT."""
    if engine not in {"merge", "set"}:
        raise ValueError("engine must be 'merge' or 'set'")
    rpn = _to_rpn(query)
    universe = sorted(index.doc_meta)
    stack: list[list[int]] = []

    for token in rpn:
        if token == "NOT":
            if not stack:
                raise ValueError("NOT is missing an operand")
            operand = stack.pop()
            if engine == "set":
                stack.append(sorted(set(universe) - set(operand)))
            else:
                stack.append(merge_and(universe, _complement_sorted(operand, universe)))
        elif token in {"AND", "OR"}:
            if len(stack) < 2:
                raise ValueError(f"{token} is missing an operand")
            right, left = stack.pop(), stack.pop()
            if engine == "set":
                a, b = set(left), set(right)
                stack.append(sorted(a & b if token == "AND" else a | b))
            else:
                stack.append(merge_and(left, right) if token == "AND" else merge_or(left, right))
        else:
            stack.append(_doc_ids(index, token))

    if len(stack) != 1:
        raise ValueError("Invalid Boolean query")
    return stack[0]


def _complement_sorted(values: list[int], universe: list[int]) -> list[int]:
    excluded = set(values)
    return [item for item in universe if item not in excluded]


def common_and_rare_terms(index: IndexData) -> tuple[list[str], list[str]]:
    ranked = sorted(index.postings, key=lambda term: (-len(index.postings[term]), term))
    common = ranked[:2]
    rare = sorted(index.postings, key=lambda term: (len(index.postings[term]), term))[:2]
    return common, rare


def benchmark_engines(index: IndexData, repeats: int = 30) -> list[dict[str, object]]:
    common, rare = common_and_rare_terms(index)
    pairs = []
    if len(common) == 2:
        pairs.append(("common", common))
    if len(rare) == 2:
        pairs.append(("rare", rare))
    results = []
    for label, pair in pairs:
        query = f"{pair[0]} AND {pair[1]}"
        row: dict[str, object] = {"group": label, "query": query}
        for engine in ("merge", "set"):
            start = time.perf_counter()
            answer = []
            for _ in range(repeats):
                answer = search(index, query, engine=engine)
            row[f"{engine}_seconds"] = (time.perf_counter() - start) / repeats
            row[f"{engine}_results"] = len(answer)
        results.append(row)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search a saved findex index.")
    parser.add_argument("index_file")
    parser.add_argument("query")
    parser.add_argument("--engine", choices=("merge", "set"), default="merge")
    args = parser.parse_args()

    tracemalloc.start()
    load_started = time.perf_counter()
    index = load_index(args.index_file)
    load_seconds = time.perf_counter() - load_started
    _, load_peak = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()

    search_started = time.perf_counter()
    found = search(index, args.query, engine=args.engine)
    search_seconds = time.perf_counter() - search_started
    _, total_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Engine: {args.engine}")
    print(f"Query: {args.query}")
    print(f"Load time: {load_seconds:.6f} s")
    print(f"Search time: {search_seconds:.6f} s")
    print(f"Load peak memory: {load_peak / 1024 / 1024:.3f} MiB")
    print(f"Peak memory (load + search): {total_peak / 1024 / 1024:.3f} MiB")
    print(f"Found documents: {len(found)}")
    for doc_id in found[:20]:
        meta = index.doc_meta[doc_id]
        print(f"{doc_id}: {meta.title} ({meta.path})")


if __name__ == "__main__":
    main()
