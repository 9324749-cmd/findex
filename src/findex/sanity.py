"""Три перевірки BM25 на реальному індексі корпусу."""
from .index import open_index
from .ranking import BM25

def run_checks(index):
    scorer = BM25()
    print("SANITY CHECK 1 — рідкісний терм має перевагу над частим")
    stopwords = {"and", "the", "a", "is", "to", "of", "in", "for", "on", "і", "й", "та", "в", "у", "до", "з", "із", "що", "це"}
    candidates = [t for t in index if t not in stopwords and not t.isdigit()]
    rare = min(candidates, key=lambda t: index.df(t), default=None)
    common = max(candidates, key=lambda t: index.df(t), default=None)
    if rare and common and rare != common:
        rare_posting = index[rare][0]
        rare_doc_ids = {p.doc_id for p in index[rare]}
        common_posting = next((p for p in index[common] if p.doc_id not in rare_doc_ids), None)
        if common_posting:
            rare_score = scorer(rare, rare_posting, index)
            common_score = scorer(common, common_posting, index)
            print(f"rare={rare!r} (df={index.df(rare)}): {rare_posting.doc_id}, score={rare_score:.4f}")
            print(f"common={common!r} (df={index.df(common)}): {common_posting.doc_id}, score={common_score:.4f}")
            print(f"Рідкісний терм вище: {rare_score > common_score}")
        else:
            print("Не знайдено документа з частим термом без рідкісного терма.")
    else:
        print("У корпусі не знайдено термів із різною документною частотою для порівняння.")

    print("SANITY CHECK 2 — 20-те повторення додає значно менше за перше")
    def tf_component(tf):
        return (tf * (scorer.k1 + 1)) / (tf + scorer.k1)
    first = tf_component(1) - tf_component(0)
    twentieth = tf_component(20) - tf_component(19)
    print(f"Перше входження: {first:.6f}; 20-те входження: {twentieth:.6f}; умова виконана: {twentieth < first}")

    print("SANITY CHECK 3 — короткий документ має перевагу над довгим")
    pairs = []
    for term in index:
        if term in stopwords:
            continue
        one_each = [p for p in index[term] if p.tf == 1]
        if len(one_each) >= 2:
            short = min(one_each, key=lambda p: index.doc_length(p.doc_id))
            long = max(one_each, key=lambda p: index.doc_length(p.doc_id))
            if short.doc_id != long.doc_id:
                difference = index.doc_length(long.doc_id) - index.doc_length(short.doc_id)
                pairs.append((difference, term, short, long))
    if pairs:
        _, term, short, long = max(pairs, key=lambda item: item[0])
        short_score, long_score = scorer(term, short, index), scorer(term, long, index)
        print(f"Терм {term!r}: короткий {short.doc_id} ({index.doc_length(short.doc_id)} токенів), score={short_score:.8f}")
        print(f"Довгий {long.doc_id} ({index.doc_length(long.doc_id)} токенів), score={long_score:.8f}")
        print(f"Короткий документ вище: {short_score > long_score}")
    else:
        print("Не знайдено двох документів з однаковим термом, який трапляється рівно один раз у кожному.")

def main():
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("index", nargs="?", default="index.bin"); args=parser.parse_args()
    with open_index(args.index) as index: run_checks(index)
if __name__ == "__main__": main()
