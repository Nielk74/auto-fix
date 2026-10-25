"""A complete sample state for trying the dashboard without TeamCity, Bitbucket, Jira or a model.

Every run is a real workflow run: ``Workflow`` writes the LangGraph checkpoints, events, model
call records and results itself, against in-process fakes and a simulated clock, so the dashboard
shows exactly what it shows for production runs. Builds, tests and model calls move the clock
on by what they take for real, and the runs start on different days of the last two weeks.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from auto_fix import control
from auto_fix import workflow as workflow_module
from auto_fix.config import Settings
from auto_fix.jobs import JobStore
from auto_fix.models import FailedTest, Failure, Proposal, TestReport, Verification
from auto_fix.schedules import ScheduleStore
from auto_fix.triage import TriageStore
from auto_fix.workflow import Workflow

MARKER = "auto-fix-demo.json"
TOKEN_ENV = "AUTO_FIX_DEMO_TOKEN"
BUILD_TYPES = ["Absl_Strings_Tests", "Fmt_Format_Tests"]
SUITES = {
    "Absl_Strings_Tests": [
        "AsciiStrToLower.Basic",
        "AsciiStrToLower.NonAscii",
        "AsciiStrToUpper.Basic",
        "StrCat.Floats",
        "StrCat.Ints",
        "StrSplit.Basic",
        "StrSplit.EmptyDelimiter",
        "Substitute.Basic",
    ],
    "Fmt_Format_Tests": [
        "ChronoTest.Duration",
        "ChronoTest.Locale",
        "FormatTest.Locale",
        "FormatTest.Precision",
        "FormatTest.Width",
        "PrintfTest.Basic",
    ],
}
CONFIG = """\
# Demo configuration written by `auto-fix dashboard --demo`. Every service address is a
# placeholder and the demo dashboard runs no jobs, so nothing here is ever contacted.
timezone: Europe/Paris
state_dir: state
teamcity: {url: "https://teamcity.demo.invalid", token_env: AUTO_FIX_DEMO_TOKEN,
  build_types: [Absl_Strings_Tests, Fmt_Format_Tests]}
bitbucket: {url: "https://bitbucket.demo.invalid", token_env: AUTO_FIX_DEMO_TOKEN,
  project: CPP, repo: abseil}
jira: {url: "https://jira.demo.invalid", token_env: AUTO_FIX_DEMO_TOKEN}
llm: {url: "https://llm.demo.invalid/v1", token_env: AUTO_FIX_DEMO_TOKEN,
  model: qwen3-coder-30b, prompt_version: assertion-v4}
repository: {path: source}
build:
  build: [[cmake, --build, build, --clean-first]]
  test: [ctest, --test-dir, build, --output-junit, "{junit}"]
baseline_repetitions: 1
"""


class WorkerLost(BaseException):
    """Ends a demo run the way a killed worker does: no handler records an outcome."""


class Clock:
    """Simulated time, moved on by each fake build, test run and model call."""

    def __init__(self, start: datetime):
        self.at = start

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.at.timestamp()


@contextmanager
def simulated(clock: Clock) -> Iterator[None]:
    """Run workflows on ``clock``: events, model calls and LangGraph checkpoints read it."""
    from langgraph.pregel import _checkpoint

    class SimulatedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return clock.at.astimezone(tz) if tz else clock.at.astimezone().replace(tzinfo=None)

    targets = [
        (workflow_module, "datetime", SimulatedDatetime),
        (control, "datetime", SimulatedDatetime),
        (_checkpoint, "datetime", SimulatedDatetime),
        (workflow_module, "time", SimpleNamespace(monotonic=clock.monotonic)),
    ]
    saved = [(module, name, getattr(module, name)) for module, name, _ in targets]
    for module, name, value in targets:
        setattr(module, name, value)
    try:
        yield
    finally:
        for module, name, value in saved:
            setattr(module, name, value)


def _sha(*parts: str) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()


class DemoWorkspace:
    """A worktree that is never on disk: commits are names, the diff is the run's patch."""

    def __init__(self, clock: Clock, name: str, diff: str, files: list[dict[str, str]], path: Path):
        self.clock, self.name, self.diff, self.files, self.path = clock, name, diff, files, path
        self.branch = f"auto-fix/{name}"
        self.current = _sha(name, "prepared")

    def prepare(self, revision: str, start: str | None = None) -> None:
        self.clock.advance(21)

    def context(self, changes: Any, max_chars: int, test_names: Any = None, signals: str = ""):
        return {"files": self.files}

    def apply_edits(self, edits: Any) -> None:
        pass

    def commit(self, summary: str) -> None:
        self.current = _sha(self.name, "commit", summary)

    def rebase(self) -> str:
        self.clock.advance(9)
        self.current = _sha(self.name, "rebased", self.current)
        return self.current

    def head(self) -> str:
        return self.current

    def is_clean(self) -> bool:
        return True

    def has_changes_against_base(self) -> bool:
        return True

    def committed_diff(self) -> str:
        return self.diff

    def push(self) -> None:
        self.clock.advance(5)


class DemoBuilder:
    """Native checks with the logs a real build and CTest run leave under ``evidence/``."""

    def __init__(self, clock: Clock, directory: Path, suite: list[str], checks: list[dict]):
        self.clock, self.directory, self.suite = clock, directory / "evidence", suite
        self.checks = deque(checks)

    def verify(self, path: Path, label: str) -> Verification:
        check = self.checks.popleft()
        if check.get("before"):
            check["before"]()
        failed = check.get("failed", [])
        passed = [name for name in self.suite if name not in failed]
        folder = self.directory / f"{label}-{uuid.uuid4().hex[:12]}"
        folder.mkdir(parents=True)
        self.clock.advance(check.get("build_seconds", 312))
        build_log = (
            "-- Configuring done (2.1s)\n-- Build files have been written to: build\n"
            + "".join(
                f"[{i}/48] Building CXX object absl/strings/CMakeFiles/{name}.dir/{name}.cc.o\n"
                for i, name in enumerate(["ascii", "str_cat", "str_split", "substitute"], 1)
            )
            + "[48/48] Linking CXX executable strings_test\n"
        )
        (folder / "build-0.log").write_text(build_log, encoding="utf-8")
        if check.get("crash"):
            (folder / "test.log").write_text("[==========] Running tests\n", encoding="utf-8")
            self.clock.advance(41)
            raise WorkerLost()
        self.clock.advance(check.get("test_seconds", 96))
        lines = [f"[==========] Running {len(self.suite)} tests from {len(self.suite)} suites."]
        for name in self.suite:
            lines.append(f"[ RUN      ] {name}")
            if name in failed:
                lines.append(check.get("message", {}).get(name, f"{name}: assertion failed"))
                lines.append(f"[  FAILED  ] {name} (3 ms)")
            else:
                lines.append(f"[       OK ] {name} (1 ms)")
        lines.append(f"[==========] {len(self.suite)} tests ran.")
        lines.append(f"[  PASSED  ] {len(passed)} tests.")
        if failed:
            lines.append(f"[  FAILED  ] {len(failed)} tests, listed below:")
            lines += [f"[  FAILED  ] {name}" for name in failed]
        log = "\n".join(lines) + "\n"
        (folder / "test.log").write_text(log, encoding="utf-8")
        cases = "".join(
            f'<testcase classname="{n.split(".")[0]}" name="{n.split(".")[1]}">'
            + ("<failure/>" if n in failed else "")
            + "</testcase>"
            for n in self.suite
        )
        (folder / "junit.xml").write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")
        return Verification(
            build_ok=True,
            test_ok=not failed,
            report=TestReport(passed=passed, failed=failed),
            output=log[-3000:],
            logs=[str(folder / "build-0.log"), str(folder / "test.log")],
        )


class DemoModel:
    """Answers in order; a ``None`` answer is cut off at the token limit, like a real one."""

    def __init__(self, clock: Clock, answers: list[dict | None], truncated: str = ""):
        self.clock, self.answers, self.truncated = clock, deque(answers), truncated
        self.last_usage: dict[str, Any] = {}
        self.last_raw = ""

    def propose(self, context: dict[str, Any]) -> Proposal:
        answer = self.answers.popleft()
        self.clock.advance(38 if answer else 61)
        prompt = 9000 + len(json.dumps(context)) // 4
        if answer is None:
            self.last_usage = {"prompt_tokens": prompt, "completion_tokens": 6000}
            self.last_raw = self.truncated
            raise ValueError(
                "Model output was truncated or did not complete normally (finish_reason: length)"
            )
        self.last_raw = json.dumps(answer)
        self.last_usage = {"prompt_tokens": prompt, "completion_tokens": 412}
        return Proposal.model_validate(answer)


def _diff(path: str, line: int, before: list[str], after: list[str], context: list[str]) -> str:
    """A one-hunk unified diff, as ``git diff`` writes it."""
    head, tail = context[:3], context[3:]
    body = [" " + text for text in head] + ["-" + text for text in before]
    body += ["+" + text for text in after] + [" " + text for text in tail]
    old, new = len(head) + len(before) + len(tail), len(head) + len(after) + len(tail)
    return (
        f"diff --git a/{path} b/{path}\nindex 3f2a91c..8b0de47 100644\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -{line},{old} +{line},{new} @@\n" + "\n".join(body) + "\n"
    )


# Each demo run: the TeamCity failure and its context, the model's answers, the checks' results.
RUNS: list[dict[str, Any]] = [
    {
        "name": "tc-48114-9b2e7c10",
        "hours_ago": 266,
        "build_type": "Fmt_Format_Tests",
        "tests": {
            "FormatTest.Width": 'format-test.cc:418: Failure\nExpected: "  42"\n  Actual: "42"'
        },
        "author": ("lmartin", "Luc Martin"),
        "commit": "Skip padding for integers that fill the field\n\nFMT-77",
        "issue": ("FMT-77", "Width is ignored for formatted integers", "Done"),
        "answers": [
            {
                "summary": "Pad integers to the requested width again",
                "explanation": "The shortcut for integers that already fill the field also ran "
                "when the width was larger, so padding was skipped. Compare against the width.",
                "edits": [
                    {
                        "path": "include/fmt/format.h",
                        "old": "if (size >= 0) return write(out, value);",
                        "new": "if (size >= specs.width) return write(out, value);",
                    }
                ],
            }
        ],
        "checks": [{"failed": ["FormatTest.Width"]}, {}, {}],
        "diff": (
            "include/fmt/format.h",
            1987,
            ["  if (size >= 0) return write(out, value);"],
            ["  if (size >= specs.width) return write(out, value);"],
            [
                "  auto size = to_unsigned(num_digits);",
                "  // Integers that fill the field need no padding.",
                "  auto width = to_unsigned(specs.width);",
                "  return write_padded(out, specs, size, width, f);",
            ],
        ),
        "publish": True,
    },
    {
        "name": "tc-48231-4f81d2aa",
        "hours_ago": 142,
        "build_type": "Fmt_Format_Tests",
        "tests": {
            "PrintfTest.Basic": 'printf-test.cc:96: Failure\nValue of: fmt::sprintf("%5s", "abc")'
        },
        "author": ("jdurand", "Julie Durand"),
        "commit": "Rework printf argument parsing",
        "answers": [
            {
                "summary": "Read the printf width before the precision",
                "explanation": "The parser consumed the precision first.",
                "edits": [
                    {"path": "src/printf.cc", "old": "parse_precision(", "new": "parse_width("}
                ],
            }
        ],
        "checks": [
            {"failed": ["PrintfTest.Basic"]},
            {"failed": ["PrintfTest.Basic"], "before": "cancel"},
        ],
        "diff": None,
    },
    {
        "name": "tc-48262-0c7d93e1",
        "hours_ago": 75,
        "build_type": "Fmt_Format_Tests",
        "tests": {
            "ChronoTest.Locale": 'chrono-test.cc:233: Failure\nExpected: "Mo"\n  Actual: "Mon"'
        },
        "author": ("lmartin", "Luc Martin"),
        "commit": "Use the C locale for chrono names in tests\n\nFMT-81",
        "issue": ("FMT-81", "ChronoTest.Locale depends on the agent's locale", "In Progress"),
        "answers": [],
        # The test passes on the unchanged code: the failure does not reproduce here.
        "checks": [{"failed": []}],
        "diff": None,
    },
    {
        "name": "tc-48295-a13f6b42",
        "hours_ago": 98,
        "build_type": "Absl_Strings_Tests",
        "tests": {
            "Substitute.Basic": 'substitute_test.cc:61: Failure\nExpected: "a-b"\n  Actual: "a$b"'
        },
        "author": ("mlefevre", "Marie Lefevre"),
        "commit": "Inline single-argument Substitute\n\nSTR-498",
        "issue": ("STR-498", "Substitute leaves $ escapes in place", "In Review"),
        "answers": [
            {
                "summary": "Expand $-escapes in the single-argument path",
                "explanation": "The inlined path copied the format string verbatim.",
                "edits": [
                    {
                        "path": "absl/strings/substitute.cc",
                        "old": "return std::string(format);",
                        "new": "return SubstituteAndAppendArray(format, args, 1);",
                    }
                ],
            }
        ],
        "checks": [{"failed": ["Substitute.Basic"]}, {}, {}],
        "diff": (
            "absl/strings/substitute.cc",
            88,
            ["  return std::string(format);"],
            ["  return SubstituteAndAppendArray(format, args, 1);"],
            [
                "std::string Substitute(absl::string_view format, const Arg& a0) {",
                "  const Arg* args[] = {&a0};",
                "  // One argument: expand $0 and $$.",
                "}",
            ],
        ),
        "publish": True,
        "publish_fails": True,
    },
    {
        "name": "tc-48310-5d0e8f37",
        "hours_ago": 27,
        "build_type": "Absl_Strings_Tests",
        "tests": {
            "StrSplit.EmptyDelimiter": "str_split_test.cc:204: Failure\nExpected size 3, got 1",
        },
        "author": ("jdurand", "Julie Durand"),
        "commit": "Treat an empty delimiter as a byte delimiter\n\nSTR-503",
        "issue": ("STR-503", "StrSplit with an empty delimiter returns one piece", "Open"),
        "answers": [
            {
                "summary": "Split on every byte for an empty delimiter",
                "explanation": "An empty ByString delimiter never matched, so nothing was split.",
                "edits": [
                    {
                        "path": "absl/strings/str_split.cc",
                        "old": "if (delimiter_.empty()) return absl::string_view();",
                        "new": "if (delimiter_.empty()) return text.substr(pos + 1, 0);",
                    }
                ],
            },
            {
                "summary": "Advance one byte at a time when the delimiter is empty",
                "explanation": "Match a zero-length delimiter after every byte.",
                "edits": [
                    {
                        "path": "absl/strings/str_split.cc",
                        "old": "size_t found = text.find(delimiter_, pos);",
                        "new": "size_t found = delimiter_.empty() ? pos + 1 "
                        ": text.find(delimiter_, pos);",
                    }
                ],
            },
        ],
        "checks": [
            {"failed": ["StrSplit.EmptyDelimiter"]},
            {"failed": ["StrSplit.EmptyDelimiter"]},
            # The second edit repairs the test and breaks another one.
            {"failed": ["StrSplit.Basic"]},
        ],
        "diff": None,
    },
    {
        "name": "tc-48327-e6b04a19",
        "hours_ago": 5,
        "build_type": "Absl_Strings_Tests",
        "tests": {
            "StrCat.Floats": 'str_cat_test.cc:140: Failure\nExpected: "1.5"\n  Actual: "1.500000"'
        },
        "author": ("mlefevre", "Marie Lefevre"),
        "commit": "Use %f for StrCat doubles",
        "answers": [],
        "checks": [{"failed": ["StrCat.Floats"], "before": "pause"}],
        "diff": None,
    },
    {
        "name": "tc-48339-7a52c0de",
        "hours_ago": 2.5,
        "build_type": "Absl_Strings_Tests",
        "tests": {
            "AsciiStrToLower.NonAscii": "ascii_test.cc:212: Failure\n"
            "Expected equality of these values:\n"
            '  absl::AsciiStrToLower("\\xC3\\x89T\\xC3\\x89")\n'
            '    Which is: "\\xE3\\x89t\\xE3\\x89"\n'
            '  "\\xC3\\x89t\\xC3\\x89"',
        },
        "author": ("mlefevre", "Marie Lefevre"),
        "commit": "Speed up AsciiStrToLower with a branchless OR\n\nSTR-412",
        "issue": ("STR-412", "AsciiStrToLower is slow on long inputs", "In Review"),
        "answers": [
            None,
            {
                "summary": "Lower-case only ASCII upper-case letters",
                "explanation": "The branchless OR set bit 5 on every byte, which corrupts UTF-8 "
                "lead and continuation bytes. Apply it only to 'A'..'Z'.",
                "edits": [
                    {
                        "path": "absl/strings/ascii.cc",
                        "old": "*p = *p | 0x20;",
                        "new": "*p = (*p >= 'A' && *p <= 'Z') ? (*p | 0x20) : *p;",
                    }
                ],
            },
        ],
        "truncated": '{"summary": "Lower-case only ASCII upper-case letters", "explanation": "The '
        "branchless OR sets bit 5 on every byte. For a UTF-8 sequence such as \\u00c9 (0xC3 0x89) "
        "this turns the lead byte into 0xE3, which starts a three-byte sequence instead, so",
        "checks": [{"failed": ["AsciiStrToLower.NonAscii"]}, {}, {}],
        "diff": (
            "absl/strings/ascii.cc",
            181,
            ["    *p = *p | 0x20;"],
            ["    *p = (*p >= 'A' && *p <= 'Z') ? (*p | 0x20) : *p;"],
            [
                "void AsciiStrToLower(char* p, size_t size) {",
                "  char* end = p + size;",
                "  for (; p < end; ++p) {",
                "  }",
                "}",
            ],
        ),
    },
    {
        "name": "tc-48344-b8c91f05",
        "hours_ago": 0.6,
        "build_type": "Fmt_Format_Tests",
        "tests": {
            "FormatTest.Precision": 'format-test.cc:502: Failure\nExpected: "3.14"\n  Actual: "3.1"'
        },
        "author": ("jdurand", "Julie Durand"),
        "commit": "Round precision with Dragonbox",
        "answers": [
            {
                "summary": "Keep the requested precision when rounding",
                "explanation": "Precision was decremented before rounding.",
                "edits": [
                    {"path": "include/fmt/format.h", "old": "precision - 1", "new": "precision"}
                ],
            }
        ],
        # The worker dies while verifying the edit.
        "checks": [{"failed": ["FormatTest.Precision"]}, {"crash": True}],
        "diff": None,
    },
]


def _failure(spec: dict[str, Any]) -> Failure:
    build_id = spec["name"].split("-")[1]
    username, _ = spec["author"]
    version = _sha(spec["name"], "change")
    return Failure(
        build_id=build_id,
        build_type=spec["build_type"],
        build_url=f"https://teamcity.demo.invalid/buildConfiguration/{spec['build_type']}/{build_id}",
        revision=version,
        tests=[
            FailedTest(
                id=str(index),
                name=name,
                details=details,
                url=f"https://teamcity.demo.invalid/test/{name}?buildId={build_id}",
            )
            for index, (name, details) in enumerate(spec["tests"].items())
        ],
        changes=[
            {
                "id": build_id + "1",
                "version": version,
                "username": username,
                "comment": spec["commit"],
                "date": "20261020T101500+0200",
                "webUrl": f"https://teamcity.demo.invalid/change/{build_id}1",
            },
            {
                "id": build_id + "0",
                "version": _sha(spec["name"], "earlier"),
                "username": "ci-bot",
                "comment": "Update third-party pins",
                "date": "20261020T081000+0200",
                "webUrl": "",
            },
        ],
    )


def _services(spec: dict[str, Any], workspace: DemoWorkspace, clock: Clock) -> tuple[Any, Any, Any]:
    _, display = spec["author"]
    pr_id = int(spec["name"].split("-")[1]) % 1000 + 1000
    pr = {
        "id": pr_id,
        "title": spec["commit"].split("\n")[0],
        "state": "MERGED",
        "author": {"user": {"displayName": display}},
        "links": {
            "self": [
                {
                    "href": f"https://bitbucket.demo.invalid/projects/CPP/repos/abseil/pull-requests/{pr_id}"
                }
            ]
        },
    }

    def create_pr(branch: str, base: str, title: str, description: str) -> dict[str, Any]:
        if spec.get("publish_fails"):
            raise RuntimeError("Bitbucket did not answer the pull request request (ReadTimeout)")
        number = pr_id + 1
        return {
            "id": number,
            "title": title,
            "state": "OPEN",
            "fromRef": {"id": "refs/heads/" + branch, "latestCommit": workspace.head()},
            "toRef": {"id": "refs/heads/" + base},
            "links": {
                "self": [
                    {
                        "href": f"https://bitbucket.demo.invalid/projects/CPP/repos/abseil/pull-requests/{number}"
                    }
                ]
            },
        }

    issues = []
    if spec.get("issue"):
        key, summary, status = spec["issue"]
        issues = [
            {
                "key": key,
                "fields": {"summary": summary, "status": {"name": status}},
                "url": f"https://jira.demo.invalid/browse/{key}",
            }
        ]
    log = (
        "[10:21:44] Step 3/4: Run tests (CTest)\n"
        + "".join(f"[10:22:{10 + i}] {name} FAILED\n" for i, name in enumerate(spec["tests"]))
        + "[10:22:31] Process exited with code 8\n[10:22:31] Step 3/4: Run tests failed"
    )

    def build_log(build_id: str) -> str:
        clock.advance(2.4)
        return log

    def context(commits: list[str]) -> list[dict[str, Any]]:
        clock.advance(1.3)
        return [pr]

    teamcity = SimpleNamespace(build_log=build_log)
    bitbucket = SimpleNamespace(context=context, find_pr=lambda *a: None, create_pr=create_pr)
    jira = SimpleNamespace(issues=lambda keys: [i for i in issues if i["key"] in keys])
    return teamcity, bitbucket, jira


def _settings(root: Path) -> Settings:
    service = {"url": "https://demo.invalid", "token_env": TOKEN_ENV}
    return Settings.model_validate(
        {
            "state_dir": root / "state",
            "teamcity": {**service, "build_types": BUILD_TYPES},
            "bitbucket": {**service, "project": "CPP", "repo": "abseil"},
            "llm": {**service, "model": "qwen3-coder-30b", "context_chars": 60000},
            "repository": {"path": root / "source"},
            "build": {"build": [["cmake", "--build", "build"]], "test": ["ctest", "{junit}"]},
            "max_attempts": 2,
        }
    )


def _run(root: Path, spec: dict[str, Any], clock: Clock) -> None:
    settings = _settings(root)
    directory = settings.state_dir / "runs" / spec["name"]
    diff = _diff(*spec["diff"]) if spec.get("diff") else ""
    files = [{"path": path, "content": "// demo source"} for path in ("absl/strings/ascii.cc",)]
    workspace = DemoWorkspace(clock, spec["name"], diff, files, root / "source")
    teamcity, bitbucket, jira = _services(spec, workspace, clock)
    flow = Workflow(
        settings,
        spec["name"],
        teamcity,
        bitbucket,
        jira,
        DemoModel(clock, list(spec["answers"]), spec.get("truncated", "")),
        publish=bool(spec.get("publish")),
    )
    requests: dict[str, Callable[[], Any]] = {
        "pause": lambda: control.request(directory, "pause", "mlefevre"),
        "cancel": lambda: control.request(directory, "cancel", "jdurand"),
    }
    checks = [
        {**check, "before": requests[check["before"]]} if check.get("before") else check
        for check in spec["checks"]
    ]
    flow.workspace = workspace
    flow.builder = DemoBuilder(clock, directory, SUITES[spec["build_type"]], checks)
    clock.advance(4)
    try:
        flow.run({"run_id": spec["name"], "failure": _failure(spec).model_dump()})
    except WorkerLost:
        pass


def _jobs(state: Path, now: datetime) -> None:
    """Two scheduled repair batches: one that queued repairs, one that found no failures."""
    store = JobStore(state)

    def stamp(hours: float) -> str:
        return (now - timedelta(hours=hours)).isoformat()

    batch = store.add(
        "batch", {"date": (now - timedelta(hours=28)).date().isoformat()}, "scheduler"
    )
    store.update(
        batch["id"],
        title="Daily repair batch · all build configurations",
        status="done",
        created=stamp(28),
        started=stamp(28),
        ended=stamp(27.9),
        result="Queued 2 repairs",
        discovered=2,
        scan_complete=True,
    )
    for name, hours in (("tc-48310-5d0e8f37", 27), ("tc-48295-a13f6b42", 98)):
        spec = next(item for item in RUNS if item["name"] == name)
        child = store.add(
            "repair",
            {"failure": _failure(spec).model_dump(), "mode": "new"},
            "scheduler",
            parent_id=batch["id"],
            title="Repair " + next(iter(spec["tests"])),
        )
        store.update(
            child["id"], status="done", run_id=name, created=stamp(hours), started=stamp(hours)
        )
    empty = store.add(
        "batch", {"date": (now - timedelta(hours=52)).date().isoformat()}, "scheduler"
    )
    store.update(
        empty["id"],
        title="Daily repair batch · all build configurations",
        status="done",
        created=stamp(52),
        started=stamp(52),
        ended=stamp(51.95),
        result="Queued 0 repairs",
        discovered=0,
        scan_complete=True,
    )


def _schedules(state: Path) -> None:
    store = ScheduleStore(state, "Europe/Paris")
    common = {"kind": "batch", "timezone": "Europe/Paris", "missed": "once", "overlap": "skip"}
    store.save(
        {
            **common,
            "name": "Weekday evening repairs",
            "params": {"date": "today", "publish": False},
            "frequency": "weekly",
            "weekdays": [0, 1, 2, 3, 4],
            "time": "18:30",
        },
        "mlefevre",
    )
    store.save(
        {
            **common,
            "name": "Monday fmt sweep",
            "params": {"date": "today", "build_type": "Fmt_Format_Tests", "publish": True},
            "frequency": "weekly",
            "weekdays": [0],
            "time": "07:30",
        },
        "lmartin",
    )


def _triage(state: Path, now: datetime) -> None:
    store = TriageStore(state)
    store.update(
        "runs/tc-48262-0c7d93e1",
        "handled",
        "lmartin",
        note="Locale-dependent test; FMT-81 pins the C locale in CI.",
        at=now - timedelta(hours=70),
    )
    store.update(
        "runs/tc-48114-9b2e7c10", "rate", "lmartin", rating="good", at=now - timedelta(hours=260)
    )
    store.update(
        "runs/tc-48310-5d0e8f37",
        "note",
        "jdurand",
        note="The second edit fixes the empty delimiter but breaks StrSplit.Basic; look at the "
        "ByString matcher before retrying.",
        at=now - timedelta(hours=20),
    )


def build_demo(root: Path, now: datetime | None = None) -> Path:
    """Write a fresh demo under ``root`` and return its configuration file.

    ``root`` must be missing, empty or an earlier demo: a real state directory is never touched.
    """
    now = now or datetime.now(UTC)
    if root.exists() and any(root.iterdir()):
        if not (root / MARKER).is_file():
            raise ValueError(f"{root} is not empty and is not a demo directory; choose another one")
        shutil.rmtree(root)
    state = root / "state"
    state.mkdir(parents=True)
    for spec in RUNS:
        clock = Clock(now - timedelta(hours=spec["hours_ago"]))
        # The workflow prints each step; a demo build stays quiet.
        with simulated(clock), contextlib.redirect_stdout(io.StringIO()):
            _run(root, spec, clock)
    _jobs(state, now)
    _schedules(state)
    _triage(state, now)
    config = root / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    (root / MARKER).write_text(json.dumps({"created": now.isoformat()}), encoding="utf-8")
    return config
