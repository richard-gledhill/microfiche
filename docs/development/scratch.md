# Scratch code

A personal notebook for snippets, commands and experiments worth keeping from guided build sessions.
Nothing here is part of the product: it is not imported, tested or published (`docs/development/` is
excluded from the docs site). Throwaway files that should not be kept go in `.temp/` (gitignored); this
page is for the ones you want to find again.

**Adding an entry:** newest first, one heading per entry, say what it is for and what it was verified
against, and keep the code runnable as written.

````markdown
## <short title> (YYYY-MM-DD)

What it is for, in a sentence. Related step or file: `path/to/file.py`.

```python
# the snippet
```
````

---

## Writing the test before the code (2026-10-09)

Notes on test-first development (red, green, refactor), with examples from the config validation work
(PR #35: `packages/core/src/core/config.py` and `tests/core/test_config.py`).

**The loop**

1. **Red:** write a test for behaviour that doesn't exist yet, run it, and read why it fails.
2. **Green:** write the smallest code that makes it pass.
3. **Refactor:** improve the design while the tests stay green.

```bash
uv run pytest tests/core/test_config.py -q --no-cov   # red: DID NOT RAISE, extra keys were accepted
```

```python
class _ConfigSection(BaseModel):
    model_config = ConfigDict(extra="forbid")          # green: unknown keys are now errors
```

Then the refactor (seven `Section(**config.get(...))` calls became one `MicroficheConfig.model_validate(config)`)
ran with every test still green.

**Why test first**

- **It makes you define "done" first.** Which exception type, which words in the message, before there is
  code that merely happens to do something.
- **It proves the test can fail.** A test written after the code and passing straight away might be vacuous.
  Four examples from this work, each of which would have passed forever:

  1. Assertions inside the `with pytest.raises(...)` block never run, because the raise ends the block.

     ```python
     # wrong: load_config raises, so the assert is never reached
     with pytest.raises(ConfigError) as exc_info:
         load_config(tmp_path)
         assert "classification" in str(exc_info.value)

     # right: assert after the block
     with pytest.raises(ConfigError) as exc_info:
         load_config(tmp_path)

     assert "classification" in str(exc_info.value)
     ```

  2. Normalising the text hides the difference the assertion was meant to see.

     ```python
     # wrong: a capitalised phrase can never appear in lowercased text, so this always passes
     assert "Extra inputs are not permitted" not in str(exc_info.value).lower()

     # right
     assert "Extra inputs are not permitted" not in str(exc_info.value)
     ```

  3. `CliRunner` doesn't put a raised exception's traceback in `stdout`.

     ```python
     # wrong: exit_code is 1 and stdout has no traceback whether or not the error was caught
     assert "Traceback" not in result.stdout

     # right: a clean exit is a SystemExit; an uncaught ConfigError is not
     assert isinstance(result.exception, SystemExit)
     ```

  4. The input never triggered the failure. Pydantic coerces `true` to `1`, so a "wrong type" test with
     `depth = true` raised nothing. `confidence_threshold = "high"` is a real type error.

- **The test is the first caller of the interface.** Testing through `load_config(...)` and expecting a
  `ConfigError` pushed the design toward one entry point and one error type.
- **It makes refactoring safe.** The behaviour is pinned, so a slip shows up in seconds.

**Red for the right reason.** Read the failure before writing code. `DID NOT RAISE` or an assertion
message about the behaviour is useful; `NameError` or an import error is red but says nothing about it.

**A mutation check, to prove a green test can see the bug.** Break the code on purpose, expect red, restore:

```bash
# in packages/cli/src/cli/commands.py, change `_ = library.config` to `pass`, then:
uv run pytest tests/cli/test_app.py -q --no-cov -k needs_the_config   # expect: 4 failed
git restore packages/cli/src/cli/commands.py
```

**Where it works less well**

- Exploratory code, where you don't know the behaviour yet. Prototype first, then test.
- Tests tied to incidental details. Assert on pydantic's stable `loc` and `type`, not its message wording.
- Red commits break CI and `git bisect` if pushed. Keep a red checkpoint local and end the branch green.
- It is a discipline, not a law. Glue code that only calls tested code gains little.

**Routine**

1. Write one failing test for the next small behaviour.
2. Run it and read the failure.
3. Write the minimum code to pass.
4. Run the whole suite, then refactor while green.
5. Commit at a green point.

See AGENTS.md, "Tests" and "Verifying your work", for the repo's rules: add or update tests for any behaviour
you change, and fix the code, not the check.

---

## Load a deliberately bad config (2026-10-08)

Shows the message a user sees for an invalid `.microfiche/microfiche-config.toml`. Used while writing
`_describe_errors` in `packages/core/src/core/config.py`. Verified on PowerShell 7.6 and Git Bash.

The scratch config goes in `.temp/` (gitignored), which `load_config` reads as if it were a library's
state folder.

PowerShell 7:

```powershell
New-Item -ItemType Directory -Force .temp | Out-Null && @'
[classification]
confidence_threshhold = 0.9
confidence_threshold = "high"
'@ > .temp/microfiche-config.toml
```

```powershell
uv run python -c "from pathlib import Path; from core.config import load_config; load_config(Path('.temp'))"
```

```powershell
Remove-Item .temp/microfiche-config.toml
```

Bash:

```bash
mkdir -p .temp && printf '[classification]\nconfidence_threshhold = 0.9\nconfidence_threshold = "high"\n' > .temp/microfiche-config.toml
```

Notes:

- Windows PowerShell 5.1 differs: no `&&`, and `>` writes UTF-16, which `tomllib` rejects. Use
  `Set-Content .temp\microfiche-config.toml -Encoding ascii` instead of `>`.
- The here-string's closing `'@` must start in column 0.
- Other things worth putting in the file: a typo'd section (`[classifcation]`), a scalar section
  (`classification = 5`) and a bad nested value (`[filing_rules]` with `rules = [{ pattern = 1 }]`).

## Seeing a test's message or failure detail (2026-10-08)

For when a test passes but you want to read what it checked, or fails and you want more than the summary.

```bash
uv run pytest tests/core/test_config.py -k bad_value -s --no-cov    # -s: show print() output
uv run pytest tests/core/test_config.py -k bad_value -rP --no-cov   # captured output of passing tests
uv run pytest tests/core/test_config.py -vv --no-cov                # full assertion diffs
uv run pytest tests/core/test_config.py --tb=long --showlocals -x   # long tracebacks, stop at first failure
```

Notes:

- `exc_info` from `pytest.raises(...) as exc_info` only has a value after the `with` block exits, so put a
  `print(exc_info.value)` or any assertion about the message **after** the block, never inside it.
- `--no-cov` skips the coverage report so the output is short.
