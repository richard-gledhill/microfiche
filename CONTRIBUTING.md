# Contributing to `microfiche`

Contributions are welcome, and greatly appreciated! Every little bit helps, and credit will
always be given.

## Types of Contributions

### Report Bugs

Report bugs at [github.com/richard-gledhill/microfiche/issues](https://github.com/richard-gledhill/microfiche/issues).

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged `bug` and `help wanted` is open to
whoever wants to implement a fix for it.

### Implement Features

Look through the GitHub issues for features. Anything tagged `enhancement` and `help wanted`
is open to whoever wants to implement it.

### Write Documentation

microfiche could always use more documentation, whether as part of the official docs, in
docstrings, or on the web in blog posts and articles.

### Submit Feedback

The best way to send feedback is to [file an issue](https://github.com/richard-gledhill/microfiche/issues).

If you are proposing a new feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that contributions are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `microfiche` for local development. This assumes
you already have `uv` and `Git` installed.

microfiche is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) with
two packages — code lives under `packages/core/src/core/` and `packages/cli/src/cli/`, and
tests mirror that layout under `tests/core/` and `tests/cli/`. See
[docs/development/architecture.md](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/architecture.md)
for the architecture behind it.

Docstrings follow [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
(`Args:`, `Returns:`, `Raises:` sections) — `mkdocstrings` renders them accordingly, so keep
new docstrings consistent with that convention.

1. Fork the `microfiche` repo on GitHub.

2. Clone your fork locally and set up the environment:

   ```bash
   git clone git@github.com:YOUR_NAME/microfiche.git
   cd microfiche
   make install
   ```

   This runs `uv sync` across the workspace and installs the pre-commit hooks.

3. Create a branch for local development, named `<type>/<short-description>` — `<type>` is a
   Conventional Commits type (`feat` or `feature`, `fix`, `chore`, `docs`, `style`, `refactor`,
   `perf`, `test`, `build`, `ci`, `revert`). A CI check validates this on every PR — it's
   advisory only for now and won't block a merge, but please follow it anyway:

   ```bash
   git checkout -b feature/name-of-your-feature
   ```

4. Make your changes. Add tests under `tests/core/` or `tests/cli/`, matching the module
   you changed.

5. Check that your changes pass formatting, linting, and type checks:

   ```bash
   make check
   ```

6. Run the test suite:

   ```bash
   make test
   ```

7. Commit your changes and push your branch to GitHub:

   ```bash
   git add .
   git commit -m "Your detailed description of your changes."
   git push origin feature/name-of-your-feature
   ```

8. Submit a pull request through the GitHub website. CI runs the same checks (`ruff`, `mypy`,
   `pytest`) across Python 3.11–3.14 automatically, plus the branch-naming check from step 3.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, update the docs — add a docstring, and note the
   feature in `README.md` if it's user-facing.
3. The branch name follows the `<type>/<short-description>` convention from step 3 above.
