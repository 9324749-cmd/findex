from pathlib import Path

OUT = Path("data")
OUT.mkdir(exist_ok=True)
samples = [
    "Python використовує словники для швидкого пошуку даних.",
    "Інвертований індекс пов'язує кожен термін із документами.",
    "Generators process documents lazily and reduce temporary memory.",
    "Hash tables use hash values to find keys efficiently.",
    "Boolean search supports AND OR and NOT operations.",
    "Текстова обробка починається з нормалізації та токенізації.",
    "A document contains words, terms, and useful metadata.",
    "Пошукова система знаходить документи за ключовими словами.",
]
for i in range(1, 1001):
    text = samples[(i - 1) % len(samples)]
    # Повторення в детермінованому порядку відтворює корпус лабораторних №1–2.
    (OUT / f"doc_{i:04d}.txt").write_text(
        f"Документ {i}. {text} {samples[i % len(samples)]}\n",
        encoding="utf-8",
    )

print(f"Створено {len(list(OUT.glob('*.txt')))} документів у {OUT}/")
