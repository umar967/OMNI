import { state } from "../state.js";
import { heading, link, empty } from "../components/ui.js";
import { reportRows } from "./reports.js";

export function dashboard() {
  const reports = state.reports;
  const recent = [...reports].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0)).slice(0, 3);
  const metrics = [
    ["Saved reports", reports.length, "Your recorded evaluations", "01"],
    ["Browser explorations", reports.filter(r => r.kind === "exploration").length, "Sessions with saved reports", "02"],
    ["Projects", state.projects.length, "Organized in your workspace", "03"],
    ["Available personas", state.personas.length, "Perspectives to explore", "04"],
  ];
  return heading(`Welcome back, ${state.preferences.name}.`, "A fresh perspective on what you're building.", link("＋ New exploration", "deck", "primary")) + `
    <section class="perspective-hero">
      <div class="hero-copy"><div class="eyebrow">THE HUMAN SIDE OF YOUR WEBSITE</div>
        <h2>Good experiences start<br>with a different perspective.</h2>
        <p>Explore your website through AI personas.<br>Follow their actions. Discover what needs a closer look.</p>
        <div class="hero-actions">${link('Start an exploration <span aria-hidden="true">↗</span>', "deck", "hero-cta")}${link("Meet your personas →", "personas", "hero-secondary")}</div>
        <div class="hero-caption"><span class="pulse"></span> Your next insight starts with a question.</div>
      </div>
      <div class="perspective-art" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="orbit orbit-three"></div><div class="orbit-core">o<span>m</span>ni</div><span class="orbit-label label-one">Observe</span><span class="orbit-label label-two">Explore</span><span class="orbit-label label-three">Understand</span><span class="art-coordinate">A CHANGE IN PERSPECTIVE / OMNI</span></div>
    </section>
    <div class="grid cols4 spacer workspace-metrics">${metrics.map(([label, value, caption, number]) => `<section class="panel stat"><div class="sectionhead"><small>${label}</small><span class="metric-index">${number}</span></div><strong>${value}</strong><small>${caption}</small></section>`).join("")}</div>
    <div class="overview-bottom spacer"><section class="panel recent-panel"><div class="sectionhead"><div><div class="eyebrow">YOUR WORK, IN FOCUS</div><h2>Recent reports</h2></div>${link("View all ↗", "reports", "link")}</div>${recent.length ? reportRows(recent) : empty("Your first perspective is waiting. Run an exploration to see its report here.", link("Create an exploration →", "deck", "primary"))}</section>
    <section class="panel perspective-note"><div class="eyebrow">A THOUGHTFUL START</div><span class="note-symbol" aria-hidden="true">✳</span><h2>One task.<br>A new point of view.</h2><p>Choose a focused task and a persona. Review the recorded evidence before drawing conclusions.</p><div class="note-footer">AI perspectives are hypotheses,<br>not a substitute for real user research.</div>${link("Explore persona library ↗", "personas", "link")}</section></div>`;
}
