"""The library: the folder microfiche manages, and everything that depends on how it is laid out.

A library is an inbox plus one or two levels of folders, group then category (or group alone, in a flat
library), with a hidden state folder
(``.microfiche``) holding its config and records. ``Library`` is the one place that knows which
folder is which: where the inbox and state folder are, what counts as excluded, what the taxonomy
is, and where a classified unit belongs. Everything else asks it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.config import MICROFICHE_DIRNAME, MicroficheConfig, load_config
from core.ledger import Ledger, LedgerCorruptError
from core.library.library_file import FolderNode, LibraryFile, load_library_file
from core.models.category import Taxonomy
from core.utils.filesystem import is_excluded, is_link

_logger = logging.getLogger(__name__)


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

    @library_file.setter
    def library_file(self, value: LibraryFile) -> None:
        """Replace the kept library file, after the file on disk has been rewritten."""

        self._library_file = value

    @property
    def state_dir(self) -> Path:
        """The hidden folder holding the config, ledger, audit log and rollback jobs."""

        return self.root / MICROFICHE_DIRNAME

    @property
    def inbox(self) -> Path:
        """The folder new documents are dropped into (named by the config's ``[library_structure] library_inbox``)."""

        return self.root / self.config.library_structure.library_inbox

    def structure(self) -> list[FolderNode]:
        """Read the library's folders, down to the configured depth, as they exist right now.

        Only folder names are read, never file contents, so this is cheap even for a library with
        10,000+ files. The inbox, the state folder, anything matching the config's exclusions, any
        symlink or junction (never followed) and any folder the ledger records as filed whole are skipped. The
        last matters after the depth is raised: a bundle filed at ``Group/pack`` would otherwise become a category.
        Nothing is cached: the folders are the authority on what exists.

        Returns:
            The groups in sorted order, each with its sub-folders as ``children`` down to
            ``[library_structure] depth`` levels. The nodes carry names only, no hints or rules.
        """

        return self._folders_in(self.root, self.config.library_structure.depth, self._filed_whole())

    def taxonomy(self) -> Taxonomy:
        """The library's groups and, for each, its category names: a view of ``structure()``.

        Nothing is cached: the folders are the taxonomy.

        Returns:
            The groups and, for each, its category names.
        """

        groups = {group.name: [child.name for child in group.children] for group in self.structure()}
        return Taxonomy(groups=groups, depth=self.config.library_structure.depth)

    def target_dir(self, *folders: str) -> Path:
        """The folder a unit classified under ``folders`` is filed into.

        Args:
            *folders: The folder names down from the library root: the group, then the category in a
                library that has them (see ``ClassificationResult.folders``).

        Returns:
            ``<root>/<group>`` or ``<root>/<group>/<category>``.
        """

        return self.root.joinpath(*folders)

    def filed_under(self, path: Path, *folders: str) -> bool:
        """Whether ``path`` is in the ``folders`` folder, or in a folder below it.

        Args:
            path: A file or folder inside the library.
            *folders: The folder names down from the library root, as for ``target_dir``.

        Returns:
            ``True`` if the path is directly in that folder or anywhere beneath it.
        """

        target = self.target_dir(*folders)
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

    def _filed_whole(self) -> set[Path]:
        """The folders microfiche filed whole, which are content and not structure.

        An unreadable ledger is a warning, not an error: it would otherwise stop ``sort``, which only appends to it.
        The folders are then simply not recognised.
        """

        try:
            return {self.root / path for path in Ledger(self.state_dir).folder_units()}
        except LedgerCorruptError as err:
            _logger.warning("the ledger can't be read, so folders filed whole are not recognised: %s", err)
            return set()

    def _folders_in(self, parent: Path, levels: int, filed_whole: set[Path]) -> list[FolderNode]:
        """The library folders directly inside ``parent``, each with its own down to ``levels`` levels in all."""

        if levels < 1:
            return []
        return [
            # Not validated: a folder is whatever it is called, even if the library file could not hold that name
            # (two names differing only by case on Linux, say). The sync decides which can be entries.
            FolderNode.model_construct(name=folder.name, children=self._folders_in(folder, levels - 1, filed_whole))
            for folder in sorted(parent.iterdir())
            if folder.is_dir() and not is_link(folder) and not self.is_excluded(folder) and folder not in filed_whole
        ]

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
