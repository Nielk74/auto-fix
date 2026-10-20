from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FailedTest(Model):
    id: str
    name: str
    details: str = ""
    url: str = ""


class Failure(Model):
    build_id: str
    build_type: str
    build_url: str
    revision: str
    branch: str = ""
    tests: list[FailedTest]
    changes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class CommandResult(Model):
    argv: list[str]
    returncode: int
    output: str
    log_path: str = ""


class TestReport(Model):
    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class Verification(Model):
    build_ok: bool
    test_ok: bool
    evidence_valid: bool = True
    report: TestReport = Field(default_factory=TestReport)
    output: str = ""
    logs: list[str] = Field(default_factory=list)


class Edit(Model):
    path: str
    old: str = Field(min_length=1)
    new: str


class Proposal(Model):
    summary: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=12000)
    edits: list[Edit] = Field(min_length=1, max_length=8)


class SourceRead(Model):
    path: str = Field(min_length=1, max_length=500)
    line: int = Field(ge=0, le=1000000)
    symbol: str = Field(max_length=160)


class Investigation(Model):
    summary: str = Field(min_length=1, max_length=1200)
    hypotheses: list[str] = Field(max_length=6)
    queries: list[str] = Field(max_length=4)
    reads: list[SourceRead] = Field(max_length=4)
    ready: bool
