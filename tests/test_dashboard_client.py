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
  loadDetail:async()=>{reads++;},busy:()=>false,tickClocks:()=>{}};
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
