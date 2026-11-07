"""Claim-level review: deterministic observations, explicitly unverified UX hypotheses.

No free-form model sentence can become a verified observation. The model selects
server-generated observation IDs; semantic relevance of its interpretation still
requires developer review. This module does not analyze screenshot pixels.
"""
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from Backend.action_journal import evidence_gaps
from Backend.task_outcomes import VerificationResult, TaskContract, evaluate_sample

VERSION = '1.0'
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Classification = Literal['observed_browser_event', 'independently_verified_task_outcome',
                         'ux_hypothesis', 'unsupported_assertion']
Category = Literal['feedback_clarity', 'navigation_clarity', 'control_labelling',
                   'error_recovery', 'task_expectation']


class FindingProposal(BaseModel):
    """Model-authored inputs only. Protected output fields are not accepted."""
    model_config = ConfigDict(extra='forbid', strict=True)
    category: Category
    affected_page: Text
    affected_control_id: int | None = None
    observation_ids: list[Text] = Field(min_length=1, max_length=6)
    hypothesis: Text
    expected_behavior: Text
    potential_user_impact: Text
    suggested_improvement: Text


class EvidenceReference(BaseModel):
    source: Literal['history', 'outcome_verification', 'screenshot']
    step: int | None = None
    phase: str
    field: str
    url: str | None = None
    control_id: int | None = None
    evidence_id: str | None = None
    filename: str | None = None
    availability: Literal['recorded', 'available', 'missing', 'not_checked', 'mismatched'] = 'recorded'


class Finding(FindingProposal):
    """Canonical saved contract. All additions are validator-owned."""
    version: Literal['1.0'] = VERSION
    id: str
    classification: Literal['ux_hypothesis'] = 'ux_hypothesis'
    validation_status: Literal['requires_developer_review'] = 'requires_developer_review'
    observed_symptom: list[str]
    reproduction_steps: list[dict]
    supporting_evidence: list[EvidenceReference]
    limitations: list[str]
    impact_status: Literal['interpretation_not_measurement'] = 'interpretation_not_measurement'
    expectation_status: Literal['proposed_usability_recommendation'] = 'proposed_usability_recommendation'
    # Legacy display aliases; never contain model-authored factual conclusions.
    issue: str
    steps: list[int]
    evidence: str
    recommendation: str


ALLOWED = {
    'feedback_clarity': {'sample_unchanged', 'text_appeared'},
    'navigation_clarity': {'url_changed'},
    'control_labelling': {'control_observed', 'control_unlabelled'},
    'error_recovery': {'text_appeared'},
    'task_expectation': {'endpoint_mismatch'},
}
TITLES = {
    'feedback_clarity': 'Review feedback after the recorded action',
    'navigation_clarity': 'Review the observed navigation transition',
    'control_labelling': 'Review the observed control label',
    'error_recovery': 'Review guidance around the recorded page message',
    'task_expectation': 'Investigate the configured endpoint mismatch',
}
SEMANTIC_LIMIT = ('Evidence references and the recorded symptom were checked. Semantic relevance, '
                  'causality, severity and usefulness of this UX interpretation are not automatically proven.')


def unique_rows(history):
    counts = Counter(r.get('step') for r in history if type(r.get('step')) is int)
    return {r['step']: r for r in history if type(r.get('step')) is int and r['step'] > 0 and counts[r['step']] == 1}


def executed(row):
    return (row.get('result') == 'executed' and
            (not row.get('journal_version') or row.get('action_status') == 'executed'))


def complete(row):
    return executed(row) and bool(row.get('before')) and bool(row.get('after'))


def evidence_refs(row, phase, field, folder=None, control_id=None, cache=None):
    state = row.get(phase, {})
    refs = [EvidenceReference(source='history', step=row['step'], phase=phase,
                              field=field, url=state.get('url'), control_id=control_id).model_dump()]
    filename = f"step-{row['step']}-{phase}.png"
    recorded = row.get('screenshots', {}).get(phase) == filename
    available = recorded and folder is not None and (Path(folder)/'evidence'/filename).is_file()
    availability = 'missing'
    if recorded:
        availability = 'not_checked' if folder is None else 'missing'
    cache_key = (row['step'], phase)
    if cache is not None and cache_key in cache:
        availability = cache[cache_key]
    elif available:
        metadata = row.get('capture_metadata', {}).get(phase, {})
        try:
            digest = hashlib.sha256((Path(folder)/'evidence'/filename).read_bytes()).hexdigest()
            availability = ('not_checked' if not metadata.get('sha256') or not metadata.get('url') else
                            'available' if digest == metadata['sha256'] and metadata['url'] == state.get('url') else 'mismatched')
        except OSError:
            availability = 'missing'
    if cache is not None:
        cache[cache_key] = availability
    refs.append(EvidenceReference(source='screenshot', step=row['step'], phase=phase,
        field='screenshots.' + phase, filename=filename,
        availability=availability).model_dump())
    return refs


def observations(history, verification=None, folder=None):
    """Derive finite, narrow facts. Never trust observed_change or model prose."""
    folder = Path(folder) if folder is not None else None
    facts, limitations = [], []
    artifact_cache = {}
    def refs_for(row, phase, field, folder=None, control_id=None):
        return evidence_refs(row, phase, field, folder, control_id, artifact_cache)
    for step, row in unique_rows(history).items():
        if not complete(row):
            limitations.append({'step': step, 'classification': 'observed_browser_event',
                'scope': 'execution_limitation', 'statement':
                f"Step {step}: {row.get('action_status') or row.get('result') or 'unrecorded'}; "
                'no complete executed before/after pair supports a website finding.',
                'limitations': evidence_gaps(row, folder)})
            continue
        before, after = row['before'], row['after']
        decision = row.get('decision', {})
        target = next((c for c in before.get('controls', []) if c.get('id') == decision.get('target')), {})
        gaps = evidence_gaps(row, folder)

        def add(suffix, kind, statement, phase='after', field='visible_text', control_id=None, refs=None):
            refs = refs or refs_for(row, phase, field, folder, control_id)
            capture_limits = []
            if any(r['availability'] == 'mismatched' for r in refs):
                capture_limits.append('A screenshot does not match the recorded page or capture hash; it cannot support this observation.')
            if any(r['availability'] == 'not_checked' for r in refs):
                capture_limits.append('Screenshot provenance has not been established; no visual claim is validated.')
            facts.append({'id': f'step-{step}-{suffix}', 'classification': 'observed_browser_event',
                'validation_status': 'validated_observation', 'kind': kind, 'step': step,
                'affected_page': (before if phase == 'before' else after).get('url', ''),
                'control_id': control_id, 'statement': statement,
                'supporting_evidence': refs,
                'limitations': gaps + capture_limits + ['A sampled browser observation is not proof of a defect or human experience.']})

        add('action', 'action_executed', f"Step {step}: the journal records {decision.get('action', 'an action')} returning successfully.",
            phase='before', field='result', control_id=target.get('id'))
        if before.get('url') and after.get('url') and before['url'] != after['url']:
            add('url', 'url_changed', f"Recorded URL changed from {before['url']} to {after['url']}.",
                field='url', refs=refs_for(row, 'before', 'url', folder) + refs_for(row, 'after', 'url', folder))
        def text_blocks(state):
            if 'text_blocks' in state:
                blocks = state['text_blocks']
            else:
                structured = state.get('text_observation', {})
                if not isinstance(structured, dict) or structured.get('version') != 'geometry-text-1':
                    return None
                blocks = structured.get('blocks', [])
            if not isinstance(blocks, list):
                return []
            return [b for b in blocks if isinstance(b, dict) and isinstance(b.get('id'), str)
                    and isinstance(b.get('text'), str) and
                    b.get('fingerprint') == hashlib.sha256((b['id']+b['text']).encode()).hexdigest()]
        before_blocks, after_blocks = text_blocks(before), text_blocks(after)
        if before_blocks is not None and after_blocks is not None:
            # Stable fragment IDs/fingerprints preserve claim identity when a
            # model sees a subset. Flat-text line indexes change under filtering.
            old = {b.get('fingerprint') for b in before_blocks}
            for b in after_blocks:
                if (b.get('fingerprint') not in old and b.get('id') and b.get('text')
                        and b.get('privacy') == 'screened'):
                    add(f"text-{b['id']}-{b['fingerprint'][:12]}", 'text_appeared',
                        f"After-sample contains this page-authored text, absent from the before-sample: {b['text']!r}.",
                        refs=refs_for(row, 'before', 'text_observation.blocks', folder) + refs_for(row, 'after', 'text_observation.blocks', folder))
        elif before_blocks is None and after_blocks is None and isinstance(before.get('visible_text'), str) and isinstance(after.get('visible_text'), str):
            old = set(before['visible_text'].splitlines())
            for i, line in enumerate(after['visible_text'].splitlines()):
                if line.strip() and line not in old and len(line) <= 1000:
                    add(f'text-{i}', 'text_appeared', f'After-sample contains this page-authored text, absent from the before-sample: {line!r}.',
                        refs=refs_for(row, 'before', 'visible_text', folder) + refs_for(row, 'after', 'visible_text', folder))
        for phase, state in [('before', before), ('after', after)]:
            controls = state.get('controls', [])
            counts = Counter(c.get('id') for c in controls if type(c.get('id')) is int)
            for c in controls:
                cid = c.get('id')
                if type(cid) is not int or counts[cid] != 1 or not isinstance(c.get('name'), str) or c.get('label_redacted'):
                    continue
                label = c['name'].strip()
                kind = 'control_observed' if label else 'control_unlabelled'
                statement = (f'{phase.capitalize()}-sample control {cid} has DOM-derived name {label!r}.' if label else
                             f'{phase.capitalize()}-sample control {cid} has an empty DOM-derived name; this is not a full accessible-name audit.')
                add(f'{phase}-control-{cid}', kind, statement, phase, 'controls.name', cid)
        def ui(state):
            return {k: state.get(k) for k in ('url', 'visible_text')} | {
                'controls': [{k: c.get(k) for k in ('id','tag','type','name','disabled','checked','options')}
                             for c in state.get('controls', [])]}
        if all(k in before and k in after for k in ('url','visible_text','controls')) and ui(before) == ui(after):
            add('unchanged', 'sample_unchanged', 'Sampled URL, viewport text and listed control properties were unchanged. '
                'Delayed responses, value edits, CSS changes and offscreen changes were not ruled out.',
                refs=refs_for(row, 'before', 'url,visible_text,controls', folder) + refs_for(row, 'after', 'url,visible_text,controls', folder))
    if len(unique_rows(history)) != len(history):
        limitations.append({'scope':'execution_limitation', 'statement':'Duplicate or invalid step IDs were excluded from claim evidence.'})
    # Only the separately supplied verifier result is trusted, never review payload fields.
    if not isinstance(verification, dict) or verification.get('verifier') != 'dom-endpoint-v1':
        return facts, limitations
    try:
        result = VerificationResult.model_validate(verification or {})
        for e in result.evidence:
            contract = TaskContract(description='Recheck persisted endpoint evidence', endpoint=e['conditions'])
            checked = evaluate_sample(contract, e['observed'], final=e.get('final', False))
            if (checked.task_outcome not in ('verified_complete', 'verified_incomplete') or
                    checked.task_outcome != result.task_outcome or not e.get('id')):
                continue
            facts.append({'id':'endpoint-' + e['id'], 'classification':'independently_verified_task_outcome',
                'validation_status':'validated_observation', 'kind':'endpoint_match' if result.task_outcome == 'verified_complete' else 'endpoint_mismatch',
                'step': e.get('step'), 'affected_page': e['observed']['url'], 'control_id':None,
                'statement': f"Configured observable endpoint: {result.task_outcome}. {checked.reason}",
                'supporting_evidence':[EvidenceReference(source='outcome_verification', step=e.get('step'),
                    phase='endpoint_inspection', field='conditions,observed', evidence_id=e['id'], url=e['observed']['url']).model_dump()],
                'limitations': checked.limitations})
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError):
        pass  # Missing/legacy/malformed verification cannot support an outcome claim.
    return facts, limitations


def prose_problem(text, role='assertion'):
    """Conservative rejection rules, NOT a semantic truth classifier."""
    text = ' '.join(str(text).split()).lower()
    proposed = (role in ('expected_behavior', 'suggested_improvement') and
                re.match(r'^(add|show|provide|display|consider|offer|clarify|label|explain|include|indicate)\b', text) and
                not re.search(r'\b(was|were|has|have|completed|succeeded|achieved|purchased|bought)\b', text))
    if not proposed and re.search(r'\b(complet(?:e|ed|ion)|succeed\w*|success\w*|accomplish\w*|achieved|purchased|bought|order placed|task failed|failed the task|reached (?:their|the|my) goal|finished (?:the|my|their) task)\b|added .{0,70}\b(?:cart|bag|basket)\b', text):
        return 'Task-outcome assertions are reserved for the independent verifier.'
    if re.search(r'\b(wcag|compliant|compliance|accessibility score|contrast ratio|screen reader|satisfaction|sus score)\b|\b\d+(?:\.\d+)?\s*(?:%|seconds?|minutes?|hours?)\b', text):
        return 'Human measurements, accessibility compliance and timing are not established by this evidence.'
    if re.search(r'\b(frustrat\w*|confus\w*|felt|feels|feeling|angry|delighted|anxious|satisfied|emotion\w*)\b', text):
        if not re.search(r'\b(may|might|could|would)\b', text) or re.search(r'\b(measured|proved|observed|was|were|felt|is|are)\b', text):
            return 'Measured or factual user emotions were not observed.'
    if re.search(r'\b(caused|causes|because|due to|therefore|proves?|proven|demonstrates?|resulted in)\b', text):
        return 'A causal or conclusive explanation is not established by browser samples.'
    if re.search(r'\b(playwright|automation error|provider|model timeout|safety boundary|safety restriction|browser crashed)\b', text):
        return 'Automation and safety limitations are not website defects.'
    return None


def reproduction(history, steps):
    last = max(steps, default=0)
    result = []
    for step, row in sorted(unique_rows(history).items()):
        if step > last:
            continue
        decision = row.get('decision', {})
        target = next((c for c in row.get('before', {}).get('controls', []) if c.get('id') == decision.get('target')), {})
        result.append({'step':step, 'action':decision.get('action'), 'control':target.get('name'),
            'url':row.get('before', {}).get('url'), 'result':row.get('result'),
            'input_omitted': decision.get('action') in ('fill','select','press','check')})
    return result


def validate_findings(proposals, history, facts):
    accepted, rejected = [], []
    catalog = {f['id']:f for f in facts}
    for index, raw in enumerate(proposals):
        problem = None
        try:
            proposal = FindingProposal.model_validate(raw)
            selected = [catalog[i] for i in proposal.observation_ids]
            if len(set(proposal.observation_ids)) != len(proposal.observation_ids):
                raise ValueError('Repeated observation IDs do not add evidence.')
            if any(f['kind'] not in ALLOWED[proposal.category] for f in selected):
                raise ValueError('Observation type does not support this finding category.')
            if any(f['affected_page'] != proposal.affected_page for f in selected):
                raise ValueError('Affected page does not match every cited observation.')
            if proposal.category == 'control_labelling' and proposal.affected_control_id is None:
                raise ValueError('A control-label finding must identify the observed control.')
            if proposal.affected_control_id is not None and any(f['control_id'] != proposal.affected_control_id for f in selected):
                raise ValueError('Affected control does not match the cited phase-specific controls.')
            for key in ('hypothesis','expected_behavior','potential_user_impact','suggested_improvement'):
                problem = prose_problem(getattr(proposal, key), role=key)
                if problem:
                    raise ValueError(problem)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            reason = problem or ('Malformed finding contract or protected output fields supplied.' if isinstance(exc, ValidationError)
                                else 'Unknown observation reference.' if isinstance(exc, KeyError) else str(exc))
            rejected.append({'id':f'rejected-{index+1}', 'classification':'unsupported_assertion',
                'validation_status':'rejected', 'reason':reason, 'proposal':deepcopy(raw)})
            continue
        refs = list({tuple(ref.items()):ref for f in selected for ref in f['supporting_evidence']}.values())
        steps = sorted({f['step'] for f in selected if type(f.get('step')) is int})
        limits = list(dict.fromkeys([SEMANTIC_LIMIT,
            'Expected behavior is a proposed usability recommendation, not a tested product requirement.',
            'Reproduction is a recorded sequence, not a replay guarantee; entered values are omitted.'] +
            [limit for f in selected for limit in f['limitations']]))
        finding = Finding(**proposal.model_dump(), id=f'finding-{index+1}',
            observed_symptom=[f['statement'] for f in selected], reproduction_steps=reproduction(history, steps),
            supporting_evidence=refs, limitations=limits, issue=TITLES[proposal.category], steps=steps,
            evidence=' '.join(f['statement'] for f in selected), recommendation=proposal.suggested_improvement)
        accepted.append(finding.model_dump())
    return accepted, rejected


def validate_review(review, history, verification=None, folder=None):
    review = review if isinstance(review, dict) else {}
    facts, execution_limits = observations(history, verification, folder)
    proposals = review.get('findings', [])
    findings, rejected = validate_findings(proposals if isinstance(proposals, list) else [proposals], history, facts)
    excluded = [r['reason'] for r in rejected]
    rows = unique_rows(history)

    def feedback_item(item, category):
        if not isinstance(item, dict):
            return None
        steps = item.get('steps', [])
        quote = ' '.join(str(item.get('evidence', '')).split())
        valid = (isinstance(steps, list) and steps and all(type(s) is int and s in rows and complete(rows[s]) for s in steps))
        # Every citation must match; one real quote cannot launder unrelated steps.
        if valid:
            valid = bool(quote) and all(any(quote in ' '.join(str(fragment).split())
                for phase in ('before', 'after') for fragment in
                [rows[s][phase].get('visible_text', '')] + [c.get('name','') for c in rows[s][phase].get('controls', [])]) for s in steps)
        problem = prose_problem(item.get('comment', ''))
        if not valid or problem or not isinstance(item.get('comment'), str) or not item['comment'].strip():
            reason = problem or 'Missing executed evidence or mismatched quotation.'
            excluded.append(category + ': ' + reason)
            rejected.append({'classification':'unsupported_assertion', 'validation_status':'rejected',
                             'reason':reason, 'proposal':deepcopy(item)})
            return None
        return {'comment':item['comment'], 'steps':steps, 'evidence':quote,
                'classification':'ux_hypothesis', 'validation_status':'requires_developer_review',
                'limitations':[SEMANTIC_LIMIT, 'Quotation anchors context only; it does not prove this interpretation or a measured feeling.']}

    feedback = review.get('persona_feedback') or {}
    feedback = feedback if isinstance(feedback, dict) else {}
    checked = {'overall_impression': feedback_item(feedback.get('overall_impression'), 'overall_impression')}
    for category in ('what_worked_well','difficult_moments','suggested_improvements'):
        items = feedback.get(category, [])
        checked[category] = [out for item in (items if isinstance(items, list) else []) if (out := feedback_item(item, category))]
    # Narrative/flow prose could smuggle unsupported emotions, causes or outcomes.
    # Keep the deterministic journey summary in the report instead.
    if review.get('experience_summary'):
        rejected.append({'classification':'unsupported_assertion', 'validation_status':'unverified',
                         'reason':'Free-form narrative is not a verified journey summary.', 'proposal':review['experience_summary']})
    raw_flows = review.get('flow_assessments') or []
    flows = [{'flow':str(f.get('flow', 'Model-proposed flow')), 'status':'attempted', 'steps':[],
              'classification':'unsupported_assertion', 'explanation':'Model flow claims are unverified; consult the independent task outcome.'}
             for f in (raw_flows if isinstance(raw_flows, list) else []) if isinstance(f, dict)]
    return {'finding_validation_version':VERSION, 'experience_summary':None, 'persona_feedback':checked,
        'findings':findings, 'verified_observations':facts, 'execution_limitations':execution_limits,
        'unsupported_claims':rejected, 'flow_assessments':flows, 'coverage_gaps':[],
        'review_validation':{'excluded_items':excluded, 'review_response_valid':isinstance(review.get('findings'), list),
            'note':SEMANTIC_LIMIT, 'semantic_accuracy_proven':False}}


def report_claim_view(report, history, folder=None):
    """Read-only compatibility projection; never grant old prose verified status."""
    report = deepcopy(report)
    if report.get('finding_validation_version') == VERSION:
        # Recompute anchors, including file availability, when a saved report is read.
        proposals = [{k:f.get(k) for k in FindingProposal.model_fields} for f in report.get('findings', [])]
        checked = validate_review({'findings':proposals, 'persona_feedback':report.get('persona_feedback')},
                                  history, report.get('outcome_verification'), folder)
        for key in ('findings', 'verified_observations', 'execution_limitations', 'persona_feedback'):
            report[key] = checked[key]
        report['unsupported_claims'] = report.get('unsupported_claims', []) + checked['unsupported_claims']
    else:
        report['findings'] = [{**f, 'classification':'unsupported_assertion', 'validation_status':'legacy_unverified',
            'limitations':['Historical model assertion; claim-level validation was not run.']} for f in report.get('findings', [])]
        report['verified_observations'], report['execution_limitations'] = observations(history, report.get('outcome_verification'), folder)
        report['claim_validation_note'] = 'Historical findings and persona prose are unverified assertions, not established defects or measured experiences.'
    return report


def proposal_schema():
    """Provider-neutral JSON schema (no refs/unions for Gemini compatibility)."""
    string = {'type':'STRING'}
    return {'type':'OBJECT', 'properties':{
        'category':{'type':'STRING', 'enum':list(ALLOWED)}, 'affected_page':string,
        'affected_control_id':{'type':'INTEGER'},
        'observation_ids':{'type':'ARRAY', 'items':string}, 'hypothesis':string,
        'expected_behavior':string, 'potential_user_impact':string, 'suggested_improvement':string},
        'required':['category','affected_page','observation_ids','hypothesis','expected_behavior',
                    'potential_user_impact','suggested_improvement']}
