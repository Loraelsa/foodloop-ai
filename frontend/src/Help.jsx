import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { Alert } from "./ui.jsx";

const TOPICS = [
  ["food_quality", "🤢", "Food quality", "It smelled, tasted or looked off"],
  ["wrong_item", "📦", "Wrong or missing item", "Not what the app showed"],
  ["vendor_issue", "🏪", "Vendor issue", "Closed, rude or refused handover"],
  ["pickup_problem", "📍", "Pickup problem", "Code or QR not accepted"],
  ["payment", "💳", "Price or payment", "Charged more than listed"],
  ["account", "👤", "Account", "Login or approval trouble"],
  ["app_bug", "🐞", "App problem", "Something is broken"],
  ["other", "💬", "Something else", "Anything not listed"],
];
const TOPIC_NAME = Object.fromEntries(TOPICS.map(([k, , n]) => [k, n]));

const FAQ = {
  citizen: [
    ["How do I pay?", "You pay the vendor when you pick up. Nothing is charged in the app."],
    ["How do I collect my order?", "Open Orders and show the QR code or 8-character code at the counter. The vendor confirms it and your order is marked collected."],
    ["Can I cancel?", "Yes, any time before pickup from Orders. The item goes back on the market and your old code stops working."],
    ["Why is the food so cheap?", "It is surplus that kitchens would otherwise throw away. A model estimates how many safe hours are left, and the discount grows as that time shrinks."],
    ["I feel unwell after eating.", "Stop eating, drink water and see a doctor if you feel worse. Then raise a Food quality complaint with the order so we can pull the listing."],
  ],
  vendor: [
    ["Why can't I list food?", "New vendor accounts need admin approval first. You can still run the freshness check meanwhile."],
    ["How is the verdict decided?", "A model estimates remaining safe hours. 4 h or more is sold at a discount, 1 to 4 h is donated, under 1 h goes to compost."],
    ["A buyer's code isn't accepted.", "Check the code has no 0/O or 1/I mix-ups. If it still fails, raise a Pickup problem complaint."],
  ],
  ngo: [
    ["Why don't I see donations?", "You see donations within 50 km once your account is approved. New ones appear when vendors list food too close to expiry to sell."],
    ["How is my route planned?", "The route solver orders your stops to cut distance, using real roads when the road service is reachable."],
  ],
  admin: [["Where are complaints?", "They are listed below the approvals queue on the Admin page."]],
};

function Status({ s }) { return <span className={`ticket-status ${s}`}>{s.replace("_", " ")}</span>; }

export default function Help({ user, prefill }) {
  const [topic, setTopic] = useState(prefill?.topic || ""); const [listingId, setListingId] = useState(prefill?.listing_id || "");
  const [message, setMessage] = useState(""); const [orders, setOrders] = useState([]); const [tickets, setTickets] = useState([]);
  const [err, setErr] = useState(""); const [ok, setOk] = useState(""); const [busy, setBusy] = useState(false); const [openFaq, setOpenFaq] = useState(-1);
  const load = useCallback(() => {
    api("/complaints/mine").then(setTickets).catch(() => {});
    (user.role === "vendor" ? api("/listings/mine") : ["citizen", "ngo"].includes(user.role) ? api("/my/items") : Promise.resolve([])).then(setOrders).catch(() => {});
  }, [user.role]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (prefill?.listing_id) { setListingId(prefill.listing_id); setTopic((t) => t || "food_quality"); } }, [prefill]);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setOk(""); setBusy(true);
    try {
      await api("/complaints", { method: "POST", body: { topic, message, listing_id: listingId ? +listingId : null } });
      setOk("Complaint sent. We will reply here and send you an alert."); setMessage(""); setTopic(""); setListingId(""); load();
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  if (user.role === "admin") return <div><h1 className="page-title">Help</h1>{FAQ.admin.map(([q, a]) => <div className="card" key={q}><h3>{q}</h3><p>{a}</p></div>)}</div>;
  return (
    <div className="help">
      <h1 className="page-title">How can we help?</h1>
      <p className="muted">Pick what went wrong, tell us what happened, and an admin will reply here.</p>
      <div className="topics" role="group" aria-label="Complaint topics">
        {TOPICS.map(([k, e, n, d]) => (
          <button key={k} type="button" className={`topic ${topic === k ? "active" : ""}`} aria-pressed={topic === k} onClick={() => { setTopic(k); document.getElementById("complaint-form")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>
            <span className="topic-ico">{e}</span><b>{n}</b><small>{d}</small>
          </button>
        ))}
      </div>

      <div className="grid cols-2" style={{ marginTop: "1.2rem" }}>
        <form className="card" id="complaint-form" onSubmit={submit}>
          <h2>Raise a complaint</h2>
          <Alert>{err}</Alert><Alert kind="ok">{ok}</Alert>
          <label>What is it about?
            <select required value={topic} onChange={(e) => setTopic(e.target.value)}><option value="" disabled>Choose a topic</option>{TOPICS.map(([k, , n]) => <option key={k} value={k}>{n}</option>)}</select>
          </label>
          {!!orders.length && (
            <label>Which order? (optional)
              <select value={listingId} onChange={(e) => setListingId(e.target.value)}><option value="">Not about one order</option>
                {orders.map((o) => <option key={o.id} value={o.id}>#{o.id} · {o.item_name}</option>)}</select>
            </label>
          )}
          <label>Tell us what happened
            <textarea required minLength={10} maxLength={1000} rows={5} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="For example: the rice smelled sour when I opened the box at home." />
          </label>
          <button className="btn" disabled={busy || !topic}>{busy ? "Sending…" : "Send complaint"}</button>
        </form>

        <div className="grid">
          <div className="card">
            <h2>Your complaints</h2>
            {!tickets.length ? <p className="muted">Nothing raised yet. If something goes wrong, it will appear here with its status.</p> : tickets.map((t) => (
              <div key={t.id} className="ticket">
                <div className="ticket-top"><b>#{t.id} · {TOPIC_NAME[t.topic]}</b><Status s={t.status} /></div>
                {t.item_name && <p className="muted">About order #{t.listing_id}, {t.item_name}</p>}
                <p>{t.message}</p>
                {t.response && <div className="reply"><b>Reply from FoodLoop</b><p>{t.response}</p></div>}
              </div>))}
          </div>
          <div className="card">
            <h2>Quick answers</h2>
            {(FAQ[user.role] || []).map(([q, a], i) => (
              <div key={q} className="faq">
                <button type="button" aria-expanded={openFaq === i} onClick={() => setOpenFaq(openFaq === i ? -1 : i)}>{q}<span aria-hidden="true">{openFaq === i ? "−" : "+"}</span></button>
                {openFaq === i && <p>{a}</p>}
              </div>))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- admin inbox ---------- */
export function AdminComplaints() {
  const [rows, setRows] = useState([]); const [text, setText] = useState({}); const [err, setErr] = useState("");
  const load = useCallback(() => { api("/admin/complaints").then(setRows).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { load(); }, [load]);
  const send = async (id, status) => {
    setErr("");
    try { await api(`/admin/complaints/${id}/reply`, { method: "POST", body: { status, response: text[id] || "" } }); setText((t) => ({ ...t, [id]: "" })); load(); }
    catch (e) { setErr(e.message); }
  };
  const open = rows.filter((r) => r.status !== "resolved").length;
  return (
    <div className="card" style={{ gridColumn: "1 / -1" }}>
      <h2>Complaints {open ? <span className="badge">{open} open</span> : null}</h2><Alert>{err}</Alert>
      {!rows.length ? <p className="muted">No complaints yet.</p> : rows.map((t) => (
        <div key={t.id} className="ticket">
          <div className="ticket-top"><b>#{t.id} · {TOPIC_NAME[t.topic]}</b><Status s={t.status} /></div>
          <p className="muted">{t.user.name} ({t.user.role}) · {t.user.email}{t.item_name ? ` · order #${t.listing_id}, ${t.item_name}` : ""}</p>
          <p>{t.message}</p>
          {t.response && <div className="reply"><b>Your reply</b><p>{t.response}</p></div>}
          {t.status !== "resolved" && (
            <>
              <label>Reply<textarea rows={2} value={text[t.id] || ""} onChange={(e) => setText((x) => ({ ...x, [t.id]: e.target.value }))} placeholder="Write a reply to the user" /></label>
              <button className="btn ghost small" disabled={(text[t.id] || "").length < 3} onClick={() => send(t.id, "in_review")}>Mark in review</button>{" "}
              <button className="btn small" disabled={(text[t.id] || "").length < 3} onClick={() => send(t.id, "resolved")}>Resolve</button>
            </>
          )}
        </div>))}
    </div>
  );
}
