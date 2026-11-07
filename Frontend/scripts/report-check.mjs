import assert from 'node:assert/strict';
globalThis.localStorage = { getItem: () => null };
const { state } = await import('../src/state.js');
const { report, reportRows } = await import('../src/pages/reports.js');
state.report = { kind: 'exploration', persona: 'Visitor', findings: [],
  journey_summary: {text: 'Recorded task <example>', outcome: 'Completion not verified'},
  review_status: 'not_completed' };
let html = report();
assert.ok(html.includes('Recorded task &lt;example&gt;'));
assert.ok(html.includes('Completion not verified'));
assert.ok(!html.includes('Flow coverage'));
state.report.outcome_verification = {reason: 'Endpoint inspected', evidence: [
  {id: 'sample-1', at: '2026-11-07', step: 1, conditions: {product_name: '<Lamp>'}, observed: {quantity: '2'}}
], limitations: ['Observable endpoint only']};
state.report.execution_status = 'finished';
state.report.journey_summary = {text: 'Cart inspected', outcome: 'Configured endpoint not satisfied'};
html = report();
assert.ok(html.includes('Configured endpoint not satisfied'));
assert.ok(html.includes('verification-sample-1'));
assert.ok(html.includes('&lt;Lamp&gt;'));
assert.ok(html.includes('Observable endpoint only'));
state.reportTab = 'Evidence';
state.evidence = [1, 2].map(step => ({step, action: 'click', result: 'executed', elapsed_seconds: 65,
  before: {}, after: {url: 'https://example.test/'}, screenshots: {after: `/step-${step}.png`},
  capture_metadata: {after: {sha256: 'identical', ready: false, pending_images: 1}}}));
html = report();
assert.equal((html.match(/<img /g) || []).length, 1);
assert.ok(html.includes('View earlier capture'));
assert.ok(html.includes('01:05'));
assert.ok(html.includes('Time not recorded'));
assert.ok(html.includes('capture unavailable'));
assert.ok(html.includes('evidence limitation'));
state.report = {kind: 'screenshot', persona: 'Visitor', findings: []};
state.reportTab = 'Overview';
html = report();
assert.ok(html.includes('Review cases'));
assert.ok(!html.includes('Persona journey evidence'));
console.log('Report rendering checks passed: legacy reports, evidence gaps, duplicate captures and screenshot reviews.');

state.report = {kind: 'exploration', persona: 'Visitor', findings: [], evidence_incomplete: true};
state.reportTab = 'Evidence';
state.evidence = [{step: 1, action: 'click', action_status: 'outcome_unknown', dispatch_state: 'started',
  evidence_gaps: ['After-observation unavailable; resulting page state is unknown.'], before: {}, after: {}}];
html = report();
assert.ok(html.includes('outcome_unknown'));
assert.ok(html.includes('Incomplete evidence'));
assert.ok(html.includes('resulting page state is unknown'));
assert.ok(reportRows([state.report]).includes('Incomplete evidence'));
console.log('Action journal rendering checks passed: uncertain dispatch, missing observations and library warning.');

state.reportTab = 'Overview';
state.report = {kind: 'exploration', persona: 'Visitor', review_status: 'completed', finding_validation_version: '1.0',
  journey_summary: {outcome: 'Completion not verified', text: 'Recorded journey only'},
  verified_observations: [{id: 'step-1-text-0', statement: 'Recorded page text: <error>', classification: 'observed_browser_event', affected_page: 'https://shop.test/form', limitations: ['Sample only']}],
  findings: [{version: '1.0', classification: 'ux_hypothesis', validation_status: 'requires_developer_review',
    category: 'error_recovery', issue: 'Review recovery guidance', affected_page: 'https://shop.test/form',
    observed_symptom: ['Recorded error text'], hypothesis: 'An example could help.', potential_user_impact: 'May help recovery.',
    expected_behavior: 'Show an example.', suggested_improvement: 'Add an email example.',
    reproduction_steps: [{step: 1, action: 'click', control: 'Continue', url: 'https://shop.test/form', result: 'executed'}],
    observation_ids: ['step-1-text-0'], supporting_evidence: [{source: 'screenshot', step: 1, phase: 'after', availability: 'missing'}],
    limitations: ['Semantic relevance is not proven']}],
  unsupported_claims: [{reason: 'Task outcomes cannot come from the model.', proposal: {issue: 'The task succeeded <script>'}}]};
html = report();
assert.ok(html.indexOf('Task outcome and recorded journey') < html.indexOf('Verified observations'));
assert.ok(html.indexOf('Verified observations') < html.indexOf('Potential UX issues'));
assert.ok(html.includes('UX hypothesis · Developer review required'));
assert.ok(html.includes('Reproduction steps from the recorded run'));
assert.ok(html.includes('Before/after evidence'));
assert.ok(html.includes('after screenshot: missing'));
assert.ok(html.includes('Suggested improvement — proposed'));
assert.ok(html.includes('Semantic accuracy has not been proven'));
assert.ok(html.includes('Unsupported or unverified assertions'));
assert.ok(html.includes('&lt;script&gt;'));
assert.ok(!html.includes('<script>'));
state.report.findings = [{issue: 'Legacy unsupported diagnosis', explanation: 'Model-declared conclusion'}];
html = report();
assert.ok(html.includes('Historical assertion: claim-level validation was not run.'));
assert.ok(!html.includes('UX hypothesis · Developer review required'));
console.log('Claim rendering checks passed: fact/hypothesis separation, reproduction, uncertainty, legacy assertions and escaping.');

assert.ok(html.includes('Perception policy: not recorded'));
for (const mode of ['neutral_passthrough', 'provisional_pilot_v1']) {
  state.report.perception_policy = {mode, parameter_status: 'provisional', human_calibrated: false,
    parameters: {candidate_budget: mode === 'neutral_passthrough' ? null : 16}, policy_rejections: 1,
    mixed_policy_history: true, recorded_decisions: [{step: 1, mode, observed_controls: 40,
      projected_controls: 16, actionable_controls: 16, rejected: true}], limitations: ['Engineering hypothesis only.']};
  html = report();
  assert.ok(html.includes(mode));
  assert.ok(html.includes('No human-data calibration is active'));
  assert.ok(html.includes('decision rejected'));
  assert.ok(html.includes('do not treat it as a matched single-mode benchmark'));
  assert.ok(html.includes('Engineering hypothesis only.'));
}
state.report.perception_policy.parameters.candidate_budget = '<script>unsafe</script>';
state.report.perception_policy.policy_rejections = '<img src=x onerror=alert(1)>';
html = report();
assert.ok(!html.includes('<script>'));
assert.ok(!html.includes('<img src=x'));
assert.ok(html.includes('&lt;script&gt;unsafe'));
console.log('Perception policy rendering checks passed: modes, provisional status, counts, mixed histories and escaping.');
