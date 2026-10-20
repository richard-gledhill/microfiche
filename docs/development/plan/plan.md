# Plan: `microfiche init`

Implements [SPEC.md](SPEC.md). Each step is test-first (red, green, refactor) and ends with its targeted tests
passing and a commit; `make check` and `make test` run at the end.

1. **Dependency and problems as data.** Add `tomlkit` to `core` (`uv add --package core tomlkit`). In
   `core/config.py`, add `ConfigProblem` and `ConfigError.problems`, built from the same pydantic errors that build
   the message; expose the packaged defaults' text. Add a comment line to every setting in the packaged defaults
   that lacks one, and keep the `microfiche/` template in step.
2. **Core: `core/library_init.py`.** `inspect_install`, `install_defaults`, `create_inbox`, and `ConfigEditor`
   (settings with value, default and help; `check`/`set` with validation; `revert_invalid`; `revert_all`;
   `changes`; `save` with backup, change detection and an atomic write). Tests in
   `tests/core/test_library_init.py`.
3. **CLI: `init`.** `cli/init_prompts.py` holds the prompts (walk-through, revert choice, backup question, library file
   rebuild); `commands.init` holds the flow and the lock; registered in `app.py`. Tests in
   `tests/cli/test_cli_init.py`, one per acceptance criterion and the extra cases in the spec.
4. **No-config guard.** `sort`, `reclassify` and `propose-categories` stop and name `init`; config errors suggest
   `init`. Update the pinned CLI test and any test that ran these on a library with no config.
5. **Docs.** how-to-use (both tabs), README Usage, `make docs-cli`, mvp-roadmap, architecture/overview,
   `microfiche/README.md`, `make module-diagram`.
6. **Close out.** `make check`, `make test`; PRD to Done; move `SPEC.md`, `plan.md`, `todo.md` to
   `archive/2026-10-library-init/`.
