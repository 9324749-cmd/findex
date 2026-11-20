# findex — лабораторна робота №4

Навчальна пошукова система: читання корпусу, інвертований індекс, Boolean-запити, TF-IDF/BM25, CLI.

[![CI](https://github.com/9324749-cmd/findex/actions/workflows/ci.yml/badge.svg)](https://github.com/9324749-cmd/findex/actions/workflows/ci.yml)

## Встановлення

Потрібен Python 3.11+ та [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
uv run findex --help
```

Встановлення як окремого інструмента з каталогу репозиторію:

```bash
uv tool install .
findex --help
```

## Команди

```bash
findex index data --out index.bin
findex search "python AND async" --index index.bin --scorer bm25 --engine merge
findex search "python OR async" --index index.bin --json > results.json
findex stats --index index.bin
```

`-v` показує інформаційні повідомлення, `-vv` — докладніші діагностичні повідомлення. Діагностика спрямовується в stderr; JSON-результат команди `search --json` — у stdout.

## Тестування та якість

```bash
uv run pytest --cov=findex --cov-report=term-missing
uv run ruff check src tests
uv run pyright
```

Набір містить 62 тестові випадки після розгортання параметризації (pytest collection): токенізатор і Unicode, парсер та AST, побудова індексу, merge/set, обидва скорери, серіалізація, CLI та три Hypothesis-властивості (round-trip, впорядкування posting-ів і Boolean merge).

**Покриття:** точний відсоток потрібно отримати локальним запуском команди вище; він навмисно не підставлений наперед, щоб не видавати неперевірене число за результат. Поза покриттям залишаються інтеграція з великими зовнішніми корпусами, продуктивність на промислових обсягах і поведінка на пошкоджених/недовірених pickle-файлах.

## Дані та безпека

Каталог `data/` містить навчальний корпус. Не відкривайте pickle-файли з невідомих джерел: формат pickle може виконувати код під час завантаження.

## Реліз

Після локального проходження всіх перевірок створіть тег `lab-04` та реліз `v0.4.0`. Wheel можна зібрати так:

```bash
uv build
```

Файл `dist/*.whl` потрібно прикріпити до GitHub Release вручну або через інструмент релізів GitHub.
