"""Інтерактивна ручна розмітка релевантності для 10 запитів."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
from .index import open_index
from .ranking import BM25, TfIdf, search


def annotate(index_path: str, judgments_path: str = "judgments.csv", k: int = 5) -> None:
    path = Path(judgments_path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("У файлі judgments.csv немає запитів.")

    with open_index(index_path) as index:
        for number, row in enumerate(rows, 1):
            query = row["query"].strip()
            print("\n" + "=" * 72)
            print(f"Запит {number}/{len(rows)}: {query}")
            bm25_results = search(index, query, BM25(), k=k)
            tfidf_results = search(index, query, TfIdf(), k=k)
            # Показуємо об’єднання кандидатів з обох ранжувальників, щоб не оцінювати
            # TF-IDF лише за документами, знайденими BM25.
            candidates = {}
            for label, ranked in (("BM25", bm25_results), ("TF-IDF", tfidf_results)):
                for rank, result in enumerate(ranked, 1):
                    if result.doc_id not in candidates:
                        candidates[result.doc_id] = {"result": result, "sources": []}
                    candidates[result.doc_id]["sources"].append(f"{label}#{rank}")
            results = list(candidates.values())
            if not results:
                print("Немає результатів для цього запиту; P@5 буде 0.")
                row["relevant_ids"] = "-"
                with path.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["query", "relevant_ids"])
                    writer.writeheader()
                    writer.writerows(rows)
                continue
            for i, item in enumerate(results, 1):
                result = item["result"]
                print(f"{i}. {result.doc_id} | {', '.join(item['sources'])} | {result.title}")
                print(f"   {result.snippet}")
            print("\nВведи номери релевантних результатів через кому (наприклад: 1,3,5).")
            print("Enter — серед показаних немає релевантних (P@5 буде 0); s — пропустити запит.")
            while True:
                answer = input("Релевантні номери: ").strip()
                if answer.lower() == "s":
                    selected = None
                    break
                if not answer:
                    selected = []
                    break
                try:
                    numbers = sorted({int(x.strip()) for x in answer.split(",")})
                    if any(n < 1 or n > len(results) for n in numbers):
                        raise ValueError
                    selected = [results[n - 1]["result"].doc_id for n in numbers]
                    break
                except ValueError:
                    print(f"Введи числа від 1 до {len(results)} через кому.")
            if selected is not None:
                row["relevant_ids"] = ";".join(selected) if selected else "-"
            # Зберігаємо після кожного запиту, щоб не втратити вже зроблену розмітку.
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["query", "relevant_ids"])
                writer.writeheader()
                writer.writerows(rows)
    print(f"\nРозмітку збережено у {path}.")
    print("Тепер виконай: uv run python -m findex.benchmark index.bin --judgments judgments.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ручна розмітка релевантності для precision@5")
    parser.add_argument("index", nargs="?", default="index.bin")
    parser.add_argument("--judgments", default="judgments.csv")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    annotate(args.index, args.judgments, args.k)


if __name__ == "__main__":
    main()
