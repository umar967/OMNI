# Persona perception Stage A

The supplied `perception_v1.py` and seven starter tests are integrated as an
uncalibrated scenario policy, version `stage-a-1.1`. No human datasets have been
fitted or evaluated. A different candidate budget does not establish expertise,
attention, confusion, or human behavior.

## Modes and use

Set `OMNI_PERSONA_POLICY` in the backend environment or `Backend/.env`, then
restart the backend. The CLI reads the same setting.

| Mode | Model observations | Status |
| --- | --- | --- |
| `neutral_passthrough` (default) | All controls returned by the existing observer and its flat text, with internal execution metadata and entered values removed | Compatibility baseline; not calibrated |
| `provisional_pilot_v1` | Deterministically ranked control subset; flat text omitted because it cannot be safely linked to permitted elements | Provisional engineering hypothesis |

Pilot budgets are 16/24/32 for beginner/intermediate/advanced, adjusted by
focused/standard/broad attention (-8/0/+8), minimum 8. The score weights are
centrality 0.40, visible area 0.30, label presence 0.20 and font size 0.10.
These numbers come from the supplied starter package, not statistical fitting.
All weights, scales, budget and text policy are recorded with a policy version
and configuration hash. Canonical profiles with identical settings use the same
policy whether supplied as a built-in preset or a custom persona.

CLI custom profiles use `--persona path/to/persona.json`; legacy JSON and
Universal Persona JSON both go through the existing resolver and capability
checks. Unsupported devices, input modes and accessibility simulation remain
rejected. New UI and API fields are unnecessary for selecting the server policy.

## Boundary and safety

`persona_engine/session.py` owns the shared integration used by `app/live.py`
and `explore_website.py`:

1. Resolve the persona and reject unsupported capabilities before opening a browser.
2. Observe using the existing Playwright observer; retain the full observation and
   original element handles on the execution side.
3. Project a permitted model view and sanitized history. Provider arguments are
   copied so they cannot mutate the policy snapshot.
4. Persist the decision, permitted view, policy provenance, diagnostic counts
   and allowed IDs in the existing durable journal before dispatch.
5. Reject malformed, disabled or excluded target IDs, durably record the rejection
   and obtain a fresh observation. IDs are never renumbered or rebound.
6. For permitted decisions, invoke the existing journal/execution revalidator,
   duplicate-action prevention, navigation guard and safety restrictions unchanged.
7. Attach full after-observations/screenshots and a separate permitted after-view.
   A missing after-view remains unavailable; it is not an empty observed page.

Both Gemini and Ollama receive permitted observations. Ollama's additional
30-control cap was removed so the shared policy owns the candidate budget.
Entered values, arbitrary metadata, raw errors, model reasons, raw history
observations and full-view change flags are not replayed into model history.
Safe change flags are recomputed from permitted views.

Reviewer calls, including saved-run reviews, also receive only permitted history.
Independent endpoint evidence is not sent through this model boundary. Endpoint
verification and deterministic claim validation continue to use full trusted
browser evidence; only those components can establish their narrow observations.
Screenshots remain full browser evidence for the developer, not perception inputs.

Old or mismatched policy histories fail closed for model replay. Historical
reports remain readable and show `legacy_unrecorded`. A resumed run containing
different policies is labeled mixed and is unsuitable for a matched comparison.
The journal's existing refusal to resume uncertain dispatch is preserved.

## Changes to the starter package

- Cache keys include numeric IDs, viewport and style inputs; reindexing cannot
  silently reuse stale candidate IDs.
- Nested metadata is allowlisted and deep-copied; input contents become a boolean
  `filled` marker. Invalid/duplicate observation IDs fail closed.
- Target validation rejects booleans, floats, missing IDs and inappropriate targets
  for non-target actions. This supplements execution-time revalidation.
- History projection checks policy version/configuration and cannot reconstruct
  missing permitted observations from full evidence.
- Reports include parameters, step counts, rejected decisions, mode and explicit
  absence of active human calibration artifacts. Report rendering escapes values.

## Reproducible checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s Backend/tests -v
node Frontend/scripts/check.mjs
node Frontend/scripts/report-check.mjs
git diff --check
```

The integration tests exercise both runner paths in both modes, canonical custom
and built-in profiles, provider prompt boundaries, historical reports, absent
after-views and durable rejections. Real Chrome fixtures verify geometry selection,
stale meaning rejection and duplicate-action prevention. Existing endpoint,
finding, safety, API and persona tests remain active.

An optional bounded local comparison uses the already installed Ollama model:

```powershell
.\.venv\Scripts\python.exe -m Backend.benchmarks.perception_stage_a --model qwen3:4b --max-actions 2 --timeout-seconds 60
```

It creates fresh Chrome contexts for prominent/peripheral target scenarios and
both modes, serves local HTML, uses the shared policy/journal/executor, and checks
an explicit product-listing endpoint independently. It saves timings, retained
candidates, actual decisions, histories, screenshots and endpoint evidence under
ignored `Backend/results/exploration_stage_a_*` directories. It never downloads
a model or calls Gemini. This is a small wiring/behavior comparison, not a full
dashboard, review-quality, human-realism or developer-pilot benchmark.

### Observed local comparison, 2026-11-08 (Asia/Karachi)

Actual artifact: `results/exploration_stage_a_20261107_200422/comparison.json`
(directory timestamp is UTC). Chrome and the installed `qwen3:4b` were used;
each scenario had at most two decisions and a 60-second per-request timeout.

| Scenario / mode | Relevant target retained | Independently checked outcome | Model request seconds |
| --- | --- | --- | --- |
| Prominent / neutral | Yes, 40 controls | unknown; provider timeout before any decision | 60.018 |
| Prominent / pilot | Yes, 16 controls | verified_complete; listing observed | 24.202 |
| Peripheral / pilot | No, 16 controls | unknown; endpoint not inspectable | 22.665, 11.081 |
| Peripheral / neutral | Yes, 40 controls | verified_complete; listing observed | 4.951 |

The peripheral pilot run scrolled once, then proposed `scroll` with target 10;
the guard rejected this non-target action before dispatch. No hidden target was
substituted. Its hidden listing is not an inspectable failed expectation, so the
verifier correctly retained `unknown`. The pilot withheld flat text as designed.

Measured `perceive()` time was 1.496–4.008 ms for these 40-control observations;
this excludes history projection, journaling, browser work and inference. The
successful pilot requests used about 600 input tokens; the successful baseline
request used 1,318. Cold/warm model state and request order were not controlled,
so neither latency superiority nor comparative success rates are established.
Two of four runs reached the configured endpoint; the others remain explicitly
unverified. The initial harness attempt failed on a route callback argument
before inference; the callback was fixed before the recorded comparison.

The full regression suite passes 161 Python tests, including real Chrome
fixtures; JavaScript syntax and report rendering checks pass. No paid provider
benchmark was run. Keep neutral mode as the default; pilot mode is ready for
controlled engineering comparisons, not a realism claim or a general pilot gate.

## Limits and Stage B prerequisites

Restricted mode can omit the only relevant control and all non-control feedback,
product names and error messages. This is a coverage limitation of the current
policy, not evidence of a website defect or a human failing to notice something.
DOM names and labels are not a complete visual-perception model. Navigation,
recovery, familiarity and accessibility policies remain descriptive.

Neutral mode can produce larger prompts now that the provider-specific candidate
cap is gone; inference latency and context limits depend on the selected provider.
Per-step projected views also enlarge the atomic journal. Ranking is O(n log n),
and the view cache grows with distinct observed states within the bounded run;
the fingerprint memory is diagnostic, not a fitted cross-step attention model.

Stage B can build on normalized geometry/quality flags, mode comparisons and
versioned provenance. It still needs authoritative dataset/license inspection,
an offline fitting/evaluation pipeline, dataset/site-disjoint splits, frozen
feature definitions, measured baselines and a server-approved artifact loader.
The existing calibration contracts do not activate caller-supplied claims.
Do not infer hesitation, confusion, abandonment or persona realism from successful
action traces. Before expanding the heuristic, add safe geometry-linked text
observations and evaluate retention of task-relevant controls against the baseline.
