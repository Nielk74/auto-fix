"""Export exact Luna evaluation records and optional native fixture proofs.

Only explicitly supplied runs are read. This command makes no model/network calls.
The destination must not exist. Evidence is allowlisted, checked, and published
atomically; credentials cause rejection rather than silently changing recordings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

MODEL = "gpt-6-luna"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
TEXT_SUFFIXES = (".json", ".jsonl", ".xml", ".xml.raw", ".log", ".txt", ".diff")
CALL_FILES = {
    "request.json",
    "response.json",
    "metadata.json",
    "events.jsonl",
    "schema.json",
    "stderr.log",
}
STATE_FILES = {"result.json", "context.json", "events.jsonl", "fix.diff", "publication.json"}
SECRET_KEY = re.compile(
    r"^(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret|authorization)$", re.I
)
SECRET_TEXT = re.compile(
    r"(?:\b(?:Bearer|Basic)\s+[A-Za-z0-9_+/=-]{16,}|\bsk-[A-Za-z0-9_-]{20,}|"
    r"https?://[^\s/:@]+:[^\s/@]+@|"
    r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
    r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_+/=-]{12,})",
    re.I,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Unsafe run or case identifier")
    return value


def contained(path: Path, root: Path) -> Path:
    """Reject symlinks, including symlinked parent directories, before reading."""
    root = root.resolve()
    absolute = Path(os.path.abspath(path))
    if not absolute.is_relative_to(root):
        raise ValueError(f"Evidence path escapes its allowed root: {path.name}")
    for part in (absolute, *absolute.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f"Symlink evidence is not allowed: {path.name}")
    return absolute


def json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


class Bundle:
    def __init__(self, directory: Path, max_file_bytes: int):
        self.directory = directory
        self.max_file_bytes = max_file_bytes
        self.hashes: dict[str, str] = {}
        self.secrets = [
            value.encode()
            for key, value in os.environ.items()
            if re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", key, re.I) and len(value) >= 8
        ]

    def check(self, data: bytes, label: str) -> None:
        if len(data) > self.max_file_bytes:
            raise ValueError(f"Evidence exceeds the per-file byte limit: {label}")
        text = data.decode("utf-8", errors="surrogateescape")
        if any(secret in data for secret in self.secrets) or SECRET_TEXT.search(text):
            raise ValueError(f"Possible credential in evidence; export rejected: {label}")
        if label.endswith(".json"):

            def walk(value: Any) -> bool:
                if isinstance(value, dict):
                    return any(
                        (
                            SECRET_KEY.fullmatch(key)
                            and item not in (None, "", "<redacted>", "[REDACTED]")
                        )
                        or walk(item)
                        for key, item in value.items()
                    )
                return isinstance(value, list) and any(walk(item) for item in value)

            try:
                document = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                # Failed/truncated model responses are still auditable evidence.
                # Their surrounding metadata/events remain strictly validated.
                return
            if walk(document):
                raise ValueError(f"Possible credential field; export rejected: {label}")

    def write(self, relative: str, data: bytes) -> str:
        path = contained(self.directory / relative, self.directory)
        self.check(data, relative)
        sha = digest(data)
        previous = self.hashes.get(relative)
        if previous and previous != sha:
            raise ValueError(f"Conflicting artifact path: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.hashes[relative] = sha
        return sha

    def copy(self, source: Path, relative: str, root: Path, expected: str | None = None) -> str:
        source = contained(source, root)
        if not source.is_file():
            raise ValueError(f"Missing evidence: {source.name}")
        if source.stat().st_size > self.max_file_bytes:
            raise ValueError(f"Evidence exceeds the per-file byte limit: {source.name}")
        data = source.read_bytes()
        if expected is not None and (not HASH.fullmatch(expected) or digest(data) != expected):
            raise ValueError(f"Evidence SHA256 mismatch: {source.name}")
        return self.write(relative, data)

    def json(self, relative: str, value: Any) -> None:
        self.write(relative, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def allowed_native(path: Path) -> bool:
    return path.name.endswith(TEXT_SUFFIXES) and not any(
        part in {".git", "source", "build", "worktrees", "remote.git", "upstream"}
        or part.startswith(".auto-fix-build")
        for part in path.parts
    )


def native_files(directory: Path) -> list[Path]:
    """Prune caches before traversal; never recurse through a symlink."""
    files: list[Path] = []
    if not directory.exists():
        return files
    for base, directories, names in os.walk(directory, followlinks=False):
        base_path = Path(base)
        directories[:] = [
            name
            for name in directories
            if allowed_native(Path(name) / "placeholder.log")
            and not (base_path / name).is_symlink()
        ]
        for name in names:
            path = base_path / name
            if allowed_native(path.relative_to(directory)):
                files.append(path)
    return sorted(files)


def validate_call(call: Path, root: Path) -> dict[str, Any]:
    metadata = json_object(contained(call / "metadata.json", root))
    if metadata.get("model") != MODEL or metadata.get("transport") != "codex-cli":
        raise ValueError("Every exported call must attest gpt-6-luna via codex-cli")
    if metadata.get("live_inference") is False:
        raise ValueError("A model call cannot attest recorded replay as live inference")
    kind = metadata.get("kind")
    if kind not in {"repair", "investigation"}:
        raise ValueError("Unknown model call kind")
    request = json_object(contained(call / "request.json", root))
    if request.get("kind", "repair") != kind:
        raise ValueError("Model request and metadata kinds disagree")
    events = contained(call / "events.jsonl", root)
    if not events.is_file():
        raise ValueError("Missing model event stream; cannot attest tool isolation")
    for line in events.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Malformed model event stream")
        if event.get("type") in {
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "web_search",
            "collab_tool_call",
        }:
            raise ValueError("Prohibited CLI tool event in model evidence")
        item = event.get("item")
        if item is not None and (
            not isinstance(item, dict) or item.get("type") not in {"agent_message", "reasoning"}
        ):
            raise ValueError("Prohibited or unknown CLI tool event in model evidence")
    if type(metadata.get("returncode")) is not int:
        raise ValueError("Missing integer model return code")
    return metadata


def export_run(bundle: Bundle, name: str, source: Path) -> tuple[dict, list[dict]]:
    identifier(name)
    source = source.resolve()
    manifest = json_object(contained(source / "manifest.json", source))
    summary = json_object(contained(source / "summary.json", source))
    for document in (manifest, summary):
        if document.get("backend") != "codex" or document.get("model") != MODEL:
            raise ValueError("Only actual gpt-6-luna codex evaluations can be exported")
    if manifest.get("live_inference") is not True:
        raise ValueError("Run must attest actual live inference")
    prefix = f"results/{name}"
    for filename in ("manifest.json", "summary.json"):
        bundle.copy(source / filename, f"{prefix}/{filename}", source)
    for filename, sha in manifest.get("source_sha256", {}).items():
        if Path(filename).name != filename or not filename.endswith(".py"):
            raise ValueError("Unsafe implementation snapshot name")
        bundle.copy(
            source / "implementation" / filename, f"{prefix}/implementation/{filename}", source, sha
        )
    cases: list[dict] = []
    seen: set[str] = set()
    for entry in summary["cases"]:
        case_id = identifier(entry["case"])
        if case_id in seen or entry.get("model") != MODEL:
            raise ValueError("Duplicate case or incorrect model in run summary")
        seen.add(case_id)
        case = contained(source / case_id, source)
        for filename in ("score.json", "requests.json", "pull-requests.json"):
            if (case / filename).is_file():
                bundle.copy(case / filename, f"{prefix}/{case_id}/{filename}", source)
        calls = sorted((case / "model").glob("call-*"), key=lambda p: int(p.name[5:]))
        if [call.name for call in calls] != [f"call-{i}" for i in range(1, len(calls) + 1)]:
            raise ValueError("Model calls must form a contiguous sequence")
        metadata = []
        for call in calls:
            metadata.append(validate_call(call, source))
            for filename in sorted(CALL_FILES):
                if (call / filename).is_file():
                    relative = (call / filename).relative_to(source).as_posix()
                    bundle.copy(call / filename, f"{prefix}/{relative}", source)
        if len(calls) != len(entry.get("model_calls", [])):
            raise ValueError("Summary and model call directory counts disagree")
        if any(call.get("model") != MODEL for call in entry.get("model_calls", [])):
            raise ValueError("Summary contains a non-Luna model call")
        for path in native_files(case / "preflight"):
            bundle.copy(path, f"{prefix}/{path.relative_to(source).as_posix()}", source)
        for run in sorted((case / "state" / "runs").glob("*")):
            contained(run, source)
            for path in sorted(run.iterdir()):
                if path.name in STATE_FILES or re.fullmatch(
                    r"(?:proposal|investigation|inspection-evidence)-\d+\.json", path.name
                ):
                    bundle.copy(path, f"{prefix}/{path.relative_to(source).as_posix()}", source)
            for path in native_files(run / "evidence"):
                bundle.copy(path, f"{prefix}/{path.relative_to(source).as_posix()}", source)
        result_path = Path(entry["result"])
        if not result_path.is_absolute():
            result_path = source / result_path
        contained(result_path, case / "state" / "runs")
        result = json_object(result_path)
        cases.append({"entry": entry, "calls": calls, "metadata": metadata, "result": result})
    if manifest.get("case_ids") != [entry["case"] for entry in summary["cases"]]:
        raise ValueError("Manifest case selection and summary disagree")
    return manifest, cases


def export_recordings(
    bundle: Bundle,
    name: str,
    source: Path,
    manifest: dict,
    cases: list[dict],
    config: dict,
    workspace: Path,
    seen: set[str],
) -> list[dict]:
    from auto_fix.models import Investigation, Proposal

    paths = {}
    for key in ("project_file", "cases_file"):
        relative = config[key]
        path = contained(workspace / relative, workspace)
        expected = manifest["project_sha256" if key == "project_file" else "cases_sha256"]
        bundle.copy(path, Path(relative).as_posix(), workspace, expected)
        paths[key] = Path(relative).as_posix()
        paths[key.replace("_file", "_sha256")] = expected
    selected = config.get("case_ids")
    available = {case["entry"]["case"] for case in cases}
    if selected is not None and (
        len(set(selected)) != len(selected) or not set(selected) <= available
    ):
        raise ValueError("Recording selection contains duplicate or unknown cases")
    entries = []
    for case in cases:
        entry, calls, metadata, result = (
            case[key] for key in ("entry", "calls", "metadata", "result")
        )
        case_id = entry["case"]
        if selected is not None and case_id not in selected:
            continue
        if selected is None and not entry["success"]:
            continue
        report = result.get("verification", {}).get("report", {})
        if not (
            entry["success"]
            and result.get("status") == "published"
            and report.get("passed")
            and report.get("failed") == []
            and calls
        ):
            raise ValueError("A recording candidate lacks successful native verification")
        if case_id in seen:
            raise ValueError("Case selected for recordings from more than one run")
        seen.add(case_id)
        recorded_calls = []
        for call, meta in zip(calls, metadata, strict=True):
            if meta["returncode"] != 0:
                raise ValueError("Replay candidate contains an unsuccessful live model call")
            kind = meta.get("kind", "repair")
            response = (call / "response.json").read_bytes()
            (Investigation if kind == "investigation" else Proposal).model_validate_json(response)
            relative = f"recordings/expanded/{case_id}/{call.name}"
            sha = {}
            for filename in ("metadata.json", "response.json", "request.json"):
                sha[filename] = bundle.copy(call / filename, f"{relative}/{filename}", source)
            recorded_calls.append(
                {
                    "directory": call.name,
                    "kind": kind,
                    "metadata_sha256": sha["metadata.json"],
                    "response_sha256": sha["response.json"],
                }
            )
        entries.append(
            {
                "id": case_id,
                **paths,
                "recordings_directory": f"recordings/expanded/{case_id}",
                "prompt": manifest["prompt_version"],
                "max_inspections": manifest["max_inspections"],
                "structured_diagnostics": manifest["structured_diagnostics"],
                "reasoning_effort": manifest["reasoning_effort"],
                "max_attempts": manifest["max_attempts"],
                "expected_completion": True,
                "expected_test_names": entry["baseline_failed"],
                "recorded_calls": recorded_calls,
                "ci_tags": ["windows-representative"]
                if case_id in config.get("windows_case_ids", [])
                else [],
                "source_run": name,
            }
        )
    return entries


def export_fixture_proofs(bundle: Bundle, index: Path, workspace: Path) -> dict:
    """Follow explicit registry paths, preserving exact files as SHA-deduplicated blobs."""
    pending: list[tuple[Path, str | None]] = [(contained(index, workspace), None)]
    mapping: dict[str, dict] = {}
    checked: set[str] = set()
    inspected_directories: set[Path] = set()

    def queue(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith((".auto-fix/", "evaluation/")):
                    expected = item.get("sha256") if isinstance(item, dict) else None
                    pending.append((workspace / key, expected))
                if isinstance(item, str) and item.startswith((".auto-fix/", "evaluation/")):
                    expected = value.get(f"{key}_sha256")
                    if key == "path":
                        expected = value.get("sha256", expected)
                    if key in {"prototype_manifest", "active_manifest"}:
                        expected = value.get(key.replace("_manifest", "_sha256"), expected)
                    if key == "junit":
                        expected = value.get("report", {}).get("raw_sha256", expected)
                    pending.append((workspace / item, expected))
                queue(item)
        elif isinstance(value, list):
            for item in value:
                queue(item)

    while pending:
        source, expected = pending.pop()
        source = contained(source, workspace)
        relative = source.relative_to(workspace).as_posix()
        if source.is_dir():
            if source not in inspected_directories:
                inspected_directories.add(source)
                pending.extend((path, None) for path in native_files(source))
            continue
        if not allowed_native(Path(relative)):
            continue
        if not source.is_file():
            raise ValueError(f"Missing referenced fixture proof: {relative}")
        data = source.read_bytes()
        sha = digest(data)
        if expected is not None:
            if not isinstance(expected, str) or not HASH.fullmatch(expected) or sha != expected:
                raise ValueError(f"Fixture proof SHA256 mismatch: {relative}")
            checked.add(relative)
        if relative in mapping:
            continue
        suffix = ".xml.raw" if source.name.endswith(".xml.raw") else source.suffix
        output = f"fixture-proofs/blobs/{sha}{suffix}"
        bundle.write(output, data)
        mapping[relative] = {"path": output, "sha256": sha, "bytes": len(data)}
        # The sibling raw report/log/proof metadata belongs to the same native run.
        if relative.startswith(".auto-fix/") and source.parent not in inspected_directories:
            inspected_directories.add(source.parent)
            pending.extend(
                (path, None)
                for path in source.parent.iterdir()
                if path.is_file() and allowed_native(Path(path.name))
            )
        if source.name.endswith(".json"):
            document = json.loads(data)
            if source.name == "SHA256SUMS.json" and isinstance(document, dict):
                pending.extend(
                    (source.parent / path, sha)
                    for path, sha in document.items()
                    if isinstance(sha, str) and allowed_native(Path(path))
                )
            queue(document)
    result = {
        "schema_version": 1,
        "source_index": index.relative_to(workspace).as_posix(),
        "files": dict(sorted(mapping.items())),
        "verified_source_hashes": sorted(checked),
        "file_count": len(mapping),
        "unique_blobs": len({item["path"] for item in mapping.values()}),
        "note": "Native authoring evidence; oracle fixtures are never repair-model input.",
    }
    bundle.json("fixture-proofs/index.json", result)
    return result


def export(
    runs: dict[str, Path],
    destination: Path,
    *,
    workspace: Path,
    recordings: dict[str, dict] | None = None,
    fixture_proofs: Path | None = None,
    max_file_bytes: int = 64 * 1024 * 1024,
) -> dict:
    workspace = workspace.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must not already exist")
    if not runs and fixture_proofs is None:
        raise ValueError("Supply at least one run or fixture proof index")
    if max_file_bytes < 1:
        raise ValueError("Byte limit must be positive")
    if recordings and not set(recordings) <= set(runs):
        raise ValueError("Recording source must name an explicitly supplied run")
    for source in runs.values():
        if destination.is_relative_to(source.resolve()):
            raise ValueError("Destination cannot be inside a source run")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        bundle = Bundle(staging, max_file_bytes)
        index: dict = {
            "schema_version": 1,
            "model": MODEL,
            "live_inference_transport": "codex-cli",
            "runs": [],
        }
        recording_entries: list[dict] = []
        recorded_cases: set[str] = set()
        for name, source in runs.items():
            manifest, cases = export_run(bundle, name, source)
            index["runs"].append(
                {
                    "name": name,
                    "manifest": f"results/{name}/manifest.json",
                    "summary": f"results/{name}/summary.json",
                    "cases": len(cases),
                    "model_calls": sum(len(case["calls"]) for case in cases),
                }
            )
            if recordings and name in recordings:
                recording_entries.extend(
                    export_recordings(
                        bundle,
                        name,
                        source.resolve(),
                        manifest,
                        cases,
                        recordings[name],
                        workspace,
                        recorded_cases,
                    )
                )
        if recordings:
            bundle.json(
                "recordings/expanded/index.json",
                {
                    "schema_version": 1,
                    "model": MODEL,
                    "live_inference_transport": "codex-cli",
                    "entries": recording_entries,
                },
            )
            index["recordings"] = len(recording_entries)
        if fixture_proofs is not None:
            fixture = contained(workspace / fixture_proofs, workspace)
            proof = export_fixture_proofs(bundle, fixture, workspace)
            index["fixture_proofs"] = {key: proof[key] for key in ("file_count", "unique_blobs")}
        bundle.json("index.json", index)
        # The checksum manifests deliberately do not checksum themselves.
        hashes = dict(sorted(bundle.hashes.items()))
        (staging / "SHA256SUMS.json").write_text(
            json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "SHA256SUMS").write_text(
            "".join(f"{sha}  {path}\n" for path, sha in hashes.items()), encoding="utf-8"
        )
        staging.rename(destination)
        return index
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", default=[], help="NAME=actual_run_directory")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--recordings",
        type=Path,
        help="JSON mapping runs to project_file, cases_file, optional case_ids/windows_case_ids",
    )
    parser.add_argument(
        "--fixture-proofs", type=Path, help="Native proof registry relative to workspace"
    )
    parser.add_argument("--max-file-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    runs = {}
    for value in args.run:
        name, path = value.split("=", 1)
        identifier(name)
        if name in runs:
            raise ValueError("Duplicate supplied run name")
        runs[name] = Path(path)
    print(
        json.dumps(
            export(
                runs,
                args.destination,
                workspace=args.workspace,
                recordings=json_object(args.recordings) if args.recordings else None,
                fixture_proofs=args.fixture_proofs,
                max_file_bytes=args.max_file_bytes,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
