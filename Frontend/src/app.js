import { api } from "./api.js";
import { state, persist } from "./state.js";
import { toast, empty, link } from "./components/ui.js";
import { layout } from "./components/layout.js";
import { dashboard } from "./pages/dashboard.js";
import { personas, builder } from "./pages/personas.js";
import { projects, project, projectNew } from "./pages/projects.js";
import { deck, plan, execution } from "./pages/testing.js";
import { reports, report, filteredRows } from "./pages/reports.js";
import { settings, login, onboarding } from "./pages/settings.js";

let page = "dashboard",
  itemId = "",
  poll = null,
  revision = 0;
const $ = (s) => document.querySelector(s);
export function navigate(to) {
  captureDraft();
  captureCases();
  location.hash = to;
}
async function refresh() {
  [
    state.health,
    state.personas,
    state.projects,
    state.reports,
    state.screenshots,
  ] = await Promise.all(
    ["/health", "/personas", "/projects", "/reports", "/screenshots"].map((p) =>
      api(p),
    ),
  );
}
function draw() {
  document.body.classList.toggle("dark", state.preferences.theme === "dark");
  const views = {
    dashboard,
    projects,
    project: () => project(itemId),
    "project-new": projectNew,
    personas,
    builder: () => builder(itemId),
    deck,
    plan,
    execution,
    reports,
    report,
    settings,
  };
  $("#app").innerHTML =
    page === "login"
      ? login()
      : page === "onboarding"
        ? onboarding()
        : layout((views[page] || dashboard)(), page);
}
function redrawKeepingFormValues() {
  const drafts = [...document.forms].map((form) =>
    [...form.elements]
      .filter((el) => el.name && el.type !== "file")
      .map((el) => ({ name: el.name, value: el.value, checked: el.checked })),
  );
  draw();
  [...document.forms].forEach((form, i) => {
    [...form.elements]
      .filter((el) => el.name && el.type !== "file")
      .forEach((el, j) => {
        const saved = drafts[i]?.[j];
        if (saved?.name === el.name) {
          el.value = saved.value;
          if (el.type === "checkbox") el.checked = saved.checked;
        }
      });
  });
}
async function route() {
  clearTimeout(poll);
  let rev = ++revision;
  [page, itemId] = location.hash.slice(1).split("/");
  page ||= "dashboard";
  try {
    await refresh();
    if (rev !== revision) return;
    if (page === "deck" && itemId) {
      let p = state.projects.find((p) => p.id === itemId);
      if (p) state.draft = { ...state.draft, url: p.url, project_id: p.id };
    }
    if (page === "plan")
      state.plan = await api(`/plans/${encodeURIComponent(itemId)}`);
    if (page === "execution") {
      state.run = await api(`/runs/${encodeURIComponent(itemId)}`);
      state.lastRun = itemId;
      localStorage.setItem("omni:last-run", itemId);
    }
    if (page === "report") {
      state.report = await api(`/reports/${encodeURIComponent(itemId)}`);
      state.reportTab = "Overview";
    }
    if (rev !== revision) return;
    draw();
    window.scrollTo(0, 0);
    if (page === "execution") schedulePoll();
  } catch (error) {
    if (rev !== revision) return;
    $("#app").innerHTML = layout(
      empty(error.message, link("Back to overview", "dashboard")),
      page,
    );
  }
}
function captureDraft() {
  const form = $('[data-form="deck"]');
  if (!form) return;
  const values = Object.fromEntries(new FormData(form));
  state.draft = {
    ...state.draft,
    ...values,
    project_id: values.project_id || null,
    mode: "UX",
  };
  persist();
}
function captureCases() {
  const form = $("#planform");
  if (!form || !state.plan) return;
  state.plan.cases = [...form.querySelectorAll("[data-case]")].map((el) => ({
    id: el.dataset.case,
    title: el.querySelector("[name=title]").value,
    expected: el.querySelector("[name=expected]").value,
    selected: el.querySelector("[name=selected]").checked,
  }));
}
async function savePlan() {
  captureCases();
  state.plan = await api(`/plans/${state.plan.id}`, {
    method: "PUT",
    body: { cases: state.plan.cases },
  });
}
function schedulePoll() {
  if (!state.run || ["completed", "failed"].includes(state.run.status)) return;
  const id = state.run.id;
  poll = setTimeout(async () => {
    if (page !== "execution" || itemId !== id) return;
    try {
      state.run = await api(`/runs/${id}`);
      if (page !== "execution" || itemId !== id) return;
      draw();
      schedulePoll();
    } catch (e) {
      toast(e.message);
      schedulePoll();
    }
  }, 1200);
}
async function busy(action) {
  if (state.busy) return;
  state.busy = true;
  let overlay = document.createElement("div");
  overlay.className = "busy";
  overlay.setAttribute("role", "status");
  overlay.textContent = "Working…";
  document.body.append(overlay);
  try {
    await action();
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = false;
    overlay.remove();
  }
}
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action,
    id = button.dataset.id;
  switch (action) {
    case "navigate":
      navigate(id);
      break;
    case "theme":
      captureDraft();
      captureCases();
      state.preferences.theme =
        state.preferences.theme === "dark" ? "light" : "dark";
      persist();
      redrawKeepingFormValues();
      break;
    case "collapse":
      captureDraft();
      captureCases();
      state.preferences.collapsed = !state.preferences.collapsed;
      persist();
      redrawKeepingFormValues();
      break;
    case "use-persona":
      state.draft.persona_id = id;
      persist();
      navigate("deck");
      break;
    case "add-case":
      captureCases();
      state.plan.cases.push({
        id: crypto.randomUUID(),
        title: "New review criterion",
        expected: "Describe what should be visible in the screenshot.",
        selected: true,
      });
      draw();
      break;
    case "remove-case":
      captureCases();
      state.plan.cases = state.plan.cases.filter((c) => c.id !== id);
      draw();
      break;
    case "save-plan":
      busy(async () => {
        await savePlan();
        draw();
        toast("Plan saved to the backend.");
      });
      break;
    case "report-tab":
      state.reportTab = id;
      draw();
      break;
    case "export-report": {
      let a = document.createElement("a");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(state.report, null, 2)], {
          type: "application/json",
        }),
      );
      a.href = url;
      a.download = `OMNI-${state.report.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
      break;
    }
    case "capture":
      captureDraft();
      busy(async () => {
        const image = await api("/capture", {
          method: "POST",
          body: { url: state.draft.url, name: "TestLab capture" },
        });
        state.draft.screenshot_id = image.id;
        persist();
        await refresh();
        draw();
        toast("Real Chrome screenshot captured. Review it before evaluation.");
      });
      break;
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-form]");
  if (!form) return;
  event.preventDefault();
  const type = form.dataset.form;
  const values = Object.fromEntries(new FormData(form));
  busy(async () => {
    switch (type) {
      case "deck":
        captureDraft();
        state.plan = await api("/plans", { method: "POST", body: state.draft });
        navigate(`plan/${state.plan.id}`);
        break;
      case "plan":
        await savePlan();
        state.run = await api("/runs", {
          method: "POST",
          body: { plan_id: state.plan.id },
        });
        navigate(`execution/${state.run.id}`);
        break;
      case "persona": {
        let body = {
          ...values,
          criteria: values.criteria
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        };
        await api(
          form.dataset.id === "new"
            ? "/personas"
            : `/personas/${form.dataset.id}`,
          { method: form.dataset.id === "new" ? "POST" : "PUT", body },
        );
        navigate("personas");
        toast("Persona saved.");
        break;
      }
      case "project": {
        let p = await api("/projects", { method: "POST", body: values });
        navigate(`project/${p.id}`);
        toast("Project created.");
        break;
      }
      case "settings":
        state.preferences.name = values.name.trim() || "Alex";
        persist();
        draw();
        toast("Preferences saved.");
        break;
      case "welcome":
        state.preferences.name = values.name.trim() || "Alex";
        persist();
        navigate("onboarding");
        break;
    }
  });
});
document.addEventListener("change", (event) => {
  if (event.target.id === "screenshot" || event.target.id === "persona") {
    captureDraft();
    draw();
  }
  if (event.target.id === "reportfilter") {
    state.projectFilter = event.target.value;
    $("#reportrows").innerHTML = filteredRows();
  }
  if (event.target.id === "upload") {
    const file = event.target.files[0];
    if (!file) return;
    captureDraft();
    if (file.size > 10 * 1024 * 1024)
      return toast("Use an image smaller than 10 MB.");
    busy(async () => {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Cannot read this image."));
        reader.readAsDataURL(file);
      });
      const image = await api("/screenshots", {
        method: "POST",
        body: { name: file.name, data },
      });
      state.draft.screenshot_id = image.id;
      persist();
      await refresh();
      draw();
      toast("Screenshot uploaded.");
    });
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id === "reportsearch") {
    state.search = event.target.value;
    $("#reportrows").innerHTML = filteredRows();
  }
  if (page === "deck") captureDraft();
  if (page === "plan") {
    captureCases();
    const count = $("#selected-count");
    if (count)
      count.textContent = `${state.plan.cases.filter((c) => c.selected).length} selected`;
  }
});
state.lastRun = localStorage.getItem("omni:last-run");
window.addEventListener("hashchange", route);
route();
