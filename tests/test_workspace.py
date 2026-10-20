from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_fix.config import RepositoryConfig
from auto_fix.models import Edit
from auto_fix.workspace import Workspace, WorkspaceError


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=master")
    source = tmp_path / "source"
    git(tmp_path, "clone", str(remote), str(source))
    git(source, "config", "user.name", "Test User")
    git(source, "config", "user.email", "test@example.invalid")
    (source / "src").mkdir()
    (source / "tests").mkdir()
    (source / "src" / "math.cpp").write_bytes(b"int add(int a, int b) { return a - b; }\r\n")
    (source / "tests" / "test_math.cpp").write_text("int test = 1;\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "Initial failing implementation")
    git(source, "push", "origin", "master")
    config = RepositoryConfig(path=source)
    return source, remote, config, git(source, "rev-parse", "HEAD")


def test_worktree_preserves_developer_changes_rebases_and_publishes(repository, tmp_path):
    source, remote, config, failing = repository
    (source / "src" / "extra.cpp").write_text("int extra = 1;\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "Later master improvement")
    git(source, "push", "origin", "master")
    latest = git(source, "rev-parse", "HEAD")
    (source / "src" / "math.cpp").write_text("developer local changes\n")
    workspace = Workspace(config, tmp_path / "state", "build-42")
    path = workspace.prepare(failing)
    assert path != source and workspace.head() == latest
    assert not workspace.has_changes_against_base()
    assert (source / "src" / "math.cpp").read_text() == "developer local changes\n"
    workspace.apply_edits([Edit(path="src/math.cpp", old="a - b", new="a + b")])
    assert not workspace.is_clean()
    assert b"\r\n" in (path / "src" / "math.cpp").read_bytes()
    assert "a + b" in workspace.diff()
    (path / "build-output.log").write_text("untracked build output")
    commit = workspace.commit("Fix add arithmetic")
    assert workspace.has_changes_against_base()
    assert "a + b" in workspace.committed_diff()
    assert workspace.is_clean()
    assert git(path, "show", "--pretty=", "--name-only", commit) == "src/math.cpp"
    assert git(path, "show", "-s", "--format=%an", commit) == "Auto Fix"
    assert git(source, "config", "user.name") == "Test User"
    assert workspace.rebase() == commit
    workspace.push()
    assert git(remote, "rev-parse", "refs/heads/auto-fix/build-42") == commit
    with pytest.raises(WorkspaceError, match="already exists remotely"):
        workspace.push()


def test_proposal_is_prevalidated_before_any_write(repository, tmp_path):
    _, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "atomic")
    workspace.prepare(failing)
    before = (workspace.path / "src" / "math.cpp").read_bytes()
    with pytest.raises(WorkspaceError, match="exactly once"):
        workspace.apply_edits(
            [
                Edit(path="src/math.cpp", old="a - b", new="a + b"),
                Edit(path="src/math.cpp", old="absent text", new="something"),
            ]
        )
    assert (workspace.path / "src" / "math.cpp").read_bytes() == before


@pytest.mark.parametrize(
    "path",
    [
        "../src/math.cpp",
        "/src/math.cpp",
        "C:/src/math.cpp",
        "src/math.cpp:secret",
        "src\\math.cpp",
        "src/./math.cpp",
        "src//math.cpp",
        "src/math.cpp ",
        "tests/test_math.cpp",
        "CMakeLists.txt",
    ],
)
def test_rejects_unsafe_and_disallowed_paths(repository, tmp_path, path):
    _, _, config, failing = repository
    config.allowed_paths = ["**"]
    workspace = Workspace(config, tmp_path / "state", "paths")
    workspace.prepare(failing)
    with pytest.raises(WorkspaceError):
        workspace.apply_edits([Edit(path=path, old="int", new="long")])


def test_duplicate_match_and_oversized_proposals_rejected(repository, tmp_path):
    _, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "limits")
    workspace.prepare(failing)
    with pytest.raises(WorkspaceError, match="found 3"):
        workspace.apply_edits([Edit(path="src/math.cpp", old="int", new="long")])
    config.max_edit_bytes = 100
    with pytest.raises(WorkspaceError, match="max_edit_bytes"):
        workspace.apply_edits([Edit(path="src/math.cpp", old="a - b", new="x" * 100)])


def test_unexpected_tracked_changes_prevent_commit(repository, tmp_path):
    _, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "unexpected")
    workspace.prepare(failing)
    workspace.apply_edits([Edit(path="src/math.cpp", old="a - b", new="a + b")])
    (workspace.path / "tests" / "test_math.cpp").write_text("disabled\n")
    with pytest.raises(WorkspaceError):
        workspace.commit("Fix")
    assert git(workspace.path, "diff", "--cached", "--name-only") == ""


def test_context_is_bounded_and_includes_sources(repository, tmp_path):
    _, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "context")
    workspace.prepare(failing)
    context = workspace.context([{"version": failing}], 2000, ["test_math"])
    assert len(json.dumps(context)) <= 2000
    assert any(file["path"] == "src/math.cpp" for file in context["files"])


def test_submodules_are_rejected_before_worktree_creation(repository, tmp_path):
    source, _, config, _ = repository
    (source / ".gitmodules").write_text('[submodule "vendor"]\npath=vendor\nurl=../vendor\n')
    git(source, "add", ".gitmodules")
    git(source, "commit", "-m", "Add submodule declaration")
    git(source, "push", "origin", "master")
    workspace = Workspace(config, tmp_path / "state", "submodules")
    with pytest.raises(WorkspaceError, match="Submodule"):
        workspace.prepare(git(source, "rev-parse", "HEAD"))
    assert not workspace.path.exists()


def test_rebase_conflict_is_aborted_and_never_resolved_automatically(repository, tmp_path):
    source, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "conflict")
    workspace.prepare(failing)
    workspace.apply_edits([Edit(path="src/math.cpp", old="a - b", new="a + b")])
    bot_commit = workspace.commit("Bot fix")
    (source / "src" / "math.cpp").write_text("int add(int a, int b) { return a * b; }\n")
    git(source, "add", "src/math.cpp")
    git(source, "commit", "-m", "Concurrent master change")
    git(source, "push", "origin", "master")
    with pytest.raises(WorkspaceError, match="conflict resolution is disabled"):
        workspace.rebase()
    assert workspace.head() == bot_commit and workspace.is_clean()
    assert not Path(git(workspace.path, "rev-parse", "--git-path", "rebase-merge")).exists()


def test_symlink_source_is_rejected(repository, tmp_path):
    source, _, config, _ = repository
    target = tmp_path / "external.cpp"
    target.write_text("external secret")
    try:
        (source / "src" / "link.cpp").symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable")
    git(source, "add", "src/link.cpp")
    git(source, "commit", "-m", "Add link")
    git(source, "push", "origin", "master")
    workspace = Workspace(config, tmp_path / "state", "symlink")
    workspace.prepare(git(source, "rev-parse", "HEAD"))
    with pytest.raises(WorkspaceError, match="Symlink"):
        workspace.apply_edits([Edit(path="src/link.cpp", old="external", new="changed")])
    assert target.read_text() == "external secret"


def test_invalid_revision_and_empty_commit_rejected(repository, tmp_path):
    _, _, config, failing = repository
    workspace = Workspace(config, tmp_path / "state", "invalid")
    with pytest.raises(ValueError, match="full"):
        workspace.prepare("HEAD~1")
    workspace.prepare(failing)
    with pytest.raises(WorkspaceError, match="empty"):
        workspace.commit("Nothing")
