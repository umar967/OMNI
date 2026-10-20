/** Same-origin API. Keys and model calls stay in Backend. No mock fallback. */
export async function api(path, { method = "GET", body } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-OMNI-Client": "workspace",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Cannot reach the OMNI backend. Start it with start.ps1, then refresh.",
    );
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((x) => x.msg).join(" · ")
        : detail || "The request failed.",
    );
  }
  return data;
}
export const imageUrl = (id) => `/api/screenshots/${encodeURIComponent(id)}`;
