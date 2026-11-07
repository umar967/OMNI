# UEyes Stage B2A audit and pre-registered preparation plan

## Approved selective-access experiment: actual result

**Verdict: partial inspection only.** The authorized probe ran against the
official version-specific file URL on 2026-11-07 at 21:26:02 UTC (November 8
locally). One request, `Range: bytes=0-0`, returned:

```
HTTP 206
Content-Range: bytes 0-0/12912746325
Content-Length: 1
Accept-Ranges: bytes
Content-Disposition: attachment; filename=UEyes_dataset.zip
```

Range handling and expected archive length were confirmed. Neither ETag nor
Last-Modified was supplied. No content digest was supplied. Consequently content
identity could not be independently pinned for subsequent range requests. The
client stopped at that gate without reading the response body. This establishes
a limitation of this checked access route, not that all selective-access methods
are impossible. No alternate URL, retry, redirect or additional range was attempted.

Application payload bytes read: **0**. Conservatively charged payload: **1 byte**,
covering the complete declared response body if transport buffering received it.
Extraction: **0 bytes / 0 files**. These figures are below the approved combined
25 MiB and cumulative extracted 512 MiB limits. HTTP headers/TLS overhead are not
part of the payload figure; no claim of packet-level wire measurement is made.
Nonessential response cookies were excluded from the preserved evidence.

No ZIP/ZIP64 directory was obtained, so no actual member paths, compression,
CRC, image/participant matches or extraction safety checks could be established.
No genuine records or images were extracted. Coordinate overlays, exclusion
statistics, actual headers/units and presentation interpretation remain pending.
The archive's published MD5 remains unverified by local bytes.

Reproducibility files: `research/ueyes_selective.py` (preflight only, no ZIP
extraction/full-download fallback), `research/ueyes_b2a_access.json` (source URL,
range, response headers, archive size, published MD5 and accounting), and
`tests/test_ueyes_access.py`. Four offline tests pass: correct range, invalid/full
responses and missing identity, changed identity, and exhausted budget. They test
client guards, not genuine human-data correctness. `git diff --check` passed.
No runtime code changed and no full regression suite was rerun.

**Smallest next step:** obtain an author-provided small sample with a published
checksum, or a documented immutable/checksummed selective-download endpoint. A
sample needs info.csv metadata, one original webpage stimulus and its linked
participant/block gaze CSV, including presentation timing/scaling documentation.
Alternatively, propose a different identity-verification protocol for explicit
review before another experiment. Current approval does not resolve missing
content identity; no further requests or fitting are being undertaken.

The remaining sections preserve the preceding audit/design and its historical
access status; this experiment result supersedes that earlier access status.

Audit date: 2026-11-08. Status: **documentation/access audit complete; genuine-data
coordinate validation blocked pending sample access**. No dataset payload,
fitting, runtime activation or synthetic substitute was used. Existing policies
and calibration contracts remain unchanged.

## Verified inventory and evidence boundaries

The official [record](https://zenodo.org/records/8010312) displays v1, published
2023-06-06. Its [JSON API](https://zenodo.org/api/records/8010312), read directly
with a 500 KB response cap, confirms one file:

| Property | Verified metadata |
| --- | --- |
| Version-specific DOI | 10.5281/zenodo.8010312 |
| Parent/concept record | 8010311 |
| File | UEyes_dataset.zip |
| File ID | 99ae6190-d07a-458e-907e-a9dbeca63c1e |
| Size | 12,912,746,325 bytes (12.913 decimal GB; about 12.03 GiB) |
| Published checksum | md5:c2d53e6af0a47e1f459416d6839ec2c1 |
| Access / license | open / cc-by-4.0 |

The checksum is a publisher declaration, not a locally verified content hash.
At intake verify it and compute SHA-256; retain the record JSON and its hash.
License attribution must identify creators/source, link CC BY 4.0, and identify
changes; also cite Jiang et al., CHI 2023, DOI 10.1145/3544548.3581096 as requested.
Keep image provenance; a dataset license does not establish ownership of every
third-party depicted interface. [CC BY terms](https://creativecommons.org/licenses/by/4.0/)

The [official README](https://github.com/YueJiang-nj/UEyes-CHI2023/blob/main/README.md)
documents images, raw eye-tracker logs, 1/3/7-second fixation maps/heatmaps,
scanpath PNGs and info.csv. Filenames encode participant and experimental block;
info.csv documents image/category/block/train-test membership. Exact CSV headers,
category spellings and assignments have not been inspected. Its prose has a
category typo, so do not implement a literal `ebpage` filter from that prose.
Per-image decoded dimensions and actual participant/block counts remain unverified.

The [official supplement](https://yuejiang-nj.github.io/Publications/2023CHI_UEyes/project_page/supp.pdf)
describes free-viewing and detected text/image/face region boxes. The archive's
actual segmentation paths/schema have not been inspected. Detected regions do
not establish interactive controls, CSS font sizes or click targets. Raster
scanpath illustrations cannot replace numeric gaze records.

## Access result and approval boundary

The API lists no independent small data file. A bounded request to the documented
[ZIP preview](https://zenodo.org/records/8010312/preview/UEyes_dataset.zip?include_deleted=0)
returned 884 bytes of HTML containing: “Too many files inside the ZIP file.”
Thus no suitable small genuine sample was obtained through the checked sources.
This does not prove selective access is impossible. Archive HEAD/range support
was not verified: the initial sandbox network probe failed DNS; the subsequent
approved network operation requested only record JSON and preview HTML.

Stop here on data processing, as requested. No coordinate overlays, exclusion
rates, row counts, overlap counts or calibration scores can be reported yet.

Preferred next access experiment, **subject to explicit approval**:

1. Probe a single tiny HTTP byte range against the API's file-content URL. Require
   206 and exact Content-Range; abort immediately if the server returns a full
   200 response. Bound total network bytes, not just extracted output.
2. Inspect the ZIP64 end record and central directory (archive exceeds 4 GiB).
   Proposed metadata cap: 4 MiB; abort if the directory requires more.
3. If supported, list member paths, compression, CRC and compressed/uncompressed
   lengths. Select archive README, info.csv, one webpage image and its corresponding
   participant/block CSV; add region JSON only if present. Proposed total network
   cap: 25 MiB and extracted cap: 512 MiB. If a required member exceeds the cap,
   stop and request an increased budget. Do not fetch arbitrary unrelated members.
4. Check member CRC, hashes and provenance. A selective sample cannot verify the
   whole archive MD5. Reject path traversal, absolute paths, symlinks and excessive
   expansion. Keep a manifest of byte ranges and member hashes.

Alternative: explicitly approve the full archive, verify its checksum, then inspect
the central directory before extraction. Full download approval does not authorize
fitting or runtime activation.

## Resources

D: had approximately **227.17 GiB free** at audit time (Get-PSDrive). Download-only
space is 12.03 GiB. Actual uncompressed size is unknown until the ZIP directory is
available. Reserve a provisional **70 decimal GB** for archive, selective/extracted
data, diagnostics and temporary files; this is a planning allowance, not a verified
upper bound. Check member-size totals against free space and extraction quotas.

Ideal full-download times, excluding overhead/retries:

| Sustained bandwidth | Time |
| --- | --- |
| 10 Mbps | 172 minutes |
| 20 Mbps | 86 minutes |
| 50 Mbps | 34 minutes |
| 100 Mbps | 17 minutes |

Use streamed download/checksums and chunked CSV reads; do not load the entire
archive or all images into RAM. Recommended workstation: 8–16 GiB RAM, one CPU
worker initially, an explicit 2 GiB worker memory budget, one decoded image at a
time. Benchmark actual peak memory/throughput on the verified sample before
projecting full processing time. No GPU or LLM is needed. Extraction/processing
duration cannot be estimated reliably without member counts and real CSV sizes.

## Measurement semantics and coordinate-validation protocol

[Gazepoint API 2.0](https://www.gazept.com/dl/Gazepoint_API_v2.0.pdf), sections 5.2,
5.4 and 5.7, defines normalized screen coordinates with origin top-left; TIME is
seconds since initialization/calibration, FPOGD is fixation duration in seconds,
FPOGID identifies fixations, FPOGV indicates fixation validity, and BPOG* denotes
best-eye point of gaze with BPOGV validity. These are vendor definitions; actual
UEyes CSV exports must still be mapped and verified, especially stimulus-relative
time and repeated streaming rows.

The [author processing code](https://github.com/YueJiang-nj/UEyes-CHI2023/blob/main/data_processing/generate_heatmaps.py)
uses MEDIA_NAME, BPOGX/BPOGY/BPOGV and FPOGD; it renames the fourth column TIME,
clips negative gaze coordinates and drops points on/outside image borders. Its
example uses 1920×1200. These choices need audit, not blind replication. Mixing
best-point coordinates with fixation duration does not prove each row is one
independent fixation; its heatmap function counts coordinates without duration
weighting even though duration is retained in intermediate data.

For image width W, height H, presentation screen Sw×Sh, the centered aspect-fit
transform implied by that code is:

```
s = min(Sw/W, Sh/H)
ox = (Sw - s*W)/2; oy = (Sh - s*H)/2
x_image = (x_screen_normalized*Sw - ox)/s
y_image = (y_screen_normalized*Sh - oy)/s
u = x_image/W; v = y_image/H
```

Screen geometry, centering and aspect-fit are hypotheses until verified against
presentation documentation/sample overlays. Source image coordinates and OMNI
CSS viewport coordinates are different frames; record any device-scale/crop
mapping explicitly. Do not assume every image is 1920×1200.

Once a real sample is obtained:

1. Hash source files, pin official code commit/hash, decode image dimensions and
   inspect all CSV headers/types. Join participant/block filenames and MEDIA_NAME
   to info.csv and image paths; reject missing/ambiguous joins, exclude calibration
   blocks from stimulus fitting and preserve raw rows.
2. Check timestamp origins, resets, monotonicity, range and units against stimulus
   presentation. Do not apply TIME≤1/3/7 until relative onset is verified. Check
   validity flags, finite coordinates, nonnegative durations and duplicate rows.
3. Distinguish streaming samples from fixation events. If FPOGID/FPOGS/FPOGV exist,
   verify their semantics and group within participant/session/stimulus; use final
   valid event duration rather than repeatedly summing cumulative durations.
   Never silently substitute BPOG samples for fixation events. If required event
   fields are absent, define a separate gaze-sample analysis or stop fixation fitting.
4. Transform without clipping input coordinates. Count missing values, invalid
   flags, out-of-screen, in-letterbox and out-of-image points separately. Preserve
   border points with 0≤x<W and 0≤y<H for pixel indexing; record differences from
   the author's strict-interior convention. Report overlapping flags and an
   exclusive disposition so totals reconcile.
5. Produce original-image overlays showing chronological fixations, durations,
   padding boundaries and excluded points; also show a screen-frame overlay.
   Independently implement the inverse transform, test corner/center round trips,
   and compare against the author transform before filtering. Synthetic geometry
   checks establish arithmetic only, never dataset correctness.
6. Manually inspect landscape, portrait and strongly padded stimuli across blocks
   and participants; record reviewer/sign-off and unexplained offsets. Compare
   reconstructed 1/3/7-second maps with supplied maps while accounting for smoothing
   and count-vs-duration weighting. No policy fitting until anomalies are resolved.

Required outputs: per-file join audit; raw/valid/excluded/questionable counts and
rates with reasons; timestamp and duration distributions; duplicate/event audit;
transform parameters; alignment overlays; unresolved anomalies. None is populated
with fabricated values in this milestone.

## Frozen split protocol

Preserve official train/test labels verbatim in an immutable source column. Audit
image hashes, perceptual duplicate/template clusters, participant IDs and blocks
for overlap before assigning experimental roles. Website-family IDs are not
documented in the inspected inventory; derive auditable duplicate/family groups
without gaze outcomes and record uncertain grouping.

- Primary stimulus-generalization evaluation: keep official test stimuli sealed;
  derive validation from official training families using seeded group assignment.
  No image/family crosses fit/validation/test. If a family spans official training
  and test, quarantine its training copies rather than moving test data into fit.
  Group blocks where feasible; report block overlap otherwise. Participant overlap
  may remain and must be reported explicitly.
- Separate participant-generalization evaluation: freeze participant groups and
  use only official-training stimuli, holding participant-specific gaze entirely
  out of fitting/tuning. This tests new viewers on potentially known stimuli.
- Optional joint evaluation: train on training participants AND training families;
  test on held-out participants AND official-test families. Mixed quadrants remain
  excluded from fitting/test scoring. Use only if the observed incidence matrix
  provides adequate independent cells; do not assume simultaneous independence.

Freeze sorted membership lists, grouping rationale, seed (proposed 20261108),
source hashes and split-manifest SHA-256 before parameter selection. Keep held-out
gaze inaccessible to the fitting process. Publish an overlap matrix and sample
counts; actual overlaps and split sizes remain unknown until data access.

## Exact Stage B2B fitting proposal (inactive)

Primary target: normalized screenshot-space fixation-event spatial density over
webpage stimuli. Use event-count weighting and equal weight per participant/image
pair, then equal weight per image; use duration weighting only as a separately
declared sensitivity analysis after event durations are validated.

Fit a smoothed 2D histogram with grid resolution selected from {8×8,16×16,32×32}
and uniform-mixture regularization alpha selected from {0.01,0.05,0.1,0.25} by
validation log likelihood. These are proposed search settings, not attention
probabilities or empirical estimates. Set q=(1-alpha)*normalized training-bin
counts+alpha/uniform-bin-count; evaluate continuous density accounting for bin area.
No task labels, persona expertise groups, fixation test data or fixture targets
enter the features or fitting. Region size is excluded until annotations/alignment
support a separate region analysis.

Comparisons: uniform density; fixed center Gaussian with width selected solely
on validation data; fitted histogram; and the frozen existing OMNI heuristic.
The latter is a control-ranking function, not a spatial density. Compare it on
aligned, verified regions/control-retention fixtures; report pixel gaze metrics
as unavailable unless a pre-registered region-to-density conversion is justified.

Primary gaze metric: held-out mean log2 density gain over uniform, aggregated by
participant/image and image. Secondary: NSS, AUC-Judd and shuffled AUC with fixed
negative sampling; CC/SIM/KL require identically normalized maps and a predeclared
spatial smoothing rule. Report image-cluster bootstrap confidence intervals and
participant sensitivity, not row-wise pseudo-independent confidence intervals.
Never choose parameters after looking at test scores.

Separately integrate a candidate prior in an offline fixture-only adapter and
compare fixed-budget target retention, permitted coverage/exposure precision,
rediscovery, independent endpoints and evidence completeness with Stage B1.
Annotations remain evaluator-only. A gaze improvement does not imply click,
task-success, expertise or human-realism accuracy. Existing runtime weights stay
unchanged until separately authorized, trusted-artifact activation is implemented.

## Proposed artifact and approval requirements

An envelope extending the existing CalibrationArtifact should include:
artifact_schema_version; dataset DOI/version/license/attribution; source URLs and
code commits; source-file SHA-256/CRC and published archive digest; audited field
mapping/units; event grouping and exclusion rules; presentation and coordinate
transforms; feature version; all frozen split membership hashes; fitting method,
candidate grid, selected parameters and seed; baseline/held-out metrics with
uncertainty and denominators; diagnostic/sign-off references; limitations; payload
SHA-256. Compute checksum over canonical payload excluding its own checksum field.
Status remains prepared/unvalidated until genuine coordinate/evaluation gates pass.
This envelope is a design, not an accepted runtime schema or active artifact.

Future eligibility requires local checksum verification, a server-owned trust
registry/allowlist, compatible feature/policy versions and coordinate/evaluation
sign-off. Client declarations alone cannot activate calibration. Approval is needed
for the capped selective-access experiment or full archive download, and separately
for fitting after coordinate review. No commit, push or infrastructure action is
authorized by this document.

## Changes and checks

Only this report was added. No executable code or runtime behavior changed.
No Python/frontend tests were rerun for a documentation-only audit; the preceding
180-pass result is historical, not a new test execution. Run git diff --check for
this change. Data-validation tests and genuine-data overlays remain pending.
