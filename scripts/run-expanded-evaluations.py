"""Run frozen Luna plans or report existing runs without launching a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_fix.experiment import run_plan, summarize_runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--directory", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--workdir", type=Path, default=Path.cwd())
    report = commands.add_parser("report")
    report.add_argument("--runs", type=Path, required=True, help="JSON list of run descriptors")
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--report-split", choices=["development", "holdout"], required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_plan(args.plan, args.directory, workdir=args.workdir, resume=args.resume)
        print(json.dumps(result, indent=2))
        return result["returncode"]
    result = summarize_runs(
        json.loads(args.runs.read_text(encoding="utf-8")),
        args.output,
        report_split=args.report_split,
    )
    print(json.dumps(result["groups"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
