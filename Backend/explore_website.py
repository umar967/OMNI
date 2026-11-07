"""Bounded live exploration with a first-time-user persona."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from Backend.flow_coverage import assess_flows
from Backend.action_journal import ActionJournal, atomic_json
from Backend.action_safety import snapshot, execute_validated, install_navigation_guard
from Backend.app.visual_evidence import capture_step
from Backend.agents.gemini_requests import ModelRequestError
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.task_outcomes import TaskContract, verify, unverified, attach_verification

ROOT = Path(__file__).resolve().parent
SELECTOR = ('button, a[href], input:not([type="hidden"]), textarea, select, '
            '[role="button"], [role="link"], [role="tab"], [role="checkbox"], '
            '[role="radio"], [contenteditable="true"]')


def save(path, data):
    atomic_json(path, data)


def observe(page):
    """Return viewport controls and their handles; IDs are local to this snapshot.

    Geometry uses CSS pixels. Visibility metadata describes CSS/viewport state,
    not occlusion, clipping by ancestors, or Playwright actionability.
    """
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
            const intersectionWidth = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
            const intersectionHeight = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
            let effectiveOpacity = 1;
            for (let node = el; node; node = node.parentElement) {
                effectiveOpacity *= Number(getComputedStyle(node).opacity);
            }
            return {tag: el.tagName.toLowerCase(), type: el.type || '',
                name: el.getAttribute('aria-label') || labelled.trim() || labels ||
                      el.innerText?.trim() || el.getAttribute('placeholder') || '',
                disabled: el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true',
                value: el.type === 'password' ? '[redacted]' : (el.value || ''),
                checked: el.checked ?? null,
                bounding_box: {x: r.x, y: r.y, width: r.width, height: r.height},
                viewport_position: {center_x: (r.left + r.width / 2) / innerWidth,
                    center_y: (r.top + r.height / 2) / innerHeight,
                    visible_fraction: intersectionWidth * intersectionHeight / (r.width * r.height)},
                style: {font_size: s.fontSize, color: s.color, background_color: s.backgroundColor},
                visibility: {css_visibility: s.visibility, display: s.display,
                    effective_opacity: effectiveOpacity, intersects_viewport: true,
                    fully_in_viewport: r.left >= 0 && r.top >= 0 &&
                        r.right <= innerWidth && r.bottom <= innerHeight},
                label_metadata: {dom_id: el.id || '', role: el.getAttribute('role') || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    aria_labelledby: el.getAttribute('aria-labelledby') || '',
                    labelledby_text: labelled.trim(), associated_labels: labels,
                    placeholder: el.getAttribute('placeholder') || '',
                    title: el.getAttribute('title') || ''},
                options: el.tagName === 'SELECT' ? [...el.options].map(o =>
                    ({text: o.text, value: o.value})) : []};
        }''')
        if data is None:
            element.dispose()
            continue
        index = len(controls)
        data['target_snapshot'] = snapshot(element)
        # Use the same semantic sample for the decision and later revalidation.
        for key in ('tag', 'type', 'name'):
            data[key] = data['target_snapshot']['semantic'][key]
        data['disabled'] = not data['target_snapshot']['enabled']
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
    return {'url': page.url, 'title': page.title(), 'visible_text': text, 'controls': controls,
            'viewport': page.evaluate('() => ({width: innerWidth, height: innerHeight})'),
            'scroll': page.evaluate('() => ({x: scrollX, y: scrollY, height: document.documentElement.scrollHeight})')}, handles


def release(handles):
    for handle in handles.values():
        try:
            handle.dispose()
        except Exception:
            pass  # Navigation may already have destroyed the document.


def execute(page, decision, observation, handles, home, on_dispatch=lambda: None):
    return execute_validated(page, decision, observation, handles, home, on_dispatch)


def coverage(history, catalog):
    observed, attempted = set(), set()
    for row in history:
        for state in (row['before'], row.get('after', {})):
            if not state:
                continue
            observed.update((state['url'], c['tag'], c['name']) for c in state['controls'])
        for c in row['before']['controls']:
            if c['id'] == row['decision'].get('target'):
                attempted.add((row['before']['url'], c['tag'], c['name']))
    return {'pages_observed': sorted({s['url'] for r in history for s in (r['before'], r.get('after', {})) if s.get('url')}),
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
    parser.add_argument('--task-contract', type=Path, help='Developer-authored task endpoint JSON; never generated by the decision model')
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
        # New snapshots retain the canonical configuration; old snapshots still migrate.
        if 'runtime_profile' in persona:
            persona = persona['runtime_profile']['persona']
        resolve_persona(persona).require_supported()
        persona = agent_persona(persona)
        catalog = json.loads((run_dir / 'flow_catalog.json').read_text(encoding='utf-8'))
        history = json.loads((run_dir / 'history.json').read_text(encoding='utf-8'))
        previous_report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
        events = previous_report.get('events', [])

        if any(r.get('action_status') == 'outcome_unknown' or
               (not r.get('journal_version') and r.get('result') == 'automation_error') for r in history):
            parser.error('Cannot automatically resume after uncertain dispatch; inspect the saved evidence first.')

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
        runtime = resolve_persona(persona).require_supported()
        persona = agent_persona(persona)
        save(run_dir / 'persona.json', dict(persona, runtime_profile=runtime.model_dump()))
        save(run_dir / 'flow_catalog.json', catalog)
        history, events = [], []
        save(run_dir / 'report.json', {
            'persona': persona['name'], 'run_status': 'running',
            'review_status': 'unavailable', 'actions_recorded': 0,
            'findings': [],
            'persona_feedback': None,
            'feedback_type': 'simulated_persona_experience',
            'note': 'Persona experience review has not run yet.',
        })
    contract_data = (json.loads(args.task_contract.read_text(encoding='utf-8')) if args.task_contract else
                     previous_report.get('task_contract') if args.resume else None)
    contract = TaskContract.model_validate(contract_data or {'description': persona.get('task') or persona.get('goal', 'Explore the website')})
    persona['task'] = contract.description
    verification = unverified('No endpoint inspection has run yet.')
    execution_status = 'partial'
    initial_report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
    initial_report.update(execution_status='partial', task=contract.description, review_status='unavailable')
    attach_verification(initial_report, contract, verification)
    save(run_dir / 'report.json', initial_report)
    stop_reason = 'Action limit reached; remaining areas are untested.'
    model_failed = False
    journal = ActionJournal(run_dir / 'history.json', history)
    journal.flush()
    started = journal.started
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
        install_navigation_guard(context, args.url)
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
            resume_url = (history[-1].get('after') or history[-1]['before'])['url'] if args.resume else args.url
            page.goto(resume_url, wait_until='domcontentloaded')
            page.wait_for_timeout(1000)
            for step in range(len(history) + 1, args.max_actions + 1):
                before, handles = observe(page)
                try:
                    print(f'\n[{step}/{args.max_actions}] Asking persona...', flush=True)
                    decision = explore_next(persona, before, history)
                    print(f"{decision.get('action')} target={decision.get('target')} | {decision.get('reason')}", flush=True)
                    row = journal.begin(step, before, decision, round(time.monotonic() - started, 2))
                    target = handles.get(decision.get('target'))
                    journal.capture(row, page, run_dir, 'before', capture_step, target)
                    result = journal.execute(row, execute, page, handles, args.url)
                    page.wait_for_timeout(1000)
                    journal.observe_after(row, page, observe, release)
                    journal.capture(row, page, run_dir, 'after', capture_step)
                    verification = verify(page, contract, step=step)
                    save(run_dir / 'history.json', history)
                    context.storage_state(path=str(run_dir / 'browser_state.json'))
                    progress_report = {
                        'persona': persona['name'], 'run_status': 'running',
                        'execution_status': 'partial', 'task': contract.description,
                        'review_status': 'unavailable', 'actions_recorded': len(history),
                        'last_step': step, 'coverage': coverage(history, catalog),
                        'findings': [], 'persona_feedback': None,
                        'feedback_type': 'simulated_persona_experience',
                        'note': 'Provisional progress only; persona experience review has not run.'}
                    attach_verification(progress_report, contract, verification)
                    save(run_dir / 'report.json', progress_report)
                    print(f"Result: {result}; changes: {row['observed_change']}", flush=True)
                    if result == 'outcome_unknown':
                        stop_reason = 'Uncertain action dispatch; automatic retries disabled.'
                        break
                    if result.startswith('refresh_required:'):
                        continue  # Observe anew; never rebind the old ID.
                    if result.startswith('blocked:') or result == 'automation_error':
                        stop_reason = 'Execution boundary: ' + result
                        break
                    if verification.task_outcome == 'verified_complete':
                        execution_status = 'finished'
                        stop_reason = 'Configured observable endpoint independently verified.'
                        break
                    if decision.get('action') == 'stop':
                        execution_status = 'finished'
                        stop_reason = 'Persona stopped: ' + decision.get('reason', '')
                        break
                    if len(history) >= 4 and all(not any(r['observed_change'].values()) for r in history[-4:]):
                        stop_reason = 'Four attempts without measured change; stopped to avoid a loop.'
                        break
                finally:
                    release(handles)
            verification = verify(page, contract, step=len(history) or None, final=True)
        except KeyboardInterrupt:
            execution_status = 'cancelled'
            verification = unverified('Session cancelled before final endpoint inspection.')
            stop_reason = 'Stopped by user; partial run.'
        except Exception as exc:
            execution_status = 'partial' if history else 'failed'
            verification = unverified('Execution failure prevented final endpoint inspection.')
            model_failed = isinstance(exc, ModelRequestError)
            stop_reason = f'Execution/model error: {exc}'
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
    report = {'persona': persona['name'], 'stop_reason': stop_reason,
              'run_status': 'failed' if execution_status in ('failed', 'cancelled') or model_failed else 'finished',
              'execution_status': execution_status, 'task': contract.description,
              'actions_recorded': len(history), 'coverage': coverage(history, catalog),
              'events': events, 'findings': [], 'persona_feedback': None,
              'feedback_type': 'simulated_persona_experience',
              'review_status': 'unavailable', 'limitations': [
                  'Simulated persona reactions are AI inferences, not measured human feelings.',
                  'Feedback and candidate findings require review against the recorded evidence.',
                  'Viewport DOM only: no visual analysis, human behavior measurement, iframe or shadow-DOM traversal.',
                  'Account submissions, payments, external pages and popup flows are untested.',
                  'One-second observations can miss delayed responses; no-change is not proof of a defect.']}
    attach_verification(report, contract, verification)
    save(run_dir / 'history.json', history)
    save(run_dir / 'report.json', report)
    if history and not model_failed:
        print('\nReviewing the persona experience from saved interactions...', flush=True)
        try:
            review = clean_review(review_run(persona, history, report['outcome_verification']), history)
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
