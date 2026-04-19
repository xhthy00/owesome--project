# awesome

An awesome project.

## Setup

```bash
uv sync
```

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=awesome --cov-report=term-missing

# Run ruff
uv run ruff check .
```
