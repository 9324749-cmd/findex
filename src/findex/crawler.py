"""Asyncio crawler with robots policy, per-host pacing and bounded concurrency."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger("findex.crawl")


@dataclass(slots=True)
class CrawlPage:
    url: str
    status: int
    bytes: int
    elapsed: float
    title: str
    text: str
    links: list[str]
    depth: int

    def json_record(self) -> dict[str, object]:
        return asdict(self)


class _HTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def canonicalize_url(url: str) -> str:
    """Normalize scheme/host, remove fragment, normalize path and query ordering."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        raise ValueError(f"Unsupported URL: {url}")
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    if not path.endswith("/") and not Path(path).suffix:
        path += "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


class RobotsCache:
    """Fetch and cache robots.txt separately for each origin."""
    def __init__(self, client: httpx.AsyncClient, user_agent: str) -> None:
        self.client = client
        self.user_agent = user_agent
        self._rules: dict[str, RobotFileParser] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._rules:
            async with self._locks[origin]:
                if origin not in self._rules:
                    parser = RobotFileParser()
                    robots_url = f"{origin}/robots.txt"
                    try:
                        response = await self.client.get(robots_url, headers={"User-Agent": self.user_agent}, timeout=5)
                        if response.status_code == 200:
                            parser.parse(response.text.splitlines())
                        else:
                            # Missing/unavailable robots file: allow, while respecting crawl pacing.
                            parser.parse(["User-agent: *", "Allow: /"])
                    except (httpx.HTTPError, asyncio.TimeoutError):
                        parser.parse(["User-agent: *", "Disallow: /"])
                    self._rules[origin] = parser
        return self._rules[origin].can_fetch(self.user_agent, url)


class AsyncCrawler:
    def __init__(self, *, concurrency: int = 5, per_host_concurrency: int = 1,
                 delay: float = 0.15, timeout: float = 10.0, max_retries: int = 3,
                 user_agent: str = "findex-student-crawler/1.0 (https://github.com/9324749-cmd/findex)",
                 client: httpx.AsyncClient | None = None, log_path: str | Path = "crawl.log") -> None:
        if concurrency < 1 or per_host_concurrency < 1 or delay < 0:
            raise ValueError("Concurrency must be >=1 and delay must be >=0")
        if not any(token in user_agent.lower() for token in ("http", "mailto:", "@")):
            raise ValueError("User-Agent must include a contact address or URL")
        self.concurrency = concurrency
        self.per_host_concurrency = per_host_concurrency
        self.delay = delay
        self.timeout = timeout
        self.max_retries = min(max_retries, 3)
        self.user_agent = user_agent
        self._external_client = client
        self.log_path = Path(log_path)
        self._global_sem = asyncio.Semaphore(concurrency)
        self._host_sems: defaultdict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(per_host_concurrency))
        self._last_request: dict[str, float] = {}
        self._pace_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._robots: RobotsCache | None = None
        self.active = 0
        self.errors = 0
        self.queue_depth = 0

    async def _pace(self, host: str) -> None:
        async with self._pace_locks[host]:
            now = time.monotonic()
            wait = self.delay - (now - self._last_request.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[host] = time.monotonic()

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(value).timestamp() - time.time()))
            except (TypeError, ValueError, OverflowError):
                return None

    async def fetch(self, url: str, depth: int = 0) -> CrawlPage | None:
        assert self._client is not None
        host = urlsplit(url).netloc
        if self._robots and not await self._robots.allowed(url):
            self._write_log(url, "ROBOTS_DENIED", 0, 0.0)
            return None
        async with self._global_sem, self._host_sems[host]:
            for attempt in range(self.max_retries + 1):
                await self._pace(host)
                started = time.perf_counter()
                self.active += 1
                try:
                    async with asyncio.timeout(self.timeout):
                        response = await self._client.get(url, headers={"User-Agent": self.user_agent}, follow_redirects=False)
                    elapsed = time.perf_counter() - started
                    body = response.content
                    status = response.status_code
                    self._write_log(url, status, len(body), elapsed)
                    if status == 429 or 500 <= status <= 599:
                        if attempt < self.max_retries:
                            retry_after = self._retry_after(response.headers.get("Retry-After"))
                            backoff = min(8.0, 0.4 * (2 ** attempt)) + random.uniform(0, 0.2)
                            await asyncio.sleep(max(backoff, retry_after or 0.0))
                            continue
                        self.errors += 1
                        return None
                    if status >= 400 or 300 <= status < 400:
                        # Redirects are not followed automatically: this prevents leaving the
                        # permitted origin and avoids redirect loops.
                        self.errors += 1
                        return None
                    parser = _HTML()
                    parser.feed(response.text)
                    links = []
                    for href in parser.links:
                        try:
                            candidate = canonicalize_url(urljoin(str(response.url), href))
                        except ValueError:
                            continue
                        if urlsplit(candidate).netloc == host:
                            links.append(candidate)
                    return CrawlPage(url=str(response.url), status=status, bytes=len(body), elapsed=elapsed,
                                     title=" ".join(" ".join(parser.title_parts).split()),
                                     text=" ".join(parser.parts), links=sorted(set(links)), depth=depth)
                except (httpx.TimeoutException, asyncio.TimeoutError):
                    elapsed = time.perf_counter() - started
                    self._write_log(url, "TIMEOUT", 0, elapsed)
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(8.0, 0.4 * (2 ** attempt)) + random.uniform(0, 0.2))
                        continue
                    self.errors += 1
                    return None
                except httpx.HTTPError as exc:
                    self.errors += 1
                    self._write_log(url, f"ERROR:{type(exc).__name__}", 0, time.perf_counter()-started)
                    return None
                finally:
                    self.active -= 1
        return None

    def _write_log(self, url: str, status: object, size: int, elapsed: float) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"url": url, "status": status, "bytes": size, "elapsed": round(elapsed, 6)}, ensure_ascii=False) + "\n")

    async def crawl(self, start_url: str, *, max_pages: int = 200, max_depth: int = 5) -> AsyncIterator[CrawlPage]:
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        start = canonicalize_url(start_url)
        own_client = self._external_client is None
        if own_client:
            self._client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=self.concurrency))
        else:
            self._client = self._external_client
        assert self._client is not None
        self._robots = RobotsCache(self._client, self.user_agent)
        queue: asyncio.Queue[tuple[str, int] | None] = asyncio.Queue()
        output: asyncio.Queue[CrawlPage | None] = asyncio.Queue()
        seen = {start}
        scheduled = 1
        queue.put_nowait((start, 0))

        async def worker() -> None:
            nonlocal scheduled
            while True:
                item = await queue.get()
                self.queue_depth = queue.qsize()
                try:
                    if item is None:
                        return
                    url, depth = item
                    page = await self.fetch(url, depth)
                    if page is not None:
                        await output.put(page)
                        if depth < max_depth:
                            for link in page.links:
                                if scheduled >= max_pages:
                                    break
                                if link not in seen:
                                    seen.add(link)
                                    scheduled += 1
                                    await queue.put((link, depth + 1))
                                    self.queue_depth = queue.qsize()
                finally:
                    queue.task_done()

        async def runner() -> None:
            async with asyncio.TaskGroup() as group:
                workers = [group.create_task(worker()) for _ in range(self.concurrency)]
                await queue.join()
                # Stop idle workers as soon as the bounded frontier is exhausted.
                for task in workers:
                    task.cancel()
            for _ in range(self.concurrency):
                await output.put(None)

        runner_task = asyncio.create_task(runner())
        finished = 0
        try:
            while finished < self.concurrency:
                item = await output.get()
                if item is None:
                    finished += 1
                else:
                    yield item
            await runner_task
        finally:
            if not runner_task.done():
                runner_task.cancel()
                try:
                    await runner_task
                except asyncio.CancelledError:
                    pass
            if own_client:
                await self._client.aclose()


async def crawl_to_jsonl(start_url: str, output_path: str | Path, *, max_pages: int = 200,
                         concurrency: int = 5, user_agent: str = "findex-student-crawler/1.0 (https://github.com/9324749-cmd/findex)",
                         log_path: str | Path = "crawl.log", delay: float = 0.15) -> int:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    crawler = AsyncCrawler(concurrency=concurrency, user_agent=user_agent, log_path=log_path, delay=delay)
    count = 0
    started = time.perf_counter()
    with target.open("w", encoding="utf-8") as stream:
        async for page in crawler.crawl(start_url, max_pages=max_pages):
            stream.write(json.dumps(page.json_record(), ensure_ascii=False) + "\n")
            stream.flush()
            count += 1
            elapsed = max(time.perf_counter() - started, 1e-9)
            print(f"pages={count} rate={count/elapsed:.2f}/s active={crawler.active} errors={crawler.errors}", flush=True)
    return count
