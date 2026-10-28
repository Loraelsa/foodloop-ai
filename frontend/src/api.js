let token = localStorage.getItem("fl_token") || "";

export const setToken = (t) => {
  token = t || "";
  t ? localStorage.setItem("fl_token", t) : localStorage.removeItem("fl_token");
};

export async function api(path, { method = "GET", body, form } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: { ...(form ? {} : { "Content-Type": "application/json" }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: form ? form : body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = Array.isArray(d) ? d.map((e) => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join("; ") : d || "Something went wrong";
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}
