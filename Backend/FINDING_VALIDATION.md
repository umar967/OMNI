# Claim-level UX finding validation (1.0)

Live runs, CLI runs and saved-run reviews call the same validator. Gemini and
Ollama use the same finding proposal schema. Persona calibration is unchanged.

## Trust boundary

The model cannot author a verified factual sentence. `observations()` builds a
catalog from history and separately supplied independent endpoint evidence.
The reviewer can select catalog IDs and propose an interpretation/recommendation.
The validator checks those IDs, their category, exact page and phase-specific
control. It generates the saved observed symptom and reproduction sequence.
It ignores model `task_outcome`/`verified_observations` fields and rejects attempts
to supply protected finding fields such as classification or observed symptom.

| Classification | What it means |
| --- | --- |
| `observed_browser_event` | A narrow fact derived from recorded data; not proof of a website defect. |
| `independently_verified_task_outcome` | A supported endpoint result, with verifier provenance and re-evaluated conditions/sample. |
| `ux_hypothesis` | A contextual interpretation or proposed improvement requiring developer review. |
| `unsupported_assertion` | Rejected, unverified narrative, or historical assertion; not promoted to a finding. |

Fact checks include unique integer step IDs, execution status, complete
before/after samples, exact URLs and controls, actual sampled text differences,
and configured endpoint expectations. `observed_change` flags are not trusted.
Reused numeric IDs in different phases are never assumed to identify the same
node. Missing/ambiguous controls cannot supply a control-label fact.

Facts say **page-authored text was recorded**, not that a page's statement is true.
An empty DOM-derived label is not a WCAG assessment. Unchanged URL/text/control
properties do not establish absence of a response, visibility of all content,
absence of a value edit or a technical defect. A successful browser action does
not establish task completion. Endpoint facts retain their observable-only scope.

## Saved finding contract

`FindingProposal` contains the category, exact affected page, optional control ID,
observation IDs, hypothesis, proposed expected behavior, potential user impact,
and suggested improvement. Categories are feedback clarity, navigation clarity,
control labelling, error recovery and task expectation mismatch. Category/type
checks prevent using an arbitrary label quote as evidence of a navigation failure.

The validator adds version, ID, generated title and observed symptom,
reproduction steps from recorded history, source/step/phase/field evidence
references, validation status and limitations. All accepted UX findings have
`validation_status=requires_developer_review`,
`impact_status=interpretation_not_measurement`, and
`expectation_status=proposed_usability_recommendation`.

Example: a recorded after-sample contains “Enter a valid email address.” A finding
may propose an email-format example near the field. The message is the recorded
symptom; whether the example is useful is a hypothesis. The validator does not
claim that the message caused confusion, that an example is currently absent,
or that the application violates an unstated product requirement.

An old-format finding saying “The database corrupted orders,” citing an executed
step and the true quote “Continue,” is rejected. So are mismatched pages/controls,
unknown IDs, screenshot-only references, fabricated factual emotions or timing,
compliance assertions, categorical causal explanations and model-declared success.
Explicit hypothetical impact can be retained with its interpretation label.

## Evidence and failure handling

Blocked actions, automation/provider failures, uncertain dispatch and incomplete
before/after pairs appear under execution/evidence limitations, not website
defects. A screenshot is a contextual artifact, never semantic proof. Availability,
capture-page correspondence and recorded SHA-256 are checked when files are
available; each image is hashed once per validation pass. Missing or mismatched
captures stay explicit and do not invalidate otherwise useful DOM observations.
No screenshot pixels are analyzed by this validator.

Reproduction is generated from the recorded sequence through the cited step;
entered values are omitted. It is not a deterministic replay guarantee. Endpoint
inspection may have no preceding browser action, and the report does not invent one.

Free-form experience summaries no longer replace the deterministic journey.
Legacy persona comments may survive only as contextual hypotheses requiring
review; quotation checks do not validate their semantics. Flow prose cannot
declare completion. A valid review with no findings can be completed without
inventing positive feedback or defects.

## Compatibility and limitations

Existing fields and routes remain readable. Legacy exploration assertions are
marked unverified on read without rewriting files; raw unsupported text is
available separately for inspection. New saved findings and feedback are checked
again against their current history and capture files. Screenshot-only reviews
remain explicitly unverified model interpretations; this milestone does not add
visual or accessibility verification.

The prose rejection rules are conservative English heuristics, not a semantic
truth classifier. They can over-reject legitimate wording and miss paraphrases.
All remaining model prose still carries an unverified interpretation label.
Structural/context matching does not prove semantic relevance, causality,
severity, accessibility, user emotion, timing, recommendation quality or general
task correctness. Semantic accuracy has **not** been established by these tests.

## Benchmark readiness

The pipeline is ready for controlled end-to-end provider benchmarks, not an
unqualified developer-pilot release. Use clean and deliberately problematic local
fixtures, supported endpoint contracts and held-out tasks. Run Gemini and Ollama
through both entry points; score endpoint correctness, evidence binding,
unsupported assertions, missed real issues, rejected useful recommendations and
developer actionability separately. Include negative controls with no intended
UX defects. Have developers adjudicate semantic relevance; counting valid
references is not an accuracy metric. No live-provider benchmark is claimed here.
