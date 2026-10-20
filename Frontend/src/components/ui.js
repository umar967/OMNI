export const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const btn = (text, action, cls = "", id = "", disabled = false) =>
  `<button type="button" class="${cls}" aria-label="${esc(
    text
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
  )}" data-action="${action}" data-id="${esc(id)}" ${disabled ? "disabled" : ""}>${text}</button>`;
export const link = (text, to, cls = "ghost") => btn(text, "navigate", cls, to);
export const heading = (title, desc, action = "") =>
  `<div class="heading"><div><div class="eyebrow">Your workspace, in perspective</div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div>${action}</div>`;
export const empty = (text, action = "") =>
  `<div class="empty"><p class="muted">${esc(text)}</p><div class="spacer">${action}</div></div>`;
export const date = (value) =>
  value
    ? new Date(value).toLocaleString("en-PK", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not recorded";
export function steps(n) {
  return `<div class="steps">${["Testing Deck", "Review plan", "Execution", "Report"].map((x, i) => `<span class="${i === n ? "current" : ""}"><i>${i + 1}</i>${x}</span>${i < 3 ? "<span>→</span>" : ""}`).join("")}</div>`;
}
export function toast(text) {
  let node = document.querySelector("#toast");
  node.textContent = text;
  node.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.style.display = "none"), 5500);
}
export const landscape = `<svg class="landscape" viewBox="0 0 1200 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#9baab6"/><stop offset=".6" stop-color="#d4c3ad"/><stop offset="1" stop-color="#b8b89d"/></linearGradient><linearGradient id="water" x2="0" y2="1"><stop stop-color="#819a91"/><stop offset="1" stop-color="#637d72"/></linearGradient><filter id="blur"><feGaussianBlur stdDeviation="8"/></filter></defs><path fill="url(#sky)" d="M0 0h1200v400H0z"/><circle cx="880" cy="110" r="32" fill="#e9ddbd" opacity=".7"/><path d="M0 230 140 130 270 208 420 110 580 230 710 164 860 222 1010 120 1200 220V400H0" fill="#6d8585" opacity=".3" filter="url(#blur)"/><path d="M0 270 160 210 300 256 460 193 650 274 820 220 1050 248 1200 193V400H0" fill="#647d78" opacity=".55"/><path fill="url(#water)" d="M0 285q300-40 600-5t600-5v125H0z"/><path d="M0 326q200-55 390-3l135 77H0z" fill="#3d5c4d"/><path d="m1200 288-150 44-210 68h360z" fill="#3b5b4b"/><g stroke="#47644e" stroke-width="3" opacity=".8"><path d="M60 400V300m-10 35 10-18 10 18m-20 14 10-18 10 18M90 400V320m-10 35 10-18 10 18M1130 400V295m-14 44 14-25 14 25m-29 18 15-26 15 26"/></g><g stroke="#ced5c0" opacity=".22"><path d="M540 310h180m-140 14h220m-260 19h310m-200 19h250"/></g></svg>`;
