"""Просте вимірювання побудови індексу через tracemalloc."""
import argparse, tracemalloc
from .index import build_index

def main():
    p=argparse.ArgumentParser(); p.add_argument("corpus", nargs="?", default="data/"); a=p.parse_args()
    tracemalloc.start(); ix=build_index(a.corpus); current, peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    print(f"Документів: {ix.num_docs}; термів: {len(ix)}; peak memory: {peak:,} bytes")
if __name__ == "__main__": main()
