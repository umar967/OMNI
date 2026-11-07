# Durable browser actions (journal version 1)

The live dashboard and CLI use `ActionJournal` and `execute_validated`. Persona
and model output do not set action statuses. Numeric control IDs are local to a
snapshot; the executor retains the original ElementHandle and compares a
document/node identity plus its current semantic signature. It never looks up a
replacement using an old ID. Existing report fields remain readable.

## Write order

1. Atomically persist the decision, original observation and intended target.
2. Attach the before screenshot independently (capture failure is recorded).
3. Revalidate the original handle: connection, identity, label, role, type,
   visibility, enabled/inert state, destination, form association/action/method/
   fields, input capability and current restrictions. Repeat after scrolling.
4. Persist `dispatch_state=started`, `action_status=outcome_unknown` **before**
   invoking Playwright. Capture-phase event checks also catch common changes
   caused by pointerdown/hover before click, and click before form submission.
5. Persist the returned action result immediately, before waiting for evidence.
6. Attach the after-observation and screenshot in separate writes. A missing
   after-observation remains `{}`; it is never copied from the before state.
7. Independently inspect the configured task endpoint. If after-observation
   fails, the runner retains the action and reports an unknown task outcome.

Writes flush and fsync a temporary JSON file and atomically replace history.json.
This provides process-crash resilience; hardware/filesystem power-loss guarantees
are outside the contract. Disk write failure prevents subsequent dispatch. An
interrupted dispatch remains uncertain, including on reload. The history file is
authoritative if report.json has not yet caught up after abrupt termination.

## Action statuses (separate from task outcome and run/review status)

| Status | Meaning |
| --- | --- |
| attempted | Decision saved; dispatch not recorded. `stop` records the model's intention without a browser action. |
| executed | Browser action returned successfully; no task-success implication. |
| blocked | Safety, stale/ambiguous target or duplicate protection prevented dispatch. |
| failed | Error before dispatch; execution is known not to have started. |
| outcome_unknown | Dispatch began; some input or side effect may have occurred. Never automatically retry. |

`result` retains existing values (`executed`, `blocked: ...`, `automation_error`,
`agent_stopped`) and adds `refresh_required: ...` and `outcome_unknown`.
Refresh rejection triggers a fresh observation and model decision within the
action budget. Neither runner substitutes a new element into the old decision.

Repeated side-effect actions on the same identity or semantic target/value are
blocked after success. This is intentionally conservative: identically labelled
buttons can collide. Uncertain dispatch stops the loop and prevents CLI resume.
Known pre-dispatch failure may be retried after a fresh decision. Legacy records
are displayed as having unverified dispatch; legacy automation errors also block
automatic resume. No existing histories are rewritten on read.

The Reports Library computes evidence completeness from history and actual image
files, displays partial rows and warns about legacy/incomplete evidence. Review
claims cannot cite a partial row with no after-observation as supporting evidence.

## Safety boundaries and limits

Both runners share the navigation guard (same origin, no OMNI API access), target
checks, journal and screenshot behavior. Form/destination/credential checks
supplement labels. Account submissions, purchases, payments, deletion, arbitrary
form submission, downloads and external/new-context navigation remain restricted.
Reversible identified search/cart submissions remain allowed.

This is not a sandbox for hostile application JavaScript: listeners already
registered on window, custom handlers, service workers, network requests and
server-side effects cannot be fully inferred from DOM semantics. An event guard
cannot undo earlier input events or server effects. Event-guard rejection after
dispatch is therefore **unknown**, not a safe retry. Changes without any observable
semantic difference (e.g. a replaced JS listener) are not detectable. No exactly-once
server transaction guarantee is claimed. Iframes and shadow-DOM controls remain
outside the existing observer. Use disposable development data.

Tests use local HTML in real Chrome plus fault-injected live/CLI runs; they do not
establish end-to-end model reliability or general task correctness. The next P0
is claim-level report validation: quoted text alone must not support a fabricated
usability defect, causal conclusion or simulated human experience. Follow that
with reproducible provider-backed pilot benchmarks.
