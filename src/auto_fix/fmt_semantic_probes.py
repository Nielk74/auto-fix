"""Versioned operator-owned native fmt checks from development semantic review.

These supplement unchanged upstream suites. They add no benchmark defects and
make no holdout claim. The probe compiles directly against candidate headers.
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

PROBE_ID = "fmt-contract-boundaries"
PROBE_CLASS = "SemanticGuard.FmtContractBoundaries"
CHECKS = {
    "DynamicStringPositive": ('sprintf("%.*s", 3, "abcdef")', "abc"),
    "DynamicStringZero": ('sprintf("%.*s", 0, "abcdef")', ""),
    "DynamicStringNegative": ('sprintf("%.*s", -3, "abcdef")', ""),
    "DynamicFloatPositive": ('sprintf("%.*f", 2, 1.25)', "1.25"),
    "DynamicFloatZero": ('sprintf("%.*f", 0, 1.25)', "1"),
    "DynamicFloatNegative": ('sprintf("%.*f", -3, 1.25)', "1"),
    "StaticIntegerPrecisionThree": ('sprintf("%.3d", 12)', "012"),
    "DynamicIntegerPrecisionThree": ('sprintf("%.*d", 3, 12)', "012"),
    "StaticIntegerPrecisionFour": ('sprintf("%.4d", 12)', "0012"),
    "DynamicIntegerPrecisionFour": ('sprintf("%.*d", 4, 12)', "0012"),
    "ChronoNanosecondsMinimum": (
        'format("{:%Y-%m-%d %H:%M:%S}", sys_time<nanoseconds>(nanoseconds::min()))',
        "1677-09-21 00:12:43.145224192",
    ),
    "ChronoNanosecondsMaximum": (
        'format("{:%Y-%m-%d %H:%M:%S}", sys_time<nanoseconds>(nanoseconds::max()))',
        "2262-04-11 23:47:16.854775807",
    ),
}
WINDOWS_MINIMUM = "<exception:time_t value out of range>"

CPP_PROBE = r"""#include <chrono>
#include <exception>
#include <iostream>
#include <limits>
#include <string>
#include "fmt/chrono.h"
#include "fmt/printf.h"

void Hex(const std::string& text) {
  constexpr char digits[] = "0123456789abcdef";
  for (unsigned char c : text) std::cout << digits[c >> 4] << digits[c & 15];
}

template <typename Operation>
bool Check(const char* name, const char* expected, Operation operation) {
  std::string actual;
  try { actual = operation(); }
  catch (const std::exception& error) { actual = "<exception:" + std::string(error.what()) + ">"; }
  catch (...) { actual = "<unknown exception>"; }
  const bool okay = actual == expected;
  std::cout << "AUTO_FIX_FMT\t" << name << "\t" << (okay ? "PASS" : "FAIL") << "\t";
  Hex(actual);
  std::cout << "\t";
  Hex(expected);
  std::cout << std::endl;
  return okay;
}

int main() {
  bool okay = true;
  okay &= Check("DynamicStringPositive", "abc", [] { return fmt::sprintf("%.*s", 3, "abcdef"); });
  okay &= Check("DynamicStringZero", "", [] { return fmt::sprintf("%.*s", 0, "abcdef"); });
  okay &= Check("DynamicStringNegative", "", [] { return fmt::sprintf("%.*s", -3, "abcdef"); });
  okay &= Check("DynamicFloatPositive", "1.25", [] { return fmt::sprintf("%.*f", 2, 1.25); });
  okay &= Check("DynamicFloatZero", "1", [] { return fmt::sprintf("%.*f", 0, 1.25); });
  okay &= Check("DynamicFloatNegative", "1", [] { return fmt::sprintf("%.*f", -3, 1.25); });
  okay &= Check("StaticIntegerPrecisionThree", "012", [] { return fmt::sprintf("%.3d", 12); });
  okay &= Check("DynamicIntegerPrecisionThree", "012", [] { return fmt::sprintf("%.*d", 3, 12); });
  okay &= Check("StaticIntegerPrecisionFour", "0012", [] { return fmt::sprintf("%.4d", 12); });
  okay &= Check("DynamicIntegerPrecisionFour", "0012", [] { return fmt::sprintf("%.*d", 4, 12); });
  using Nanoseconds = std::chrono::nanoseconds;
#ifdef _WIN32
  const char* minimum_expected = "<exception:time_t value out of range>";
#else
  const char* minimum_expected = "1677-09-21 00:12:43.145224192";
#endif
  okay &= Check("ChronoNanosecondsMinimum", minimum_expected, [] {
    return fmt::format("{:%Y-%m-%d %H:%M:%S}", fmt::sys_time<Nanoseconds>((Nanoseconds::min)()));
  });
  okay &= Check("ChronoNanosecondsMaximum", "2262-04-11 23:47:16.854775807", [] {
    return fmt::format("{:%Y-%m-%d %H:%M:%S}", fmt::sys_time<Nanoseconds>((Nanoseconds::max)()));
  });
  return okay ? 0 : 1;
}
"""

CMAKE_PROJECT = """cmake_minimum_required(VERSION 3.20)
project(auto_fix_fmt_guard LANGUAGES CXX)
add_executable(af_fmt_probe probe.cc)
target_compile_features(af_fmt_probe PRIVATE cxx_std_17)
target_compile_definitions(af_fmt_probe PRIVATE FMT_HEADER_ONLY=1)
target_include_directories(af_fmt_probe PRIVATE "${AUTO_FIX_FMT_SOURCE}/include")
if(MSVC)
  target_compile_options(af_fmt_probe PRIVATE /utf-8)
endif()
set_target_properties(af_fmt_probe PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin")
if(CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang|AppleClang)$" AND NOT MSVC)
  target_compile_options(af_fmt_probe PRIVATE -fsanitize=undefined -fno-sanitize-recover=undefined)
  target_link_options(af_fmt_probe PRIVATE -fsanitize=undefined -fno-sanitize-recover=undefined)
  file(WRITE "${CMAKE_BINARY_DIR}/sanitizer.txt" "undefined-nonrecovering")
else()
  file(WRITE "${CMAKE_BINARY_DIR}/sanitizer.txt" "unavailable-native-output-checks-only")
endif()
"""


def fmt_contract_command(probe: str = PROBE_ID) -> list[str]:
    if probe != PROBE_ID:
        raise ValueError("Unknown fmt semantic probe")
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--workspace",
        ".",
        "--junit",
        "{junit}",
        "--probe",
        probe,
    ]


def _expected(name: str, *, windows: bool) -> str:
    if windows and name == "ChronoNanosecondsMinimum":
        return WINDOWS_MINIMUM
    return CHECKS[name][1]


def _native_checks(output: str, *, windows: bool = False) -> dict[str, tuple[bool, str]]:
    checks = {}
    for line in output.splitlines():
        if not line.startswith("AUTO_FIX_FMT\t"):
            continue
        parts = line.split("\t")
        if len(parts) != 5 or parts[1] not in CHECKS or parts[2] not in {"PASS", "FAIL"}:
            raise ValueError("Native fmt probe emitted an invalid assertion record")
        _, name, status, actual_hex, expected_hex = parts
        if name in checks:
            raise ValueError(f"Native fmt probe repeated assertion: {name}")
        try:
            actual = bytes.fromhex(actual_hex).decode("utf-8")
            expected = bytes.fromhex(expected_hex).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Native fmt assertion has invalid UTF-8 hex values") from exc
        if expected != _expected(name, windows=windows) or (status == "PASS") != (
            actual == expected
        ):
            raise ValueError("Native fmt assertion disagrees with its trusted expected value")
        checks[name] = status == "PASS", actual
    if set(checks) != set(CHECKS):
        raise ValueError("Native fmt probe did not execute every trusted assertion")
    return checks


def _junit(path: Path, checks: dict, error: str = "", *, windows: bool = False) -> None:
    suite = XML.Element("testsuite", name=PROBE_CLASS)
    for name, (operation, _) in CHECKS.items():
        if name not in checks:
            continue
        passed, actual = checks[name]
        case = XML.SubElement(suite, "testcase", classname=PROBE_CLASS, name=name)
        if not passed:
            node = XML.SubElement(case, "failure", message="Fmt public formatting contract changed")
            node.text = (
                f"fmt::{operation} must produce {json.dumps(_expected(name, windows=windows))}; "
                f"actual = {json.dumps(actual)}. Negative dynamic precision is clamped to zero "
                "by the pinned fmt API."
            )
    if error:
        case = XML.SubElement(suite, "testcase", classname=PROBE_CLASS, name="Execution")
        XML.SubElement(case, "error", message="Native fmt probe could not complete").text = error
    path.parent.mkdir(parents=True, exist_ok=True)
    XML.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def _command(argv: list[str], workspace: Path, log: Path) -> dict:
    print(f"Fmt probe command: {json.dumps(argv)}", flush=True)
    with log.open("wb") as stream:
        result = subprocess.run(
            argv,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    raw = log.read_bytes()
    output = raw.decode("utf-8", errors="replace")
    print(output, flush=True)
    return {
        "argv": argv,
        "returncode": result.returncode,
        "output": output,
        "log": str(log),
        "log_sha256": hashlib.sha256(raw).hexdigest(),
    }


def run_probe(workspace: Path, junit: Path, probe: str = PROBE_ID) -> int:
    if probe != PROBE_ID:
        raise ValueError("Unknown fmt semantic probe")
    if junit.exists() or junit.is_symlink() or junit.with_suffix(".evidence.json").exists():
        print("Fmt semantic probe requires fresh report destinations", file=sys.stderr)
        return 127
    workspace, junit = workspace.resolve(), junit.resolve()
    windows = os.name == "nt"
    checks: dict[str, tuple[bool, str]] = {}
    error = ""
    evidence = {
        "probe": probe,
        "classification": "posthoc-development-semantic-guard",
        "workspace": str(workspace),
        "commands": [],
        "probe_source_sha256": hashlib.sha256(CPP_PROBE.encode()).hexdigest(),
        "cmake_source_sha256": hashlib.sha256(CMAKE_PROJECT.encode()).hexdigest(),
        "platform": sys.platform,
        "chrono_minimum_contract": "out-of-range exception" if windows else "rendered1677 UTC",
        "sanitizer": "not-configured",
    }
    try:
        for name in ("printf.h", "chrono.h", "format.h", "format-inl.h"):
            if not (workspace / "include/fmt" / name).is_file():
                raise ValueError("Workspace is not a fmt header source tree")
        evidence["candidate_header_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((workspace / "include/fmt").glob("*.h"))
        }
        root = workspace / ".auto-fix-build/sg/fmt"
        if not root.resolve().is_relative_to(workspace):
            raise ValueError("Fmt probe build must remain inside the candidate workspace")
        project, build, logs = root / "p", root / "b", root / "r" / uuid.uuid4().hex[:8]
        project.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True)
        (project / "probe.cc").write_bytes(CPP_PROBE.encode("utf-8"))
        (project / "CMakeLists.txt").write_bytes(CMAKE_PROJECT.encode("utf-8"))
        generator = ["-G", "Ninja"] if not windows and shutil.which("ninja") else []
        commands = [
            (
                "configure",
                [
                    "cmake",
                    "-S",
                    str(project),
                    "-B",
                    str(build),
                    *generator,
                    f"-DAUTO_FIX_FMT_SOURCE={workspace}",
                    "-DCMAKE_BUILD_TYPE=Release",
                ],
            ),
            (
                "build",
                [
                    "cmake",
                    "--build",
                    str(build),
                    "--config",
                    "Release",
                    "--parallel",
                    "2",
                    *([] if windows else ["--clean-first"]),
                    "--target",
                    "af_fmt_probe",
                    *(["--", "/t:Rebuild"] if windows else []),
                ],
            ),
        ]
        for stage, argv in commands:
            result = _command(argv, workspace, logs / f"{stage}.log")
            evidence["commands"].append(result)
            if result["returncode"]:
                raise ValueError(f"Fmt probe {stage} failed with exit {result['returncode']}")
        evidence["sanitizer"] = (build / "sanitizer.txt").read_text()
        executable = build / "bin" / ("af_fmt_probe.exe" if windows else "af_fmt_probe")
        result = _command([str(executable)], workspace, logs / "native.log")
        evidence["commands"].append(result)
        checks = _native_checks(result["output"], windows=windows)
        expected_returncode = int(any(not passed for passed, _ in checks.values()))
        if result["returncode"] != expected_returncode:
            raise ValueError(
                f"Fmt probe process did not complete normally: exit {result['returncode']}"
            )
    except Exception as exc:
        error = str(exc)
        print(f"Invalid fmt probe evidence: {error}", file=sys.stderr, flush=True)
    evidence.update(error=error, checks=checks)
    try:
        _junit(junit, checks, error, windows=windows)
        junit.with_suffix(".evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        print(f"Unable to persist fmt probe evidence: {exc}", file=sys.stderr, flush=True)
        return 127
    return 127 if error or not checks else int(any(not passed for passed, _ in checks.values()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--probe", choices=[PROBE_ID], required=True)
    args = parser.parse_args(argv)
    return run_probe(args.workspace, args.junit, args.probe)


if __name__ == "__main__":
    raise SystemExit(main())
