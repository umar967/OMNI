/** Dashboard intentionally preserves the prototype's illustrative statistics. */
import { state } from "../state.js";
import { heading, landscape, link } from "../components/ui.js";
export function dashboard() {
  return (
    heading(
      `A clearer perspective, ${state.preferences.name}.`,
      "A little clarity for everything you're building.",
      link("＋ New test", "deck", "primary"),
    ) +
    `<section class="hero">${landscape}<span class="season">A MOMENT OF CLARITY / 01</span><div class="heroText"><div class="eyebrow" style="color:#eef1e2">Thoughtful testing. Human perspective.</div><h1>Build with confidence.<br>See through their eyes.</h1><p>One space to understand how your website really feels.</p>${link("Start an exploration ↗", "deck")}</div></section><div class="grid cols4 spacer">${[
      ["Explorations", "24", "↑ 4 this week"],
      ["Average quality", "84", "out of 100"],
      ["Issues discovered", "18", "Across QA & UX"],
      ["Your personas", "3", "Different perspectives"],
    ]
      .map(
        ([t, n, s]) =>
          `<div class="panel stat"><small>${t}</small><strong>${n}</strong><small>${s}</small></div>`,
      )
      .join(
        "",
      )}</div><div class="grid cols3 spacer"><section class="panel"><div class="sectionhead"><h3>Test outcomes</h3><small>Sample · last 30 days</small></div><div class="row"><div class="donut"><strong>78<small>%</small></strong></div><div class="legend"><span class="dot"></span>Passed · 78%<br><span class="dot" style="background:#d6dfcf"></span>Review · 14%<br><span class="dot" style="background:#cda893"></span>Failed · 8%</div></div></section><section class="panel"><div class="sectionhead"><h3>Issues by severity</h3><small>18 total</small></div>${[
      ["Critical", 2, 17],
      ["High", 5, 42],
      ["Medium", 8, 67],
      ["Low", 3, 25],
    ]
      .map(
        ([t, n, w]) =>
          `<div class="row" style="justify-content:space-between;font-size:11px"><span>${t}</span><span>${n}</span></div><div class="bar"><span style="width:${w}%"></span></div>`,
      )
      .join(
        "",
      )}</section><section class="panel"><div class="sectionhead"><h3>Pick up where you left off</h3></div><div class="projecticon">↗</div><h3>Evergreen Store</h3><p class="muted spacer">Sample dashboard card. Open your real reports to continue.</p>${link("View your reports →", "reports", "ghost spacer")}</section></div><section class="panel spacer"><div class="sectionhead"><h3>Recent explorations <small>· Sample data</small></h3>${link("Your real reports ↗", "reports", "link")}</div><div class="listrow"><div class="row"><span class="avatar">↗</span><div><h3>Evergreen Store</h3><small>Combined · Oct 19, 2026 · Maya Chen</small></div></div><span class="badge">84/100 · Sample</span></div></section>`
  );
}
