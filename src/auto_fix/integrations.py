"""Small REST adapters for the on-premises services; no cloud SDK assumptions."""

from __future__ import annotations

import re
import ssl
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx

from auto_fix.config import BitbucketConfig, ServiceConfig, TeamCityConfig
from auto_fix.models import FailedTest, Failure


class IntegrationError(RuntimeError):
    """Service request or response was unsuitable for a reliable fix workflow."""


def _segment(value: str) -> str:
    return quote(str(value), safe="")


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise IntegrationError(f"Invalid service collection: {key}")
    return value


class _Service:
    def __init__(self, config: ServiceConfig, client: httpx.Client | None = None):
        self.config = config
        self.base_url = config.url.rstrip("/")
        self._origin = self._origin_of(self.base_url)
        self._context = urlsplit(self.base_url).path.rstrip("/")
        self._token = config.token()
        self._owns_client = client is None
        verify = ssl.create_default_context(cafile=config.ca_bundle) if config.ca_bundle else True
        self.client = client or httpx.Client(timeout=60, verify=verify, follow_redirects=False)

    @staticmethod
    def _origin_of(url: str) -> tuple[str, str | None, int]:
        parts = urlsplit(url)
        return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)

    def _url(self, path: str, previous: str | None = None) -> str:
        parts = urlsplit(path)
        if parts.scheme or parts.netloc:
            url = urljoin(self.base_url + "/", path)
        elif previous and not path.startswith("/"):
            url = urljoin(previous, path)
        elif self._context and path.startswith(self._context + "/"):
            base_parts = urlsplit(self.base_url)
            url = f"{base_parts.scheme}://{base_parts.netloc}{path}"
        else:
            # TeamCity may return /app/rest/... even when hosted under /teamcity.
            url = self.base_url + "/" + path.lstrip("/")
        parsed = urlsplit(url)
        if (
            self._origin_of(url) != self._origin
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise IntegrationError("Refusing a service link outside the configured origin")
        if self._context and not parsed.path.startswith(self._context + "/"):
            raise IntegrationError("Refusing a service link outside the configured context path")
        return url

    def _request(
        self,
        method: str,
        path: str,
        *,
        allowed_statuses: tuple[int, ...] = (),
        **kwargs: Any,
    ) -> httpx.Response:
        url = self._url(path)
        try:
            response = self.client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                follow_redirects=False,
                **kwargs,
            )
        except httpx.HTTPError:
            # Exception request URLs can contain query data; never expose them or auth headers.
            raise IntegrationError(f"{type(self).__name__} request failed") from None
        if not 200 <= response.status_code < 300 and response.status_code not in allowed_statuses:
            raise IntegrationError(f"{type(self).__name__} returned HTTP {response.status_code}")
        return response

    def _json(
        self, method: str, path: str, *, missing_ok: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        response = self._request(
            method, path, allowed_statuses=(404,) if missing_ok else (), **kwargs
        )
        if missing_ok and response.status_code == 404:
            return {}
        try:
            data = response.json()
        except ValueError:
            raise IntegrationError(f"{type(self).__name__} returned invalid JSON") from None
        if not isinstance(data, dict):
            raise IntegrationError(f"{type(self).__name__} returned a non-object response")
        return data

    def close(self) -> None:
        if self._owns_client:
            self.client.close()


class TeamCity(_Service):
    config: TeamCityConfig

    def __init__(self, config: TeamCityConfig, client: httpx.Client | None = None):
        super().__init__(config, client)

    def _pages(self, path: str, params: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
        url = self._url(path)
        seen: set[str] = set()
        for _ in range(1000):
            page_key = str(httpx.URL(url, params=params)) if params else url
            if page_key in seen:
                raise IntegrationError("TeamCity pagination repeated a page")
            seen.add(page_key)
            data = self._json("GET", url, params=params)
            yield data
            next_href = data.get("nextHref")
            if not next_href:
                return
            if not isinstance(next_href, str):
                raise IntegrationError("Invalid TeamCity nextHref")
            url = self._url(next_href, previous=url)
            params = None
        raise IntegrationError("TeamCity pagination exceeded 1000 pages")

    def _revision(self, build: dict[str, Any]) -> tuple[str, str]:
        revisions = _items(build.get("revisions", {}), "revision")
        if self.config.vcs_root_id:
            revisions = [
                revision
                for revision in revisions
                if revision.get("vcs-root-instance", {}).get("vcs-root-id")
                == self.config.vcs_root_id
                or revision.get("vcs-root-instance", {}).get("vcs-root", {}).get("id")
                == self.config.vcs_root_id
            ]
        if len(revisions) != 1:
            raise IntegrationError(
                "TeamCity build must have exactly one matching VCS revision; configure vcs_root_id"
            )
        revision = str(revisions[0].get("version", ""))
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
            raise IntegrationError("TeamCity build has no exact Git SHA revision")
        return revision, str(revisions[0].get("vcsBranchName", build.get("branchName", "")))

    def failures(self, day: date, timezone: str) -> list[Failure]:
        zone = ZoneInfo(timezone)
        start = datetime.combine(day, time.min, zone)
        end = datetime.combine(day + timedelta(days=1), time.min, zone)
        # Expand by one second so TeamCity's strict 'after' includes midnight exactly.
        lower_bound = (start - timedelta(seconds=1)).strftime("%Y%m%dT%H%M%S%z")
        result: list[Failure] = []
        seen_builds: set[str] = set()
        for build_type in self.config.build_types:
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", build_type):
                raise IntegrationError("Unsupported TeamCity build configuration ID")
            locator = (
                f"buildType:(id:{build_type}),defaultFilter:false,state:finished,"
                f"branch:default:any,personal:false,canceled:false,failedToStart:false,"
                f"finishDate:(date:{lower_bound},condition:after),count:100"
            )
            for page in self._pages(
                "/app/rest/builds",
                {"locator": locator, "fields": "nextHref,build(id,finishDate)"},
            ):
                for summary in _items(page, "build"):
                    build_id = str(summary.get("id", ""))
                    if not re.fullmatch(r"\d+", build_id):
                        raise IntegrationError("Invalid TeamCity build ID")
                    try:
                        finished = datetime.strptime(summary["finishDate"], "%Y%m%dT%H%M%S%z")
                    except (KeyError, TypeError, ValueError):
                        raise IntegrationError(
                            "TeamCity build has no valid finish timestamp"
                        ) from None
                    if not start <= finished < end or build_id in seen_builds:
                        continue
                    seen_builds.add(build_id)
                    tests: list[FailedTest] = []
                    for test_page in self._pages(
                        "/app/rest/testOccurrences",
                        {
                            "locator": (
                                f"build:(id:{build_id}),status:FAILURE,"
                                "ignored:false,muted:false,count:100"
                            ),
                            "fields": (
                                "nextHref,testOccurrence(id,name,status,details,ignored,muted,"
                                "test(id),logAnchor)"
                            ),
                        },
                    ):
                        for test in _items(test_page, "testOccurrence"):
                            if (
                                test.get("status") != "FAILURE"
                                or test.get("ignored") in (True, "true")
                                or test.get("muted") in (True, "true")
                            ):
                                continue
                            tests.append(
                                FailedTest(
                                    id=str(test.get("test", {}).get("id", test.get("id", ""))),
                                    name=str(test.get("name", "")),
                                    details=str(test.get("details", ""))[:50000],
                                    url=self._url("/viewLog.html")
                                    + "?"
                                    + urlencode({"buildId": build_id, "buildTab": "testsInfo"}),
                                )
                            )
                    if not tests:
                        continue
                    build = self._json(
                        "GET",
                        f"/app/rest/builds/id:{build_id}",
                        params={
                            "fields": (
                                "id,buildTypeId,webUrl,branchName,revisions(revision(version,"
                                "vcsBranchName,vcs-root-instance(vcs-root-id,vcs-root(id))))"
                            )
                        },
                    )
                    revision, branch = self._revision(build)
                    changes: list[dict[str, Any]] = []
                    for change_page in self._pages(
                        "/app/rest/changes",
                        {
                            "locator": f"build:(id:{build_id}),count:100",
                            "fields": (
                                "nextHref,change(id,version,comment,username,date,webUrl,"
                                "vcsRootInstance(vcs-root-id))"
                            ),
                        },
                    ):
                        for change in _items(change_page, "change"):
                            root = change.get("vcsRootInstance", {}).get("vcs-root-id")
                            if self.config.vcs_root_id and root != self.config.vcs_root_id:
                                continue
                            changes.append(change)
                    evidence = self._evidence(build_id)
                    result.append(
                        Failure(
                            build_id=build_id,
                            build_type=str(build.get("buildTypeId", build_type)),
                            build_url=str(build.get("webUrl") or tests[0].url),
                            revision=revision,
                            branch=branch,
                            tests=tests,
                            changes=changes,
                            evidence_urls=evidence,
                        )
                    )
        return result

    def _evidence(self, build_id: str) -> list[str]:
        urls = []
        for path in self.config.evidence_artifact_paths:
            if (
                not path
                or path.startswith(("/", "\\"))
                or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise IntegrationError(
                    "Evidence artifact paths must be relative and traversal-free"
                )
            encoded = quote(path, safe="/")
            metadata = self._json(
                "GET",
                f"/app/rest/builds/id:{build_id}/artifacts/metadata/{encoded}",
                missing_ok=True,
            )
            if metadata.get("name"):
                urls.append(
                    self._url(f"/app/rest/builds/id:{build_id}/artifacts/content/{encoded}")
                )
        return urls

    def build_log(self, build_id: str) -> str:
        if not re.fullmatch(r"\d+", str(build_id)):
            raise IntegrationError("Invalid TeamCity build ID")
        # Stream to avoid loading a multi-gigabyte build log into memory.
        try:
            with self.client.stream(
                "GET",
                self._url("/downloadBuildLog.html"),
                params={"buildId": build_id, "plain": "true"},
                headers={"Authorization": f"Bearer {self._token}"},
                follow_redirects=False,
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise IntegrationError(f"TeamCity returned HTTP {response.status_code}")
                output = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    output.extend(chunk[: max(0, 200000 - len(output))])
                    if len(output) >= 200000:
                        break
        except httpx.HTTPError:
            raise IntegrationError("TeamCity build log request failed") from None
        return output.decode("utf-8", errors="replace")


class Bitbucket(_Service):
    config: BitbucketConfig

    def __init__(self, config: BitbucketConfig, client: httpx.Client | None = None):
        super().__init__(config, client)
        self.repo_path = (
            f"/rest/api/latest/projects/{_segment(config.project)}/repos/{_segment(config.repo)}"
        )

    def _pages(self, path: str, **params: str) -> Iterator[dict[str, Any]]:
        start = 0
        seen: set[int] = set()
        for _ in range(1000):
            if start in seen:
                raise IntegrationError("Bitbucket pagination repeated a page")
            seen.add(start)
            data = self._json("GET", path, params={**params, "start": start, "limit": 100})
            yield data
            if data.get("isLastPage") is True:
                return
            next_start = data.get("nextPageStart")
            if (
                isinstance(next_start, bool)
                or not isinstance(next_start, int)
                or next_start <= start
            ):
                raise IntegrationError("Bitbucket returned invalid nextPageStart")
            start = next_start
        raise IntegrationError("Bitbucket pagination exceeded 1000 pages")

    def context(self, commits: list[str]) -> list[dict[str, Any]]:
        result = []
        seen: set[int] = set()
        for commit in dict.fromkeys(commits):
            if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit):
                raise IntegrationError("Bitbucket commit lookup requires an exact Git SHA")
            for page in self._pages(self.repo_path + f"/commits/{commit}/pull-requests"):
                for summary in _items(page, "values"):
                    pr_id = summary.get("id")
                    if not isinstance(pr_id, int) or isinstance(pr_id, bool):
                        raise IntegrationError("Bitbucket returned invalid pull request ID")
                    if pr_id in seen:
                        continue
                    seen.add(pr_id)
                    result.append(self._json("GET", self.repo_path + f"/pull-requests/{pr_id}"))
        return result

    def find_pr(self, branch: str, base: str) -> dict[str, Any] | None:
        for page in self._pages(
            self.repo_path + "/pull-requests",
            state="OPEN",
            direction="OUTGOING",
            at="refs/heads/" + branch,
        ):
            for pr in _items(page, "values"):
                if (
                    pr.get("fromRef", {}).get("id") == "refs/heads/" + branch
                    and pr.get("toRef", {}).get("id") == "refs/heads/" + base
                ):
                    return pr
        return None

    def create_pr(self, branch: str, base: str, title: str, description: str) -> dict[str, Any]:
        repository = {"slug": self.config.repo, "project": {"key": self.config.project}}
        # One submission only: callers reconcile via find_pr after any uncertain HTTP outcome.
        return self._json(
            "POST",
            self.repo_path + "/pull-requests",
            json={
                "title": title,
                "description": description,
                "fromRef": {"id": "refs/heads/" + branch, "repository": repository},
                "toRef": {"id": "refs/heads/" + base, "repository": repository},
            },
        )


class Jira(_Service):
    def issues(self, keys: list[str]) -> list[dict[str, Any]]:
        result = []
        for key in dict.fromkeys(keys):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", key):
                raise IntegrationError("Invalid Jira issue key")
            issue = self._json(
                "GET",
                "/rest/api/2/issue/" + _segment(key),
                params={"fields": "summary,description,status,issuetype,labels,comment,issuelinks"},
            )
            result.append(
                {
                    "key": str(issue.get("key", key)),
                    "fields": issue.get("fields", {}),
                    "url": self._url("/browse/" + _segment(key)),
                }
            )
        return result
