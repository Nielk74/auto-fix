"""Explicit offline replay of recorded model responses; no live inference occurs."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from auto_fix.models import Proposal


class RecordedRepairModel:
    """Replay sequential public-code repair responses for regression checks.

    This backend checks workflow mechanics against previously generated edits.
    It cannot measure model quality on a new failure. It never calls a model or
    falls back to another provider, and never modifies the source recordings.
    """

    def __init__(self, directory: Path, expected_model: str = "gpt-6-luna"):
        self.directory = directory.resolve()
        if not self.directory.is_dir():
            raise ValueError("Recorded replay requires an existing recording directory")
        if not expected_model:
            raise ValueError("Recorded replay requires an expected model identity")
        self.expected_model = expected_model
        self.calls: list[dict[str, Any]] = []

    def propose(self, context: dict[str, Any]) -> Proposal:
        # The recording contains the prior model's output, never an oracle patch
        # supplied by the caller. Context still goes through the normal workflow
        # and apply/build/test gates; replay does not inspect or change it.
        del context
        number = len(self.calls) + 1
        directory = self.directory / f"call-{number}"
        started = time.monotonic()
        call: dict[str, Any] = {
            "model": self.expected_model,
            "transport": "recorded-replay",
            "live_inference": False,
            "recording": str(directory),
            "usage": {},
            "recorded_usage": {},
            "returncode": 1,
        }
        self.calls.append(call)
        try:
            metadata_path = directory / "metadata.json"
            response_path = directory / "response.json"
            if not metadata_path.is_file() or not response_path.is_file():
                raise RuntimeError(f"Recorded replay call-{number} is missing response or metadata")
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise RuntimeError(
                    f"Recorded replay call-{number} has unreadable metadata"
                ) from exc
            if not isinstance(metadata, dict):
                raise RuntimeError(f"Recorded replay call-{number} metadata must be an object")
            if metadata.get("model") != self.expected_model:
                raise RuntimeError(
                    f"Recorded replay call-{number} model differs from expected "
                    f"{self.expected_model}"
                )
            returncode = metadata.get("returncode")
            if type(returncode) is not int or returncode != 0:
                raise RuntimeError(f"Recorded replay call-{number} did not complete successfully")
            try:
                response = response_path.read_bytes()
                proposal = Proposal.model_validate_json(response)
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"Recorded replay call-{number} contains an invalid proposal"
                ) from exc
            call.update(
                {
                    "returncode": 0,
                    "recorded_usage": metadata.get("usage", {}),
                    "provenance": {
                        "metadata": metadata,
                        "response_sha256": hashlib.sha256(response).hexdigest(),
                    },
                }
            )
            return proposal
        except RuntimeError as exc:
            call["error"] = str(exc)
            raise
        finally:
            call["elapsed_seconds"] = round(time.monotonic() - started, 3)

    def close(self) -> None:
        pass
