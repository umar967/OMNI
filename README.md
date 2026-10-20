# OMNI

OMNI is an AI-powered UX testing prototype. It evaluates screenshots using Gemini and explores live websites with a first-time-user persona using Playwright and either Gemini or a local Ollama model.

## Features

- Persona-based screenshot and live website evaluation
- Screenshot analysis with Gemini
- Evidence-based findings with severity levels
- Structured JSON reports

## Project structure

```text
OMNI/
|-- Backend/
|   |-- app/                 # API routes, schemas, and storage
|   |-- agents/              # Screenshot evaluation and exploration logic
|   |-- personas/            # Shared persona definitions
|   |-- screenshots/         # Sample and uploaded evidence
|   |-- results/             # Reports and saved exploration sessions
|   |-- screenshot_meta/     # Uploaded screenshot metadata
|   |-- tests/               # Python tests
|   |-- main.py              # Screenshot evaluation CLI
|   |-- explore_website.py   # Live exploration CLI
|   |-- review_saved_run.py  # Saved-run review CLI
|   |-- flow_coverage.py     # Flow coverage logic
|   |-- flow_catalog.json   # Known flow definitions
|   |-- PRESENTATION.md      # Demonstration guide
|   |-- .env                 # Backend credentials (not committed)
|   |-- .env.example         # Configuration template
|-- Frontend/                # OMNI UI, styles, and UI checks
|-- requirements.txt         # All Python runtime and test dependencies
|-- start.ps1                # Start the API and serve the frontend
|-- README.md
```


## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/umar967/OMNI.git
   cd OMNI
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   On Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Copy `Backend/.env.example` to `Backend/.env` and add your Gemini API key:

   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

   The `Backend/.env` file is ignored by Git and should never be committed.

## Usage

Run these commands from the OMNI repository root. Start the workspace with `./start.ps1` and open http://127.0.0.1:8000/.

To run a persona-based UX evaluation:

```bash
python -m Backend.main
```

By default, `Backend/main.py` evaluates `Backend/screenshots/signup.png` using the older-user persona and writes the result to `Backend/results/older_user_report.json`. Use `--persona`, `--screenshot`, `--task`, and `--output` to override these defaults; run `python -m Backend.main --help` for details.

## Report format

Each finding includes:

- The UX issue and category
- A severity level (`Low`, `Medium`, or `High`)
- An explanation of its impact on the persona
- Visible evidence from the screenshot
- A practical recommendation

## Live first-time-user exploration

Start the website locally, then run:

```powershell
python -m Backend.explore_website --url http://127.0.0.1:5173/ --max-actions 40
```

The runner loads `Backend/personas/first_time_user.json` and uses Gemini to choose each
next action from the current viewport, with previous actions and observations as
memory. It highlights the target and continues automatically; no Enter prompts.
By default, each decision and the final review use the Gemini API. Successful
requests have no artificial spacing. Action requests use a 30-second HTTP timeout;
final reviews use 60 seconds. Temporary network/server failures get one retry
after two seconds, with SDK retries disabled to avoid nested retry loops.
Quota errors are retried only when the API supplies a retry delay of at most
10 seconds; longer or unspecified waits stop promptly and preserve history.
A model failure skips the final review to avoid immediately hitting the same
failure again. Use the saved-run reviewer later to review preserved interactions.
Set `GEMINI_MODEL` to a model available to your key. Optional settings are
`GEMINI_ACTION_TIMEOUT_SECONDS`, `GEMINI_REVIEW_TIMEOUT_SECONDS`, and
`GEMINI_MAX_ATTEMPTS` (total attempts, default 2, capped at 3). The old
`GEMINI_REQUEST_SPACING_SECONDS` setting is no longer used. Testing Deck activity
logs show Gemini attempts and retry waits. These are per-request HTTP timeouts,
not a guaranteed deadline for the entire browser session.

To avoid cloud API quotas, install [Ollama](https://ollama.com/download/windows)
on Windows, download a local model once, and run:

```powershell
ollama pull qwen3:4b
python -m Backend.explore_website --provider ollama --model qwen3:4b --max-actions 40
```

The Ollama option uses only its local endpoint at `127.0.0.1:11434` for model
decisions and review, so it requires no Gemini API key or per-request cloud
quota. It does require enough local memory and may be slower or less reliable
than a cloud model. Review actions and findings against the saved history.
To use it from Testing Deck, set `OMNI_MODEL_PROVIDER=ollama` and
`OLLAMA_MODEL=qwen3:4b` in `Backend/.env`, then restart the backend. Ollama
must be running with that model installed. Live sessions do not require a Gemini
key in this mode; screenshot reviews still use Gemini. Local requests default to
one attempt with a 120-second timeout (`OLLAMA_MAX_ATTEMPTS` and
`OLLAMA_TIMEOUT_SECONDS`), and request progress appears in the session log.
If only the final review times out, retry it without replaying the browser:

```powershell
python -m Backend.review_saved_run --provider ollama --run Backend/results/exploration_<timestamp>
```

Every run creates a separate `Backend/results/exploration_<timestamp>/` folder containing
`persona.json`, `history.json` (before/after observations, decisions, execution
errors and measured changes), and `report.json` (candidate findings with evidence
step numbers, flow assessments, coverage gaps and testing limitations).
The main feedback is in `persona_feedback`: `overall_impression`,
`what_worked_well`, `difficult_moments`, and `suggested_improvements`.
Comments use the persona's voice and cite executed steps plus an exact recorded
label or text excerpt. `findings` contains optional concrete issues, so an empty
findings list can still accompany useful experience feedback. Reactions are AI
inferences, not measured human feelings. Reference checks exclude comments with
missing steps or unmatched quotes; they cannot prove a reaction or recommendation
is correct. Exclusions are recorded under `review_validation`.
Use the saved-run reviewer to generate this format from an existing history
without repeating browser actions. A broader feedback report can take longer on
a CPU; this does not make unvisited flows tested.
The `coverage.flows` section is generated directly from browser observations,
even when the model's final issue review fails. Each flow is marked `confirmed`,
`attempted`, `blocked`, or `untested`, with step numbers to inspect in
`history.json`. The run also saves a copy of `flow_catalog.json` so the coverage
rules used for that run remain available. These rules currently describe the
OMNI TestLab site; update them if testing another website. They do not direct
the persona's actions.
Ctrl+C stops exploration and attempts a final review of the saved partial run.
An API failure preserves the recorded evidence and reports the failure.

The persona chooses its own route. The action limit bounds exploration, not
coverage: this is not a guarantee that all flows or issues were discovered.
Account submissions and checkout are blocked; account testing needs a dedicated
test setup. External navigation and new tabs are not explored. This version reads
viewport DOM text and controls only; it does not assess visual contrast/layout,
traverse iframes/shadow DOM, record video, or measure human experiences. Findings
are hypotheses for review against the saved evidence. A successful browser action
does not prove that a user flow completed. DOM observations may miss delayed or
purely visual changes. Automation failures are recorded separately from findings.

## Security

Keep API keys and other credentials in `Backend/.env`. Do not place secrets directly in source files or commit them to the repository.

## Using the D:\FYP\OMNI working folder

This folder is the active local project. Run `./start.ps1` from here and open http://127.0.0.1:8000/. The optional evaluation target is maintained outside this repository and can be started separately on port 5173.

All Python features, configuration, tests, and saved data live under `Backend/`. The API and CLI share its `personas/`, `screenshots/`, `results/`, and `agents/` folders. Persona edits preserve extra behavioral fields. API projects, review plans, and execution state are stored in `Backend/projects/`, `Backend/plans/`, and `Backend/runs/` as needed. `OMNI_DATA_DIR` can override the API data root for an isolated workspace. `Frontend/` contains only the OMNI interface and its JavaScript checks.

Reports Library includes both screenshot evaluations and Backend/results/exploration_*/report.json. Exploration reports show recorded persona feedback, candidate observations, flow coverage and sanitized before/after history. Failed or incomplete reviews are labeled accordingly. Browser cookies, browser_state.json and entered field values are not served to the frontend.

`Backend/.env` is the single local environment file and is loaded without exposing its key to the frontend. A configured key does not establish that the model is currently available or its quota is sufficient. Testing Deck defaults to **Live persona session**: enter the target URL and task, select a persona and interaction limit, review the criteria, then start. Chrome opens a fresh session, the persona chooses real actions from the live DOM, and Reports Library shows first-person experience feedback with recorded evidence. Screenshot review remains available as a separate method. Google Chrome must be installed. Sessions cannot currently be paused. Account submissions, password entry, payments and external navigation remain blocked, so a signup task can inspect and interact with safe form fields but cannot complete account creation. Feedback is a simulated persona perspective, not a human participant's testimony.

Run all Python tests from the repository root with `.venv/Scripts/python.exe -m unittest discover -s Backend/tests -t . -v`. The API uses `Backend.app.server:app`; `start.ps1` sets the correct working directory.
