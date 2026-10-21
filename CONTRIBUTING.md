# Contributing

Issues and reproduction cases are welcome. Code is mirrored from Quarry's internal repository, which is the source of truth; pull requests are reviewed and ported there before the mirror is updated.

Use `uv run pytest`, `uv run mypy --strict src/quarryserp`, and `uv build`.

We intentionally do not commit uv.lock: this library tests resolution across supported Python versions and the declared dependency ranges. CI resolves development dependencies from pyproject.toml for each interpreter. A local lock is disposable and is ignored explicitly.
