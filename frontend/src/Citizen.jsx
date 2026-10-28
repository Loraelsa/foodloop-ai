import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { Alert, CATEGORIES, CAT_EMOJI, FoodImage, OutcomeButtons, QrCard, RatingBadge, StarPicker, fmtLeft } from "./ui.jsx";

const SORTS = { near: "Nearest first", cheap: "Price: low to high", off: "Biggest discount", fresh: "Freshest first" };
const FILTERS = [["top", "Rated 4.0+"], ["deal", "40% off or more"], ["cheap", "Under ₹150"], ["close", "Within 5 km"], ["saved", "Saved ♥"]];
const rupees = (n) => `₹${Math.round(n)}`;
const directions = (l) => `https://www.google.com/maps/dir/?api=1&destination=${l.lat},${l.lon}`;

function useSaved() {
  const [ids, setIds] = useState(() => { try { return JSON.parse(localStorage.getItem("fl_saved") || "[]"); } catch { return []; } });
  const toggle = (id) => setIds((cur) => {
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    try { localStorage.setItem("fl_saved", JSON.stringify(next)); } catch { /* storage blocked: saves last for this visit only */ }
    return next;
  });
  return [ids, toggle];
}

/* ---------- one food card ---------- */
function DealCard({ l, saved, onSave, onOpen }) {
  return (
    <article className="deal" onClick={() => onOpen(l)}>
      <div className="deal-img">
        <FoodImage l={l} />
        <span className="ribbon">{Math.round(l.discount_pct)}% OFF</span>
        <button className={`heart ${saved ? "on" : ""}`} aria-pressed={saved} aria-label={saved ? `Remove ${l.item_name} from saved` : `Save ${l.item_name}`}
          onClick={(e) => { e.stopPropagation(); onSave(l.id); }}>{saved ? "♥" : "♡"}</button>
        <span className="timer">{fmtLeft(l.remaining_hours)} left</span>
      </div>
      <div className="deal-body">
        <div className="deal-top"><h3><button className="title-btn" onClick={(e) => { e.stopPropagation(); onOpen(l); }}>{l.item_name}</button></h3><RatingBadge rating={l.vendor_rating} reviews={l.vendor_reviews} /></div>
        <p className="meta">{l.vendor}</p>
        <p className="meta">{CATEGORIES[l.category]} · {l.distance_km} km away · {l.quantity_kg} kg</p>
        <p className="deal-price"><b>{rupees(l.price)}</b> <s>{rupees(l.mrp)}</s> <span className="save">You save {rupees(l.mrp - l.price)}</span></p>
      </div>
    </article>
  );
}

/* ---------- detail sheet ---------- */
function Sheet({ l, onClose, onReserve, busy }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const pct = Math.round(Math.min(Math.max(l.freshness_score, 0.06), 1) * 100);
  return (
    <div className="backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={l.item_name} onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <div className="sheet-img"><FoodImage l={l} big /><span className="ribbon">{Math.round(l.discount_pct)}% OFF</span></div>
        <div className="sheet-body">
          <div className="deal-top"><h2>{l.item_name}</h2><RatingBadge rating={l.vendor_rating} reviews={l.vendor_reviews} /></div>
          <p className="meta">{l.vendor} · {l.distance_km} km away · <a href={directions(l)} target="_blank" rel="noreferrer">Get directions</a></p>
          <div className="fresh-box">
            <div className="fresh-row"><b>About {fmtLeft(l.remaining_hours)} of freshness left</b><span className="muted">{pct}%</span></div>
            <div className="fresh-bar" aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>
            <p className="muted">Our model estimates this from the food type, storage, temperature and how long ago it was made. Eat it soon after pickup.</p>
          </div>
          <dl className="bill">
            <div><dt>Full price</dt><dd><s>{rupees(l.mrp)}</s></dd></div>
            <div><dt>Rescue discount ({Math.round(l.discount_pct)}%)</dt><dd className="save">− {rupees(l.mrp - l.price)}</dd></div>
            <div className="total"><dt>Pay at pickup</dt><dd>{rupees(l.price)}</dd></div>
          </dl>
          <p className="muted">{l.quantity_kg} kg available. Reserve it, then show your QR code at the counter. You can cancel any time before pickup.</p>
          <button className="btn wide" disabled={busy} onClick={() => onReserve(l)}>{busy ? "Reserving…" : `Reserve for ${rupees(l.price)}`}</button>
        </div>
      </div>
    </div>
  );
}

/* ---------- explore ---------- */
function Explore({ user, rows, radius, setRadius, saved, toggleSave, onOpen, err }) {
  const [q, setQ] = useState(""); const [cat, setCat] = useState("all"); const [sort, setSort] = useState("near"); const [on, setOn] = useState([]);
  const flip = (k) => setOn((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]));
  const counts = useMemo(() => (rows || []).reduce((m, l) => ({ ...m, [l.category]: (m[l.category] || 0) + 1 }), {}), [rows]);
  const shown = useMemo(() => {
    let r = rows || [];
    const s = q.trim().toLowerCase();
    if (s) r = r.filter((l) => `${l.item_name} ${l.vendor} ${CATEGORIES[l.category]}`.toLowerCase().includes(s));
    if (cat !== "all") r = r.filter((l) => l.category === cat);
    if (on.includes("top")) r = r.filter((l) => (l.vendor_rating || 0) >= 4);
    if (on.includes("deal")) r = r.filter((l) => l.discount_pct >= 40);
    if (on.includes("cheap")) r = r.filter((l) => l.price < 150);
    if (on.includes("close")) r = r.filter((l) => l.distance_km <= 5);
    if (on.includes("saved")) r = r.filter((l) => saved.includes(l.id));
    const by = { near: (a, b) => a.distance_km - b.distance_km, cheap: (a, b) => a.price - b.price, off: (a, b) => b.discount_pct - a.discount_pct, fresh: (a, b) => b.freshness_score - a.freshness_score };
    return [...r].sort(by[sort]);
  }, [rows, q, cat, sort, on, saved]);
  const maxOff = rows?.length ? Math.round(Math.max(...rows.map((l) => l.discount_pct))) : 0;
  return (
    <>
      <section className="hero-banner">
        <div>
          <p className="loc">📍 Near {user.name.split(" ")[0]}'s location · within
            <select aria-label="Search radius" value={radius} onChange={(e) => setRadius(+e.target.value)}>{[5, 10, 30, 100].map((r) => <option key={r} value={r}>{r} km</option>)}</select></p>
          <h1>Good food, rescued at up to {maxOff || 70}% off</h1>
          <p>{rows === null ? "Looking for deals…" : `${rows.length} ${rows.length === 1 ? "deal" : "deals"} from nearby kitchens, picked by freshness.`}</p>
        </div>
        <div className="banner-emoji" aria-hidden="true"><span>🍛</span><span>🥐</span><span>🥗</span></div>
      </section>

      <div className="searchbar">
        <span aria-hidden="true">🔍</span>
        <input type="search" placeholder="Search food or kitchens" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search food or kitchens" />
      </div>

      <h2 className="section">What are you craving?</h2>
      <div className="cats" role="group" aria-label="Food categories">
        <button className={`cat ${cat === "all" ? "active" : ""}`} onClick={() => setCat("all")}><span className="cat-dot">🍽️</span>All<small>{rows?.length ?? 0}</small></button>
        {Object.entries(CATEGORIES).map(([k, v]) => (
          <button key={k} className={`cat ${cat === k ? "active" : ""}`} onClick={() => setCat(k)} aria-pressed={cat === k}><span className="cat-dot">{CAT_EMOJI[k]}</span>{v}<small>{counts[k] || 0}</small></button>
        ))}
      </div>

      <div className="filters" role="group" aria-label="Filters">
        <label className="sort">Sort<select value={sort} onChange={(e) => setSort(e.target.value)}>{Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        {FILTERS.map(([k, v]) => <button key={k} className={`chip ${on.includes(k) ? "active" : ""}`} aria-pressed={on.includes(k)} onClick={() => flip(k)}>{v}</button>)}
      </div>

      <Alert>{err}</Alert>
      <h2 className="section">{shown.length} {shown.length === 1 ? "place" : "places"} to rescue food from</h2>
      {rows === null ? <p className="muted">Loading…</p> : !shown.length ? (
        <div className="empty"><div className="empty-emoji">🍽️</div><h3>No deals match</h3><p className="muted">Clear a filter or widen the search radius. New food appears as kitchens close for the day.</p>
          <button className="btn ghost" onClick={() => { setQ(""); setCat("all"); setOn([]); setRadius(100); }}>Reset filters</button></div>
      ) : <div className="deals">{shown.map((l) => <DealCard key={l.id} l={l} saved={saved.includes(l.id)} onSave={toggleSave} onOpen={onOpen} />)}</div>}
    </>
  );
}

/* ---------- orders ---------- */
function Tracker({ done }) {
  const steps = ["Reserved", "At the counter", "Collected"];
  return (
    <ol className="tracker" aria-label="Order progress">
      {steps.map((s, i) => <li key={s} className={i < done ? "done" : i === done ? "now" : ""}><span>{i < done ? "✓" : i + 1}</span>{s}</li>)}
    </ol>
  );
}

function OrderCard({ o, stars, reload, goto, flash, onCancel }) {
  const [busy, setBusy] = useState(false);
  const completed = o.status === "completed";
  const rate = async (n) => {
    setBusy(true);
    try { await api(`/listings/${o.id}/review`, { method: "POST", body: { stars: n } }); flash("Thanks for rating!"); reload(); } catch (e) { flash(e.message, "err"); } finally { setBusy(false); }
  };
  return (
    <article className="order">
      <div className="order-img"><FoodImage l={o} /></div>
      <div className="order-main">
        <div className="deal-top"><h3>{o.item_name}</h3><span className="order-price">{rupees(o.price)}</span></div>
        <p className="meta">{o.vendor} · Order #{o.id}</p>
        {!completed && <Tracker done={1} />}
        {!completed && <QrCard item={o} />}
        {completed && (
          <div className="after">
            {stars[o.id] ? <p className="muted">You rated this {"★".repeat(stars[o.id])}{"☆".repeat(5 - stars[o.id])}</p> : <div><span className="muted">How was {o.vendor}?</span> {!busy && <StarPicker onPick={rate} />}</div>}
            {!o.reported && <OutcomeButtons id={o.id} onDone={reload} />}
          </div>
        )}
        <div className="order-actions">
          {!completed && <a className="btn ghost small" href={directions(o)} target="_blank" rel="noreferrer">Get directions</a>}
          {!completed && <button className="btn danger small" onClick={() => onCancel(o)}>Cancel order</button>}
          <button className="btn ghost small" onClick={() => goto("help", { listing_id: o.id })}>Need help?</button>
        </div>
      </div>
    </article>
  );
}

function Orders({ orders, stars, reload, goto, flash, onCancel }) {
  if (orders === null) return <p className="muted">Loading…</p>;
  if (!orders.length) return <div className="empty"><div className="empty-emoji">🧾</div><h3>No orders yet</h3><p className="muted">Reserve something from Explore and it will show up here with its pickup code.</p><button className="btn" onClick={() => goto("home")}>Find food</button></div>;
  const active = orders.filter((o) => o.status !== "completed"), past = orders.filter((o) => o.status === "completed");
  return (
    <>
      {!!active.length && <><h2 className="section">Ready for pickup</h2><div className="orders">{active.map((o) => <OrderCard key={o.id} o={o} stars={stars} reload={reload} goto={goto} flash={flash} onCancel={onCancel} />)}</div></>}
      {!!past.length && <><h2 className="section">Past orders</h2><div className="orders">{past.map((o) => <OrderCard key={o.id} o={o} stars={stars} reload={reload} goto={goto} flash={flash} onCancel={onCancel} />)}</div></>}
    </>
  );
}

/* ---------- container ---------- */
export default function Citizen({ user, view, goto }) {
  const [radius, setRadius] = useState(30);
  const [rows, setRows] = useState(null); const [orders, setOrders] = useState(null); const [stars, setStars] = useState({});
  const [err, setErr] = useState(""); const [msg, setMsg] = useState(null); const [open, setOpen] = useState(null); const [busy, setBusy] = useState(false);
  const [saved, toggleSave] = useSaved();
  const reload = useCallback(() => {
    api(`/market?radius_km=${radius}`).then((r) => { setRows(r); setErr(""); }).catch((e) => setErr(e.message));
    api("/my/items").then(setOrders).catch(() => setOrders([]));
    api("/my/reviews").then(setStars).catch(() => {});
  }, [radius]);
  useEffect(() => { reload(); }, [reload]);
  const flash = (text, kind = "ok") => { setMsg({ text, kind }); setTimeout(() => setMsg(null), 6000); };
  const reserve = async (l) => {
    setBusy(true);
    try { await api(`/listings/${l.id}/reserve`, { method: "POST" }); setOpen(null); flash(`Reserved “${l.item_name}”. Show your code at ${l.vendor} and pay ${rupees(l.price)} on pickup.`); goto("orders"); }
    catch (e) { setOpen(null); flash(e.message, "err"); } finally { setBusy(false); reload(); }
  };
  const cancel = async (o) => {
    if (!window.confirm(`Cancel your order for ${o.item_name}?`)) return;
    try { await api(`/listings/${o.id}/cancel`, { method: "POST" }); flash("Order cancelled. The item is back on the market."); } catch (e) { flash(e.message, "err"); }
    reload();
  };
  const savedRows = (rows || []).filter((l) => saved.includes(l.id));
  return (
    <div className="citizen">
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      {view === "home" && <Explore user={user} rows={rows} radius={radius} setRadius={setRadius} saved={saved} toggleSave={toggleSave} onOpen={setOpen} err={err} />}
      {view === "orders" && <><h1 className="page-title">Your orders</h1><Orders orders={orders} stars={stars} reload={reload} goto={goto} flash={flash} onCancel={cancel} /></>}
      {view === "saved" && (
        <>
          <h1 className="page-title">Saved for later</h1>
          {!savedRows.length ? <div className="empty"><div className="empty-emoji">♡</div><h3>Nothing saved</h3><p className="muted">Tap the heart on any food card to keep it here. Saved items disappear once they are sold.</p><button className="btn" onClick={() => goto("home")}>Browse food</button></div>
            : <div className="deals">{savedRows.map((l) => <DealCard key={l.id} l={l} saved onSave={toggleSave} onOpen={setOpen} />)}</div>}
        </>
      )}
      {open && <Sheet l={open} onClose={() => setOpen(null)} onReserve={reserve} busy={busy} />}
    </div>
  );
}
