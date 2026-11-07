# Universal Persona Foundation (Milestone 3)

`UniversalPersona` in `schema.py` is the versioned configuration contract for
both curated presets and user-defined profiles. Presets are JSON data under
`Backend/personas/`, not agent subclasses. The existing four legacy presets and
the new Power User preset resolve through the same code. Expanding the library
does not require adding agent implementations.

## Public profile and internal runtime

The configuration has `schema_version: "1.0"`, `profile`, `calibration`, and
`provenance`. Only the profile name is mandatory; nested defaults are validated.
The profile includes description, technical experience, site familiarity,
environment/viewport/input, accessibility, perception, navigation, recovery,
and task context. Technical experience does not imply site familiarity.
No demographic field is used to derive abilities.

`resolve_persona(configuration, task=None)` returns a `RuntimeProfile`, containing
the validated configuration, effective task, internal `EngineParameters`,
capability issues and warnings. An explicit task overrides the optional default
goal. Internal parameters are not writable through the public schema. Unknown
fields and schema versions are rejected. Booleans are not accepted as viewport
dimensions or retry counts. Sizes are CSS pixels.

The engine is `foundation-1`, with `legacy_passthrough` mode and provisional
status. Behavioral simulation is disabled and active calibration IDs are empty.
Attention, navigation and recovery settings are declarations only: this milestone
does not change selection, timing, scrolling, retries, or hard-coded stop rules.
The legacy descriptive prompt remains the execution mechanism.

## API and future builder

- `GET /api/personas/schema` returns the actual Pydantic-generated JSON Schema,
  including nested defaults, enum choices, required fields and numeric ranges.
- `POST /api/personas/validate` accepts a canonical profile or legacy request and
  returns its runtime resolution, without persisting anything.
- Existing `GET/POST /api/personas` and `PUT /api/personas/{id}` remain available.
  POST/PUT accept either a complete canonical configuration or the existing flat
  name/technical_skill/goal/criteria request. Canonical PUT replaces the profile;
  legacy PUT updates its four existing fields and preserves other dimensions.

A future form must render all `profile` dimensions from the JSON Schema (or
submit against it), resolve `$ref`s, and call the validation endpoint. JSON Schema
expresses field constraints; server validation also enforces cross-field device
compatibility and calibration evidence rules. Internal parameters must not become
form inputs. API errors use HTTP 422. A structurally valid, unsupported profile
can be saved and inspected; `persona_validation` explains why it cannot run live.

Minimal canonical request:

```json
{
  "schema_version": "1.0",
  "profile": {
    "name": "Product researcher",
    "technical_experience": "advanced",
    "website_familiarity": "first_visit",
    "task_context": {
      "default_goal": "Find product specifications",
      "criteria": ["Clear labels", "Action feedback"]
    }
  }
}
```

## Migration and compatibility

Legacy files are normalized on read without rewriting them. `technical_level`
and the existing low/basic/moderate/intermediate/high/advanced aliases map to the
three technical-experience values. Existing IDs, extra legacy fields and behavior
preferences survive compatibility responses and flat edits. Unrecognized skill
values are rejected rather than assigned invented meanings. Free-text familiarity
is retained in migration notes when it cannot be mapped safely.

API responses retain flat fields for the existing frontend and add
`universal_persona` and `persona_validation`. The canonical object is authoritative;
flat aliases are regenerated from it. Historical report readers do not migrate or
rewrite snapshots. New live and CLI snapshots include a `runtime_profile`, and
CLI resume recognizes that snapshot. Screenshot review receives the legacy prompt
projection, not internal engine/calibration declarations.

The live API checks the saved plan snapshot before queuing a run. Both runners
resolve and check support before interacting. Supported execution remains desktop,
1366x768, mouse/keyboard. Mobile/tablet profiles require touch in this schema, but
touch execution, keyboard-only execution, alternative viewports, screen-reader
execution, reduced-motion emulation and enforced visual requirements are not
implemented. Such requests are reported explicitly and blocked for live runs;
they are not silently simulated. Screenshot reviews remain screenshot reviews,
not evidence that those capabilities were exercised.

Provider configuration, Gemini/Ollama calls, observations, evidence capture,
safety boundaries and frontend code remain in place. Per-client BYOK credential
isolation is a separate milestone; no API keys belong in persona configurations.

## Calibration artifact contract

An artifact declares its ID, dataset and dataset version, source, license,
fitting method, affected profile field paths, parameter status, fitting split,
evaluation split/metrics/report/leakage controls, optional SHA-256 and limitations.
Dataset names are open text so UEyes, Mind2Web and future datasets use one contract.
Statuses are `calibrated`, `research-informed`, or `provisional`.

A calibrated declaration requires a fitting split, a different evaluation split,
evaluation metrics/report/leakage description and checksum. References must name
existing profile fields; duplicate IDs are rejected. These are structural checks,
not proof of fitting, split independence, licensing, or scientific validity.
All submitted artifacts remain inactive and unverified in Milestone 3. No shipped
preset claims human calibration. A future trusted artifact loader must verify
actual files, checksums, provenance, field applicability and evaluation before use.

## Verification and next task

Run `.venv/Scripts/python.exe -m unittest discover -s Backend/tests -t . -v`
from the repository root, and `npm run check` in `Frontend/`.
Foundation tests cover preset/custom parity, invalid and missing fields, schema
versions, compatibility, non-destructive migration, task overrides, calibration
declarations, API round trips and live capability rejection.

Next: implement a shared observation-to-feature adapter and an enforceable
perception boundary for CLI and live execution. Preserve snapshot-local control
IDs, define perceived text/history projection, and add rejection tests before
activating any attention policy. Dataset fitting/evaluation and artifact trust
must precede any claim of human calibration.
