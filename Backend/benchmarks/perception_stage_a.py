"""Small matched Stage A comparison: real Chrome + installed local Ollama only.

Not a human calibration or pilot-readiness benchmark. No model downloads, paid
API calls, or review-model calls. All tested pages are fulfilled from local HTML.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright
from Backend.action_journal import ActionJournal, atomic_json
from Backend.action_safety import install_navigation_guard
from Backend.agents.local_persona import next_action
from Backend.agents.exploration_agent import request_ollama
from Backend.app.visual_evidence import capture_step
from Backend.explore_website import observe, execute, release
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.persona_engine.session import PerceptionSession
from Backend.task_outcomes import TaskContract, verify

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://omni-perception.test/'


def fixture_html(peripheral=False):
    position = 'left:1280px;top:720px;width:70px;height:20px;font-size:12px' if peripheral else 'left:470px;top:32px;width:380px;height:70px;font-size:24px'
    buttons = [f'<button style="{position}" onclick="document.querySelector(\'#menu\').hidden=true;document.querySelector(\'#products\').hidden=false">Open product listing</button>']
    for i in range(1, 40):
        buttons.append(f'<button style="left:{150+i%8*130}px;top:{140+i//8*85}px;width:110px;height:32px">Help topic {i}</button>')
    return '<html><head><title>Local catalog fixture</title><style>button{position:absolute;white-space:nowrap}body{margin:0}</style></head><body><div id="menu">' + ''.join(buttons) + '</div><section id="products" hidden><h1 id="ready">Products</h1><article class="product"><span class="name">Arc Lamp</span></article><article class="product"><span class="name">Studio Headphones</span></article></section></body></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen3:4b')
    parser.add_argument('--max-actions', type=int, default=2, choices=range(1,4))
    parser.add_argument('--timeout-seconds', type=int, default=60)
    args = parser.parse_args()
    os.environ.update(OLLAMA_MODEL=args.model, OLLAMA_TIMEOUT_SECONDS=str(args.timeout_seconds), OLLAMA_MAX_ATTEMPTS='1')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    root = ROOT/'results'/('exploration_stage_a_' + stamp)
    root.mkdir(parents=True)
    contract = TaskContract(description='Open the product listing and observe products.', endpoint={
        'strategy':'product_listing', 'expected_url':URL, 'container_selector':'#products',
        'ready_selector':'#ready', 'item_selector':'.product', 'name_selector':'.name', 'complete_collection':True})
    summary = {'at':datetime.now(timezone.utc).isoformat(), 'provider':'local_ollama', 'model':args.model,
               'human_calibrated':False, 'max_actions':args.max_actions, 'timeout_seconds':args.timeout_seconds,
               'limitations':['One run per scenario/mode; stochastic decisions and cold/warm inference times are not controlled.',
                   'Local synthetic UI, shared runner infrastructure; no dashboard UI automation or model review benchmark.',
                   'This measures scenario behavior and implementation wiring, not human attention or expertise.'], 'runs':[]}
    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        try:
            for peripheral in (False, True):
                modes = ('provisional_pilot_v1','neutral_passthrough') if peripheral else ('neutral_passthrough','provisional_pilot_v1')
                for mode in modes:
                    name = ('peripheral' if peripheral else 'prominent') + '-' + mode
                    folder = root/name
                    folder.mkdir()
                    context = browser.new_context(viewport={'width':1366,'height':768})
                    install_navigation_guard(context, URL)
                    page = context.new_page()
                    html = fixture_html(peripheral)
                    page.route(URL + '**', lambda route: route.fulfill(body=html, content_type='text/html'))
                    page.on('dialog', lambda dialog: dialog.dismiss())
                    runtime = resolve_persona({'profile':{'name':'Benchmark visitor','technical_experience':'beginner'}}, contract.description)
                    session = PerceptionSession(runtime, mode)
                    journal = ActionJournal(folder/'history.json', [])
                    journal.flush()
                    metrics = {'scenario':name, 'mode':mode, 'model_seconds':[], 'policy_ms':[], 'decisions':[]}
                    print(f'RUN {name}', flush=True)
                    try:
                        page.goto(URL, wait_until='domcontentloaded')
                        for number in range(1, args.max_actions+1):
                            before, handles = observe(page)
                            try:
                                started = time.perf_counter()
                                perceived = session.perceive(before)
                                metrics['policy_ms'].append(round((time.perf_counter()-started)*1000, 3))
                                if number == 1:
                                    metrics.update(target_retained=0 in perceived.allowed_targets, **perceived.diagnostics)
                                started = time.perf_counter()
                                try:
                                    decision = session.decide(lambda persona, view, history: next_action(persona, view, history, request_ollama),
                                                              agent_persona(runtime), perceived, journal.history)
                                finally:
                                    metrics['model_seconds'].append(round(time.perf_counter()-started, 3))
                                row = journal.begin(number, before, decision, round(time.monotonic()-journal.started, 2))
                                session.record_before(journal, row, perceived)
                                journal.capture(row, page, folder, 'before', capture_step)
                                result = session.execute(journal, row, perceived, execute, page, handles, URL)
                                metrics['decisions'].append({'action':decision.get('action'), 'target':decision.get('target'), 'result':result})
                                journal.observe_after(row, page, observe, release)
                                session.record_after(journal, row)
                                journal.capture(row, page, folder, 'after', capture_step)
                                outcome = verify(page, contract, step=number)
                                if outcome.task_outcome == 'verified_complete' or decision.get('action') == 'stop' or result == 'outcome_unknown':
                                    break
                            finally:
                                release(handles)
                    except Exception as exc:
                        metrics['error'] = f'{type(exc).__name__}: {exc}'
                    outcome = verify(page, contract, step=len(journal.history) or None, final=True)
                    metrics.update(task_outcome=outcome.task_outcome, policy=session.report(journal.history))
                    atomic_json(folder/'verification.json', outcome.model_dump())
                    atomic_json(folder/'metrics.json', metrics)
                    summary['runs'].append(metrics)
                    atomic_json(root/'comparison.json', summary)
                    context.close()
                    print(json.dumps({k:v for k,v in metrics.items() if k != 'policy'}), flush=True)
        finally:
            browser.close()
    print(f'Results: {root / "comparison.json"}', flush=True)


if __name__ == '__main__':
    main()
