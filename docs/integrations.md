# On-premises integration notes

The adapters use service URLs from configuration, Bearer tokens from environment
variables, explicit timeouts, and normal certificate verification. An internal CA
can be supplied through each service's `ca_bundle`. Redirects are rejected, and
TeamCity pagination cannot send credentials to another origin or outside the
configured application context. No API call is automatically retried. In
particular, an uncertain pull-request creation must be reconciled by searching
for the source and target branches before submitting again.

## TeamCity

Discovery selects configured build configurations, finished nonpersonal builds,
and all branches with `defaultFilter:false`. TeamCity's ordinary build list
defaults to successful builds on the default branch, which would conceal the
failures this workflow needs. A `finishDate` lower bound narrows discovery, then
the adapter checks the exact interval from local midnight to the following local
midnight using the configured IANA timezone. This includes builds that started
yesterday and finished today, and handles 23-hour and 25-hour days.

The adapter follows `nextHref` for builds, test occurrences, and changes. It
selects actual failed, unmuted, nonignored test occurrences; a build can fail due
to compilation or infrastructure without having a unit-test failure. Explicit
fields request assertion details. Unit-test framework names may need mapping to
the local JUnit runner through `build.test_name_map`.

Build `revisions` supplies the exact checked-out Git SHA. Configure
`teamcity.vcs_root_id` when a build checks out multiple roots. The adapter fails
when it cannot select exactly one revision; the build changes list represents
commits associated with that build, usually since its predecessor, and cannot
replace the checkout revision. Associated changes are filtered to the configured
root.

Relevant endpoints:

```text
GET /app/rest/builds?locator=...
GET /app/rest/testOccurrences?locator=build:(id:ID),status:FAILURE,...
GET /app/rest/builds/id:ID?fields=...,revisions(...)
GET /app/rest/changes?locator=build:(id:ID)
GET /downloadBuildLog.html?buildId=ID&plain=true
GET /app/rest/builds/id:ID/artifacts/metadata/PATH
GET /app/rest/builds/id:ID/artifacts/content/PATH
```

Log downloads stream at most 200,000 bytes. Configured evidence artifact paths
are checked for existence before links are emitted. Missing optional screenshots
are skipped; authentication failures remain visible. Images must already have
been published by the test/build process. Reviewers need TeamCity access, and
artifact links are subject to TeamCity retention policies.

Sources: [build discovery and changes](https://www.jetbrains.com/help/teamcity/rest/get-build-details.html),
[test occurrence filters](https://www.jetbrains.com/help/teamcity/rest/testoccurrencelocator.html),
[test occurrence details](https://www.jetbrains.com/help/teamcity/rest/testoccurrence.html),
[exact revisions](https://www.jetbrains.com/help/teamcity/rest/revision.html),
[build logs](https://www.jetbrains.com/help/teamcity/build-log.html),
[artifacts](https://www.jetbrains.com/help/teamcity/rest/manage-finished-builds.html),
[authentication](https://www.jetbrains.com/help/teamcity/rest/teamcity-rest-api-documentation.html).

## Bitbucket Data Center

Commit context is retrieved from the repository PRs containing each exact SHA.
Each associated PR is fetched in full to retain its title, description, and
links. Paged responses use the server's `nextPageStart`, which is not assumed to
equal `start + limit`.

```text
GET /rest/api/latest/projects/PROJECT/repos/REPO/commits/SHA/pull-requests
GET /rest/api/latest/projects/PROJECT/repos/REPO/pull-requests/ID
GET /rest/api/latest/projects/PROJECT/repos/REPO/pull-requests?state=OPEN&...
POST /rest/api/latest/projects/PROJECT/repos/REPO/pull-requests
```

Creation specifies source and target `refs/heads/...` and the same repository.
The Git credential used to push the branch is separate from the REST token;
configure Git Credential Manager or SSH on the Windows worker. Tokens are never
embedded in clone URLs. The PR body includes source build links, issue links,
validation evidence, and any existing screenshot links. Bitbucket Markdown can
embed images using `![description](URL)`. There is no assumed undocumented
attachment-upload endpoint. Draft support varies across installed Bitbucket
versions, so this starter creates an ordinary open PR for review and never
merges it.

Sources: [PR endpoints](https://developer.atlassian.com/server/bitbucket/rest/v1005/api-group-pull-requests/),
[paging](https://docs.atlassian.com/bitbucket-server/rest/7.0.5/bitbucket-rest.html),
[HTTP access tokens](https://confluence.atlassian.com/bitbucketserver101/http-access-tokens-1721010667.html),
[Markdown syntax](https://confluence.atlassian.com/bitbucketserver0718/markdown-syntax-guide-1097182852.html).

## Jira Data Center

```text
GET /rest/api/2/issue/KEY?fields=summary,description,status,issuetype,labels,comment,issuelinks
Authorization: Bearer PERSONAL_ACCESS_TOKEN
```

Issue keys come from commit and PR context. The adapter preserves retrieved issue
fields and adds the browser URL under the configured application context path.
It performs read operations only. Jira Data Center PAT authentication differs
from Jira Cloud's email and API-token mechanism.

Sources: [Jira Server/Data Center REST reference](https://docs.atlassian.com/software/jira/docs/api/REST/9.7.2/),
[personal access tokens](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html).

## Windows C++ builds

Use a Visual Studio Developer PowerShell or a scheduled worker with the Visual
Studio build environment initialized. Both a solution command such as
`msbuild Solution.sln /m /p:Configuration=Release /p:Platform=x64` and a CMake
build can be configured as explicit argument arrays. The test command must write
a fresh JUnit report; an exit code alone cannot prove the originally failing
test ran and passed. Choose the actual solution configuration and test runner
used by the project.

Sources: [MSBuild of solution targets](https://learn.microsoft.com/en-us/visualstudio/msbuild/how-to-build-specific-targets-in-solutions-by-using-msbuild-exe?view=visualstudio),
[MSBuild for C++](https://learn.microsoft.com/en-us/cpp/build/msbuild-visual-cpp?view=msvc-170),
[CTest options](https://cmake.org/cmake/help/latest/manual/ctest.1.html).

These adapters and mock responses do not establish compatibility with a specific
private server installation. Validate configured endpoints, permissions, VCS
roots, build commands, and test-name mappings against that installation.
