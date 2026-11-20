"""Show GIL status and a race condition with and without a lock."""
from __future__ import annotations

import sys
import threading
import time


def gil_enabled() -> bool | None:
    probe = getattr(sys, "_is_gil_enabled", None)
    return bool(probe()) if probe is not None else None


def run_counter(use_lock: bool, threads: int = 8, iterations: int = 20_000) -> int:
    counter = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal counter
        for _ in range(iterations):
            if use_lock:
                with lock:
                    counter += 1
            else:
                # Deliberately split read/modify/write to expose a race.
                current = counter
                time.sleep(0)
                counter = current + 1

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    return counter


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"sys._is_gil_enabled(): {gil_enabled()!r} (None означає, що інтерпретатор не має цього API)")
    expected = 8 * 20_000
    raced = run_counter(False)
    protected = run_counter(True)
    print(f"Очікуване значення: {expected}")
    print(f"Без Lock: {raced}")
    print(f"З Lock: {protected}")
    print("Lock робить операцію читання-зміни-запису критичною секцією.")


if __name__ == "__main__":
    main()
