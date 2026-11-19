"""CLI ранжованого пошуку (збережено ім'я модуля з лабораторної №2)."""
import argparse, logging
from .index import open_index
from .ranking import search, BM25, TfIdf

def main(argv=None):
    parser = argparse.ArgumentParser(description="Ранжований пошук у findex")
    parser.add_argument("index", help="Шлях до index.bin або index.json")
    parser.add_argument("query", help="Запит: python AND (async OR await)")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--scorer", choices=["bm25", "tfidf"], default="bm25")
    parser.add_argument("--engine", choices=["merge", "set"], default="merge", help="Спосіб Boolean-операцій")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scorer = BM25() if args.scorer == "bm25" else TfIdf()
    with open_index(args.index) as index:
        for result in search(index, args.query, scorer=scorer, k=args.k, engine=args.engine): print(result)
if __name__ == "__main__": main()
