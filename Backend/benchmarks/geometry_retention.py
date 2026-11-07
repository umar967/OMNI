"""Real Chrome regression fixtures with a deterministic permitted-view driver.

No LLM/API requests. Evaluation annotations are never passed to the driver.
This is instrumentation verification, not autonomous task-success measurement.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
from Backend.action_journal import ActionJournal, atomic_json
from Backend.action_safety import install_navigation_guard
from Backend.app.visual_evidence import capture_step
from Backend.explore_website import observe, execute, release
from Backend.persona_engine.perception_v1 import POLICY_VERSION
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.persona_engine.session import PerceptionSession
from Backend.task_outcomes import verify
from .contract import BenchmarkSuite
from .retention_metrics import exposure_sample, run_metrics

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://omni-retention.test/'


def fixture_html(kind):
    position = 'left:470px;top:40px;width:380px;height:60px;font-size:24px'
    if kind == 'dense':
        position = 'left:1280px;top:720px;width:70px;height:20px;font-size:12px'
    if kind == 'below_fold':
        position = 'left:470px;top:1200px;width:380px;height:60px;font-size:24px'
    disabled = 'disabled' if kind == 'disabled' else ''
    click = "document.querySelector('#menu').hidden=true;document.querySelector('#products').hidden=false"
    if kind == 'error_message':
        click = "document.querySelector('#feedback').textContent='Products are temporarily unavailable. Try later.'"
    buttons = f'<button id="open-catalog" {disabled} style="{position}" onclick="{click}">Open product listing</button>'
    if kind == 'dense':
        buttons += ''.join(f'<button style="left:{150+i%8*130}px;top:{140+i//8*85}px;width:110px;height:32px">Help topic {i}</button>' for i in range(1,40))
    return ('<html><head><title>Local catalog</title><style>button{position:absolute;white-space:nowrap}body{margin:0}</style></head>'
        '<body><div id="menu"><p>Browse available products using the listing control.</p>' + buttons +
        '</div><p id="feedback" style="position:absolute;top:110px"></p><section id="products" hidden>'
        '<h1 id="ready">Products</h1><article class="product"><span class="name">Arc Lamp</span></article>'
        '<article class="product"><span class="name">Studio Headphones</span></article></section>' +
        ('<div style="height:1600px"></div>' if kind == 'below_fold' else '') + '</body></html>')


def permitted_view_driver(persona, view, history):
    """Scripted policy probe, using only task text and permitted controls."""
    for c in view['controls']:
        if c.get('name') and c['name'].casefold() in persona['task'].casefold() and not c.get('disabled'):
            if not any(r['result']=='executed' and r['decision']['action']=='click' for r in history):
                return {'action':'click','target':c['id'],'value':'','reason':'Task label present'}
    if view.get('perception', {}).get('scan_available'):
        return {'action':'scan','target':-1,'value':'','reason':'Request more candidates'}
    scroll = view.get('scroll', {})
    if scroll.get('y', 0) + view.get('viewport', {}).get('height', 0) < scroll.get('height', 0)-2:
        return {'action':'scroll','target':-1,'value':'down','reason':'Inspect below viewport'}
    return {'action':'stop','target':-1,'value':'','reason':'No further scripted progress'}


def run_suite(manifest, output):
    suite = BenchmarkSuite.model_validate(manifest)
    if suite.policy_version != POLICY_VERSION:
        raise ValueError('Manifest must pin the running policy version.')
    source_files = ['persona_engine/perception_v1.py','persona_engine/text_policy.py','text_observations.py',
                    'persona_engine/session.py','persona_engine/schema.py','action_journal.py','action_safety.py',
                    'explore_website.py','task_outcomes.py','benchmarks/geometry_retention.py',
                    'benchmarks/retention_metrics.py','benchmarks/contract.py']
    summary = {'suite':suite.model_dump(), 'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files},
        'driver':'deterministic_permitted_view_probe', 'human_calibrated':False, 'runs':[]}
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        try:
            for case in suite.cases:
                for persona_id, config in suite.personas.items():
                    for mode in suite.modes:
                        name = f'{case.task_id}-{persona_id}-{mode}'
                        # Do not use arbitrary manifest identifiers as filesystem paths.
                        folder = output / hashlib.sha256(name.encode()).hexdigest()[:20]
                        folder.mkdir()
                        context = browser.new_context(viewport={'width':1366,'height':768})
                        install_navigation_guard(context, URL)
                        page = context.new_page()
                        html = fixture_html(case.fixture)
                        page.route(URL+'**', lambda route: route.fulfill(body=html,content_type='text/html'))
                        context.on('page', lambda popup: popup.close())
                        page.on('dialog', lambda dialog: dialog.dismiss())
                        session = PerceptionSession(resolve_persona(config, case.task.description), mode)
                        persona = agent_persona(resolve_persona(config, case.task.description))
                        journal = ActionJournal(folder/'history.json', [])
                        samples, timings = [], []
                        event = 'initial'
                        error = None
                        try:
                            page.goto(URL, wait_until='domcontentloaded')
                            for step in range(1,suite.max_actions+1):
                                start = time.perf_counter()
                                raw, handles = observe(page)
                                try:
                                    observation_ms = (time.perf_counter()-start)*1000
                                    start = time.perf_counter()
                                    perceived = session.perceive(raw)
                                    timings.append({'observation_ms':round(observation_ms,3), 'policy_ms':round((time.perf_counter()-start)*1000,3)})
                                    samples.append(exposure_sample(raw,perceived,case.targets,handles,event,page))
                                    decision = session.decide(permitted_view_driver,persona,perceived,journal.history)
                                    row = journal.begin(step,raw,decision,round(time.monotonic()-journal.started,2))
                                    session.record_before(journal,row,perceived)
                                    journal.capture(row,page,folder,'before',capture_step)
                                    result = session.execute(journal,row,perceived,execute,page,handles,URL)
                                    page.wait_for_timeout(150)
                                    journal.observe_after(row,page,observe,release)
                                    session.record_after(journal,row)
                                    journal.capture(row,page,folder,'after',capture_step)
                                    outcome = verify(page,case.task,step=step)
                                    if outcome.task_outcome=='verified_complete' or decision['action']=='stop' or result=='outcome_unknown':
                                        break
                                    event = decision['action']
                                finally:
                                    release(handles)
                        except Exception as exc:
                            error = type(exc).__name__ + ': ' + str(exc)
                        outcome = verify(page,case.task,step=len(journal.history) or None,final=True)
                        saved_history = json.loads((folder/'history.json').read_text(encoding='utf-8')) if (folder/'history.json').exists() else []
                        metrics = run_metrics(samples,saved_history,outcome,folder)
                        run = {'case':case.task_id,'persona':persona_id,'mode':mode,'split':case.split,
                               'folder':folder.name,'error':error,'metrics':metrics,'timings':timings,
                               'policy':session.report(journal.history)}
                        atomic_json(folder/'verification.json',outcome.model_dump())
                        atomic_json(folder/'exposure.json',samples)
                        atomic_json(folder/'metrics.json',run)
                        summary['runs'].append(run)
                        atomic_json(output/'summary.json',summary)
                        context.close()
                        print(json.dumps({'case':case.task_id,'persona':persona_id,'mode':mode,'metrics':metrics,'error':error}),flush=True)
        finally:
            browser.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).with_name('fixtures')/'retention_v1.json')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    output = args.output or ROOT/'results'/('retention_b1_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    result = run_suite(json.loads(args.manifest.read_text(encoding='utf-8')),output)
    print('Results: ' + str(output/'summary.json'))
    if any(r['error'] or not r['metrics']['annotations_valid'] for r in result['runs']):
        raise SystemExit(1)


if __name__=='__main__':
    main()
