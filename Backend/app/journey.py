"""Derive report context from the saved trace without inferring task success."""
from Backend.task_outcomes import outcome_view
def journey_summary(report, history):
    executed = [r for r in history if r.get('result') == 'executed']
    attempted = [r for r in history if r.get('decision', {}).get('action') != 'stop']
    pages = list(dict.fromkeys(r.get(s, {}).get('url') for r in history
                               for s in ('before', 'after') if r.get(s, {}).get('url')))
    task = report.get('task') or 'No task was recorded'
    sentences = [f'The recorded goal was: {task.rstrip(".")}.']
    if history:
        labels = []
        for row in executed:
            decision = row.get('decision', {})
            label = row.get('target_label') or next((c.get('name', '') for c in row.get('before', {}).get('controls', []) if c.get('id') == decision.get('target')), '')
            labels.append(f"{decision.get('action', 'interaction')}{' on ' + label if label else ''} (step {row.get('step')})")
        sentences.append(f'The trace records {len(executed)} executed interactions across {len(pages)} recorded page URLs.')
        if labels:
            sentences.append('The recorded sequence included ' + '; '.join(labels[:4]) + '.')
        failed = [r for r in attempted if r.get('result') != 'executed']
        if failed:
            sentences.append('Some actions were blocked or could not execute (steps ' + ', '.join(str(r.get('step')) for r in failed) + '); these are execution limitations, not confirmed website defects.')
        unchanged = [r for r in executed if r.get('observed_change') and not any(r['observed_change'].values())]
        if unchanged:
            sentences.append('No measured state change followed steps ' + ', '.join(str(r.get('step')) for r in unchanged) + '; this alone does not establish user difficulty.')
    else:
        sentences.append('No interaction trace is available, so navigation and recovery cannot be reconstructed.')
    status, reason = outcome_view(report)
    labels = {'verified_complete': 'Configured endpoint verified',
              'verified_incomplete': 'Configured endpoint not satisfied',
              'unknown': 'Completion not verified', 'unsupported': 'Verification unsupported'}
    sentences.append(reason)
    return {'text': ' '.join(sentences), 'source': 'recorded_trace',
            'steps': [r.get('step') for r in history],
            'outcome': labels.get(status, labels['unknown']), 'task_outcome': status,
            'stop_reason': report.get('stop_reason') or 'Stop reason not recorded'}
