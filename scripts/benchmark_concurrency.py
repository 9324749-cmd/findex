"""Repeatable benchmark for serial, threaded and process-based indexing."""
from __future__ import annotations

import argparse
import csv
import os
import platform
import statistics
import time
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from findex.index import build_partial, merge


def cpu_model() -> str:
    model = platform.processor().strip()
    if model:
        return model
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.lower().startswith(("model name", "hardware")):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.machine() or "невідомо"


def peak_rss_mb() -> float:
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        return value / (1024 if platform.system() == "Linux" else 1024 * 1024)
    except (ImportError, AttributeError):
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except ImportError:
            return float("nan")



class PeakRSSSampler:
    """Sample parent-process RSS during one benchmark cell."""
    def __init__(self) -> None:
        try:
            import psutil
            self._process = psutil.Process()
            self.peak = self._process.memory_info().rss
        except ImportError:
            self._process = None
            self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        if self._process is None:
            return
        while not self._stop.wait(0.01):
            self.peak = max(self.peak, self._process.memory_info().rss)

    def __enter__(self) -> "PeakRSSSampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()
        if self._process is not None:
            self.peak = max(self.peak, self._process.memory_info().rss)

    def megabytes(self) -> float:
        if self._process is not None:
            return self.peak / (1024 * 1024)
        return peak_rss_mb()

def child_cpu_seconds() -> float:
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime + usage.ru_stime
    except (ImportError, AttributeError):
        return 0.0


def one_run(root: Path, executor_name: str, workers: int) -> dict[str, float | str | int]:
    files = sorted(str(p) for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"})
    if not files:
        raise SystemExit(f"У каталозі {root} немає .txt/.md файлів")
    chunk_size = (len(files) + workers - 1) // workers
    chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]
    cpu_start = time.process_time()
    child_start = child_cpu_seconds()
    wall_start = time.perf_counter()
    merge_seconds = 0.0
    with PeakRSSSampler() as rss_sampler:
        if executor_name == "serial":
            partials = [build_partial(files, str(root))]
        else:
            pool_type = ThreadPoolExecutor if executor_name == "threads" else ProcessPoolExecutor
            options = {"mp_context": __import__("multiprocessing").get_context("spawn")} if executor_name == "processes" else {}
            with pool_type(max_workers=workers, **options) as pool:
                futures = [pool.submit(build_partial, chunk, str(root)) for chunk in chunks]
                partials = [future.result() for future in futures]
        merge_start = time.perf_counter()
        result = merge(partials)
        merge_seconds = time.perf_counter() - merge_start
        _ = result.num_docs
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start + child_cpu_seconds() - child_start
    return {
        "executor": executor_name,
        "workers": workers,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "parent_peak_rss_mb": rss_sampler.megabytes(),
        "merge_seconds": merge_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="?", type=Path, default=Path("data"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.csv"))
    parser.add_argument("--plot", type=Path, default=Path("docs/speedup.png"))
    parser.add_argument("--workers", nargs="+", type=int, help="Додаткові кількості воркерів; за замовчуванням 2, 4, 8 та os.cpu_count()")
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("Для звіту потрібно щонайменше три повтори")
    cpu_count = os.cpu_count() or 1
    worker_counts = list(dict.fromkeys([1, *(args.workers or [2, 4, 8, cpu_count])]))
    if any(value < 1 for value in worker_counts):
        parser.error("Кількість воркерів має бути додатною")
    raw: list[dict[str, float | str | int]] = []
    for executor_name in ("serial", "threads", "processes"):
        counts = [1] if executor_name == "serial" else worker_counts
        for workers in counts:
            runs = []
            for repeat in range(args.repeats):
                print(f"{executor_name=} {workers=} повтор {repeat + 1}/{args.repeats}", flush=True)
                runs.append(one_run(args.corpus, executor_name, workers))
            row: dict[str, float | str | int] = {"executor": executor_name, "workers": workers}
            for field in ("wall_seconds", "cpu_seconds", "parent_peak_rss_mb", "merge_seconds"):
                row[field] = statistics.median(float(item[field]) for item in runs)
            raw.append(row)
    baseline = next(float(row["wall_seconds"]) for row in raw if row["executor"] == "serial")
    for row in raw:
        row["speedup"] = baseline / float(row["wall_seconds"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["executor", "workers", "wall_seconds", "cpu_seconds", "parent_peak_rss_mb", "merge_seconds", "speedup"]
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(raw)
    args.plot.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for executor_name in ("threads", "processes"):
        selected = sorted((row for row in raw if row["executor"] == executor_name), key=lambda row: int(row["workers"]))
        ax.plot([int(row["workers"]) for row in selected], [float(row["speedup"]) for row in selected], marker="o", label=executor_name)
    max_workers = max(worker_counts)
    ax.plot([1, max_workers], [1, max_workers], linestyle="--", label="ідеальне лінійне прискорення")
    ax.set_xlabel("Кількість воркерів")
    ax.set_ylabel("Прискорення відносно serial")
    ax.set_title("Масштабування індексації findex")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.plot, dpi=160)
    print(f"Збережено {args.output} та {args.plot}")
    hardware = f"{cpu_model()}; логічних CPU: {cpu_count}"
    readme = Path("README.md")
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        table_lines = ["| Executor | Workers | Wall time, s | CPU time, s | Peak parent RSS, MB | Merge, s | Speedup |", "|---|---:|---:|---:|---:|---:|---:|"]
        for row in raw:
            table_lines.append(
                f"| {row['executor']} | {row['workers']} | {float(row['wall_seconds']):.3f} | "
                f"{float(row['cpu_seconds']):.3f} | {float(row['parent_peak_rss_mb']):.1f} | "
                f"{float(row['merge_seconds']):.4f} | {float(row['speedup']):.2f} |"
            )
        table = "\n".join(table_lines)
        content = content.replace("<!-- BENCHMARK_TABLE_START -->\n<!-- BENCHMARK_TABLE_END -->", f"<!-- BENCHMARK_TABLE_START -->\n{table}\n<!-- BENCHMARK_TABLE_END -->")
        content = content.replace("**Модель процесора та кількість ядер:** буде заповнено скриптом.", f"**Модель процесора та кількість логічних CPU:** {hardware}.")
        readme.write_text(content, encoding="utf-8")
    print(f"CPU: {hardware}")


if __name__ == "__main__":
    main()
