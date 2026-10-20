"""Temporary, file-backed fictional on-prem APIs around real C++ evaluation evidence.

No model is mocked here. All requests stay inside ``httpx.MockTransport``; no
company server can be contacted and publication records remain in memory.
"""

from __future__ import annotations

import copy
import html
import json
import re
from collections.abc import Callable
from datetime import datetime, time, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx

from auto_fix.models import Failure

TOKEN_ENV = "AUTO_FIX_EVALUATION_TOKEN"
TOKEN = "synthetic-evaluation-token"
TC_URL = "https://ci.meridian.invalid/teamcity"
BB_URL = "https://code.meridian.invalid/bitbucket"
JIRA_URL = "https://issues.meridian.invalid/jira"
PROJECT = "PLAT"
REPO = "cpp-runtime"
VCS_ROOT = "Platform_CppRuntime"
EVIDENCE_PATH = "reports/unit-test-failure.svg"


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Read the editable repository fixture, or its copy in an installed wheel."""
    if path is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        repository_path = Path(__file__).resolve().parents[2] / "evaluation/fixtures/onprem.json"
        source = (
            repository_path
            if repository_path.is_file()
            else files("auto_fix").joinpath("fixtures/onprem.json")
        )
        data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("synthetic") is not True:
        raise ValueError("Evaluation service fixtures must declare schema 1 and synthetic=true")
    return data


class ScenarioServices:
    """Serve realistic APIs for one independently reproduced failing build.

    ``failure`` supplies actual Git revisions, test names and assertion output.
    ``issue_description`` supplies requirements, never the injected defect or
    expected patch. ``latest_commit`` reads a local bare repository after the
    workflow pushes; the mock PR therefore reports the real pushed commit.
    """

    def __init__(
        self,
        failure: Failure,
        *,
        now: datetime,
        commit_messages: dict[str, str] | None = None,
        changed_files: dict[str, list[str]] | None = None,
        latest_commit: Callable[[str], str] | None = None,
        fixture_path: Path | None = None,
        include_evidence: bool = True,
        issue_key: str = "PLAT-1842",
        issue_summary: str | None = None,
        issue_description: str | None = None,
    ):
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Mock CI timestamps require a timezone-aware datetime")
        if not failure.build_id.isdecimal():
            raise ValueError("Mock build ID must be numeric")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", issue_key):
            raise ValueError("Mock issue key must be a Jira issue key")
        self.failure = failure.model_copy(deep=True)
        self.now = now
        self.fixture = load_fixture(fixture_path)
        self.company = self.fixture["company"]
        self.include_evidence = include_evidence
        self.issue_key = issue_key
        self.issue_summary = issue_summary or self.fixture["issues"]["primary"]["summary"]
        self.issue_description = issue_description
        self.latest_commit = latest_commit
        self.requests: list[dict[str, Any]] = []
        self.created_prs: list[dict[str, Any]] = []
        self.changed_files = changed_files or {}
        self.commit_messages = commit_messages or {}
        self._changes = self._make_changes()
        self._prs = self._make_pull_requests()
        text = json.dumps([self._changes, self._prs])
        self._issue_keys = set(re.findall(r"\b[A-Z][A-Z0-9_]*-\d+\b", text)) | {issue_key}
        build_id = int(failure.build_id)
        self._successful_id = str(build_id + 11)
        self._infrastructure_id = str(build_id + 12)
        self._yesterday_id = str(build_id + 13)
        self._tomorrow_id = str(build_id + 14)
        self.transport = httpx.MockTransport(self.handle)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=False)

    @property
    def evidence_url(self) -> str:
        return (
            f"{TC_URL}/app/rest/builds/id:{self.failure.build_id}/artifacts/content/{EVIDENCE_PATH}"
        )

    def _make_changes(self) -> list[dict[str, Any]]:
        source = self.failure.changes or [{"version": self.failure.revision}]
        result = []
        for index, source_change in enumerate(source):
            revision = source_change.get("version", self.failure.revision)
            result.append(
                {
                    **source_change,
                    "id": str(93517 + index),
                    "version": revision,
                    "comment": self.commit_messages.get(revision)
                    or source_change.get("comment")
                    or f"{self.issue_key} Runtime utility maintenance",
                    "username": source_change.get("username", "maya.chen"),
                    "date": (self.now - timedelta(hours=2, minutes=index * 17)).strftime(
                        "%Y%m%dT%H%M%S%z"
                    ),
                    "webUrl": f"{BB_URL}/projects/{PROJECT}/repos/{REPO}/commits/{revision}",
                    "vcsRootInstance": {"vcs-root-id": VCS_ROOT},
                }
            )
        # A checkout can include an unrelated infrastructure VCS root. The real
        # TeamCity adapter must discard it using its configured vcs_root_id.
        result.append(
            {
                "id": "93599",
                "version": "e" * 40,
                "comment": "OPS-218 Refresh agent certificate rotation runbook",
                "username": "oliver.martin",
                "vcsRootInstance": {"vcs-root-id": "Platform_BuildTools"},
            }
        )
        return result

    def _ref(self, branch: str, revision: str) -> dict[str, Any]:
        return {
            "id": "refs/heads/" + branch,
            "displayId": branch,
            "latestCommit": revision,
            "repository": {
                "slug": REPO,
                "id": 61,
                "name": "C++ Runtime",
                "project": {"key": PROJECT, "id": 8, "name": "Platform"},
            },
        }

    def _make_pull_requests(self) -> dict[int, dict[str, Any]]:
        result = {}
        for name, template in self.fixture["pull_requests"].items():
            pr = copy.deepcopy(template)
            pr_id = pr["id"]
            if name == "primary":
                pr["title"] = f"{self.issue_key} {self.issue_summary}"
                pr["description"] = f"Tracks {self.issue_key}. " + pr["description"]
                touched = sorted({path for paths in self.changed_files.values() for path in paths})
                if touched:
                    pr["description"] += "\n\nChanged paths: " + ", ".join(touched)
            pr.update(
                {
                    "createdDate": int((self.now - timedelta(days=2)).timestamp() * 1000),
                    "updatedDate": int((self.now - timedelta(hours=1)).timestamp() * 1000),
                    "fromRef": self._ref(f"feature/runtime-{pr_id}", self.failure.revision),
                    "toRef": self._ref("master", self.failure.revision),
                    "author": {"user": self.fixture["people"]["author"], "role": "AUTHOR"},
                    "reviewers": [
                        {
                            "user": self.fixture["people"]["reviewer"],
                            "role": "REVIEWER",
                            "approved": pr["state"] == "MERGED",
                            "status": "APPROVED" if pr["state"] == "MERGED" else "UNAPPROVED",
                        }
                    ],
                    "participants": [],
                    "links": {
                        "self": [
                            {
                                "href": (
                                    f"{BB_URL}/projects/{PROJECT}/repos/{REPO}"
                                    f"/pull-requests/{pr_id}"
                                )
                            }
                        ]
                    },
                }
            )
            result[pr_id] = pr
        return result

    def _test_occurrences(self) -> list[dict[str, Any]]:
        real = [
            {
                "id": f"id:{index + 7100},build:(id:{self.failure.build_id})",
                "test": {"id": test.id or str(index + 8100)},
                "name": test.name,
                "status": "FAILURE",
                "ignored": False,
                "muted": False,
                "duration": 83 + index * 11,
                "details": test.details,
                "logAnchor": f"#testNameId{index + 8100}",
            }
            for index, test in enumerate(self.failure.tests)
        ]
        return real

    def _noise_tests(self) -> list[dict[str, Any]]:
        return [
            {"id": "901", "name": "NetworkShareAvailability", "status": "FAILURE", "muted": True},
            {"id": "902", "name": "NightlyPerformanceBudget", "status": "FAILURE", "ignored": True},
            {"id": "903", "name": "CompilerSmokeTest", "status": "SUCCESS"},
        ]

    def _build_log(self) -> str:
        lines = [
            "SYNTHETIC ON-PREM CI RECORD: assertion output below comes from the actual evaluator.",
            f"Build #{self.failure.build_id} ({self.failure.build_type}); branch master",
            f"Agent: {self.company['agent']['name']} (fictional Windows CI metadata)",
            f"Checkout directory: {self.company['agent']['work_directory']}",
            f"VCS revision: {self.failure.revision}",
            "Step 1/3: Checkout completed",
            "Step 2/3: Native compile completed",
            "Step 3/3: CTest regression suite",
        ]
        for test in self.failure.tests:
            lines.extend([f"[ FAILED ] {test.name}", test.details])
        lines.extend(
            [
                f"{len(self.failure.tests)} unmuted failed test(s); "
                "see individual assertions above.",
                "Build status: FAILURE (unit-test failures)",
            ]
        )
        return "\n".join(lines)

    def _evidence(self) -> bytes:
        names = ", ".join(test.name for test in self.failure.tests)
        escaped = html.escape(names[:120])
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="210" '
            'viewBox="0 0 1000 210"><rect width="1000" height="210" fill="#182332"/>'
            '<g fill="#f4f5f7" font-family="sans-serif">'
            '<text x="24" y="38" font-size="22">SYNTHETIC TeamCity report fixture</text>'
            f'<text x="24" y="78" font-size="17">Build {self.failure.build_id} | '
            f"{html.escape(self.failure.build_type)}</text>"
            f'<text x="24" y="115" font-size="14">Failed: {escaped}</text>'
            f'<text x="24" y="149" font-size="13">Revision {self.failure.revision}</text>'
            '<text x="24" y="184" font-size="13">Illustrated report, not a captured '
            "screenshot. See real JUnit and native build logs for execution evidence.</text>"
            "</g></svg>"
        ).encode()

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Record sanitized traffic and reject unknown origins/routes explicitly."""
        record = {
            "method": request.method,
            "host": request.url.host,
            "path": request.url.path,
            "query": dict(request.url.params),
        }
        self.requests.append(record)
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            response = httpx.Response(401, json={"error": "Synthetic fixture token required"})
        elif request.url.scheme != "https":
            response = httpx.Response(400, json={"error": "Expected configured HTTPS fixture URL"})
        elif request.url.host == "ci.meridian.invalid":
            response = self._teamcity(request)
        elif request.url.host == "code.meridian.invalid":
            response = self._bitbucket(request)
        elif request.url.host == "issues.meridian.invalid":
            response = self._jira(request)
        else:
            response = httpx.Response(404, json={"error": "Unknown fictional service origin"})
        record["status"] = response.status_code
        return response

    @staticmethod
    def _unknown() -> httpx.Response:
        return httpx.Response(404, json={"error": "Unknown synthetic fixture route"})

    @staticmethod
    def _page(request: httpx.Request) -> int:
        return int(request.url.params.get("fixture_page", "1"))

    def _teamcity(self, request: httpx.Request) -> httpx.Response:
        prefix = "/teamcity"
        if request.method != "GET" or not request.url.path.startswith(prefix + "/"):
            return self._unknown()
        path = request.url.path.removeprefix(prefix)
        if path == "/app/rest/builds":
            midnight = datetime.combine(self.now.date(), time.min, self.now.tzinfo)
            if self._page(request) == 1:
                builds = [
                    (self._yesterday_id, midnight - timedelta(seconds=1)),
                    (self._successful_id, midnight + timedelta(hours=7, minutes=41)),
                    (self._infrastructure_id, midnight + timedelta(hours=8, minutes=6)),
                ]
                next_href = "/app/rest/builds?fixture_page=2"
            elif self._page(request) == 2:
                builds = [
                    (self.failure.build_id, self.now),
                    (self._successful_id, midnight + timedelta(hours=7, minutes=41)),
                    (self._tomorrow_id, midnight + timedelta(days=1)),
                ]
                next_href = None
            else:
                return self._unknown()
            data: dict[str, Any] = {
                "count": len(builds),
                "build": [
                    {"id": int(build_id), "finishDate": finished.strftime("%Y%m%dT%H%M%S%z")}
                    for build_id, finished in builds
                ],
            }
            if next_href:
                data["nextHref"] = next_href
            return httpx.Response(200, json=data)
        if path == "/app/rest/testOccurrences":
            build_id = request.url.params.get("fixture_build")
            if build_id is None:
                match = re.search(r"build:\(id:(\d+)\)", request.url.params.get("locator", ""))
                build_id = match.group(1) if match else None
            if build_id == self._successful_id:
                return httpx.Response(200, json={"count": 0, "testOccurrence": []})
            if build_id == self._infrastructure_id:
                return httpx.Response(200, json={"testOccurrence": self._noise_tests()[:2]})
            if build_id != self.failure.build_id:
                return self._unknown()
            real = self._test_occurrences()
            if self._page(request) == 1:
                return httpx.Response(
                    200,
                    json={
                        "testOccurrence": real[:1] + self._noise_tests(),
                        "nextHref": (
                            "/teamcity/app/rest/testOccurrences?fixture_page=2"
                            f"&fixture_build={build_id}"
                        ),
                    },
                )
            if self._page(request) == 2:
                return httpx.Response(200, json={"testOccurrence": real[1:]})
            return self._unknown()
        if path == f"/app/rest/builds/id:{self.failure.build_id}":
            return httpx.Response(
                200,
                json={
                    "id": int(self.failure.build_id),
                    "buildTypeId": self.failure.build_type,
                    "number": self.now.strftime("%Y.%m.%d") + ".143",
                    "status": "FAILURE",
                    "state": "finished",
                    "branchName": "master",
                    "webUrl": f"{TC_URL}/viewLog.html?buildId={self.failure.build_id}",
                    "agent": self.company["agent"],
                    "revisions": {
                        "revision": [
                            {
                                "version": self.failure.revision,
                                "vcsBranchName": self.failure.branch or "refs/heads/master",
                                "vcs-root-instance": {"vcs-root-id": VCS_ROOT},
                            },
                            {
                                "version": "e" * 40,
                                "vcsBranchName": "refs/heads/master",
                                "vcs-root-instance": {"vcs-root-id": "Platform_BuildTools"},
                            },
                        ]
                    },
                },
            )
        if path == "/app/rest/changes":
            build_id = request.url.params.get("fixture_build")
            if build_id is None:
                match = re.search(r"build:\(id:(\d+)\)", request.url.params.get("locator", ""))
                build_id = match.group(1) if match else None
            if build_id != self.failure.build_id:
                return self._unknown()
            if self._page(request) == 1:
                return httpx.Response(
                    200,
                    json={
                        "change": self._changes[:1],
                        "nextHref": (
                            f"{TC_URL}/app/rest/changes?fixture_page=2&fixture_build={build_id}"
                        ),
                    },
                )
            if self._page(request) == 2:
                return httpx.Response(200, json={"change": self._changes[1:]})
            return self._unknown()
        if path == "/downloadBuildLog.html":
            if request.url.params.get("buildId") == self.failure.build_id:
                return httpx.Response(200, text=self._build_log())
            return self._unknown()
        artifact_base = f"/app/rest/builds/id:{self.failure.build_id}/artifacts/"
        if self.include_evidence and path == artifact_base + "metadata/" + EVIDENCE_PATH:
            return httpx.Response(
                200,
                json={
                    "name": EVIDENCE_PATH.rsplit("/", 1)[1],
                    "size": len(self._evidence()),
                    "content": {"href": self.evidence_url},
                },
            )
        if self.include_evidence and path == artifact_base + "content/" + EVIDENCE_PATH:
            return httpx.Response(
                200, content=self._evidence(), headers={"Content-Type": "image/svg+xml"}
            )
        return self._unknown()

    def _bitbucket(self, request: httpx.Request) -> httpx.Response:
        base = f"/bitbucket/rest/api/latest/projects/{PROJECT}/repos/{REPO}"
        path = request.url.path
        match = re.fullmatch(re.escape(base) + r"/commits/([0-9a-fA-F]{40,64})/pull-requests", path)
        if match and request.method == "GET":
            known = {self.failure.revision} | {change["version"] for change in self._changes[:-1]}
            if match.group(1) not in known:
                return self._unknown()
            start = request.url.params.get("start", "0")
            ids = list(self._prs)
            if start == "0":
                return httpx.Response(
                    200,
                    json={
                        "size": 1,
                        "limit": 100,
                        "start": 0,
                        "isLastPage": False,
                        "nextPageStart": 37,
                        "values": [{"id": ids[0]}],
                    },
                )
            if start == "37":
                return httpx.Response(
                    200,
                    json={
                        "size": len(ids),
                        "start": 37,
                        "isLastPage": True,
                        "values": [{"id": pr_id} for pr_id in ids],
                    },
                )
            return self._unknown()
        match = re.fullmatch(re.escape(base) + r"/pull-requests/(\d+)", path)
        if match and request.method == "GET":
            pr_id = int(match.group(1))
            if pr_id in self._prs:
                return httpx.Response(200, json=self._prs[pr_id])
            for pr in self.created_prs:
                if pr["id"] == pr_id:
                    return httpx.Response(200, json=pr)
            return self._unknown()
        if path == base + "/pull-requests":
            if request.method == "GET":
                branch = request.url.params.get("at")
                values = [
                    pr for pr in self.created_prs if not branch or pr["fromRef"]["id"] == branch
                ]
                return httpx.Response(
                    200,
                    json={"size": len(values), "start": 0, "isLastPage": True, "values": values},
                )
            if request.method == "POST":
                payload = json.loads(request.content)
                branch = payload.get("fromRef", {}).get("id", "")
                base_branch = payload.get("toRef", {}).get("id", "")
                if not branch.startswith("refs/heads/") or base_branch != "refs/heads/master":
                    return httpx.Response(400, json={"error": "Expected repair branch into master"})
                record = copy.deepcopy(payload)
                pr_id = 901 + len(self.created_prs)
                if self.latest_commit:
                    record["fromRef"]["latestCommit"] = self.latest_commit(branch)
                record.update(
                    {
                        "id": pr_id,
                        "version": 0,
                        "state": "OPEN",
                        "open": True,
                        "closed": False,
                        "author": {"user": self.fixture["people"]["bot"], "role": "AUTHOR"},
                        "reviewers": [],
                        "synthetic": True,
                        "links": {
                            "self": [
                                {
                                    "href": (
                                        f"{BB_URL}/projects/{PROJECT}/repos/{REPO}"
                                        f"/pull-requests/{pr_id}"
                                    )
                                }
                            ]
                        },
                    }
                )
                self.created_prs.append(record)
                return httpx.Response(201, json=record)
        return self._unknown()

    def _jira(self, request: httpx.Request) -> httpx.Response:
        match = re.fullmatch(r"/jira/rest/api/2/issue/([A-Z][A-Z0-9_]*-\d+)", request.url.path)
        if request.method != "GET" or not match or match.group(1) not in self._issue_keys:
            return self._unknown()
        key = match.group(1)
        fields = copy.deepcopy(self.fixture["issues"].get(key, self.fixture["issues"]["primary"]))
        if key == self.issue_key:
            fields["summary"] = self.issue_summary
            if self.issue_description:
                fields["description"] = self.issue_description
        return httpx.Response(
            200,
            json={
                "id": str(10000 + sum(ord(character) for character in key)),
                "key": key,
                "self": f"{JIRA_URL}/rest/api/2/issue/{key}",
                "fields": fields,
                "synthetic": True,
            },
        )
