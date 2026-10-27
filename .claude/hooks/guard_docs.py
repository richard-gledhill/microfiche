"""Claude Code PreToolUse hook: keep development docs under docs/development/.

Reads the tool call as JSON on stdin. Exit 2 (with a message on stderr) blocks the write and tells the
agent what to do instead; exit 0 allows it. Edits to MkDocs content and mkdocs.yml are allowed.
conventions.md and constraints.md ship with the project and are protected: only the owner changes them. Add a
directory to PROTECTED_DIRS to protect its existing files the same way; creating a new one is still allowed.
Shell-command edits (mv, sed) are not seen by this hook.
"""

import json
import os
import sys
from pathlib import Path

PLAN = "docs/development/plan"
# Default locations used by the agent workflows (and old layouts) mapped to where the file belongs.
REDIRECTS = {
    "spec.md": f"{PLAN}/SPEC.md",
    "constraints.md": "docs/development/constraints.md",
    "plan.md": f"{PLAN}/plan.md",
    "todo.md": f"{PLAN}/todo.md",
    "tasks/plan.md": f"{PLAN}/plan.md",
    "tasks/todo.md": f"{PLAN}/todo.md",
    "docs/development/spec.md": f"{PLAN}/SPEC.md",
}
PREFIX_REDIRECTS = {
    "tasks/": f"{PLAN}/",
    "docs/development/tasks/": f"{PLAN}/",
}
PROTECTED = ("docs/development/conventions.md", "docs/development/constraints.md")
PROTECTED_DIRS: tuple[str, ...] = ()  # e.g. ("docs/development/requirements/",)

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path")
if not path:
    sys.exit(0)

root = Path(os.environ.get("CLAUDE_PROJECT_DIR", data.get("cwd", "."))).resolve()
resolved = (root / path).resolve()
try:
    rel = resolved.relative_to(root).as_posix().lower()
except ValueError:
    sys.exit(0)  # outside the repo

if (rel in PROTECTED and resolved.exists()) or (rel.startswith(PROTECTED_DIRS) and resolved.is_file()):
    print(
        f"Blocked: {rel} is protected (see AGENTS.md). Don't edit it to match your code. "
        "Describe the change you think is needed in your summary and ask the user to make or approve it.",
        file=sys.stderr,
    )
    sys.exit(2)

target = REDIRECTS.get(rel) or next((t for prefix, t in PREFIX_REDIRECTS.items() if rel.startswith(prefix)), None)
if target:
    print(f"Blocked: {rel} is not a development docs path (see AGENTS.md). Write {target} instead.", file=sys.stderr)
    sys.exit(2)
