from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from findex.crawler import AsyncCrawler, canonicalize_url
from findex.corpus import iter_documents
from findex.index import build_index


def test_canonicalize_url() -> None:
    assert canonicalize_url("HTTP://EXAMPLE.COM/a#part") == "http://example.com/a/"
    assert canonicalize_url("http://example.com/?b=2&a=1#x") == "http://example.com/?a=1&b=2"
    assert canonicalize_url("https://EXAMPLE.com") == "https://example.com/"


def test_crawl_limit_robots_cache_and_jsonl_index(tmp_path: Path) -> None:
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked/\n")
        if path == "/blocked/":
            return httpx.Response(200, text="must not fetch")
        number = 0 if path == "/" else int(path.strip("/").replace("p", ""))
        links = "".join(f'<a href="/p{i}/">next</a>' for i in range(1, 8)) if number == 0 else ""
        if number == 1:
            links += '<a href="/blocked/">blocked</a>'
        return httpx.Response(200, text=f"<html><title>Page {number}</title><body>async indexing page {number}{links}</body></html>")

    async def run() -> list[dict[str, object]]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = AsyncCrawler(concurrency=3, per_host_concurrency=3, delay=0, client=client,
                               user_agent="findex-tests/1.0 (https://example.test/contact)", log_path=tmp_path / "crawl.log")
        pages = [page async for page in crawler.crawl("HTTP://EXAMPLE.TEST/#start", max_pages=4)]
        await client.aclose()
        return [page.json_record() for page in pages]

    records = asyncio.run(run())
    assert len(records) == 4
    assert all(record["status"] == 200 for record in records)
    assert "/blocked/" not in calls
    assert calls["/robots.txt"] == 1
    output = tmp_path / "crawled.jsonl"
    output.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    docs = list(iter_documents(tmp_path))
    assert len(docs) == 4
    index = build_index(tmp_path)
    assert index.num_docs == 4
    assert "async" in index


def test_retry_429_then_success(tmp_path: Path) -> None:
    counts = {"/": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        counts["/"] += 1
        if counts["/"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, text="<title>Recovered</title>ok")

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = AsyncCrawler(concurrency=1, delay=0, client=client,
                               user_agent="findex-tests/1.0 (https://example.test/contact)", log_path=tmp_path / "retry.log")
        pages = [page async for page in crawler.crawl("https://retry.test/", max_pages=1)]
        await client.aclose()
        return pages

    pages = asyncio.run(run())
    assert len(pages) == 1
    assert pages[0].title == "Recovered"
    assert counts["/"] == 2
    log = (tmp_path / "retry.log").read_text(encoding="utf-8")
    assert '"status": 429' in log
    assert '"status": 200' in log


def test_non_retryable_404(tmp_path: Path) -> None:
    counts = {"/": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        counts["/"] += 1
        return httpx.Response(404)

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = AsyncCrawler(concurrency=1, delay=0, client=client,
                               user_agent="findex-tests/1.0 (https://example.test/contact)", log_path=tmp_path / "404.log")
        pages = [page async for page in crawler.crawl("https://missing.test/", max_pages=1)]
        await client.aclose()
        return pages

    assert asyncio.run(run()) == []
    assert counts["/"] == 1


def test_robots_disallow_is_respected(tmp_path: Path) -> None:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        if request.url.path == "/":
            return httpx.Response(200, text='<a href="/private/">private</a>')
        return httpx.Response(200, text="should not be fetched")

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        crawler = AsyncCrawler(concurrency=1, delay=0, client=client,
                               user_agent="findex-tests/1.0 (https://example.test/contact)", log_path=tmp_path / "robots.log")
        pages = [page async for page in crawler.crawl("https://robots.test/", max_pages=2)]
        await client.aclose()
        return pages

    pages = asyncio.run(run())
    assert len(pages) == 1
    assert "/private/" not in fetched
    assert fetched.count("/robots.txt") == 1
