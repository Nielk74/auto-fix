"""Download evidence separately from the dashboard's bounded text previews."""

from __future__ import annotations

import codecs
import mimetypes
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

from auto_fix import history

TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".log",
    ".txt",
    ".diff",
    ".patch",
    ".xml",
    ".yaml",
    ".yml",
    ".md",
    ".csv",
    ".out",
    ".err",
    ".html",
    ".ps1",
    ".cpp",
    ".h",
}


def _is_text(path: Path, source: BinaryIO) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    kind = mimetypes.guess_type(path.name)[0] or ""
    if kind.startswith(("image/", "audio/", "video/")):
        return False
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        while chunk := source.read(1024 * 1024):
            if b"\x00" in chunk:
                return False
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
        return True
    except UnicodeError:
        return False
    finally:
        source.seek(0)


def _copy(source: BinaryIO, destination: BinaryIO, text: bool) -> None:
    secrets = (
        [
            value.encode("utf-8")
            for name, value in os.environ.items()
            if len(value) >= 8
            and any(word in name.upper() for word in ("TOKEN", "PASSWORD", "SECRET", "API_KEY"))
        ]
        if text
        else []
    )
    if not secrets:
        shutil.copyfileobj(source, destination, length=1024 * 1024)
        return
    keep = max(map(len, secrets)) - 1
    pending = b""
    while True:
        chunk = source.read(1024 * 1024)
        pending += chunk
        cut = max(0, len(pending) - keep) if chunk else len(pending)
        # Keep a whole secret when it crosses the chunk boundary.
        if chunk:
            previous = -1
            while previous != cut:
                previous = cut
                for secret in secrets:
                    start = pending.find(secret, max(0, cut - len(secret) + 1))
                    if start >= 0 and start < cut < start + len(secret):
                        cut = start
        ready, pending = pending[:cut], pending[cut:]
        for secret in sorted(secrets, key=len, reverse=True):
            ready = ready.replace(secret, b"[REDACTED]")
        destination.write(ready)
        if not chunk:
            return


def _allowed(run: Path, path: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and path.resolve().is_relative_to(run.resolve())
        and not any(
            part.casefold().startswith("checkpoints.sqlite") for part in path.relative_to(run).parts
        )
        and not any(parent.is_symlink() for parent in path.parents if parent != run.parent)
    )


def download(root: Path, run_id: str, relative: str) -> tuple[BinaryIO, str, str] | None:
    run = history.discover_runs(root).get(run_id)
    if run is None or run.is_symlink() or not run.resolve().is_relative_to(root.resolve()):
        return None
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        if relative:
            path = run / relative
            if not _allowed(run, path):
                output.close()
                return None
            with path.open("rb") as source:
                text = _is_text(path, source)
                _copy(source, output, text)
            kind = (
                "text/plain"
                if text
                else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            filename = path.name
        else:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(run.rglob("*")):
                    if _allowed(run, path):
                        with (
                            path.open("rb") as source,
                            bundle.open(path.relative_to(run).as_posix(), "w") as entry,
                        ):
                            _copy(source, entry, _is_text(path, source))
            kind, filename = "application/zip", run.name + "-evidence.zip"
        output.seek(0)
        return output, kind, filename
    except (OSError, ValueError):
        output.close()
        return None
