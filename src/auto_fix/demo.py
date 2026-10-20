"""Offline service fixtures around real Git, LangGraph, CMake and CTest execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from auto_fix.config import Settings
from auto_fix.integrations import Bitbucket, Jira, TeamCity
from auto_fix.llm import RepairModel
from auto_fix.workflow import Workflow, failure_key, write_json


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return result.stdout.strip()


def run_demo(directory: Path) -> int:
    if not shutil.which("cmake") or not shutil.which("ctest") or not shutil.which("git"):
        raise RuntimeError("Demo requires Git and CMake >=3.26 with a native C++ compiler")
    directory = directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Demo directory must be empty; choose a new --directory")
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "source"
    source.mkdir()
    _git(directory, "init", "--bare", str(directory / "remote.git"))
    _git(source, "init", "-b", "master")
    _git(source, "config", "user.name", "Auto Fix Demo")
    _git(source, "config", "user.email", "demo@example.invalid")
    (source / "src").mkdir()
    (source / "tests").mkdir()
    (source / ".gitignore").write_text(".auto-fix-build/\n", encoding="utf-8")
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.26)\nproject(AutoFixDemo LANGUAGES CXX)\n"
        "enable_testing()\nadd_executable(arithmetic_test src/add.cpp tests/add_test.cpp)\n"
        "add_test(NAME math.add COMMAND arithmetic_test)\n",
        encoding="utf-8",
    )
    (source / "src" / "add.cpp").write_text(
        "int add(int a, int b) { return a - b; }\n", encoding="utf-8"
    )
    (source / "tests" / "add_test.cpp").write_text(
        "#include <iostream>\nint add(int, int);\nint main() {\n"
        '  if (add(2, 3) != 5) { std::cerr << "Expected add(2,3) == 5\\n"; return 1; }\n'
        "  return 0;\n}\n",
        encoding="utf-8",
    )
    (source / "README.md").write_text("DEMO-7: Addition must add its operands.\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "DEMO-7 add arithmetic unit test")
    failed_sha = _git(source, "rev-parse", "HEAD")
    _git(source, "remote", "add", "origin", str(directory / "remote.git"))
    _git(source, "push", "-u", "origin", "master")

    previous_token = os.environ.get("AUTO_FIX_DEMO_TOKEN")
    os.environ["AUTO_FIX_DEMO_TOKEN"] = "local-demo-token"
    service = {"url": "http://demo.invalid", "token_env": "AUTO_FIX_DEMO_TOKEN"}
    settings = Settings.model_validate(
        {
            "state_dir": directory / "state",
            "timezone": "Europe/Paris",
            "teamcity": {**service, "build_types": ["Cpp_UnitTests"]},
            "bitbucket": {**service, "project": "DEMO", "repo": "cpp"},
            "jira": service,
            "llm": {**service, "url": "http://demo.invalid/v1", "model": "qwen-demo-fixture"},
            "repository": {"path": source, "allowed_paths": ["src/**"]},
            "build": {
                "configure": [["cmake", "-S", ".", "-B", ".auto-fix-build"]],
                "build": [
                    ["cmake", "--build", ".auto-fix-build", "--config", "Release", "--clean-first"]
                ],
                "test": [
                    "ctest",
                    "--test-dir",
                    ".auto-fix-build",
                    "-C",
                    "Release",
                    "--output-on-failure",
                    "--no-tests=error",
                    "--output-junit",
                    "{junit}",
                ],
                "timeout_seconds": 120,
            },
        }
    )
    now = datetime.now(ZoneInfo(settings.timezone))
    created_prs: list[dict] = []
    requests: list[str] = []
    advanced_master = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal advanced_master
        if request.headers.get("Authorization") != "Bearer local-demo-token":
            return httpx.Response(401)
        path = request.url.path
        requests.append(f"{request.method} {path}")
        if path == "/app/rest/builds":
            return httpx.Response(
                200, json={"build": [{"id": 101, "finishDate": now.strftime("%Y%m%dT%H%M%S%z")}]}
            )
        if path == "/app/rest/testOccurrences":
            return httpx.Response(
                200,
                json={
                    "testOccurrence": [
                        {
                            "id": "id:1,build:(id:101)",
                            "name": "math.add",
                            "status": "FAILURE",
                            "details": "Expected add(2,3) == 5",
                            "test": {"id": "1"},
                        }
                    ]
                },
            )
        if path == "/app/rest/builds/id:101":
            return httpx.Response(
                200,
                json={
                    "id": 101,
                    "buildTypeId": "Cpp_UnitTests",
                    "webUrl": "http://demo.invalid/viewLog.html?buildId=101",
                    "revisions": {
                        "revision": [{"version": failed_sha, "vcsBranchName": "refs/heads/master"}]
                    },
                },
            )
        if path == "/app/rest/changes":
            return httpx.Response(
                200,
                json={
                    "change": [
                        {"version": failed_sha, "comment": "DEMO-7 add arithmetic unit test"}
                    ]
                },
            )
        if path == "/downloadBuildLog.html":
            return httpx.Response(200, text="math.add FAILED: Expected add(2,3) == 5")
        if path.endswith("/commits/" + failed_sha + "/pull-requests"):
            return httpx.Response(200, json={"values": [{"id": 7}], "isLastPage": True})
        if path.endswith("/pull-requests/7"):
            return httpx.Response(
                200,
                json={
                    "id": 7,
                    "title": "DEMO-7 Arithmetic support",
                    "description": "Addition of two integers",
                    "links": {
                        "self": [
                            {"href": "http://demo.invalid/projects/DEMO/repos/cpp/pull-requests/7"}
                        ]
                    },
                },
            )
        if path == "/rest/api/2/issue/DEMO-7":
            return httpx.Response(
                200,
                json={
                    "key": "DEMO-7",
                    "fields": {
                        "summary": "Addition must return a + b",
                        "description": "2 plus 3 equals 5",
                        "status": {"name": "Open"},
                    },
                },
            )
        if path == "/v1/chat/completions":
            # Exercise the final fetch/rebase gate by advancing master during inference.
            if not advanced_master:
                (source / "README.md").write_text(
                    "DEMO-7: Addition must add its operands.\nMaster advanced during repair.\n",
                    encoding="utf-8",
                )
                _git(source, "add", "README.md")
                _git(source, "commit", "-m", "Document arithmetic while agent repairs")
                _git(source, "push", "origin", "master")
                advanced_master = True
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "Fix integer addition",
                                        "explanation": (
                                            "The implementation subtracted the second operand. "
                                            "Add it to satisfy DEMO-7 and math.add."
                                        ),
                                        "edits": [
                                            {
                                                "path": "src/add.cpp",
                                                "old": "return a - b;",
                                                "new": "return a + b;",
                                            }
                                        ],
                                    }
                                )
                            },
                        }
                    ]
                },
            )
        if path.endswith("/pull-requests"):
            if request.method == "GET":
                return httpx.Response(200, json={"values": created_prs, "isLastPage": True})
            payload = json.loads(request.content)
            posted_head = _git(
                directory,
                "--git-dir",
                str(directory / "remote.git"),
                "rev-parse",
                "--verify",
                payload["fromRef"]["id"],
            )
            record = {
                **payload,
                "fromRef": {**payload["fromRef"], "latestCommit": posted_head},
                "id": 42,
                "links": {"self": [{"href": "http://demo.invalid/pull-requests/42"}]},
            }
            created_prs.append(record)
            return httpx.Response(201, json=record)
        return httpx.Response(404, json={"error": "Unexpected demo route"})

    try:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            tc, bb = TeamCity(settings.teamcity, client), Bitbucket(settings.bitbucket, client)
            jira, model = Jira(settings.jira, client), RepairModel(settings.llm, client)
            failures = tc.failures(now.date(), settings.timezone)
            if len(failures) != 1:
                raise RuntimeError("Demo discovery did not find exactly one failed build")
            run_id = failure_key(failures[0])
            flow = Workflow(settings, run_id, tc, bb, jira, model, publish=True)
            result = flow.run({"run_id": run_id, "failure": failures[0].model_dump()})
            if result["status"] != "published":
                raise RuntimeError(f"Demo stopped: {result.get('reason', result['status'])}")
            if len(created_prs) != 1 or not advanced_master:
                raise RuntimeError("Demo did not create one PR after master advanced")
            if "DEMO-7" not in created_prs[0]["description"]:
                raise RuntimeError("Demo PR lacks Jira context")
            remote_sha = _git(
                directory,
                "--git-dir",
                str(directory / "remote.git"),
                "rev-parse",
                f"refs/heads/{result['branch']}",
            )
            if remote_sha != result["head"]:
                raise RuntimeError("Remote branch is not the tested commit")
            if created_prs[0]["fromRef"]["latestCommit"] != remote_sha:
                raise RuntimeError("Demo PR receipt does not identify the tested remote commit")
            if "return a - b;" not in (source / "src/add.cpp").read_text():
                raise RuntimeError("Demo modified source checkout")
            # Simulate re-entering publisher after uncertain delivery: look up the existing PR.
            recovered = flow.publish_pr(result)
            if recovered["pr"]["id"] != 42 or len(created_prs) != 1:
                raise RuntimeError("Demo PR reconciliation created a duplicate")
            summary = {
                "status": "passed",
                "mode": "offline API/model fixtures; real git + C++ build + tests",
                "baseline_failed": result["baseline"]["report"]["failed"],
                "final_passed": result["verification"]["report"]["passed"],
                "master_advanced_during_repair": advanced_master,
                "verified_pushed_sha": remote_sha,
                "verified_pull_request_sha": created_prs[0]["fromRef"]["latestCommit"],
                "pull_requests_created": len(created_prs),
                "result": str(flow.directory / "result.json"),
                "requests": requests,
            }
            write_json(directory / "summary.json", summary)
            print(json.dumps(summary, indent=2))
            return 0
    finally:
        if previous_token is None:
            os.environ.pop("AUTO_FIX_DEMO_TOKEN", None)
        else:
            os.environ["AUTO_FIX_DEMO_TOKEN"] = previous_token
