#!/usr/bin/env bash
# Run the built wheels the way a user of a release would, in an environment that has none of this repository in it.
#
# check_wheels.py reads the wheels; this runs them. `uv run --isolated --no-project --with <wheel>` makes a throwaway
# environment holding only the core and cli wheels and what they depend on, so a file the wheels forgot to include
# (the packaged defaults file) is missing here, as it would be for a user. An editable install from the checkout
# never shows that, because there the file is always on disk beside the code.
#
# It checks that `microfiche --version` prints the wheels' version, that `sort` files a document from a copy of
# tests/mock_library, and that `rollback --last` undoes it.
#
# Usage: scripts/smoke_wheels.sh <dist-dir>
# Needs uv and network access (for the wheels' dependencies). Exit code 0 means every step worked.
set -euo pipefail

dist="${1:?usage: smoke_wheels.sh <dist-dir>}"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

core=("$dist"/core-*.whl)
cli=("$dist"/cli-*.whl)
if [ "${#core[@]}" -ne 1 ] || [ "${#cli[@]}" -ne 1 ] || [ ! -f "${core[0]}" ] || [ ! -f "${cli[0]}" ]; then
  echo "error: expected one core and one cli wheel in $dist" >&2
  exit 1
fi
version="$(basename "${core[0]}" | cut -d- -f2)"

microfiche() {
  uv run --isolated --no-project --with "${core[0]}" --with "${cli[0]}" microfiche "$@"
}

shown="$(microfiche --version)"
if [ "$shown" != "microfiche $version" ]; then
  echo "error: \`microfiche --version\` printed '$shown', expected 'microfiche $version'" >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -R "$repo/tests/mock_library" "$work/library"

sorted="$(microfiche sort --library "$work/library")"
if ! grep -q '^Job: ' <<<"$sorted" || grep -q '^Filed: 0' <<<"$sorted"; then
  echo "error: \`microfiche sort\` filed nothing from the mock library:" >&2
  echo "$sorted" >&2
  exit 1
fi
microfiche rollback --library "$work/library" --last >/dev/null

echo "ok: $(basename "${core[0]}") and $(basename "${cli[0]}") install in a clean environment; --version, sort and rollback --last work"
