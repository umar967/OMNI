"""Bounded live exploration with a first-time-user persona."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from Backend.flow_coverage import assess_flows
from Backend.agents.gemini_requests import ModelRequestError

ROOT = Path(__file__).resolve().parent
SELECTOR = ('button, a[href], input:not([type="hidden"]), textarea, select, '
            '[role="button"], [role="link"], [role="tab"], [role="checkbox"], '
            '[role="radio"], [contenteditable="true"]')
RESTRICTED = re.compile(r'\b(check\s*out|place order|pay|buy now|purchase|subscribe|send|'
                        r'delete|sign\s*up|register|create account|log\s*in|sign\s*in|submit)\b', re.I)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def observe(page):
    handles, controls = {}, []
    open_dialog = page.query_selector('dialog[open]')
    control_scope = open_dialog if open_dialog else page
    for element in control_scope.query_selector_all(SELECTOR):
        data = element.evaluate('''el => {
            const r = el.getBoundingClientRect(), s = getComputedStyle(el);
            if (!r.width || !r.height || s.visibility === 'hidden' ||
                s.display === 'none' || r.bottom <= 0 || r.top >= innerHeight ||
                r.right <= 0 || r.left >= innerWidth) return null;
            const labels = [...(el.labels || [])].map(x => x.innerText).join(' ');
            const labelled = (el.getAttribute('aria-labelledby') || '').split(' ')
                .map(id => document.getElementById(id)?.innerText || '').join(' ');
            return {tag: el.tagName.toLowerCase(), type: el.type || '',
                name: el.getAttribute('aria-label') || labelled.trim() || labels ||
                      el.innerText?.trim() || el.getAttribute('placeholder') || '',
                disabled: el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true',
                value: el.type === 'password' ? '[redacted]' : (el.value || ''),
                checked: el.checked ?? null,
                options: el.tagName === 'SELECT' ? [...el.options].map(o =>
                    ({text: o.text, value: o.value})) : []};
        }''')
        if data is None:
            element.dispose()
            continue
        index = len(controls)
        data['id'] = index
        controls.append(data)
        handles[index] = element
    text = page.evaluate('''() => {
       const visible_scope = document.querySelector('dialog[open]') || document.body;
       const walker = document.createTreeWalker(visible_scope, NodeFilter.SHOW_TEXT);
        const chunks = []; let node;
        while (node = walker.nextNode()) {
            if (!node.textContent.trim() || ['SCRIPT','STYLE','NOSCRIPT'].includes(node.parentElement.tagName)) continue;
            const range = document.createRange(); range.selectNodeContents(node);
            const r = range.getBoundingClientRect(), s = getComputedStyle(node.parentElement);
            if (r.width && r.height && r.bottom > 0 && r.top < innerHeight &&
                r.right > 0 && r.left < innerWidth && s.visibility !== 'hidden' &&
                s.display !== 'none') chunks.push(node.textContent.trim());
        }
        return chunks.join('\\n');
    }''')
    return {'url': page.url, 'visible_text': text, 'controls': controls,
            'scroll': page.evaluate('() => ({x: scrollX, y: scrollY, height: document.documentElement.scrollHeight})')}, handles


def release(handles):
    for handle in handles.values():
        try:
            handle.dispose()
        except Exception:
            pass  # Navigation may already have destroyed the document.


def execute(page, decision, observation, handles, home):
    action, value = decision.get('action'), decision.get('value', '')
    if action == 'scroll':
        if value not in {'up', 'down'}:
            raise ValueError('Scroll value must be up or down')
        page.mouse.wheel(0, (1 if value == 'down' else -1) * 550)
        return 'executed'
    if action == 'back':
        page.go_back(wait_until='domcontentloaded')
        return 'executed'
    if action == 'home':
        page.goto(home, wait_until='domcontentloaded')
        return 'executed'
    if action == 'wait':
        page.wait_for_timeout(1500)
        return 'executed'
    if action == 'press' and value == 'Escape':
        page.keyboard.press('Escape')
        return 'executed'
    if action not in {'click', 'fill', 'select', 'check', 'hover', 'press'}:
        raise ValueError(f'Unsupported action: {action}')
    index = decision.get('target')
    if type(index) is not int or index not in handles:
        raise ValueError('Target was not in the current observation')
    control = next(c for c in observation['controls'] if c['id'] == index)
    element = handles[index]
    if control['disabled']:
        return 'blocked: disabled control'
    if action == 'click':
        # Account links may be opened for inspection; their submissions stay blocked.
        account_link = control['tag'] == 'a' and re.search(
            r'\b(log\s*in|sign\s*in|sign\s*up|register|create account)\b', control['name'], re.I)
        if RESTRICTED.search(control['name']) and not account_link:
            return 'blocked: account/submission/checkout boundary, not a website defect'
        submit = element.evaluate('''el => !!el.form &&
            ((el.tagName === 'BUTTON' && el.type === 'submit') ||
             (el.tagName === 'INPUT' && ['submit','image'].includes(el.type)))''')
        if submit and not re.search(r'\bsearch\b', control['name'], re.I):
            return 'blocked: form submission requires a dedicated test setup'
    if action == 'fill' and control['type'] in {'password', 'file', 'hidden'}:
        return 'blocked: credential/file input outside this exploration'
    if action == 'press':
        if value != 'Enter' or control['tag'] != 'input' or not (
            control['type'] == 'search' or re.search(r'\bsearch\b', control['name'], re.I)
        ):
            return 'blocked: Enter is only enabled on identified search inputs'
    element.scroll_into_view_if_needed()
    element.evaluate('''el => {
        const old = el.style.outline; el.style.outline = '3px solid #e8790b';
        setTimeout(() => {el.style.outline = old;}, 800);
    }''')
    box = element.bounding_box()
    if box:
        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=12)
    page.wait_for_timeout(500)
    if action == 'click':
        element.click(timeout=6000)
    elif action == 'hover':
        element.hover(timeout=6000)
    elif action == 'fill':
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError('Fill requires at most 500 characters')
        element.fill(value, timeout=6000)
    elif action == 'select':
        element.select_option(value=value, timeout=6000)
    elif action == 'check':
        if value not in {'true', 'false'}:
            raise ValueError('Check value must be true or false')
        element.set_checked(value == 'true', timeout=6000)
    elif action == 'press':
        element.press('Enter', timeout=6000)
    return 'executed'


def coverage(history, catalog):
    observed, attempted = set(), set()
    for row in history:
        for state in (row['before'], row['after']):
            observed.update((state['url'], c['tag'], c['name']) for c in state['controls'])
        for c in row['before']['controls']:
            if c['id'] == row['decision'].get('target'):
                attempted.add((row['before']['url'], c['tag'], c['name']))
    return {'pages_observed': sorted({s['url'] for r in history for s in (r['before'], r['after'])}),
            'areas_attempted': sorted({r['decision'].get('area', 'Unknown') for r in history}),
            'flows': assess_flows(history, catalog),
            'observed_controls_not_targeted': [list(c) for c in sorted(observed - attempted)],
            'note': 'Configured flows show observed states after matching actions; this is not proof of whole-site coverage or human usability.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5173/')
    parser.add_argument('--max-actions', type=int, default=40)
    parser.add_argument('--provider', choices=['gemini', 'ollama'], default='gemini')
    parser.add_argument('--model', help='Ollama model name, such as qwen3:4b')
    parser.add_argument('--flows', type=Path, default=ROOT / 'flow_catalog.json',
                        help='JSON catalog of site flows to track; does not direct the persona')
    parser.add_argument(
    '--resume',
    type=Path,
    help='Continue an existing exploration folder from its saved history',)
    args = parser.parse_args()
    if args.max_actions < 1 or urlparse(args.url).scheme not in {'http', 'https'}:
        parser.error('Use an HTTP(S) URL and a positive action limit')
    os.environ['OMNI_MODEL_PROVIDER'] = args.provider
    if args.model:
        os.environ['OLLAMA_MODEL' if args.provider == 'ollama' else 'GEMINI_MODEL'] = args.model
    from Backend.agents.exploration_agent import apply_review, clean_review, explore_next, review_run
    if args.resume:
        run_dir = args.resume.resolve()
        results_dir = (ROOT / 'results').resolve()

        if run_dir.parent != results_dir or not run_dir.name.startswith('exploration_'):
            parser.error('--resume must point to an exploration folder inside results')

        required = ['persona.json', 'flow_catalog.json', 'history.json',
                    'report.json', 'browser_state.json']
        missing = [name for name in required if not (run_dir / name).is_file()]
        if missing:
            parser.error('Cannot resume: missing ' + ', '.join(missing))

        persona = json.loads((run_dir / 'persona.json').read_text(encoding='utf-8'))
        catalog = json.loads((run_dir / 'flow_catalog.json').read_text(encoding='utf-8'))
        history = json.loads((run_dir / 'history.json').read_text(encoding='utf-8'))
        previous_report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
        events = previous_report.get('events', [])

        if not history:
            parser.error('Cannot resume a run with no recorded actions')
        if len(history) >= args.max_actions:
            parser.error('--max-actions must be greater than the saved action count')

        args.url = history[0]['before']['url']
    else:
        persona = json.loads(
            (ROOT / 'personas/first_time_user.json').read_text(encoding='utf-8')
        )
        catalog = json.loads(args.flows.read_text(encoding='utf-8'))
        run_dir = ROOT / 'results' / (
            'exploration_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        )
        run_dir.mkdir(parents=True)
        save(run_dir / 'persona.json', persona)
        save(run_dir / 'flow_catalog.json', catalog)
        history, events = [], []
        save(run_dir / 'report.json', {
            'persona': persona['name'], 'run_status': 'running',
            'review_status': 'not_completed', 'actions_recorded': 0,
            'findings': [],
            'persona_feedback': None,
            'feedback_type': 'simulated_persona_experience',
            'note': 'Persona experience review has not run yet.',
        })
    stop_reason = 'Action limit reached; remaining areas are untested.'
    model_failed = False
    started = time.monotonic()
    print(f"Persona: {persona['name']} | Provider: {args.provider} | Limit: {args.max_actions} actions\nResults: {run_dir}", flush=True)
    print('Each decision calls the chosen model. Ctrl+C stops exploration and saves progress.', flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, timeout=15000)
        context_options = {'viewport': {'width': 1366, 'height': 768}}
        if args.resume:
            context_options['storage_state'] = str(run_dir / 'browser_state.json')
            print(f'Resuming after step {history[-1]["step"]} from the last recorded page.',
                  flush=True)
            events.append({
                'type': 'resume',
                'message': 'Restored cookies and local storage, then reopened the last URL. '
                           'Temporary page state such as open dialogs was not restored.',
            })
        context = browser.new_context(**context_options)
        context.set_default_timeout(6000)
        context.set_default_navigation_timeout(15000)
        def route_request(route):
            request = route.request
            if request.is_navigation_request() and urlparse(request.url).netloc != urlparse(args.url).netloc:
                events.append({'type': 'boundary', 'message': 'External navigation blocked', 'url': request.url})
                route.abort()
            else:
                route.continue_()
        context.route('**/*', route_request)
        page = context.new_page()
        def close_popup(popup):
            events.append({'type': 'limitation', 'message': 'New tab closed; popup flow untested'})
            popup.close()
        context.on('page', close_popup)
        def dismiss_dialog(dialog):
            events.append({'type': 'dialog', 'message': dialog.message})
            dialog.dismiss()
        page.on('dialog', dismiss_dialog)
        try:
            resume_url = history[-1]['after']['url'] if args.resume else args.url
            page.goto(resume_url, wait_until='domcontentloaded')
            page.wait_for_timeout(1000)
            for step in range(len(history) + 1, args.max_actions + 1):
                before, handles = observe(page)
                try:
                    print(f'\n[{step}/{args.max_actions}] Asking persona...', flush=True)
                    decision = explore_next(persona, before, history)
                    print(f"{decision.get('action')} target={decision.get('target')} | {decision.get('reason')}", flush=True)
                    result, error = 'agent_stopped', None
                    if decision.get('action') != 'stop':
                        try:
                            result = execute(page, decision, before, handles, args.url)
                        except Exception as exc:
                            result, error = 'automation_error', str(exc)
                    page.wait_for_timeout(1000)
                    after, after_handles = observe(page)
                    release(after_handles)
                    row = {'step': step, 'elapsed_seconds': round(time.monotonic() - started, 2),
                           'before': before, 'decision': decision, 'result': result,
                           'automation_error': error, 'after': after,
                           'observed_change': {k: before[k] != after[k] for k in before}}
                    history.append(row)
                    save(run_dir / 'history.json', history)
                    context.storage_state(path=str(run_dir / 'browser_state.json'))
                    save(run_dir / 'report.json', {
                        'persona': persona['name'], 'run_status': 'running',
                        'review_status': 'not_completed', 'actions_recorded': len(history),
                        'last_step': step, 'coverage': coverage(history, catalog),
                        'findings': [], 'persona_feedback': None,
                        'feedback_type': 'simulated_persona_experience',
                        'note': 'Provisional progress only; persona experience review has not run.'})
                    print(f"Result: {result}; changes: {row['observed_change']}", flush=True)
                    if decision.get('action') == 'stop':
                        stop_reason = 'Persona stopped: ' + decision.get('reason', '')
                        break
                    if len(history) >= 4 and all(not any(r['observed_change'].values()) for r in history[-4:]):
                        stop_reason = 'Four attempts without measured change; stopped to avoid a loop.'
                        break
                finally:
                    release(handles)
        except KeyboardInterrupt:
            stop_reason = 'Stopped by user; partial run.'
        except Exception as exc:
            model_failed = isinstance(exc, ModelRequestError)
            stop_reason = f'Execution/model error: {exc}'
        finally:
            context.close()
            browser.close()
    report = {'persona': persona['name'], 'stop_reason': stop_reason,
              'run_status': 'finished',
              'actions_recorded': len(history), 'coverage': coverage(history, catalog),
              'events': events, 'findings': [], 'persona_feedback': None,
              'feedback_type': 'simulated_persona_experience',
              'review_status': 'not_completed', 'limitations': [
                  'Simulated persona reactions are AI inferences, not measured human feelings.',
                  'Feedback and candidate findings require review against the recorded evidence.',
                  'Viewport DOM only: no visual analysis, human behavior measurement, iframe or shadow-DOM traversal.',
                  'Account submissions, payments, external pages and popup flows are untested.',
                  'One-second observations can miss delayed responses; no-change is not proof of a defect.']}
    save(run_dir / 'history.json', history)
    save(run_dir / 'report.json', report)
    if history and not model_failed:
        print('\nReviewing the persona experience from saved interactions...', flush=True)
        try:
            review = clean_review(review_run(persona, history), history)
            apply_review(report, review)
        except (Exception, KeyboardInterrupt) as exc:
            report['review_error'] = str(exc) or 'Review interrupted'
            report['limitations'].append('Review failed; empty findings does not mean no issues.')
    save(run_dir / 'report.json', report)
    print(f"\n{stop_reason}\nRecorded {len(history)} steps; "
          f"persona experience review: {report['review_status']}; "
          f"{len(report['findings'])} candidate issues.")
    print(f"Read: {run_dir / 'report.json'}\nEvidence: {run_dir / 'history.json'}")


if __name__ == '__main__':
    main()
