"""Командний інтерфейс findex."""
from __future__ import annotations

import json
import asyncio
import time
import logging
from pathlib import Path
from typing import Annotated, Literal

import typer
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.live import Live

from .index import build_index, load_index, save_index
from .crawler import AsyncCrawler
from .query import QuerySyntaxError
from .ranking import BM25, TfIdf, search

app = typer.Typer(no_args_is_help=True, help="Локальна пошукова система findex")
console = Console(stderr=True)


def configure_logging(verbose: int) -> None:
    """Налаштовує діагностичний логер один раз у точці входу CLI."""
    level = logging.WARNING if verbose == 0 else logging.INFO if verbose == 1 else logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", stream=__import__("sys").stderr, force=True)


@app.callback()
def main(
    verbose: Annotated[int, typer.Option("-v", "--verbose", count=True, is_flag=True, help="Збільшити деталізацію логів")]=0,
) -> None:
    configure_logging(verbose)


@app.command("index")
def index_command(
    corpus: Annotated[Path, typer.Argument(help="Каталог із .txt/.md документами")]=Path("data"),
    output: Annotated[Path, typer.Option("--out", "-o", help="Файл індексу")]=Path("index.bin"),
    fmt: Annotated[Literal["pickle", "json"], typer.Option("--format", help="pickle або json")]= "pickle",
    workers: Annotated[int, typer.Option("--workers", min=1, help="Кількість воркерів")]=1,
    executor: Annotated[Literal["serial", "threads", "processes"], typer.Option("--executor", help="serial, threads або processes")]= "serial",
) -> None:
    """Створити та зберегти інвертований індекс."""
    try:
        if not corpus.exists():
            raise FileNotFoundError(f"Корпус не знайдено: {corpus}")
        with Progress(SpinnerColumn(), TextColumn("Індексація…"), BarColumn(), TimeElapsedColumn(), console=console) as progress:
            task = progress.add_task("index", total=None)
            index = build_index(corpus, workers=workers, executor=executor)
            progress.update(task, completed=1, total=1)
        save_index(index, output, fmt)
        console.print(f"[green]Готово:[/green] {index}; виконавець: {executor}; воркерів: {workers}; файл: {output}")
    except (OSError, ValueError) as exc:
        typer.echo(f"Помилка: {exc}", err=True)
        raise typer.Exit(code=1) from None



@app.command("crawl")
def crawl_command(
    start_url: Annotated[str, typer.Argument(help="Початкова URL-адреса дозволеного сайту")],
    output: Annotated[Path, typer.Option("--out", "-o", help="JSONL файл сторінок")]=Path("data/crawled.jsonl"),
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, help="Жорстка межа сторінок")]=200,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, help="Одночасні мережеві запити")]=5,
    per_host_concurrency: Annotated[int, typer.Option("--per-host-concurrency", min=1, help="Одночасні запити до одного хоста")]=2,
    delay: Annotated[float, typer.Option("--delay", min=0, help="Мінімальна пауза для одного хоста")]=0.15,
    user_agent: Annotated[str, typer.Option("--user-agent", help="Чесний User-Agent з URL або контактом") ]="findex-student-crawler/1.0 (+https://github.com/9324749-cmd/findex)",
    log_path: Annotated[Path, typer.Option("--log", help="Лог усіх URL")]=Path("crawl.log"),
) -> None:
    """Асинхронно обійти дозволений сайт і записати сторінки у JSONL."""
    async def run() -> int:
        crawler = AsyncCrawler(concurrency=concurrency, per_host_concurrency=per_host_concurrency, delay=delay, user_agent=user_agent, log_path=log_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        started = time.perf_counter()
        with output.open("w", encoding="utf-8") as stream, Live(console=console, refresh_per_second=8) as live:
            async for page in crawler.crawl(start_url, max_pages=max_pages):
                stream.write(json.dumps(page.json_record(), ensure_ascii=False) + "\n")
                stream.flush()
                count += 1
                elapsed = max(time.perf_counter() - started, 1e-9)
                panel = Table(title="findex async crawler")
                panel.add_column("Показник")
                panel.add_column("Значення", justify="right")
                panel.add_row("Зібрано сторінок", str(count))
                panel.add_row("Швидкість", f"{count/elapsed:.2f} стор./с")
                panel.add_row("Активні запити", str(crawler.active))
                panel.add_row("Помилки", str(crawler.errors))
                panel.add_row("Глибина черги", str(crawler.queue_depth))
                live.update(panel)
        return count
    try:
        count = asyncio.run(run())
        console.print(f"[green]Краулер завершив роботу:[/green] {count} сторінок → {output}; лог: {log_path}")
    except (OSError, ValueError, httpx.HTTPError) as exc:
        typer.echo(f"Помилка краулера: {exc}", err=True)
        raise typer.Exit(code=1) from None

@app.command("search")
def search_command(
    query: Annotated[str, typer.Argument(help="Boolean-запит, наприклад python AND async")],
    index_path: Annotated[Path, typer.Option("--index", "-i", help="Файл індексу")]=Path("index.bin"),
    limit: Annotated[int, typer.Option("-k", min=1, max=100)]=10,
    scorer: Annotated[Literal["bm25", "tfidf"], typer.Option("--scorer", help="bm25 або tfidf")]= "bm25",
    engine: Annotated[Literal["merge", "set"], typer.Option("--engine", help="merge або set")]= "merge",
    as_json: Annotated[bool, typer.Option("--json", help="Вивести JSON у stdout")]=False,
) -> None:
    """Виконати ранжований пошук."""
    try:
        if not index_path.exists():
            raise FileNotFoundError(f"Файл індексу не знайдено: {index_path}")
        if scorer not in {"bm25", "tfidf"}:
            raise ValueError("scorer має бути bm25 або tfidf")
        if engine not in {"merge", "set"}:
            raise ValueError("engine має бути merge або set")
        index = load_index(index_path)
        results = search(index, query, BM25() if scorer == "bm25" else TfIdf(), k=limit, engine=engine)
        rows = [{"doc_id": r.doc_id, "title": r.title, "score": r.score, "snippet": r.snippet} for r in results]
        if as_json:
            typer.echo(json.dumps(rows, ensure_ascii=False))
        else:
            table = Table(title=f"Результати пошуку: {query}")
            table.add_column("№", justify="right")
            table.add_column("Документ")
            table.add_column("Оцінка", justify="right")
            table.add_column("Фрагмент")
            for number, row in enumerate(rows, 1):
                table.add_row(str(number), f"{row['title']} ({row['doc_id']})", f"{row['score']:.4f}", str(row['snippet']))
            Console().print(table)
    except (OSError, ValueError, QuerySyntaxError, KeyError) as exc:
        typer.echo(f"Помилка: {exc}", err=True)
        raise typer.Exit(code=1) from None


@app.command("stats")
def stats_command(
    index_path: Annotated[Path, typer.Option("--index", "-i")]=Path("index.bin"),
) -> None:
    """Показати коротку статистику індексу."""
    try:
        index = load_index(index_path)
        table = Table(title="Статистика індексу")
        table.add_column("Показник")
        table.add_column("Значення", justify="right")
        table.add_row("Документів", str(index.num_docs))
        table.add_row("Унікальних термів", str(len(index)))
        table.add_row("Середня довжина", f"{index.avg_doc_length:.2f}")
        Console().print(table)
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"Помилка: {exc}", err=True)
        raise typer.Exit(code=1) from None
