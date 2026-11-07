"""Run the selected persona against a real page and retain its interaction journal."""
import time
import os
from Backend.action_journal import ActionJournal
from Backend.action_safety import install_navigation_guard

from playwright.sync_api import sync_playwright
from Backend.explore_website import observe, execute, release
from Backend.agents.exploration_agent import explore_next, review_run, clean_review, apply_review
from Backend.agents.gemini_requests import ModelRequestError
from . import storage as db
from .visual_evidence import capture_step
from Backend.persona_engine.resolver import resolve_persona, agent_persona
from Backend.persona_engine.session import PerceptionSession
from Backend.task_outcomes import TaskContract, verify, unverified, attach_verification


def run_live(item_id, plan, progress):
    contract = TaskContract.model_validate(plan.get('task_contract') or {'description': plan['instructions']})
    folder = db.directory('results') / ('exploration_' + item_id)
    folder.mkdir(parents=True, exist_ok=True)
    runtime = resolve_persona(plan['persona'], plan['instructions']).require_supported()
    perception = PerceptionSession(runtime)
    persona = dict(agent_persona(runtime),
                   review_criteria=[c for c in plan['cases'] if c['selected']])
    db.write(folder / 'persona.json', dict(persona, runtime_profile=runtime.model_dump()))
    history = []
    journal = ActionJournal(folder / 'history.json', history)
    journal.flush()
    report = dict(persona=persona['name'], run_id=item_id, created_at=db.now(),
                  task=plan['instructions'], url=plan['url'], project_id=plan['project_id'],
                  persona_id=plan['persona_id'], findings=[], persona_feedback=None,
                  provider=os.getenv('OMNI_MODEL_PROVIDER', 'gemini'),
                  model=os.getenv('OLLAMA_MODEL', 'qwen3:4b') if os.getenv('OMNI_MODEL_PROVIDER', 'gemini').lower() == 'ollama' else os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'),
                  feedback_type='simulated_persona_experience', review_status='unavailable',
                  execution_status='partial',
                  run_status='running', actions_recorded=0,
                  limitations=['Persona reactions are simulated from recorded interactions.',
                               'Account submissions, payments, external navigation and popup flows are not tested.',
                               'DOM observations do not assess visual layout or contrast.'])
    report['perception_policy'] = perception.report(history)
    attach_verification(report, contract, unverified('No endpoint inspection has run yet.'))
    db.write(folder / 'report.json', report)
    started = journal.started
    stop_reason = 'Action limit reached; remaining areas are untested.'
    model_failed = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=False)
            try:
                context = browser.new_context(viewport={'width':1366, 'height':768})
                context.set_default_timeout(6000)
                context.set_default_navigation_timeout(30000)
                install_navigation_guard(context, plan['url'])
                page = context.new_page()
                context.on('page', lambda popup: popup.close())
                page.on('dialog', lambda dialog: dialog.dismiss())
                page.goto(plan['url'], wait_until='domcontentloaded')
                page.wait_for_timeout(1000)
                for step in range(1, plan['max_actions'] + 1):
                    before, handles = observe(page)
                    try:
                        perceived = perception.perceive(before)
                        progress(item_id, f'Step {step}: persona is deciding what to do.', stage='exploring')
                        decision = perception.decide(explore_next, persona, perceived, history)
                        row = journal.begin(step, before, decision, round(time.monotonic()-started, 2))
                        perception.record_before(journal, row, perceived)
                        target = handles.get(decision.get('target')) if type(decision.get('target')) is int and decision['target'] in perceived.allowed_targets else None
                        journal.capture(row, page, folder, 'before', capture_step, target)
                        result = perception.execute(journal, row, perceived, execute, page, handles, plan['url'])
                        page.wait_for_timeout(1000)
                        journal.observe_after(row, page, observe, release)
                        perception.record_after(journal, row)
                        journal.capture(row, page, folder, 'after', capture_step)
                        verification = verify(page, contract, step=step)
                        attach_verification(report, contract, verification)
                        report['actions_recorded'] = len(history)
                        report['perception_policy'] = perception.report(history)
                        db.write(folder / 'report.json', report)
                        progress(item_id, f'Step {step}: {decision.get("action")} — {result}.', stage='exploring')
                        if result == 'outcome_unknown':
                            stop_reason = 'Uncertain action dispatch; automatic retries disabled.'
                            break
                        if row.get('perception_rejection') or result == 'perception_scanned' or result.startswith('refresh_required:'):
                            continue  # A new observation gets new IDs and handles.
                        if verification.task_outcome == 'verified_complete':
                            report['execution_status'] = 'finished'
                            stop_reason = 'Configured observable endpoint independently verified.'
                            break
                        if decision.get('action') == 'stop':
                            report['execution_status'] = 'finished'
                            stop_reason = 'Persona stopped: ' + decision.get('reason', '')
                            break
                        if result.startswith('blocked:') or result == 'automation_error':
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
                attach_verification(report, contract, verify(page, contract, step=len(history) or None, final=True))
            finally:
                browser.close()
    except KeyboardInterrupt:
        stop_reason = 'Session cancelled; partial evidence retained.'
        report['execution_status'] = 'cancelled'
        report['run_status'] = 'failed'
        attach_verification(report, contract, unverified('Session cancelled before final endpoint inspection.'))
    except ModelRequestError as exc:
        stop_reason = str(exc)
        model_failed = True
        report['run_status'] = 'failed'
        report['execution_status'] = 'partial' if history else 'failed'
        attach_verification(report, contract, unverified('Model failure prevented final endpoint inspection.'))
    except Exception:
        stop_reason = 'Browser or model execution failed; recorded actions remain available.'
        report['run_status'] = 'failed'
        report['execution_status'] = 'partial' if history else 'failed'
        attach_verification(report, contract, unverified('Execution failure prevented final endpoint inspection.'))
    else:
        report['run_status'] = 'finished'
    report['stop_reason'] = stop_reason
    report['actions_recorded'] = len(history)
    journal.flush()
    report['perception_policy'] = perception.report(history)
    if history and not model_failed:
        progress(item_id, 'Writing persona feedback from the recorded visit.', stage='reviewing')
        try:
            apply_review(report, clean_review(review_run(persona, perception.history(history), None), history, report['outcome_verification'], folder))
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
