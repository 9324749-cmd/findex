"""Сумісний допоміжний CLI для побудови індексу."""
import argparse
import logging
from .index import build_index, save_index

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", nargs="?", default="data/")
    parser.add_argument("--out", default="index.bin")
    parser.add_argument("--format", choices=["pickle", "json"], default="pickle")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    index = build_index(args.corpus)
    save_index(index, args.out, args.format)
    logging.info("Побудовано індекс: %s", index)

if __name__ == "__main__":
    main()
