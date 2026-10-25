"""Exercise the shipped refresh function without adding a JavaScript test dependency."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_selected_run_outside_the_history_page_refreshes_without_reloading_artifacts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser's refresh function")
    page = Path(__file__).parents[1] / "src/auto_fix/dashboard.html"
    script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const start=html.indexOf('async function refresh() {');
const end=html.indexOf('\nif(state.selected)',start);
let reads=0;
const state={selected:'runs/off-page',runs:[],tab:'overview',detail:{summary:{updated:'old'}}};
const context={state,loadRuns:async()=>false,loadJobs:async()=>false,
  loadSchedules:async()=>false,loadBatches:async()=>false,
  loadDetail:async()=>{reads++;},busy:()=>false,tickClocks:()=>{},showFreshness:()=>{}};
vm.createContext(context);vm.runInContext(html.slice(start,end),context);
(async()=>{
  await context.refresh();
  assert.equal(reads,1,'A direct link or attention-selected run must keep polling off-page');
  state.tab='files';await context.refresh();
  assert.equal(reads,1,'Open artifact previews must not be replaced by polling');
  state.tab='overview';state.runs=[{id:'runs/off-page',status:'ready',updated:'old'}];
  await context.refresh();assert.equal(reads,1,'An unchanged visible terminal run needs no reload');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script, str(page)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_home_navigation_from_global_views_updates_browser_history():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser's navigation function")
    page = Path(__file__).parents[1] / "src/auto_fix/dashboard.html"
    script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const start=html.indexOf('async function openWorkflow(');
const end=html.indexOf('\nasync function loadRuns()',start);
(async()=>{
  for(const view of ['schedules','batches','history']) {
    const entries=[],state={workflow:null,selected:null,view,history:{}};
    const context={state,history:{pushState:(_,__,url)=>entries.push(url)},historyHash:()=>'',
      document:{getElementById:()=>({scrollTop:0})},loadRuns:async()=>false,renderSidebar:()=>{},renderHome:()=>{}};
    vm.createContext(context);vm.runInContext(html.slice(start,end),context);
    await context.openWorkflow(null);
    assert.deepEqual(entries,['#'],'Home from '+view+' must have its own browser-history entry');
    assert.equal(state.view,null);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script, str(page)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_diff_model_parses_files_pairs_lines_marks_words_and_highlights_cpp():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser's diff functions")
    page = Path(__file__).parents[1] / "src/auto_fix/dashboard.html"
    script = r"""
// Loose asserts: arrays made inside the vm context have that context's prototypes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert');
const html=fs.readFileSync(process.argv[1],'utf8');
const start=html.indexOf('/* ---------- diff model');
const end=html.indexOf('/* ---------- diff view',start);
const context={};vm.createContext(context);vm.runInContext(html.slice(start,end)+
  ';Object.assign(globalThis,{parseDiff,pairRows,wordRanges,lexLine,annotate});',context);
const {parseDiff,pairRows,wordRanges,lexLine,annotate}=context;
const diff=[
  'diff --git a/src/add.cc b/src/add.cc','index 1..2 100644','--- a/src/add.cc','+++ b/src/add.cc',
  '@@ -10,4 +10,3 @@ int Add(int a, int b) {','   // sum','--- not a header, a removed line',
  '-  return a - b;','+  return a + b;',' }',
  'diff --git a/old.h b/new.h','similarity index 100%','rename from old.h','rename to new.h',
  'diff --git a/n.txt b/n.txt','new file mode 100644','--- /dev/null','+++ b/n.txt','@@ -0,0 +1 @@',
  '+hello',String.fromCharCode(92)+' No newline at end of file',''].join('\n');
const files=parseDiff(diff);
assert.deepEqual(files.map(f=>[f.path,f.status,f.add,f.del]),
  [['src/add.cc','modified',1,2],['new.h','renamed',0,0],['n.txt','added',1,0]]);
const hunk=files[0].hunks[0];
assert.equal(hunk.context,'int Add(int a, int b) {');
assert.deepEqual(hunk.lines.map(l=>[l.kind,l.old,l.new]),
  [['ctx',10,10],['del',11,undefined],['del',12,undefined],['add',undefined,11],['ctx',13,12]]);
assert.equal(files[2].hunks[0].lines.at(-1).kind,'note');
const rows=pairRows(hunk.lines);
assert.equal(rows.length,4);
assert.equal(rows[1].left.text,'-- not a header, a removed line');
assert.equal(rows[1].right.text,'  return a + b;');
assert.equal(rows[2].right,null);
assert.deepEqual(wordRanges('return a - b;','return a + b;'),[[[9,10]],[[9,10]]]);
assert.equal(wordRanges('abc','xyz'),null);
const lexed=lexLine('if (x) return Foo("s", 3); // done /*','cpp');
assert.deepEqual(lexed.runs.map(r=>r[2]),['kw','kw','fn','str','num','com']);
const open=lexLine('int a; /* begins','cpp');
assert.equal(open.open,true);
assert.deepEqual(lexLine('still */ int b;','cpp',true).runs.map(r=>r[2]),['com','kw']);
assert.equal(lexLine('x = 1','').runs.length,0);
const one='--- a/x.cc\n+++ b/x.cc\n@@ -1 +1 @@\n-int a = 1;\n+int a = 2;\n';
const marked=annotate(parseDiff(one)[0]);
assert.deepEqual(marked.hunks[0].lines.map(l=>l.changed),[[[8,9]],[[8,9]]]);
const bare=parseDiff('-return a - b;\n+return a + b;\n')[0];
assert.deepEqual([bare.path,bare.add,bare.del,bare.hunks[0].lines[0].old],['patch',1,1,undefined]);
"""
    result = subprocess.run(
        [node, "-e", script, str(page)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_tour_picks_an_example_for_each_situation_and_none_when_missing():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser's tour functions")
    page = Path(__file__).parents[1] / "src/auto_fix/dashboard.html"
    script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert');
const html=fs.readFileSync(process.argv[1],'utf8');
const start=html.indexOf('function tourExamples(');
const end=html.indexOf('\nconst runHash',start);
const context={};vm.createContext(context);
vm.runInContext(html.slice(start,end)+';globalThis.tourExamples=tourExamples;',context);
const runs=[
  {id:'a',status:'blocked',regressions:1,live:false},{id:'b',status:'ready',regressions:0},
  {id:'c',status:'in_progress',live:true},{id:'d',status:'in_progress',live:false},
  {id:'e',status:'publication_unknown'},{id:'f',status:'ready'}];
const tests=[{name:'t',not_reproduced:0},{name:'u',not_reproduced:2}];
const x=context.tourExamples(runs,[runs[5]],tests);
// A ready run that needs attention comes first; a live run is never "abandoned".
assert.deepEqual([x.ready.id,x.regression.id,x.abandoned.id,x.unknown.id,x.flaky.name],['f','a','d','e','u']);
const none=context.tourExamples([{id:'g',status:'published',regressions:0}],[],[]);
assert.deepEqual([none.ready,none.regression,none.abandoned,none.unknown,none.flaky],[null,null,null,null,null]);
"""
    result = subprocess.run(
        [node, "-e", script, str(page)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_trace_nests_calls_and_checks_under_the_steps_that_made_them():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser's trace functions")
    page = Path(__file__).parents[1] / "src/auto_fix/dashboard.html"
    script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert');
const html=fs.readFileSync(process.argv[1],'utf8');
const part=(from,to)=>{
  const i=html.indexOf(from),j=html.indexOf(to,i);
  assert.ok(i>=0&&j>i,from);
  return html.slice(i,j);
};
const context={state:{traceOpen:new Map()}};vm.createContext(context);
vm.runInContext([
  part('const STATUS = {','// Deep links'),
  part('/* ---------- test reports','/** Failing tests at the baseline'),
  part('function tokens(','function renderResponse('),
  part('function stepStatus(','/** Why an attempt produced no edit'),
  part('function buildLabel(','/** The compiler and test-runner output'),
  'const flowTone = step => stepStatus(step).tone;',
  part('/* ---------- trace:','function selectSpan('),
  ';Object.assign(globalThis,{traceTree,walkSpans,defaultSpan,spanOpen,legacySpan,callsIn});',
].join('\n'),context);
const {traceTree,walkSpans,defaultSpan,spanOpen,legacySpan,callsIn}=context;
const t=m=>`2026-10-25T19:${String(m).padStart(2,'0')}:00Z`;
const step=(index,node,status,a,b)=>({index,node,status,started:t(a),changes:{},
  ended:b===null?null:t(b),duration_seconds:b===null?null:(b-a)*60});
// A repair that made no usable edit, then a second repair that passes:
// call 2 starts the moment the first repair ends.
const steps=[step(0,'collect_context','working',0,1),step(1,'prepare','working',1,2),
  step(2,'baseline','working',2,9),step(3,'repair','invalid_proposal',9,10),
  step(4,'repair','working',10,11),step(5,'verify','validated',11,18),
  step(6,'finalize','ready',18,25),step(7,'publish_pr','ready',25,25)];
const call=(index,a,usage,error=null)=>({file:`model-calls/0${index}-repair.json`,index,
  kind:'repair',model:'m',started:t(a),elapsed_seconds:60,usage,error});
const build=(label,folder)=>({label,folder:'evidence/'+folder,time:t(30),files:[]});
const detail={steps,
  summary:{name:'tc-1',status:'ready',live:false,duration_seconds:1500,started:t(0),tests:['T']},
  model_calls:[call(1,9,{prompt_tokens:100,completion_tokens:20},'ValueError: cut off'),
    call(2,10,{input_tokens:50,output_tokens:5})],
  builds:[build('baseline','baseline-aaaaaaaaaaaa'),build('attempt-2','attempt-2-bbbbbbbbbbbb'),
    build('final-rebased','final-rebased-cccccccccccc')]};
const root=traceTree(detail);
const shape=span=>span.children.length?[span.id,span.children.map(shape)]:span.id;
assert.deepStrictEqual(JSON.parse(JSON.stringify(shape(root))),['run',[
  ['phase:Setup',['step:0','step:1']],
  ['phase:Baseline',[['step:2',['build:evidence/baseline-aaaaaaaaaaaa']]]],
  ['phase:Attempt 1',[['step:3',['call:model-calls/01-repair.json']]]],
  ['phase:Attempt 2',[['step:4',['call:model-calls/02-repair.json']],
    ['step:5',['build:evidence/attempt-2-bbbbbbbbbbbb']]]],
  ['phase:Finish',[['step:6',['build:evidence/final-rebased-cccccccccccc']],'step:7']]]]);
const by=Object.fromEntries(walkSpans(root).map(({span})=>[span.id,span]));
assert.equal(root.tokens,175);
assert.equal(by['phase:Attempt 1'].tokens,120);
assert.equal(by['phase:Attempt 1'].tone,'warn');
assert.equal(by['phase:Setup'].tone,'ok');
assert.equal(by['step:4'].visit,2);
assert.equal(callsIn(detail,[steps[3]]).length,1,
  'A call that starts as a step ends belongs to the next step only');
// The trace opens on the last attempt's check; attempts unfold,
// and phases that went well stay folded.
assert.equal(defaultSpan(detail),'step:5');
assert.equal(spanOpen(by['phase:Setup']),false);
assert.equal(spanOpen(by['phase:Attempt 1']),true);
context.state.traceOpen.set('phase:Setup',true);
assert.equal(spanOpen(by['phase:Setup']),true);
// An interrupted step never ended: its phase does not count up to now,
// and the trace opens on it.
const cut={...detail,summary:{...detail.summary,status:'in_progress'},builds:[],
  steps:[...steps.slice(0,6),step(6,'finalize','interrupted',18,null)]};
const finish=walkSpans(traceTree(cut)).find(({span})=>span.id==='phase:Finish').span;
assert.equal(finish.seconds,null);
assert.equal(finish.tone,'bad');
assert.equal(defaultSpan(cut),'step:6');
const link=hash=>JSON.parse(JSON.stringify(legacySpan(new URLSearchParams(hash))));
assert.deepStrictEqual(link('run=r&tab=log&open=4,6'),{tab:'overview',span:'step:4'});
assert.deepStrictEqual(link('run=r&tab=calls&call=model-calls/01-repair.json'),
  {tab:'overview',span:'call:model-calls/01-repair.json'});
assert.deepStrictEqual(link('run=r&tab=calls'),{tab:'overview',span:null});
assert.deepStrictEqual(link('run=r&tab=files&file=x'),{tab:'files',span:null});
assert.deepStrictEqual(link('run=r&span=build:x'),{tab:'overview',span:'build:x'});
"""
    result = subprocess.run(
        [node, "-e", script, str(page)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
