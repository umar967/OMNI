# OMNI Frontend

The dusk UI is a buildless ES-module application served by the backend at http://127.0.0.1:8000. It needs no npm install. Do not open index.html directly: its data comes from same-origin `/api` requests.

- `src/app.js`: routing, form actions, real run polling
- `src/api.js`: HTTP client and error handling
- `src/state.js`: backend records in memory, browser-local display preferences and draft inputs
- `src/components/`: shared layout and UI helpers
- `src/pages/`: dashboard, projects, personas, testing, reports, settings and local welcome
- `src/styles/`: original design tokens and connected-screen styles

All data screens, including overview counts and recent reports, read the Python API. API failure never falls back to sample results. The visual system in `src/styles/polish.css` extends the original sage palette with responsive layouts, light/dark surfaces and reduced-motion-aware transitions. Page entrances run on navigation, not during execution polling.

Run `npm.cmd run check` for JavaScript syntax checks. Start the complete app from the repository root using `./start.ps1`.

## Persona reports and journey evidence

Live reports now show a run-specific experience, a separate task outcome and stop reason, chronological journey evidence, candidate problems, and issue-linked recommendations. Individual exploration reports no longer show a Flow Coverage tab. Screenshot-only reports retain their review cases.

- New model reviews request a 70–120-word third-person `experience_summary` from the same history used for findings. Invalid length, nonexistent/nonexecuted citations, or unmatched quoted evidence cause the narrative to be omitted. Citation checks do not verify the truth of every narrative claim: it is labelled AI interpretation.
- Existing reports and failed reviews receive a factual `journey_summary` derived on read from saved history. No paid regeneration or modification of old evidence is needed. Task completion remains unverified; successful actions and a finished run do not establish task success.
- New viewport captures wait up to eight seconds for visible images, fonts, content and common loading indicators. Metadata records title, URL, elapsed capture time, readiness and a content hash. Timeouts remain capture limitations. CSS backgrounds, custom unmarked loading states and offscreen lazy-loaded images are not guaranteed ready. Existing captures cannot acquire missing metadata retroactively.
- Evidence retains the original before/after files for audit. The gallery collapses detailed before states after the initial step and references byte-identical new captures instead of displaying the same image again. It does not equate different screenshots with the same state merely because their URLs match. No video feature is added.

Validation: `npm.cmd --prefix Frontend run check`, `node Frontend/scripts/report-check.mjs`, and `.venv/Scripts/python.exe -m unittest discover -s Backend/tests` from the repository root. The backend suite includes a local Chrome fixture for delayed and broken images; provider responses are mocked. Live generated narrative quality still needs a real-provider pilot review.
