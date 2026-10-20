from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import zlib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "expanded-evidence.py"
SPEC = importlib.util.spec_from_file_location("expanded_evidence", SCRIPT)
assert SPEC and SPEC.loader
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def run(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / ".auto-fix" / "development-prototype"
    case = source / "sample_case"
    result = case / "state" / "runs" / "sample-run" / "result.json"
    native = result.parent / "evidence" / "verification" / "junit.xml"
    native.parent.mkdir(parents=True)
    native.write_text('<testsuites><testsuite><testcase name="a"/></testsuite></testsuites>')
    (native.parent / "test.log").write_text("1 test passed\n", encoding="utf-8")
    write_json(
        result,
        {
            "status": "published",
            "verification": {
                "report": {"passed": ["Suite.a"], "failed": []},
                "logs": [str(native)],
            },
        },
    )
    write_json(
        result.parent / "inspection-evidence-1.json",
        {"reads": [{"path": "example.cc", "content": "int f();"}]},
    )
    write_json(
        result.parent / "baseline-checks.json",
        {"requested": 3, "observed": 2, "checks": [{"report": {"failed": ["Suite.a"]}}]},
    )
    (result.parent / "fix.diff").write_text(
        "--- a/example.cc\n+++ b/example.cc\n@@ -1 +1 @@\n-return 0;\n+return 1;\n"
    )
    write_json(workspace / "evaluation" / "project.json", {"id": "sample"})
    write_json(
        workspace / "evaluation" / "cases.json", [{"id": "sample_case", "split": "development"}]
    )
    calls = []
    for number, kind in enumerate(("investigation", "repair"), start=1):
        call = case / "model" / f"call-{number}"
        metadata = {
            "model": "gpt-6-luna",
            "transport": "codex-cli",
            "kind": kind,
            "returncode": 0,
            "reasoning_effort": "medium",
            "usage": {"input_tokens": 50},
        }
        write_json(call / "metadata.json", metadata)
        write_json(
            call / "request.json", {"system": "test instruction", "context": {}, "kind": kind}
        )
        response = (
            {
                "summary": "Read implementation",
                "hypotheses": [],
                "queries": ["function"],
                "reads": [{"path": "example.cc", "line": 0, "symbol": ""}],
                "ready": False,
            }
            if kind == "investigation"
            else {
                "summary": "Repair boundary",
                "explanation": "Restore the observed contract",
                "edits": [{"path": "example.cc", "old": "return 0;", "new": "return 1;"}],
            }
        )
        write_json(call / "response.json", response)
        (call / "events.jsonl").write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": json.dumps(response)},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls.append(metadata)
    entry = {
        "case": "sample_case",
        "model": "gpt-6-luna",
        "success": True,
        "baseline_failed": ["Suite.a"],
        "model_calls": calls,
        "result": str(result),
    }
    manifest = {
        "model": "gpt-6-luna",
        "backend": "codex",
        "live_inference": True,
        "case_ids": ["sample_case"],
        "source_sha256": {},
        "project_sha256": sha(workspace / "evaluation" / "project.json"),
        "cases_sha256": sha(workspace / "evaluation" / "cases.json"),
        "prompt_version": "contract-v3",
        "max_inspections": 3,
        "max_attempts": 2,
        "structured_diagnostics": True,
        "reasoning_effort": "medium",
    }
    write_json(source / "manifest.json", manifest)
    write_json(
        source / "summary.json", {"model": "gpt-6-luna", "backend": "codex", "cases": [entry]}
    )
    write_json(case / "score.json", entry)
    return workspace, source


def test_preserves_tree_exact_hashes_and_excludes_caches(run, tmp_path):
    workspace, source = run
    for relative in (
        "sample_case/source/.git/objects/object",
        "sample_case/source/.env",
        "sample_case/remote.git/config",
        "sample_case/state/worktrees/main/secret.log",
        "sample_case/model/call-1/program.exe",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not for export")
    destination = tmp_path / "artifact"
    index = evidence.export({"dev": source}, destination, workspace=workspace)
    assert index["runs"][0]["model_calls"] == 2
    native = "results/dev/sample_case/state/runs/sample-run/evidence/verification/junit.xml"
    hashes = json.loads((destination / "SHA256SUMS.json").read_text())
    assert native in hashes
    baseline = "results/dev/sample_case/state/runs/sample-run/baseline-checks.json"
    assert baseline in hashes
    assert (destination / baseline).read_bytes() == (
        source / "sample_case/state/runs/sample-run/baseline-checks.json"
    ).read_bytes()
    for relative, expected in hashes.items():
        assert sha(destination / relative) == expected
    assert not any(
        ".git" in path or "/source/" in path or "worktrees" in path or path.endswith(".exe")
        for path in hashes
    )
    assert not (destination / "results/dev/sample_case/result.json").exists()


@pytest.mark.parametrize("location", ["manifest", "summary", "metadata", "summary_call"])
def test_rejects_other_models_without_publishing(run, tmp_path, location):
    workspace, source = run
    path = source / (
        "sample_case/model/call-1/metadata.json"
        if location == "metadata"
        else f"{location if location != 'summary_call' else 'summary'}.json"
    )
    document = json.loads(path.read_text())
    if location == "summary_call":
        document["cases"][0]["model_calls"][0]["model"] = "another-model"
    else:
        document["model"] = "another-model"
    write_json(path, document)
    destination = tmp_path / "artifact"
    with pytest.raises(ValueError, match="model|Luna|luna"):
        evidence.export({"dev": source}, destination, workspace=workspace)
    assert not destination.exists()
    assert not list(tmp_path.glob(".artifact-*"))


@pytest.mark.parametrize(
    "event",
    [
        {"type": "item.started", "item": {"type": kind}}
        for kind in (
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "web_search",
            "collab_tool_call",
            "unknown_tool",
        )
    ]
    + [{"type": "command_execution"}, {"type": "item.completed", "item": "invalid"}],
)
def test_rejects_outside_cli_actions(run, tmp_path, event):
    workspace, source = run
    (source / "sample_case/model/call-1/events.jsonl").write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="tool event"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_rejects_malformed_cli_jsonl(run, tmp_path):
    workspace, source = run
    (source / "sample_case/model/call-1/events.jsonl").write_text('{"type":')
    with pytest.raises(ValueError):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


@pytest.mark.parametrize("change", ["missing_kind", "not_live", "gap", "wrong_kind"])
def test_rejects_unattested_or_inconsistent_call_sequences(run, tmp_path, change):
    workspace, source = run
    call = source / "sample_case/model/call-1"
    metadata = json.loads((call / "metadata.json").read_text())
    if change == "gap":
        call.rename(call.parent / "call-3")
    elif change == "wrong_kind":
        write_json(call / "request.json", {"kind": "repair"})
    else:
        if change == "missing_kind":
            del metadata["kind"]
        else:
            metadata["live_inference"] = False
        write_json(call / "metadata.json", metadata)
    with pytest.raises(ValueError):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_archives_failed_truncated_responses_without_making_replay_claim(run, tmp_path):
    workspace, source = run
    summary = json.loads((source / "summary.json").read_text())
    summary["cases"][0]["success"] = False
    write_json(source / "summary.json", summary)
    raw = b'{"summary":"incomplete'
    (source / "sample_case/model/call-2/response.json").write_bytes(raw)
    destination = tmp_path / "artifact"
    index = evidence.export({"dev": source}, destination, workspace=workspace)
    assert "recordings" not in index
    assert (destination / "results/dev/sample_case/model/call-2/response.json").read_bytes() == raw


def test_recording_rejects_native_failures_and_bad_input_hashes(run, tmp_path):
    workspace, source = run
    config = {
        "dev": {"project_file": "evaluation/project.json", "cases_file": "evaluation/cases.json"}
    }
    (workspace / "evaluation/cases.json").write_text("{}")
    with pytest.raises(ValueError, match="SHA256"):
        evidence.export(
            {"dev": source}, tmp_path / "bad-input", workspace=workspace, recordings=config
        )
    write_json(workspace / "evaluation/cases.json", [{"id": "sample_case", "split": "development"}])
    result = source / "sample_case/state/runs/sample-run/result.json"
    write_json(
        result,
        {
            "status": "published",
            "verification": {"report": {"passed": ["Suite.a"], "failed": ["Suite.b"]}},
        },
    )
    with pytest.raises(ValueError, match="native verification"):
        evidence.export(
            {"dev": source}, tmp_path / "bad-native", workspace=workspace, recordings=config
        )


@pytest.mark.parametrize("repetitions", [None, 3])
def test_investigation_then_repair_records_replay_in_sequence(run, tmp_path, repetitions):
    from auto_fix.recorded_model import RecordedRepairModel

    workspace, source = run
    if repetitions is not None:
        manifest = json.loads((source / "manifest.json").read_text())
        manifest["baseline_repetitions"] = repetitions
        write_json(source / "manifest.json", manifest)
    destination = tmp_path / "artifact"
    evidence.export(
        {"dev": source},
        destination,
        workspace=workspace,
        recordings={
            "dev": {
                "project_file": "evaluation/project.json",
                "cases_file": "evaluation/cases.json",
                "windows_case_ids": ["sample_case"],
            }
        },
    )
    index = json.loads((destination / "recordings/expanded/index.json").read_text())
    entry = index["entries"][0]
    assert entry["baseline_repetitions"] == (repetitions or 1)
    assert entry["ci_tags"] == ["windows-representative"]
    assert [call["kind"] for call in entry["recorded_calls"]] == ["investigation", "repair"]
    model = RecordedRepairModel(destination / entry["recordings_directory"])
    assert model.inspect({}).reads[0].path == "example.cc"
    assert model.propose({}).edits[0].new == "return 1;"
    assert all(call["transport"] == "recorded-replay" for call in model.calls)


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abcdefghijklmnop123456",
        "https://admin:password@example.test",
        '{"api_key":"private-key-value"}',
    ],
)
def test_rejects_credentials_in_allowlisted_evidence(run, tmp_path, secret):
    workspace, source = run
    call = source / "sample_case/model/call-1"
    if secret.startswith("{"):
        (call / "response.json").write_text(secret)
    else:
        (call / "stderr.log").write_text(secret)
    with pytest.raises(ValueError, match="credential"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_rejects_environment_secrets_without_printing_them(run, tmp_path, monkeypatch):
    workspace, source = run
    token = "private_environment_credential"
    monkeypatch.setenv("CUSTOM_API_TOKEN", token)
    (source / "sample_case/model/call-1/stderr.log").write_text(token)
    with pytest.raises(ValueError) as error:
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)
    assert token not in str(error.value)


def test_rejects_symlinked_evidence_and_outside_result_pointer(run, tmp_path):
    workspace, source = run
    response = source / "sample_case/model/call-1/response.json"
    actual = tmp_path / "outside.json"
    response.rename(actual)
    response.symlink_to(actual)
    with pytest.raises(ValueError, match="Symlink"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)
    response.unlink()
    actual.rename(response)
    summary = json.loads((source / "summary.json").read_text())
    summary["cases"][0]["result"] = str(tmp_path / "outside-result.json")
    write_json(source / "summary.json", summary)
    with pytest.raises(ValueError, match="escapes"):
        evidence.export({"dev": source}, tmp_path / "artifact", workspace=workspace)


def test_refuses_existing_destination_and_oversized_evidence(run, tmp_path):
    workspace, source = run
    destination = tmp_path / "artifact"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exist"):
        evidence.export({"dev": source}, destination, workspace=workspace)
    assert destination.exists()
    with pytest.raises(ValueError, match="byte limit"):
        evidence.export(
            {"dev": source}, tmp_path / "limited", workspace=workspace, max_file_bytes=10
        )


def test_fixture_proofs_follow_hashes_deduplicate_and_exclude_binaries(tmp_path):
    workspace = tmp_path / "workspace"
    proof = workspace / ".auto-fix/proof/case"
    proof.mkdir(parents=True)
    for filename in ("clean.xml", "injected.xml"):
        (proof / filename).write_text("<testsuites/>")
    (proof / "test.log").write_text("actual native log\n")
    (proof / "program.exe").write_bytes(b"binary")
    (proof / "source").mkdir()
    (proof / "source/secret.log").write_text("source cache must be pruned")
    audit = workspace / "evaluation/hunk-audit.json"
    write_json(
        audit,
        {
            "evidence": {
                ".auto-fix/proof/case/injected.xml": {"sha256": sha(proof / "injected.xml")}
            }
        },
    )
    index = workspace / "evaluation/dataset-index.json"
    write_json(
        index,
        {
            "clean_junit": ".auto-fix/proof/case/clean.xml",
            "clean_junit_sha256": sha(proof / "clean.xml"),
            "audit": {"path": "evaluation/hunk-audit.json", "sha256": sha(audit)},
        },
    )
    destination = tmp_path / "artifact"
    evidence.export({}, destination, workspace=workspace, fixture_proofs=index)
    mapping = json.loads((destination / "fixture-proofs/index.json").read_text())
    files = mapping["files"]
    assert (
        files[".auto-fix/proof/case/clean.xml"]["path"]
        == files[".auto-fix/proof/case/injected.xml"]["path"]
    )
    assert ".auto-fix/proof/case/test.log" in files
    assert ".auto-fix/proof/case/injected.xml" in mapping["verified_source_hashes"]
    assert all("program.exe" not in key and "/source/" not in key for key in files)
    (proof / "injected.xml").write_text("tampered")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        evidence.export({}, tmp_path / "bad-artifact", workspace=workspace, fixture_proofs=index)


def test_fixture_proof_reference_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    index = workspace / "evaluation/index.json"
    write_json(index, {"proof": ".auto-fix/../../outside.xml"})
    with pytest.raises(ValueError, match="escapes"):
        evidence.export({}, tmp_path / "artifact", workspace=workspace, fixture_proofs=index)


# Exact historical snapshot bytes, compressed for a self-contained fixture.
# The first is demo.py at da25f4f; the second adds the audited PR receipt check.
# Neither fixture is imported or executed. Whole-file SHA checks fix their identity.
HISTORICAL_DEMO_FIXTURES = {
    "847729e49167f81950e783cd882240377a04b7f04b4ec85175a2cebdc85654d7": (
        b"c-p-hYjfK+^1FWp%1$PvBT=@SYi^XPcaGzv?!|G&aeBRTG#rYAEW~^j0R5;(|NV9W@J(8Ft`mQ-NMf;A"
        b"?0XlmEbC;sj95a6p!|vjlq}he%sCar=V_jVgi}8vZ<!pCcYbp5miyUiL=KMqOG<ngJ~*R75_&^}T(UHA"
        b"Ez8>4TJkg|p0~^qljji@XDOEepQO@9FtN2|zI_pCQaq=kcoHkX7L{-LBI9X5h0vHoUsB0pTHr0-^=RhH"
        b"Rm2v>;0Jis1AnFoWyvxvM*a)$NAO<KvXU~pG1U9HOg-R*8>GpST@-UZQYl$-AzDBzk@SM=treiJm|Wz+"
        b"B?Zp?%D6uwXVi}mn7nPxjiR`ia!NCw@#8e4Q48og<(JDSy)GdCZQe&@>9YvAd`WLd<eD={J;l?lt&lE>"
        b"cfq8M9GNOcjL5dnFT|7x$sIEO8Gol+1pYwcc_hiK#%!18iLD0l@7w}Z)`(c+1NaZ~6k5k%oR3PtU`2z="
        b"*%{Ai?VFz|RY-H0<+3#>=}r3+O@cH8KF_RNF2{ejYQP|8z%u)BM}Kn+^?*Jxn{b5;0R(<H%WTJR0yg7?"
        b"G*0c1aT>^!-)fd9Hh}yz8`zS7jvD=QuU9Ns*;WvPwp$KKdEcM}0~i`amO0asc<wVn$!VV8E)F?Qxoy1$"
        b"nt<>>a)w3+hNjI*8Q9OWAKbkk$u*NJ;*$jQ>xz<tXU|BG#u<w!xAgYQErI;XXBY6L(G|6wVrSJ5y<tKM"
        b"+fi%z$!*0H7ZixYo9%Sy{>_i_2G!NFaSl#kK?#jBdHWJnAWdNckW8=1cwEA@$#vsPTq^T9O{CB|Koo6W"
        b"s#Qo&5NXcAHPtppCdATTtr~>Erza`ZFDHQFvcxFxcmWF<C2nBkuq#PjCAAt7jl7Owf&XJ)$WjDNK<zXT"
        b"C<njlCVq_TS^Hql<PEza$i9b6q%l}GzM<y+liv7o7E$mvSAN7ogTPEy9N~fGG?-8uL_HP5!?<g9k)*&G"
        b"$JKrW4b!$<bV6frLgPiwqHyv#0fO2F+Cirj_#JAQD{o{IWvN%%vb-4h8t1WRtRS?1J3Re(bn>2{_B)>w"
        b"@JC-jNH($$xTkdQ-TwQxpZ4D#ek2FK{|+!#g_I`#BEqEvx@sE+{V?=&h{6%u2U1osgp5D|5n$T{K-?h9"
        b"h~g5ysUiH-L|%;8@Ar=nNem9eg-_(*<oJ01{cF-fjdM47wO%RWuOVrOci^)KfY|DHgf5IM9CBCqLZ6Ju"
        b";w4%4imQKNts!RVa{oi?f6tO2%0o(iVkuY>1h=0*CpDrJNzP0C4fHqxcXL<g<x}O9Yy{sMksloL-HiMV"
        b"cL4r-It?i2<fosAb$FA3@M%aiAi&K4?lWL|S?qOJ?el3xTNx2{VEy&i2;uZ_|Ml^q8;31xczt+$GJY{7"
        b"`(em1+-ui|D!`;5X+}A?RN>xZBu#^dnP}hcfH#O^<8fmAuNPOVRf<M(@Jd8SA%z1o0vdW^<%7p;BINXH"
        b"4Bl2KZ}banv3FVR2Ca&^l(P$#e2vG<a<NkM=M6lS?^JU#po^us@ML;P6QDX3E={f&hlKKi0@wFHot=1Z"
        b"j(+!$1K!!mzYgCU$}7n8UZ^=>v!XQcqcQr>v0A~z43qKB$eoq*$eI!hGr;L&f{>+`1!~nK57t4LzE#!+"
        b"p-v6~W05DiF(z}K!US1rWj=T1lTug#c`@~XwXi}n$l*XueHApO517p&Ifpq1t($xRg%BM$Fv<WjPJp}H"
        b"-ZuM%{U}H7$=i$y7&^BOvdsGgT6Cryz<k|8vnVpzHXh@ckql&prF17t@f{sU8_yR=gJG<g-yDQAxQ%{T"
        b"D3hyQrA5eG1o`8dCR)CxeCe!>bP1-C5Lm^++!aYF%`k#w8jJ?NYo1_G*xv482J#MZG(PKSrh+%F4hYUo"
        b"+K9^kQJXkEzEY3PkZR56qb{~$q4Um=PRA?s21^fOHCp8qr!=CzFp~m!P5_pJ<Cu5W=%Yyam?45pB0TCJ"
        b"9FK7nGr=K<4(S7k4u(d`%?(kYi;r;%o7OecFldr0dc}-ly1NnOms}-={ZMymblo%D%VS;Nc!Gl1LR7`w"
        b"y`3gpO(WN};FUmiI4f&m7hdh6!nF&}<QAU8IO_nywnVk(P!mRwt(}J~kmxhd=ccgwBS%J<QSkq@K|j3m"
        b"lK`e`Zw>=*{76vk)3N4SK`ewS#Wq-`y25r(^{cA9iZ3FA(wSBzN0KJWYqu9E0U&iSXx$a{L&}8-6}enN"
        b"ocU7~<CaP)tXC8geoi`JVA|lTNg0|H+0S=&oe~V)18lQc7#x&~pQ=L1u*>zcj3%MIwC)O6h}Ek!T$4MT"
        b"u(q7~Ml@O=bOQ4xP`Am6G6L}+3Oh=)x3e=+jg{G5<wfo+hQGTzyI}oG$hgJoHHMZcDh}4lOVkb9dh(wq"
        b"@ssfE$uCcipL~4sr{%2Y>&6P3C`ZFN34)wMQ5VqvV+);+dQ1IQ)?9VaOLaqU2a{qG{GaZQ6!WGwK7$qv"
        b"7<f5RRe4j)ZFEtv2_8dxjuvjc**|*s>GW{Zgpf*bTxv#tQoIR)ao|Q3tlf5$Y<QX8k#3-9p?H{HPc%!v"
        b"k#3ZV-#@HKI)h~BNO7f^3=Pb=ri)MaWG9SXze_LNm5if*DD+3+4EH;L4bxwNy~EzTq64PQ`3hW~eyI|E"
        b"Fzu^Ayn-4eSiLvu$mvo{&_#-g$-39`-ZgrZ;gP}(z~NtfGn3b=-EZncT*AtVCS~S&Us3hf8bX*}Ltyj6"
        b"SEv<*jy#BA%B!nhY3X4II*!BFQ!?NVIy6A76bfu7+SWuDmtta(XZ4ct84#J}Q8X@MS-pX|fjSd&uCP%k"
        b"YC-44dXC*Q@ecIwgRf+U&As)#^fic>ym%NHf046zF<_{Y$%xjJX1`Jxk!RSMA2RWfih#3BYF)I-_CdNN"
        b"@;W8z00C5WXnMqw%MIQ^&}ezDF=&HWfj=1XTc(~96WrcJl}r;T<T|2Q53cbSdluzY{ESWZCQOK&PBh=Y"
        b"k%PIUx0S4iB(r2xC2IGICXZuZRi0L}Z&dc`o{_~p!Mm+JdnAi;L4F`063Dpk4g6J_aaU$2Cy<;D#s06B"
        b")zvQge~Er2i>TD$tTFL>@Kclrc$Oenc+!|ae!rwLSb?AyP`i-}$VkcJ)+GH<u@F;QggM7ImMp1C@Z1Js"
        b"b86En6{ekyZ0_&%%lN@fzhg~pK}bP1SLb?eqYqjC8$Ryp^1S%#Z6nrpwP8Z1wU`DuM#Opyyk0?6AmFbP"
        b"X|^CX;w>6}J*~d>#BTYBLE#&v4k-(Ci2B+xL6=Y-6wpE&rI2a1DFKhE5IX+dkG*IoNu8tMR@^X;GhuI>"
        b"wwd%H*MtXCCJv!)D^1_9p#~~?lSO{w8z*Hyc%qtowo=FW5k)0bIPfG|a$lu2=q_|eq_8%ZSdUv^Us)@W"
        b"DG`8PEN@AX_yN))p>iLN)OieNfSF=rZ2o#FmJ6A-rd2!9dV~Z^G^uJCSdEjUufdbh>js`@kH@oqF!cOk"
        b"h&Lm2?uGaUCG%hw+|Ge(Juux~Qjz%W;hEKqeUC`nYhA$&X}j);-C{ul?pwJjd=^E=&ow^GX?gV^<v5|M"
        b";oI8=T~BLNW#-TKdPd6ZxJ-gK<hhM}_W2%E#4VXLMOkA=(b>~`a2`|{?HU%h=L|I*pO+%h?Pu7<r-T+I"
        b"UZ^gNq`9Ql+MJ(Bep?A#-4@X}4<ZK4x50}h0*jNG{(PJUmuJN{+caq%hxmd7YDQCgWH2I&1%_vHfvMI`"
        b"HU~^2Gtn7U*Pbe<MRgO(fHm-cQMaSiSq?0MccrSSdaOiVyC7A;L{Z$2*tGfaJWd8~@n&PcQys<u!fs={"
        b"ZD0{i>|(0wChzvx*3iA4kcl9@qWl(~LY1RJ+7J?Y17R(?C9s|;y@~GAw)81aJcf2syW>^Ta=tTf?KV;e"
        b"0L9I)l0PGZXJiC9sxy2<vV0LiB2&9<Q>mx95{Bs1Ww1L-qXLaAa9YJ#%9PY7Gsm8ove?er={haMd|s3$"
        b"bJe6bgwW7>5QCSR!<cntGz8l>m%s23;Hl2ao{ox@p6ZpJ&YiW@E8&`jYati+xi;1m_sCvLT%%U9{%}hC"
        b"C8oM@vrg#JR1}>G154^22-thxC<y0|APOjm{NPe3Gb747-^jMwsWbih{ecet>RQ!S&#4$p893>?_x?Z+"
        b"uG)Qt&fv1%*}N+Ry->Z+r}OrCTaONwyZmleY9wNNC__&b2BKFaOek4lriyJtFlkd_b!FSks|pb}ZvaiI"
        b"+dm-sP*<nUBP0zL$d(MqFlg1aOo$pSdcG$gS)50xp`4Dvg;G_q7RJbp!sei+T>3yJ*fm3sHYHJ-UXnah"
        b"TUM9$aN>tkw-f6DoQ8!TF_=M<ZO!x^$(SkUR>mz*c5pb#MLgd_tL!z`$C&`GkOVAZy3jD#Kp<hBMJ&K$"
        b"u_jffO6pBnYUenaF9hv7_fa<$5F$0Vt@l41O?1R7?pwdqH?6@EAWg<Qo+={1vm7{wu&`r-$UGfF&?y@&"
        b"E=G`f*u~=#pA1;vsk3Uuc!vB64@d!YD9|Nc1D65q!=-(jS2|AJ1MzeN0g$&mY7YjzEQ&YBcz`ylh$;-W"
        b"X9{L?UXjsxMxZdMtt`Dh1~+S|JJGgM(Uyl&VFeSi0T*R*^J#hddtWM9-Oz42LZe}Nol&81txOvjDeYP_"
        b"z(C<myAVuww&(OFq&xar7|J-RC5l*WG%sF(4|@-Bs%cEMyI5J8_20!Bsd?4nG!lbYhVN-LsoDA;qoNl2"
    ),
    "053d650cf66563a277528a0e52ff1893d12bb3bed949088c064d998ad3e28603": (
        b"c-qZcZFAc;68`RAfwGecnMjoF=9(L&>Yd{_Y3|}U<2b$EIT{W{LKb3@U<uGK_2|FfE&#rhlAY^h&L1q2"
        b"SS%Kc-Dh_JSeA9NTt+ORM9}Pt1(Yn=jm$GDh@bI12}wr%h`eEPMBe$y#hc7eS0i$G>|aviL-XMo6_U^!"
        b"8sw7k#I-DIXJ?u5n0VeYM^2tcSe)`q0)4`zk7QzJ$9(%Dcv3ubQ9OwiaEr>fe3526ph9TQp)aXqF)jEO"
        b"@47Yh<tk!}qVWT~>V`jfLRqrpMazHS{VlwgvaF;`Z;bSQF1ZJ~a08w!*+tRkBbAaR7otVP5=k#IJ+*@L"
        b"C6kLhxTK)Df3VCSku&PYhfLnK`bJS)bUCG|&$444(x^pr&9lp8#IFm=f0_3YS^6wOEnm{x5xLHoq@L30"
        b"&Q3^|#Jgb9MvY9BB1YtipIwM45i)bg_-Fi`?hyEc70)9{W;JEIS)SOc5&zCDU}cSnH9my@&`+^-49EGX"
        b"Bn(zGxSXA3Ijw#3Q)LP~muW6rjgsE9KhY%MA?SH#<#IXxt5qY0bp|f8A9wXP$4C$C6Eg`{$Ph^2Cu6DY"
        b"7)`)rypYD+4p~M6$+KIn5~T)MKdlC~Bw(Y){@m*o3s$xj#9-}~LwMHLD8T`S8c}7=v=lz`nV{q}PjD7T"
        b"S;jNldId6p;J@b#oemsLyOnaVpJzX~`#+LvCRfBK3E0;aC5KO+l7Po4i)d!)>6cT2^(&uU;K!pYYCFZu"
        b"swR5FgcP=;#`2TfN+~WFPzG<d(~<jEKgt_YSHs3RfWU$h8mIF11(*Qm&;dlI*JL~{>DuDD@g)wG`Wa26"
        b"&^ADnY#!Gpq&o<nX8=vL$&m@M^jE7!Vfg7z%Jj<)V7M$X20UKCfX0X$95a}eq^?@E8WYXD&S8Q7V_(Q}"
        b"37Ui&G>|9<Ty+ya#__BJaA)$G-4ImYeLB(@yc^%pa{o?m{5Xv$pv{#ZvCuFuos~wiz;YT&s5PRUis5FQ"
        b"HM>YSXvT3hj-X@OmWv=X1`rxAau$V?&j|?BcF+zxWx(&y%3OIPn=DJa(w^nTpw~E$J>vzT{p-=`$G0c%"
        b"30lANIRQNS0*hp$`apZi_TC-5fAi_!&Cy44_}gzlV^vIP;x8f`N+49*(CCMur$ZFB*glA|iXmhKiim*P"
        b"CP3l_X-brq@J%)0rzZ2F#eRQqd_-aZ5Enj?!;|CVgZHmUi#7J$hHAa5h`&apA>9FH5g@VE?+77`EF5xI"
        b"V4+XOWbuNmdzY(!U~M60=yLu;<A2YRAj(5ZeqtOv34+_tpOczUN+jon{swlO0NmWwb@^C<l8xm1Bl3eo"
        b"zMGN1;0yr2r_+FD8TsiaVjbP2u=q42nh@w_K=&Cqy(s3or{?*%lC6vgyD<LxYZl@3=-}1yksF6CZ+LZd"
        b"d@_DMB?n>1Fx+eCLla<95T4QuAXT^<oTTaS&=dXJ9YBLPHi#4Be?7Pwtui!{11b?6g%l6W2x#bul@Ey7"
        b"WSG&bF`%tbX!HwAv3FPvgH|OS&)5Y^z6LSVT&$G*d4o@dovKd?axtC@Px4EefYe;LG`V6KB$O8vw0`jE"
        b"?8JNh_BRhT;GLcP^XR>iyrMksrJ4gbE8>A4jS)k~Y6KHAOvXDScUGQ7)|6P70Zu0qq%2Vuq*a|f7zb(k"
        b"Mp+w%IynT6MV{!!n9O;K6J)8C``ndJ%3uZL#nc1U!U)YEhYdCJRn(Y1U^a{59OW5U-Q)upgy_(LQwET6"
        b"0^Qw{CuY7d9|h!|yiKWqrgQ5sO}$TGMP~{C=Ia)lMUlz2`50hEF;E$nvYnLUI|4_W&lgC8p{?lOY=ktp"
        b"&3<@MCRcmPicq;o^7}PS^!l3er873lC74P=U=#~;R}`gm!w8aTa2ousb%H_R$&(&spze@I<Fk%tDtP1Q"
        b"z~J1ZjcEKIwTt89OZC_csn&cx>T)XvI`1^;bi873xb!eqtyNBON+aqE(<y-G1ZXn=j(KN{K8X~@3<+cs"
        b";Zc9%c#N%>2@X+oL?2*uIMh;3Zb$-Me2h6vTGvd&qzPB@iW$XpcPq;;xk?QCsqR$kx~I8U$GX1p1chY_"
        b"(G>UgcbjxIi(J=&R|3`HtgMAyc(scP*DjFBEs(>2bpT;oqS<Fq6Go7&orf%th?(beQ&|0;qasWz;D4>r"
        b"53l?rfbJU2q2aY3392z2YpxZ<La0(~!)2-~Z1+^Zs>-YQB2p-wX;pG0JW;6K9;76I)WNWISJV$_CQPWv"
        b"<qG1=AF3F)R8nERq>%7uq!R|F4ZWI_p(&C5Y<JHo$q*i3n#I5XP%eI|3MHd1*H2TLg!a<9D`+8BuXwm7"
        b"ci3TVIrWKXwjk&P`c0s2lN03x;$9MVjA(y%cceB}W_J~e+*u5N_jdQd`<IY$i`6R(EmJfctd*B&8@Bc6"
        b"-;d%);n|~K9vwgW_~;MIS<lyv5w=N=j&l+Oc?LyYK>vp+bUx}S^?O-!)IpT$hTaY*r6%}4-5V+8O>KMz"
        b"D;RL_vZJc<rkLC4qF@_6hV~pi+<JZR_T8t`qir2RDgn4ukN%{18v_I2#uTi*c9d+OOm9m!P_$Uw&#ot0"
        b"rQgUlO2hAORwA82GW1qyrI`#3^tq;sPaComMz7!T3wI^s=x>Vs+i-^S9pHxPufV;--n^nirrr4pAWy$k"
        b"2|u{@RUlqM4HB&08*|L)QcMsc#l&RY>v``OJ;w0B#SH-PFTR<}>(Ms5`jD2evZ6_uxo#?|{#-{0`85PK"
        b"KYWQ+QP{}66sAyJ?Uj}YLl8KQUQNjW9CT!WS}7E`ooHJVU0jNZMV{76#-|`;nn%&Nh-LK+%q`NHm~(|2"
        b"g`yU8p0DS)dnVq2{eAG&n&IZ&dZT;|Atul7C&r%y7S9J9RWcdTn$a9o1|#wmcjkv&JftGXSSqzGTIKcu"
        b"UlMuEi8??4QyuCavE*_KItUsqH#&oMh!x<$5N?@zPE2rm6IC)zppfe<#d>gzKN(pRs`x3J>`#~wIh|;|"
        b"e<Ogoq_@>t53S6SQI)7|T$((NeN}l{&3&VCukI;XYzW?M>)9u1lne3$fhB>Adt>0Q(u}(@Lpg!ubSU<J"
        b"^;%u+A^uCml{BJKhqFe<?*XT17T{TeT;WM$0{Q)t%3uWxy@1+{TtG%j7Pltphl+)m(jv?=d}GOysszt%"
        b"FgB+)tx{pynaKA2z5X@6_om;mmbMV25Ia-ndTwJMvi>)G+||{2@z=YJSew<B4xOz<9^@Di>oM?p1yO+j"
        b"UMJE_L2Tt)Z20wT^|d>8%SQ|f-zat9EYKn9Ys&;(LU~X?3+<Fb@^o7Q9#bK7{M*dE*iMo<N5QGMVIHT#"
        b"-r8-u=tIzi2U8{vp=~Qm-!h>FD|(Yge&QRDvhUqdbv|3E<NS!C5h@;d5-l@dr8Ni_dPk)2HkVir8{j~B"
        b"E0LTCU@w-pq)7aLX^~L5_h;%nL^GgFu{Ab-{VJ9NnQcw0cB1uw6)f3swPj#6PLjTcPeQL7e4aj>&-&if"
        b"^ZPO0&d}LN@eNAm!7R9)1K0Mz^!Ad9#BYwytZwXkK-ym072J}x>pihsENB3}6-?o?D0ci@gJG>6Tp)X_"
        b"NsAMzj=0sq{Z7xmD|8vyOWt@w)x)cHBGxw$l#gtA+tX%deQx1Bol{7u=jT{D%!ig%FG0XFoO0K*pFA-P"
        b"d!#5vP^Tl^abbxfA1l>E9nz<D{q|U^u5h01_q3E%Mp;a3sTUe`!Lxm9-99d9x<t*eiXBp|6X#wP=AJRt"
        b"cAue*+h?U|>ur3P#ixW8rE;h)-tb&fYi-UUWp-ORj=FWDc^*a#jM#=~ln5;HX8Q9n4=&G&Z?@U&b{ygh"
        b"5~v<cFO<QEEEbsNn2TVwZFzH0H!>ZaQFVQ+qFPip$_!b9{}*-3Or43rAb97j>Z;pH=CzAv6-^Yy{fy0V"
        b"37%`pz%AZv+&5N-n!vDoz|aP&h$eQ?Rqe{}^<dP{{iu+MfP*jI!c(YneMrATLT?~Fh;9jtXSOhi-tTVN"
        b"Q=WJX{jPRbu9W3`cix(9qz+Pw8+N6BMuyMGEaa%J@DWM#MFa_9?bcFdp5|&DvQwAp?kvp;EVAHf6=zaY"
        b"Qj^RaA7kogJ8P#4{>b^fDDmd%u)_#KL+f4&UTO_v_L|ZVeBWH6!^4!vI=g*5Dn@#&M|wPW)>iKd*F0P="
        b"a&a$iYi+h+?e&Ul)@rRkoDzSDB}3e-x4JSF#k=Cbk~#u`de0k$_51-sfdr8sTngo8L`At9*)}^BdFuBt"
        b"{x754vc5xnS1j~G?IAy&x6dtmY_Oc=ceBzWk=uP0da5`OJtAR3trcec7}UU}O{v-$xxJRPNZbgBb1hgQ"
        b"=EGJQbWFiMNXV%cjD>)YkQ3A;)XWD3Z6(r$EjF)wO{(i&Ft1Q=M>r1<7NCMH8AxN;s(ZK)-dgf}Pd>6Z"
        b"M+Je{W0(t7TNDLqWX7{{@TW}rASM71L+G87i1SO5r)uWvmL_)maO!rF93ZD*0eFTpER(IRqsN3ymvbx4"
        b"ibM(*?b$xUM=!2CcolgPu!!l((r|+X3G*~!0iJ_4r7~r4Z?0B5xJ!K@Xx~Afx|)I%++43e`0#e3LvwM#"
        b"{)N6;4=xLJ5nk$5p$nenz`>J+TV%-0)3FYthjF)}1(k=}wwc5yL)LfAK<&MGM*ND8N_SBo3J>eN3~3)P"
        b"4Z>cD@OsnB(>q4MyaoL|9Q3fbyg3Fg^im~M;j){%M3HB5P}A|=z|h0D&Q5rS6Yy*sVK2y{5-oMP-d3jH"
        b"f@l?2F(VzoXj9}(%WDLia_Q=-e=`yo%hltI3PWxcV6Z^auI(xrD!j6Z@HX3bdNcA}eZLTGC#q%2ShhBA"
        b"@BxUwhd|wQ(%PlIl&Afd`bMf>H8_pLAeZ3_e@$t2{tIcWxpV"
    ),
}


@pytest.fixture(params=tuple(HISTORICAL_DEMO_FIXTURES))
def historical_demo(request):
    data = zlib.decompress(base64.b85decode(HISTORICAL_DEMO_FIXTURES[request.param]))
    assert hashlib.sha256(data).hexdigest() == request.param
    assert b"Bearer local-demo-token" in data
    return data


def install_historical_demo(source, data):
    path = source / "implementation/demo.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["source_sha256"]["demo.py"] = sha(path)
    write_json(source / "manifest.json", manifest)


def test_historical_snapshot_export_preserves_exact_bytes_and_records_exception(
    run, tmp_path, historical_demo
):
    workspace, source = run
    install_historical_demo(source, historical_demo)
    destination = tmp_path / "artifact"
    index = evidence.export({"historical-dev_3": source}, destination, workspace=workspace)
    relative = "results/historical-dev_3/implementation/demo.py"
    expected = hashlib.sha256(historical_demo).hexdigest()
    assert (destination / relative).read_bytes() == historical_demo
    assert sha(destination / relative) == expected
    assert json.loads((destination / "SHA256SUMS.json").read_text())[relative] == expected
    exemptions = index["credential_scan_exemptions"]
    assert len(exemptions) == 1
    assert exemptions[0]["path"] == relative and exemptions[0]["sha256"] == expected
    assert exemptions[0]["scheme"] == "Bearer"
    assert exemptions[0]["synthetic_value"] == "local-demo-token"
    assert "exported bytes are unchanged" in exemptions[0]["reason"]
    assert (
        json.loads((destination / "index.json").read_text())["credential_scan_exemptions"]
        == exemptions
    )


@pytest.mark.parametrize(
    "label",
    [
        "results/dev/implementation/other.py",
        "results/dev/context/demo.py",
        "results/dev/nested/implementation/demo.py",
        "results/unsafe.name/implementation/demo.py",
        "results/dev/implementation/demo.py.json",
        "recordings/dev/implementation/demo.py",
    ],
)
def test_known_snapshot_bytes_receive_no_exception_at_other_paths(tmp_path, historical_demo, label):
    bundle = evidence.Bundle(tmp_path / "bundle", 64 * 1024)
    with pytest.raises(ValueError, match="credential"):
        bundle.write(label, historical_demo)
    assert not bundle.hashes and not bundle.scanner_exemptions


@pytest.mark.parametrize("change", ["append", "replace"])
def test_altered_snapshot_is_not_audited_even_at_exact_demo_path(tmp_path, historical_demo, change):
    data = (
        historical_demo + b"\n# Different bytes.\n"
        if change == "append"
        else historical_demo.replace(b"local-demo-token", b"another-demo-token")
    )
    bundle = evidence.Bundle(tmp_path / "bundle", 64 * 1024)
    with pytest.raises(ValueError, match="credential"):
        bundle.write("results/dev/implementation/demo.py", data)
    assert not bundle.hashes and not bundle.scanner_exemptions


def test_current_environment_secret_is_checked_before_known_literal_mask(
    tmp_path, historical_demo, monkeypatch
):
    # Even the audited fixture cannot hide a value treated as a live env secret.
    monkeypatch.setenv("CUSTOM_API_TOKEN", "local-demo-token")
    bundle = evidence.Bundle(tmp_path / "bundle", 64 * 1024)
    with pytest.raises(ValueError, match="credential") as error:
        bundle.write("results/dev/implementation/demo.py", historical_demo)
    assert "local-demo-token" not in str(error.value)
    assert not bundle.hashes and not bundle.scanner_exemptions


@pytest.mark.parametrize("extra", ["header", "json-field", "environment"])
def test_known_demo_exception_does_not_disable_other_evidence_credential_checks(
    run, tmp_path, historical_demo, monkeypatch, extra
):
    workspace, source = run
    install_historical_demo(source, historical_demo)
    call = source / "sample_case/model/call-1"
    if extra == "json-field":
        write_json(call / "response.json", {"token": "sensitive value"})
    else:
        value = "Bearer actual-private-token-123456" if extra == "header" else "private_env_value"
        (call / "stderr.log").write_text(value)
        if extra == "environment":
            monkeypatch.setenv("CUSTOM_API_TOKEN", value)
    destination = tmp_path / "artifact"
    with pytest.raises(ValueError, match="credential"):
        evidence.export({"dev": source}, destination, workspace=workspace)
    assert not destination.exists()
    assert not list(tmp_path.glob(".artifact-*"))
