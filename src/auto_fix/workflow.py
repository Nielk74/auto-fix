from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from auto_fix.build import Builder
from auto_fix.config import Settings
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.llm import RepairModel
from auto_fix.models import Failure, Verification
from auto_fix.workspace import Workspace


class State(TypedDict, total=False):
    run_id: str
    failure: dict[str, Any]
    context: dict[str, Any]
    attempt: int
    feedback: str
    proposal: dict[str, Any]
    baseline: dict[str, Any]
    verification: dict[str, Any]
    status: str
    reason: str
    head: str
    branch: str
    pr: dict[str, Any]
    resume_ready: bool


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


def matched_names(settings: Settings, failure: Failure) -> set[str]:
    return {settings.build.test_name_map.get(t.name, t.name) for t in failure.tests}


def validates_fix(report: Verification, expected: set[str]) -> bool:
    return report.build_ok and report.test_ok and expected.issubset(set(report.report.passed))


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
        f"[Screenshot artifact]({url})\n\n![TeamCity screenshot]({url})"
        for url in failure.evidence_urls
    )
    links_text = "\n".join(links)
    return redact(
        f"{proposal.get('explanation', 'Automated repair candidate.')}\n\n"
        f"Reproduced failing tests:\n{tests}\n\n"
        f"Original TeamCity revision: `{failure.revision}`\n\n"
        f"Verified commit after rebasing onto the configured base: `{state['head']}`\n\n"
        "Validation: configured native build and full test command passed; originally failing "
        "tests are present and passing in the fresh JUnit report.\n\n"
        f"Context:\n{links_text}\n\n{evidence}\n\n"
        f"Automation run: `{state['run_id']}`. AI-generated candidate; review before merging."
    )


class Workflow:
    """Small readable graph; only repair uses an LLM. Side effects have explicit gates."""

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

    def event(self, node: str, **details: Any) -> None:
        event = {"time": datetime.now(UTC).isoformat(), "node": node, **details}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(redact(json.dumps(event)) + "\n")
        print(f"[{self.run_id}] {node}", flush=True)

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
        return {"branch": self.workspace.branch}

    def baseline(self, state: State) -> State:
        self.event("baseline")
        result = self.builder.verify(self.workspace.path, "baseline")
        failure = Failure.model_validate(state["failure"])
        expected = matched_names(self.settings, failure)
        if not result.build_ok:
            return {
                "baseline": result.model_dump(),
                "status": "blocked",
                "reason": "Baseline build failed",
            }
        if not expected or not expected.issubset(set(result.report.failed)):
            return {
                "baseline": result.model_dump(),
                "status": "blocked",
                "reason": (
                    "Corresponding TC test failures were not reproduced after rebase; "
                    "check test_name_map or flaky tests"
                ),
            }
        return {"baseline": result.model_dump(), "feedback": result.output, "status": "working"}

    def repair(self, state: State) -> State:
        attempt = state.get("attempt", 0) + 1
        self.event("repair", attempt=attempt)
        cfg = self.settings
        budget = cfg.llm.context_chars
        source = self.workspace.context(
            Failure.model_validate(state["failure"]).changes,
            max_chars=budget // 2,
            test_names=[test["name"] for test in state["failure"]["tests"]],
        )
        context = {
            "failure": state["failure"],
            "allowed_paths": cfg.repository.allowed_paths,
            "repository": source,
            "context": dict(state.get("context", {})),
            "previous_validation": state.get("feedback", "")[-12000:],
            "attempt": attempt,
        }
        # Preserve valid structured evidence when pruning the auxiliary text budget.
        while len(json.dumps(context)) > budget and context["context"]:
            context["context"].pop(next(iter(context["context"])))
        if len(json.dumps(context)) > budget:
            return {
                "attempt": attempt,
                "status": "blocked",
                "reason": "Context exceeds configured model budget",
            }
        try:
            proposal = self.model.propose(context)
            self.workspace.apply_edits(proposal.edits)
            write_json(self.directory / f"proposal-{attempt}.json", proposal.model_dump())
            return {"attempt": attempt, "proposal": proposal.model_dump(), "status": "working"}
        except (ValueError, RuntimeError, KeyError) as exc:
            return {"attempt": attempt, "feedback": redact(str(exc)), "status": "invalid_proposal"}

    def verify(self, state: State) -> State:
        self.event("verify", attempt=state["attempt"])
        result = self.builder.verify(self.workspace.path, f"attempt-{state['attempt']}")
        failure = Failure.model_validate(state["failure"])
        okay = validates_fix(result, matched_names(self.settings, failure))
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
        else:
            self.workspace.commit(state["proposal"]["summary"])
        head = self.workspace.rebase()
        if not self.workspace.has_changes_against_base():
            return {
                "status": "blocked",
                "reason": "Candidate is identical to the latest base; no fix PR is needed",
            }
        result = self.builder.verify(self.workspace.path, "final-rebased")
        failure = Failure.model_validate(state["failure"])
        if not validates_fix(result, matched_names(self.settings, failure)):
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
            remote_head = existing.get("fromRef", {}).get("latestCommit")
            if remote_head and remote_head != state["head"]:
                raise RuntimeError("Existing PR head differs from the verified candidate")
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
        remote_head = pr.get("fromRef", {}).get("latestCommit")
        if remote_head and remote_head != state["head"]:
            raise RuntimeError("Created PR head differs from the verified candidate")
        write_json(self.directory / "publication.json", {"status": "published", "pr": pr})
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
            lambda s: "repair" if s["status"] == "working" else "blocked",
            ["repair", "blocked"],
        )
        graph.add_conditional_edges(
            "repair",
            lambda s: (
                "blocked"
                if s["status"] == "blocked"
                else "verify"
                if s["status"] == "working"
                else "repair"
                if s["attempt"] < self.settings.max_attempts
                else "blocked"
            ),
            ["verify", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "verify",
            lambda s: (
                "finalize"
                if s["status"] == "validated"
                else "repair"
                if s["attempt"] < self.settings.max_attempts
                else "blocked"
            ),
            ["finalize", "repair", "blocked"],
        )
        graph.add_conditional_edges(
            "finalize",
            lambda s: "publish_pr" if s["status"] == "ready" else "blocked",
            ["publish_pr", "blocked"],
        )
        graph.add_edge("publish_pr", END)
        graph.add_edge("blocked", END)
        return graph.compile(checkpointer=checkpointer)

    def run(self, initial: State) -> State:
        state = initial
        try:
            with sqlite3.connect(
                self.directory / "checkpoints.sqlite", check_same_thread=False
            ) as conn:
                graph = self.graph(SqliteSaver(conn))
                for update in graph.stream(
                    initial,
                    {"configurable": {"thread_id": self.run_id}, "recursion_limit": 60},
                    stream_mode="updates",
                    durability="sync",
                ):
                    for value in update.values():
                        if isinstance(value, dict):
                            state = {**state, **value}
                            write_json(self.directory / "result.json", state)
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
        write_json(self.directory / "result.json", state)
        return state
