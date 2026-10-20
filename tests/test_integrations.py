from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from auto_fix.config import BitbucketConfig, ServiceConfig, TeamCityConfig
from auto_fix.integrations import Bitbucket, IntegrationError, Jira, TeamCity

SHA = "a" * 40
OTHER_SHA = "b" * 40


@pytest.fixture(autouse=True)
def service_tokens(monkeypatch):
    monkeypatch.setenv("TEST_SERVICE_TOKEN", "never-print-this-token")


def tc(client, **kwargs):
    return TeamCity(
        TeamCityConfig(
            url="https://ci.example/teamcity",
            token_env="TEST_SERVICE_TOKEN",
            build_types=["Project_Tests"],
            **kwargs,
        ),
        client,
    )


def bb(client):
    return Bitbucket(
        BitbucketConfig(
            url="https://git.example/bitbucket",
            token_env="TEST_SERVICE_TOKEN",
            project="PROJ",
            repo="app",
        ),
        client,
    )


def revision(sha=SHA, root="Root_App"):
    return {
        "version": sha,
        "vcsBranchName": "refs/heads/master",
        "vcs-root-instance": {"vcs-root-id": root},
    }


def test_teamcity_pages_dates_exact_revision_tests_changes_and_evidence():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer never-print-this-token"
        assert request.url.path.startswith("/teamcity/")
        path = request.url.path.removeprefix("/teamcity")
        if path == "/app/rest/builds":
            if "page" in request.url.params:
                return httpx.Response(
                    200,
                    json={
                        "build": [
                            {"id": 12, "finishDate": "20261026T000000+0100"},
                            {"id": 13, "finishDate": "20261025T235959+0100"},
                        ]
                    },
                )
            locator = request.url.params["locator"]
            assert "defaultFilter:false" in locator
            assert "state:finished" in locator
            assert "branch:default:any" in locator
            assert "finishDate:(date:20261024T235959+0200,condition:after)" in locator
            assert "status:FAILURE" not in locator
            return httpx.Response(
                200,
                json={
                    "nextHref": "/app/rest/builds?page=2",
                    "build": [
                        {"id": 9, "finishDate": "20261024T235959+0200"},
                        {"id": 10, "finishDate": "20261025T000000+0200"},
                    ],
                },
            )
        if path == "/app/rest/testOccurrences":
            if "id:13" in request.url.params.get("locator", ""):
                return httpx.Response(200, json={"testOccurrence": []})
            if "page" in request.url.params:
                return httpx.Response(
                    200,
                    json={
                        "testOccurrence": [
                            {
                                "id": "occurrence:2",
                                "test": {"id": "test:2"},
                                "name": "SecondFailure",
                                "status": "FAILURE",
                                "details": "expected 2 got 1",
                            }
                        ]
                    },
                )
            assert "status:FAILURE,ignored:false,muted:false" in request.url.params["locator"]
            return httpx.Response(
                200,
                json={
                    "nextHref": "/teamcity/app/rest/testOccurrences?page=2",
                    "testOccurrence": [
                        {"id": "1", "name": "Fail", "status": "FAILURE", "details": "bad"},
                        {"id": "2", "name": "Ignored", "status": "FAILURE", "ignored": True},
                        {"id": "3", "name": "Muted", "status": "FAILURE", "muted": True},
                        {"id": "4", "name": "Passed", "status": "SUCCESS"},
                    ],
                },
            )
        if path == "/app/rest/builds/id:10":
            return httpx.Response(
                200,
                json={
                    "id": 10,
                    "webUrl": "https://ci.example/teamcity/viewLog.html?buildId=10",
                    "revisions": {"revision": [revision(), revision(OTHER_SHA, "Root_Tools")]},
                },
            )
        if path == "/app/rest/changes":
            if "page" in request.url.params:
                return httpx.Response(
                    200,
                    json={
                        "change": [
                            {
                                "version": OTHER_SHA,
                                "comment": "PROJ-2 related commit",
                                "vcsRootInstance": {"vcs-root-id": "Root_App"},
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "nextHref": "https://ci.example/teamcity/app/rest/changes?page=2",
                    "change": [
                        {"version": SHA, "vcsRootInstance": {"vcs-root-id": "Root_App"}},
                        {"version": "c" * 40, "vcsRootInstance": {"vcs-root-id": "Root_Tools"}},
                    ],
                },
            )
        if path == "/app/rest/builds/id:10/artifacts/metadata/screenshots/failure image.png":
            return httpx.Response(200, json={"name": "failure image.png"})
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    failures = tc(
        client,
        vcs_root_id="Root_App",
        evidence_artifact_paths=["screenshots/failure image.png"],
    ).failures(date(2026, 10, 25), "Europe/Paris")
    assert len(failures) == 1
    failure = failures[0]
    assert failure.build_id == "10"
    assert failure.revision == SHA
    assert failure.branch == "refs/heads/master"
    assert [test.name for test in failure.tests] == ["Fail", "SecondFailure"]
    assert [change["version"] for change in failure.changes] == [SHA, OTHER_SHA]
    assert failure.evidence_urls == [
        "https://ci.example/teamcity/app/rest/builds/id:10/artifacts/content/"
        "screenshots/failure%20image.png"
    ]
    assert not any(
        "id:9" in str(request.url) or "id:12" in str(request.url) for request in requests
    )


def test_teamcity_no_builds_has_no_failures():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"build": []}))
    )
    assert tc(client).failures(date(2026, 10, 20), "Europe/Paris") == []


def test_teamcity_missing_optional_screenshot_produces_no_fabricated_link():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    assert tc(client, evidence_artifact_paths=["screenshots/missing.png"])._evidence("10") == []


def test_teamcity_screenshot_auth_failure_is_not_silently_hidden():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    with pytest.raises(IntegrationError, match="HTTP 403"):
        tc(client, evidence_artifact_paths=["screenshots/missing.png"])._evidence("10")


@pytest.mark.parametrize("next_href", ["https://evil.example/steal", "//evil.example/steal"])
def test_teamcity_rejects_cross_origin_pagination_before_sending_token(next_href):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"nextHref": next_href, "build": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(IntegrationError, match="origin"):
        tc(client).failures(date(2026, 10, 20), "UTC")
    assert len(requests) == 1


def test_teamcity_rejects_pagination_loop():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"build": [], "nextHref": "/app/rest/builds?page=2"}
            )
        )
    )
    with pytest.raises(IntegrationError, match="repeated"):
        tc(client).failures(date(2026, 10, 20), "UTC")


@pytest.mark.parametrize(
    "revisions",
    [[], [revision(), revision(OTHER_SHA, "Root_Tools")], [revision("short")]],
)
def test_teamcity_never_guesses_ambiguous_or_non_git_revision(revisions):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(IntegrationError, match="revision"):
        tc(client)._revision({"revisions": {"revision": revisions}})


def test_teamcity_requires_matching_configured_vcs_root():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(IntegrationError, match="matching VCS"):
        tc(client, vcs_root_id="Unknown")._revision({"revisions": {"revision": [revision()]}})


def test_teamcity_build_log_is_bounded_and_uses_context_path():
    def handler(request):
        assert request.url.path == "/teamcity/downloadBuildLog.html"
        assert dict(request.url.params) == {"buildId": "123", "plain": "true"}
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, content=b"x" * 300000)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert len(tc(client).build_log("123")) == 200000


def test_bitbucket_context_paginates_using_server_cursor_and_deduplicates():
    seen_starts = []

    def handler(request):
        assert request.headers["Authorization"] == "Bearer never-print-this-token"
        if request.url.path.endswith(f"/commits/{SHA}/pull-requests"):
            start = int(request.url.params["start"])
            seen_starts.append(start)
            if start == 0:
                return httpx.Response(
                    200,
                    json={
                        "values": [{"id": 1}],
                        "isLastPage": False,
                        "nextPageStart": 37,
                    },
                )
            assert start == 37
            return httpx.Response(200, json={"values": [{"id": 1}, {"id": 2}], "isLastPage": True})
        pr_id = int(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(
            200,
            json={"id": pr_id, "title": f"PROJ-{pr_id}", "description": "Fix it", "links": {}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert [pr["id"] for pr in bb(client).context([SHA, SHA])] == [1, 2]
    assert seen_starts == [0, 37]


def test_bitbucket_find_pr_matches_both_branches():
    def handler(request):
        assert request.url.params["at"] == "refs/heads/auto-fix/123"
        return httpx.Response(
            200,
            json={
                "isLastPage": True,
                "values": [
                    {
                        "id": 1,
                        "fromRef": {"id": "refs/heads/auto-fix/123"},
                        "toRef": {"id": "refs/heads/develop"},
                    },
                    {
                        "id": 2,
                        "fromRef": {"id": "refs/heads/auto-fix/123"},
                        "toRef": {"id": "refs/heads/master"},
                    },
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert bb(client).find_pr("auto-fix/123", "master")["id"] == 2


def test_bitbucket_create_pr_correct_payload_once():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert (
            request.url.path == "/bitbucket/rest/api/latest/projects/PROJ/repos/app/pull-requests"
        )
        payload = json.loads(request.content)
        assert payload["title"] == "Fix"
        assert payload["description"] == "[TeamCity](https://ci.example/10)"
        assert payload["fromRef"]["id"] == "refs/heads/auto-fix/123"
        assert payload["toRef"] == {
            "id": "refs/heads/master",
            "repository": {"slug": "app", "project": {"key": "PROJ"}},
        }
        return httpx.Response(201, json={"id": 42})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert bb(client).create_pr(
        "auto-fix/123", "master", "Fix", "[TeamCity](https://ci.example/10)"
    ) == {"id": 42}
    assert len(requests) == 1


def test_post_uncertain_outcome_never_retried_or_exposes_token():
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("sensitive message never-print-this-token", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(IntegrationError) as exc:
        bb(client).create_pr("auto-fix/123", "master", "Fix", "Evidence")
    assert "never-print-this-token" not in str(exc.value)
    assert len(requests) == 1


def test_redirect_never_forwards_auth():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"})

    # Even an injected client with redirect following enabled cannot forward auth.
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(IntegrationError, match="HTTP 302"):
        bb(client).context([SHA])
    assert len(requests) == 1


def test_bitbucket_invalid_cursor_fails_instead_of_looping():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"values": [], "isLastPage": False, "nextPageStart": 0}
            )
        )
    )
    with pytest.raises(IntegrationError, match="nextPageStart"):
        bb(client).context([SHA])


def test_jira_uses_data_center_api_pat_and_preserves_context_path():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/jira/rest/api/2/issue/PROJ-12"
        assert request.headers["Authorization"] == "Bearer never-print-this-token"
        assert "description" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={"key": "PROJ-12", "fields": {"summary": "Broken", "description": "Expected"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jira = Jira(
        ServiceConfig(url="https://jira.example/jira", token_env="TEST_SERVICE_TOKEN"), client
    )
    issues = jira.issues(["PROJ-12", "PROJ-12"])
    assert issues == [
        {
            "key": "PROJ-12",
            "fields": {"summary": "Broken", "description": "Expected"},
            "url": "https://jira.example/jira/browse/PROJ-12",
        }
    ]
    assert len(requests) == 1
    jira.close()
    assert not client.is_closed
