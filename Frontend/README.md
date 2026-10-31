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
