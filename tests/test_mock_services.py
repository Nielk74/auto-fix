from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from defusedxml import ElementTree

from auto_fix.config import BitbucketConfig, ServiceConfig, TeamCityConfig
from auto_fix.integrations import Bitbucket, IntegrationError, Jira, TeamCity
from auto_fix.mock_services import (
    BB_URL,
    EVIDENCE_PATH,
    JIRA_URL,
    PROJECT,
    REPO,
    TC_URL,
    TOKEN,
    TOKEN_ENV,
    VCS_ROOT,
    ScenarioServices,
    load_fixture,
)
from auto_fix.models import FailedTest, Failure

SHA = "a" * 40
EARLIER_SHA = "b" * 40


@pytest.fixture(autouse=True)
def mock_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)


def make_services(day=date(2026, 10, 20), **kwargs):
    return ScenarioServices(
        Failure(
            build_id="68143",
            build_type="Platform_Strings_Windows",
            build_url=f"{TC_URL}/viewLog.html?buildId=68143",
            revision=SHA,
            branch="refs/heads/master",
            tests=[
                FailedTest(
                    id="703113",
                    name="AsciiTest.ToLower",
                    details="Expected equality of these values:\n  expected: abc\n  actual: ABC",
                ),
                FailedTest(
                    id="703114",
                    name="AsciiTest.ToUpper",
                    details="Expected equality of these values:\n  expected: ABC\n  actual: abc",
                ),
            ],
            changes=[
                {"version": SHA, "comment": "PLAT-1842 String utility maintenance"},
                {"version": EARLIER_SHA, "comment": "PLAT-1731 Stabilize diagnostic byte output"},
            ],
        ),
        now=datetime.combine(day, datetime.min.time(), ZoneInfo("Europe/Paris")).replace(
            hour=10, minute=14
        ),
        **kwargs,
    )


def teamcity(client):
    return TeamCity(
        TeamCityConfig(
            url=TC_URL,
            token_env=TOKEN_ENV,
            build_types=["Platform_Strings_Windows"],
            vcs_root_id=VCS_ROOT,
            evidence_artifact_paths=[EVIDENCE_PATH],
        ),
        client,
    )


def bitbucket(client):
    return Bitbucket(
        BitbucketConfig(url=BB_URL, token_env=TOKEN_ENV, project=PROJECT, repo=REPO), client
    )


@pytest.mark.parametrize("day", [date(2026, 10, 20), date(2026, 10, 25)])
def test_real_adapters_discover_only_current_unmuted_failures_across_pages(day):
    services = make_services(day)
    with services.client() as client:
        tc = teamcity(client)
        failures = tc.failures(day, "Europe/Paris")
        assert len(failures) == 1
        failure = failures[0]
        assert failure.revision == SHA
        assert failure.branch == "refs/heads/master"
        assert [test.name for test in failure.tests] == ["AsciiTest.ToLower", "AsciiTest.ToUpper"]
        assert [change["version"] for change in failure.changes] == [SHA, EARLIER_SHA]
        assert failure.evidence_urls == [services.evidence_url]
        log = tc.build_log(failure.build_id)
        assert "expected: abc" in log
        assert "actual: ABC" in log
        assert "SYNTHETIC ON-PREM CI RECORD" in log
    assert all(request["status"] == 200 for request in services.requests)
    assert not any(
        request["query"].get("locator", "").startswith("build:(id:68156)")
        or request["query"].get("locator", "").startswith("build:(id:68157)")
        for request in services.requests
    )
    assert any(request["query"].get("fixture_page") == "2" for request in services.requests)
    assert TOKEN not in json.dumps(services.requests)
    assert "Authorization" not in json.dumps(services.requests)


def test_bitbucket_and_jira_use_real_adapters_with_cursor_deduplication_and_noise():
    services = make_services(
        issue_summary="ASCII casing is locale-independent",
        issue_description="Preserve non-ASCII bytes; transform only the documented ASCII range.",
    )
    with services.client() as client:
        prs = bitbucket(client).context([SHA, EARLIER_SHA, SHA])
        assert [pr["id"] for pr in prs] == [418, 402, 425]
        assert [pr["state"] for pr in prs] == ["MERGED", "MERGED", "OPEN"]
        assert prs[0]["author"]["user"]["displayName"] == "Maya Chen"
        assert "PLAT-1842" in prs[0]["title"]
        jira = Jira(ServiceConfig(url=JIRA_URL, token_env=TOKEN_ENV), client)
        issues = jira.issues(["PLAT-1842", "PLAT-1731", "OPS-218"])
        assert issues[0]["fields"]["summary"] == "ASCII casing is locale-independent"
        assert issues[0]["fields"]["description"].startswith("Preserve non-ASCII bytes")
        assert issues[0]["url"] == JIRA_URL + "/browse/PLAT-1842"
        assert issues[1]["fields"]["status"]["name"] == "Done"
        assert "administration only" in issues[2]["fields"]["description"]
        with pytest.raises(IntegrationError, match="HTTP 404"):
            jira.issues(["UNKNOWN-999"])
    cursors = [
        request["query"]["start"] for request in services.requests if "/commits/" in request["path"]
    ]
    assert cursors == ["0", "37", "0", "37"]


def test_mock_pr_publication_records_real_pushed_head_and_supports_reconciliation():
    resolved_refs = []

    def latest_commit(ref):
        resolved_refs.append(ref)
        return "c" * 40

    services = make_services(latest_commit=latest_commit)
    with services.client() as client:
        bb = bitbucket(client)
        assert bb.find_pr("auto-fix/tc-68143", "master") is None
        pr = bb.create_pr(
            "auto-fix/tc-68143", "master", "[auto-fix] Restore casing", "TeamCity and Jira links"
        )
        assert pr["fromRef"]["latestCommit"] == "c" * 40
        assert pr["synthetic"] is True
        assert bb.find_pr("auto-fix/tc-68143", "master") == pr
        assert bb.find_pr("auto-fix/unrelated", "master") is None
        assert bb.find_pr("auto-fix/tc-68143", "develop") is None
    assert resolved_refs == ["refs/heads/auto-fix/tc-68143"]
    assert len(services.created_prs) == 1
    assert sum(request["method"] == "POST" for request in services.requests) == 1


def test_report_artifact_is_accessible_xml_and_explicitly_synthetic():
    services = make_services()
    services.failure.tests[0].name = "TemplateTest.<char & unsigned char>"
    with services.client() as client:
        response = client.get(services.evidence_url, headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/svg+xml"
        root = ElementTree.fromstring(response.content)
        rendered_text = " ".join(root.itertext())
        assert "SYNTHETIC" in rendered_text
        assert "not a captured screenshot" in rendered_text
        assert "TemplateTest.<char & unsigned char>" in rendered_text


def test_absent_optional_evidence_does_not_fabricate_artifact_link():
    services = make_services(include_evidence=False)
    with services.client() as client:
        failures = teamcity(client).failures(services.now.date(), "Europe/Paris")
    assert failures[0].evidence_urls == []


def test_transport_rejects_missing_auth_unknown_routes_and_wrong_context():
    services = make_services()
    with services.client() as client:
        assert client.get(TC_URL + "/app/rest/builds").status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        for url in [
            "https://ci.meridian.invalid/app/rest/builds",
            TC_URL + "/unknown",
            "https://external.example/teamcity/app/rest/builds",
            "http://ci.meridian.invalid/teamcity/app/rest/builds",
        ]:
            assert client.get(url, headers=headers).status_code in {400, 404}


def test_fixture_override_is_editable_and_must_be_explicitly_synthetic(tmp_path):
    fixture = load_fixture()
    fixture["people"]["author"]["displayName"] = "Ravi Shah"
    path = tmp_path / "onprem.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    services = make_services(fixture_path=path)
    with services.client() as client:
        assert bitbucket(client).context([SHA])[0]["author"]["user"]["displayName"] == "Ravi Shah"
    fixture["synthetic"] = False
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic=true"):
        load_fixture(path)


def test_mock_time_must_be_timezone_aware():
    service = make_services()
    with pytest.raises(ValueError, match="timezone-aware"):
        ScenarioServices(service.failure, now=datetime(2026, 10, 20, 10, 14))
