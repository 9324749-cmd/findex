"""Командний інтерфейс findex."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from .index import build_index, load_index, save_index
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
