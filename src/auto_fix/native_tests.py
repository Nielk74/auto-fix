"""Run complete selected upstream GoogleTest binaries and merge their JUnit evidence."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET


def run_native(build_dir: Path, targets: list[str], junit: Path) -> int:
    junit = junit.resolve()
    junit.parent.mkdir(parents=True, exist_ok=True)
    merged = ET.Element("testsuites")
    failed = False
    for target in targets:
        matches = [
            path
            for path in build_dir.rglob(target + "*")
            if path.is_file() and path.name in {target, target + ".exe"}
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one built executable for {target}; found {matches}")
        report = junit.with_name(f"{junit.stem}-{target}.xml")
        if report.exists():
            raise ValueError("Native report path must be fresh")
        result = subprocess.run(
            [str(matches[0].resolve()), f"--gtest_output=xml:{report}", "--gtest_color=no"],
            check=False,
            timeout=180,
        )
        failed |= result.returncode != 0
        if not report.is_file():
            raise ValueError(f"{target} did not produce test evidence")
        raw = report.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # GoogleTest sometimes emits raw signed-char values in assertion
            # text. Keep original bytes; normalize only their text encoding.
            # XML structure/outcomes are still parsed strictly and never removed.
            report.with_suffix(report.suffix + ".raw").write_bytes(raw)
            text = raw.decode("utf-8", errors="replace")
        root = SafeET.fromstring(text)
        suites = list(root) if root.tag == "testsuites" else [root]
        for suite in suites:
            merged.append(suite)
    ET.ElementTree(merged).write(junit, encoding="utf-8", xml_declaration=True)
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--junit", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_native(args.build_dir, args.targets, args.junit)


if __name__ == "__main__":
    raise SystemExit(main())
