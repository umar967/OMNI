import { state } from "../state.js";
import { imageUrl } from "../api.js";
import {
  esc,
  btn,
  link,
  heading,
  steps,
  empty,
  date,
} from "../components/ui.js";
export function deck() {
  let d = state.draft;
  const live = (d.method || "live") === "live";
  return (
    steps(0) +
    heading(
      "Every exploration starts here.",
      "Let your persona use a live website and share its experience.",
    ) +
    `<div class="deck"><form class="panel" data-form="deck"><h2>Set the scene</h2><label for="target">Website / page URL</label><input id="target" name="url" type="url" required value="${esc(d.url)}"><small>The persona opens this URL in Chrome and interacts with the page.</small><label for="method">Testing method</label><select id="method" name="method"><option value="live" ${live ? "selected" : ""}>Live persona session</option><option value="screenshot" ${!live ? "selected" : ""}>Screenshot review</option></select><label for="instructions">Task or instructions</label><textarea id="instructions" name="instructions" required maxlength="10000">${esc(d.instructions)}</textarea><label>Evaluation mode</label><div class="choices"><button type="button" class="choice selected">UX<small>Connected · Live browser interaction</small></button><button type="button" class="choice" disabled>QA<small>Not supported by this backend</small></button><button type="button" class="choice" disabled>Combined<small>Requires functional QA support</small></button></div><label for="persona">Choose a perspective</label><select id="persona" name="persona_id" required>${state.personas.map((p) => `<option value="${esc(p.id)}" ${p.id === d.persona_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>${live ? `<label for="max-actions">Maximum interactions</label><input id="max-actions" name="max_actions" type="number" min="1" max="60" value="${esc(d.max_actions || 20)}"><small>The persona clicks, scrolls, and fills safe fields. Account submissions and payments remain outside this session.</small>` : `<label for="screenshot">Screenshot to evaluate</label><select id="screenshot" name="screenshot_id" required><option value="">Choose a screenshot</option>${state.screenshots.map((s) => `<option value="${esc(s.id)}" ${s.id === d.screenshot_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select><div class="row spacer wrap"><label class="upload" for="upload">＋ Upload PNG / JPEG</label><input type="file" id="upload" accept="image/png,image/jpeg" hidden>${btn("Capture this TestLab page ↗", "capture", "ghost")}</div><small>Capture opens real Chrome, takes a screenshot, then closes it. It does not interact with the page.</small>`}<label for="project">Save to project · optional</label><select id="project" name="project_id"><option value="">Keep report ungrouped</option>${state.projects.map((p) => `<option value="${esc(p.id)}" ${p.id === d.project_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select><div class="foot"><small>Review cases before the model call.</small><button class="primary" ${state.personas.length ? "" : "disabled"}>Prepare review plan →</button></div></form><aside><section class="panel"><div class="eyebrow">A human point of view</div><h2>Your people.<br>Your evidence.</h2><p class="muted spacer">The plan is built from your persona’s actual evaluation criteria, then reviewed by you. The persona uses the live page when you start the session. Feedback is based on its recorded actions.</p><div class="hint spacer ${state.health.gemini_configured ? "" : "warning"}">${live && state.health.provider === "ollama" ? `Local Ollama model: ${esc(state.health.model)}. Live sessions run on this computer.` : state.health.gemini_configured ? "Gemini key configured. Live evaluation is available." : "Gemini key is not configured. Add it to Backend/.env and restart. Your existing reports work without a key."}</div></section>${!live && d.screenshot_id ? `<section class="panel spacer"><h3>Selected screenshot</h3><img class="screen-preview spacer" src="${imageUrl(d.screenshot_id)}" alt="Selected evidence screenshot"><small>${esc(d.screenshot_id)}</small></section>` : ""}</aside></div>`
  );
}
export function plan() {
  let p = state.plan;
  if (!p)
    return empty("No review plan loaded.", link("Open Testing Deck", "deck"));
  return (
    steps(1) +
    heading(
      "Make the plan your own.",
      "Review the persona criteria and task before starting the session.",
      `<span class="badge" id="selected-count">${p.cases.filter((c) => c.selected).length} selected</span>`,
    ) +
    `<div class="deck"><section class="panel"><div class="sectionhead"><h2>Review cases</h2>${btn("＋ Add case", "add-case", "ghost")}</div><form id="planform" data-form="plan">${p.cases.map((c) => `<div class="testcase" data-case="${esc(c.id)}"><input type="checkbox" name="selected" aria-label="Select ${esc(c.title)}" ${c.selected ? "checked" : ""}><div class="casebody"><input name="title" aria-label="Case title" value="${esc(c.title)}" required maxlength="500"><label for="expected-${esc(c.id)}">Expected visible behavior</label><textarea id="expected-${esc(c.id)}" name="expected" required maxlength="2000">${esc(c.expected)}</textarea><small>UX · Persona criterion · Human-reviewed</small></div>${btn("×", "remove-case", "icon", c.id)}</div>`).join("")}<div class="foot">${link("← Testing Deck", "deck")}<div class="row">${btn("Save plan", "save-plan", "ghost")}<button class="primary">Start evaluation →</button></div></div></form></section><aside class="panel" style="align-self:start"><div class="eyebrow">Exploration brief</div><h3>${esc(p.persona.name)}</h3><p class="muted spacer">${esc(p.instructions)}</p><div class="tags"><span class="tag">UX</span><span class="tag">${esc(p.url)}</span></div>${p.method === "live" ? "" : `<img class="screen-preview" src="${imageUrl(p.screenshot_id)}" alt="Screenshot to be analyzed">`}<div class="hint spacer">${p.method === "live" ? "The persona chooses actions on the live website, then shares first-person feedback tied to recorded steps. This is a simulated persona experience." : "Selected cases guide the screenshot review."}</div></aside></div>`
  );
}
export function execution() {
  let r = state.run;
  if (!r) return empty("No evaluation selected.", link("Start one", "deck"));
  let p = r.plan,
    done = r.status === "completed",
    failed = r.status === "failed";
  return (
    steps(2) +
    heading(
      done
        ? "Your evaluation is complete."
        : failed
          ? "The evaluation needs attention."
          : "Seeing through their eyes.",
      "Live status from your backend. No simulated timers or logs.",
      `<span class="badge ${failed ? "fail" : ""}">${esc(r.status)}</span>`,
    ) +
    `<div class="deck"><section class="panel"><div class="sectionhead"><h2>${done ? "Report ready" : failed ? "Evaluation needs attention" : p.method === "live" ? "Live persona session" : "Screenshot analysis"}</h2><span class="badge">${esc(r.stage)}</span></div>${p.method === "live" ? `<div class="hint spacer">${failed ? "The session stopped. Inspect the activity log and saved report below." : done ? "The persona session has finished. Open the report for its feedback." : "Follow the persona session in Chrome and the activity log below."}</div>` : `<img class="screen-preview evidence-full" src="${imageUrl(p.screenshot_id)}" alt="Actual screenshot submitted for evaluation">`}<p class="muted spacer">${esc(p.url)}</p><div class="stage-list spacer">${(p.method === "live" ? ["queued", "preparing", "exploring", "reviewing", "completed"] : ["queued", "preparing", "analyzing", "completed"]).map((s) => `<span class="badge ${r.stage === s ? "warn" : ""}">${s === r.stage ? "● " : ""}${s}</span>`).join("")}</div>${r.error ? `<div class="hint warning spacer" role="alert">${esc(r.error)}</div>` : ""}<div class="foot"><small>${esc(p.persona.name)} · UX</small>${r.report_id ? link("View report →", `report/${r.report_id}`, "primary") : failed ? link("Review plan", `plan/${p.id}`, "primary") : "<small>Waiting for the evaluator…</small>"}</div><section class="spacer"><h3>Activity log</h3><div class="log spacer">${r.logs.map((l) => `<div>${esc(date(l.at))} · ${esc(l.message)}</div>`).join("")}</div></section></section><aside class="panel" style="align-self:start"><h3>Selected review criteria</h3>${p.cases
      .filter((c) => c.selected)
      .map(
        (c) =>
          `<div class="listrow"><small>${esc(c.title)}</small><span class="badge">${done ? "Reviewed" : "Included"}</span></div>`,
      )
      .join(
        "",
      )}<div class="hint spacer">Sessions run up to the configured interaction limit and cannot currently be paused. You may navigate away and return using the latest evaluation link in Settings.</div></aside></div>`
  );
}
