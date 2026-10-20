"""Copy public-code evaluation evidence into reviewable repository artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def export(rounds: dict[str, Path], destination: Path, accepted: str) -> None:
    index = {"model": "gpt-6-luna", "live_inference_transport": "codex-cli", "rounds": []}
    for name, source in rounds.items():
        summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
        if summary["backend"] != "codex" or summary["model"] != "gpt-6-luna":
            raise ValueError(
                "Only actual Luna model evaluations belong in this live-results export"
            )
        target = destination / "results" / name
        target.mkdir(parents=True, exist_ok=True)
        copied: dict[str, str] = {}

        def copy(original: Path, relative: str, target=target, copied=copied) -> None:
            if not original.is_file():
                return
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, output)
            copied[relative] = hashlib.sha256(output.read_bytes()).hexdigest()

        copy(source / "manifest.json", "manifest.json")
        for case in summary["cases"]:
            case_name = case["case"]
            current = source / case_name
            result = Path(case["result"])
            state = json.loads(result.read_text(encoding="utf-8"))
            for file in ("score.json", "requests.json", "pull-requests.json"):
                copy(current / file, f"{case_name}/{file}")
            for file in ("result.json", "context.json", "events.jsonl", "fix.diff"):
                copy(result.parent / file, f"{case_name}/{file}")
            for phase in ("baseline", "verification"):
                for log in state.get(phase, {}).get("logs", []):
                    path = Path(log)
                    prefix = "baseline" if phase == "baseline" else "final"
                    copy(path, f"{case_name}/native/{prefix}-{path.name}")
            for call in sorted((current / "model").glob("call-*")):
                for file in ("request.json", "response.json", "metadata.json", "events.jsonl"):
                    copy(call / file, f"{case_name}/model/{call.name}/{file}")
                if name == accepted:
                    if not case["success"]:
                        raise ValueError(
                            "Accepted replay recordings must all pass native validation"
                        )
                    recorded = destination / "recordings" / "accepted" / case_name / call.name
                    recorded.mkdir(parents=True, exist_ok=True)
                    for file in ("response.json", "metadata.json"):
                        shutil.copyfile(call / file, recorded / file)
            case["exported_evidence"] = case_name
        (target / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        copied["summary.json"] = hashlib.sha256((target / "summary.json").read_bytes()).hexdigest()
        (target / "SHA256SUMS.json").write_text(json.dumps(copied, indent=2), encoding="utf-8")
        calls = [call for case in summary["cases"] for call in case["model_calls"]]
        index["rounds"].append(
            {
                "name": name,
                "successes": summary["successes"],
                "total": summary["total"],
                "model_calls": len(calls),
                "elapsed_seconds": round(
                    sum(case["elapsed_seconds"] for case in summary["cases"]), 3
                ),
                "input_tokens": sum(call["usage"].get("input_tokens", 0) for call in calls),
                "output_tokens": sum(call["usage"].get("output_tokens", 0) for call in calls),
                "summary": f"{name}/summary.json",
            }
        )
    (destination / "results" / "index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="NAME=directory")
    parser.add_argument("--destination", type=Path, default=Path("evaluation"))
    parser.add_argument("--accepted", default="focused-v2")
    args = parser.parse_args()
    rounds = {}
    for value in args.run:
        name, path = value.split("=", 1)
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Round name must contain only letters, digits, hyphens and underscores"
            )
        rounds[name] = Path(path)
    if args.accepted not in rounds:
        raise ValueError("Accepted replay source must be one of the supplied runs")
    export(rounds, args.destination, args.accepted)


if __name__ == "__main__":
    main()
