# Two OMNI presentation flows

Start OMNI at http://127.0.0.1:8000. Dashboard is illustrative; all other data comes from your backend. No public hosting is needed for this local presentation.

## Flow 1 — Your persona, evidence and a new evaluation

Prerequisites: Gemini key/model configured in Backend/.env, internet access and backend running. Use the existing signup screenshot to avoid depending on TestLab or capture during the presentation.

1. **Persona Library** → **Older / Low-Tech User** → **Edit persona**. Point out its real goal and five criteria. Cancel if no changes are needed.
2. **Use in test** → **Testing Deck**. Show the selected persona, `signup.png`, and task “Create an account comfortably and independently.”
3. Optional: select a real project created beforehand. Otherwise keep the report ungrouped.
4. **Prepare review plan**. Explain that the visible criteria came from the persona. Edit a criterion or deselect one, then **Save plan**.
5. **Start evaluation** → **Execution Monitor**. Explain that this is one screenshot request to Gemini; the log shows actual stages, without fake percentages or functional passes.
6. **View report**. Explain the persona impact, severity, evidence and recommendations. Open **Evidence** to show the exact submitted image.
7. **Export report JSON**. Optionally return to the project's reports to show the saved result.

Model responses vary and may take time or fail due to network/quota/model availability. Do a rehearsal with your key before presenting. This flow does not automate account creation or prove the form works.

## Flow 2 — Review your saved results without a model call

This flow works without a Gemini key, internet, TestLab or Chrome capture.

1. **Reports Library** → search **First-Time User**.
2. **View report** → show the existing task “Create an account” and the three findings from your original JSON.
3. Explain one observation, its recorded evidence and recommendation.
4. Open **Evidence**. The old report contains textual evidence but no recorded screenshot link; the UI explicitly says so.
5. **Export report JSON**, then return to Reports Library and open the older-user report to contrast how persona context changes the findings.

## Optional live screenshot capture

Start OMNI-TestLab on port 5173. In Testing Deck use `http://127.0.0.1:5173/login?mode=signup` and **Capture this TestLab page**. Installed Chrome opens separately, takes the screenshot and closes. Review the new preview before analysis. This captures the page only; it does not perform a signup or checkout journey.

For a populated checkout state, prepare that state manually in TestLab and upload its screenshot. Capture uses a fresh browser session and does not reuse the state from your existing browser.
