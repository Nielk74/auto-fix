from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import Field, field_validator, model_validator

from auto_fix.models import Model


class ServiceConfig(Model):
    url: str
    token_env: str
    ca_bundle: str | None = None

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Expected an absolute HTTP(S) URL")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("URLs must not contain credentials, query strings or fragments")
        return value.rstrip("/")

    def token(self) -> str:
        value = os.environ.get(self.token_env, "")
        if not value:
            raise ValueError(f"Missing environment variable: {self.token_env}")
        return value


class TeamCityConfig(ServiceConfig):
    build_types: list[str] = Field(min_length=1)
    vcs_root_id: str | None = None
    evidence_artifact_paths: list[str] = Field(default_factory=list)


class BitbucketConfig(ServiceConfig):
    project: str
    repo: str


class LLMConfig(ServiceConfig):
    model: str
    max_tokens: int = Field(default=6000, ge=256, le=32000)
    context_chars: int = Field(default=60000, ge=4000, le=200000)
    temperature: float = Field(default=0.1, ge=0, le=2)
    extra_body: dict[str, Any] = Field(default_factory=dict)


class RepositoryConfig(Model):
    path: Path
    remote: str = "origin"
    base_branch: str = "master"
    author_name: str = "Auto Fix"
    author_email: str = "auto-fix@example.invalid"
    allowed_paths: list[str] = Field(default_factory=lambda: ["src/**", "include/**"])
    context_paths: list[str] = Field(default_factory=lambda: ["src/**", "include/**", "tests/**"])
    context_strategy: Literal["legacy", "focused"] = "focused"
    max_edit_bytes: int = Field(default=80000, ge=100, le=500000)

    @field_validator("remote", "base_branch")
    @classmethod
    def valid_ref(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", value):
            raise ValueError("Unsupported git remote or branch")
        if ".." in value or "//" in value or value.endswith(("/", ".", ".lock")):
            raise ValueError("Invalid git remote or branch")
        return value


class BuildConfig(Model):
    configure: list[list[str]] = Field(default_factory=list)
    build: list[list[str]] = Field(min_length=1)
    test: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=1800, ge=1, le=14400)
    # Exact TC name -> JUnit name. Missing entries use the TC name verbatim.
    test_name_map: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def junit_required(self) -> BuildConfig:
        if not any("{junit}" in part for part in self.test):
            raise ValueError("test command must write a fresh JUnit report using {junit}")
        for command in [*self.configure, *self.build, self.test]:
            if not command or any(not item for item in command):
                raise ValueError("Commands must be nonempty argument arrays")
        return self


class Settings(Model):
    timezone: str = "Europe/Paris"
    state_dir: Path = Path(".auto-fix")
    teamcity: TeamCityConfig
    bitbucket: BitbucketConfig
    jira: ServiceConfig | None = None
    llm: LLMConfig
    repository: RepositoryConfig
    build: BuildConfig
    max_attempts: int = Field(default=2, ge=1, le=5)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


def load_settings(path: Path) -> Settings:
    settings = Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    # Resolve paths against the config, independent of Task Scheduler's working directory.
    for owner, name in [(settings, "state_dir"), (settings.repository, "path")]:
        value = getattr(owner, name)
        setattr(owner, name, (path.resolve().parent / value).resolve())
    return settings
