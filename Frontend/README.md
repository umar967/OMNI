# OMNI Frontend

The dusk UI is a buildless ES-module application served by the backend at http://127.0.0.1:8000. It needs no npm install. Do not open index.html directly: its data comes from same-origin `/api` requests.

- `src/app.js`: routing, form actions, real run polling
- `src/api.js`: HTTP client and error handling
- `src/state.js`: backend records in memory, browser-local display preferences and draft inputs
- `src/components/`: shared layout and UI helpers
- `src/pages/`: dashboard, projects, personas, testing, reports, settings and local welcome
- `src/styles/`: original design tokens and connected-screen styles

Only `pages/dashboard.js` contains illustrative records. Every other data screen reads the Python API. API failure never falls back to sample results.

Run `npm.cmd run check` for JavaScript syntax checks. Start the complete app from the repository root using `./start.ps1`.
