"""The effective configuration, without secrets, and live checks of every service it names."""

from __future__ import annotations

import os
import ssl
import subprocess
import time
from typing import Any

import httpx

from auto_fix.config import ServiceConfig, Settings


def describe(settings: Settings) -> dict[str, Any]:
    """The configuration as the dashboard shows it: token variables by name and whether set."""

    def service(config: ServiceConfig | None, **extra: Any) -> dict[str, Any] | None:
        if config is None:
            return None
        return {
            "url": config.url,
            "token_env": config.token_env,
            "token_set": bool(os.environ.get(config.token_env)),
            "ca_bundle": config.ca_bundle,
            **extra,
        }

    return {
        "timezone": settings.timezone,
        "state_dir": str(settings.state_dir),
        "teamcity": service(settings.teamcity, build_types=settings.teamcity.build_types),
        "bitbucket": service(
            settings.bitbucket, project=settings.bitbucket.project, repo=settings.bitbucket.repo
        ),
        "jira": service(settings.jira),
        "llm": service(
            settings.llm,
            model=settings.llm.model,
            prompt_version=settings.llm.prompt_version,
            max_tokens=settings.llm.max_tokens,
            context_chars=settings.llm.context_chars,
            temperature=settings.llm.temperature,
        ),
        "repository": {
            "path": str(settings.repository.path),
            "remote": settings.repository.remote,
            "base_branch": settings.repository.base_branch,
            "allowed_paths": settings.repository.allowed_paths,
        },
        "build": {
            "configure": settings.build.configure,
            "build": settings.build.build,
            "test": settings.build.test,
            "additional_tests": settings.build.additional_tests,
            "timeout_seconds": settings.build.timeout_seconds,
        },
        "limits": {
            "max_attempts": settings.max_attempts,
            "max_inspections": settings.max_inspections,
            "baseline_repetitions": settings.baseline_repetitions,
        },
    }


def _probe(
    name: str, config: ServiceConfig, path: str, client: httpx.Client | None = None
) -> dict[str, Any]:
    """One authenticated GET; only the status code is reported, never the response body."""
    token = os.environ.get(config.token_env, "")
    if not token:
        return {
            "name": name,
            "ok": False,
            "detail": f"Missing environment variable {config.token_env}",
        }
    verify: Any = ssl.create_default_context(cafile=config.ca_bundle) if config.ca_bundle else True
    own = client is None
    client = client or httpx.Client(timeout=15, verify=verify, follow_redirects=False)
    started = time.monotonic()
    try:
        response = client.get(
            config.url + path,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        # Exception text can hold request URLs with query data; report only the kind.
        return {"name": name, "ok": False, "detail": f"Unreachable ({type(exc).__name__})"}
    finally:
        if own:
            client.close()
    elapsed = round((time.monotonic() - started) * 1000)
    code = response.status_code
    if code < 300:
        return {"name": name, "ok": True, "detail": f"HTTP {code}", "ms": elapsed}
    hint = {401: "token rejected", 403: "token lacks permission", 404: "path not found"}
    return {
        "name": name,
        "ok": False,
        "detail": f"HTTP {code}" + (f" ({hint[code]})" if code in hint else ""),
        "ms": elapsed,
    }


def _repository(settings: Settings) -> dict[str, Any]:
    path = settings.repository.path
    if not path.is_dir():
        return {"name": "Git repository", "ok": False, "detail": f"{path} does not exist"}
    try:
        done = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", settings.repository.base_branch],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": "Git repository", "ok": False, "detail": type(exc).__name__}
    if done.returncode:
        return {
            "name": "Git repository",
            "ok": False,
            "detail": f"Branch {settings.repository.base_branch} not found in {path}",
        }
    return {"name": "Git repository", "ok": True, "detail": f"{path} @ {done.stdout.strip()[:12]}"}


def check(settings: Settings, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Reach TeamCity, Bitbucket, Jira and the model with the configured tokens."""
    bitbucket = settings.bitbucket
    results = [
        _probe("TeamCity", settings.teamcity, "/app/rest/server", client),
        _probe(
            "Bitbucket",
            bitbucket,
            f"/rest/api/1.0/projects/{bitbucket.project}/repos/{bitbucket.repo}",
            client,
        ),
    ]
    if settings.jira:
        results.append(_probe("Jira", settings.jira, "/rest/api/2/myself", client))
    results.append(_probe("Model endpoint", settings.llm, "/models", client))
    results.append(_repository(settings))
    return results
