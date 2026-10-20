"""Evaluation-only adapter using an explicitly selected model through the Codex CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from auto_fix.llm import SYSTEM
from auto_fix.models import Proposal
from auto_fix.workflow import write_json


class CodexRepairModel:
    """Give the real model exactly the workflow packet; reject external tool use."""

    def __init__(self, directory: Path, model: str = "gpt-6-luna", timeout: int = 180):
        self.directory = directory.resolve()
        self.model = model
        self.timeout = timeout
        self.calls: list[dict[str, Any]] = []

    def propose(self, context: dict[str, Any]) -> Proposal:
        executable = shutil.which("codex")
        if not executable:
            raise RuntimeError("Install and authenticate Codex CLI to run live Luna evaluations")
        directory = self.directory / f"call-{len(self.calls) + 1}"
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "request.json", {"system": SYSTEM, "context": context})
        write_json(directory / "schema.json", Proposal.model_json_schema())
        argv = [
            executable,
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            self.model,
            "-c",
            'model_reasoning_effort="medium"',
            "--json",
            "--output-schema",
            str(directory / "schema.json"),
            "--output-last-message",
            str(directory / "response.json"),
            "-",
        ]
        prompt = (
            "You are the repair-model component of an automated workflow evaluation. "
            "Use ONLY the system instructions and JSON context supplied in this message. "
            "Do not call tools, read files, inspect a repository or search online. "
            "The runner will apply your proposed edits and compile/test them. "
            "Return the requested JSON object only.\n\nSYSTEM INSTRUCTIONS:\n"
            + SYSTEM
            + "\n\nWORKFLOW CONTEXT:\n"
            + json.dumps(context, ensure_ascii=False)
        )
        started = time.monotonic()
        with (directory / "events.jsonl").open("w", encoding="utf-8") as output:
            with (directory / "stderr.log").open("w", encoding="utf-8") as errors:
                try:
                    result = subprocess.run(
                        argv,
                        input=prompt,
                        encoding="utf-8",
                        cwd=directory,
                        stdout=output,
                        stderr=errors,
                        timeout=self.timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    raise RuntimeError("Evaluation model call timed out") from None
        events = []
        for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        usage = next((e.get("usage", {}) for e in events if e.get("type") == "turn.completed"), {})
        call = {
            "model": self.model,
            "transport": "codex-cli",
            "reasoning_effort": "medium",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "returncode": result.returncode,
            "usage": usage,
            "directory": str(directory),
        }
        self.calls.append(call)
        write_json(directory / "metadata.json", call)
        tool_types = {"command_execution", "file_change", "mcp_tool_call", "web_search"}
        if any(e.get("item", {}).get("type") in tool_types for e in events):
            raise RuntimeError("Evaluation invalid: repair model attempted outside tool access")
        response = directory / "response.json"
        if result.returncode or not response.is_file():
            errors = [e for e in events if e.get("type") in {"error", "turn.failed"}]
            raise RuntimeError(f"Codex model call failed (exit {result.returncode}): {errors}")
        return Proposal.model_validate_json(response.read_text(encoding="utf-8"))

    def close(self) -> None:
        pass
