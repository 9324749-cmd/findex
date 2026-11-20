"""Reproducible 200-page benchmark against an in-process local mirror (no live network)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import tempfile
import time
from pathlib import Path

import httpx
import psutil

from findex.crawler import AsyncCrawler


class LocalMirror(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.004)  # deterministic simulated network latency
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n", request=request)
        if path == "/":
            links = "".join(f'<a href="/page/{i}/">page {i}</a>' for i in range(1, 200))
            return httpx.Response(200, text=f"<title>Local mirror</title><main>asyncio crawler benchmark {links}</main>", request=request)
        return httpx.Response(200, text=f"<title>{path}</title><main>asyncio concurrent crawler page index search</main>", request=request)


async def one_run(concurrency: int, repeats: int, log: Path) -> tuple[float, float, int, float]:
    wall_values: list[float] = []
    rss_peak = 0
    errors = 0
    process = psutil.Process(os.getpid())
    for repeat in range(repeats):
        transport = LocalMirror()
        client = httpx.AsyncClient(transport=transport)
        crawler = AsyncCrawler(concurrency=concurrency, per_host_concurrency=concurrency,
                               delay=0, client=client,
                               user_agent="findex-benchmark/1.0 (+https://github.com/9324749-cmd/findex)",
                               log_path=log)
        count = 0
        started = time.perf_counter()
        async for _page in crawler.crawl("http://local-mirror.test/", max_pages=200):
            count += 1
            rss_peak = max(rss_peak, process.memory_info().rss)
        wall_values.append(time.perf_counter() - started)
        errors += crawler.errors
        await client.aclose()
        if count != 200:
            raise RuntimeError(f"Expected 200 pages, received {count}")
    wall = sorted(wall_values)[len(wall_values)//2]
    return wall, 200 / wall, errors, rss_peak / (1024 * 1024)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("crawler_benchmark.csv"))
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as temp:
        for concurrency in (1, 5, 20):
            wall, rate, errors, rss = await one_run(concurrency, args.repeats, Path(temp) / f"crawl-{concurrency}.log")
            rows.append({"concurrency": concurrency, "pages": 200, "wall_seconds_median": round(wall, 4),
                         "pages_per_second": round(rate, 2), "errors": errors, "peak_rss_mb": round(rss, 2)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print("| Concurrency | Pages | Wall time, s | Pages/s | Errors | Peak RSS, MB |")
    print("|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        print(f"| {row['concurrency']} | 200 | {row['wall_seconds_median']:.4f} | {row['pages_per_second']:.2f} | {row['errors']} | {row['peak_rss_mb']:.2f} |")


if __name__ == "__main__":
    asyncio.run(main())
