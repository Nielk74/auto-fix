from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from auto_fix.build import run_command
from auto_fix.config import RepositoryConfig
from auto_fix.models import Edit

SHA = re.compile(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\Z")
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp"}
TEST_DIRECTORIES = {"test", "tests", "testing", "unittest", "unittests", "googletest", "gtest"}


class WorkspaceError(RuntimeError):
    pass


class Workspace:
    def __init__(self, config: RepositoryConfig, state_dir: Path, run_id: str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id):
            raise ValueError("run_id must contain only letters, digits, hyphens and underscores")
        self.config = config
        self.source = config.path.resolve()
        self.state_dir = state_dir.resolve()
        self.run_id = run_id
        self.path = self.state_dir / "worktrees" / run_id
        self.branch = f"auto-fix/{run_id}"
        self._command_number = 0
        self._log_session = uuid.uuid4().hex[:12]

    def _git(self, args: list[str], *, source: bool = False, check: bool = True) -> str:
        self._command_number += 1
        result = run_command(
            ["git", *args],
            self.source if source else self.path,
            180,
            self.state_dir
            / "git-logs"
            / self.run_id
            / self._log_session
            / f"{self._command_number:04d}.log",
        )
        if check and result.returncode:
            raise WorkspaceError(f"Git command failed ({result.returncode}): {result.output}")
        # Plumbing callers need complete path lists; only model-facing context is truncated.
        if Path(result.log_path).stat().st_size > 20_000_000:
            raise WorkspaceError("Git output exceeds the 20 MB machine-output limit")
        return Path(result.log_path).read_text(encoding="utf-8")

    def _fetch_base(self) -> None:
        remote, branch = self.config.remote, self.config.base_branch
        self._git(
            ["fetch", "--no-tags", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"],
            source=True,
        )

    def prepare(self, revision: str) -> Path:
        if not SHA.fullmatch(revision):
            raise ValueError("Expected a full 40- or 64-character Git commit SHA")
        root = self._git(["rev-parse", "--show-toplevel"], source=True).strip()
        if Path(root).resolve() != self.source:
            raise WorkspaceError("repository.path must point to the root of an existing Git clone")
        if self.path.exists():
            raise WorkspaceError(f"Run workspace already exists: {self.path}; use a new run ID")
        self._fetch_base()
        exists = run_command(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            self.source,
            30,
            self.state_dir / "git-logs" / self.run_id / "revision-check.log",
        )
        if exists.returncode:
            self._git(["fetch", "--no-tags", self.config.remote, revision], source=True)
        self._git(["rev-parse", "--verify", f"{revision}^{{commit}}"], source=True)
        base = f"refs/remotes/{self.config.remote}/{self.config.base_branch}"
        for ref in (revision, base):
            tree = self._git(["ls-tree", "-r", ref], source=True)
            if any(line.startswith("160000 ") for line in tree.splitlines()) or any(
                line.endswith("\t.gitmodules") for line in tree.splitlines()
            ):
                raise WorkspaceError(
                    "Submodule repositories require disposable-clone support; "
                    "this prototype supports repositories without submodules"
                )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._git(["worktree", "add", "-b", self.branch, str(self.path), revision], source=True)
        self._rebase_fetched()
        return self.path

    def _rebase_fetched(self) -> str:
        try:
            self._git(
                [
                    "-c",
                    "core.hooksPath=" + str(self._empty_hooks()),
                    "-c",
                    f"user.name={self.config.author_name}",
                    "-c",
                    f"user.email={self.config.author_email}",
                    "-c",
                    "commit.gpgsign=false",
                    "rebase",
                    f"refs/remotes/{self.config.remote}/{self.config.base_branch}",
                ]
            )
        except WorkspaceError as error:
            self._git(["rebase", "--abort"], check=False)
            raise WorkspaceError(
                f"Rebase failed; automatic conflict resolution is disabled. {error}"
            ) from error
        return self.head()

    def _empty_hooks(self) -> Path:
        path = self.state_dir / "empty-hooks"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def rebase(self) -> str:
        if not self.is_clean():
            raise WorkspaceError("Commit tracked changes before rebasing")
        self._fetch_base()
        return self._rebase_fetched()

    def head(self) -> str:
        return self._git(["rev-parse", "HEAD"]).strip()

    def is_clean(self) -> bool:
        return not self._git(["diff", "--name-only", "HEAD", "--"]).strip()

    def has_changes_against_base(self) -> bool:
        self._command_number += 1
        result = run_command(
            [
                "git",
                "diff",
                "--quiet",
                "--no-ext-diff",
                "--no-textconv",
                f"refs/remotes/{self.config.remote}/{self.config.base_branch}",
                "HEAD",
                "--",
            ],
            self.path,
            60,
            self.state_dir
            / "git-logs"
            / self.run_id
            / self._log_session
            / f"{self._command_number:04d}.log",
        )
        if result.returncode not in {0, 1}:
            raise WorkspaceError(f"Unable to compare fix to base: {result.output}")
        return result.returncode == 1

    def _tracked_paths(self) -> list[str]:
        return [p for p in self._git(["ls-files", "-z"]).split("\0") if p]

    def context(
        self, changes: list[dict], max_chars: int, test_names: list[str] | None = None
    ) -> dict[str, Any]:
        if max_chars < 100:
            raise ValueError("Context budget must be at least 100 characters")
        result: dict[str, Any] = {"head": self.head(), "commits": [], "files": []}
        remaining = max_chars - len(json.dumps(result)) - 100
        revisions: list[str] = []
        for change in changes:
            candidate = str(change.get("version", change.get("revision", "")))
            if SHA.fullmatch(candidate) and candidate not in revisions:
                revisions.append(candidate)
        if self.head() not in revisions:
            revisions.append(self.head())
        changed_paths: set[str] = set()
        for revision in revisions[:12]:
            names = self._git(
                ["show", "--pretty=format:", "--name-only", revision, "--"], check=False
            )
            changed_paths.update(names.splitlines())
        for revision in revisions[:12]:
            if remaining < 200:
                break
            details = self._git(
                ["show", "--format=fuller", "--no-ext-diff", "--no-textconv", revision, "--"],
                check=False,
            )
            content = details[: min(remaining // 3, 12000)]
            item = {"revision": revision, "diff": content}
            size = len(json.dumps(item)) + 2
            if size > remaining:
                break
            result["commits"].append(item)
            remaining -= size
        candidates = [
            path
            for path in self._tracked_paths()
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in self.config.context_paths)
        ]
        mentions = [
            part.casefold()
            for name in test_names or []
            for part in re.split(r"[.:/ ]", name)
            if len(part) >= 4
        ]
        candidates.sort(
            key=lambda path: (
                path not in changed_paths,
                not any(s in path.casefold() for s in mentions),
                path,
            )
        )
        for relative in candidates[:200]:
            if remaining < 200:
                break
            try:
                path = self._safe_existing_path(relative)
                if path.stat().st_size > 100_000:
                    continue
                content = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeError, WorkspaceError):
                continue
            item = {"path": relative, "content": content[: min(remaining - 100, 14000)]}
            size = len(json.dumps(item)) + 2
            if size > remaining:
                # JSON escaping can expand strings; retain a smaller useful excerpt.
                item["content"] = item["content"][: max(0, (remaining - 100) // 6)]
                size = len(json.dumps(item)) + 2
            if size <= remaining:
                result["files"].append(item)
                remaining -= size
        return result

    def _safe_existing_path(self, relative: str) -> Path:
        parts = relative.split("/")
        if (
            not relative
            or "\\" in relative
            or ":" in relative
            or any(ord(c) < 32 for c in relative)
            or PurePosixPath(relative).is_absolute()
            or any(part in {"", ".", ".."} for part in parts)
            or any(part.rstrip(" .") != part for part in parts)
        ):
            raise WorkspaceError(f"Unsafe repository-relative path: {relative!r}")
        path = self.path.joinpath(*parts)
        for candidate in [path, *path.parents]:
            if candidate == self.path:
                break
            if candidate.is_symlink():
                raise WorkspaceError(f"Symlink paths are not editable: {relative}")
        try:
            path.resolve(strict=True).relative_to(self.path.resolve())
        except (ValueError, FileNotFoundError) as error:
            raise WorkspaceError(f"Path must be an existing worktree file: {relative}") from error
        if not path.is_file():
            raise WorkspaceError(f"Path must be an existing file: {relative}")
        return path

    def _editable_path(self, relative: str, tracked: set[str]) -> Path:
        path = self._safe_existing_path(relative)
        name = path.stem.casefold()
        if relative not in tracked:
            raise WorkspaceError(f"Only existing tracked source files may be edited: {relative}")
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in self.config.allowed_paths):
            raise WorkspaceError(f"Path is outside repository.allowed_paths: {relative}")
        if (
            path.suffix.casefold() not in SOURCE_SUFFIXES
            or any(
                part.casefold() in TEST_DIRECTORIES for part in PurePosixPath(relative).parts[:-1]
            )
            or name.startswith(("test_", "tests_"))
            or name.endswith(("_test", "_tests", "test", "tests"))
        ):
            raise WorkspaceError(f"Test and build configuration edits are disabled: {relative}")
        return path

    def apply_edits(self, edits: list[Edit]) -> None:
        if not edits:
            raise WorkspaceError("No edits were proposed")
        size = sum(len(edit.old.encode("utf-8")) + len(edit.new.encode("utf-8")) for edit in edits)
        if size > self.config.max_edit_bytes:
            raise WorkspaceError("Proposal exceeds repository.max_edit_bytes")
        tracked = set(self._tracked_paths())
        originals: dict[Path, bytes] = {}
        proposed: dict[Path, str] = {}
        for edit in edits:
            path = self._editable_path(edit.path, tracked)
            if path not in originals:
                originals[path] = path.read_bytes()
                try:
                    proposed[path] = originals[path].decode("utf-8")
                except UnicodeError as error:
                    raise WorkspaceError(f"File is not UTF-8: {edit.path}") from error
            if edit.old == edit.new:
                raise WorkspaceError(f"Edit makes no change: {edit.path}")
            count = proposed[path].count(edit.old)
            if count != 1:
                raise WorkspaceError(
                    f"Expected old text exactly once in {edit.path}; found {count}"
                )
            proposed[path] = proposed[path].replace(edit.old, edit.new, 1)
        # Validate the whole proposal before writing anything; preserve CRLF bytes and mode.
        temporary: dict[Path, Path] = {}
        replaced: list[Path] = []
        try:
            for path, content in proposed.items():
                if path.read_bytes() != originals[path]:
                    raise WorkspaceError(f"File changed while preparing edits: {path.name}")
                descriptor, name = tempfile.mkstemp(prefix=".auto-fix-", dir=path.parent)
                temporary[path] = Path(name)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content.encode("utf-8"))
                temporary[path].chmod(stat.S_IMODE(path.stat().st_mode))
            for path, temp in temporary.items():
                os.replace(temp, path)
                replaced.append(path)
        except Exception:
            for path in replaced:
                path.write_bytes(originals[path])
            raise
        finally:
            for temp in temporary.values():
                temp.unlink(missing_ok=True)

    def diff(self) -> str:
        return self._git(["diff", "--no-ext-diff", "--no-textconv", "HEAD", "--"])

    def committed_diff(self) -> str:
        return self._git(["show", "--format=", "--no-ext-diff", "--no-textconv", "HEAD", "--"])

    def commit(self, summary: str) -> str:
        if not summary.strip() or "\0" in summary:
            raise WorkspaceError("Commit summary must not be empty")
        changed = [
            p for p in self._git(["diff", "--name-only", "-z", "HEAD", "--"]).split("\0") if p
        ]
        if not changed:
            raise WorkspaceError("Refusing to create an empty fix commit")
        tracked = set(self._tracked_paths())
        for path in changed:
            self._editable_path(path, tracked)
        self._git(["add", "--", *changed])
        self._git(
            [
                "-c",
                f"user.name={self.config.author_name}",
                "-c",
                f"user.email={self.config.author_email}",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={self._empty_hooks()}",
                "commit",
                "--only",
                "-m",
                summary.strip(),
                "--",
                *changed,
            ]
        )
        return self.head()

    def push(self) -> None:
        if not self.is_clean():
            raise WorkspaceError("Refusing to push with uncommitted tracked changes")
        existing = self._git(
            ["ls-remote", "--heads", self.config.remote, f"refs/heads/{self.branch}"]
        )
        if existing.strip():
            raise WorkspaceError(
                "Bot branch already exists remotely; reconcile the previous publication"
            )
        self._git(["push", "--", self.config.remote, f"HEAD:refs/heads/{self.branch}"])
