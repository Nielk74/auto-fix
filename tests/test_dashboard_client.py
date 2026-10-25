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
