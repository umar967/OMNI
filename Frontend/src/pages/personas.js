import { state } from "../state.js";
import { esc, btn, link, heading, empty } from "../components/ui.js";
export function personas() {
  return (
    heading(
      "A different pair of eyes.",
      "Your persona definitions, loaded from the local project persona files.",
      link("＋ Create persona", "builder/new", "primary"),
    ) +
    `<div class="grid cols3">${state.personas.map((p) => `<section class="panel personaCard"><div class="persona"><div class="portrait">◈</div><div><h2>${esc(p.name)}</h2><small>${esc(p.technical_skill)} technical confidence</small></div></div><p class="muted spacer">${esc(p.goal)}</p><div class="tags">${p.criteria.map((c) => `<span class="tag">${esc(c)}</span>`).join("")}</div><div class="foot">${link("Edit persona", `builder/${p.id}`)}${btn("Use in test ↗", "use-persona", "link", p.id)}</div></section>`).join("") || empty("No personas yet. Create your first perspective.")}</div>`
  );
}
export function builder(id) {
  let p = state.personas.find((p) => p.id === id) || {
    name: "",
    technical_skill: "moderate",
    goal: "",
    criteria: [],
  };
  return (
    heading(
      id === "new" ? "Shape a perspective." : "Refine a perspective.",
      "Save directly to your backend persona library.",
    ) +
    `<div class="deck"><form class="panel" data-form="persona" data-id="${esc(id)}"><label for="pname">Name</label><input id="pname" name="name" value="${esc(p.name)}" required maxlength="100"><label for="pskill">Technical confidence</label><select id="pskill" name="technical_skill">${[...new Set([p.technical_skill, "low", "basic", "moderate", "intermediate", "high", "advanced"])].map((x) => `<option ${p.technical_skill === x ? "selected" : ""}>${x}</option>`).join("")}</select><label for="pgoal">Primary goal</label><textarea id="pgoal" name="goal" required maxlength="2000">${esc(p.goal)}</textarea><label for="pcriteria">Evaluation criteria · one per line</label><textarea id="pcriteria" name="criteria" required rows="7">${esc(p.criteria.join("\n"))}</textarea><div class="foot">${link("Cancel", "personas")}<button class="primary">Save persona →</button></div></form><aside class="panel" style="align-self:start"><div class="eyebrow">Design for someone</div><h2>People bring context.<br>Testing should too.</h2><p class="muted spacer">Your evaluator uses the name, technical confidence, goal and evaluation criteria stored in each persona.</p><div class="hint spacer">Manual editing is connected. Prompt-based persona generation is not implemented in the current backend.</div></aside></div>`
  );
}
