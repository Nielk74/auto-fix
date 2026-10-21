from __future__ import annotations

import json
import re
import ssl
from typing import Any, TypeVar

import httpx

from auto_fix.config import LLMConfig
from auto_fix.models import Investigation, Model, Proposal
from auto_fix.prompts import BASELINE, INVESTIGATE, repair_prompt

SYSTEM = BASELINE
Response = TypeVar("Response", bound=Model)


class RepairModel:
    """Standard Chat Completions; no native tool calling/JSON mode dependency."""

    def __init__(self, config: LLMConfig, client: httpx.Client | None = None):
        self.config = config
        self._owns_client = client is None
        verify = ssl.create_default_context(cafile=config.ca_bundle) if config.ca_bundle else True
        self.client = client or httpx.Client(timeout=180, verify=verify, follow_redirects=False)
        self.last_usage: dict[str, Any] = {}

    def propose(self, context: dict[str, Any]) -> Proposal:
        return self._request(context, repair_prompt(self.config.prompt_version), Proposal)

    def inspect(self, context: dict[str, Any]) -> Investigation:
        return self._request(context, INVESTIGATE, Investigation)

    def _request(
        self, context: dict[str, Any], system: str, response_type: type[Response]
    ) -> Response:
        cfg = self.config
        self.last_usage = {}
        body = dict(cfg.extra_body)
        # Extra vendor options cannot replace the destination, model, messages or auth.
        body.update(
            model=cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            stream=False,
        )
        try:
            response = self.client.post(
                cfg.url + "/chat/completions",
                headers={"Authorization": f"Bearer {cfg.token()}"},
                json=body,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise RuntimeError(f"Model response transport failed ({type(exc).__name__})") from exc
        if response.status_code >= 300:
            raise RuntimeError(f"Model request failed (HTTP {response.status_code})")
        data = response.json()
        usage = data.get("usage")
        self.last_usage = usage if isinstance(usage, dict) else {}
        choice = data["choices"][0]
        if choice.get("finish_reason") not in (None, "stop"):
            raise ValueError("Model output was truncated or did not complete normally")
        content = choice["message"].get("content")
        if not isinstance(content, str):
            raise ValueError("Model did not return text content")
        # Some compatible servers add a fenced JSON envelope or visible thinking prefix.
        content = re.sub(r"^\s*<think>.*?</think>\s*", "", content, flags=re.S).strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        return response_type.model_validate_json(content)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
