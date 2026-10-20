const read = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
};
export const state = {
  preferences: read("omni:preferences", {
    name: "Alex",
    theme: "light",
    collapsed: false,
  }),
  health: null,
  personas: [],
  projects: [],
  reports: [],
  screenshots: [],
  draft: read("omni:draft", {
    url: "http://127.0.0.1:5173/login?mode=signup",
    instructions: "Explore signup and fill the name and email fields. Stop before submitting.",
    persona_id: "older_user",
    screenshot_id: "signup.png",
    project_id: null,
    mode: "UX",
    max_actions: 4,
  }),
  plan: null,
  run: null,
  report: null,
  evidence: [],
  reportTab: "Overview",
  search: "",
  projectFilter: "",
  busy: false,
};
export function persist() {
  localStorage.setItem("omni:preferences", JSON.stringify(state.preferences));
  localStorage.setItem("omni:draft", JSON.stringify(state.draft));
}
