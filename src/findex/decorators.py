"""Декоратор вимірювання часу з коректним збереженням метаданих."""
from functools import wraps
from time import perf_counter
import logging
log = logging.getLogger("findex.timing")

def timed(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = (perf_counter() - start) * 1000
            log.info("[timed] %s: %.3f ms", fn.__name__, elapsed)
    return wrapper
