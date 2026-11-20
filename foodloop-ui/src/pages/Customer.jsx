import React, { useMemo, useState } from 'react'
import { Routes, Route, Link, useNavigate, useParams, NavLink } from 'react-router-dom'
import { MapPin, Search, ShoppingBag, ChevronDown, Clock, Star, Leaf, Minus, Plus, Receipt, LogOut, User, ArrowLeft, Sprout, BadgeCheck, Navigation } from 'lucide-react'
import { useStore } from '../store.jsx'
import { Logo, Tile, useNow, fmtLeft, Drawer, Empty, StatusBadge } from '../components/ui.jsx'
import { CATEGORIES, haversine, inr, impactOf, ROAD_FACTOR } from '../engine.js'
import { LOCALITIES } from '../data.js'

const HOME = LOCALITIES['Koramangala']
const km = (v) => (haversine(HOME, v) * ROAD_FACTOR).toFixed(1)

function useSellable() {
  const { listings, vendors } = useStore()
  const now = useNow()
  return useMemo(() => listings
    .filter((l) => l.status === 'live' && l.decision === 'sell' && l.qty > 0 && l.expiresAt > now)
    .map((l) => ({ ...l, vendor: vendors.find((v) => v.id === l.vendorId) }))
    .filter((l) => l.vendor && l.vendor.status === 'approved'), [listings, vendors, now])
}

/* ---------------------------- top navigation ---------------------------- */
function Nav({ q, setQ, onCart }) {
  const { session, cart, logout } = useStore()
  const go = useNavigate()
  const [open, setOpen] = useState(false)
  const count = cart.reduce((s, c) => s + c.qty, 0)
  return (
    <header className="topnav">
      <div className="wrap">
        <Logo to="/shop" />
        <div className="searchbar">
          <div className="loc"><MapPin size={18} color="#E23744" /><span>Koramangala, Bengaluru</span><ChevronDown size={16} /></div>
          <Search size={18} style={{ marginLeft: 14 }} />
          <input value={q} onChange={(e) => { setQ(e.target.value); go('/shop') }} placeholder="Search for a restaurant, dish or cuisine" aria-label="Search" />
        </div>
        <div className="row right">
          <button className="iconbtn cartbtn" onClick={onCart} aria-label={`Cart, ${count} items`}><ShoppingBag size={19} />{count > 0 && <span className="count">{count}</span>}</button>
          <div className="menu">
            <button className="avatar" style={{ border: 0 }} onClick={() => setOpen(!open)} aria-label="Account menu">{session.name[0]}</button>
            {open && (<div className="pop" onMouseLeave={() => setOpen(false)}>
              <div style={{ padding: '10px 12px' }}><div className="b">{session.name}</div><div className="xs muted">Customer</div></div>
              <Link to="/shop/orders" onClick={() => setOpen(false)}><Receipt size={17} />My orders</Link>
              <button onClick={() => { logout(); go('/') }}><LogOut size={17} />Sign out</button>
            </div>)}
          </div>
        </div>
      </div>
    </header>
  )
}

/* -------------------------------- home --------------------------------- */
function Home({ q }) {
  const { orders } = useStore()
  const items = useSellable()
  const [cat, setCat] = useState(null)
  const [sort, setSort] = useState('ending')
  const [veg, setVeg] = useState(false)

  const rests = useMemo(() => {
    const map = new Map()
    for (const l of items) {
      if (cat && l.category !== cat) continue
      if (veg && !l.vendor.veg) continue
      const ql = q.trim().toLowerCase()
      if (ql && !(l.vendor.name + ' ' + l.vendor.cuisines + ' ' + l.item).toLowerCase().includes(ql)) continue
      const e = map.get(l.vendorId) || { vendor: l.vendor, items: [] }
      e.items.push(l); map.set(l.vendorId, e)
    }
    const arr = [...map.values()].map((e) => ({
      ...e,
      maxOff: Math.max(...e.items.map((i) => i.discount)),
      soon: Math.min(...e.items.map((i) => i.expiresAt)),
      dist: +km(e.vendor),
      from: Math.min(...e.items.map((i) => i.price)),
    }))
    arr.sort({ ending: (a, b) => a.soon - b.soon, discount: (a, b) => b.maxOff - a.maxOff, near: (a, b) => a.dist - b.dist, rating: (a, b) => b.vendor.rating - a.vendor.rating }[sort])
    return arr
  }, [items, cat, sort, veg, q])

  const mine = orders.reduce((s, o) => s + o.kg, 0)
  const imp = impactOf(mine)

  return (
    <div className="wrap" style={{ paddingBottom: 60 }}>
      <section className="hero">
        <div className="art" aria-hidden>🍲</div><div className="art2" aria-hidden>🥘</div>
        <h1>Great food. Last-minute prices.</h1>
        <p>Restaurants near you list surplus the moment it is ready to go. Pick it up before it expires and keep good food out of the bin.</p>
        <div className="stats">
          <div><b>{items.length}</b><span>items available now</span></div>
          <div><b>Up to {Math.max(0, ...items.map((i) => i.discount))}% off</b><span>on today's surplus</span></div>
          <div><b>Pay on pickup</b><span>no online payment</span></div>
        </div>
      </section>

      {orders.length > 0 && (
        <div className="impactstrip">
          <span className="ic"><Leaf size={22} /></span>
          <div><div className="b">You've rescued {mine.toFixed(1)} kg of food</div><div className="sm muted">That is about {imp.meals} meals and {Math.max(imp.co2, 0)} kg CO₂e kept out of landfill.</div></div>
        </div>
      )}

      <div className="cats" role="group" aria-label="Food categories">
        {Object.entries(CATEGORIES).filter(([k]) => k !== 'packaged' || true).map(([k, c]) => (
          <button key={k} className={'cat' + (cat === k ? ' on' : '')} onClick={() => setCat(cat === k ? null : k)} aria-pressed={cat === k}>
            <span className="ic" style={{ background: `linear-gradient(145deg, ${c.tint[0]}, ${c.tint[1]})` }}>{c.emoji}</span><span>{c.label}</span>
          </button>
        ))}
      </div>

      <div className="sect-h">
        <h2>{cat ? CATEGORIES[cat].label : 'Surplus near you'} <span className="muted b" style={{ fontSize: 15 }}>({rests.length})</span></h2>
      </div>
      <div className="filters" style={{ marginBottom: 20 }}>
        {[['ending', 'Ending soon'], ['discount', 'Biggest discount'], ['near', 'Nearest'], ['rating', 'Top rated']].map(([k, t]) => (
          <button key={k} className={'chip' + (sort === k ? ' on' : '')} onClick={() => setSort(k)}>{t}</button>
        ))}
        <button className={'chip' + (veg ? ' on' : '')} onClick={() => setVeg(!veg)}><span className="vegmark" />Pure veg</button>
        {(cat || veg || q) && <button className="chip" style={{ borderStyle: 'dashed' }} onClick={() => { setCat(null); setVeg(false) }}>Clear filters</button>}
      </div>

      {rests.length === 0 ? <Empty emoji="🔎" title="Nothing matches right now">Try another category, or check back soon. New surplus is listed through the day.</Empty> : (
        <div className="grid">
          {rests.map((r) => <RestCard key={r.vendor.id} r={r} />)}
        </div>
      )}
    </div>
  )
}

function RestCard({ r }) {
  const now = useNow()
  const top = r.items.reduce((a, b) => (b.discount > a.discount ? b : a))
  return (
    <Link to={`/shop/r/${r.vendor.id}`} className="rcard">
      <Tile cat={top.category} className="img">
        <span className="big">{CATEGORIES[top.category].emoji}</span>
        <span className="timer"><Clock size={12} />{fmtLeft(r.soon, now)}</span>
        <span className="offer">{r.maxOff}% OFF<small>on {r.items.length} item{r.items.length > 1 ? 's' : ''}</small></span>
      </Tile>
      <div className="meta">
        <div className="l2"><h3>{r.vendor.name}</h3><span className="rating">{r.vendor.rating}<Star size={11} fill="#fff" /></span></div>
        <div className="l2"><p>{r.vendor.cuisines}</p><span className="sm muted num">{r.dist} km</span></div>
        <p>{r.vendor.locality} · from <b style={{ color: 'var(--ink)' }}>{inr(r.from)}</b></p>
      </div>
    </Link>
  )
}

/* --------------------------- restaurant detail -------------------------- */
function Vendor({ onCart }) {
  const { vid } = useParams()
  const { vendors, cart, cartAdd, cartDec } = useStore()
  const items = useSellable().filter((l) => l.vendorId === vid)
  const v = vendors.find((x) => x.id === vid)
  const now = useNow()
  if (!v) return <div className="wrap"><Empty title="Restaurant not found" /></div>
  const qty = (id) => cart.find((c) => c.listingId === id)?.qty || 0
  const cartVendorItems = cart.filter((c) => items.some((i) => i.id === c.listingId))
  const total = cartVendorItems.reduce((s, c) => s + c.qty * (items.find((i) => i.id === c.listingId)?.price || 0), 0)

  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="rhead">
        <Link to="/shop" className="row sm muted b" style={{ marginBottom: 12 }}><ArrowLeft size={15} />All restaurants</Link>
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div>
            <h1>{v.name}</h1>
            <div className="muted" style={{ marginTop: 4 }}>{v.cuisines}</div>
            <div className="muted sm row" style={{ marginTop: 4 }}><MapPin size={14} />{v.locality}, Bengaluru · {km(v)} km away</div>
          </div>
          <div className="col" style={{ alignItems: 'flex-end', gap: 6 }}>
            <span className="rating" style={{ fontSize: 16, padding: '5px 10px' }}>{v.rating}<Star size={13} fill="#fff" /></span>
            <span className="badge green"><BadgeCheck size={13} />FoodLoop verified</span>
          </div>
        </div>
      </div>

      <div className="two l17" style={{ marginTop: 8 }}>
        <div>
          <h2 style={{ fontSize: 21, margin: '22px 0 0' }}>Today's surplus <span className="muted" style={{ fontWeight: 500, fontSize: 15 }}>({items.length})</span></h2>
          {items.length === 0 && <Empty emoji="🍽️" title="Everything here has been claimed">New items appear as the kitchen lists them.</Empty>}
          {items.map((l) => (
            <div className="menurow" key={l.id}>
              <div className="grow">
                <span className={'vegmark' + (/chicken|mutton|fish|egg/i.test(l.item) ? ' non' : '')} />
                <h3 style={{ fontSize: 18, margin: '6px 0 4px' }}>{l.item}</h3>
                <div className="row" style={{ gap: 8 }}><b className="num" style={{ fontSize: 16 }}>{inr(l.price)}</b><s className="muted num">{inr(l.mrp)}</s><span className="badge green">{l.discount}% off</span></div>
                <div className="sm muted" style={{ marginTop: 8 }}>{l.qty} {l.unit} left · {CATEGORIES[l.category].label}</div>
                <div className="row sm" style={{ marginTop: 6, color: l.expiresAt - now < 3 * 3600e3 ? 'var(--red-d)' : 'var(--ink3)', fontWeight: 600 }}><Clock size={14} />{fmtLeft(l.expiresAt, now)}</div>
              </div>
              <Tile cat={l.category} className="t">
                <span>{CATEGORIES[l.category].emoji}</span>
                {qty(l.id) === 0
                  ? <button className="add" onClick={() => cartAdd(l.id, l.qty)}>ADD</button>
                  : <div className="stepper"><button onClick={() => cartDec(l.id)} aria-label="Remove one"><Minus size={15} /></button><span className="num">{qty(l.id)}</span><button onClick={() => cartAdd(l.id, l.qty)} aria-label="Add one"><Plus size={15} /></button></div>}
              </Tile>
            </div>
          ))}
        </div>
        <aside>
          <div className="card pad sticky-cart" style={{ marginTop: 22 }}>
            <h3>Pickup details</h3>
            <div className="col" style={{ gap: 14, marginTop: 14 }}>
              <div className="row" style={{ alignItems: 'flex-start' }}><Navigation size={18} color="#E23744" /><div><div className="b">{v.name}</div><div className="sm muted">{v.locality}, Bengaluru</div></div></div>
              <div className="row" style={{ alignItems: 'flex-start' }}><Sprout size={18} color="#1BA672" /><div className="sm muted">Each item you rescue keeps about 2.5 kg CO₂e per kg of food out of landfill.</div></div>
              <button className="btn primary block" disabled={!cartVendorItems.length} onClick={onCart}>{cartVendorItems.length ? `View cart · ${inr(total)}` : 'Add items to continue'}</button>
              <div className="hint">Pay at the counter when you collect. Bring your pickup code.</div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}

/* ------------------------------ cart drawer ----------------------------- */
function Cart({ open, onClose }) {
  const { cart, listings, vendors, cartAdd, cartDec, placeOrder, toast, uid } = useStore()
  const go = useNavigate()
  const lines = cart.map((c) => ({ ...c, l: listings.find((l) => l.id === c.listingId) })).filter((x) => x.l)
  const total = lines.reduce((s, x) => s + x.qty * x.l.price, 0)
  const saved = lines.reduce((s, x) => s + x.qty * (x.l.mrp - x.l.price), 0)

  const order = () => {
    const byV = {}
    lines.forEach((x) => { (byV[x.l.vendorId] ||= []).push(x) })
    const orders = Object.entries(byV).map(([vid, xs]) => ({
      id: uid('o'), vendorId: vid, status: 'placed', at: Date.now(),
      code: String(Math.floor(1000 + Math.random() * 9000)),
      items: xs.map((x) => ({ listingId: x.listingId, item: x.l.item, qty: x.qty, price: x.l.price, category: x.l.category })),
      total: xs.reduce((s, x) => s + x.qty * x.l.price, 0),
      kg: +xs.reduce((s, x) => s + x.qty * x.l.kgPerUnit, 0).toFixed(2),
    }))
    placeOrder(cart, orders)
    onClose(); toast('Order placed. Pay at the counter on pickup.'); go('/shop/orders')
  }

  return (
    <Drawer open={open} onClose={onClose} title="Your cart"
      footer={lines.length > 0 && (<div className="col" style={{ gap: 12 }}>
        <div className="row between"><span className="muted">Total (pay on pickup)</span><b className="num" style={{ fontSize: 20 }}>{inr(total)}</b></div>
        <button className="btn primary lg block" onClick={order}>Place order</button>
      </div>)}>
      {lines.length === 0 ? <Empty emoji="🛒" title="Your cart is empty">Add surplus items from a restaurant to get started.</Empty> : (<>
        {lines.map((x) => (
          <div key={x.listingId} className="row" style={{ padding: '14px 0', borderBottom: '1px solid var(--line2)', alignItems: 'flex-start' }}>
            <Tile cat={x.l.category} className="" style={{ width: 52, height: 52, borderRadius: 12, display: 'grid', placeItems: 'center', fontSize: 26 }} />
            <div className="grow"><div className="b">{x.l.item}</div><div className="xs muted">{vendors.find((v) => v.id === x.l.vendorId)?.name}</div><div className="num sm" style={{ marginTop: 4 }}>{inr(x.l.price)}</div></div>
            <div className="seg" style={{ alignItems: 'center' }}>
              <button onClick={() => cartDec(x.listingId)} aria-label="Remove one"><Minus size={14} /></button>
              <span className="b num" style={{ padding: '7px 6px' }}>{x.qty}</span>
              <button onClick={() => cartAdd(x.listingId, x.l.qty)} aria-label="Add one"><Plus size={14} /></button>
            </div>
          </div>
        ))}
        <div className="note info" style={{ marginTop: 16 }}><Leaf size={16} style={{ flex: 'none', marginTop: 2 }} />You're saving {inr(saved)} compared with the regular price.</div>
      </>)}
    </Drawer>
  )
}

/* -------------------------------- orders -------------------------------- */
function Orders() {
  const { orders, vendors } = useStore()
  return (
    <div className="wrap" style={{ paddingBottom: 60, maxWidth: 820 }}>
      <div className="sect-h"><h2>My orders</h2></div>
      {orders.length === 0 ? <div className="card"><Empty emoji="🧾" title="No orders yet">Orders you place will show up here with a pickup code.<div style={{ marginTop: 14 }}><Link className="btn primary" to="/shop">Browse surplus</Link></div></Empty></div> : (
        <div className="col" style={{ gap: 16 }}>
          {orders.map((o) => {
            const v = vendors.find((x) => x.id === o.vendorId)
            return (
              <div className="card pad" key={o.id}>
                <div className="row between" style={{ alignItems: 'flex-start' }}>
                  <div><h3>{v?.name}</h3><div className="sm muted">{v?.locality} · {new Date(o.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</div></div>
                  <StatusBadge s={o.status} />
                </div>
                <div style={{ margin: '14px 0', borderTop: '1px dashed var(--line)', paddingTop: 12 }}>
                  {o.items.map((i) => <div key={i.listingId} className="row between sm" style={{ padding: '3px 0' }}><span>{i.qty} × {i.item}</span><span className="num">{inr(i.qty * i.price)}</span></div>)}
                </div>
                <div className="row between">
                  <div className="row"><span className="muted sm">Pickup code</span><span className="badge" style={{ fontSize: 15, letterSpacing: 2, height: 30, padding: '0 12px' }}>{o.code}</span></div>
                  <b className="num">{inr(o.total)} <span className="muted sm" style={{ fontWeight: 500 }}>pay on pickup</span></b>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Customer() {
  const [q, setQ] = useState('')
  const [cartOpen, setCartOpen] = useState(false)
  return (
    <>
      <Nav q={q} setQ={setQ} onCart={() => setCartOpen(true)} />
      <Routes>
        <Route index element={<Home q={q} />} />
        <Route path="r/:vid" element={<Vendor onCart={() => setCartOpen(true)} />} />
        <Route path="orders" element={<Orders />} />
      </Routes>
      <Cart open={cartOpen} onClose={() => setCartOpen(false)} />
    </>
  )
}
