# watchdog review

Research, not a decision: whether the `watchdog` package is suitable for [watch mode](../requirements/watch-mode-prd.md).
Checked on 2026-10-19 against watchdog's PyPI page, its GitHub README and changelog, and Microsoft's notes on
`ReadDirectoryChangesW`. Record the decision as an ADR when watch mode is specified.

## What it is

- A cross-platform file-system event library: inotify on Linux, FSEvents and kqueue on macOS, kqueue on BSD,
  `ReadDirectoryChangesW` on Windows, and a `PollingObserver` that compares directory snapshots on any platform.
- Apache-2.0 licensed. The latest release is 6.0.0 (2024-11-01), which lists CPython 3.9 to 3.13. A 7.0.0 is in
  development with breaking changes (glob-style pattern matching, attribute changes moved out of `on_modified`) and adds
  Python 3.15. Python 3.14, which microfiche supports, is not listed for 6.0.0, so it would need checking in CI.
- Actively maintained (the 7.0 changelog has several Windows fixes: renames split across event batches, case-only
  renames, and Windows ARM wheels).

## What matters for microfiche

| Need | What watchdog gives | Fit |
|---|---|---|
| Know when a new file or folder lands in `_sorting/` | Created and moved events, on every platform | Good |
| Know when a file has finished being written | `FileClosedEvent` exists, but only `InotifyObserver` on Linux emits it. On Windows there is no close event | Poor: microfiche must check stability itself |
| Not miss files | On Windows, `ReadDirectoryChangesW` uses a fixed buffer per directory and can drop all pending records under load; Microsoft's guidance is to rescan when that happens. A remote share can stop sending notifications without any error | Poor without a rescan |
| Network drives | The README says to use `PollingObserver` explicitly for CIFS shares | Polling only |
| OneDrive folders | Nothing found either way; synced placeholders are written by the sync client, so behaviour needs testing on a real machine | Unknown |
| Small dependency | Pure Python apart from the macOS backend; `watchmedo` is an optional extra not needed | Good |

## Conclusion

watchdog is suitable as a **trigger**, not as the **source of truth**. On Windows, the main platform here, it gives no
"finished writing" signal and can drop events, so watch mode cannot rely on it alone either way. Every design that
works needs the same two pieces microfiche would build anyway:

1. A **rescan** of the inbox with the existing `scanner.py::scan_sorting_inbox`, so a missed event only delays a file.
2. A **stability check** (size and modification time unchanged across two looks, then the rename-only move, which
   fails cleanly on a file that is still open).

Since the inbox is small and the rescan is cheap, the recommendation is:

- **Build watch mode on polling first**, using the existing scanner every few seconds, with no new dependency. It works
  the same on local disks, network shares and OneDrive, and is easy to test with a fake clock.
- **Add watchdog later, as an optional trigger** (behind a small seam, perhaps as an extra) only if polling's delay or
  cost is a measured problem. The rescan and stability check stay underneath it.

## Open questions

- Does polling every few seconds cost anything noticeable on a OneDrive-synced inbox (hydrating placeholders)? The
  scanner reads names and sizes only, but test it on a real machine.
- If watchdog is added: 6.x or 7.x? 7.0's pattern and event changes are breaking, so start on whichever is current
  then, and pin the major version.

## Sources

- [watchdog on PyPI](https://pypi.org/project/watchdog/): version, licence, Python versions, platform backends, the
  CIFS and polling notes.
- [watchdog on GitHub](https://github.com/gorakhargosh/watchdog) and its
  [changelog](https://github.com/gorakhargosh/watchdog/blob/master/changelog.rst): maintenance, the 7.0 changes, and
  close events being emitted only by `InotifyObserver`.
- [FileSystemWatcher Follies](https://learn.microsoft.com/zh-cn/archive/blogs/winsdk/filesystemwatcher-follies)
  (Microsoft): `ReadDirectoryChangesW` buffer overflows, rescanning, and remote servers that stop notifying.
