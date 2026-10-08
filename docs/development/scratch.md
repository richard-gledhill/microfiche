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
