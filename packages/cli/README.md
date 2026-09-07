# cli

The `microfiche` command-line interface, built with [Typer](https://typer.tiangolo.com/) and
[Rich](https://rich.readthedocs.io/).

This package is part of the [microfiche](../../README.md) uv workspace and isn't published or
used standalone — see the [root README](../../README.md) for installation, usage, and
configuration, and [CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.

## Contents

| Module | Purpose |
|---|---|
| `app.py` | The Typer application; registers every command. |
| `commands.py` | Command implementations: `sort`, `review`, `propose-categories`, `resort`, `index`, `audit`, `rollback`. |
| `display.py` | Rich rendering helpers for CLI output. |
| `review.py` | Interactive review-queue workflow (not yet implemented). |

This package depends on [`core`](../core) for all scanning, classification, and filing logic —
it is presentation and command orchestration only.

## Development

From the repo root:

```bash
make install
uv run microfiche --help
```

Tests for this package live in [tests/cli/](../../tests/cli).

## License

Distributed under the MIT license, as part of the microfiche project. See
[LICENSE](../../LICENSE).
