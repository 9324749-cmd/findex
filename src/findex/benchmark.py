"""Обчислює precision@5 для TF-IDF та BM25 за ручною розміткою."""
import argparse
import csv
from pathlib import Path
from .index import open_index
from .ranking import search, BM25, TfIdf


def evaluate(index, rows):
    output = []
    for row in rows:
        raw_relevant = row["relevant_ids"].strip()
        if not raw_relevant:
            continue  # порожнє поле означає, що запит ще не оцінено
        relevant = set() if raw_relevant == "-" else {x.strip() for x in raw_relevant.split(";") if x.strip()}
        for name, scorer in (("TF-IDF", TfIdf()), ("BM25", BM25())):
            results = search(index, row["query"], scorer=scorer, k=5)
            hits = sum(r.doc_id in relevant for r in results)
            output.append({"query": row["query"], "scorer": name, "hits": hits, "precision_at_5": hits / 5})
    return output


def update_readme(results, readme_path="README.md"):
    """Оновлює підсумкову таблицю P@5 після фактичного запуску."""
    path = Path(readme_path)
    if not path.exists() or not results:
        return False
    averages = {}
    for scorer in ("TF-IDF", "BM25"):
        values = [r["precision_at_5"] for r in results if r["scorer"] == scorer]
        if values:
            averages[scorer] = sum(values) / len(values)
    if len(averages) != 2:
        return False
    rows_by_query = {}
    for row in results:
        rows_by_query.setdefault(row["query"], {})[row["scorer"]] = row["precision_at_5"]
    table_lines = ["| Запит | TF-IDF P@5 | BM25 P@5 |", "|---|---:|---:|"]
    for query, values in rows_by_query.items():
        tfidf = f"{values['TF-IDF']:.3f}" if "TF-IDF" in values else "—"
        bm25 = f"{values['BM25']:.3f}" if "BM25" in values else "—"
        table_lines.append(f"| `{query}` | {tfidf} | {bm25} |")
    table_lines.append(f"| **Середнє** | **{averages['TF-IDF']:.3f}** | **{averages['BM25']:.3f}** |")
    table = "\n".join(table_lines)
    text = path.read_text(encoding="utf-8")
    marker = "<!-- P5_RESULTS_START -->"
    end_marker = "<!-- P5_RESULTS_END -->"
    replacement = f"{marker}\n{table}\n{end_marker}"
    if marker in text and end_marker in text:
        before, rest = text.split(marker, 1)
        _, after = rest.split(end_marker, 1)
        text = before + replacement + after
    else:
        text += "\n\n### Фактичні результати precision@5\n\n" + replacement + "\n"
    path.write_text(text, encoding="utf-8")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("index")
    p.add_argument("--judgments", default="judgments.csv")
    p.add_argument("--out", default="precision_at_5.csv")
    p.add_argument("--readme", default="README.md")
    a = p.parse_args()
    with Path(a.judgments).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with open_index(a.index) as ix:
        results = evaluate(ix, rows)
    with Path(a.out).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query", "scorer", "hits", "precision_at_5"])
        w.writeheader()
        w.writerows(results)
    if not results:
        print("Немає розмічених запитів. Спочатку виконай: uv run python -m findex.judge index.bin")
        return
    for r in results:
        print(f"{r['scorer']:6} P@5={r['precision_at_5']:.2f} | {r['query']}")
    if update_readme(results, a.readme):
        print(f"README оновлено фактичними середніми значеннями P@5: {a.readme}")
    print(f"CSV збережено: {a.out}")


if __name__ == "__main__":
    main()
