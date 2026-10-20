import { state } from "../state.js";
import { esc, link, heading, empty } from "../components/ui.js";
import { reportRows } from "./reports.js";
export function projects() {
  return (
    heading(
      "A home for your work.",
      "Save explorations by website, or keep reports ungrouped.",
      link("＋ New project", "project-new", "primary"),
    ) +
    `<div class="grid cols3">${state.projects.map((p) => `<section class="panel projectcard"><span class="projecticon">❋</span><h2>${esc(p.name)}</h2><p>${esc(p.description)}<br>${esc(p.url)}</p><div class="row"><small>${state.reports.filter((r) => r.project_id === p.id).length} reports</small>${link("Open project ↗", `project/${p.id}`)}</div></section>`).join("") || empty("No saved projects yet. Your existing reports are available in Reports Library.", link("Open reports", "reports"))}</div>`
  );
}
export function project(id) {
  const p = state.projects.find((p) => p.id === id);
  if (!p) return empty("Project not found.", link("All projects", "projects"));
  return (
    heading(
      p.name,
      p.url,
      link("＋ Test this website", `deck/${p.id}`, "primary"),
    ) +
    `<section class="panel"><div class="sectionhead"><h2>Project reports</h2>${link("← All projects", "projects", "link")}</div><p class="muted">${esc(p.description)}</p>${reportRows(state.reports.filter((r) => r.project_id === p.id))}</section>`
  );
}
export function projectNew() {
  return (
    heading(
      "A new home for your work.",
      "Project saving is optional for every exploration.",
    ) +
    `<form class="panel" style="max-width:700px" data-form="project"><label for="projname">Project name</label><input name="name" id="projname" required maxlength="100"><label for="projurl">Website URL</label><input type="url" name="url" id="projurl" value="http://127.0.0.1:5173/" required><label for="projdesc">Description</label><textarea name="description" id="projdesc"></textarea><div class="foot">${link("Cancel", "projects")}<button class="primary">Create project →</button></div></form>`
  );
}
