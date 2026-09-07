<!--
Best-practices README.md template for a Python project.

How to use:
1. Copy this file to the project root as `README.md`.
2. Fill in every <angle-bracket> placeholder and remove the HTML comments (like this one).
3. Delete any section that doesn't apply (e.g. drop "CLI Usage" for a library-only package).
4. Keep it honest and current - a README that lies about install steps or CLI flags is worse
   than no README. Update it in the same PR as the change it describes.
-->

# <project-name>

[![Release](https://img.shields.io/github/v/release/<owner>/<project-name>)](https://github.com/<owner>/<project-name>/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/<owner>/<project-name>/main.yml?branch=main)](https://github.com/<owner>/<project-name>/actions)
[![codecov](https://codecov.io/gh/<owner>/<project-name>/branch/main/graph/badge.svg)](https://codecov.io/gh/<owner>/<project-name>)
[![License](https://img.shields.io/github/license/<owner>/<project-name>)](LICENSE)

<!-- One or two sentences: what it does and who it's for. This is the elevator pitch - the
     reader decides whether to keep scrolling based on this alone. -->
<one-paragraph description of the project>

- **Documentation**: <https://<owner>.github.io/<project-name>/>
- **Source code**: <https://github.com/<owner>/<project-name>>

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Features

<!-- A short bullet list, not a spec. Three to six bullets is usually right. -->

- <feature one>
- <feature two>
- <feature three>

## Requirements

- Python <minimum version>+
- <any other runtime prerequisite - a database, an external CLI, an API key>

## Installation

```bash
pip install <project-name>
```

<!-- If the project uses uv/poetry/pipx instead of (or alongside) pip, show that too - use
     whichever your users will actually run. Don't list every possible tool "for completeness";
     pick the one this project is built around. -->

```bash
uv add <project-name>
```

## Usage

<!-- The smallest possible example that produces real output. A reader should be able to
     copy-paste this and see it work in under a minute. -->

```bash
<command> --example
```

```python
from <package_name> import <thing>

<thing>.do_something()
```

For the full command/API reference, see the [documentation](https://<owner>.github.io/<project-name>/).

## Configuration

<!-- Only include this section if the project has meaningful configuration. Document each
     setting's default and effect - don't just link to a schema file with no explanation. -->

| Setting | Default | Description |
|---|---|---|
| `<SETTING_NAME>` | `<default>` | <what it controls> |

## Development

Clone the repo and set up the environment:

```bash
git clone https://github.com/<owner>/<project-name>.git
cd <project-name>
uv sync
uv run pre-commit install
```

Run the quality checks before committing:

```bash
uv run pre-commit run -a
uv run mypy
```

## Testing

```bash
uv run pytest
```

<!-- Mention coverage expectations or how to run a single test file if that's not obvious
     from pytest's own --help. -->

## Project Structure

<!-- Only worth including once the layout isn't obvious from the repo root - e.g. a
     multi-package workspace, or a non-standard src/ layout. Keep it to the folders a
     contributor actually needs to know about, not a full recursive tree. -->

```text
<project-name>/
├── src/<package_name>/    # library code
├── tests/                  # test suite, mirrors src/ layout
└── docs/                   # documentation source
```

## Contributing

Contributions are welcome. Please open an issue before starting significant work so we can
agree on the approach, then:

1. Fork the repo and create a branch off `main`.
2. Make your change, with tests.
3. Run `uv run pre-commit run -a` and `uv run pytest` locally.
4. Open a pull request describing what changed and why.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

## License

Distributed under the <license name> license. See [LICENSE](LICENSE) for details.
