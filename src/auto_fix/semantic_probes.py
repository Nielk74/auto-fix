"""Trusted, optional native checks added after development semantic review.

These probes complement unchanged upstream suites. They are operator-owned
validation, not additional benchmark defects or evidence of holdout performance.
The generated C++ and CMake files stay inside the candidate's ignored build tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from xml.etree import ElementTree as XML

PROBE_CLASS = "SemanticGuard.DurationMinUnit"
CHECK_NAMES = (
    "InputFinite",
    "TruncExactMinimumUnit",
    "FloorExactMinimumUnit",
    "CeilExactMinimumUnit",
)

# INT64_MIN is a finite Duration, but its absolute value saturates to infinity.
# An exact multiple must survive rounding even when the unit is negative.
DURATION_PROBE = r"""#include <cstdint>
#include <iostream>
#include <limits>
#include "absl/time/time.h"

bool Check(bool condition, const char* name, absl::Duration result) {
  std::cout << "AUTO_FIX_PROBE\t" << name << "\t"
            << (condition ? "PASS" : "FAIL") << "\t"
            << absl::FormatDuration(result) << "\n";
  return condition;
}

int main() {
  const absl::Duration d = absl::Seconds((std::numeric_limits<int64_t>::min)());
  const absl::Duration unit = d;
  bool okay = Check(d != absl::InfiniteDuration() && d != -absl::InfiniteDuration(),
                    "InputFinite", d);
  const absl::Duration truncated = absl::Trunc(d, unit);
  const absl::Duration floored = absl::Floor(d, unit);
  const absl::Duration ceiling = absl::Ceil(d, unit);
  okay &= Check(truncated == d, "TruncExactMinimumUnit", truncated);
  okay &= Check(floored == d, "FloorExactMinimumUnit", floored);
  okay &= Check(ceiling == d, "CeilExactMinimumUnit", ceiling);
  return okay ? 0 : 1;
}
"""

CMAKE_PROJECT = """cmake_minimum_required(VERSION 3.20)
project(auto_fix_semantic_probe LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(ABSL_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ABSL_BUILD_TEST_HELPERS OFF CACHE BOOL "" FORCE)
set(ABSL_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
add_subdirectory("${AUTO_FIX_ABSEIL_SOURCE}" abseil)
add_executable(auto_fix_duration_min_unit probe.cc)
target_link_libraries(auto_fix_duration_min_unit PRIVATE absl::time)
set_target_properties(auto_fix_duration_min_unit PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin")
"""


def duration_min_unit_command() -> list[str]:
    """Return a trusted BuildConfig.additional_tests entry for time suites."""
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--workspace",
        ".",
        "--junit",
        "{junit}",
        "--probe",
        "duration-min-unit",
    ]


def _command(argv: list[str], cwd: Path, log: Path) -> dict:
    """Inherit Builder's process group and its configured whole-command timeout."""
    print(f"Semantic probe command: {json.dumps(argv)}", flush=True)
    try:
        with log.open("wb") as output_file:
            result = subprocess.run(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
        returncode = result.returncode
        output = log.read_bytes().decode("utf-8", errors="replace")
    except OSError as error:
        returncode, output = 127, f"Unable to execute semantic probe command: {error}\n"
    log.write_text(output, encoding="utf-8")
    print(output, end="" if output.endswith("\n") else "\n", flush=True)
    return {"argv": argv, "returncode": returncode, "output": output, "log": str(log)}


def _native_checks(output: str) -> dict[str, tuple[bool, str]]:
    checks: dict[str, tuple[bool, str]] = {}
    for line in output.splitlines():
        if not line.startswith("AUTO_FIX_PROBE\t"):
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4 or parts[1] not in CHECK_NAMES or parts[2] not in {"PASS", "FAIL"}:
            raise ValueError("Native probe emitted an invalid assertion record")
        if parts[1] in checks:
            raise ValueError(f"Native probe repeated assertion: {parts[1]}")
        checks[parts[1]] = parts[2] == "PASS", parts[3]
    if set(checks) != set(CHECK_NAMES):
        raise ValueError("Native probe did not execute every trusted assertion")
    return checks


def _junit(path: Path, checks: dict[str, tuple[bool, str]], error: str = "") -> None:
    suite = XML.Element("testsuite", name=PROBE_CLASS)
    for name in CHECK_NAMES:
        if name not in checks:
            continue
        passed, actual = checks[name]
        case = XML.SubElement(suite, "testcase", classname=PROBE_CLASS, name=name)
        if not passed:
            failure = XML.SubElement(case, "failure", message="Exact finite multiple changed")
            failure.text = (
                "For finite d = unit = Seconds(INT64_MIN), rounding must preserve d. "
                f"{name} produced {actual}."
            )
    if error:
        case = XML.SubElement(suite, "testcase", classname=PROBE_CLASS, name="Execution")
        XML.SubElement(
            case, "error", message="Native semantic probe could not complete"
        ).text = error
    path.parent.mkdir(parents=True, exist_ok=True)
    XML.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def run_probe(workspace: Path, junit: Path) -> int:
    workspace = workspace.resolve()
    if junit.exists() or junit.is_symlink():
        print("Semantic probe requires a fresh JUnit destination", file=sys.stderr)
        return 2
    junit = junit.resolve()
    checks: dict[str, tuple[bool, str]] = {}
    error = ""
    evidence: dict = {
        "probe": "duration-min-unit",
        "classification": "posthoc-development-semantic-guard",
        "workspace": str(workspace),
        "commands": [],
        "probe_source_sha256": hashlib.sha256(DURATION_PROBE.encode()).hexdigest(),
    }
    try:
        if (
            not (workspace / "absl/time/time.h").is_file()
            or not (workspace / "CMakeLists.txt").is_file()
        ):
            raise ValueError("Workspace is not an Abseil CMake source tree")
        root = workspace / ".auto-fix-build/semantic-probes/duration-min-unit"
        if not root.resolve().is_relative_to(workspace):
            raise ValueError("Semantic probe output must remain inside the candidate workspace")
        project, build = root / "project", root / "build"
        logs = root / "runs" / uuid.uuid4().hex[:12]
        project.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True)
        (project / "probe.cc").write_text(DURATION_PROBE, encoding="utf-8")
        (project / "CMakeLists.txt").write_text(CMAKE_PROJECT, encoding="utf-8")
        evidence["candidate_duration_sha256"] = hashlib.sha256(
            (workspace / "absl/time/duration.cc").read_bytes()
        ).hexdigest()
        generator = ["-G", "Ninja"] if os.name != "nt" and shutil.which("ninja") else []
        configure = [
            "cmake",
            "-S",
            str(project),
            "-B",
            str(build),
            *generator,
            f"-DAUTO_FIX_ABSEIL_SOURCE={workspace}",
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        compile_command = [
            "cmake",
            "--build",
            str(build),
            "--config",
            "Release",
            "--parallel",
            "4",
            *([] if os.name == "nt" else ["--clean-first"]),
            "--target",
            "auto_fix_duration_min_unit",
            *(["--", "/t:Rebuild"] if os.name == "nt" else []),
        ]
        executable = (
            build
            / "bin"
            / (
                "auto_fix_duration_min_unit.exe"
                if os.name == "nt"
                else "auto_fix_duration_min_unit"
            )
        )
        for stage, command in (("configure", configure), ("build", compile_command)):
            result = _command(command, workspace, logs / f"{stage}.log")
            evidence["commands"].append(result)
            if result["returncode"]:
                raise ValueError(f"Semantic probe {stage} failed with exit {result['returncode']}")
        result = _command([str(executable)], workspace, logs / "native.log")
        evidence["commands"].append(result)
        checks = _native_checks(result["output"])
        if result["returncode"] and all(passed for passed, _ in checks.values()):
            raise ValueError(f"Semantic probe process failed with exit {result['returncode']}")
    except Exception as exc:
        error = str(exc)
        print(f"Invalid semantic probe evidence: {error}", file=sys.stderr, flush=True)
    _junit(junit, checks, error)
    evidence.update(error=error, checks=checks)
    junit.with_suffix(".evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return int(bool(error) or not checks or any(not passed for passed, _ in checks.values()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--probe", choices=["duration-min-unit"], required=True)
    args = parser.parse_args(argv)
    return run_probe(args.workspace, args.junit)


if __name__ == "__main__":
    raise SystemExit(main())
