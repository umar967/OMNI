"""Run the selected persona against a real page and retain its interaction journal."""
import time
import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from Backend.explore_website import observe, execute, release
from Backend.agents.exploration_agent import explore_next, review_run, clean_review, apply_review
from Backend.agents.gemini_requests import ModelRequestError
from . import storage as db
from .visual_evidence import capture_step


def run_live(item_id, plan, progress):
    folder = db.directory('results') / ('exploration_' + item_id)
    folder.mkdir(parents=True, exist_ok=True)
    persona = dict(plan['persona'], task=plan['instructions'],
                   review_criteria=[c for c in plan['cases'] if c['selected']])
    db.write(folder / 'persona.json', persona)
    history = []
    report = dict(persona=persona['name'], run_id=item_id, created_at=db.now(),
                  task=plan['instructions'], url=plan['url'], project_id=plan['project_id'],
                  persona_id=plan['persona_id'], findings=[], persona_feedback=None,
                  provider=os.getenv('OMNI_MODEL_PROVIDER', 'gemini'),
                  model=os.getenv('OLLAMA_MODEL', 'qwen3:4b') if os.getenv('OMNI_MODEL_PROVIDER', 'gemini').lower() == 'ollama' else os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'),
                  feedback_type='simulated_persona_experience', review_status='not_completed',
                  run_status='running', actions_recorded=0,
                  limitations=['Persona reactions are simulated from recorded interactions.',
                               'Account submissions, payments, external navigation and popup flows are not tested.',
                               'DOM observations do not assess visual layout or contrast.'])
    db.write(folder / 'report.json', report)
    started = time.monotonic()
    stop_reason = 'Action limit reached; remaining areas are untested.'
    model_failed = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=False)
            try:
                context = browser.new_context(viewport={'width':1366, 'height':768})
                context.set_default_timeout(6000)
                context.set_default_navigation_timeout(30000)
                origin = urlsplit(plan['url'])
                def guard(route):
                    target = urlsplit(route.request.url)
                    # Never let a tested website navigate into OMNI's own API.
                    workspace = target.hostname in ('localhost', '127.0.0.1') and target.port == 8000
                    if workspace or (route.request.is_navigation_request() and
                                     (target.scheme, target.netloc) != (origin.scheme, origin.netloc)):
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', guard)
                page = context.new_page()
                context.on('page', lambda popup: popup.close())
                page.on('dialog', lambda dialog: dialog.dismiss())
                page.goto(plan['url'], wait_until='domcontentloaded')
                page.wait_for_timeout(1000)
                for step in range(1, plan['max_actions'] + 1):
                    before, handles = observe(page)
                    try:
                        progress(item_id, f'Step {step}: persona is deciding what to do.', stage='exploring')
                        decision = explore_next(persona, before, history)
                        target = handles.get(decision.get('target'))
                        label = next((c['name'] for c in before['controls'] if c['id'] == decision.get('target')), '')
                        images = {}
                        for phase in ('before',):
                            try:
                                images[phase] = capture_step(page, folder, step, phase, target)
                            except Exception:
                                progress(item_id, f'Step {step}: screenshot capture unavailable; interaction evidence will still be saved.')
                        result, error = 'agent_stopped', None
                        if decision.get('action') != 'stop':
                            try:
                                result = execute(page, decision, before, handles, plan['url'])
                            except Exception:
                                result, error = 'automation_error', 'Browser action could not be completed.'
                        page.wait_for_timeout(1000)
                        try:
                            images['after'] = capture_step(page, folder, step, 'after', target)
                        except Exception:
                            progress(item_id, f'Step {step}: after screenshot unavailable.')
                        after, after_handles = observe(page)
                        release(after_handles)
                        history.append(dict(step=step, elapsed_seconds=round(time.monotonic()-started, 2),
                                            before=before, after=after, decision=decision, result=result,
                                            automation_error=error,
                                            screenshots=images, target_label=label,
                                            observed_change={k: before[k] != after[k] for k in before}))
                        db.write(folder / 'history.json', history)
                        report['actions_recorded'] = len(history)
                        db.write(folder / 'report.json', report)
                        progress(item_id, f'Step {step}: {decision.get("action")} — {result}.', stage='exploring')
                        if decision.get('action') == 'stop':
                            stop_reason = 'Persona stopped: ' + decision.get('reason', '')
                            break
                        if result.startswith('blocked:'):
                            stop_reason = 'Reached an exploration boundary: ' + result
                            report['limitations'].append(stop_reason)
                            break
                        if len(history) >= 2 and all(
                            r['decision'].get('action') == decision.get('action') and
                            r['decision'].get('target') == decision.get('target') and
                            not any(r['observed_change'].values()) for r in history[-2:]
                        ):
                            stop_reason = 'Repeated action without observed progress; moving to feedback.'
                            break
                        if len(history) >= 4 and all(not any(r['observed_change'].values()) for r in history[-4:]):
                            stop_reason = 'Stopped after four attempts without measured change.'
                            break
                    finally:
                        release(handles)
            finally:
                browser.close()
    except ModelRequestError as exc:
        stop_reason = str(exc)
        model_failed = True
        report['run_status'] = 'failed'
    except Exception:
        stop_reason = 'Browser or model execution failed; recorded actions remain available.'
        report['run_status'] = 'failed'
    else:
        report['run_status'] = 'finished'
    report['stop_reason'] = stop_reason
    db.write(folder / 'history.json', history)
    if history and not model_failed:
        progress(item_id, 'Writing persona feedback from the recorded visit.', stage='reviewing')
        try:
            apply_review(report, clean_review(review_run(persona, history), history))
        except ModelRequestError as exc:
            report['review_error'] = str(exc)
        except Exception:
            report['review_error'] = 'Experience review failed. Recorded interactions remain available.'
    db.write(folder / 'report.json', report)
    complete = report['run_status'] == 'finished' and report['review_status'] == 'completed'
    progress(item_id, 'Persona session saved.' if complete else 'Partial session saved; inspect the report for limitations.',
             status='completed' if complete else 'failed', stage='completed' if complete else 'failed',
             report_id=folder.name,
             error=None if complete else report.get('review_error', stop_reason))
