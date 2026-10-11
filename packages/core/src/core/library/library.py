"""The library: the folder microfiche manages, and everything that depends on how it is laid out.

A library is an inbox plus two levels of folders, group then category, with a hidden state folder
(``.microfiche``) holding its config and records. ``Library`` is the one place that knows which
folder is which: where the inbox and state folder are, what counts as excluded, what the taxonomy
is, and where a classified unit belongs. Everything else asks it.
"""

from __future__ import annotations

from pathlib import Path

from core.config import MICROFICHE_DIRNAME, MicroficheConfig, load_config
from core.library.library_file import LibraryFile, load_library_file
from core.models.category import Taxonomy
from core.utils.filesystem import is_excluded


class ScopeOutsideLibraryError(ValueError):
    """Raised when asked to look at a folder that isn't inside the library."""

    def __init__(self, scope: Path, library_root: Path) -> None:
        self.scope = scope
        super().__init__(f"Scope '{scope}' is not inside the library '{library_root}'")


class Library:
    """A library folder, its config, and its layout.

    Constructing one does no I/O. The config and the library file are read from ``<root>/.microfiche``
    the first time something needs them (a missing file means defaults, or no hints), so operations that
    only need paths - such as undoing a job - work even if either file is broken.

    Args:
        root: The library's root folder.
        config: The library's config, if the caller already has one; otherwise it is loaded lazily.

    Attributes:
        root: The library's root folder.
    """

    def __init__(self, root: Path, config: MicroficheConfig | None = None) -> None:
        self.root = root
        self._config = config
        self._library_file: LibraryFile | None = None

    @property
    def config(self) -> MicroficheConfig:
        """The library's configuration, loaded on first use and then kept (and mutable)."""

        if self._config is None:
            self._config = load_config(self.state_dir)
        return self._config

    @property
    def library_file(self) -> LibraryFile:
        """The library's hints and filename rules, loaded on first use and then kept.

        Checked against the config's ``[library_structure] depth``, so loading it also loads the config.
        """

        if self._library_file is None:
            self._library_file = load_library_file(self.state_dir, self.config.library_structure.depth)
        return self._library_file

    @property
    def state_dir(self) -> Path:
        """The hidden folder holding the config, ledger, audit log and rollback jobs."""

        return self.root / MICROFICHE_DIRNAME

    @property
    def inbox(self) -> Path:
        """The folder new documents are dropped into (named by the config's ``[library_structure] library_inbox``)."""

        return self.root / self.config.library_structure.library_inbox

    def taxonomy(self) -> Taxonomy:
        """Read the library's groups and categories from the folders that exist right now.

        Only folder names are read, never file contents, so this is cheap even for a library with
        10,000+ files. The inbox, the state folder and anything matching the config's exclusions
        are skipped at both levels. Nothing is cached: the folders are the taxonomy.

        Returns:
            The groups and, for each, its category names.
        """

        groups: dict[str, list[str]] = {}
        for group_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            if self.is_excluded(group_dir):
                continue
            groups[group_dir.name] = [
                category_dir.name
                for category_dir in sorted(group_dir.iterdir())
                if category_dir.is_dir() and not self.is_excluded(category_dir)
            ]
        return Taxonomy(groups=groups)

    def target_dir(self, group: str, category: str) -> Path:
        """The folder a unit classified as ``group``/``category`` is filed into.

        Args:
            group: The unit's group.
            category: The unit's category within ``group``.

        Returns:
            ``<root>/<group>/<category>``.
        """

        return self.root / group / category

    def filed_under(self, path: Path, group: str, category: str) -> bool:
        """Whether ``path`` is in the ``group``/``category`` folder, or in a folder below it.

        Args:
            path: A file or folder inside the library.
            group: The unit's group.
            category: The unit's category within ``group``.

        Returns:
            ``True`` if the path is directly in the category folder or anywhere beneath it.
        """

        target = self.target_dir(group, category)
        return path.parent == target or target in path.parents

    def is_excluded(self, path: Path) -> bool:
        """Whether ``path`` (inside the library) is not part of the library's content.

        The inbox and the state folder are always excluded, whatever the config says. Beyond that,
        any component of the path *relative to the library root* matching one of the config's
        exclusion patterns excludes it. Folders above the library are never considered, so a
        library kept under ``~/.vaults`` or ``~/_work`` behaves like any other.

        Args:
            path: A path inside the library.

        Returns:
            ``True`` if the path is excluded.

        Raises:
            ValueError: if ``path`` isn't inside the library.
        """

        relative = path.relative_to(self.root)
        if relative.parts and relative.parts[0] in (self.config.library_structure.library_inbox, MICROFICHE_DIRNAME):
            return True
        return is_excluded(relative, self.config.exclusions.exclude)

    def relative(self, path: Path) -> str:
        """Express ``path`` relative to the library, with forward slashes.

        Args:
            path: The path to express.

        Returns:
            The path relative to the library root, or as-is if it lies outside it.
        """

        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def files(self, scope: Path | None = None) -> list[Path]:
        """List every file under ``scope`` (default: the whole library) that isn't excluded.

        Args:
            scope: A folder inside the library to limit the listing to. May be relative to the
                working directory or spelled differently from ``root``.

        Returns:
            The files, in sorted path order.

        Raises:
            ScopeOutsideLibraryError: if ``scope`` isn't inside the library.
        """

        search_root = self._search_root(scope)
        return [path for path in sorted(search_root.rglob("*")) if path.is_file() and not self.is_excluded(path)]

    def _search_root(self, scope: Path | None) -> Path:
        """``scope`` re-expressed under ``root``'s own spelling of the path.

        File locations are compared with ``root``-based destinations, so a relative or
        differently-spelled scope must not leak through as-is.
        """

        if scope is None:
            return self.root
        try:
            return self.root / scope.resolve().relative_to(self.root.resolve())
        except ValueError as err:
            raise ScopeOutsideLibraryError(scope, self.root) from err
