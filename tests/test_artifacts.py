from __future__ import annotations

import io
import json
import zipfile

import pytest

from auto_fix import artifacts


def evidence(tmp_path):
    run = tmp_path / "runs" / "tc-1"
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({"status": "ready"}), encoding="utf-8")
    return run


def test_downloads_keep_large_text_redacted_and_binary_bytes_unchanged(tmp_path, monkeypatch):
    run = evidence(tmp_path)
    monkeypatch.setenv("AUTO_FIX_TEST_TOKEN", "secret-download-value")
    text = "a" * (1024 * 1024 - 8) + "secret-download-value" + "b" * 2_000_000
    (run / "native.log").write_text(text, encoding="utf-8")
    (run / "image.png").write_bytes(b"\x89PNG\x00\xff\x01")
    handle, kind, name = artifacts.download(tmp_path, "runs/tc-1", "native.log")
    with handle:
        data = handle.read()
    assert name == "native.log" and kind.startswith("text/plain")
    assert b"secret-download-value" not in data
    assert data == text.replace("secret-download-value", "[REDACTED]").encode()
    handle, _, _ = artifacts.download(tmp_path, "runs/tc-1", "image.png")
    with handle:
        assert handle.read() == b"\x89PNG\x00\xff\x01"


def test_bundle_excludes_checkpoints_and_traversal_and_redacts_text(tmp_path, monkeypatch):
    run = evidence(tmp_path)
    monkeypatch.setenv("AUTO_FIX_TEST_SECRET", "bundle-sensitive-value")
    (run / "evidence.log").write_text("bundle-sensitive-value", encoding="utf-8")
    (run / "checkpoints.sqlite").write_bytes(b"private state")
    (tmp_path / "outside.log").write_text("outside", encoding="utf-8")
    assert artifacts.download(tmp_path, "runs/tc-1", "../../outside.log") is None
    assert artifacts.download(tmp_path, "runs/tc-1", "checkpoints.sqlite") is None
    assert artifacts.download(tmp_path, "runs/missing", "") is None
    handle, kind, name = artifacts.download(tmp_path, "runs/tc-1", "")
    with handle:
        bundle = zipfile.ZipFile(io.BytesIO(handle.read()))
    assert kind == "application/zip" and name.endswith(".zip")
    assert set(bundle.namelist()) == {"result.json", "evidence.log"}
    assert bundle.read("evidence.log") == b"[REDACTED]"


@pytest.mark.parametrize(
    "relative",
    [
        "CHECKPOINTS.SQLITE",
        "Checkpoints.sqlite-wal",
        "nested/CHECKPOINTS.SQLITE-shm",
    ],
)
def test_checkpoint_exclusion_is_case_insensitive_in_requests_and_bundles(tmp_path, relative):
    run = evidence(tmp_path)
    target = run / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"private checkpoint data")
    assert artifacts.download(tmp_path, "runs/tc-1", relative) is None
    handle, _, _ = artifacts.download(tmp_path, "runs/tc-1", "")
    with handle, zipfile.ZipFile(handle) as bundle:
        assert relative not in bundle.namelist()


@pytest.mark.parametrize("name", ["trace.stderr", "native-output", "trace.data"])
def test_unknown_text_formats_are_redacted_in_individual_and_zip_downloads(
    tmp_path, monkeypatch, name
):
    run = evidence(tmp_path)
    monkeypatch.setenv("AUTO_FIX_TEST_SECRET", "unlisted-format-secret")
    (run / name).write_bytes(b"Trace: unlisted-format-secret\n")
    handle, _, _ = artifacts.download(tmp_path, "runs/tc-1", name)
    with handle:
        assert handle.read() == b"Trace: [REDACTED]\n"
    handle, _, _ = artifacts.download(tmp_path, "runs/tc-1", "")
    with handle, zipfile.ZipFile(handle) as bundle:
        assert bundle.read(name) == b"Trace: [REDACTED]\n"
