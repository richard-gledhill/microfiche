# Coding Standards

- Docstrings: Google style (`Args:`/`Returns:`/`Raises:`) — `mkdocstrings` renders them for the
  published docs.
- `ruff` config lives entirely in the root `pyproject.toml`; per-package `pyproject.toml` files
  carry only that package's own dependencies, not tool config.
- mypy is strict (`disallow_untyped_defs`, `warn_return_any`, etc.) and runs from the repo root
  against both `packages/*/src` trees at once.
- User docs track the CLI: any change to a command, an option, or a command's status in
  `docs/development/requirements/mvp-roadmap.md` must also update
  [docs/how-to-use.md](../docs/how-to-use.md) (the command in both its Bash and PowerShell tabs,
  plus its "Current limitations" list) and the Usage section of [README.md](../README.md#usage).
