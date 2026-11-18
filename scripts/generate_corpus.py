"""Create a reproducible local demonstration corpus (not committed to Git)."""

from pathlib import Path

ROOT = Path("data")
PARAGRAPHS = [
    "Python підтримує ітератори, генератори та послідовну обробку текстових даних.",
    "Пошукова система аналізує документи, виділяє терми та зберігає статистику.",
    "Unicode-нормалізація допомагає порівнювати текст із різними способами кодування.",
    "Генератор повертає наступний елемент лише тоді, коли його запитує споживач.",
    "Модуль pathlib забезпечує зручну роботу з файлами та каталогами.",
    "Регулярні вирази дають змогу знаходити слова, числа та інші текстові шаблони.",
    "Лінивий конвеєр зменшує потребу зберігати всі проміжні результати в пам'яті.",
    "Лічильник термів накопичує частоти слів для подальшого пошуку й ранжування.",
    "Тестування перевіряє правила токенізації на українських та англійських прикладах.",
    "Вимірювання часу й пам'яті допомагає порівнювати різні реалізації алгоритму.",
]


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    count = 1000
    for index in range(1, count + 1):
        # Deterministic variety: each document contains a different rotation.
        lines = [f"Документ {index}. Навчальний корпус findex."]
        for offset in range(len(PARAGRAPHS)):
            lines.append(PARAGRAPHS[(index + offset) % len(PARAGRAPHS)])
        (ROOT / f"document_{index:04d}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    print(f"Created {count} UTF-8 text documents in {ROOT}/")


if __name__ == "__main__":
    main()
