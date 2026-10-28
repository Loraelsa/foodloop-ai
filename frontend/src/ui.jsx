import { useEffect, useState } from "react";
import { api } from "./api.js";

export const CATEGORIES = { cooked_meal: "Cooked meal", bakery: "Bakery", dairy: "Dairy", produce: "Fruit & veg", packaged: "Packaged", dessert: "Dessert" };
export const CAT_EMOJI = { cooked_meal: "🍛", bakery: "🍞", dairy: "🥛", produce: "🥗", packaged: "📦", dessert: "🍰" };

export function Alert({ kind = "err", children }) {
  return children ? <div className={`alert ${kind}`} role={kind === "err" ? "alert" : "status"}>{children}</div> : null;
}

/* Pictures: a vendor's own photo when there is one, otherwise an illustrated tile picked from the item name. */
const KEYWORDS = [
  [/croissant/i, "🥐"], [/puri|roti|paratha|naan|chapati|kulcha/i, "🫓"], [/samosa|momo|dumpling|kachori/i, "🥟"],
  [/pizza/i, "🍕"], [/burger/i, "🍔"], [/sandwich|sub\b/i, "🥪"], [/noodle|pasta|chowmein|maggi/i, "🍜"], [/idli|dosa|uttapam|pancake/i, "🥞"],
  [/salad|fruit|veg(etable)?s?\b.*(box|pack)/i, "🥗"], [/curd|yogh?urt|milk|lassi|buttermilk|dahi/i, "🥛"],
  [/cake|pastry|brownie|donut|halwa|kheer|sweet|gulab|ladoo|dessert/i, "🍰"], [/bread|loaf|pav|bun|toast|bagel/i, "🍞"],
  [/paneer|curry|dal|rajma|chole|sabzi|masala|sambar|kadhai/i, "🍲"], [/biryani|pulao|rice|khichdi|chawal/i, "🍛"],
];
export const foodEmoji = (l) => (KEYWORDS.find(([re]) => re.test(l.item_name)) || [null, CAT_EMOJI[l.category] || "🍽️"])[1];

export function FoodImage({ l, big = false }) {
  if (l.has_photo) return <img className={`food-photo ${big ? "big" : ""}`} loading="lazy" src={`/api/listings/${l.id}/photo`} alt={l.item_name} />;
  return (
    <div className={`food-art tile ${l.category} ${big ? "big" : ""}`} role="img" aria-label={l.item_name}>
      <span className="plate" aria-hidden="true">{foodEmoji(l)}</span>
    </div>
  );
}

export function fmtLeft(h) {
  if (h < 1) return `${Math.max(Math.round(h * 60), 1)} min`;
  if (h >= 72) return "3+ days";
  if (h >= 48) return "2 days";
  return `${h < 10 ? h.toFixed(1).replace(/\.0$/, "") : Math.round(h)} h`;
}

export function RatingBadge({ rating, reviews }) {
  return rating ? <span className="rate" title={`${reviews} rating${reviews === 1 ? "" : "s"}`}>{rating.toFixed(1)} ★</span> : <span className="rate new">New</span>;
}

export function StarPicker({ onPick, label = "Rate this order" }) {
  const [hover, setHover] = useState(0);
  return (
    <div className="stars" role="group" aria-label={label} onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" className={n <= hover ? "on" : ""} onMouseEnter={() => setHover(n)} onFocus={() => setHover(n)} onBlur={() => setHover(0)}
          onClick={() => onPick(n)} aria-label={`${n} star${n > 1 ? "s" : ""}`}>★</button>
      ))}
    </div>
  );
}

export function QrCard({ item }) {
  const [q, setQ] = useState(null);
  useEffect(() => { api(`/listings/${item.id}/qr`).then(setQ).catch(() => {}); }, [item.id]);
  if (!q) return null;
  return (
    <div className="qr">
      <div className="qr-img" dangerouslySetInnerHTML={{ __html: q.svg }} aria-label={`QR code ${q.code}`} />
      <div><div className="muted">Show this to the vendor</div><div className="code">{q.code}</div></div>
    </div>
  );
}

export function OutcomeButtons({ id, onDone }) {
  const [msg, setMsg] = useState("");
  const send = async (verdict) => {
    try { await api(`/listings/${id}/outcome`, { method: "POST", body: { verdict } }); setMsg("Thanks, this helps the model learn."); onDone?.(); }
    catch (e) { setMsg(e.message); }
  };
  if (msg) return <span className="muted">{msg}</span>;
  return (
    <span className="outcome">
      <span className="muted">Was the food fine?</span>{" "}
      <button className="btn small ghost" onClick={() => send("fine")}>Yes, fine</button>{" "}
      <button className="btn small danger" onClick={() => send("spoiled")}>It was spoiled</button>
    </span>
  );
}
