import { state } from "../state.js";
import { esc, btn, link, heading, landscape } from "../components/ui.js";
export function settings() {
  return (
    heading(
      "Make yourself at home.",
      "Your preferences and backend connection.",
    ) +
    `<div class="deck"><form class="panel" data-form="settings"><h2>Profile & appearance</h2><label for="displayname">Display name</label><input name="name" id="displayname" value="${esc(state.preferences.name)}" maxlength="80"><div class="switchrow"><div><h3>Appearance</h3><p class="muted">A light or dark workspace.</p></div>${btn(state.preferences.theme === "dark" ? "☾ Dark" : "☀ Light", "theme", "ghost")}</div><div class="switchrow"><div><h3>Welcome flow</h3><p class="muted">Local entry and onboarding.</p></div>${link("Open welcome →", "login")}</div><div class="foot"><small>Preferences are stored in this browser.</small><button class="primary">Save preferences</button></div></form><aside class="panel" style="align-self:start"><h3>Backend connection</h3><div class="listrow"><small>API</small><span class="badge">Connected</span></div><div class="listrow"><small>Gemini key</small><span class="badge ${state.health.gemini_configured ? "" : "warn"}">${state.health.gemini_configured ? "Configured" : "Missing"}</span></div><div class="listrow"><small>Model</small><span>${esc(state.health.model)}</span></div><p class="muted spacer">${state.health.gemini_configured ? "Live evaluations are enabled." : "Add GEMINI_API_KEY to Backend/.env and restart the backend to enable new evaluations."}</p>${state.lastRun ? link("Open latest evaluation →", `execution/${state.lastRun}`, "ghost spacer") : ""}<div class="hint spacer">Connected: personas, projects, screenshots, review plans, Gemini analysis, saved reports and JSON export. Dashboard only uses sample data. Authentication and functional browser QA are not implemented.</div></aside></div>`
  );
}
export function login() {
  return `<div class="auth"><section class="authArt">${landscape}<div class="logo" style="position:relative">◒ OMNI</div><h1>A fresh perspective<br>on every experience.</h1><p>Thoughtful testing. Human perspective.</p></section><section class="authform"><form class="authinner" data-form="welcome"><div class="eyebrow">Welcome to OMNI</div><h1>Good to have you here.</h1><p class="muted">Open your local evaluation workspace.</p><label for="welcome-name">Your display name</label><input id="welcome-name" name="name" value="${esc(state.preferences.name)}" required maxlength="80"><button class="primary full">Continue →</button><div class="hint spacer">This app runs locally on your computer. No account system is connected, so no email or password is requested.</div></form></section></div>`;
}
export function onboarding() {
  return `<div class="onboard"><div class="logo">◒ OMNI</div><section class="panel spacer" style="padding:40px"><div class="eyebrow">A place to begin</div><h1>Let’s see through their eyes.</h1><p class="muted spacer">1. Choose one of your actual personas.<br>2. Select a screenshot and review the evaluation criteria.<br>3. Run Gemini analysis and inspect saved findings.</p><div class="foot">${link("Open saved reports", "reports")}${link("Enter workspace →", "dashboard", "primary")}</div></section></div>`;
}
