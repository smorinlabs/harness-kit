default: all

fmt:
    uv run ruff format .

lint:
    uv run ruff check .

typecheck:
    uv run ty check

test:
    uv run pytest

all: fmt lint typecheck test
