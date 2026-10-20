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
from auto_fix.workflow import Workflow, failure_key, redact, write_json

MERMAID = """flowchart TD
  A[TeamCity: today's failed tests] --> B[Git / Bitbucket / Jira context]
  B --> C[Isolated checkout: rebase onto master]
  C --> D[Build + reproduce original test failures]
  D -->|reproduced| E[Qwen: propose bounded source edits]
  D -->|not reproduced| X[Stop with evidence]
  E --> F[Native build + full tests / fresh JUnit]
  F -->|failed; attempts remain| E
  F -->|passed| G[Commit + rebase onto latest master]
  F -->|budget exhausted| X
  G --> H[Rebuild + full tests + original tests passing]
  H -->|passed| I[Local candidate / Bitbucket PR with --publish]
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
        if journal["status"] == "published":
            saved.update(status="published", pr=journal["pr"])
        else:
            existing = bitbucket.find_pr(branch, base)
            if existing:
                saved.update(status="published", pr=existing)
                write_json(publication, {"status": "published", "branch": branch, "pr": existing})
            else:
                saved.update(
                    status="publication_unknown",
                    reason="Interrupted publication; inspect remote branch/PR before retrying",
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
    commands.add_parser("graph")
    args = parser.parse_args(argv)
    if args.command == "graph":
        print(MERMAID)
        return 0
    if args.command == "demo":
        from auto_fix.demo import run_demo

        return run_demo(args.directory)
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
                    if existing:
                        previous.update(status="published", pr=existing)
                        write_json(receipt, previous)
                    else:
                        print(
                            f"{key}: publication outcome unknown; "
                            "inspect remote branch/PR before retrying"
                        )
                    statuses.append(previous)
                    continue
                if previous and previous["status"] == "published":
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
