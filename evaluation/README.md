# C++ workflow evaluation fixture

Run the complete workflow with `auto-fix evaluate`; see the [evaluation guide](../docs/evaluation.md) for live GPT-6 Luna, endpoint, and recorded replay commands.

This benchmark uses the real [Abseil C++ library](https://github.com/abseil/abseil-cpp), pinned to LTS release `20260107.1` (`255c84dadd029fd8ad25c5efb5933e47beaa00c7`). Abseil contains widely used production C++ components and officially supports CMake on Windows. Its Apache 2.0 license permits this isolated testing; keep upstream license files in downloaded checkouts.

The fixture is substantial: **840 `.cc`/`.h` files and 265,865 lines** under `absl`, including **517 production files and 142,256 production lines** by the documented filename/path filter. The complete downloaded working tree is 10,862,971 bytes, excluding `.git`. These are measured source snapshot counts, not claims about compiled coverage. The evaluation builds a small, representative set of real upstream unit test binaries; it does not build or test every Abseil component.

`project.json` records exact source/dependency revisions, build options, metrics, and primary source links. GoogleTest is independently pinned to release `v1.17.0` (`52eb8108c5bdec04579160ae17225d66034bd723`). Downloaded source and compiled output stay under ignored `.auto-fix/`; this repository does not vendor Abseil or GoogleTest.

## Cases and what they measure

`cases.json` is the evaluator's fixture oracle. It supplies exact mutations to fixture preparation and verification. **Do not include this manifest, a clean-source oracle, or explicit expected repair edits in the model prompt.** Direct cases intentionally expose the recent change through normal Git context; indirect cases omit the mutation from the reported recent changes. The workflow should receive the same evidence available from an ordinary failing build: test output, source inspection, Git changes, pull requests, and Jira context.

| Case | Production behavior | Existing upstream suite | Context |
| --- | --- | --- | --- |
| `ascii_lower_dispatch` | In-place lowercase conversion uses the wrong case-folding dispatch | `absl_ascii_test` | Direct changed-source context |
| `hex_digit_conversion` | Escaped hexadecimal letter digits decode to incorrect bytes | `absl_escaping_test` | Direct changed-source context |
| `split_ascii_carriage_return` | ASCII whitespace splitting retains Windows carriage returns | `absl_str_split_test` | Indirect change context; retrieve implementation from failure |
| `demangle_rvalue_function_qualifier` | Rvalue reference qualified callback symbols fail to demangle | `absl_demangle_test` | Indirect change context; relevant parser lies 58,148 bytes into a 101,007-byte source file |

Each case is injected independently into an otherwise clean pinned checkout. These are **synthetic source regressions**, not historical Abseil bugs. Existing upstream tests are preserved. No test is weakened, replaced, or generated to make a proposed repair pass. Full selected test suites, rather than only the single reported failing test, validate a repair. A reverse mutation is a useful integrity check, but successful evaluation must compile and execute the model's actual patch.

Two direct cases test the ordinary path where recent changes identify relevant source. Two indirect cases require the workflow to locate the implementation from test names/content despite unrelated recent changes. The large parser case detects workflows that truncate every file to a fixed prefix and consequently cannot see the relevant code.

## Recorded workflow evaluation

Live `gpt-6-luna` evaluations through Codex CLI on macOS completed 2 of 4 cases with the original strategy, 2 of 4 with the first source-retrieval revision, and 4 of 4 with the revised focused strategy. The final run and a fresh confirmation each used one model call per case and passed 188 existing upstream tests, giving eight successful repair runs across four unique synthetic defects. The initial unsuccessful revision is retained alongside the successful result. See the [evaluation results](../docs/evaluation.md#verified-live-results) and [accepted model recordings](recordings/accepted) for evidence and replay instructions.

## Native build independently

Requires Git, CMake, and a C++17 compiler. The complete evaluation additionally uses Ninja on Linux/macOS; Windows uses its default CMake generator and clean rebuilds. On Windows, run in a Visual Studio 2022 Developer PowerShell with the C++ build tools installed. The commands use the default platform CMake generator and work with single- and multi-configuration generators.

```powershell
git clone --depth 1 --branch 20260107.1 https://github.com/abseil/abseil-cpp.git .auto-fix/upstream/abseil
git -C .auto-fix/upstream/abseil rev-parse HEAD
# Must print 255c84dadd029fd8ad25c5efb5933e47beaa00c7.
git clone --depth 1 --branch v1.17.0 https://github.com/google/googletest.git .auto-fix/upstream/googletest
git -C .auto-fix/upstream/googletest rev-parse HEAD
# Must print 52eb8108c5bdec04579160ae17225d66034bd723.
$gtestPath = (Resolve-Path .auto-fix/upstream/googletest).Path
cmake -S .auto-fix/upstream/abseil -B .auto-fix/upstream/abseil-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=17 -DABSL_BUILD_TESTING=ON -DABSL_USE_GOOGLETEST_HEAD=OFF "-DABSL_LOCAL_GOOGLETEST_DIR=$gtestPath" -DABSL_ENABLE_INSTALL=OFF
cmake --build .auto-fix/upstream/abseil-build --config Release --clean-first --parallel 4 --target absl_ascii_test absl_escaping_test absl_str_split_test absl_demangle_test
ctest --test-dir .auto-fix/upstream/abseil-build -C Release -R '^absl_(ascii|escaping|str_split|demangle)_test$' --output-on-failure
```

The source SHA checks are required even when cloning a named tag: tags can be moved. Fixture preparation should fail if the checkout differs from the manifest. Builds must use the pinned local GoogleTest checkout rather than downloading its current main branch.

## Interpreting results

The evaluator writes `manifest.json`, `summary.json`, per-case scores, model evidence, real native test reports, and mocked request/PR payloads. The selected suites execute **188 upstream tests**, plus one test disabled by upstream.

A useful report distinguishes reproduction, model repair, build/test validation, final rebase/retest, and mock PR creation. Record model identity, prompt/configuration revision, attempts, elapsed time, test counts, changed files, and failures at each stage. Keep the original failing output, actual model response, applied diff, compiler output, JUnit results, and mocked PR payload for audit.

Model changes and context changes can affect results; rerun exactly the same case set before and after an improvement. Four synthetic cases provide a reproducible smoke benchmark, not a general repair success rate for an organization's C++ solution. A final clean source diff, immutable test hashes, and execution of the repaired upstream binaries provide stronger evidence than the model claiming it fixed a failure.

## Primary sources

- [Abseil release 20260107.1](https://github.com/abseil/abseil-cpp/releases/tag/20260107.1)
- [Official CMake quickstart](https://abseil.io/docs/cpp/quickstart-cmake.html)
- [Pinned upstream CMake configuration](https://github.com/abseil/abseil-cpp/blob/255c84dadd029fd8ad25c5efb5933e47beaa00c7/CMakeLists.txt)
- [Pinned Apache 2.0 license](https://github.com/abseil/abseil-cpp/blob/255c84dadd029fd8ad25c5efb5933e47beaa00c7/LICENSE)
- [GoogleTest v1.17.0](https://github.com/google/googletest/releases/tag/v1.17.0)
