"""Deterministic metrics with denominators and unknowns, not human realism scores."""
from Backend.action_journal import evidence_gaps, retry_key


def ratio(numerator, denominator):
    return {'numerator':numerator, 'denominator':denominator,
            'value':numerator/denominator if denominator else None}


def exposure_sample(raw, perceived, annotations, handles, event='initial', page=None):
    visible, exposed, actionable, critical = set(), set(), set(), set()
    errors = []
    ids = set(perceived.allowed_targets)
    exposed_ids = {c['id'] for c in perceived.model_observation['controls']}
    for annotation in annotations:
        if annotation.critical:
            critical.add(annotation.target_id)
        matched = []
        try:
            if page is not None and page.locator(annotation.selector).count() != 1:
                errors.append(annotation.target_id + ': selector must identify one fixture control')
                continue
            for cid, handle in handles.items():
                if handle.evaluate('(el, selector) => el.matches(selector)', annotation.selector):
                    matched.append(cid)
        except Exception:
            errors.append(annotation.target_id + ': annotation inspection unavailable')
            continue
        if len(matched) > 1:
            errors.append(annotation.target_id + ': ambiguous selector')
        elif matched:
            visible.add(annotation.target_id)
            if matched[0] in exposed_ids:
                exposed.add(annotation.target_id)
            if matched[0] in ids:
                actionable.add(annotation.target_id)
    enabled = {c['id'] for c in raw['controls'] if not c.get('disabled')}
    # Precision counts unique controls, even if several annotations refer to one.
    target_control_ids = set()
    for cid, handle in handles.items():
        try:
            if any(handle.evaluate('(el, selector) => el.matches(selector)', a.selector) for a in annotations):
                target_control_ids.add(cid)
        except Exception:
            errors.append('Control annotation inspection unavailable')
    metrics = {'task_target_retention':ratio(len(exposed), len(annotations)),
        'visible_target_retention':ratio(len(exposed), len(visible)),
        'actionable_target_retention':ratio(len(actionable), len(annotations)),
        'permitted_control_coverage':ratio(len(ids & enabled), len(enabled)),
        'exposure_precision':ratio(len(exposed_ids & target_control_ids), len(exposed_ids))}
    if errors:
        metrics = {key:None for key in metrics}
    return {'event':event, 'visible_target_ids':sorted(visible), 'retained_target_ids':sorted(exposed),
        'actionable_target_ids':sorted(actionable),
        'critical_target_ids':sorted(critical), 'errors':errors,
        **metrics,
        'text_status':perceived.diagnostics.get('text', {})}


def run_metrics(samples, history, verification, folder):
    retained = set().union(*(set(s['retained_target_ids']) for s in samples)) if samples else set()
    critical = set().union(*(set(s['critical_target_ids']) for s in samples)) if samples else set()
    actionable = set().union(*(set(s.get('actionable_target_ids', [])) for s in samples)) if samples else set()
    scan_retained = set().union(*(set(s['retained_target_ids']) for s in samples if s['event']=='scan')) if samples else set()
    scroll_retained = set().union(*(set(s['retained_target_ids']) for s in samples if s['event']=='scroll')) if samples else set()
    seen, repeated, unknown_pairs = set(), 0, 0
    for row in history:
        if row.get('result') != 'executed':
            continue
        if not row.get('after'):
            unknown_pairs += 1
            continue
        def ui(state):
            return (state.get('url'), state.get('visible_text'),
                    [{k:c.get(k) for k in ('id','name','tag','type','disabled','checked','value')}
                     for c in state.get('controls', [])], state.get('scroll'))
        if ui(row['before']) == ui(row['after']):
            key = retry_key(row)
            repeated += key in seen
            seen.add(key)
    complete = sum(not evidence_gaps(row, folder) for row in history)
    valid = not any(s['errors'] for s in samples)
    return {'annotations_valid':valid, 'initial':samples[0] if samples else None,
        'cumulative_critical_retention':ratio(len(retained & critical), len(critical)) if valid else None,
        'cumulative_critical_actionable_retention':ratio(len(actionable & critical), len(critical)) if valid else None,
        'critical_retained_after_scan':sorted(scan_retained & critical),
        'critical_retained_after_scroll':sorted(scroll_retained & critical),
        'repeated_ineffective_interactions':repeated, 'uninspectable_execution_pairs':unknown_pairs,
        'invalid_action_rejections':sum(bool(r.get('perception_rejection')) for r in history),
        'safety_rejections':sum(r.get('action_status')=='blocked' and not r.get('perception_rejection') for r in history),
        'task_outcome':verification.task_outcome,
        'evidence_complete_actions':ratio(complete, len(history)),
        'text_partial_samples':sum(bool(s['text_status'].get('partial')) for s in samples),
        'limitations':['Target annotations are evaluator-defined relevance, not human fixation labels.',
            'No observed change is a sampled condition, not proof of a website defect.',
            'Exposure precision measures a restricted target set; other exposed controls may be useful.']}
