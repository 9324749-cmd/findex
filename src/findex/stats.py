"""Потокова статистика корпусу."""
from collections import Counter
from .corpus import iter_documents
from .tokenize import tokenize

def corpus_stats(root):
    docs = terms = chars = 0; frequencies = Counter()
    for doc in iter_documents(root):
        docs += 1; chars += len(doc.text)
        tokens = list(tokenize(doc.text)); terms += len(tokens); frequencies.update(tokens)
    return {"documents": docs, "terms": terms, "characters": chars, "unique_terms": len(frequencies), "top_terms": frequencies.most_common(10)}
