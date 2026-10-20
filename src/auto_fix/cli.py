from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from filelock import FileLock, Timeout

from auto_fix.config import load_settings
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.llm import RepairModel
from auto_fix.publication import require_verified_pr
from auto_fix.workflow import Workflow, failure_key, redact, write_json

MERMAID = """flowchart TD
  A[TeamCity: today's failed tests] --> B[Git / Bitbucket / Jira context]
  B --> C[Isolated checkout: rebase onto master]
  C --> D[Build + reproduce original test failures]
  D -->|reproduced| R[Optional bounded source investigation]
  R --> E[Configured model such as Qwen: bounded source edits]
  D -->|not reproduced| X[Stop with evidence]
  E --> F[Native build + full tests + configured additional suites]
  F -->|failed; attempts remain| R
  F -->|passed| G[Commit + rebase onto latest master]
  F -->|budget exhausted| X
  G --> H[Rebuild + full verification / all baseline tests retained]
  H -->|passed| I[Local candidate / verified Bitbucket PR with --publish]
  H -->|failed| X
"""


def recover_publication(state_dir: Path, key: str, bitbucket: Bitbucket, base: str):
    """The write-ahead journal wins over a stale receipt across all repair attempts."""
    runs = state_dir / "runs"
    if not runs.exists():
        return None
    candidates = [
        path
        for path in runs.iterdir()
        if path.is_dir() and re.fullmatch(re.escape(key) + r"(?:-r\d+)?", path.name)
    ]
    candidates.sort(
        key=lambda path: int(path.name.rsplit("-r", 1)[1]) if "-r" in path.name else 0, reverse=True
    )
    for path in candidates:
        publication = path / "publication.json"
        if not publication.exists():
            continue
        journal = json.loads(publication.read_text(encoding="utf-8"))
        result = path / "result.json"
        saved = json.loads(result.read_text(encoding="utf-8")) if result.exists() else {}
        branch = journal.get("branch", saved.get("branch", f"auto-fix/{path.name}"))
        saved.update(run_id=path.name, branch=branch)
        # The journal is written immediately before side effects and takes
        # precedence over an older checkpoint or receipt.
        head = journal.get("head", saved.get("head"))
        existing = (
            journal.get("pr")
            if journal["status"] == "published"
            else bitbucket.find_pr(branch, base)
        )
        try:
            require_verified_pr(existing, head, branch, base)
        except RuntimeError as exc:
            saved.update(status="publication_unknown", reason=str(exc))
        else:
            saved.update(status="published", head=head, pr=existing)
            saved.pop("reason", None)
            write_json(
                publication,
                {"status": "published", "branch": branch, "head": head, "pr": existing},
            )
        return saved
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TeamCity C++ failure repair with LangGraph")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--config", type=Path, required=True)
        sub.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
        if name == "run":
            sub.add_argument(
                "--publish",
                action="store_true",
                help="Push verified branches and create Bitbucket PRs",
            )
            sub.add_argument(
                "--retry-blocked",
                action="store_true",
                help="Retry stopped repairs in a fresh worktree",
            )
    demo = commands.add_parser("demo")
    demo.add_argument("--directory", type=Path, default=Path(".auto-fix/demo"))
    evaluation = commands.add_parser(
        "evaluate", help="Run large C++ fixtures with a live repair model"
    )
    evaluation.add_argument("--directory", type=Path, required=True)
    evaluation.add_argument("--profile", choices=["legacy", "focused"], default="focused")
    evaluation.add_argument("--backend", choices=["codex", "endpoint", "replay"], default="codex")
    evaluation.add_argument("--model", default="gpt-6-luna")
    evaluation.add_argument("--case", action="append", dest="cases")
    evaluation.add_argument("--upstream-cache", type=Path, default=Path(".auto-fix/upstream"))
    evaluation.add_argument("--config", type=Path)
    evaluation.add_argument("--recordings", type=Path)
    evaluation.add_argument("--project-file", type=Path)
    evaluation.add_argument("--cases-file", type=Path)
    evaluation.add_argument("--split", choices=["development", "holdout"])
    evaluation.add_argument(
        "--prompt", choices=["repair-v1", "evidence-v2", "contract-v3"], default="repair-v1"
    )
    evaluation.add_argument("--max-inspections", type=int, default=0)
    evaluation.add_argument("--inspections-per-attempt", type=int, default=6)
    evaluation.add_argument("--max-attempts", type=int, default=2)
    evaluation.add_argument("--baseline-repetitions", type=int, default=1)
    evaluation.add_argument("--structured-diagnostics", action="store_true")
    evaluation.add_argument("--context-chars", type=int, default=60000)
    evaluation.add_argument("--definition-reads", action="store_true")
    evaluation.add_argument("--reasoning-effort", choices=["medium", "high"], default="medium")
    operations = commands.add_parser(
        "evaluate-operations", help="Exercise real Git/native workflow fault scenarios with Luna"
    )
    operations.add_argument("--directory", type=Path, required=True)
    operations.add_argument(
        "--prompt", choices=["repair-v1", "evidence-v2", "contract-v3"], default="contract-v3"
    )
    operations.add_argument("--max-inspections", type=int, default=1)
    operations.add_argument("--inspections-per-attempt", type=int, default=6)
    operations.add_argument("--baseline-repetitions", type=int, default=1)
    operations.add_argument("--context-chars", type=int, default=60000)
    operations.add_argument("--definition-reads", action="store_true")
    operations.add_argument("--reasoning-effort", choices=["medium", "high"], default="medium")
    operations.add_argument("--upstream-cache", type=Path)
    operations.add_argument("--case", action="append", dest="cases")
    commands.add_parser("graph")
    args = parser.parse_args(argv)
    if args.command == "graph":
        print(MERMAID)
        return 0
    if args.command == "demo":
        from auto_fix.demo import run_demo

        return run_demo(args.directory)
    if args.command == "evaluate-operations":
        from auto_fix.operational_evaluation import run_operational_evaluation

        return run_operational_evaluation(
            args.directory,
            prompt_version=args.prompt,
            max_inspections=args.max_inspections,
            inspections_per_attempt=args.inspections_per_attempt,
            baseline_repetitions=args.baseline_repetitions,
            context_chars=args.context_chars,
            definition_reads=args.definition_reads,
            reasoning_effort=args.reasoning_effort,
            upstream_cache=args.upstream_cache,
            selected=args.cases,
        )
    if args.command == "evaluate":
        from auto_fix.evaluation import run_evaluation

        return run_evaluation(
            args.directory,
            profile=args.profile,
            backend=args.backend,
            model_name=args.model,
            selected=args.cases,
            upstream_cache=args.upstream_cache,
            endpoint_config=args.config,
            recordings=args.recordings,
            project_file=args.project_file,
            cases_file=args.cases_file,
            split=args.split,
            prompt_version=args.prompt,
            max_inspections=args.max_inspections,
            inspections_per_attempt=args.inspections_per_attempt,
            max_attempts=args.max_attempts,
            baseline_repetitions=args.baseline_repetitions,
            reasoning_effort=args.reasoning_effort,
            structured_diagnostics=args.structured_diagnostics,
            context_chars=args.context_chars,
            definition_reads=args.definition_reads,
        )
    # Configuration-adjacent secrets work independently of Task Scheduler's working directory.
    load_dotenv(args.config.resolve().parent / ".env", override=False)
    services = []
    try:
        settings = load_settings(args.config)
        day = args.date or datetime.now(ZoneInfo(settings.timezone)).date()
        tc = TeamCity(settings.teamcity)
        services.append(tc)
        if args.command == "scan":
            failures = tc.failures(day, settings.timezone)
            print(redact(json.dumps([f.model_dump() for f in failures], indent=2)))
            return 0
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        # Single worker protects worktrees, SQLite journals and one 27B inference endpoint.
        with FileLock(str(settings.state_dir / "worker.lock"), timeout=0):
            failures = tc.failures(day, settings.timezone)
            bb = Bitbucket(settings.bitbucket)
            model = RepairModel(settings.llm)
            jira = Jira(settings.jira) if settings.jira else None
            services.extend([bb, model] + ([jira] if jira else []))
            statuses = []
            for failure in failures:
                key = failure_key(failure)
                receipt = settings.state_dir / "receipts" / f"{key}.json"
                previous = (
                    json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else None
                )
                recovered = recover_publication(
                    settings.state_dir, key, bb, settings.repository.base_branch
                )
                if recovered:
                    write_json(receipt, recovered)
                    statuses.append(recovered)
                    print(f"{key}: {recovered['status']} (publication journal)")
                    continue
                if previous and previous["status"] == "publication_unknown":
                    existing = bb.find_pr(previous["branch"], settings.repository.base_branch)
                    try:
                        require_verified_pr(
                            existing,
                            previous.get("head"),
                            previous["branch"],
                            settings.repository.base_branch,
                        )
                    except RuntimeError as exc:
                        previous.update(reason=str(exc))
                        write_json(receipt, previous)
                        print(f"{key}: publication outcome unknown; {exc}")
                    else:
                        previous.update(status="published", pr=existing)
                        previous.pop("reason", None)
                        write_json(receipt, previous)
                    statuses.append(previous)
                    continue
                if previous and previous["status"] == "published":
                    try:
                        require_verified_pr(
                            previous.get("pr"),
                            previous.get("head"),
                            previous.get("branch", ""),
                            settings.repository.base_branch,
                        )
                    except RuntimeError as exc:
                        previous.update(status="publication_unknown", reason=str(exc))
                        write_json(receipt, previous)
                        print(f"{key}: publication receipt needs reconciliation; {exc}")
                    else:
                        print(f"{key}: already published")
                    statuses.append(previous)
                    continue
                ready = previous and previous["status"] == "ready"
                if previous and not (ready and args.publish) and not args.retry_blocked:
                    print(f"{key}: {previous['status']} (saved candidate/evidence)")
                    statuses.append(previous)
                    continue
                if ready and not args.publish:
                    statuses.append(previous)
                    continue
                # A prior run directory without a receipt may have crashed between side effects.
                # Inspect its persisted result/publication intent instead of replaying the graph.
                if not previous:
                    original = settings.state_dir / "runs" / key
                    if original.exists():
                        result_file = original / "result.json"
                        publication_file = original / "publication.json"
                        if publication_file.exists():
                            saved = (
                                json.loads(result_file.read_text(encoding="utf-8"))
                                if result_file.exists()
                                else {}
                            )
                            saved.update(
                                status="publication_unknown", branch=f"auto-fix/{key}", run_id=key
                            )
                            write_json(receipt, saved)
                            print(
                                f"{key}: interrupted publication; rerun to reconcile the remote PR"
                            )
                            statuses.append(saved)
                            continue
                        if not args.retry_blocked:
                            saved = {
                                "run_id": key,
                                "status": "blocked",
                                "reason": (
                                    "Interrupted local run; use --retry-blocked for a fresh attempt"
                                ),
                            }
                            write_json(receipt, saved)
                            statuses.append(saved)
                            continue
                if ready:
                    run_id = previous["run_id"]
                    initial = {**previous, "resume_ready": True}
                else:
                    attempt = 0
                    run_id = key
                    while (settings.state_dir / "runs" / run_id).exists():
                        attempt += 1
                        run_id = f"{key}-r{attempt}"
                    initial = {"run_id": run_id, "failure": failure.model_dump()}
                flow = Workflow(settings, run_id, tc, bb, jira, model, publish=args.publish)
                result = flow.run(initial)
                write_json(receipt, result)
                statuses.append(result)
            print(redact(json.dumps({"date": str(day), "results": statuses}, indent=2)))
            return int(any(s["status"] not in {"ready", "published"} for s in statuses))
    except Timeout:
        print("A worker is already running for this state directory")
        return 2
    except Exception as exc:
        print(redact(f"{type(exc).__name__}: {exc}"))
        return 2
    finally:
        for service in reversed(services):
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
