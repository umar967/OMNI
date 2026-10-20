import { state } from "../state.js";
import { imageUrl } from "../api.js";
import {
  esc,
  btn,
  link,
  heading,
  empty,
  date,
  steps,
} from "../components/ui.js";
export function reportRows(reports) {
  return reports.length
    ? reports
        .map(
          (r) =>
            `<div class="listrow"><div class="row"><span class="avatar">↗</span><div><h3>${esc(r.task || r.id)}</h3><small>${esc(r.persona)} · ${r.findings.length} findings · ${r.imported ? "Existing report" : esc(date(r.created_at))}</small></div></div><div class="row"><span class="badge">UX</span>${link("View report ↗", `report/${r.id}`)}</div></div>`,
        )
        .join("")
    : empty(
        "No reports in this view. Start an evaluation or choose another filter.",
      );
}
export function reports() {
  return (
    heading(
      "The bigger picture.",
      "Your saved evaluation results, loaded from Backend/results.",
      link("＋ New exploration", "deck", "primary"),
    ) +
    `<section class="panel"><div class="row wrap" style="margin-bottom:20px"><input id="reportsearch" aria-label="Search reports" placeholder="Search tasks, personas or findings…" value="${esc(state.search)}"><select id="reportfilter" aria-label="Filter by project" style="max-width:240px"><option value="">All reports</option><option value="ungrouped" ${state.projectFilter === "ungrouped" ? "selected" : ""}>Ungrouped reports</option>${state.projects.map((p) => `<option value="${esc(p.id)}" ${state.projectFilter === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div><div id="reportrows">${filteredRows()}</div></section>`
  );
}
export function filteredRows() {
  let q = state.search.toLowerCase();
  return reportRows(
    state.reports.filter(
      (r) =>
        JSON.stringify([r.task, r.persona, r.findings])
          .toLowerCase()
          .includes(q) &&
        (!state.projectFilter ||
          (state.projectFilter === "ungrouped"
            ? !r.project_id
            : r.project_id === state.projectFilter)),
    ),
  );
}
export function report() {
  let r = state.report;
  if (!r) return empty("Report not found.", link("Reports Library", "reports"));
  let severity = { High: 0, Medium: 0, Low: 0 };
  r.findings.forEach(
    (f) => (severity[f.severity] = (severity[f.severity] || 0) + 1),
  );
  let project = state.projects.find((p) => p.id === r.project_id);
  let tab = state.reportTab;
  return (
    steps(3) +
    heading(
      r.task || "Evaluation report",
      `${r.persona} · ${r.method || "Existing screenshot UX evaluation"}`,
      btn("↓ Export report JSON", "export-report", "ghost"),
    ) +
    `<div class="hint">${r.imported ? "Imported from your existing result file. The original report did not record a URL, model, screenshot association or run timestamp. Those details are left unassigned." : "Saved evaluation snapshot. Findings are Gemini’s analysis of the recorded screenshot; they are not confirmed functional test results."}</div><div class="grid cols4 spacer">${[
      ["Findings", r.findings.length],
      ["High", severity.High],
      ["Medium", severity.Medium],
      ["Low", severity.Low],
    ]
      .map(
        ([t, n]) =>
          `<div class="panel stat"><small>${t}</small><strong>${n}</strong></div>`,
      )
      .join(
        "",
      )}</div><div class="tabs spacer">${["Overview", "Review cases", "Evidence"].map((t) => btn(t, "report-tab", t === tab ? "primary" : "ghost", t)).join("")}</div><div class="deck"><section class="panel">${tab === "Overview" ? `<h2>Where the experience can improve</h2>${r.findings.length ? r.findings.map((f, i) => `<article class="finding"><span class="badge ${f.severity === "High" ? "fail" : f.severity === "Medium" ? "warn" : ""}">${esc(f.severity)}</span> <small>${esc(f.category)} · OM-${i + 1}</small><h3>${esc(f.issue)}</h3><p class="muted">${esc(f.explanation)}</p><p class="spacer"><strong>Visible evidence</strong><br>${esc(f.evidence)}</p><div class="hint spacer"><strong>Recommendation</strong><br>${esc(f.recommendation)}</div>${btn("Inspect evidence →", "report-tab", "link spacer", "Evidence")}</article>`).join("") : empty("No visible issues were identified in this evaluation.")}` : tab === "Review cases" ? `<h2>Evaluation scope</h2>${r.cases?.length ? r.cases.map((c) => `<div class="listrow"><div><h3>${esc(c.title)}</h3><p class="muted">${esc(c.expected)}</p></div><span class="badge">Reviewed</span></div>`).join("") : empty("The original report did not record individual review cases.")}<p class="muted spacer">Screenshot review does not produce a functional pass/fail verdict for each case.</p>` : `<h2>Evidence journal</h2>${r.screenshot_id ? `<a href="${imageUrl(r.screenshot_id)}" target="_blank" rel="noopener"><img class="screen-preview evidence-full spacer" src="${imageUrl(r.screenshot_id)}" alt="Original screenshot submitted for this report"></a><small>Click to open the original screenshot.</small>` : '<div class="hint spacer">No screenshot association was recorded in this report. The textual observations below are preserved exactly from your result file.</div>'}${r.findings.map((f, i) => `<article class="finding"><span class="badge">OM-${i + 1} · Recorded evidence</span><h3>${esc(f.issue)}</h3><p class="muted">${esc(f.evidence)}</p></article>`).join("")}`}</section><aside class="panel" style="align-self:start"><div class="eyebrow">Report context</div><h3>${esc(r.persona)}</h3>${[
      ["URL", r.url || "Not recorded"],
      ["Mode", "Screenshot UX"],
      ["Project", project?.name || "Ungrouped"],
      ["Model", r.model || "Not recorded"],
      ["Run date", r.imported ? "Not recorded" : date(r.created_at)],
    ]
      .map(
        ([t, v]) =>
          `<div class="listrow"><small>${t}</small><span class="context-value">${esc(v)}</span></div>`,
      )
      .join(
        "",
      )}${link("← Reports Library", "reports", "ghost spacer")}${project ? link("Open project ↗", `project/${project.id}`, "ghost spacer") : ""}</aside></div>`
  );
}
