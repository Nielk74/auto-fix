"""Compile trusted guards against pinned clean upstream; zero model inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def git(directory: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=directory,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never"),
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=["abseil", "fmt"], required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        parser.error("Use a fresh output directory")
    directory.mkdir(parents=True, exist_ok=True)
    workspace = Path(__file__).resolve().parents[1]
    project_file = workspace / "evaluation/expanded" / f"{args.project}-validation-v6.json"
    project = json.loads(project_file.read_bytes())
    result = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "classification": "pinned-clean-native-guard-smoke",
        "live_model_calls": 0,
        "platform": sys.platform,
        "python": sys.version,
        "project": args.project,
        "project_sha256": hashlib.sha256(project_file.read_bytes()).hexdigest(),
        "expected_commit": project["commit"],
        "success": False,
    }
    source = directory / "source"
    source.mkdir()
    try:
        git(source, "init", "--quiet")
        git(source, "remote", "add", "origin", project["repository"])
        git(source, "fetch", "--depth", "1", "origin", project["commit"])
        git(source, "-c", "core.autocrlf=false", "checkout", "--detach", "FETCH_HEAD")
        result["actual_commit"] = git(source, "rev-parse", "HEAD")
        if result["actual_commit"] != project["commit"]:
            raise ValueError("Fetched source differs from the pinned upstream commit")
        with (source / ".git/info/exclude").open("a", encoding="utf-8") as output:
            output.write("\n/.auto-fix-build/\n")
        if git(source, "status", "--porcelain"):
            raise ValueError("Fresh source checkout is dirty")
        if args.project == "fmt":
            from auto_fix import fmt_semantic_probes as module

            probe = module.PROBE_ID
        else:
            from auto_fix import semantic_probes as module

            probe = "duration-rounding-boundaries"
        result["probe"] = probe
        result["implementation_sha256"] = hashlib.sha256(
            Path(module.__file__).read_bytes()
        ).hexdigest()
        junit = directory / "junit.xml"
        result["native_returncode"] = module.run_probe(source, junit, probe)
        from auto_fix.build import parse_junit

        report = parse_junit(junit)
        result["report"] = report.model_dump()
        result["junit_sha256"] = hashlib.sha256(junit.read_bytes()).hexdigest()
        result["source_status_after"] = git(source, "status", "--porcelain")
        expected_count = 12 if args.project == "fmt" else 10
        result["success"] = (
            result["native_returncode"] == 0
            and len(report.passed) == expected_count
            and not report.failed
            and not report.skipped
            and not result["source_status_after"]
        )
        if not result["success"]:
            raise ValueError("Trusted guard did not pass completely on pinned clean source")
    except Exception as error:
        result["error"] = str(error)
        result["success"] = False
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
