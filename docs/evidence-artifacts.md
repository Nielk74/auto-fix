The evidence exporter packages existing evaluation results without calling a model, running a build, or contacting an API. It accepts only explicitly supplied live `gpt-6-luna` runs using `codex-cli`. Exporting a development prototype does not turn it into a formal result or select a winning workflow.

Run this from the repository root, using an installed development environment:

```console
python scripts/expanded-evidence.py --run development=ACTUAL_RUN_DIRECTORY --destination .auto-fix/artifacts/development
```

Repeat `--run NAME=DIRECTORY` to combine runs. Names contain letters, digits, hyphens, and underscores. The destination must be new, outside the input runs. Export first writes a temporary directory and publishes it only after validation succeeds. Existing artifacts are never overwritten.

The output preserves the original relative tree under `results/NAME/`: manifests, summaries, attested implementation snapshots, case scores, synthetic service requests and PR records, model requests/responses/schemas/metadata/events, workflow state and inspection evidence, repair diffs, and native JUnit/logs. Source clones, Git objects, worktrees, build caches, executables, environment files, and unrelated files are excluded. Failed runs and truncated model responses remain evidence; they are not automatically eligible for replay.

Every call must identify the exact model, CLI transport, explicit `repair` or `investigation` kind, and integer return code. Requests and metadata must agree. Malformed event streams, outside CLI tool events, and unknown item types reject the export. Recorded typed searches and reads are legitimate workflow actions; they remain in the inspection evidence rather than being mistaken for CLI tool use.

The exporter rejects detected credentials rather than rewriting recorded responses. It checks current secret environment values, common token/header patterns, and credential fields. Input files have a 64 MiB limit each; `--max-file-bytes` changes that limit. Files are never silently truncated. These checks do not authenticate the model provider or replace review of evidence intended for public release.

To create replay recordings, supply a JSON configuration mapping run names to their frozen input manifests. Explicit case selection makes the intended replay set reviewable:

```json
{
  "accepted-development": {
    "project_file": "evaluation/expanded/fmt.json",
    "cases_file": "evaluation/expanded/cases_fmt.json",
    "case_ids": ["fmt_utf8_validation_boundaries"],
    "windows_case_ids": ["fmt_utf8_validation_boundaries"]
  }
}
```

```console
python scripts/expanded-evidence.py --run accepted-development=ACTUAL_RUN_DIRECTORY --recordings recording-config.json --destination .auto-fix/artifacts/accepted-development
python scripts/replay-expanded.py --root .auto-fix/artifacts/accepted-development --index recordings/expanded/index.json validate
```

Manifest paths are relative to `--workspace` (the current directory by default), and their SHA-256 values must match the live run. `case_ids` is optional; omitting it selects successful cases only. Explicitly selecting a failed case rejects the export. `windows_case_ids` supplies CI tags; it does not claim that Windows was tested.

Recordings live under `recordings/expanded/CASE/call-N/`, with the exact response, metadata, and request bytes. Their index records input hashes, prompt, reasoning effort, inspection/repair budgets, structured diagnostics, original failing test identities, and the ordered call hashes/kinds. Only published cases with passing native verification and valid successful model responses qualify. Investigation calls retain their position before repairs. The paired [replay script](../scripts/replay-expanded.py) validates that index, then can replay accepted actions through fresh native gates without live inference. Its independent grade requires every originally passing and failing test to appear as passing in the actual final JUnit, plus matching tested, pushed, and PR commits. Its `matrix --platform linux` selects every recorded case; `matrix --platform windows` selects tagged representatives.

Fixture authoring proofs can be exported alone or alongside runs:

```console
python scripts/expanded-evidence.py --fixture-proofs evaluation/expanded/dataset-index.json --destination .auto-fix/artifacts/fixture-proofs
```

This mode follows the dataset registry, its case/project manifests, hunk audits, and referenced native proof paths. It verifies supplied source hashes and includes related XML, raw XML, logs, and JSON proof metadata. Identical files share a blob in `fixture-proofs/blobs/`. `fixture-proofs/index.json` maps each original workspace-relative path to its exported blob, exact hash, and byte count; `verified_source_hashes` distinguishes files checked against an existing trusted hash from sibling logs hashed at export. Build/source caches and binaries stay excluded. Fixture manifests contain evaluator-only mutations and must never be sent to the repair model.

`SHA256SUMS` and `SHA256SUMS.json` cover every exported record except the checksum manifests themselves. Verify an artifact portably from its root:

```python
import hashlib
import json
from pathlib import Path

root = Path(".auto-fix/artifacts/development")
for relative, expected in json.loads((root / "SHA256SUMS.json").read_text()).items():
    assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
```

The exporter preserves paths within each run; absolute source paths inside raw JSON/logs remain historical provenance. The fixture remapping index resolves ignored authoring paths without those original directories. Attachments outside the text evidence allowlist, such as compiled files or screenshot image assets, are not included.

The exporter was checked against a development prototype containing two native repairs and six genuine Luna calls, including investigation actions, plus a separate unsuccessful development baseline. Those checks validate packaging and provenance handling; they are not final benchmark accuracy results. The fixture-only packaging check preserved 676 source proof files as 562 unique blobs, approximately 15 MiB. No holdout model outcomes were inspected during this validation.
