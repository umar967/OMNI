import { state } from "../state.js";
import { imageUrl } from "../api.js";
import { esc, btn, link, heading, empty, date, steps } from "../components/ui.js";

const exploration = (r) => r.kind === "exploration";
const feedbackCount = (r) => {
  const f = r.persona_feedback || {};
  return (f.overall_impression ? 1 : 0) + ["what_worked_well", "difficult_moments", "suggested_improvements"].reduce((n, key) => n + (f[key]?.length || 0), 0);
};
const reviewLabel = (value) => value === "completed" ? "Reviewed" : ["partial", "not_completed"].includes(value) ? "Review incomplete" : value === "unavailable" ? "Review unavailable" : value || "Not recorded";
const title = (r) => exploration(r) ? `Browser exploration · ${r.actions_recorded || 0} recorded actions` : r.task || r.id;

export function reportRows(records) {
  return records.length ? records.map((r) => `
    <div class="listrow"><div class="row"><span class="avatar">↗</span><div>
      <h3>${esc(title(r))}</h3><small>${esc(r.persona)} · ${exploration(r) ? feedbackCount(r) : r.findings.length} ${exploration(r) ? "persona comments" : "findings"}
      · ${exploration(r) ? esc(reviewLabel(r.review_status)) : r.imported ? "Existing report" : esc(date(r.created_at))}</small>
    ${exploration(r) && r.evidence_incomplete ? '<span class="badge warn">Incomplete evidence</span>' : ""}</div></div><div class="row"><span class="badge">${exploration(r) ? "Exploration" : "Screenshot UX"}</span>${link("View report ↗", `report/${r.id}`)}</div></div>
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

    ${btn("Inspect evidence →", "report-tab", "link spacer", "Evidence")}</article>`).join("");
}

function recommendations(r) {
  const items = r.findings.map((f, i) => ({ ...f, number: i + 1 })).filter(f => f.recommendation);
  return items.length ? `<section class="spacer"><h2>Recommendations</h2>${items.map(f => `<div class="hint spacer"><strong>OM-${f.number} · ${esc(f.issue)}</strong><p>${esc(f.recommendation)}</p></div>`).join("")}</section>` : "";
}

function feedback(r) {
  const data = r.persona_feedback;
  if (!data) return exploration(r) ? `<div class="hint warning spacer"><strong>Persona feedback is unavailable</strong><p>${esc(r.review_error || r.stop_reason || "The model review did not finish.")}</p><p>${r.actions_recorded || 0} actions were recorded. Open Evidence to inspect them. No usability verdict was produced.</p></div>` : "";
  return `<section class="spacer"><h2>Persona reflections</h2><p class="muted spacer">${esc(r.feedback_note || "AI-inferred reactions from recorded interactions, not measured human feelings.")}</p>
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

const elapsed = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0
  ? `${Math.floor(value / 60).toString().padStart(2, "0")}:${Math.floor(value % 60).toString().padStart(2, "0")}` : "Time not recorded";

function experienceSummary(r) {
  if (!exploration(r)) return "";
  const summary = r.experience_summary;
  const trace = r.journey_summary;
  return `<section class="experience-summary"><div class="sectionhead"><h2>Persona experience</h2><span class="badge">${summary ? "AI interpretation" : "Recorded journey"}</span></div>
    <p>${esc(summary?.comment || trace?.text || "No execution summary is available for this report.")}</p>
    ${summary ? `<small>Based on steps ${esc(summary.steps.join(", "))}. References are checked; the interpretation still needs human review.</small>` : ""}
    ${r.evidence_incomplete ? '<p class="hint warning">Incomplete evidence: inspect the action journal and missing captures in Journey evidence.</p>' : ""}
    <div class="journey-outcome"><div><small>Task outcome</small><h3>${esc(trace?.outcome || "Completion not verified")}</h3></div><div><small>Session ending</small><p>${esc(trace?.stop_reason || r.stop_reason || "Not recorded")}</p></div></div>
    ${r.outcome_verification ? `<details class="hint spacer"><summary>Independent endpoint verification</summary><p>${esc(r.outcome_verification.reason)}</p><p>Execution: ${esc(r.execution_status || "Not recorded")}</p>${(r.outcome_verification.evidence || []).map(e => `<div id="verification-${esc(e.id)}"><small>Evidence ${esc(e.id)} · ${esc(e.at)} · ${e.step ? `step ${esc(e.step)}` : "endpoint inspection"}</small><pre>${esc(JSON.stringify({conditions: e.conditions, observed: e.observed}, null, 2))}</pre></div>`).join("")}${(r.outcome_verification.limitations || []).map(x => `<p>${esc(x)}</p>`).join("")}</details>` : ""}</section>`;
}

function evidence(r) {
  if (!exploration(r)) return `<h2>Evaluation screenshot</h2>${r.screenshot_id ? `<a href="${imageUrl(r.screenshot_id)}" target="_blank" rel="noopener"><img class="screen-preview evidence-full spacer" src="${imageUrl(r.screenshot_id)}" alt="Original evaluation screenshot"></a>` : empty("No screenshot was associated with this report.")}`;
  const seen = new Map();
  return `<h2>Persona journey evidence</h2><p class="muted spacer">Recorded screens in execution order. Timestamps are elapsed session time, not human task time. Identical captures reference the earlier image; missing evidence stays visible.</p>
    <div class="journey-timeline">${!state.evidence.length ? empty("No interaction trace is available for this run.") : state.evidence.map(row => {
      const issues = (r.findings || []).map((f, i) => ({...f, number: i + 1})).filter(f => f.steps?.includes(row.step));
      const captures = ["before", "after"].map(phase => {
        const src = row.screenshots?.[phase];
        const meta = row.capture_metadata?.[phase] || {};
        const title = meta.title || row[phase]?.title || row[phase]?.url || "Page title not recorded";
        if (!src) return `<div class="hint spacer">${phase === "before" ? "Before" : "After"} capture unavailable. This state cannot be reconstructed.</div>`;
        const existing = meta.sha256 && seen.get(meta.sha256);
        const id = `capture-${row.step}-${phase}`;
        if (meta.sha256 && !existing) seen.set(meta.sha256, {id, step: row.step, phase});
        const figure = `<figure class="journey-capture" id="${id}"><figcaption><strong>${esc(title)}</strong><small>${phase === "before" ? "Before action" : "After action"} · ${elapsed(meta.elapsed_seconds)} · ${esc(row[phase]?.url || meta.url || "URL not recorded")}</small></figcaption>
          ${existing ? `<p class="hint">Identical to step ${esc(existing.step)} (${existing.phase}). <a href="#${existing.id}" data-capture-ref="${existing.id}">View earlier capture ↑</a></p>` : `<a href="${esc(src)}" target="_blank" rel="noopener"><img class="screen-preview evidence-full" src="${esc(src)}" alt="Step ${esc(row.step)}, ${phase} ${esc(row.action)}: ${esc(title)}" loading="lazy"></a>`}
          ${meta.ready === false ? `<div class="hint warning spacer">Capture readiness was incomplete: ${esc(meta.pending_images ?? "unknown")} visible images unresolved${meta.busy ? "; loading indicators remained" : ""}${meta.fonts_ready === false ? "; fonts were still loading" : ""}. This is an evidence limitation, not a confirmed website issue.</div>` : !Object.hasOwn(meta, "ready") ? `<small>Loading readiness was not recorded for this capture.</small>` : ""}</figure>`;
              return phase === "before" && row !== state.evidence[0] ? `<details class="spacer"><summary>Inspect state before this action</summary>${figure}</details>` : figure;
      }).join("");
      return `<article class="journey-step"><div class="journey-step-heading"><span class="journey-number">${esc(row.step)}</span><div><h3>${esc(row.action || "Recorded interaction")}${row.target_label ? ` · ${esc(row.target_label)}` : ""}</h3><small>${elapsed(row.elapsed_seconds)} · ${esc(row.result || "Result not recorded")}</small></div></div>
        <small>Action status: ${esc(row.action_status || "Legacy — dispatch not recorded")} · Dispatch: ${esc(row.dispatch_state || "Not recorded")}</small>
        ${row.evidence_gaps?.length ? `<div class="hint warning spacer"><strong>Incomplete evidence</strong>${row.evidence_gaps.map(g => `<p>${esc(g)}</p>`).join("")}</div>` : ""}
        ${row.reason ? `<p class="muted spacer"><strong>Agent's stated intention:</strong> ${esc(row.reason)}</p>` : ""}
        ${issues.length ? `<div class="hint spacer"><strong>Associated candidate issues</strong>${issues.map(f => `<p>OM-${f.number} · ${esc(f.issue)} <span class="badge">${esc(f.severity)}</span></p>`).join("")}</div>` : ""}
        ${captures}</article>`;
    }).join("")}</div>`;
}

export function report() {
  const r = state.report;
  if (!r) return empty("Report not found.", link("Reports Library", "reports"));
  const severity = { High: 0, Medium: 0, Low: 0 };
  r.findings.forEach((f) => severity[f.severity] = (severity[f.severity] || 0) + 1);
  const metrics = exploration(r)
    ? [["Interactions performed", r.actions_executed ?? r.actions_recorded ?? 0],
       ["Persona comments", feedbackCount(r)],
       ["What worked well", r.persona_feedback?.what_worked_well?.length || 0],
       ["Suggested improvements", r.persona_feedback?.suggested_improvements?.length || 0]]
    : [["Recorded findings", r.findings.length], ["High", severity.High], ["Medium", severity.Medium], ["Low", severity.Low]];
  const project = state.projects.find((p) => p.id === r.project_id);
  const intro = exploration(r)
    ? "Saved browser exploration. Persona feedback and candidate observations are AI inferences, not measured human experiences or proof of whole-site coverage."
    : r.imported ? "Existing screenshot report. Missing URL, model, screenshot association and run timestamp remain unassigned."
    : "Saved screenshot evaluation. Findings are model observations, not confirmed functional test results.";
  return steps(3) + heading(exploration(r) ? "Exploration report" : r.task || "Evaluation report", `${r.persona} · ${r.method || "Screenshot UX evaluation"}`, btn("↓ Export report JSON", "export-report", "ghost")) + `
    <div class="hint">${intro}</div><div class="grid cols4 spacer">${metrics.map(([label, count]) => `<div class="panel stat"><small>${label}</small><strong>${esc(count)}</strong></div>`).join("")}</div>
    <div class="tabs spacer">${(exploration(r) ? [["Experience & findings", "Overview"], ["Journey evidence", "Evidence"]] : [["Overview", "Overview"], ["Review cases", "Review cases"], ["Evidence", "Evidence"]]).map(([label, key]) => btn(label, "report-tab", key === state.reportTab ? "primary" : "ghost", key)).join("")}</div>
    <div class="deck"><section class="panel">${state.reportTab === "Overview" ? `${experienceSummary(r)}${feedback(r)}<h2 class="spacer">Problems encountered</h2>${findings(r)}${recommendations(r)}` : state.reportTab === "Review cases" ? scope(r) : evidence(r)}
    ${r.limitations?.length ? `<details class="hint spacer"><summary>Recorded limitations</summary>${r.limitations.map((v) => `<p>${esc(v)}</p>`).join("")}</details>` : ""}</section>
    <aside class="panel" style="align-self:start"><div class="eyebrow">Persona overview</div><h3>${esc(r.persona)}</h3>
      ${[["Goal", r.task || "Not recorded"], ["Technical familiarity", r.persona_snapshot?.technical_skill || r.persona_snapshot?.technical_level || "Not recorded"], ["URL", r.url || "Not recorded"], ["Mode", exploration(r) ? "Browser exploration" : "Screenshot UX"], ["Review", exploration(r) ? reviewLabel(r.review_status) : "Screenshot analysis"], ["Project", project?.name || "Ungrouped"], ["Model", r.model || "Not recorded"], ["Run date", r.imported ? "Not recorded" : date(r.created_at)]].map(([label, value]) => `<div class="listrow"><small>${label}</small><span class="context-value">${esc(value)}</span></div>`).join("")}
      ${link("← Reports Library", "reports", "ghost spacer")}${project ? link("Open project ↗", `project/${project.id}`, "ghost spacer") : ""}
    </aside></div>`;
}
