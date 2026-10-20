# Evaluate and adapt the workflow

The evaluation runs the same LangGraph workflow against a pinned public C++ codebase, realistic synthetic TeamCity/Bitbucket/Jira responses, and a selectable repair model. Git operations, native compilation, test execution, rebases, and local branch publication are real. Enterprise API requests and Bitbucket PR creation are intercepted locally; company credentials are unnecessary.

[Fixture provenance and cases](../evaluation/README.md) describe the pinned Abseil release and GoogleTest dependency. Four independent source regressions cover lowercase dispatch, escaped hexadecimal bytes, Windows carriage returns, and C++ symbol demangling. Existing upstream test suites execute **188 tests**, with one additional test disabled by upstream. These synthetic bugs are a smoke benchmark; they are not historical Abseil incidents or an estimate of general C++ repair accuracy.

## Verified live results

On 20 October 2026, actual `gpt-6-luna` calls through Codex CLI with `medium` reasoning effort ran on macOS. Each round compiled and executed the upstream C++ tests, applied the model's own edits, and exercised the complete rebase/retest/local-push/mock-PR path.

| Round | Context implementation | Cases completed | Live model calls | Evidence |
| --- | --- | --- | --- | --- |
| `baseline-v1` | Original file-prefix selection | 2 / 4 | 6 | [Summary](../evaluation/results/baseline-v1/summary.json) |
| `focused-v1` | Initial failure/symbol retrieval | 2 / 4 | 7 | [Summary](../evaluation/results/focused-v1/summary.json) |
| `focused-v2` | Revised source ranking and focused excerpts | 4 / 4 | 4 | [Summary](../evaluation/results/focused-v2/summary.json) |
| `confirmation-v2` | Same focused implementation, fresh live calls | 4 / 4 | 4 | [Summary](../evaluation/results/confirmation-v2/summary.json) |

The first retrieval revision did not improve this case set; its unsuccessful results are retained. The next revision reduced noisy build/path signals and irrelevant large-document matches, improving which implementation excerpts reached the model. The final round repaired each case with one model call:

| Case | Final executed tests passing | Model calls |
| --- | --- | --- |
| Lowercase dispatch | 12 | 1 |
| Hexadecimal escape decoding | 18 | 1 |
| Carriage-return whitespace splitting | 31 | 1 |
| Reference-qualified callback demangling | 127 | 1 |
| Total | 188 | 4 |

The fresh confirmation round also repaired all four cases with one model call per case and passed the same 188 tests. Together, the final two rounds completed **eight repair runs across four unique synthetic defects**. They are repeated trials of the same defects, rather than eight different bugs.

One additional escaping test is disabled by upstream. The [accepted response recordings](../evaluation/recordings/accepted) preserve the actual final-round model proposals for native replay. These results show improvement on four fixed synthetic regressions. They do not establish a general repair rate, Windows live-model results, or behavior on your private C++ solution. Windows/Linux recorded replay is configured in CI; a CI result is separate evidence from these live macOS runs.

## Run with GPT-6 Luna

Install the project dependencies as described in the main README. Windows needs Visual Studio C++ build tools and a Developer PowerShell terminal. Linux and macOS additionally need Ninja; those platforms use Ninja to avoid stale objects when a source edit and object compilation share a timestamp second. Windows uses the default Visual Studio CMake generator, `--config Release`, and a targeted MSBuild `/t:Rebuild`. This forces compilation of the selected test project and its dependencies without cleaning the entire Abseil solution before every verification.

Authenticate your installed Codex CLI, then run:

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/luna-focused --profile focused --backend codex --model gpt-6-luna
```

The model is [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna). The evaluation adapter invokes the actual model through Codex CLI with `medium` reasoning effort, structured output, and an isolated request directory. It supplies only the workflow's JSON context and repair instructions. External tool use is prohibited and detected in the returned CLI events. The model proposes edits; the runner applies and tests them.

Each output directory must be empty or new, preserving earlier evidence. The first run downloads pinned Abseil/GoogleTest checkouts into `.auto-fix/upstream`. Later runs reuse these clean source caches and build each scenario in a new local checkout/worktree. Internet access is needed for the public source download and live model requests.

To investigate fewer cases, repeat `--case`:

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/luna-two-cases --case split_ascii_carriage_return --case demangle_rvalue_function_qualifier
```

A run succeeds only after the actual patch builds, the full configured upstream suite passes, the final rebase is retested, the tested SHA is pushed to a local bare repository, and exactly one mock Bitbucket PR is created. Test edits are rejected. `summary.json` reports every case; the process exits nonzero if any case fails.

## Compare a workflow change

`legacy` reproduces the original file-prefix context selection. `focused`, the default, retrieves source excerpts around failure locations and symbols, follows local includes, and preserves useful build/test feedback for another repair attempt. Both use the same source regressions, test binaries, model interface, retry limit, and final verification gates.

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/luna-legacy --profile legacy --backend codex
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/luna-candidate --profile focused --backend codex
```

Compare the per-case outcome and failed stage before looking at totals. A context retrieval failure, malformed model proposal, wrong patch, compilation failure, and publication failure require different fixes. Re-run the whole case set after changing a shared step; repeat live runs to assess variability. Current runs capture manifest hashes identifying the implementation and fixture. The historical `focused-v1` round predates manifest instrumentation and retains `context-engine.py.txt` plus its model request packets instead.

The evaluator knows the mutations to create and score a scenario. It does not send `cases.json` or explicit expected repair edits to the model. Direct-context cases expose the recent source diff, as a normal TeamCity change would; this can make their inverse patch easy. Indirect-context cases report a later unrelated change and require locating an older defective implementation. The clean upstream repository remains the evaluator's private input, rather than a model tool.

## Replay recorded responses

The replay backend reads genuine saved model proposals and executes the remaining workflow against fresh native builds. It makes **no live model request** and cannot measure how a new prompt or context selection changes model quality.

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/replay --profile focused --backend replay --recordings evaluation/recordings/accepted
```

Recordings have one directory per case, containing `call-1/metadata.json`, `call-1/response.json`, and further calls when needed. Replay validates model identity and successful original-call metadata, preserves the original recording, and records its response hash and provenance in the new run. Missing calls fail; there is no fallback to live inference or a hand-written patch.

CI is configured to use recorded Luna outputs to check workflow mechanics and native Abseil builds on Windows and Linux. CI replay is separate from live model evaluation. Review [the workflow configuration](../.github/workflows/ci.yml) and its uploaded evidence to see which checks a particular commit ran.

## Evaluate your Qwen endpoint

Use an ordinary local configuration whose `llm` section points at your OpenAI-compatible server:

```powershell
uv run --no-sync auto-fix evaluate --directory .auto-fix/evaluation/qwen --profile focused --backend endpoint --config config.local.yaml
```

Only the configured model endpoint is used from this configuration. TeamCity, Bitbucket, Jira, repository, and build settings remain the isolated synthetic evaluation. The model name comes from `llm.model`; its token comes from the configured environment variable. The runner also loads `.env` beside the configuration, with existing shell environment values taking precedence. This lets you compare Qwen against the same failures before connecting company systems.

## Inspect the evidence

| Artifact | What it shows |
| --- | --- |
| `manifest.json` | Model/backend/profile, source hashes, fixture hash, and whether inference was live |
| `summary.json` | Every case's outcome, attempts, elapsed time, original failures, and final test count |
| `<case>/preflight/` | Actual native build and failing upstream test evidence used to populate TeamCity |
| `<case>/model/call-N/` | Live CLI request, structured response, events, stderr, usage, and model metadata |
| `<case>/state/runs/<run-id>/` | Workflow checkpoint results, repair proposals, logs, diffs, and verification reports |
| `<case>/requests.json` | Mock TeamCity/Bitbucket/Jira requests made through the production adapters |
| `<case>/pull-requests.json` | Mock PR payload, including synthetic TeamCity/Jira/evidence links |
| `<case>/score.json` | Per-case score and verified local remote-branch SHA |

The exact workflow result path is also stored in each score entry. Native assertion output is obtained from the compiled upstream tests, rather than authored fixture logs. Company names, people, tickets, discussions, CI metadata, and evidence URLs come from [onprem.json](../evaluation/fixtures/onprem.json). Screenshot URLs exercise link handling; the benchmark does not capture application screenshots.

## Make a targeted adaptation

Change [context.py](../src/auto_fix/context.py) for source retrieval, [llm.py](../src/auto_fix/llm.py) for repair instructions, [workflow.py](../src/auto_fix/workflow.py) for nodes and retry routing, or [integrations.py](../src/auto_fix/integrations.py) for API behavior. Scenario data lives in the evaluation manifests and `fixtures/onprem.json`. Add new defects with existing tests and verify the unmodified snapshot passes before injecting each defect.

Keep repair scope and validation independent: the model should edit production source while unchanged upstream tests decide whether the resulting behavior is acceptable. Inspect the patch itself alongside passing tests, especially where different implementations could satisfy a limited test suite.
