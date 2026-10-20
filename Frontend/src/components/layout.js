import { state } from "../state.js";
import { btn, esc } from "./ui.js";
export function layout(body, page) {
  const p = state.preferences;
  const nav = [
    ["dashboard", "◫", "Overview"],
    ["projects", "▦", "Projects"],
    ["deck", "⌁", "Testing Deck"],
    ["personas", "♧", "Persona Library"],
    ["reports", "▤", "Reports Library"],
  ];
  const names = {
    dashboard: "Overview",
    projects: "Projects",
    project: "Project details",
    deck: "Testing Deck",
    plan: "Test Plan Review",
    execution: "Execution Monitor",
    personas: "Persona Library",
    builder: "Persona Builder",
    reports: "Reports Library",
    report: "Report Viewer",
    settings: "Settings",
  };
  return `<div class="shell ${p.collapsed ? "collapsed" : ""}"><aside class="sidebar"><div class="logo"><span class="mark">◒</span><span class="hide">OMNI</span></div><div class="workspace"><span class="avatar">O</span><span class="hide">Personal workspace<br><small>Local evaluation</small></span></div><nav class="nav" aria-label="Primary">${nav.map(([to, i, t]) => btn(`<span class="ico">${i}</span><span class="hide">${t}</span>`, "navigate", page === to || (to === "deck" && ["plan", "execution"].includes(page)) || (to === "reports" && page === "report") || (to === "personas" && page === "builder") ? "active" : "", to)).join("")}</nav><div class="sidebottom"><nav class="nav">${btn('<span class="ico">⚙</span><span class="hide">Settings</span>', "navigate", page === "settings" ? "active" : "", "settings")}${btn('<span class="ico">⇥</span><span class="hide">Collapse sidebar</span>', "collapse")}</nav><div class="profile"><span class="avatar">${esc(p.name[0] || "A")}</span><span class="hide">${esc(p.name)}<br><small>Local workspace</small></span></div></div></aside><main class="main"><header><div class="crumb">Workspace <span style="margin:0 12px">/</span> ${names[page] || "Overview"}</div><div class="topright"><span class="pill">${page === "dashboard" ? "Sample dashboard" : "Connected to local backend"}</span>${btn(p.theme === "dark" ? "☀ Light" : "☾ Dark", "theme", "icon")}<span class="avatar">${esc(p.name[0] || "A")}</span></div></header><div class="content">${body}<div class="notice"><span class="pulse"></span>${page === "dashboard" ? "Dashboard metrics are illustrative. All other screens use your backend data." : "Your personas, screenshots and reports · Stored in Backend on this computer."}</div></div></main></div>`;
}
