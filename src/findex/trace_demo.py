"""Демонструє @timed і повторне звернення до кешу запитів."""
import argparse
import logging
from .index import load_index
from .ranking import search

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", nargs="?", default="index.bin")
    parser.add_argument("--query", default="python AND словники")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    index = load_index(args.index)
    search(index, args.query)
    search(index, args.query)

if __name__ == "__main__":
    main()
