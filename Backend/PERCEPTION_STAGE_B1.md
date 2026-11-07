# Stage B1: geometry-linked observations and retention evaluation

Implemented policy version: `stage-b1-1`. Text contract: `geometry-text-1`.
Benchmark contract: `retention-1`. All policy numbers remain provisional.
No human data were fitted, no models were trained, and no model/API calls or
dataset downloads were used for this milestone's evaluation.

## Implemented changes

| Area | Files | Behavior |
| --- | --- | --- |
| Observation | `text_observations.py`, `explore_website.py` | Adds structured text alongside the existing flat text, controls and handles |
| Perception | `persona_engine/text_policy.py`, `perception_v1.py`, `schema.py`, `session.py` | Shared text filtering, profile fields and explicit cumulative scans |
| Both runners/providers | `app/live.py`, `explore_website.py`, `agents/exploration_agent.py`, `agents/local_persona.py` | Advertises scan availability; records scans without browser dispatch; fresh observations after scans |
| Evidence/findings | `action_journal.py`, `finding_validation.py` | Text gaps are explicit; fragment citations preserve identity across filtering; transient Windows replacement locks retry only file replacement |
| Reports | `../Frontend/src/pages/reports.js`, `../Frontend/scripts/report-check.mjs` | Existing policy detail shows scan and text coverage; historical reports still render |
| Offline evaluation | `benchmarks/contract.py`, `retention_metrics.py`, `geometry_retention.py`, `fixtures/retention_v1.json` | Typed manifest, evaluator-only annotations, source/manifest hashes, real Chrome fixtures and metrics |
| Regression tests | `tests/test_geometry_perception.py` | Geometry, privacy, partial evidence, scanning, claim identity, split validation and runner parity |

The repository `.gitignore` also excludes generated `retention_b1_*` artifacts;
the fixture manifest and source are tracked candidates, while run evidence stays local.

BYOK configuration, persona calibration activation, existing execution safety and
independent endpoint strategies were not changed. The Universal Persona schema
accepts old profiles through additive defaults; the policy version/hash changes,
so older projected histories are not silently replayed into the new policy.

## Structured text and exposure

Each text block records normalized text, a bounding rectangle and line rectangles
in CSS viewport pixels, clipped intersection rectangles/fraction, CSS visibility,
effective opacity, quality flags, deterministic control IDs where available, and
an association status. Structural-path IDs are stable only for an unchanged DOM
structure; content fingerprints include that ID and text. Neither is a locator
or an execution identity. Original numeric control IDs and element handles remain
the authority for target revalidation.

Associations use control containment, HTML labels and ARIA `labelledby`,
`describedby`, `errormessage`, `details` and `controls` references. Association
with an offscreen/non-observed control is marked incomplete. Unassociated text
is explicitly marked `semantic_association_unknown`; proximity is not used to
invent an association. This allows standalone instructions, product names and
feedback to remain available under the text budget.

Collection is bounded at 4,000 visited text nodes, 256 text blocks, 500 characters
per block and 32 line rectangles per block. Limits and partial/unavailable status
are recorded. Text clipped at the viewport or an overflow ancestor is recorded
with its intersection but withheld from model text: exposing the entire string
would also expose invisible characters. Complex clipping and occlusion are not
proved. CSS-generated text, canvas, frames and shadow DOM are not fully supported.

New model views reconstruct flat text from permitted structured blocks; they
never fall back to the old raw string when structured text is partial/unavailable.
If collection is unavailable, control labels/options and title/URL are also
withheld because reflected-value privacy screening could not complete.
Legacy observations without this contract retain Stage A behavior: neutral can
use legacy flat text; pilot withholds it. Raw historical evidence is not rewritten.

Associated text must reference only exposed controls. Known excluded labels and
their copied occurrences (including adjacent text-node copies) are withheld.
Conflicting names/metadata on exposed controls are redacted; a redacted label
cannot generate an unlabelled-control finding. Title/URL and other model fields
are also screened against known excluded labels and sensitive values.

Input/textarea/editable contents, marked private regions (`data-omni-private` or
`data-private`), reflected field values, obvious email addresses and card-like
digit sequences are conservatively screened. Private values used for matching
stay in the page; only affected control IDs/title/URL flags leave that check.
This is not comprehensive PII detection: arbitrary secrets, indirect semantic
references and visual occlusion cannot be guaranteed absent. Conservative matching
can also withhold useful text. Full screenshots and existing raw evidence remain
developer evidence and can contain private content; this is not a redaction tool
for all persisted artifacts.

Provider decisions and reviews use the same permitted projections and sanitized
history. Evaluator annotations are never sent to either. Finding text references
use fragment ID plus content fingerprint, not filtered line position; malformed
or mismatched fingerprints cannot establish a text observation. Independent task
verification continues to inspect the trusted browser state directly.

## Explicit scanning policy

The modes remain `neutral_passthrough` (default) and `provisional_pilot_v1`.
Neutral exposes all observed controls, subject to existing actionability/safety,
and up to the collector's 256 eligible text blocks; it does not scan.

Additive canonical profile settings:

```json
{"perception": {"attention":"standard", "label_preference":"neutral",
  "text_budget":80, "scanning":"progressive", "max_scan_passes":3}}
```

`text_budget` accepts 0–256; `max_scan_passes` accepts 0–16; scanning can be
`progressive` or `disabled`. Pilot mode uses the configured budget. Neutral's
effective budget and the configured profile budget are separately recorded.
All defaults are engineering limits, not estimated human parameters.

Pilot keeps Stage A's unchanged 16/24/32 control budgets and attention offsets.
An explicit `scan`, target `-1`, expands the current control-layout view to the
next cumulative budget: a standard beginner gets 16, then 32, 48 and 64 controls.
The text budget expands cumulatively too. Reobserving/waiting does not itself
expand exposure. Scrolling changes the viewport and can expose new controls.
The same-view scan cap and overall run action limit remain authoritative.
More than 64 candidates can remain excluded for this default beginner view;
the report exposes counts and scan exhaustion. Use another viewport/scroll,
explicit profile limits or neutral mode for broader coverage. No unbounded
rediscovery or human scanpath behavior is implemented.

Scanning is journaled as `action_kind=perception`, result `perception_scanned`,
with `dispatch_state=not_dispatched`; it is not a browser event or task success.
Both runners immediately take a fresh observation. Actual browser actions still
pass permitted-target validation, the original handle revalidator, side-effect
duplicate prevention and navigation/form safety guards.

## Evaluation format, metrics and leakage controls

The manifest specifies suite/policy versions, interface/task/family IDs, fixture,
persona configuration, split, public task description, expected endpoint and
evaluator-only target selectors/criticality. The harness passes only the resolved
task/persona, permitted view and sanitized history to the driver. Ordinary DOM
IDs may naturally appear in observations; they are not evaluator annotations.

Each target selector must identify exactly one fixture control. Invalid/ambiguous
annotations invalidate retention ratios. Every ratio records numerator and
denominator; a zero denominator produces `null`, never an invented zero/one.

- Task-target retention: exposed annotated targets / all annotated task targets.
- Visible-target retention: exposed targets / currently observed annotated targets.
- Actionable-target retention: permitted actionable targets / annotated targets.
  A disabled control may be retained but not actionable.
- Permitted-control coverage: permitted actionable controls / enabled observed controls.
- Exposure precision: exposed annotated controls / all exposed controls. It does
  not imply other controls are irrelevant or bad to expose.
- Cumulative critical retention and critical targets retained following scans or
  scrolling, with exposure and actionability separated.
- Repeated ineffective interactions: repeated semantic actions with complete,
  unchanged sampled before/after state; incomplete pairs remain unknown.
- Invalid-action and safety-rejection counts, independent task outcome, raw text
  observation completeness and evidence-complete recorded decisions.

Evidence completeness requires before/after screenshot evidence, an after-sample,
durable journal metadata and no partial/unavailable structured text sample.
Its denominator includes scans and stop decisions. A narrower permitted text
view is separately marked limited; it is not automatically missing raw evidence.
Metrics read the persisted journal, not an unsaved in-memory result.

All five supplied fixtures are **development engineering regressions**, not an
untouched test set. The deterministic driver matches task words to permitted
labels, scans if offered, scrolls when possible, and stops otherwise. This tests
wiring and observability; it is not a benchmark of autonomous model decisions.

For a future held-out suite: allocate whole website/template families to one split,
deduplicate screenshots/layout variants before allocation, and freeze task/target
annotations, endpoint contracts, persona configurations, source hashes and budgets
before scoring. The contract rejects duplicate interface/task cases and family,
interface or fixture variants crossing splits. Source and manifest hashes are
saved. Automated family checks rely on truthful family labels and cannot detect
all visual duplicates. Have the evaluator own test annotations; fit only on a
separate human-data training set, tune only on validation, and evaluate the test
set once per frozen candidate. Changes informed by these shipped fixtures remain
development changes. No attention weights were fitted to them.

## Actual Chrome evaluation

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m Backend.benchmarks.geometry_retention
.\.venv\Scripts\python.exe -m unittest discover -s Backend/tests -v
node Frontend/scripts/check.mjs
node Frontend/scripts/report-check.mjs
git diff --check
```

Actual final benchmark: `results/retention_b1_20261107_210458/summary.json`
(UTC directory timestamp; run on November 8 locally). Ten runs, five local
fixtures × two modes, fresh Chrome contexts, one standard beginner profile.

| Fixture | Initial target retained: neutral / pilot | Final retained | Independently verified outcome, both modes |
| --- | --- | --- | --- |
| Clean listing | 1/1 / 1/1 | 1/1 | verified_complete |
| Dense/peripheral target | 1/1 / 0/1 | 1/1; pilot needed two explicit scans | verified_complete |
| Below fold | 0/1 / 0/1 | 1/1 after scrolling | verified_complete |
| Disabled control | 1/1 / 1/1 | Exposed, 0/1 actionable | unknown |
| Error message instead of listing | 1/1 / 1/1 | 1/1 | unknown |

Dense initial permitted coverage was 40/40 neutral and 16/40 pilot. Initial
exposure precision was 1/40 and 0/16 respectively; after two pilot scans it was
1/40. All ten runs had complete recorded evidence (16/16 decisions), valid
annotations and no harness errors. Six endpoints matched; four remain unknown
because the configured listing was not inspectable. There were zero repeated
ineffective interactions or invalid-action rejections from this scripted driver;
adversarial tests exercise positive rejection and repetition counters separately.

Full `observe()` time ranged 44.505–763.635 ms (median 124.729 ms); `perceive()`
ranged 0.480–9.656 ms (median 0.8715 ms) over these small fixtures. These are local
measurements, not capacity guarantees. Collection currently walks DOM text and
checks associations against controls, so large pages can cost substantially more;
geometry, text blocks and projected history also enlarge atomic journal writes.

The first benchmark attempt encountered transient Windows journal replacement
locks and retained incomplete/uncertain evidence. A bounded 50/100/200 ms retry
now applies only to atomic file replacement for Windows sharing/access errors;
persistent failures still abort, preserve the old file and cannot replay a browser
action. The failed evidence remains in `results/retention_b1_20261107_205136`.

Final validation: **180 Python tests passed, zero failed**, including real Chrome
fixtures. Frontend JavaScript syntax, report rendering and `git diff --check`
passed. Recorded benchmark source hashes match the final implementation files.
No independent human-data held-out evaluation has been performed.

## Stage B2: exact intake requirements and proposed scope

This section is a design, not an implemented loader or calibration claim.
The official UEyes README documents images, raw eye-tracker CSVs, 1/3/7-second
fixation/heat maps and scanpath images, and `info.csv` with image/category/block/
train-test metadata. It does not document Playwright DOM/control IDs or task
success labels. [Official dataset README](https://github.com/YueJiang-nj/UEyes-CHI2023/blob/main/README.md)

The supplement additionally describes per-UI segmentation JSON with **detected**
image, text and face boxes and free-viewing saliency intervals. These are not
verified interactive-control annotations. Their actual archive paths, field
schema and alignment still require intake inspection; no segmentation files
were downloaded here. [Official supplement](https://yuejiang-nj.github.io/Publications/2023CHI_UEyes/project_page/supp.pdf)

The published v1 archive is `UEyes_dataset.zip`, 12.9 GB, listed MD5
`c2d53e6af0a47e1f459416d6839ec2c1`; bytes were **not** downloaded or verified.
[Versioned archive record](https://zenodo.org/records/8010312). The university
catalog lists CC BY 4.0; retain the actual release's license and attribution with
the intake manifest. [Aalto dataset catalog](https://research.aalto.fi/en/datasets/ueyes-understanding-visual-saliency-across-user-interface-types/)

The authors' processing code reads `MEDIA_NAME`, `BPOGX`, `BPOGY`, `BPOGV` and
`FPOGD`, and renames the fourth CSV column to `TIME`. It derives participant/block
from filenames and transforms screen coordinates through image scaling/padding.
The example processing configuration uses 1920×1200. Verify actual headers,
units and presentation transforms before importing; do not blindly copy positional
column renaming. [Official processing code](https://github.com/YueJiang-nj/UEyes-CHI2023/blob/main/data_processing/generate_heatmaps.py),
[processing instructions](https://github.com/YueJiang-nj/UEyes-CHI2023/tree/main/data_processing)

Required B2 intake contract:

| Required data | Validation / purpose |
| --- | --- |
| Release ID/DOI/version, license text, attribution, source URL, archive checksum and per-file hashes | Reproducible, authorized provenance; verify bytes at intake |
| Stimulus ID, original image, decoded width/height, UI category, block, published split | Join every observation to exactly one screenshot; initially restrict to the webpage subset |
| Participant/session identifier and stimulus association | Keep repeated participant/stimulus samples together; quantify participant variation without demographic inference |
| Raw gaze/fixation coordinates, validity indicator, timestamp, duration and units | Reject invalid/nonfinite rows; establish whether repeated stream rows represent one fixation; document grouping/deduplication |
| Recorded presentation dimensions, scaling, padding, origin and coordinate convention | Reconstruct screenshot-pixel coordinates; validate overlays before normalizing by image width/height; document any mapping to OMNI CSS viewport pixels/device scale |
| Published 1/3/7-second fixation maps, their dimensions and generation rules | Cross-check reconstructed spatial distributions; scanpath PNGs alone are not numeric fixation records |
| Website/template or duplicate-family groups, plus frozen train/validation/test assignments | Enforce stimulus/family separation; where site IDs are unavailable, establish duplicate groups before splitting |
| Optional verified region/control boxes and their extraction/annotation quality | Necessary to evaluate element-level fixation retention, area/label/font effects; DOM roles and CSS fonts are not established by screenshots |
| A calibration manifest with feature version, preprocessing, fitting method, seeds, split hashes, metrics, uncertainty and artifact hash | Use the existing calibration contract, plus a future server-approved artifact loader |

**First defensible scope:** a screenshot-space spatial prior from valid gaze on
webpage stimuli, evaluated against uniform and center-bias baselines on separate
stimuli/participants. A lightweight binned or regularized statistical fit needs
no LLM training. Adopt element-level calibration only if matching region boxes
and reliable screen-to-region alignment are available and verified. Availability
of matching interactive-control annotations in the selected release has not been
established here; documented detected text/image/face boxes are a different target.
Treat estimates from OCR/detection as estimates, not ground-truth DOM metadata.

UEyes documentation inspected here does not establish expertise/familiarity
groups, task-target relevance, scroll actions, retries, abandonment, frustration
or task completion. Those remain unsupported calibration targets for this intake.
Do not fit the 16/24/32 expertise budgets or scan-pass counts from these assumptions.
Free-viewing gaze is not equivalent to task-driven control discovery. Human-data
fitting, held-out statistical evaluation, artifact activation and any claim of
improved human realism remain future work.
