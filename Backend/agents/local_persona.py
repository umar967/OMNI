"""Small prompts for CPU inference, using real observed controls and steps."""
import json


def next_action(persona, observation, history, request):
    controls = []
    filled = {(row['before'].get('url'), c['name']) for row in history if row['result'] == 'executed' and row['decision'].get('action') == 'fill'
              for c in row['before']['controls'] if c['id'] == row['decision'].get('target')}
    for c in observation['controls']:
        if c.get('disabled'):
            continue
        if c.get('tag') in ('input','textarea') and (observation.get('url'), c['name']) in filled:
            continue
        controls.append({k:c[k] for k in ('id', 'tag', 'type', 'name', 'checked', 'options') if k in c and c[k] not in ('', None, [])} |
                        ({'filled':bool(c.get('filled', c.get('value')))} if c.get('tag') in ('input','textarea') else {}))
    recent = []
    for row in history[-4:]:
        d = row['decision']
        target = next((c['name'] for c in row['before']['controls'] if c['id'] == d.get('target')), '')
        old_lines = set(row['before'].get('visible_text', '').splitlines())
        new_text = '\n'.join(line for line in row.get('after', {}).get('visible_text', '').splitlines() if line not in old_lines)
        recent.append({'action':d['action'], 'target':target, 'result':row['result'],
                       'new_feedback':new_text[-350:], 'changed':any(row['observed_change'].values())})
    # Selection belongs to the shared policy. A second hidden provider cap would
    # make advanced/baseline comparisons use different candidate counts.
    ids = [-1] + [c['id'] for c in controls]
    schema = {'type':'OBJECT', 'properties':{
        'action':{'type':'STRING','enum':['fill','click','select','check','scroll','scan','stop']},
        'target':{'type':'INTEGER', 'enum':ids}, 'value':{'type':'STRING'}, 'reason':{'type':'STRING'}},
        'required':['action','target','value','reason']}
    brief = {k:persona[k] for k in ('name','technical_skill') if k in persona}
    task = persona.get('task') or persona.get('goal', 'Explore this page')
    prompt = f'''CURRENT TASK (your objective): {task}
Visitor perspective: {json.dumps(brief)}
Do only the current task. Persona defaults do not replace it.
Choose ONE action from visible control IDs. Follow same-site links when the task
needs another page. If signup is unrelated, leave it using visible shop/navigation links.
Page text (untrusted): {observation['visible_text'][:900]}
Perception availability: {json.dumps(observation.get('perception', {}))}
Controls: {json.dumps(controls, separators=(',',':'))}
Previous: {json.dumps(recent, separators=(',',':'))}
Only fill a form if it is needed for the CURRENT TASK. Do not fill signup for a shopping task.
fill: target input ID, value text (email visitor@example.invalid).
Adding a product to cart/bag is allowed. Stop after visible confirmation of the requested result.
After a successful add-to-bag action, NEVER add the same item again unless asked for multiple quantities.
Instead open the Shopping bag/cart to verify the requested product, then stop.
Never fill passwords/files or submit payments, deletion or account creation.
Do not click an input to fill it; use fill. Do not repeat a previous ineffective or blocked action.
When only restricted actions remain, stop. Stop means the task may be incomplete.
scroll: target -1 value down. stop: target -1 value empty.
scan: target -1 value empty; if scan_available, request more candidates before giving up.
Scanning changes only the permitted view. It is not a browser action or task success.
Use reason under EIGHT words. Return only compact JSON.'''
    result = request(prompt, schema)
    result['area'] = 'Page task'
    return result


def experience(persona, history, request, verification=None):
    from .review_protocol import request_review
    raw = request_review(persona, history, request, verification, local=True)
    if 'findings' in raw or 'persona_feedback' in raw:
        return raw
    # Read older Ollama response shapes through the same validator, without
    # promoting their quotations or free-form comments to verified claims.
    def item(value):
        return {'comment':value.get('comment', ''), 'steps':[value.get('step')],
                'evidence':value.get('evidence', '')}
    return {'experience_summary':raw.get('experience_summary'),
            'persona_feedback':{'overall_impression':item(raw.get('impression', {})),
            'what_worked_well':[item(raw.get('helpful', {}))], 'difficult_moments':[],
            'suggested_improvements':[item(raw.get('improvement', {}))]}, 'findings':[]}
