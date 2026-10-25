# Auto Fix

A small Windows-first workflow that investigates today's failing TeamCity C++ tests, gathers Git, Bitbucket Data Center and Jira context, asks your own Qwen endpoint for a focused fix, and opens a Bitbucket pull request after local verification.

The framework is **LangGraph**. The research compared it with CrewAI, Microsoft Agent Framework and PydanticAI before implementation. LangGraph fits the explicit collect → repair → build → test loop, has a substantial open-source community, and runs without a hosted agent service. Read the dated comparison and primary sources in [docs/research.md](docs/research.md).

GitHub hosts this tool. Your C++ source, generated branches and fix PRs stay in your existing on-premises Bitbucket repository. The model requests go to the configured OpenAI-compatible endpoint.

```mermaid
flowchart TD
    A[Today's failed TeamCity tests] --> B[Git commits and Bitbucket PRs]
    B --> C[Jira issues and TeamCity evidence links]
    C --> D[Isolated worktree at failing revision]
    D --> E[Rebase onto master]
    E --> F[Build and reproduce matching failures]
    F --> Q[Repeat unchanged baseline and check complete stable evidence]
    Q -->|Stable| R[Model-directed source searches and reads]
    Q -->|Invalid or varying outcomes| Z[Save blocked result and evidence]
    R --> G[Model proposes bounded source edits]
    G --> H[Build, full configured suites and additional validation]
    H -->|Failure, within attempt limit| R
    H -->|Pass| I[Commit, fetch and rebase master again]
    I --> J[Rebuild and verify all original test identities again]
    J --> K[Local verified fix and evidence]
    K -->|Explicit --publish| L[Push tested commit and verify Bitbucket PR receipt]
```

The API, Git and compiler nodes are ordinary Python functions; the model performs diagnosis, requests bounded source evidence, and proposes exact text edits. You can extend the workflow by adding a named node and an edge in the graph. Read [the complete workflow and extension guide](docs/workflow.md) for each gate and its evidence. There is one worker and one model endpoint, keeping resource use and execution order easy to follow.

## Try the complete local demo

Prerequisites: Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/), Git, CMake 3.26+, and a C++ compiler. On Windows, install Visual Studio 2022 Build Tools with **Desktop development with C++**, then use a Developer PowerShell terminal. Existing CMake installations must support CTest's `--output-junit` option.

```powershell
git clone https://github.com/Nielk74/auto-fix.git
Set-Location auto-fix
uv sync --locked --extra dev --python 3.12
uv run --no-sync auto-fix demo --directory .auto-fix/demo
```

The demo uses in-process fake HTTP responses and a deterministic fake model, creates a real disposable Git repository, compiles a small broken C++ program, reproduces its test failure, applies a fix, rebases and retests. It exercises the publication path against the fake Bitbucket adapter. It needs no enterprise credentials. The JSON result identifies the local evidence directory.

```powershell
uv run --no-sync auto-fix graph
uv run --no-sync pytest
```

CI runs the checks and native C++ demo on both Windows and Linux with Python 3.11 and 3.12. The small demo uses synthetic services and source code; the larger evaluation uses synthetic services with real public Abseil source. A passing demo establishes the sample workflow; your real server versions, model and C++ solution still need configuration and a local trial.

## Evaluate against a substantial C++ repository

The expanded evaluation covers **45 distinct synthetic regressions in Abseil and fmt**, split by behavior family into 24 development cases and 21 held-out cases. It completed **468 C++ workflow trials with 1,401 actual Luna calls**, plus 41 operational fault trials with 73 calls. Cases include multi-location and multi-file changes, indirect Git context, and faults across Git, model delivery and PR recovery.

The frozen selected workflow passed its configured native suites in **63/63 holdout runs**. Independent review found no confirmed functional defect in **54/63**: the first selected round scored **19/21 distinct cases**, versus **3/21** for the baseline. Two further rounds repeat those same 21 cases. Nine published patches retained contract defects despite green tests: six public output failures and three internal helper failures. The fresh operational run produced all 13 expected behaviors, including correct blocks and publication reconciliation. See the [concise results](docs/results.md), [complete method](docs/expanded-evaluation.md), [frozen dataset](evaluation/expanded/dataset-index.json), and [raw evidence](docs/evidence-artifacts.md). These synthetic public-project results do not estimate production accuracy or Qwen quality. The original four cases below remain a smoke benchmark.

The evaluation uses pinned **Abseil C++**, with 840 source/header files and 265,865 lines, and realistic synthetic TeamCity, Bitbucket and Jira data. Four independently injected source defects are checked by unchanged upstream tests. Git, native builds, rebases, and local branch publication run for real; enterprise services are mocked.

Live GPT-6 Luna evaluation on macOS improved from **2 of 4 cases repaired to 4 of 4** after source-context changes. The final round and a fresh confirmation each repaired all four cases with one model call per case and passed 188 unchanged upstream tests per round. The initial unsuccessful retrieval revision is retained in the [results and evidence](docs/evaluation.md#verified-live-results). These four synthetic regressions are a smoke benchmark, not a general repair-rate estimate.

Run an actual GPT-6 Luna evaluation through an authenticated Codex CLI:

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/luna --profile focused --backend codex --model gpt-6-luna
```

Or rerun saved Luna responses with fresh native builds and no live inference:

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/replay --backend replay --recordings evaluation/recordings/accepted
```

Use a new output directory for each run. Windows uses Visual Studio C++ build tools; Linux/macOS also require Ninja. To evaluate your Qwen server while keeping enterprise systems mocked, use `--backend endpoint --config config.local.yaml`.

[The evaluation guide](docs/evaluation.md) covers case selection, comparing workflow changes, model recordings, evidence, and limitations. [Fixture provenance](evaluation/README.md) records exact upstream revisions and the four scenarios.

## Connect your systems

Start from [examples/config.windows.yaml](examples/config.windows.yaml) for CMake/CTest or [examples/config.msbuild.yaml](examples/config.msbuild.yaml) for a Visual Studio solution and GoogleTest executable.

```powershell
Copy-Item examples/config.windows.yaml config.local.yaml
Copy-Item .env.example .env
# Edit config.local.yaml and .env with your local values.
uv run --no-sync auto-fix scan --config config.local.yaml
uv run --no-sync auto-fix run --config config.local.yaml
```

Set the actual TeamCity build configuration IDs, Bitbucket project/repository, C++ clone path, model URL and served model ID. `llm.url` is the API base, normally ending in `/v1`; the client calls Chat Completions. All service tokens come from the environment variable names in the YAML. The CLI loads a local `.env`; shell environment values take precedence. `.env`, `config.local.yaml`, local state and worktrees are ignored by Git.

Use the server root URL for TeamCity, Bitbucket and Jira, including any deployment context such as `/bitbucket` or `/jira`. Set `ca_bundle` to an absolute PEM path when your on-premises services use an internal CA. Git uses its own trust and authentication settings: configure Git Credential Manager or SSH for the worker account.

The workflow needs TeamCity read access, Bitbucket repository/PR read access, Jira issue read access when Jira is enabled, and access to your custom model. Publishing additionally needs Git push access and Bitbucket PR creation access. No credentials belong in repository URLs or committed YAML.

Build commands are argument arrays executed in the isolated worktree. The CMake example uses `--clean-first` and the MSBuild example uses `/t:Rebuild /nr:false` so verification rebuilds the edited sources instead of accepting stale incremental binaries. Configure the complete suite you want verified, not only the previously failing test. The test command must write a fresh XML report at `{junit}`. The Windows examples set `baseline_repetitions: 2`: two unchanged-source native runs must reproduce the failures with identical passed, failed and skipped test identities before inference. Invalid, incomplete or varying baseline evidence stops the run. The compatibility default is one repetition.

The validator requires the original failing test identities to appear as passing after repair. XML identity is `classname.name` when `classname` is nonempty and differs from `name`; otherwise it is `name`. This keeps GoogleTest fixtures distinct, such as `Arithmetic.AddsIntegers`, while CTest's identical class/name fields remain a single name. Duplicate identities are rejected. Use `build.test_name_map` when TeamCity uses a different label; confirm both sides against your runner's XML. An empty, missing or unrelated report cannot authorize publication.

`repository.allowed_paths` controls which source files the model can edit; keep test, build and workflow files outside that list. `context_paths` controls the source files available for diagnosis. The default `context_strategy: focused` retrieves bounded excerpts around failure locations, symbols, and local includes, including relevant code deep inside large files. `legacy` retains the original file-prefix strategy for comparison. Context, model output, edit size, retries and command duration are bounded. Change `max_attempts` to adjust the default two repair attempts.

The example configurations enable the policy selected on Luna development cases: `assertion-v4`, complete bounded C++ definition reads, six inspections shared across up to four repairs, at most two inspections per attempt, and a 160,000-character input budget. They also require two unchanged baselines. Qwen quality and your endpoint's context capacity are unmeasured; adjust `llm.context_chars` to the deployed capacity and evaluate that configuration. Provider-specific reasoning fields remain in `llm.extra_body` for your server's supported options.

“Today” uses the configured IANA timezone, defaulting to `Europe/Paris`. To investigate a specific date:

```powershell
uv run --no-sync auto-fix scan --config config.local.yaml --date 2026-10-20
uv run --no-sync auto-fix run --config config.local.yaml --date 2026-10-20
```

## Publish a verified fix

The default run keeps the result local. Add `--publish` to enable automatic Git push and Bitbucket PR creation for fixes that pass the verification gates:

```powershell
uv run --no-sync auto-fix run --config config.local.yaml --publish
```

PRs include the diagnosis, source revision and commit context, TeamCity and Jira links, and validation results. Existing screenshot/artifact URLs can be listed under `teamcity.evidence_artifact_paths`; these are linked as evidence in the PR. The MVP does not capture new application screenshots or upload images to Bitbucket. Viewers need access to the linked TeamCity artifacts.

Each failure uses an isolated branch/worktree. Your main checkout is not used for edits or builds. Rebase conflicts, absent source revisions, failures that no longer reproduce, failed builds, unmatched test names and exhausted attempts stop that fix. The workflow never merges a PR.

Local state under `state_dir` records workflow checkpoints, evidence and publication receipts. Repeated discovery is deduplicated. SQLite checkpoints provide an audit trail; this version does not promise transparent recovery of arbitrary in-flight native builds. After inspecting a blocked result, explicitly opt into another attempt:

```powershell
uv run --no-sync auto-fix run --config config.local.yaml --retry-blocked
```

Publication records help avoid blindly repeating an external write after a network error. If publication is uncertain, inspect the recorded state, remote branch and Bitbucket PR before rerunning. Retain the state directory between scheduled invocations. A process lock prevents overlapping workers using that directory.

## Run daily on Windows

The wrapper uses this checkout's `.venv\Scripts\auto-fix.exe` and propagates its exit code. First run it manually:

```powershell
.\scripts\run-today.ps1 -Config .\config.local.yaml
# Include -Publish once your configured integration is ready.
.\scripts\register-task.ps1 -Config .\config.local.yaml -Time '17:30' -Publish
```

The registration script creates a daily Task Scheduler entry for the current logged-in account, with overlapping launches ignored. It stores no password or tokens and needs no elevated task principal. The task runs while that account is logged in; the `.env` remains local to the checkout. Configure a dedicated worker account separately if the machine must run unattended after reboot. Registration only occurs when you execute the script.

For the MSBuild example, a scheduled task starts a plain PowerShell process. Use absolute tool paths in the command arrays, or configure the worker account's persistent tool environment; a Developer PowerShell terminal's temporary `PATH` will not automatically carry into the scheduled task.

Inspect the result with `Get-ScheduledTask -TaskName AutoFix-Daily` and remove it with `Unregister-ScheduledTask -TaskName AutoFix-Daily`. Daily execution uses the machine's current date interpreted by the application's configured timezone.

## Inspect run history in the dashboard

To look around before connecting anything, start the demo:

```powershell
uv run --no-sync auto-fix dashboard --demo
```

It writes a sample state to `.auto-fix/dashboard-demo` (or `--directory`), rebuilt on each start, and opens a guided tour on the first visit; the **?** button in the header replays it. The demo's runs are real workflow runs against stand-in TeamCity, Bitbucket, Jira, model and build services on a simulated clock: a published fix, a verified candidate after a truncated model answer, a paused, a cancelled and an abandoned run, a fix that broke another test, a failure that did not reproduce, an uncertain publication, schedules, batches and review decisions. Run controls work, but no job runs and every service address is a placeholder. `--demo` refuses a directory that holds anything but an earlier demo.

The dashboard reads the state directory, including runs that finished before it started. It needs no additional service or package:

```powershell
uv run --no-sync auto-fix dashboard --config config.local.yaml
# Or, read-only, any state directory or evaluation output tree.
uv run --no-sync auto-fix dashboard --directory .auto-fix/evaluation/luna
```

Open `http://127.0.0.1:8765/`. A run page leads with what a reviewer needs: **The fix** (the verified `fix.diff` in a unified or side-by-side view with word-level changes and syntax colours, and copyable `git switch`/`git apply` commands) or **Why it stopped** in plain words, then **Validation** (the whole suite before and after the edit, with tests the edit newly broke called out), **The failure** (TeamCity failure messages, the failing build's commits, their pull requests and Jira issues) and the repair attempts. **Build log** shows each check's compiler and test output; **Checkpoints** lists the state each node changed, with the complete LangGraph checkpoint after any step; **Model calls** show latency, tokens, the request and, for a failed call, what the model returned. The header shows when the page last refreshed and warns when the server stops answering. The server listens on localhost; use `--host` deliberately because the pages contain source and issue context.

The top bar leads to **History**, **Tests** (each failing test's runs, fixes and failures that did not reproduce), **Metrics** (fix rate, time to a verified fix, failed model calls and tokens per workflow and day), **Schedules**, **Batches** and **Settings** (the effective configuration, with token variables by name only, and a connection check for TeamCity, Bitbucket, Jira, the model and the repository). Settings can also turn on browser notifications for runs that need attention. The header's theme button, or Settings, switches between the system theme, light and dark; the choice is kept per browser.

### Start and control workflows

Started with `--config`, the dashboard can also run workflows. The tree groups **Repairs**, **Evaluations** and **Tools**. Repair workflows are named by their purpose, with the TeamCity configuration as their scope. **Workflows** leads with runs needing attention, active work, upcoming schedules and recent repair batches, followed by the workflow catalogue. **Run…** opens the workflow's parameters, with the equivalent command line, before anything starts; the clock button schedules it. Queued jobs can be reordered. Jobs run one at a time. A run page has one main button for its state and an **Actions** menu for the rest:

| Run state | Main button | Actions menu |
| --- | --- | --- |
| Running | Stop… (after the current step, or immediately; not while publishing) | Pause after this step |
| Paused | Resume | Re-run from a step, Cancel run |
| Blocked or cancelled | Run again (a fresh worktree) | Re-run from a step |
| Ready | Publish pull request (refused while the fix is rejected) | Re-run from a step |
| Publication unknown | Reconcile with Bitbucket | |

Every finished run's **Actions** menu also records a review decision: **Reject this fix**, **Mark handled manually**, **Snooze** or **Dismiss from attention**, each with an optional reason, and **Reopen**. A decided run leaves **Needs attention**; the decision, notes and a good/bad fix rating are kept in `triage.json` in the state directory.

**Re-run from a step** (`baseline`, `investigate`, `repair` or `verify`) starts a new run (`<key>-rN`) from the same prepared commit, with the edits applied before that step and the checkpoint that step started from; the original run is kept. Stop and pause also work on runs that the scheduled `run` command started.

The dashboard runs queued jobs itself unless it is started with `--no-runner`; then `auto-fix worker --config config.local.yaml` runs them, for example as a service. `auto-fix queue --config … --kind batch --param publish=true` adds a job from a terminal. Write requests need a token embedded in the page and are refused from other origins, so other sites cannot act through your browser.

### Find runs and download evidence

Each workflow's history, and **History**, supports 25/50/100 runs per page, search as you type,
exact status filters, a start-date range with Today/7/30-day presets, and sorting by result,
start or duration. The URL preserves the page and filters, including when returning from a run.
History rows use stored summaries without loading every checkpoint. Row icons download the
verified patch, when available, and the run's ZIP evidence bundle. The Artifacts tab also downloads individual files. Downloads support large
logs and binary evidence; text previews retain their 2 MB limit. Text downloads redact configured
secret values, and checkpoint databases and files outside the evidence directory are excluded.

The run overview ends with the executed LangGraph path (including repeat visits); click a step
to inspect its state changes in **Checkpoints**. The attention list includes verified local
candidates awaiting publication, paused and blocked runs, uncertain publication, runs whose
worker disappeared and jobs that could not start. Its rows act in place (publish, resume,
reconcile, retry) and can be dismissed.

### Schedule workflows

Use a workflow's clock button or **Schedules** to create a one-time, daily or weekday schedule
with saved parameters and an explicit IANA timezone, such as `Europe/Paris`. A repair schedule
can use the execution day's failures, resolved in that timezone, or a fixed date. Schedules show
their next five occurrences, last trigger and last job outcome, and can be edited, disabled or
deleted without deleting past runs.

Schedules are persisted in the state directory and dispatched by the same embedded runner or
standalone `auto-fix worker`; a worker must be running for them to fire. The default missed-run
policy catches up once after downtime. **Skip missed occurrences** skips triggers more than a
minute late. The default overlap policy skips an occurrence while that schedule still has queued
or running work; alternatively queue another invocation. Nonexistent local times during a DST
spring-forward are skipped, and repeated fall-back times run once at their first occurrence.
Re-enabling a schedule starts from its next future occurrence. No Windows tasks are registered
by the dashboard; the existing Task Scheduler scripts remain available separately.

### Follow a repair batch

**Batches** retains manual and scheduled discovery invocations and their child repair jobs.
Expand a batch to see individual outcomes and open run evidence or job logs. Summaries include
ready/published/blocked repairs, already-handled failures and scans that found no failures.
Discovery errors and partial discovery remain visible. Dismissing a failed job hides it from the
queue while retaining its record for batch history. Older jobs retain their recorded outcome;
parent/child links are available for batches created with this version.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/dashboard-overview.png">
  <img alt="Run overview: result, TeamCity and Git facts, the executed workflow path with a repair and verify loop, and per-step durations" src="docs/images/dashboard-overview-light.png">
</picture>

The run history lists every run grouped by state directory or evaluation case:

![Run history with published, ready and blocked runs and their reasons](docs/images/dashboard-runs.png)

**Checkpoints** (formerly the build log) expands any graph step to the state it changed; this run's first repair failed verification before a second proposal passed:

![Build log with the investigate step and the failed verification expanded](docs/images/dashboard-build-log.png)

Each model call keeps its latency, token usage, explanation and exact proposed edits:

![Model calls with token usage and the accepted source edit](docs/images/dashboard-model-calls.png)

The screenshots use synthetic runs with stubbed services and predate the 2026-10-25 layout.

Live OpenTelemetry traces are optional. Install the extra with `uv sync --locked --extra dev --extra trace`, start a self-hosted [Arize Phoenix](https://arize.com/docs/phoenix) collector (for example `phoenix serve`), and add to the configuration:

```yaml
tracing:
  endpoint: http://127.0.0.1:6006/v1/traces
  project: auto-fix
```

Each run becomes one Phoenix session: LangGraph nodes become spans, with model calls nested under their node as LLM spans. Token values are redacted. The `demo` and `evaluate` commands export when `AUTO_FIX_TRACE_ENDPOINT` is set. Spans contain the model context, so keep the collector on company-managed infrastructure. Export runs in the background and never delays a build. Phoenix does not receive spans while it is stopped; the dashboard still shows those runs from the state directory.

## Add a workflow step

Nodes are plain functions receiving and updating shared state. For example, add a deterministic ownership hint in `src/auto_fix/workflow.py`:

```python
def add_owner(state: State) -> State:
    return {"context": {**state.get("context", {}), "owner": "C++ platform team"}}
```

In `Workflow.graph()`, register it and replace the existing direct `collect_context` → `prepare` edge with:

```python
graph.add_node("add_owner", add_owner)
graph.add_edge("collect_context", "add_owner")
graph.add_edge("add_owner", "prepare")
```

The new context reaches the repair model through the existing state. A richer step can query another internal API using the same pattern; use a conditional edge when its result should stop or redirect execution.

## Scope of this starter

This is an executable starter, not a guarantee that a 27B model can fix arbitrary C++ regressions. It uses standard Chat Completions plus validated JSON edits, so native tool calling and strict server-side JSON schema support are not prerequisites. Endpoint-specific compatibility and fix quality require a real trial with your deployment.

Use a worker that is permitted to execute the checked-out C++ project: configured builds and tests execute repository code. Run logs and checkpoints can contain internal source, test output and issue context; keep `state_dir` on company-managed storage. Git submodule repositories are currently rejected; initializing and validating submodules needs a dedicated extension. This starter has no cloud tracing requirement, distributed job queue, automatic conflict resolution, automatic merge, or generated UI screenshot capture.
