import { state } from "../state.js";
import { imageUrl } from "../api.js";
import { esc, btn, link, heading, empty, date, steps } from "../components/ui.js";

const exploration = (r) => r.kind === "exploration";
const reviewLabel = (value) => value === "completed" ? "Reviewed" : value === "not_completed" ? "Review incomplete" : value || "Not recorded";
const title = (r) => exploration(r) ? `Browser exploration · ${r.actions_recorded || 0} recorded actions` : r.task || r.id;

export function reportRows(records) {
  return records.length ? records.map((r) => `
    <div class="listrow"><div class="row"><span class="avatar">↗</span><div>
      <h3>${esc(title(r))}</h3><small>${esc(r.persona)} · ${r.findings.length} ${exploration(r) ? "candidate observations" : "findings"}
      · ${exploration(r) ? esc(reviewLabel(r.review_status)) : r.imported ? "Existing report" : esc(date(r.created_at))}</small>
    </div></div><div class="row"><span class="badge">${exploration(r) ? "Exploration" : "Screenshot UX"}</span>${link("View report ↗", `report/${r.id}`)}</div></div>
  `).join("") : empty("No reports in this view. Start an evaluation or choose another filter.");
}

export function reports() {
  return heading("The bigger picture.", "Your saved screenshot evaluations and browser explorations.", link("＋ New exploration", "deck", "primary")) + `
    <section class="panel"><div class="row wrap" style="margin-bottom:20px">
      <input id="reportsearch" aria-label="Search reports" placeholder="Search tasks, personas or findings…" value="${esc(state.search)}">
      <select id="reportfilter" aria-label="Filter by project" style="max-width:240px"><option value="">All reports</option>
        <option value="ungrouped" ${state.projectFilter === "ungrouped" ? "selected" : ""}>Ungrouped reports</option>
        ${state.projects.map((p) => `<option value="${esc(p.id)}" ${state.projectFilter === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
      </select></div><div id="reportrows">${filteredRows()}</div></section>`;
}

export function filteredRows() {
  const query = state.search.toLowerCase();
  return reportRows(state.reports.filter((r) =>
    JSON.stringify([r.task, r.persona, r.findings, r.id, r.kind]).toLowerCase().includes(query) &&
    (!state.projectFilter || (state.projectFilter === "ungrouped" ? !r.project_id : r.project_id === state.projectFilter))));
}

function findings(r) {
  if (!r.findings.length) return empty(exploration(r) && r.review_status !== "completed"
    ? "The review did not complete. An empty findings list is not evidence that the website has no issues."
    : "No issues were identified within the recorded evaluation scope.");
  return r.findings.map((f, i) => `<article class="finding">
    <span class="badge ${f.severity === "High" ? "fail" : f.severity === "Medium" ? "warn" : ""}">${esc(f.severity)}</span>
    <small>${esc(f.category || "Candidate observation")} · OM-${i + 1}${f.steps?.length ? ` · Steps ${esc(f.steps.join(", "))}` : ""}</small>
    <h3>${esc(f.issue)}</h3><p class="muted">${esc(f.explanation || f.potential_persona_impact || "")}</p>
    <p class="spacer"><strong>Recorded evidence</strong><br>${esc(f.evidence)}</p>
    <div class="hint spacer"><strong>Recommendation</strong><br>${esc(f.recommendation)}</div>
    ${btn("Inspect evidence →", "report-tab", "link spacer", "Evidence")}</article>`).join("");
}

function feedback(r) {
  const data = r.persona_feedback;
  if (!data) return "";
  return `<section class="spacer"><h2>Persona experience</h2><p class="muted spacer">${esc(r.feedback_note || "AI-inferred reactions from recorded interactions, not measured human feelings.")}</p>
    ${[["Overall impression", data.overall_impression ? [data.overall_impression] : []], ["What worked well", data.what_worked_well], ["Difficult moments", data.difficult_moments], ["Suggested improvements", data.suggested_improvements]].map(([label, items]) =>
      items?.length ? `<div class="finding"><h3>${label}</h3>${items.map((item) => `<p class="spacer">${esc(item.comment)}</p><small>Steps ${esc((item.steps || []).join(", "))} · ${esc(item.evidence)}</small>`).join("")}</div>` : "").join("")}</section>`;
}

function scope(r) {
  if (!exploration(r)) return `<h2>Evaluation scope</h2>${r.cases?.length ? r.cases.map((c) => `<div class="listrow"><div><h3>${esc(c.title)}</h3><p class="muted">${esc(c.expected)}</p></div><span class="badge">Reviewed</span></div>`).join("") : empty("The original report did not record individual review cases.")}<p class="muted spacer">Screenshot review does not produce a functional pass/fail verdict for each case.</p>`;
  const flows = r.flow_assessments || [];
  return `<h2>Recorded exploration scope</h2><p class="muted spacer">${r.actions_recorded || 0} actions · ${esc(r.stop_reason || "Stop reason not recorded")}</p>
    ${flows.map((f) => `<div class="finding"><span class="badge">${esc(f.status)}</span><h3>${esc(f.flow || f.name)}</h3><p class="muted">${esc(f.explanation)}</p><small>Steps ${esc((f.steps || []).join(", "))}</small></div>`).join("")}
    ${r.coverage?.flows?.length ? `<h3 class="spacer">Configured flow checks</h3>${r.coverage.flows.map((f) => `<div class="listrow"><span>${esc(f.name)}</span><span class="badge">${esc(f.status)}</span></div>`).join("")}` : ""}
    ${r.coverage_gaps?.length ? `<div class="hint spacer"><strong>Coverage gaps</strong>${r.coverage_gaps.map((g) => `<p>${esc(g)}</p>`).join("")}</div>` : ""}`;
}

function evidence(r) {
  const screenshot = r.screenshot_id ? `<a href="${imageUrl(r.screenshot_id)}" target="_blank" rel="noopener"><img class="screen-preview evidence-full spacer" src="${imageUrl(r.screenshot_id)}" alt="Original evaluation screenshot"></a>` : "";
  return `<h2>Evidence journal</h2>${screenshot}
    ${!screenshot && !state.evidence.length ? '<div class="hint spacer">No screenshot association or interaction history was recorded for this report. Original textual evidence is preserved below.</div>' : ""}
    ${r.findings.map((f, i) => `<article class="finding"><span class="badge">OM-${i + 1} · Recorded evidence</span><h3>${esc(f.issue)}</h3><p class="muted">${esc(f.evidence)}</p></article>`).join("")}
    ${state.evidence.length ? `<h3 class="spacer">Recorded interactions</h3><p class="muted spacer">DOM observations from the saved visit. Browser session storage and entered field values are not exposed.</p>${state.evidence.map((row) => `<details class="finding"><summary>Step ${esc(row.step)} · ${esc(row.action)} · ${esc(row.result)}</summary><p class="spacer">${esc(row.reason)}</p>${["before", "after"].map((key) => `<h3 class="spacer">${key === "before" ? "Before" : "After"}</h3><small>${esc(row[key].url)}</small><p class="muted" style="white-space:pre-wrap;max-height:260px;overflow:auto">${esc(row[key].visible_text)}</p>`).join("")}</details>`).join("")}` : ""}`;
}

export function report() {
  const r = state.report;
  if (!r) return empty("Report not found.", link("Reports Library", "reports"));
  const severity = { High: 0, Medium: 0, Low: 0 };
  r.findings.forEach((f) => severity[f.severity] = (severity[f.severity] || 0) + 1);
  const project = state.projects.find((p) => p.id === r.project_id);
  const intro = exploration(r)
    ? "Saved browser exploration. Persona feedback and candidate observations are AI inferences, not measured human experiences or proof of whole-site coverage."
    : r.imported ? "Existing screenshot report. Missing URL, model, screenshot association and run timestamp remain unassigned."
    : "Saved screenshot evaluation. Findings are model observations, not confirmed functional test results.";
  return steps(3) + heading(exploration(r) ? "Exploration report" : r.task || "Evaluation report", `${r.persona} · ${r.method || "Screenshot UX evaluation"}`, btn("↓ Export report JSON", "export-report", "ghost")) + `
    <div class="hint">${intro}</div><div class="grid cols4 spacer">${[["Recorded findings", r.findings.length], ["High", severity.High], ["Medium", severity.Medium], ["Low", severity.Low]].map(([label, count]) => `<div class="panel stat"><small>${label}</small><strong>${count}</strong></div>`).join("")}</div>
    <div class="tabs spacer">${[["Overview", "Overview"], [exploration(r) ? "Flow coverage" : "Review cases", "Review cases"], ["Evidence", "Evidence"]].map(([label, key]) => btn(label, "report-tab", key === state.reportTab ? "primary" : "ghost", key)).join("")}</div>
    <div class="deck"><section class="panel">${state.reportTab === "Overview" ? `<h2>Recorded observations</h2>${findings(r)}${feedback(r)}` : state.reportTab === "Review cases" ? scope(r) : evidence(r)}
    ${r.limitations?.length ? `<details class="hint spacer"><summary>Recorded limitations</summary>${r.limitations.map((v) => `<p>${esc(v)}</p>`).join("")}</details>` : ""}</section>
    <aside class="panel" style="align-self:start"><div class="eyebrow">Report context</div><h3>${esc(r.persona)}</h3>
      ${[["URL", r.url || "Not recorded"], ["Mode", exploration(r) ? "Browser exploration" : "Screenshot UX"], ["Review", exploration(r) ? reviewLabel(r.review_status) : "Screenshot analysis"], ["Project", project?.name || "Ungrouped"], ["Model", r.model || "Not recorded"], ["Run date", r.imported ? "Not recorded" : date(r.created_at)]].map(([label, value]) => `<div class="listrow"><small>${label}</small><span class="context-value">${esc(value)}</span></div>`).join("")}
      ${link("← Reports Library", "reports", "ghost spacer")}${project ? link("Open project ↗", `project/${project.id}`, "ghost spacer") : ""}
    </aside></div>`;
}
