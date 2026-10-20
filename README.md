# OMNI

OMNI is a local persona-based UX evaluation workspace. Its dusk frontend connects to the existing Python/Gemini screenshot evaluator, your persona JSON files and your saved evaluation reports.

**OMNI workspace:** http://127.0.0.1:8000/

**Evaluation target (OMNI-TestLab):** http://127.0.0.1:5173/

These are separate applications. Keep TestLab on port 5173; OMNI's frontend and API share port 8000.

## Structure

```text
OMNI/
├── Frontend/
│   ├── index.html
│   ├── package.json              # JavaScript check only; no install/build needed
│   ├── scripts/check.mjs
│   └── src/
│       ├── app.js                # Router, form actions, real execution polling
│       ├── api.js                # Same-origin backend client
│       ├── state.js              # Preferences and draft inputs
│       ├── components/           # Layout and shared UI helpers
│       ├── pages/                # One module per screen group
│       └── styles/               # Original dusk UI and connected-screen styles
├── Backend/
│   ├── app/                      # API, schemas and atomic JSON storage
│   ├── agents/persona_agent.py   # Original evaluator, now reusable by API/CLI
│   ├── personas/                # Your original and newly saved personas
│   ├── results/                 # Your original and newly generated reports
│   ├── screenshots/             # Your original, uploaded and captured images
│   ├── projects/                # Created on first use
│   ├── plans/                   # Persisted review plans, created on first use
│   ├── runs/                    # Live execution state/logs, created on first use
│   ├── tests/                   # Isolated integration regression tests
│   ├── .env.example
│   ├── main.py                  # Optional direct CLI
│   └── requirements.txt
├── OMNI-TestLab/                # Existing evaluation target submodule, unchanged
├── start.ps1
└── PRESENTATION.md              # Two click-through presentation flows
```

## Install and start on Windows

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Backend/requirements.txt
Copy-Item Backend/.env.example Backend/.env
```

Edit `Backend/.env` locally. Set `GEMINI_API_KEY` to your key, and `GEMINI_MODEL` to a model available to that key. The original program's model name, `gemini-3.8-flash`, is preserved as the default; availability is not assumed. Existing saved reports, personas and plan preparation work without a key. New evaluations require a working key/model and network access. A root `.env` is also supported for existing setups; environment variables take precedence. Never put secrets in frontend files or commit `.env`.

```powershell
.\start.ps1
```

Open **http://127.0.0.1:8000/**. Keep this terminal running. Stop with Ctrl+C. On macOS/Linux, use the equivalent virtual-environment Python and run `python -m uvicorn app.server:app --host 127.0.0.1 --port 8000` from `Backend/`.

### Start the evaluation target separately

```powershell
git submodule update --init --recursive
cd OMNI-TestLab
npm.cmd install
npm.cmd run dev
```

TestLab opens at **http://127.0.0.1:5173/**. See its own README for demo credentials, deliberately planted UX issues and reset instructions. It is not moved into Frontend: it is the website being evaluated, not OMNI's UI.

## Connected workflow

1. Choose a persona from **Persona Library**, or create/edit a persona. Saving writes to `Backend/personas`.
2. In **Testing Deck**, enter the task and page URL. Choose the existing `signup.png`, upload a PNG/JPEG up to 10 MB, or capture the local TestLab page.
3. **Prepare review plan** creates editable criteria from the selected persona. This preparation is deterministic, not an AI-generated browser action plan.
4. Select/edit/add/remove cases, then start evaluation. One Gemini request reviews the screenshot using the selected criteria.
5. **Execution Monitor** displays actual backend stages and logs. Successful analysis saves the report and links to **Report Viewer**.
6. Reports show the returned findings, severity, persona impact, visible evidence, recommendations and recorded context. Export downloads the actual report JSON.

**Dashboard only** keeps the prototype's sample metrics/cards. Every other data screen reads your backend. Failed requests never become fake results.

### Capture behavior and current limits

- Capture uses installed Google Chrome through Playwright, in a separate visible window. It loads the supplied TestLab URL, takes a screenshot and closes. A fresh session is used; it does not inherit your login, cart or checkout state. For those states, navigate manually in TestLab, take a screenshot and upload it.
- Automated capture is restricted to `localhost`/`127.0.0.1` on port 5173. Upload works when Chrome is unavailable. External page resources are blocked during capture.
- The backend implements **screenshot UX analysis**, not functional QA, autonomous journeys, pause/resume or task completion checks. Unsupported modes are disabled in the UI. There are no fabricated pass rates or quality scores outside Dashboard.
- Original JSON reports did not record a URL, run date, model, per-case outcomes or screenshot linkage. These remain unassigned rather than being inferred. Their original findings are preserved.
- Welcome/onboarding is local workspace entry, not account authentication. The API is intended for loopback use only and is not suitable for public deployment without authentication and storage changes.
- Gemini receives the selected persona, task, selected review criteria and screenshot when you start a run. Review your screenshot before sending it.
- New runtime records are saved locally and ignored by Git. The two original personas/reports and original screenshot remain tracked. Existing reports are independent snapshots; later persona edits do not rewrite them.
- Interrupted runs are marked failed on backend restart. Model/network/quota errors produce a failed run and no fabricated report.

## Direct evaluator CLI

```powershell
.\.venv\Scripts\python.exe Backend/main.py --task "Create an account"
```

Defaults are resolved relative to Backend, regardless of the current directory. Optional `--persona`, `--screenshot` and `--output` accept explicit paths. The default output is `Backend/results/cli_report.json`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r Backend/requirements-dev.txt
cd Backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd ../Frontend
npm.cmd run check
```

Integration tests use temporary data and a stubbed model; they never call Gemini or overwrite your records. The old root `test_api.py` connectivity-only script was removed. Keep the integration suite: it verifies the application's actual data flow and failure behavior.
