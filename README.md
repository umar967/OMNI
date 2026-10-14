# OMNI

OMNI is an AI-powered UX testing prototype that evaluates interface screenshots from the perspective of predefined user personas. It uses Google's Gemini API to identify visible usability issues and return structured recommendations.

## Features

- Persona-based UX evaluation
- Screenshot analysis with Gemini
- Evidence-based findings with severity levels
- Structured JSON reports

## Project structure

```text
OMNI/
├── agents/          # Persona evaluation agent
├── personas/        # User persona definitions
├── results/         # Generated evaluation reports
├── screenshots/     # Interface screenshots to evaluate
├── main.py          # Main evaluation script
└── test_api.py      # Gemini API connectivity test
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
   pip install google-genai python-dotenv
   ```

4. Create a `.env` file in the project root and add your Gemini API key:

   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

   The `.env` file is ignored by Git and should never be committed.

## Usage

To verify the Gemini API connection:

```bash
python test_api.py
```

To run a persona-based UX evaluation:

```bash
python main.py
```

By default, `main.py` evaluates `screenshots/signup.png` using the older-user persona and writes the result to `results/older_user_report.json`. Update the paths in `main.py` to evaluate another persona or screenshot.

## Report format

Each finding includes:

- The UX issue and category
- A severity level (`Low`, `Medium`, or `High`)
- An explanation of its impact on the persona
- Visible evidence from the screenshot
- A practical recommendation

## Security

Keep API keys and other credentials in `.env`. Do not place secrets directly in source files or commit them to the repository.
