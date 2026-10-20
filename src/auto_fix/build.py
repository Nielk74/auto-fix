from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as XML

from defusedxml import ElementTree

from auto_fix.config import BuildConfig
from auto_fix.models import CommandResult, TestReport, Verification

OUTPUT_LIMIT = 24000


def _redact(value: str) -> str:
    for name, secret in os.environ.items():
        if len(secret) >= 5 and any(
            marker in name.upper() for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")
        ):
            value = value.replace(secret, "[REDACTED]")
    return value


def run_command(argv: list[str], cwd: Path, timeout: int, log_path: Path) -> CommandResult:
    """Run operator-configured argv without a shell; terminate descendants on timeout."""
    if not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ValueError("Command must be a nonempty argument array")
    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    options: dict = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    returncode = 127
    with tempfile.TemporaryFile() as output_file:
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                **options,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=15,
                            check=False,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                process.wait()
                returncode = 124
                output_file.write(f"\nCommand timed out after {timeout} seconds.\n".encode())
        except OSError as error:
            output_file.write(f"Unable to execute command: {error}\n".encode())
        output_file.seek(0)
        output = _redact(output_file.read().decode("utf-8", errors="replace"))
    log_path.write_text(output, encoding="utf-8")
    if len(output) > OUTPUT_LIMIT:
        output = "[Earlier output omitted; see log file.]\n" + output[-OUTPUT_LIMIT:]
    return CommandResult(
        argv=[_redact(arg) for arg in argv],
        returncode=returncode,
        output=output,
        log_path=str(log_path),
    )


def parse_junit(path: Path) -> TestReport:
    """Trust testcase outcomes, not potentially incorrect suite summary counters."""
    root = ElementTree.parse(path).getroot()
    report = TestReport()
    seen: set[str] = set()
    for case in root.iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        name = case.get("name", "")
        if not name:
            raise ValueError("JUnit testcase is missing its name")
        classname = case.get("classname", "")
        if classname and classname != name:
            name = f"{classname}.{name}"
        if name in seen:
            raise ValueError(f"JUnit testcase names must be unique; duplicate name: {name}")
        seen.add(name)
        outcomes = {child.tag.rsplit("}", 1)[-1] for child in case}
        if outcomes & {"failure", "error"}:
            report.failed.append(name)
        elif (
            "skipped" in outcomes
            or case.get("status", "").lower() in {"notrun", "disabled", "skipped"}
            or case.get("result", "").lower() in {"suppressed", "skipped"}
        ):
            report.skipped.append(name)
        else:
            report.passed.append(name)
    return report


class Builder:
    def __init__(self, config: BuildConfig, artifact_dir: Path):
        self.config = config
        self.artifact_dir = artifact_dir.resolve()

    def verify(self, worktree: Path, label: str) -> Verification:
        safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", label)[:80] or "verification"
        directory = self.artifact_dir / f"{safe_label}-{uuid.uuid4().hex[:12]}"
        directory.mkdir(parents=True)
        junit = directory / "junit.xml"
        logs: list[str] = []
        outputs: list[str] = []
        for index, command in enumerate([*self.config.configure, *self.config.build]):
            result = run_command(
                command, worktree, self.config.timeout_seconds, directory / f"build-{index}.log"
            )
            logs.append(result.log_path)
            outputs.append(result.output)
            if result.returncode:
                outputs.append(f"Build command failed with exit code {result.returncode}.")
                return Verification(
                    build_ok=False,
                    test_ok=False,
                    evidence_valid=False,
                    output="\n".join(outputs)[-OUTPUT_LIMIT:],
                    logs=logs,
                )
        report = TestReport()
        test_ok = True
        seen: set[str] = set()
        merged = XML.Element("testsuites")
        evidence_ok = True
        commands = [self.config.test, *self.config.additional_tests]
        for index, command in enumerate(commands):
            label = "primary" if index == 0 else f"additional-{index}"
            # Preserve the original path/format when no extra suites are configured.
            suite_junit = directory / f"junit-{label}.xml" if len(commands) > 1 else junit
            logfile = directory / ("test.log" if index == 0 else f"test-{label}.log")
            result = run_command(
                [arg.replace("{junit}", str(suite_junit)) for arg in command],
                worktree,
                self.config.timeout_seconds,
                logfile,
            )
            logs.append(result.log_path)
            outputs.append(f"Validation suite: {label}\n{result.output}")
            suite_report = None
            try:
                if not suite_junit.is_file() or suite_junit.is_symlink():
                    raise ValueError("Test command did not produce a fresh JUnit report")
                if suite_junit.stat().st_size > 20_000_000:
                    raise ValueError("JUnit report exceeds the 20 MB size limit")
                suite_report = parse_junit(suite_junit)
                logs.append(str(suite_junit))
                identities = {*suite_report.passed, *suite_report.failed, *suite_report.skipped}
                if duplicates := seen & identities:
                    raise ValueError(
                        "JUnit testcase names must be unique across validation suites; "
                        f"duplicate name: {sorted(duplicates)[0]}"
                    )
                seen.update(identities)
                for outcome in ("passed", "failed", "skipped"):
                    getattr(report, outcome).extend(getattr(suite_report, outcome))
                if not suite_report.passed and not suite_report.failed:
                    raise ValueError(
                        "JUnit report contains no executed tests (empty or all skipped)"
                    )
                if len(commands) > 1:
                    suite = XML.SubElement(merged, "testsuite", name=label)
                    for case in ElementTree.parse(suite_junit).getroot().iter():
                        if case.tag.rsplit("}", 1)[-1] == "testcase":
                            suite.append(deepcopy(case))
            except Exception as exc:
                # Malformed XML and blocked DTD/entity payloads invalidate verification.
                outputs.append(f"Invalid test evidence ({label}): {exc}")
                evidence_ok = False
            if result.returncode:
                outputs.append(f"Test command ({label}) failed with exit code {result.returncode}.")
                test_ok = False
                if result.returncode in {124, 127}:
                    outputs.append(
                        f"Invalid test evidence ({label}): command did not complete; "
                        "reported assertions may be partial."
                    )
                    evidence_ok = False
                elif suite_report is None or not suite_report.failed:
                    outputs.append(
                        f"Invalid test evidence ({label}): "
                        "command failed without failing assertions."
                    )
                    evidence_ok = False
        if len(commands) > 1 and evidence_ok:
            XML.ElementTree(merged).write(junit, encoding="utf-8", xml_declaration=True)
            logs.append(str(junit))
        return Verification(
            build_ok=True,
            test_ok=evidence_ok and test_ok and not report.failed,
            evidence_valid=evidence_ok,
            report=report,
            output="\n".join(outputs)[-OUTPUT_LIMIT:],
            logs=logs,
        )
