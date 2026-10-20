"""Evidence-only flow coverage from recorded browser actions."""

import re


def _matches(pattern, value):
    return bool(re.search(pattern, str(value), re.IGNORECASE))


def _target_name(row):
    target_id = row['decision'].get('target')
    return next((control['name'] for control in row['before']['controls']
                 if control['id'] == target_id), '')


def assess_flows(history, catalog):
    """Mark a flow confirmed only after a relevant action and observed end state."""
    assessments = []
    for flow in catalog['flows']:
        attempts = [row for row in history
                    if _matches(flow['attempt_action'], row['decision'].get('action', ''))
                    and _matches(flow['attempt_target'], _target_name(row))]
        attempt_steps = [row['step'] for row in attempts]
        confirmed_step = None
        for attempt in attempts:
            if attempt['result'] != 'executed':
                continue
            state = attempt['after']
            checks = []
            if 'confirm_url' in flow:
                checks.append(_matches(flow['confirm_url'], state['url']))
            if 'confirm_text' in flow:
                checks.append(_matches(flow['confirm_text'], state['visible_text']))
            if 'confirm_new_text' in flow:
                checks.append(_matches(flow['confirm_new_text'], state['visible_text'])
                              and not _matches(flow['confirm_new_text'],
                                               attempt['before']['visible_text']))
            if 'confirm_control' in flow:
                checks.append(any(_matches(flow['confirm_control'], c['name'])
                                  for c in state['controls']))
            if checks and all(checks) and any(attempt['observed_change'].values()):
                confirmed_step = attempt['step']
                break
        if confirmed_step is not None:
            status = 'confirmed'
            evidence_steps = sorted(set(attempt_steps + [confirmed_step]))
        elif attempts and all(row['result'].startswith('blocked:') for row in attempts):
            status = 'blocked'
            evidence_steps = attempt_steps
        elif attempts:
            status = 'attempted'
            evidence_steps = attempt_steps
        else:
            status = 'untested'
            evidence_steps = []
        assessments.append({
            'id': flow['id'], 'name': flow['name'], 'status': status,
            'evidence_steps': evidence_steps,
            'note': ('Configured end state was observed after a matching action.'
                     if status == 'confirmed' else
                     'No configured end state was established in this run.'),
        })
    return assessments
