import React, { useMemo, useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import { HandHeart, Route as RouteIcon, History, Leaf, Truck, Utensils, Check, MapPin, Clock, Sprout, Gauge } from 'lucide-react'
import { useStore } from '../store.jsx'
import { DashShell, PageHead, Kpi, Tile, Empty, StatusBadge, RouteMap, useNow, fmtLeft } from '../components/ui.jsx'
import { apiRoute } from '../api.js'
import { CATEGORIES, optimiseRoute, routeLength, impactOf, CO2_PER_KM, roadKm } from '../engine.js'

function useNgo() {
  const { session, ngos, listings, vendors, pickups } = useStore()
  const ngo = ngos.find((n) => n.id === session.id)
  const now = useNow()
  const open = listings
    .filter((l) => l.status === 'live' && l.decision === 'donate' && l.expiresAt > now)
    .map((l) => ({ ...l, vendor: vendors.find((v) => v.id === l.vendorId), kg: +(l.qty * l.kgPerUnit).toFixed(1) }))
    .filter((l) => l.vendor)
    .map((l) => ({ ...l, dist: +roadKm(ngo, l.vendor).toFixed(1) }))
    .sort((a, b) => a.expiresAt - b.expiresAt)
  return { ngo, open, mine: pickups.filter((p) => p.ngoId === ngo.id), now }
}

const NAV = [
  { to: '/ngo', label: 'Donations', icon: HandHeart, end: true },
  { to: '/ngo/pickups', label: 'My pickups', icon: History },
]

function Donations() {
  const { ngo, open, mine } = useNgo()
  const { claim, toast, uid } = useStore()
  const [sel, setSel] = useState([])
  const [plan, setPlan] = useState(null)
  const now = useNow()

  const chosen = open.filter((l) => sel.includes(l.id))
  const kg = chosen.reduce((s, l) => s + l.kg, 0)
  const over = kg > ngo.capacityKg
  const toggle = (id) => { setPlan(null); setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id])) }

  const build = async () => {
    const stops = chosen.map((l) => ({ ...l.vendor, listing: l }))
    const naiveKm = routeLength(ngo, stops)
    const r = await apiRoute(ngo, stops)
    if (r) {
      const order = r.order.map((id) => stops.find((s) => s.id === id))
      setPlan({ order, km: routeLength(ngo, order), naive: stops, naiveKm, source: 'OR-Tools API', ms: r.solve_ms })
    } else {
      const { order, km } = optimiseRoute(ngo, stops)
      setPlan({ order, km, naive: stops, naiveKm, source: 'Offline heuristic' })
    }
  }

  const confirm = () => {
    claim({ id: uid('p'), ngoId: ngo.id, listingIds: plan.order.map((s) => s.listing.id), km: +plan.km.toFixed(1), naiveKm: +plan.naiveKm.toFixed(1), kg: +kg.toFixed(1), at: Date.now(), status: 'planned', stops: plan.order.map((s) => ({ name: s.name, locality: s.locality, item: s.listing.item })) })
    toast('Pickup accepted. Route saved to My pickups.')
    setSel([]); setPlan(null)
  }

  const savedKm = plan ? Math.max(plan.naiveKm - plan.km, 0) : 0
  const totalKg = mine.reduce((s, p) => s + p.kg, 0), totalKm = mine.reduce((s, p) => s + p.km, 0)

  return (<>
    <PageHead title="Available donations" sub={`${ngo.name} · pickups within Bengaluru, nearest expiry first`} />
    <div className="kpis">
      <Kpi icon={HandHeart} label="Open donations" value={open.length} sub="waiting for an NGO" color="#3B6FE0" bg="#EAF0FF" />
      <Kpi icon={Utensils} label="Meals rescued" value={impactOf(totalKg).meals} sub={`${totalKg.toFixed(1)} kg so far`} color="#1BA672" bg="#E8F7F0" />
      <Kpi icon={Truck} label="Pickups planned" value={mine.length} sub={`${totalKm.toFixed(1)} km driven`} color="#E23744" bg="#FFF1F2" />
      <Kpi icon={Gauge} label="Vehicle capacity" value={ngo.capacityKg + ' kg'} sub="per trip" color="#C98A14" bg="#FFF6E0" />
    </div>

    <div className="two" style={{ alignItems: 'start' }}>
      <div className="card">
        <div className="row between" style={{ padding: '18px 20px 12px' }}><h3>Select donations to collect</h3><span className="muted sm">{sel.length} selected</span></div>
        {open.length === 0 ? <Empty emoji="🤝" title="No open donations right now">Restaurants send items here when they are too close to expiry to sell but still safe to serve.</Empty> :
          open.map((l) => (
            <div key={l.id} className={'selrow' + (sel.includes(l.id) ? ' on' : '')} onClick={() => toggle(l.id)} role="checkbox" aria-checked={sel.includes(l.id)} tabIndex={0} onKeyDown={(e) => (e.key === ' ' || e.key === 'Enter') && (e.preventDefault(), toggle(l.id))}>
              <span className="check">{sel.includes(l.id) && <Check size={14} strokeWidth={3} />}</span>
              <Tile cat={l.category} className="" style={{ width: 52, height: 52, borderRadius: 12, display: 'grid', placeItems: 'center', fontSize: 26 }} />
              <div className="grow">
                <div className="b">{l.item}</div>
                <div className="sm muted row" style={{ gap: 6 }}><MapPin size={13} />{l.vendor.name}, {l.vendor.locality} · {l.dist} km</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="b num">{l.qty} {l.unit} · {l.kg} kg</div>
                <div className="xs row" style={{ justifyContent: 'flex-end', gap: 4, color: l.expiresAt - now < 2 * 3600e3 ? 'var(--red-d)' : 'var(--ink3)', fontWeight: 600 }}><Clock size={12} />{fmtLeft(l.expiresAt, now)}</div>
              </div>
            </div>
          ))}
      </div>

      <div className="col" style={{ position: 'sticky', top: 24 }}>
        <div className="card pad">
          <h3>Pickup plan</h3>
          <div className="row between" style={{ margin: '14px 0 6px' }}><span className="muted sm">Load</span><b className="num" style={{ color: over ? 'var(--red-d)' : undefined }}>{kg.toFixed(1)} / {ngo.capacityKg} kg</b></div>
          <div className="progress"><i style={{ width: Math.min(100, (kg / ngo.capacityKg) * 100) + '%', background: over ? 'var(--red)' : undefined }} /></div>
          {over && <div className="note" style={{ marginTop: 12 }}>This is more than one trip can carry. Remove an item or split it into two pickups.</div>}
          <button className="btn primary block" style={{ marginTop: 16 }} disabled={!sel.length || over} onClick={build}><RouteIcon size={18} />Plan optimised route</button>
        </div>

        {plan && (<div className="card pad">
          <div className="row between"><h3>Optimised route</h3><span className="badge" data-testid="route-source">{plan.source}</span></div>
          <div style={{ margin: '12px 0' }}><RouteMap base={ngo} stops={plan.order} naive={plan.naive} height={430} /></div>
          <div className="stop"><span className="n base">★</span><div><div className="b">Start: {ngo.name}</div><div className="xs muted">{ngo.locality}</div></div></div>
          {plan.order.map((s, i) => (<div className="stop" key={s.id}><span className="n">{i + 1}</span><div><div className="b">{s.name}</div><div className="xs muted">{s.locality} · {s.listing.item} · {s.listing.kg} kg</div></div></div>))}
          <div className="eq" style={{ marginTop: 14, gap: 10 }}>
            <div className="card pad" style={{ padding: 12, boxShadow: 'none' }}><div className="xs muted">Route length</div><div className="bb num" style={{ fontSize: 20 }}>{plan.km.toFixed(1)} km</div></div>
            <div className="card pad" style={{ padding: 12, boxShadow: 'none', background: 'var(--green-bg)', borderColor: '#C6EBDB' }}><div className="xs muted">Saved vs order accepted</div><div className="bb num" style={{ fontSize: 20, color: 'var(--green-d)' }}>{savedKm.toFixed(1)} km</div></div>
          </div>
          <div className="hint" style={{ margin: '10px 0 14px' }}>Fuel saved ≈ {(savedKm * CO2_PER_KM).toFixed(1)} kg CO₂e. Distances are straight-line × 1.3 road factor.</div>
          <button className="btn green block" onClick={confirm}><Check size={18} />Accept and confirm pickup</button>
        </div>)}
      </div>
    </div>
  </>)
}

function Pickups() {
  const { mine } = useNgo()
  const { setPickup, listings, setListing, toast } = useStore()
  const done = (p) => { setPickup(p.id, { status: 'completed' }); toast('Pickup marked completed') }
  return (<>
    <PageHead title="My pickups" sub="Routes you have accepted and their results." />
    {mine.length === 0 ? <div className="card"><Empty emoji="🚚" title="No pickups yet">Select donations on the previous page to plan your first route.</Empty></div> :
      <div className="col" style={{ gap: 16 }}>{mine.map((p) => {
        const imp = impactOf(p.kg, p.km)
        return (<div className="card pad" key={p.id}>
          <div className="row between"><div><h3>{p.stops.length} stop{p.stops.length > 1 ? 's' : ''} · {p.kg} kg</h3><div className="sm muted">{new Date(p.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</div></div><StatusBadge s={p.status} /></div>
          <div className="col" style={{ gap: 0, margin: '12px 0' }}>{p.stops.map((s, i) => (<div className="stop" key={i}><span className="n">{i + 1}</span><div><div className="b">{s.name}</div><div className="xs muted">{s.locality} · {s.item}</div></div></div>))}</div>
          <div className="row" style={{ gap: 22, flexWrap: 'wrap' }}>
            <div><div className="xs muted">Distance</div><b className="num">{p.km} km</b></div>
            <div><div className="xs muted">Meals</div><b className="num">{imp.meals}</b></div>
            <div><div className="xs muted">CO₂e avoided</div><b className="num">{Math.max(imp.co2, 0)} kg</b></div>
            {p.status === 'planned' && <button className="btn green sm right" onClick={() => done(p)}><Check size={16} />Mark completed</button>}
          </div>
        </div>)
      })}</div>}
  </>)
}

export default function Ngo() {
  return (
    <DashShell role="NGO" color="#3B6FE0" icon={HandHeart} nav={NAV}>
      <Routes><Route index element={<Donations />} /><Route path="pickups" element={<Pickups />} /></Routes>
    </DashShell>
  )
}
