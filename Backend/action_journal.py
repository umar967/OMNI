"""Crash-conservative action records shared by both browser runners.

history.json is an atomic, fsynced snapshot. The dispatch marker is committed
before calling Playwright; an interrupted dispatch is never assumed to have failed.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/indexers can briefly deny replacement. Retry only this
        # atomic filesystem operation, never the browser action or dispatch.
        for attempt in range(4):
            try:
                os.replace(temp, path)
                break
            except PermissionError as exc:
                if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 3:
                    raise
                time.sleep((0.05, 0.1, 0.2)[attempt])
    finally:
        if temp.exists():
            temp.unlink()


def now():
    return datetime.now(timezone.utc).isoformat()


def evidence_gaps(row, folder=None):
    gaps = []
    if not row.get('journal_version'):
        gaps.append('Legacy record: dispatch durability and target revalidation were not recorded.')
    if not row.get('after'):
        gaps.append('After-observation unavailable; resulting page state is unknown.')
    for phase in ('before', 'after'):
        text_status = row.get(phase, {}).get('text_observation', {}).get('status')
        if text_status in ('partial', 'unavailable'):
            gaps.append(f'{phase.capitalize()} geometry-linked text observation {text_status}.')
        filename = row.get('screenshots', {}).get(phase)
        expected = f"step-{row.get('step')}-{phase}.png"
        if not filename or (folder is not None and (filename != expected or not (folder / 'evidence' / expected).is_file())):
            gaps.append(f'{phase.capitalize()} screenshot unavailable.')
        elif row.get('capture_metadata', {}).get(phase, {}).get('ready') is False:
            gaps.append(f'{phase.capitalize()} screenshot readiness was incomplete.')
    if row.get('action_status') == 'outcome_unknown':
        gaps.append('Dispatch started but execution could not be confirmed. Do not retry automatically.')
    elif row.get('action_status') == 'attempted' and row.get('decision', {}).get('action') != 'stop':
        gaps.append('Decision saved; dispatch was not recorded.')
    return gaps


def retry_key(row):
    decision = row.get('decision', {})
    # Conservative semantic key survives DOM replacement, new IDs and resume.
    target = row.get('intended_target') or next((c for c in row.get('before', {}).get('controls', [])
                if c.get('id') == decision.get('target')), {})
    semantic = target.get('target_snapshot', {}).get('semantic') or {
        k: target.get(k) for k in ('tag', 'type', 'name')}
    semantic = {k: semantic.get(k, '') for k in ('tag', 'type', 'name', 'href')}
    return (row.get('before', {}).get('url'), decision.get('action'),
            json.dumps(decision.get('value', ''), sort_keys=True),
            json.dumps(semantic, sort_keys=True))


class ActionJournal:
    def __init__(self, path, history):
        self.path, self.history = Path(path), history
        self.started = time.monotonic()

    def flush(self):
        atomic_json(self.path, self.history)

    def begin(self, step, before, decision, elapsed_seconds):
        target = next((c for c in before.get('controls', [])
                       if c.get('id') == decision.get('target')), None)
        row = deepcopy(dict(journal_version=1, action_id=uuid.uuid4().hex,
            step=step, elapsed_seconds=elapsed_seconds, before=before, after={},
            decision=decision, intended_target=target, target_label=(target or {}).get('name', ''),
            action_status='attempted', dispatch_state='not_dispatched', result='attempted',
            automation_error=None, observed_change={}, screenshots={}, capture_metadata={},
            evidence_errors={}, timestamps={'decision_saved': now()}))
        self.history.append(row)
        self.flush()  # Failure here aborts before any browser action.
        return row

    def update(self, row, **values):
        row.update(values)
        self.flush()

    def execute(self, row, executor, page, handles, home):
        decision = row['decision']
        if decision.get('action') == 'stop':
            self.update(row, result='agent_stopped')
            return row['result']
        side_effect = decision.get('action') in {'click', 'press', 'fill', 'select', 'check'}
        prior = self.history[:self.history.index(row)]
        uncertain = any(r.get('action_status') == 'outcome_unknown' or
                        (not r.get('journal_version') and r.get('result') == 'automation_error') for r in prior)
        identity = (row.get('intended_target') or {}).get('target_snapshot', {}).get('identity')
        duplicate = side_effect and any(
            r.get('result') == 'executed' and (retry_key(r) == retry_key(row) or
                (identity and identity == (r.get('intended_target') or {}).get('target_snapshot', {}).get('identity') and
                 r['decision'].get('action') == decision.get('action') and r['decision'].get('value', '') == decision.get('value', '')))
            for r in prior)
        if uncertain or duplicate:
            self.update(row, action_status='blocked', result='blocked: automatic retry may duplicate a side effect')
            return row['result']

        dispatched = False

        def on_dispatch():
            nonlocal dispatched
            dispatched = True
            row['timestamps']['dispatch_started'] = now()
            self.update(row, dispatch_state='started', action_status='outcome_unknown', result='outcome_unknown')

        try:
            result = executor(page, decision, row['before'], handles, home, on_dispatch=on_dispatch)
        except BaseException as exc:
            row['timestamps']['execution_returned'] = now()
            self.update(row, action_status='outcome_unknown' if dispatched else 'failed',
                        result='outcome_unknown' if dispatched else 'automation_error',
                        automation_error=f'{type(exc).__name__}: browser action did not return successfully.')
            if not isinstance(exc, Exception):
                raise
            return row['result']
        row['timestamps']['execution_returned'] = now()
        self.update(row, result=result,
                    action_status='executed' if result == 'executed' else 'blocked',
                    dispatch_state='acknowledged' if result == 'executed' else row['dispatch_state'])
        return result

    def observe_after(self, row, page, observe, release):
        try:
            after, handles = observe(page)
            release(handles)
        except BaseException as exc:
            row['evidence_errors']['after_observation'] = type(exc).__name__
            self.flush()
            raise
        row['timestamps']['after_observed'] = now()
        def observable(key, value):
            # Internal identities are safety evidence, not visible UI progress.
            if key == 'controls':
                return [{k: v for k, v in c.items() if k != 'target_snapshot'} for c in value or []]
            return value
        self.update(row, after=after, observed_change={
            k: observable(k, v) != observable(k, after.get(k)) for k, v in row['before'].items()})

    def capture(self, row, page, folder, phase, capture, target=None):
        metadata = {'capture_started_at': now()}
        try:
            image = capture(page, folder, row['step'], phase, target, metadata)
        except Exception as exc:
            row['evidence_errors'][phase + '_screenshot'] = type(exc).__name__
        else:
            row['screenshots'][phase] = image
        metadata['elapsed_seconds'] = round(time.monotonic() - self.started, 2)
        metadata['capture_finished_at'] = now()
        row['capture_metadata'][phase] = metadata
        self.flush()
