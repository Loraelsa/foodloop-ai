import { useCallback, useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import { Alert, CATEGORIES, OutcomeButtons, QrCard } from "./ui.jsx";
import Citizen from "./Citizen.jsx";
import Help, { AdminComplaints } from "./Help.jsx";

const STORAGES = { ambient: "Room temperature", refrigerated: "Refrigerated", hot_held: "Kept hot" };
const VERDICT = { sell: "Sell at a discount", donate: "Donate to an NGO", compost: "Send to compost" };

/* ---------- freshness ring ---------- */
function Ring({ score, hours, decision }) {
  const r = 52, c = 2 * Math.PI * r, color = `var(--${decision})`;
  return (
    <svg className="ring" viewBox="0 0 132 132" role="img" aria-label={`Freshness ${Math.round(score * 100)} percent, about ${hours} hours left`}>
      <circle cx="66" cy="66" r={r} fill="none" stroke="#e3e9e6" strokeWidth="12" />
      <circle cx="66" cy="66" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
        strokeDasharray={`${c * score} ${c}`} transform="rotate(-90 66 66)" />
      <text x="66" y="66" textAnchor="middle" fontSize="26" fontWeight="800" fill="currentColor">{Math.max(hours, 0).toFixed(1)}</text>
      <text x="66" y="86" textAnchor="middle" fontSize="12" fill="#55666f">hours left</text>
    </svg>
  );
}

function Verdict({ a }) {
  return (
    <div className="verdict">
      <Ring score={a.freshness_score} hours={a.remaining_hours} decision={a.decision} />
      <div>
        <div className={`verdict-title ${a.decision}`}>{VERDICT[a.decision]}</div>
        {a.decision === "sell" && <p>Suggested price ₹{a.price} ({a.discount_pct}% off)</p>}
        {a.decision === "donate" && <p>Too close to expiry to sell — an NGO can collect it for free.</p>}
        {a.decision === "compost" && <p>Not safe to eat. Composting avoids landfill emissions.</p>}
      </div>
    </div>
  );
}

/* ---------- route drawing (plain SVG: no map library, no tile downloads) ---------- */
function RouteMap({ routes }) {
  const pts = routes.flat();
  if (!pts.length) return null;
  const W = 520, H = 300, pad = 28;
  const lats = pts.map((p) => p.lat), lons = pts.map((p) => p.lon);
  const [la0, la1, lo0, lo1] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)];
  const sx = (lon) => pad + ((lon - lo0) / (lo1 - lo0 || 1)) * (W - 2 * pad);
  const sy = (lat) => H - pad - ((lat - la0) / (la1 - la0 || 1)) * (H - 2 * pad);
  const colors = ["#0e5c4b", "#1d6fa5", "#b7791f", "#6b4f3a", "#8a3ffc"];
  return (
    <svg className="route-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Optimised pickup route">
      {routes.map((rt, i) => (
        <g key={i}>
          <polyline fill="none" stroke={colors[i % 5]} strokeWidth="2.5" points={rt.map((p) => `${sx(p.lon)},${sy(p.lat)}`).join(" ")} />
          {rt.slice(0, -1).map((p, k) => (
            <g key={k}>
              <circle cx={sx(p.lon)} cy={sy(p.lat)} r={k === 0 ? 16 : 11} fill={k === 0 ? "#14222b" : colors[i % 5]} />
              <text x={sx(p.lon)} y={sy(p.lat) + 4} textAnchor="middle" fontSize={k === 0 ? "10" : "11"} fontWeight="700" fill="#fff">{k === 0 ? "NGO" : k}</text>
            </g>
          ))}
        </g>
      ))}
    </svg>
  );
}

/* ---------- brand + landing art ---------- */
function Logo() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <circle cx="24" cy="24" r="22" fill="#0f9d63" />
      <path d="M24 10a14 14 0 0 1 13.3 9.7" fill="none" stroke="#ffb020" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M38 26a14 14 0 0 1-22.6 8.4" fill="none" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M11 29A14 14 0 0 1 16 14.6" fill="none" stroke="#f0476a" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M33 8l5 2.5-3.5 4z" fill="#ffb020" />
    </svg>
  );
}

const reduceMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function LoopArt() {
  const still = reduceMotion();
  const path = "M220 40 A110 110 0 1 1 219.9 40";
  const dots = [["#0f9d63", 0], ["#f0476a", -3.4], ["#9a5b0b", -6.8]];
  return (
    <svg className="loop-art" viewBox="0 0 440 320" role="img" aria-label="Food moving from vendors to citizens and NGOs in a loop">
      <path id="loop" d={path} transform="translate(0 10)" fill="none" stroke="#1d1a33" strokeOpacity=".14" strokeWidth="14" strokeDasharray="2 18" strokeLinecap="round" />
      {!still && dots.map(([c, b], i) => (
        <circle key={i} r="11" fill={c}>
          <animateMotion dur="10s" begin={`${b}s`} repeatCount="indefinite" rotate="auto"><mpath href="#loop" /></animateMotion>
        </circle>
      ))}
      {still && dots.map(([c], i) => <circle key={i} r="11" fill={c} cx={220 + 110 * Math.cos(i * 2.09)} cy={160 + 110 * Math.sin(i * 2.09)} />)}
      <g className="station"><circle cx="220" cy="46" r="34" fill="#ffb020" /><text x="220" y="52" textAnchor="middle">Vendor</text></g>
      <g className="station"><circle cx="318" cy="228" r="34" fill="#0f9d63" /><text x="318" y="234" textAnchor="middle" style={{ fill: "#fff" }}>Citizen</text></g>
      <g className="station"><circle cx="122" cy="228" r="34" fill="#f0476a" /><text x="122" y="234" textAnchor="middle" style={{ fill: "#fff" }}>NGO</text></g>
      <text x="220" y="165" textAnchor="middle" style={{ fontSize: 22, fontWeight: 600 }}>Zero</text>
      <text x="220" y="190" textAnchor="middle" style={{ fontSize: 22, fontWeight: 600 }}>waste loop</text>
    </svg>
  );
}

function useCountUp(target, ms = 1100) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (reduceMotion() || !target) { setV(target); return; }
    let raf; const t0 = performance.now();
    const tick = (t) => { const p = Math.min((t - t0) / ms, 1); setV(target * (1 - Math.pow(1 - p, 3))); if (p < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function StatCard({ value, label, cls, decimals = 0 }) {
  const v = useCountUp(+value || 0);
  return (
    <div className={`card stat-card ${cls}`}>
      <div className="stat">{v.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

/* ---------- impact ---------- */
function Impact({ compact = false }) {
  const [d, setD] = useState(null);
  const [m, setM] = useState(null);
  useEffect(() => {
    api("/impact").then(setD).catch(() => {});
    if (!compact) api("/system/metrics").then(setM).catch(() => {});
  }, [compact]);
  if (!d) return <p className="muted">Loading impact…</p>;
  const items = [
    [d.kg_saved, "kg of food kept out of the bin", "kg", 1], [d.meals_redistributed, "meals given to people", "meals", 0],
    [d.co2_avoided_food_kg, "kg CO₂e avoided (estimate)", "co2", 1], [d.co2_avoided_routes_kg, "kg CO₂ saved by shorter routes", "km", 2],
  ];
  return (
    <>
      <div className="grid cols-2" style={{ gridTemplateColumns: compact ? "1fr 1fr" : undefined }}>
        {items.map(([v, l, c, dec]) => <StatCard key={l} value={v} label={l} cls={c} decimals={dec} />)}
      </div>
      {!compact && (
        <>
          <p className="muted" style={{ marginTop: ".8rem" }}>
            CO₂e uses {d.assumptions.co2e_per_kg_food} kg per kg of food and {d.assumptions.kg_per_meal} kg per meal. These are configurable estimates, not measurements.
          </p>
          {m && (
            <div className="card" style={{ marginTop: "1rem" }}>
              <h3>System efficiency (live)</h3>
              <p className="muted">API median {m.p50_ms} ms · 95th percentile {m.p95_ms} ms · cache hit rate {(m.cache_hit_rate * 100).toFixed(0)}% ({m.requests_sampled} requests sampled)</p>
            </div>
          )}
        </>
      )}
    </>
  );
}

/* ---------- auth ---------- */
function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ name: "", email: "", password: "", role: "vendor", lat: 28.6139, lon: 77.209 });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const locate = () =>
    navigator.geolocation?.getCurrentPosition((p) => setF((x) => ({ ...x, lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5) })),
      () => setErr("Location was blocked. Enter your latitude and longitude instead."));
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const body = mode === "login" ? { email: f.email, password: f.password } : { ...f, lat: +f.lat, lon: +f.lon };
      const r = await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", body });
      setToken(r.token); onAuth(r.user);
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  return (
    <div className="hero">
      <div>
        <h1>Food that is still good should reach a plate, not a bin.</h1>
        <p className="hero-lead">Vendors list surplus. FoodLoop AI checks how fresh it is and decides whether to sell it cheaper, donate it, or compost it. NGOs get the shortest pickup route.</p>
        <LoopArt />
        <h2 style={{ marginTop: "1.5rem" }}>Impact so far</h2>
        <Impact compact />
      </div>
      <form className="card auth-card" onSubmit={submit}>
        <h2>{mode === "login" ? "Log in" : "Create your account"}</h2>
        <Alert>{err}</Alert>
        {mode === "register" && (
          <>
            <label>Name<input required minLength={2} value={f.name} onChange={set("name")} autoComplete="name" /></label>
            <label>I am a
              <select value={f.role} onChange={set("role")}>
                <option value="vendor">Vendor with surplus food</option><option value="citizen">Citizen looking for discounted food</option><option value="ngo">NGO collecting donations</option>
              </select>
            </label>
          </>
        )}
        {mode === "register" && ["vendor", "ngo"].includes(f.role) && <p className="muted">Vendor and NGO accounts are checked by an admin before they can list or collect food.</p>}
        <label>Email<input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label>Password{mode === "register" && " (8+ characters)"}<input required type="password" minLength={mode === "register" ? 8 : 1} value={f.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {mode === "register" && (
          <>
            <div className="row">
              <label>Latitude<input type="number" step="any" value={f.lat} onChange={set("lat")} /></label>
              <label>Longitude<input type="number" step="any" value={f.lon} onChange={set("lon")} /></label>
            </div>
            <button type="button" className="btn ghost small" onClick={locate} style={{ marginBottom: ".9rem" }}>Use my location</button>
          </>
        )}
        <div><button className="btn" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}</button></div>
        <p className="muted" style={{ marginTop: ".8rem" }}>
          {mode === "login" ? "New here? " : "Already registered? "}
          <a href="#" onClick={(e) => { e.preventDefault(); setErr(""); setMode(mode === "login" ? "register" : "login"); }}>{mode === "login" ? "Create an account" : "Log in"}</a>
        </p>
      </form>
    </div>
  );
}

/* ---------- shared: QR code, outcome report, photo ---------- */
function Photo({ l }) {
  return l.has_photo ? <img className="thumb" loading="lazy" src={`/api/listings/${l.id}/photo`} alt={l.item_name} /> : null;
}

function VerifyBanner({ user }) {
  if (user.verified || !["vendor", "ngo"].includes(user.role)) return null;
  return <Alert kind="warn">Your account is waiting for admin approval. You can use the freshness check now; listing or accepting food unlocks once an admin approves you.</Alert>;
}

function Notifications() {
  const [n, setN] = useState({ unread: 0, items: [] }); const [open, setOpen] = useState(false);
  const load = useCallback(() => api("/notifications").then(setN).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);
  const toggle = async () => { setOpen(!open); if (!open && n.unread) { await api("/notifications/read", { method: "POST" }); setTimeout(load, 600); } };
  return (
    <div className="bell">
      <button className="btn ghost small" onClick={toggle} aria-label={`Notifications, ${n.unread} unread`}>Alerts{n.unread ? <b className="badge">{n.unread}</b> : null}</button>
      {open && <div className="card pop">{!n.items.length ? <p className="muted">No alerts yet.</p> : n.items.map((i) => <p key={i.id} className={i.read ? "muted" : ""}>{i.message}</p>)}</div>}
    </div>
  );
}

/* ---------- vendor ---------- */
const EMPTY = { item_name: "", category: "cooked_meal", quantity_kg: 5, mrp: 300, hours_since_prepared: 2, storage: "ambient", ambient_temp_c: 30 };

function Vendor({ user }) {
  const [f, setF] = useState(EMPTY); const [code, setCode] = useState(""); const [photoFile, setPhotoFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const load = useCallback(() => api("/listings/mine").then(setRows).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const set = (k, num) => (e) => { setPreview(null); setF({ ...f, [k]: num ? +e.target.value : e.target.value }); };
  const body = () => ({ ...f, item_name: f.item_name || "Unnamed item" });
  const check = async () => { setErr(""); try { setPreview(await api("/predict", { method: "POST", body: body() })); } catch (e) { setErr(e.message); } };
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setOk("");
    try {
      const l = await api("/listings", { method: "POST", body: body() });
      if (photoFile) { const form = new FormData(); form.append("file", photoFile); await api(`/listings/${l.id}/photo`, { method: "POST", form }).catch((pe) => setErr(`Listed, but the photo failed: ${pe.message}`)); }
      setPhotoFile(null); setOk(`Listed “${l.item_name}” — decision: ${VERDICT[l.decision].toLowerCase()}.`); setPreview(null); setF(EMPTY); load();
    } catch (e2) { setErr(e2.message); }
  };
  const complete = async (id) => { try { await api(`/listings/${id}/complete`, { method: "POST" }); load(); } catch (e) { setErr(e.message); } };
  const handover = async (e) => {
    e.preventDefault(); setErr(""); setOk("");
    try { const l = await api("/handover", { method: "POST", body: { code } }); setOk(`Handover confirmed for “${l.item_name}”.`); setCode(""); load(); } catch (e2) { setErr(e2.message); }
  };
  return (
    <div style={{ marginTop: "1rem" }}>
    <VerifyBanner user={user} />
    <div className="grid cols-2">
      <form className="card" onSubmit={submit}>
        <h2>List surplus food</h2>
        <Alert>{err}</Alert><Alert kind="ok">{ok}</Alert>
        <label>Item name<input required minLength={2} value={f.item_name} onChange={set("item_name")} placeholder="e.g. Veg biryani" /></label>
        <div className="row">
          <label>Category<select value={f.category} onChange={set("category")}>{Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label>Storage<select value={f.storage} onChange={set("storage")}>{Object.entries(STORAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        </div>
        <div className="row">
          <label>Quantity (kg)<input type="number" min="0.1" step="0.1" required value={f.quantity_kg} onChange={set("quantity_kg", true)} /></label>
          <label>Full price for the lot (₹)<input type="number" min="0" step="1" value={f.mrp} onChange={set("mrp", true)} /></label>
        </div>
        <div className="row">
          <label>Hours since prepared<input type="number" min="0" step="0.5" required value={f.hours_since_prepared} onChange={set("hours_since_prepared", true)} /></label>
          <label>Room temperature (°C)<input type="number" min="-10" max="55" step="1" value={f.ambient_temp_c} onChange={set("ambient_temp_c", true)} /></label>
        </div>
        <label>Photo (optional, JPEG/PNG/WebP, up to 1.5 MB)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setPhotoFile(e.target.files[0] || null)} /></label>
        <button type="button" className="btn ghost" onClick={check}>Check freshness</button>{" "}
        <button className="btn">List item</button>
        {preview && <div style={{ marginTop: "1.2rem" }}><Verdict a={preview} /></div>}
      </form>
      <div className="card">
        <h2>Confirm a handover</h2>
        <form onSubmit={handover} className="row" style={{ alignItems: "end" }}>
          <label>Buyer or NGO code (from their QR)<input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={10} placeholder="e.g. K7M2QX9A" required /></label>
          <div><button className="btn">Confirm</button></div>
        </form>
        <h2 style={{ marginTop: "1.4rem" }}>Your listings</h2>
        {!rows.length ? <p className="muted">Nothing listed yet. Add your first surplus item on the left.</p> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Item</th><th>Decision</th><th>Status</th><th></th></tr></thead>
            <tbody>{rows.map((l) => (
              <tr key={l.id}>
                <td><Photo l={l} />{l.item_name}<div className="muted">{l.quantity_kg} kg</div></td>
                <td><span className={`tag ${l.decision}`}>{l.decision}</span>{l.decision === "sell" && <div className="muted">₹{l.price}</div>}</td>
                <td><span className="tag status">{l.status}</span></td>
                <td>{l.status !== "completed" && l.decision !== "donate" && (l.decision === "compost" || l.status === "reserved") &&
                  <button className="btn small" onClick={() => complete(l.id)}>{l.decision === "compost" ? "Mark composted" : "Mark collected"}</button>}
                  {l.status === "completed" && l.decision !== "compost" && <OutcomeButtons id={l.id} />}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </div>
    </div>
  );
}

/* ---------- NGO ---------- */
function Ngo({ user }) {
  const [accepted, setAccepted] = useState([]);
  const [rows, setRows] = useState([]); const [sel, setSel] = useState([]); const [pickups, setPickups] = useState([]);
  const [vehicles, setVehicles] = useState(1); const [cap, setCap] = useState("");
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api("/donations").then(setRows).catch((e) => setErr(e.message)); api("/ngo/pickups").then(setPickups).catch(() => {}); api("/my/items").then(setAccepted).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const plan = async () => {
    setErr(""); setBusy(true);
    try { await api("/ngo/accept", { method: "POST", body: { listing_ids: sel, vehicles: +vehicles, capacity_kg: cap ? +cap : null } }); setSel([]); load(); }
    catch (e) { setErr(e.message); load(); } finally { setBusy(false); }
  };
  const done = async (id) => { await api(`/ngo/pickups/${id}/complete`, { method: "POST" }); load(); };
  return (
    <div style={{ marginTop: "1rem" }}>
    <VerifyBanner user={user} />
    <div className="grid cols-2">
      <div className="card">
        <h2>Donations available</h2>
        <Alert>{err}</Alert>
        {!rows.length ? <p className="muted">No donations waiting. New ones appear when vendors list food that is too close to expiry to sell.</p> : (
          <>
            <div className="table-wrap"><table>
              <thead><tr><th></th><th>Item</th><th>Kg</th><th>Distance</th></tr></thead>
              <tbody>{rows.map((l) => (
                <tr key={l.id}>
                  <td><input type="checkbox" style={{ width: "auto" }} checked={sel.includes(l.id)} onChange={() => toggle(l.id)} aria-label={`Select ${l.item_name}`} /></td>
                  <td><Photo l={l} />{l.item_name}<div className="muted">{l.vendor} · {l.remaining_hours} h left</div></td><td>{l.quantity_kg}</td><td>{l.distance_km} km</td>
                </tr>))}</tbody>
            </table></div>
            <div className="row" style={{ marginTop: ".9rem" }}>
              <label>Vehicles<input type="number" min="1" max="5" value={vehicles} onChange={(e) => setVehicles(e.target.value)} /></label>
              <label>Capacity per vehicle (kg, optional)<input type="number" min="1" value={cap} onChange={(e) => setCap(e.target.value)} /></label>
            </div>
            <button className="btn" disabled={!sel.length || busy} onClick={plan}>{busy ? "Planning…" : `Plan pickup (${sel.length} selected)`}</button>
          </>
        )}
      </div>
      <div className="grid">
        {!pickups.length ? <div className="card"><h2>Pickup routes</h2><p className="muted">Select donations and plan a pickup to see the shortest route here.</p></div> : pickups.map((p) => (
          <div className="card" key={p.id}>
            <h2>Pickup #{p.id} <span className="tag status">{p.status}</span></h2>
            <RouteMap routes={p.route.routes} />
            <p className="muted">Distances: {p.route.distance_source === "osrm" ? "real road network (OSRM)" : "straight-line estimate × 1.3 (road service unavailable)"}</p>
            {accepted.filter((a) => a.status !== "completed").map((a) => a && p.route.routes.flat().some((s) => s.listing_id === a.id) && <div key={a.id} className="mine"><b>{a.item_name}</b> · {a.vendor}<QrCard item={a} /></div>)}
            <p style={{ marginTop: ".6rem" }}>{p.total_kg} kg · <b>{p.distance_km} km</b> planned vs {p.baseline_km} km in acceptance order — saves {(p.baseline_km - p.distance_km).toFixed(1)} km and about {p.co2_saved_kg} kg CO₂.</p>
            {p.status === "planned" && <button className="btn small" onClick={() => done(p.id)}>Mark collected</button>}
          </div>))}
        {accepted.filter((a) => a.status === "completed" && !a.reported).slice(0, 5).map((a) => <div key={a.id} className="card"><b>{a.item_name}</b> collected. <OutcomeButtons id={a.id} onDone={load} /></div>)}
      </div>
    </div>
    </div>
  );
}

/* ---------- admin ---------- */
function Admin() {
  const [pending, setPending] = useState([]); const [stats, setStats] = useState(null); const [err, setErr] = useState(""); const [msg, setMsg] = useState("");
  const load = useCallback(() => { api("/admin/pending").then(setPending).catch((e) => setErr(e.message)); api("/admin/outcome-stats").then(setStats).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const decide = async (id, approve) => { await api(`/admin/users/${id}/verify`, { method: "POST", body: { approve } }); load(); };
  const calibrate = async () => { const r = await api("/admin/calibrate", { method: "POST" }); setMsg(r.status === "ok" ? `Safety margin set to ${r.recommended_margin_h} h.` : `Need ${r.needed} reported outcomes (have ${r.n}).`); load(); };
  return (
    <div className="grid cols-2" style={{ marginTop: "1rem" }}>
      <div className="card">
        <h2>Accounts waiting for approval</h2><Alert>{err}</Alert>
        {!pending.length ? <p className="muted">Nobody is waiting.</p> : pending.map((u) => (
          <div key={u.id} className="mine"><b>{u.name}</b> · {u.role} · {u.email}<br />
            <button className="btn small" onClick={() => decide(u.id, true)}>Approve</button>
          </div>))}
      </div>
      <div className="card">
        <h2>Model feedback</h2>
        {stats && <p className="muted">{stats.status === "ok" ? `${stats.n} reported outcomes, ${stats.spoiled_total} spoiled. Recommended safety margin: ${stats.recommended_margin_h} h (current ${stats.current_margin_h} h).` : `${stats.n} of ${stats.needed} reported outcomes needed before calibration.`}</p>}
        <Alert kind="ok">{msg}</Alert>
        <button className="btn" onClick={calibrate}>Calibrate safety margin</button>{" "}
        <a className="btn ghost" href="#" onClick={async (e) => { e.preventDefault(); const r = await fetch("/api/admin/outcomes.csv", { headers: { Authorization: `Bearer ${localStorage.getItem("fl_token")}` } }); const b = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "outcomes.csv"; a.click(); }}>Download outcomes CSV</a>
      </div>
      <AdminComplaints />
    </div>
  );
}

/* ---------- app shell ---------- */
const TABS = {
  citizen: [["home", "Explore", "🏠"], ["orders", "Orders", "🧾"], ["saved", "Saved", "♥"], ["help", "Help", "💬"], ["impact", "Impact", "🌱"]],
  vendor: [["work", "My listings", "🍽️"], ["help", "Help", "💬"], ["impact", "Impact", "🌱"]],
  ngo: [["work", "Pickups", "🚚"], ["help", "Help", "💬"], ["impact", "Impact", "🌱"]],
  admin: [["work", "Admin", "🛡️"], ["impact", "Impact", "🌱"]],
};

export default function App() {
  const [user, setUser] = useState(null); const [ready, setReady] = useState(false);
  const [tab, setTab] = useState(null); const [helpFor, setHelpFor] = useState(null);
  useEffect(() => { api("/me").then(setUser).catch(() => setToken("")).finally(() => setReady(true)); }, []);
  const logout = () => { setToken(""); setUser(null); setTab(null); };
  const goto = (v, extra) => { setHelpFor(extra || null); setTab(v); window.scrollTo?.({ top: 0 }); };
  if (!ready) return null;
  const tabs = user ? TABS[user.role] : [];
  const view = tab && tabs.some(([k]) => k === tab) ? tab : tabs[0]?.[0];
  const body = !user ? <Auth onAuth={setUser} />
    : view === "impact" ? <div><h1 className="page-title">Community impact</h1><Impact /></div>
    : view === "help" ? <Help user={user} prefill={helpFor} />
    : user.role === "citizen" ? <Citizen user={user} view={view} goto={goto} />
    : { vendor: <Vendor user={user} />, ngo: <Ngo user={user} />, admin: <Admin /> }[user.role];
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><Logo /><span className="name">Food<b>Loop</b> AI</span></div>
        {user && (
          <>
            <nav className="tabs" aria-label="Main">
              {tabs.map(([k, label, ico]) => (
                <button key={k} className="tab" aria-current={view === k ? "page" : undefined} onClick={() => goto(k)}><span className="tab-ico" aria-hidden="true">{ico}</span><span>{label}</span></button>
              ))}
            </nav>
            <Notifications />
            <span className="who">{user.name} · {user.role}{["vendor", "ngo"].includes(user.role) && !user.verified ? " (pending)" : ""}</span>
            <button className="btn ghost small" onClick={logout}>Log out</button>
          </>
        )}
      </header>
      <main key={view}>{body}</main>
    </div>
  );
}
