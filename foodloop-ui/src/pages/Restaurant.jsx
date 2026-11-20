import React, { useEffect, useMemo, useState } from 'react'
import { apiDecide } from '../api.js'
import { Routes, Route, useNavigate, Link } from 'react-router-dom'
import { LayoutDashboard, PlusCircle, ListChecks, Receipt, Store, Leaf, IndianRupee, Package, Sprout, Trash2, Sparkles, Clock, Thermometer } from 'lucide-react'
import { useStore } from '../store.jsx'
import { DashShell, PageHead, Kpi, Tile, DecisionBadge, StatusBadge, Empty, StackedBars, Donut, DECISION, useNow, fmtLeft } from '../components/ui.jsx'
import { CATEGORIES, STORAGE, decide, inr, impactOf, THRESHOLDS } from '../engine.js'

const NAV = [
  { to: '/restaurant', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/restaurant/add', label: 'Add surplus', icon: PlusCircle },
  { to: '/restaurant/listings', label: 'My listings', icon: ListChecks },
  { to: '/restaurant/orders', label: 'Pickups', icon: Receipt },
]

function useMine() {
  const { session, listings, orders, vendors } = useStore()
  const vendor = vendors.find((v) => v.id === session.id)
  return {
    vendor,
    listings: listings.filter((l) => l.vendorId === session.id),
    orders: orders.filter((o) => o.vendorId === session.id),
  }
}

function Dashboard() {
  const { history, pickups } = useStore()
  const { vendor, listings, orders } = useMine()
  const now = useNow()
  const live = listings.filter((l) => l.status === 'live' && l.expiresAt > now)
  const soldKg = orders.reduce((s, o) => s + o.kg, 0)
  const donatedKg = listings.filter((l) => l.status === 'claimed').reduce((s, l) => s + l.qty * l.kgPerUnit, 0)
  const imp = impactOf(soldKg + donatedKg)
  const revenue = orders.reduce((s, o) => s + o.total, 0)
  const mix = ['sell', 'donate', 'compost'].map((d) => ({ key: d, value: listings.filter((l) => l.decision === d).length, color: DECISION[d].color }))

  return (<>
    <PageHead title={`Good day, ${vendor.name}`} sub="Here is how today's surplus is moving.">
      <Link to="/restaurant/add" className="btn primary"><PlusCircle size={18} />Add surplus</Link>
    </PageHead>
    {vendor.status !== 'approved' && <div className="note" style={{ marginBottom: 18 }}>Your account is waiting for admin approval. You can list items, but customers will not see them yet.</div>}
    <div className="kpis">
      <Kpi icon={Package} label="Live listings" value={live.length} sub="visible right now" color="#E23744" bg="#FFF1F2" />
      <Kpi icon={IndianRupee} label="Revenue recovered" value={inr(revenue)} sub="from discounted sales" color="#1BA672" bg="#E8F7F0" />
      <Kpi icon={Leaf} label="Food rescued" value={(soldKg + donatedKg).toFixed(1) + ' kg'} sub={`${imp.meals} meals`} color="#3B6FE0" bg="#EAF0FF" />
      <Kpi icon={Sprout} label="CO₂e avoided" value={Math.max(imp.co2, 0) + ' kg'} sub="2.5 kg per kg of food" color="#C98A14" bg="#FFF6E0" />
    </div>
    <div className="two">
      <div className="card pad">
        <div className="row between" style={{ marginBottom: 6 }}><h3>Food by channel, last 14 days</h3><span className="badge">Sample history (kg)</span></div>
        <div className="legend" style={{ marginBottom: 10 }}>{[['Sold', '#1BA672'], ['Donated', '#3B6FE0'], ['Composted', '#E0A81E']].map(([t, c]) => <span key={t}><i style={{ background: c }} />{t}</span>)}</div>
        <StackedBars data={history} keys={['sold', 'donated', 'composted']} colors={['#1BA672', '#3B6FE0', '#E0A81E']} />
      </div>
      <div className="card pad">
        <h3>Today's decisions</h3>
        <div className="row" style={{ justifyContent: 'center', margin: '14px 0' }}><Donut parts={mix} label={listings.length} sub="items listed" /></div>
        <div className="col" style={{ gap: 8 }}>{mix.map((m) => <div key={m.key} className="row between sm"><span className="row"><i className="dot" style={{ background: m.color }} />{DECISION[m.key].label}</span><b className="num">{m.value}</b></div>)}</div>
      </div>
    </div>
    <div className="card" style={{ marginTop: 18 }}>
      <div className="row between" style={{ padding: '18px 20px 6px' }}><h3>Recent listings</h3><Link to="/restaurant/listings" className="b sm" style={{ color: 'var(--red-d)' }}>View all</Link></div>
      <ListingsTable rows={listings.slice(0, 5)} compact />
    </div>
  </>)
}

function ListingsTable({ rows, compact }) {
  const { setListing, removeListing, toast } = useStore()
  const now = useNow()
  if (!rows.length) return <Empty emoji="🥘" title="No listings yet">Add your first surplus item and FoodLoop will decide the best route for it.</Empty>
  return (
    <div className="tablewrap"><table>
      <thead><tr><th>Item</th><th>Quantity</th><th>Decision</th><th>Time left</th><th>Price</th><th>Status</th>{!compact && <th />}</tr></thead>
      <tbody>{rows.map((l) => {
        const expired = l.status === 'live' && l.expiresAt <= now
        return (<tr key={l.id}>
          <td><div className="cellitem"><Tile cat={l.category} className="t" /><div><div className="b">{l.item}</div><div className="xs muted">{CATEGORIES[l.category].label} · {STORAGE[l.storage].label}</div></div></div></td>
          <td className="num">{l.qty} {l.unit}</td>
          <td><DecisionBadge d={l.decision} /></td>
          <td className="num sm">{l.status === 'live' ? fmtLeft(l.expiresAt, now) : '—'}</td>
          <td className="num">{l.decision === 'sell' ? <><b>{inr(l.price)}</b> <span className="xs muted">{l.discount}% off</span></> : <span className="muted">Free</span>}</td>
          <td><StatusBadge s={expired ? 'expired' : l.status} /></td>
          {!compact && <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
            {l.status === 'live' && l.decision === 'compost' && <button className="btn sm" onClick={() => { setListing(l.id, { status: 'composted' }); toast('Marked as composted') }}>Mark composted</button>}{' '}
            {l.status === 'live' && <button className="iconbtn" style={{ width: 34, height: 34, display: 'inline-grid' }} aria-label="Remove listing" onClick={() => { removeListing(l.id); toast('Listing removed') }}><Trash2 size={15} /></button>}
          </td>}
        </tr>)
      })}</tbody>
    </table></div>
  )
}

function Listings() {
  const { listings } = useMine()
  const [f, setF] = useState('all')
  const rows = listings.filter((l) => f === 'all' || l.decision === f)
  return (<>
    <PageHead title="My listings" sub="Every item, the decision FoodLoop made, and where it stands.">
      <div className="seg">{['all', 'sell', 'donate', 'compost'].map((k) => <button key={k} className={f === k ? 'on' : ''} onClick={() => setF(k)}>{k === 'all' ? 'All' : DECISION[k].label}</button>)}</div>
    </PageHead>
    <div className="card"><ListingsTable rows={rows} /></div>
  </>)
}

function AddSurplus() {
  const { vendor } = useMine()
  const { addListing, toast } = useStore()
  const go = useNavigate()
  const [f, setF] = useState({ item: '', category: 'cooked', storage: 'hot', qty: 10, unit: 'portions', kgPerUnit: 0.4, mrp: 200, hours: 2, temp: 30 })
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }))
  const local = useMemo(() => decide(f), [f])
  const [srv, setSrv] = useState(null)
  useEffect(() => {
    const kgNow = f.qty * f.kgPerUnit
    const t = setTimeout(() => { apiDecide(f, kgNow).then((r) => setSrv(r ? { remaining: r.remaining_h, decision: r.decision, discount: r.discount } : null)) }, 250)
    return () => clearTimeout(t)
  }, [f])
  const d = srv || local
  const info = DECISION[d.decision]
  const maxLife = CATEGORIES[f.category].base * STORAGE[f.storage].factor
  const pct = Math.max(0, Math.min(100, (d.remaining / Math.max(maxLife, 1)) * 100))
  const price = Math.round(f.mrp * (1 - d.discount / 100))
  const kg = +(f.qty * f.kgPerUnit).toFixed(1)
  const valid = f.item.trim() && f.qty > 0 && f.mrp >= 0

  const publish = (e) => {
    e.preventDefault()
    addListing(vendor.id, { ...f, item: f.item.trim(), override: srv || undefined })
    toast(d.decision === 'sell' ? 'Published for customers' : d.decision === 'donate' ? 'Sent to NGOs for pickup' : 'Logged for composting')
    go('/restaurant/listings')
  }

  return (<>
    <PageHead title="Add surplus" sub="Tell us what is left. FoodLoop estimates how long it stays safe and picks the best channel." />
    <form className="two l15" style={{ alignItems: 'start' }} onSubmit={publish}>
      <div className="card pad">
        <div className="eq">
          <div className="field" style={{ gridColumn: '1/-1' }}><label htmlFor="item">Item name</label><input id="item" className="input" placeholder="e.g. Veg Dum Biryani" value={f.item} onChange={(e) => set('item', e.target.value)} /></div>
          <div className="field"><label htmlFor="cat">Food category</label>
            <select id="cat" className="select" value={f.category} onChange={(e) => set('category', e.target.value)}>{Object.entries(CATEGORIES).map(([k, c]) => <option key={k} value={k}>{c.emoji} {c.label}</option>)}</select></div>
          <div className="field"><label htmlFor="sto">How is it stored?</label>
            <select id="sto" className="select" value={f.storage} onChange={(e) => set('storage', e.target.value)}>{Object.entries(STORAGE).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}</select></div>
          <div className="field"><label htmlFor="hrs">Hours since prepared</label><input id="hrs" className="input" type="number" min="0" step="0.5" value={f.hours} onChange={(e) => set('hours', +e.target.value)} /></div>
          <div className="field"><label htmlFor="tmp">Room temperature (°C)</label><input id="tmp" className="input" type="number" min="5" max="45" value={f.temp} onChange={(e) => set('temp', +e.target.value)} /></div>
          <div className="field"><label htmlFor="qty">Quantity</label><input id="qty" className="input" type="number" min="1" value={f.qty} onChange={(e) => set('qty', +e.target.value)} /></div>
          <div className="field"><label htmlFor="unit">Unit</label>
            <select id="unit" className="select" value={f.unit} onChange={(e) => set('unit', e.target.value)}>{['portions', 'pieces', 'boxes', 'loaves', 'cups', 'kg'].map((u) => <option key={u}>{u}</option>)}</select></div>
          <div className="field"><label htmlFor="kgu">Weight per unit (kg)</label><input id="kgu" className="input" type="number" min="0.01" step="0.01" value={f.kgPerUnit} onChange={(e) => set('kgPerUnit', +e.target.value)} /></div>
          <div className="field"><label htmlFor="mrp">Regular price per unit (₹)</label><input id="mrp" className="input" type="number" min="0" value={f.mrp} onChange={(e) => set('mrp', +e.target.value)} /></div>
        </div>
      </div>

      <div className="card preview">
        <div className={'top ' + d.decision}>
          <div className="row xs" style={{ opacity: .9, gap: 6 }}><Sparkles size={14} />Recommended action<span className="right" data-testid="decision-source">{srv ? 'XGBoost model' : 'Rule table (offline)'}</span></div>
          <div style={{ fontSize: 30, fontWeight: 800, margin: '4px 0' }}>{info.label}</div>
          <div className="sm" style={{ opacity: .95 }}>{d.decision === 'sell' ? `Safe for about ${d.remaining} more hours. Customers can buy it at ${d.discount}% off.` : d.decision === 'donate' ? `About ${d.remaining} h of safe time left. Best sent to an NGO for same-day serving.` : 'Too close to its limit to serve safely. It will be composted.'}</div>
          <div className="gauge" role="img" aria-label="Remaining safe life"><i style={{ width: pct + '%' }} /></div>
          <div className="row between xs" style={{ marginTop: 6, opacity: .9 }}><span>Expires</span><span>{Math.max(d.remaining, 0)} h left</span></div>
        </div>
        <div style={{ padding: '6px 20px 20px' }}>
          <div className="kv"><span className="muted">Total weight</span><b className="num">{kg} kg</b></div>
          {d.decision === 'sell' && <div className="kv"><span className="muted">Customer price</span><b className="num">{inr(price)} <s className="muted xs" style={{ fontWeight: 400 }}>{inr(f.mrp)}</s></b></div>}
          <div className="kv"><span className="muted">Meals if rescued</span><b className="num">{impactOf(kg).meals}</b></div>
          <div className="kv"><span className="muted">CO₂e avoided</span><b className="num">{impactOf(kg).co2} kg</b></div>
          <button className="btn primary lg block" style={{ marginTop: 14 }} disabled={!valid}>Publish listing</button>
          <div className="hint" style={{ marginTop: 10 }}>Rule: sell at {THRESHOLDS.sell} h or more remaining, donate at {THRESHOLDS.donate}–{THRESHOLDS.sell} h, compost below {THRESHOLDS.donate} h. Preview uses a shelf-life rule table; the live system calls the trained XGBoost model.</div>
        </div>
      </div>
    </form>
  </>)
}

function Pickups() {
  const { orders } = useMine()
  const { setOrder, toast } = useStore()
  return (<>
    <PageHead title="Customer pickups" sub="Check the code, hand over the food, mark it collected." />
    <div className="card">
      {orders.length === 0 ? <Empty emoji="🧾" title="No pickups yet">Orders appear here as soon as a customer reserves an item.</Empty> : (
        <div className="tablewrap"><table><thead><tr><th>Code</th><th>Items</th><th>Total</th><th>Placed</th><th>Status</th><th /></tr></thead>
          <tbody>{orders.map((o) => (<tr key={o.id}>
            <td><span className="badge" style={{ fontSize: 14, letterSpacing: 2 }}>{o.code}</span></td>
            <td className="sm">{o.items.map((i) => `${i.qty} × ${i.item}`).join(', ')}</td>
            <td className="num b">{inr(o.total)}</td>
            <td className="sm muted">{new Date(o.at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}</td>
            <td><StatusBadge s={o.status} /></td>
            <td style={{ textAlign: 'right' }}>{o.status === 'placed' && <button className="btn sm green" onClick={() => { setOrder(o.id, { status: 'collected' }); toast('Marked as collected') }}>Mark collected</button>}</td>
          </tr>))}</tbody></table></div>
      )}
    </div>
  </>)
}

export default function Restaurant() {
  return (
    <DashShell role="Restaurant" color="#F59E0B" icon={Store} nav={NAV}>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="add" element={<AddSurplus />} />
        <Route path="listings" element={<Listings />} />
        <Route path="orders" element={<Pickups />} />
      </Routes>
    </DashShell>
  )
}
