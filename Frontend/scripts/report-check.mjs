import assert from 'node:assert/strict';
globalThis.localStorage = { getItem: () => null };
const { state } = await import('../src/state.js');
const { report } = await import('../src/pages/reports.js');
state.report = { kind: 'exploration', persona: 'Visitor', findings: [],
  journey_summary: {text: 'Recorded task <example>', outcome: 'Completion not verified'},
  review_status: 'not_completed' };
let html = report();
assert.ok(html.includes('Recorded task &lt;example&gt;'));
assert.ok(html.includes('Completion not verified'));
assert.ok(!html.includes('Flow coverage'));
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
