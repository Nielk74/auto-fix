from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from auto_fix import control, tracing
from auto_fix.build import Builder
from auto_fix.config import Settings
from auto_fix.diagnostics import failure_diagnostics
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.investigation import gather_evidence, invalidate_evidence, merge_evidence
from auto_fix.llm import RepairModel
from auto_fix.models import Failure, Verification
from auto_fix.publication import require_verified_pr
from auto_fix.validation_context import failed_assertions
from auto_fix.workspace import Workspace


class State(TypedDict, total=False):
    run_id: str
    failure: dict[str, Any]
    context: dict[str, Any]
    attempt: int
    feedback: str
    proposal: dict[str, Any]
    baseline: dict[str, Any]
    baseline_checks: list[dict[str, Any]]
    verification: dict[str, Any]
    status: str
    reason: str
    head: str
    branch: str
    pr: dict[str, Any]
    resume_ready: bool
    inspections: int
    investigation: dict[str, Any]
    last_repair: dict[str, Any]
    inspection_round: int
    round_inspections: int
    prepared_head: str


def failure_key(failure: Failure) -> str:
    payload = [
        failure.build_type,
        failure.build_id,
        failure.revision,
        sorted(t.name for t in failure.tests),
    ]
    digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:12]
    return f"tc-{failure.build_id}-{digest}"


def redact(text: str) -> str:
    for name, value in os.environ.items():
        if len(value) >= 8 and any(
            word in name.upper() for word in ("TOKEN", "PASSWORD", "SECRET", "API_KEY")
        ):
            text = text.replace(value, "[REDACTED]")
    return text


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(redact(json.dumps(data, indent=2, ensure_ascii=False)), encoding="utf-8")
    temporary.replace(path)


def model_usage(model: Any) -> dict[str, Any]:
    """Latest call's token usage; recording must never fail a repair on an unknown adapter."""
    recorded = getattr(model, "calls", None)
    if isinstance(recorded, list) and recorded and isinstance(recorded[-1], dict):
        # Codex and replay adapters keep one record per call.
        usage = recorded[-1].get("usage") or recorded[-1].get("recorded_usage")
    else:
        usage = getattr(model, "last_usage", None)
    return usage if isinstance(usage, dict) else {}


def matched_names(settings: Settings, failure: Failure) -> set[str]:
    return {settings.build.test_name_map.get(t.name, t.name) for t in failure.tests}


def validates_fix(report: Verification, expected: set[str]) -> bool:
    return (
        report.build_ok
        and report.test_ok
        and report.evidence_valid
        and expected.issubset(set(report.report.passed))
    )


def pr_description(state: State) -> str:
    failure = Failure.model_validate(state["failure"])
    proposal = state.get("proposal", {})
    tests = "\n".join(f"- `{t.name}`" for t in failure.tests)
    issues = state.get("context", {}).get("issues", [])
    prs = state.get("context", {}).get("pull_requests", [])
    links = [f"- [TeamCity build {failure.build_id}]({failure.build_url})"]
    for issue in issues:
        if issue.get("url"):
            links.append(f"- [{issue.get('key', 'Jira issue')}]({issue['url']})")
    for pr in prs:
        urls = pr.get("links", {}).get("self", [])
        if urls:
            links.append(f"- [Related PR {pr.get('id', '')}]({urls[0]['href']})")
    evidence = "\n".join(
        f"[TeamCity artifact]({url})\n\n![TeamCity evidence]({url})"
        for url in failure.evidence_urls
    )
    links_text = "\n".join(links)
    count = len(state.get("baseline_checks", []))
    reproduction = (
        (
            "Baseline reproduction: 1 native run before repair.\n\n"
            if count == 1
            else f"Baseline reproduction: {count} native runs with matching test outcomes "
            "before repair.\n\n"
        )
        if count
        else ""
    )
    return redact(
        f"{proposal.get('explanation', 'Automated repair candidate.')}\n\n"
        f"Reproduced failing tests:\n{tests}\n\n"
        f"Original TeamCity revision: `{failure.revision}`\n\n"
        f"Verified commit after rebasing onto the configured base: `{state['head']}`\n\n"
        f"{reproduction}"
        "Validation: configured native build and full test command passed; originally failing "
        "tests are present and passing in the fresh JUnit report.\n\n"
        f"Context:\n{links_text}\n\n{evidence}\n\n"
        f"Automation run: `{state['run_id']}`. AI-generated candidate; review before merging."
    )


class Workflow:
    """Explicit investigation/repair graph with native verification and publication gates."""

    def __init__(
        self,
        settings: Settings,
        run_id: str,
        teamcity: TeamCity,
        bitbucket: Bitbucket,
        jira: Jira | None,
        model: RepairModel,
        publish: bool = False,
    ):
        self.settings = settings
        self.run_id = run_id
        self.teamcity = teamcity
        self.bitbucket = bitbucket
        self.jira = jira
        self.model = model
        self.publish = publish
        self.directory = settings.state_dir / "runs" / run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.workspace = Workspace(settings.repository, settings.state_dir, run_id)
        self.builder = Builder(settings.build, self.directory / "evidence")

    def _saved_result(self) -> State:
        """The run's last written state; kept if resuming fails before the graph starts."""
        try:
            return json.loads((self.directory / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def event(self, node: str, quiet: bool = False, **details: Any) -> None:
        event = {"time": datetime.now(UTC).isoformat(), "node": node, **details}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(redact(json.dumps(event)) + "\n")
        if not quiet:
            print(f"[{self.run_id}] {node}", flush=True)

    def call_model(self, kind: str, context: dict[str, Any], attempt: int) -> Any:
        """Record each model request and its outcome for the dashboard and optional traces."""
        calls = self.directory / "model-calls"
        index = len(list(calls.glob("*.json"))) + 1 if calls.is_dir() else 1
        started = datetime.now(UTC).isoformat()
        clock = time.monotonic()
        response = error = None
        with tracing.model_span(kind, self.settings.llm.model, context) as finish:
            try:
                ask = self.model.inspect if kind == "investigation" else self.model.propose
                response = ask(context)
                return response
            except Exception as exc:
                error = redact(f"{type(exc).__name__}: {exc}")
                raise
            finally:
                elapsed = round(time.monotonic() - clock, 3)
                usage = model_usage(self.model)
                output = response.model_dump() if response is not None else None
                finish(output, usage, error)
                write_json(
                    calls / f"{index:02d}-{kind}.json",
                    {
                        "index": index,
                        "kind": kind,
                        "attempt": attempt,
                        "model": self.settings.llm.model,
                        "started": started,
                        "elapsed_seconds": elapsed,
                        "usage": usage,
                        "error": error,
                        "context": context,
                        "response": output,
                        # A rejected answer's text, e.g. output cut off at max_tokens.
                        "raw": redact(str(getattr(self.model, "last_raw", "") or ""))[-20000:]
                        if error
                        else None,
                    },
                )
                self.event(
                    "model_call",
                    quiet=True,
                    kind=kind,
                    call=index,
                    elapsed_seconds=elapsed,
                    ok=error is None,
                )

    def collect_context(self, state: State) -> State:
        self.event("collect_context")
        failure = Failure.model_validate(state["failure"])
        commits = list(
            dict.fromkeys(
                [failure.revision] + [c["version"] for c in failure.changes if c.get("version")]
            )
        )
        prs = self.bitbucket.context(commits)
        text = json.dumps([failure.changes, prs])
        keys = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+-\d+\b", text)))[:30]
        issues = self.jira.issues(keys) if self.jira and keys else []
        context = {
            "pull_requests": prs,
            "issues": issues,
            "ci_log": self.teamcity.build_log(failure.build_id)[-16000:],
        }
        write_json(self.directory / "context.json", context)
        return {"context": context, "attempt": 0, "status": "working"}

    def prepare(self, state: State) -> State:
        self.event("prepare")
        failure = Failure.model_validate(state["failure"])
        self.workspace.prepare(failure.revision)
        # A re-run from a later step starts its worktree from this exact commit.
        return {"branch": self.workspace.branch, "prepared_head": self.workspace.head()}

    def baseline(self, state: State) -> State:
        self.event("baseline")
        failure = Failure.model_validate(state["failure"])
        expected = matched_names(self.settings, failure)
        checks: list[dict[str, Any]] = []
        reference = None
        head = self.workspace.head() if self.settings.baseline_repetitions > 1 else None
        for index in range(self.settings.baseline_repetitions):
            label = "baseline" if index == 0 else f"baseline-repeat-{index + 1}"
            result = self.builder.verify(self.workspace.path, label)
            checks.append(result.model_dump())
            write_json(
                self.directory / "baseline-checks.json",
                {
                    "requested": self.settings.baseline_repetitions,
                    "observed": len(checks),
                    "checks": checks,
                },
            )
            evidence = {"baseline": checks[0], "baseline_checks": checks}
            if not result.build_ok:
                return {**evidence, "status": "blocked", "reason": "Baseline build failed"}
            if not result.evidence_valid:
                return {
                    **evidence,
                    "status": "blocked",
                    "reason": "Baseline test evidence is invalid or incomplete",
                }
            if head is not None and (
                self.workspace.head() != head or not self.workspace.is_clean()
            ):
                return {
                    **evidence,
                    "status": "blocked",
                    "reason": "Baseline verification changed tracked sources or commit",
                }
            outcomes = tuple(
                frozenset(getattr(result.report, name)) for name in ("passed", "failed", "skipped")
            )
            if reference is not None and outcomes != reference:
                return {
                    **evidence,
                    "status": "blocked",
                    "reason": "Baseline outcomes varied across repetitions; test suite is unstable",
                }
            if not expected or not expected.issubset(set(result.report.failed)):
                return {
                    **evidence,
                    "status": "blocked",
                    "reason": (
                        "Corresponding TC test failures were not reproduced after rebase; "
                        "check test_name_map or flaky tests"
                    ),
                }
            reference = outcomes
        return {
            "baseline": checks[0],
            "baseline_checks": checks,
            "feedback": result.output,
            "status": "working",
        }

    def _model_context(self, state: State, attempt: int) -> dict[str, Any]:
        cfg = self.settings
        budget = cfg.llm.context_chars
        structured = cfg.structured_diagnostics or cfg.max_inspections > 0
        failure = Failure.model_validate(state["failure"])
        signal_lines = "\n".join(
            [
                *(test.details for test in failure.tests),
                state.get("feedback", ""),
                state.get("context", {}).get("ci_log", ""),
            ]
        ).splitlines()
        signals = "\n".join(
            line
            for line in signal_lines
            if not re.match(r"^\s*\[\s*(?:RUN|OK|PASSED|={2,}|-{2,})\s*\]", line)
            and not re.match(r"^\s*\[\s*\d+%\]\s*(?:Built|Building|Linking)", line)
            and not re.match(
                r"^\s*\[\s*\d+/\d+\]\s+(?:Building|Linking|Creating|Completed|No\b)", line
            )
            and not re.search(r"\bTest\s+#\d+.*\bPassed\b", line)
        )
        if structured:
            signals = signals[:45000] + signals[-15000:]
            previous_edits = state.get("last_repair", {}).get("proposal", {}).get("edits", [])
            signals += (
                "\n"
                + "\n".join(
                    edit["path"] + "\n" + edit["old"] + "\n" + edit["new"]
                    for edit in previous_edits
                )[:15000]
            )
        test_names = [test["name"] for test in state["failure"]["tests"]]
        if structured:
            test_names = list(
                dict.fromkeys(
                    [
                        *state.get("verification", {}).get("report", {}).get("failed", []),
                        *test_names,
                    ]
                )
            )[:200]
        source = self.workspace.context(
            failure.changes,
            max_chars=budget // 3 if structured and cfg.max_inspections else budget // 2,
            test_names=test_names,
            signals=signals,
        )
        context = {
            "failure": state["failure"],
            "allowed_paths": cfg.repository.allowed_paths,
            "repository": source,
            "context": dict(state.get("context", {})),
            "previous_validation": state.get("feedback", "")[-12000:],
            "attempt": attempt,
        }
        if structured:
            # The immutable full failure set stays in state for validation. Only
            # model evidence is sampled so one broad regression cannot exhaust
            # its context with hundreds of repeated assertion messages.
            groups: dict[str, list] = {}
            for test in failure.tests:
                groups.setdefault(test.name.rsplit(".", 1)[0], []).append(test)
            representatives = []
            for offset in range(12):
                for tests in groups.values():
                    if offset < len(tests) and len(representatives) < 12:
                        test = tests[offset].model_dump()
                        test["details"] = test["details"][:700]
                        representatives.append(test)
            context["failure"] = {**state["failure"], "tests": representatives}
            context["failure_groups"] = {
                "total_failed_tests": len(failure.tests),
                "suites": [{"name": name, "count": len(tests)} for name, tests in groups.items()][
                    :50
                ],
                "representative_details_only": True,
            }
            context["previous_validation"] = failure_diagnostics(state.get("feedback", ""))
            baseline_checks = state.get("baseline_checks", [])
            latest_baseline = baseline_checks[-1] if baseline_checks else state.get("baseline", {})
            latest = state.get("verification", latest_baseline)
            context["latest_validation"] = {
                "build_ok": latest.get("build_ok"),
                "test_ok": latest.get("test_ok"),
                "failed": latest.get("report", {}).get("failed", [])[:100],
                "assertions": failed_assertions(latest, evidence_root=self.directory),
            }
            context["investigation"] = state.get("investigation", {})
            previous = state.get("last_repair")
            if previous:
                context["previous_repair"] = previous
                if len(json.dumps(previous)) > budget // 4:
                    context["previous_repair"] = {
                        **previous,
                        "proposal": {
                            "summary": previous.get("proposal", {}).get("summary", "")[:500],
                            "edits": [
                                {
                                    "path": edit["path"],
                                    "old": edit["old"][:1000],
                                    "new": edit["new"][:1000],
                                }
                                for edit in previous.get("proposal", {}).get("edits", [])
                            ],
                        },
                        "truncated": True,
                    }
        # Preserve valid structured evidence when pruning the auxiliary text budget.
        while len(json.dumps(context)) > budget and context["context"]:
            context["context"].pop(next(iter(context["context"])))
        if structured:
            while len(json.dumps(context)) > budget and len(context["repository"]["files"]) > 1:
                context["repository"]["files"].pop()
        if len(json.dumps(context)) > budget:
            raise ValueError("Context exceeds configured model budget")
        return context

    def investigate(self, state: State) -> State:
        count = state.get("inspections", 0)
        target_attempt = state.get("attempt", 0) + 1
        round_count = (
            state.get("round_inspections", 0)
            if state.get("inspection_round") == target_attempt
            else 0
        )
        if (
            count >= self.settings.max_inspections
            or round_count >= self.settings.inspections_per_attempt
        ):
            return {"status": "working"}
        count += 1
        round_count += 1
        progress = {
            "inspections": count,
            "inspection_round": target_attempt,
            "round_inspections": round_count,
        }
        self.event("investigate", inspection=count)
        try:
            context = self._model_context(state, state.get("attempt", 0) + 1)
            request = self.call_model("investigation", context, target_attempt)
            write_json(self.directory / f"investigation-{count}.json", request.model_dump())
            if request.ready and not request.queries and not request.reads:
                return {
                    **progress,
                    "investigation": {
                        **state.get("investigation", {}),
                        "hypotheses": request.hypotheses,
                    },
                    "status": "working",
                }
            if not request.queries and not request.reads:
                return {**progress, "status": "blocked", "reason": request.summary}
            evidence = gather_evidence(
                self.workspace, request, max_chars=min(24000, self.settings.llm.context_chars // 6)
            )
            previous = state.get("investigation", {}).get("evidence", [])
            combined = merge_evidence(
                previous, evidence, max_chars=min(48000, self.settings.llm.context_chars * 3 // 10)
            )
            report = {"hypotheses": request.hypotheses, "evidence": [combined]}
            write_json(self.directory / f"inspection-evidence-{count}.json", report)
            return {
                **progress,
                "investigation": report,
                "status": "inspecting"
                if (
                    count < self.settings.max_inspections
                    and round_count < self.settings.inspections_per_attempt
                    and not request.ready
                )
                else "working",
            }
        except (ValueError, RuntimeError, KeyError) as exc:
            return {
                **progress,
                "status": "blocked",
                "reason": "Investigation failed: " + redact(str(exc)),
            }

    def _repair_entry(self, state: State) -> str:
        return (
            "investigate"
            if state.get("inspections", 0) < self.settings.max_inspections
            else "repair"
        )

    def repair(self, state: State) -> State:
        attempt = state.get("attempt", 0) + 1
        self.event("repair", attempt=attempt)
        try:
            context = self._model_context(state, attempt)
        except ValueError as exc:
            return {"attempt": attempt, "status": "blocked", "reason": str(exc)}
        proposal = None
        try:
            proposal = self.call_model("repair", context, attempt)
            write_json(self.directory / f"proposal-{attempt}.json", proposal.model_dump())
            self.workspace.apply_edits(proposal.edits)
            refreshed = {
                **state.get("investigation", {}),
                "evidence": [
                    invalidate_evidence(
                        state.get("investigation", {}).get("evidence", []),
                        {edit.path for edit in proposal.edits},
                        max_chars=min(48000, self.settings.llm.context_chars * 3 // 10),
                    )
                ],
            }
            return {
                "attempt": attempt,
                "proposal": proposal.model_dump(),
                "last_repair": {
                    "attempt": attempt,
                    "proposal": proposal.model_dump(),
                    "applied": True,
                },
                "investigation": refreshed,
                "status": "working",
            }
        except (ValueError, RuntimeError, KeyError) as exc:
            return {
                "attempt": attempt,
                "feedback": redact(str(exc)),
                "last_repair": {
                    "attempt": attempt,
                    "proposal": proposal.model_dump() if proposal is not None else {},
                    "applied": False,
                },
                "status": "invalid_proposal",
            }

    def _required_tests(self, state: State) -> set[str]:
        failure = Failure.model_validate(state["failure"])
        baseline = state.get("baseline", {}).get("report", {})
        return {
            *matched_names(self.settings, failure),
            *baseline.get("passed", []),
            *baseline.get("failed", []),
        }

    def verify(self, state: State) -> State:
        self.event("verify", attempt=state["attempt"])
        result = self.builder.verify(self.workspace.path, f"attempt-{state['attempt']}")
        okay = validates_fix(result, self._required_tests(state))
        return {
            "verification": result.model_dump(),
            "feedback": result.output,
            "status": "validated" if okay else "verification_failed",
        }

    def finalize(self, state: State) -> State:
        self.event("finalize")
        if state.get("resume_ready"):
            if self.workspace.head() != state["head"] or not self.workspace.is_clean():
                raise RuntimeError(
                    "Prepared candidate changed since verification; refusing publication"
                )
            if (
                self.settings.baseline_repetitions > 1
                and len(state.get("baseline_checks", [])) < self.settings.baseline_repetitions
            ):
                return {
                    "status": "blocked",
                    "reason": "Saved candidate has fewer baseline checks than required; "
                    "start a fresh repair with the selected repetition policy",
                }
        else:
            self.workspace.commit(state["proposal"]["summary"])
        head = self.workspace.rebase()
        if not self.workspace.has_changes_against_base():
            return {
                "status": "blocked",
                "reason": "Candidate is identical to the latest base; no fix PR is needed",
            }
        result = self.builder.verify(self.workspace.path, "final-rebased")
        if not validates_fix(result, self._required_tests(state)):
            return {
                "verification": result.model_dump(),
                "status": "blocked",
                "reason": "Validation after final rebase failed",
            }
        if not self.workspace.is_clean() or head != self.workspace.head():
            raise RuntimeError("Build/test modified tracked sources; refusing publication")
        (self.directory / "fix.diff").write_text(
            redact(self.workspace.committed_diff()), encoding="utf-8"
        )
        return {"head": head, "verification": result.model_dump(), "status": "ready"}

    def publish_pr(self, state: State) -> State:
        self.event("publish_pr", enabled=self.publish)
        if not self.publish:
            return {"status": "ready"}
        if self.workspace.head() != state["head"] or not self.workspace.is_clean():
            raise RuntimeError("Verified candidate changed before push")
        existing = self.bitbucket.find_pr(
            self.workspace.branch, self.settings.repository.base_branch
        )
        if existing:
            require_verified_pr(
                existing, state["head"], self.workspace.branch, self.settings.repository.base_branch
            )
            write_json(
                self.directory / "publication.json",
                {
                    "status": "published",
                    "branch": self.workspace.branch,
                    "head": state["head"],
                    "pr": existing,
                    "reconciled": True,
                },
            )
            return {"status": "published", "pr": existing}
        if (self.directory / "publication.json").exists():
            raise RuntimeError(
                "Publication journal exists without a matching PR; reconcile before retrying"
            )
        # Persist intent before external side effects. Unknown outcomes are never blindly retried.
        write_json(
            self.directory / "publication.json",
            {
                "status": "intent",
                "branch": self.workspace.branch,
                "head": state["head"],
            },
        )
        self.workspace.push()
        pr = self.bitbucket.create_pr(
            self.workspace.branch,
            self.settings.repository.base_branch,
            "[auto-fix] " + state["proposal"]["summary"][:240],
            pr_description(state),
        )
        require_verified_pr(
            pr, state["head"], self.workspace.branch, self.settings.repository.base_branch
        )
        write_json(
            self.directory / "publication.json",
            {
                "status": "published",
                "branch": self.workspace.branch,
                "head": state["head"],
                "pr": pr,
            },
        )
        return {"status": "published", "pr": pr}

    def blocked(self, state: State) -> State:
        return {
            "status": "blocked",
            "reason": state.get("reason")
            or "Repair budget exhausted: " + state.get("feedback", "")[-2000:],
        }

    def graph(self, checkpointer: SqliteSaver | None = None):
        graph = StateGraph(State)
        for name in (
            "collect_context",
            "prepare",
            "baseline",
            "investigate",
            "repair",
            "verify",
            "finalize",
            "publish_pr",
            "blocked",
        ):
            graph.add_node(name, getattr(self, name))
        graph.add_conditional_edges(
            START,
            lambda s: "finalize" if s.get("resume_ready") else "collect_context",
            ["finalize", "collect_context"],
        )
        graph.add_edge("collect_context", "prepare")
        graph.add_edge("prepare", "baseline")
        graph.add_conditional_edges(
            "baseline",
            lambda s: self._repair_entry(s) if s["status"] == "working" else "blocked",
            ["investigate", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "investigate",
            lambda s: (
                "blocked"
                if s["status"] == "blocked"
                else "investigate"
                if s["status"] == "inspecting"
                else "repair"
            ),
            ["investigate", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "repair",
            lambda s: (
                "blocked"
                if s["status"] == "blocked"
                else "verify"
                if s["status"] == "working"
                else self._repair_entry(s)
                if s["attempt"] < self.settings.max_attempts
                else "blocked"
            ),
            ["verify", "investigate", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "verify",
            lambda s: (
                "finalize"
                if s["status"] == "validated"
                else self._repair_entry(s)
                if s["attempt"] < self.settings.max_attempts
                else "blocked"
            ),
            ["finalize", "investigate", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "finalize",
            lambda s: "publish_pr" if s["status"] == "ready" else "blocked",
            ["publish_pr", "blocked"],
        )
        graph.add_edge("publish_pr", END)
        graph.add_edge("blocked", END)
        return graph.compile(checkpointer=checkpointer)

    def run(self, initial: State | None) -> State:
        """Run the graph from ``initial``, or continue the run's thread from its last checkpoint.

        After every step the run honours a pause or cancel request from ``control.json``: the
        step's checkpoint is already saved, so a paused run resumes with the next step.
        """
        state: State = initial if initial is not None else self._saved_result()
        # A request left from an earlier process must not stop this one before it starts.
        control.clear(self.directory)
        control.mark_process(self.directory)
        try:
            with (
                tracing.session(self.run_id),
                sqlite3.connect(
                    self.directory / "checkpoints.sqlite", check_same_thread=False
                ) as conn,
            ):
                graph = self.graph(SqliteSaver(conn))
                config = {"configurable": {"thread_id": self.run_id}, "recursion_limit": 60}
                if initial is None:
                    saved = graph.get_state(config).values
                    if not saved:
                        raise RuntimeError("This run has no checkpoint to resume from")
                    state = dict(saved)
                    self.event("resumed")
                for update in graph.stream(
                    initial, config, stream_mode="updates", durability="sync"
                ):
                    for value in update.values():
                        if isinstance(value, dict):
                            state = {**state, **value}
                            write_json(self.directory / "result.json", state)
                    stop = control.pending(self.directory)
                    if stop:
                        status = "paused" if stop["request"] == "pause" else "cancelled"
                        verb = "Paused" if status == "paused" else "Cancelled"
                        state = {**state, "status": status, "reason": f"{verb} by {stop['by']}"}
                        self.event(status, by=stop["by"])
                        control.clear(self.directory)
                        break
        except Exception as exc:
            publication = self.directory / "publication.json"
            unknown = (
                publication.exists() and json.loads(publication.read_text())["status"] == "intent"
            )
            state = {
                **state,
                "status": "publication_unknown" if unknown else "blocked",
                "reason": redact(f"{type(exc).__name__}: {exc}"),
            }
            self.event("stopped", status=state["status"], reason=state["reason"])
        finally:
            control.clear_process(self.directory)
        write_json(self.directory / "result.json", state)
        return state


def fork(flow: Workflow, source: Path, step_index: int) -> None:
    """Seed ``flow``, a new run, to continue ``source`` from one of its steps.

    Call ``flow.run(None)`` afterwards.

    The new worktree starts from the commit the source run prepared, with the edits its
    earlier repairs applied, and the new thread starts from the checkpoint the chosen step
    started from. The source run is never modified.
    """
    from auto_fix import history
    from auto_fix.models import Edit

    saved, executed = history.run_steps(source)
    if not saved:
        raise ValueError("This run has no checkpoints to re-run from")
    if not 0 < step_index < len(executed):
        raise ValueError("That step cannot be re-run")
    step = executed[step_index]
    if step["node"] not in {"baseline", "investigate", "repair", "verify"}:
        raise ValueError(f"A re-run cannot start at {step['node']}")
    values = next(item["values"] for item in saved if item["step"] == step["from_checkpoint"])
    applied = []
    for earlier in executed[:step_index]:
        repair = earlier["changes"].get("last_repair") or {}
        if earlier["node"] == "repair" and repair.get("applied"):
            proposal = json.loads(
                (source / f"proposal-{repair['attempt']}.json").read_text(encoding="utf-8")
            )
            applied.append([Edit.model_validate(edit) for edit in proposal["edits"]])
    run_id = flow.run_id
    start = values.get("prepared_head")
    flow.workspace.prepare(values["failure"]["revision"], start=start)
    for edits in applied:
        flow.workspace.apply_edits(edits)
    state = {
        **values,
        "run_id": run_id,
        "branch": flow.workspace.branch,
        "prepared_head": start or flow.workspace.head(),
    }
    with sqlite3.connect(flow.directory / "checkpoints.sqlite", check_same_thread=False) as conn:
        graph = flow.graph(SqliteSaver(conn))
        graph.update_state(
            {"configurable": {"thread_id": run_id}}, state, as_node=executed[step_index - 1]["node"]
        )
    flow.event(
        "forked",
        source=source.name,
        step=step_index,
        from_node=step["node"],
        edits_replayed=len(applied),
        same_commit=bool(start),
    )
    write_json(flow.directory / "result.json", state)
