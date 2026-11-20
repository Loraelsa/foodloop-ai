import React, { useMemo, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LayoutDashboard, Store, HeartHandshake, ListChecks, Globe2, ShieldCheck, Leaf, Utensils, Sprout, Users, Search, Check, Ban } from 'lucide-react'
import { useStore } from '../store.jsx'
import { DashShell, PageHead, Kpi, Tile, DecisionBadge, StatusBadge, Empty, StackedBars, Donut, HBars, DECISION } from '../components/ui.jsx'
import { CATEGORIES, STORAGE, THRESHOLDS, impactOf, inr, KG_PER_MEAL, CO2_PER_KG, CO2_PER_KM } from '../engine.js'

const NAV = [
  { to: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/admin/restaurants', label: 'Restaurants', icon: Store },
  { to: '/admin/ngos', label: 'NGOs', icon: HeartHandshake },
  { to: '/admin/listings', label: 'All listings', icon: ListChecks },
  { to: '/admin/impact', label: 'Impact & SDGs', icon: Globe2 },
  { to: '/admin/rules', label: 'Decision rules', icon: ShieldCheck },
]

function totals(s) {
  const kgOf = (l) => l.qty * l.kgPerUnit
  const soldKg = s.orders.reduce((a, o) => a + o.kg, 0)
  const donatedKg = s.listings.filter((l) => l.status === 'claimed').reduce((a, l) => a + kgOf(l), 0)
  const km = s.pickups.reduce((a, p) => a + p.km, 0)
  const histKg = s.history.reduce((a, d) => a + d.sold + d.donated, 0)
  return { soldKg, donatedKg, km, histKg, revenue: s.orders.reduce((a, o) => a + o.total, 0) }
}

function Overview() {
  const s = useStore()
  const t = totals(s)
  const rescued = t.histKg + t.soldKg + t.donatedKg
  const imp = impactOf(rescued, t.km)
  const pendingV = s.vendors.filter((v) => v.status === 'pending').length, pendingN = s.ngos.filter((n) => n.status === 'pending').length
  const mix = ['sell', 'donate', 'compost'].map((d) => ({ key: d, value: s.listings.filter((l) => l.decision === d).length, color: DECISION[d].color }))
  const byLoc = useMemo(() => {
    const m = {}; s.listings.forEach((l) => { const v = s.vendors.find((x) => x.id === l.vendorId); if (v) m[v.locality] = (m[v.locality] || 0) + l.qty * l.kgPerUnit })
    return Object.entries(m).map(([label, value]) => ({ label, value: +value.toFixed(1) })).sort((a, b) => b.value - a.value).slice(0, 6)
  }, [s.listings, s.vendors])

  return (<>
    <PageHead title="Platform overview" sub="Everything happening across restaurants, NGOs and customers." />
    {(pendingV + pendingN > 0) && <div className="note" style={{ marginBottom: 18 }}><Users size={16} style={{ flex: 'none', marginTop: 2 }} />{pendingV} restaurant{pendingV !== 1 ? 's' : ''} and {pendingN} NGO{pendingN !== 1 ? 's' : ''} waiting for approval.</div>}
    <div className="kpis">
      <Kpi icon={Leaf} label="Food rescued" value={Math.round(rescued).toLocaleString('en-IN') + ' kg'} sub="last 14 days + live" color="#1BA672" bg="#E8F7F0" />
      <Kpi icon={Utensils} label="Meals provided" value={imp.meals.toLocaleString('en-IN')} sub={`at ${KG_PER_MEAL} kg per meal`} color="#3B6FE0" bg="#EAF0FF" />
      <Kpi icon={Sprout} label="CO₂e avoided" value={Math.round(Math.max(imp.co2, 0)).toLocaleString('en-IN') + ' kg'} sub="net of pickup transport" color="#C98A14" bg="#FFF6E0" />
      <Kpi icon={Store} label="Active partners" value={s.vendors.filter((v) => v.status === 'approved').length + s.ngos.filter((n) => n.status === 'verified').length} sub={`${s.vendors.length} restaurants · ${s.ngos.length} NGOs`} color="#E23744" bg="#FFF1F2" />
    </div>
    <div className="two">
      <div className="card pad">
        <div className="row between"><h3>Food by channel</h3><span className="badge">Sample history (kg/day)</span></div>
        <div className="legend" style={{ margin: '8px 0 10px' }}>{[['Sold', '#1BA672'], ['Donated', '#3B6FE0'], ['Composted', '#E0A81E']].map(([x, c]) => <span key={x}><i style={{ background: c }} />{x}</span>)}</div>
        <StackedBars data={s.history} keys={['sold', 'donated', 'composted']} colors={['#1BA672', '#3B6FE0', '#E0A81E']} />
      </div>
      <div className="card pad">
        <h3>Decision mix</h3>
        <div className="row" style={{ justifyContent: 'center', margin: '14px 0' }}><Donut parts={mix} label={s.listings.length} sub="listings" /></div>
        <div className="col" style={{ gap: 8 }}>{mix.map((m) => <div key={m.key} className="row between sm"><span className="row"><i className="dot" style={{ background: m.color }} />{DECISION[m.key].label}</span><b className="num">{m.value}</b></div>)}</div>
      </div>
    </div>
    <div className="eq" style={{ marginTop: 18 }}>
      <div className="card pad"><h3 style={{ marginBottom: 16 }}>Surplus by locality (kg listed)</h3><HBars rows={byLoc} fmt={(v) => v + ' kg'} /></div>
      <div className="card pad"><h3 style={{ marginBottom: 6 }}>Needs attention</h3>
        {s.vendors.filter((v) => v.status === 'pending').map((v) => (<div key={v.id} className="row" style={{ padding: '12px 0', borderBottom: '1px solid var(--line2)' }}><div className="grow"><div className="b">{v.name}</div><div className="xs muted">Restaurant · {v.locality}</div></div><button className="btn sm green" onClick={() => { s.setVendor(v.id, { status: 'approved' }); s.toast(v.name + ' approved') }}>Approve</button></div>))}
        {s.ngos.filter((n) => n.status === 'pending').map((n) => (<div key={n.id} className="row" style={{ padding: '12px 0', borderBottom: '1px solid var(--line2)' }}><div className="grow"><div className="b">{n.name}</div><div className="xs muted">NGO · {n.locality}</div></div><button className="btn sm green" onClick={() => { s.setNgo(n.id, { status: 'verified' }); s.toast(n.name + ' verified') }}>Verify</button></div>))}
        {pendingV + pendingN === 0 && <Empty emoji="✅" title="All caught up">No partners are waiting for review.</Empty>}
      </div>
    </div>
  </>)
}

function Restaurants() {
  const s = useStore()
  const [q, setQ] = useState('')
  const rows = s.vendors.filter((v) => (v.name + v.locality + v.cuisines).toLowerCase().includes(q.toLowerCase()))
  return (<>
    <PageHead title="Restaurants" sub="Approve new partners and pause accounts when needed.">
      <div className="searchbar" style={{ width: 280, height: 42 }}><Search size={17} style={{ marginLeft: 14 }} /><input placeholder="Search restaurants" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search restaurants" /></div>
    </PageHead>
    <div className="card tablewrap"><table>
      <thead><tr><th>Restaurant</th><th>Locality</th><th>Cuisine</th><th>Listings</th><th>Rating</th><th>Status</th><th /></tr></thead>
      <tbody>{rows.map((v) => (<tr key={v.id}>
        <td><div className="cellitem"><span className="avatar" style={{ borderRadius: 10, width: 38, height: 38 }}>{v.name[0]}</span><div><div className="b">{v.name}</div><div className="xs muted">Joined {v.joined}</div></div></div></td>
        <td>{v.locality}</td><td className="sm">{v.cuisines}</td>
        <td className="num">{s.listings.filter((l) => l.vendorId === v.id).length}</td>
        <td><span className="rating">{v.rating}</span></td>
        <td><StatusBadge s={v.status} /></td>
        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
          {v.status !== 'approved' && <button className="btn sm green" onClick={() => { s.setVendor(v.id, { status: 'approved' }); s.toast('Approved') }}><Check size={15} />Approve</button>}
          {v.status === 'approved' && <button className="btn sm" onClick={() => { s.setVendor(v.id, { status: 'suspended' }); s.toast('Account suspended') }}><Ban size={15} />Suspend</button>}
        </td></tr>))}</tbody>
    </table></div>
  </>)
}

function Ngos() {
  const s = useStore()
  return (<>
    <PageHead title="NGOs" sub="Only verified organisations can claim donations." />
    <div className="card tablewrap"><table>
      <thead><tr><th>Organisation</th><th>Locality</th><th>Capacity</th><th>Contact</th><th>Pickups</th><th>Status</th><th /></tr></thead>
      <tbody>{s.ngos.map((n) => (<tr key={n.id}>
        <td><div className="cellitem"><span className="avatar" style={{ borderRadius: 10, width: 38, height: 38, background: '#EAF0FF', color: '#2850B5' }}>{n.name[0]}</span><div className="b">{n.name}</div></div></td>
        <td>{n.locality}</td><td className="num">{n.capacityKg} kg</td><td className="sm">{n.contact}</td>
        <td className="num">{s.pickups.filter((p) => p.ngoId === n.id).length}</td>
        <td><StatusBadge s={n.status} /></td>
        <td style={{ textAlign: 'right' }}>{n.status !== 'verified' ? <button className="btn sm green" onClick={() => { s.setNgo(n.id, { status: 'verified' }); s.toast('NGO verified') }}><Check size={15} />Verify</button> : <button className="btn sm" onClick={() => { s.setNgo(n.id, { status: 'suspended' }); s.toast('NGO suspended') }}><Ban size={15} />Suspend</button>}</td>
      </tr>))}</tbody>
    </table></div>
  </>)
}

function AllListings() {
  const s = useStore()
  const [f, setF] = useState('all')
  const rows = s.listings.filter((l) => f === 'all' || l.decision === f)
  return (<>
    <PageHead title="All listings" sub="Moderate anything that should not be live.">
      <div className="seg">{['all', 'sell', 'donate', 'compost'].map((k) => <button key={k} className={f === k ? 'on' : ''} onClick={() => setF(k)}>{k === 'all' ? 'All' : DECISION[k].label}</button>)}</div>
    </PageHead>
    <div className="card tablewrap"><table>
      <thead><tr><th>Item</th><th>Restaurant</th><th>Qty</th><th>Decision</th><th>Remaining</th><th>Status</th><th /></tr></thead>
      <tbody>{rows.map((l) => (<tr key={l.id}>
        <td><div className="cellitem"><Tile cat={l.category} className="t" /><div className="b">{l.item}</div></div></td>
        <td className="sm">{s.vendors.find((v) => v.id === l.vendorId)?.name}</td>
        <td className="num">{l.qty} {l.unit}</td><td><DecisionBadge d={l.decision} /></td>
        <td className="num">{l.remaining} h</td><td><StatusBadge s={l.status} /></td>
        <td style={{ textAlign: 'right' }}>{l.status === 'live' && <button className="btn sm" onClick={() => { s.removeListing(l.id); s.toast('Listing removed') }}>Remove</button>}</td>
      </tr>))}</tbody>
    </table></div>
  </>)
}

function Impact() {
  const s = useStore()
  const t = totals(s)
  const rescued = t.histKg + t.soldKg + t.donatedKg
  const imp = impactOf(rescued, t.km)
  const SDG = [
    ['2', 'Zero Hunger', 'Surplus reaches NGOs and customers instead of the bin.', '#DDA63A'],
    ['11', 'Sustainable Cities', 'Hyperlocal redistribution inside Bengaluru neighbourhoods.', '#F99D26'],
    ['12', 'Responsible Consumption', 'Food is recovered before it becomes waste.', '#BF8B2E'],
    ['13', 'Climate Action', 'Avoided landfill emissions net of pickup transport.', '#3F7E44'],
  ]
  return (<>
    <PageHead title="Impact & SDGs" sub="The numbers behind the sustainability dashboard." />
    <div className="kpis">
      <Kpi icon={Leaf} label="Food rescued" value={Math.round(rescued).toLocaleString('en-IN') + ' kg'} color="#1BA672" bg="#E8F7F0" />
      <Kpi icon={Utensils} label="Meals" value={imp.meals.toLocaleString('en-IN')} color="#3B6FE0" bg="#EAF0FF" />
      <Kpi icon={Sprout} label="CO₂e avoided (net)" value={Math.round(Math.max(imp.co2, 0)).toLocaleString('en-IN') + ' kg'} color="#C98A14" bg="#FFF6E0" />
      <Kpi icon={Store} label="Revenue recovered" value={inr(t.revenue)} sub="customer orders" color="#E23744" bg="#FFF1F2" />
    </div>
    <div className="eq">{SDG.map(([n, t2, d, c]) => (<div className="card sdg" key={n}><span className="n" style={{ background: c }}>{n}</span><div><div className="b">SDG {n} · {t2}</div><div className="sm muted">{d}</div></div></div>))}</div>
    <div className="card pad" style={{ marginTop: 18 }}>
      <h3>How these figures are calculated</h3>
      <div className="col" style={{ gap: 0, marginTop: 8 }}>
        <div className="kv"><span>Meals</span><span className="muted">kg ÷ {KG_PER_MEAL} (WRAP meal equivalent)</span></div>
        <div className="kv"><span>CO₂e avoided</span><span className="muted">kg × {CO2_PER_KG} (FAO food wastage footprint)</span></div>
        <div className="kv"><span>Transport emissions</span><span className="muted">km × {CO2_PER_KM} kg CO₂e (average diesel van, UK DESNZ 2025 factors)</span></div>
      </div>
      <div className="note info" style={{ marginTop: 14 }}>The 14-day history is sample data for demonstration. Live figures combine it with orders and pickups made in this session.</div>
    </div>
  </>)
}

function Rules() {
  return (<>
    <PageHead title="Decision rules" sub="How FoodLoop turns remaining safe time into an action." />
    <div className="three">
      {[['sell', `${THRESHOLDS.sell} h or more`, 'Listed for customers. Discount grows from 20% to 70% as time runs down.'], ['donate', `${THRESHOLDS.donate}–${THRESHOLDS.sell} h`, 'Offered to verified NGOs for same-day serving.'], ['compost', `Under ${THRESHOLDS.donate} h`, 'Too close to the safe limit. Sent to composting.']].map(([k, r, d]) => (
        <div className="card pad" key={k}><DecisionBadge d={k} /><div className="bb" style={{ fontSize: 24, margin: '12px 0 6px' }}>{r}</div><div className="sm muted">{d}</div></div>))}
    </div>
    <div className="card" style={{ marginTop: 18 }}>
      <div style={{ padding: '18px 20px 6px' }}><h3>Shelf-life assumptions</h3><div className="sm muted" style={{ marginTop: 2 }}>Safe hours at 25 °C, room temperature. Halves for every 10 °C above 25 °C.</div></div>
      <div className="tablewrap"><table><thead><tr><th>Category</th><th>Safe hours</th>{Object.values(STORAGE).map((x) => <th key={x.label}>{x.label} (×{x.factor})</th>)}</tr></thead>
        <tbody>{Object.entries(CATEGORIES).map(([k, c]) => (<tr key={k}><td><div className="cellitem"><Tile cat={k} className="t" /><span className="b">{c.label}</span></div></td><td className="num">{c.base} h</td>{Object.values(STORAGE).map((x) => <td key={x.label} className="num">{+(c.base * x.factor).toFixed(0)} h</td>)}</tr>))}</tbody></table></div>
    </div>
    <div className="note" style={{ marginTop: 18 }}>These are documented assumptions, not measured spoilage data. Thresholds and the discount curve are design choices to be calibrated with pilot data.</div>
  </>)
}

export default function Admin() {
  return (
    <DashShell role="Admin" color="#1C1C1C" icon={ShieldCheck} nav={NAV}>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="restaurants" element={<Restaurants />} />
        <Route path="ngos" element={<Ngos />} />
        <Route path="listings" element={<AllListings />} />
        <Route path="impact" element={<Impact />} />
        <Route path="rules" element={<Rules />} />
      </Routes>
    </DashShell>
  )
}
