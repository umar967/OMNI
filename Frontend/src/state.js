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
    instructions: "Create an account comfortably and independently.",
    persona_id: "older_user",
    screenshot_id: "signup.png",
    project_id: null,
    mode: "UX",
  }),
  plan: null,
  run: null,
  report: null,
  reportTab: "Overview",
  search: "",
  projectFilter: "",
  busy: false,
};
export function persist() {
  localStorage.setItem("omni:preferences", JSON.stringify(state.preferences));
  localStorage.setItem("omni:draft", JSON.stringify(state.draft));
}
export const currentPersona = () =>
  state.personas.find((p) => p.id === state.draft.persona_id) ||
  state.personas[0];
