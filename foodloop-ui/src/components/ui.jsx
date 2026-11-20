import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Repeat2, LogOut, X, CheckCircle2, RotateCcw } from 'lucide-react'
import { CATEGORIES } from '../engine.js'
import { useStore } from '../store.jsx'

export const Logo = ({ to = '/' }) => (
  <NavLink to={to} className="logo" aria-label="FoodLoop AI home">
    <span className="mark"><Repeat2 size={19} strokeWidth={2.6} /></span>
    <span>Food<em>Loop</em></span>
  </NavLink>
)

export const tint = (cat) => `linear-gradient(145deg, ${CATEGORIES[cat].tint[0]}, ${CATEGORIES[cat].tint[1]})`

export function Tile({ cat, className = '', style, children }) {
  return (
    <div className={className} style={{ background: tint(cat), ...style }}>
      {children ?? CATEGORIES[cat].emoji}
    </div>
  )
}

export function useNow(ms = 30000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t) }, [ms])
  return now
}

export function fmtLeft(expiresAt, now = Date.now()) {
  const m = Math.floor((expiresAt - now) / 60000)
  if (m <= 0) return 'Expired'
  if (m < 60) return `${m} min left`
  const h = Math.floor(m / 60)
  return h >= 48 ? `${Math.round(h / 24)} days left` : `${h}h ${m % 60}m left`
}

export const DECISION = {
  sell:    { label: 'Sell',    cls: 'green', color: '#1BA672' },
  donate:  { label: 'Donate',  cls: 'blue',  color: '#3B6FE0' },
  compost: { label: 'Compost', cls: 'amber', color: '#C98A14' },
}
export const DecisionBadge = ({ d }) => <span className={'badge ' + DECISION[d].cls}>{DECISION[d].label}</span>

export const STATUS = {
  live: ['green', 'Live'], sold: ['', 'Sold out'], claimed: ['blue', 'Claimed by NGO'],
  composted: ['amber', 'Composted'], expired: ['red', 'Expired'], placed: ['amber', 'Ready for pickup'],
  collected: ['green', 'Collected'], planned: ['amber', 'Route planned'], completed: ['green', 'Completed'],
  pending: ['amber', 'Pending'], approved: ['green', 'Approved'], verified: ['green', 'Verified'], suspended: ['red', 'Suspended'],
}
export const StatusBadge = ({ s }) => <span className={'badge ' + (STATUS[s]?.[0] || '')}>{STATUS[s]?.[1] || s}</span>

export const Kpi = ({ icon: Icon, label, value, sub, color = '#E23744', bg = '#FFF1F2' }) => (
  <div className="card kpi">
    <div className="top"><span>{label}</span><span className="ico" style={{ background: bg, color }}><Icon size={18} /></span></div>
    <div className="v num">{value}</div>
    {sub && <div className="d">{sub}</div>}
  </div>
)

export const Empty = ({ emoji = '🍽️', title, children }) => (
  <div className="empty"><div className="big">{emoji}</div><div className="b" style={{ color: 'var(--ink)', fontSize: 16 }}>{title}</div><div>{children}</div></div>
)

export function Toast() {
  const { note } = useStore()
  if (!note) return null
  return <div className="toast" role="status" key={note.id}><CheckCircle2 size={18} color="#4ADE9B" />{note.msg}</div>
}

export function Drawer({ open, onClose, title, children, footer }) {
  useEffect(() => {
    if (!open) return
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open) return null
  return (<>
    <div className="scrim" onClick={onClose} />
    <aside className="drawer" role="dialog" aria-label={title}>
      <header><h3 style={{ fontSize: 18 }}>{title}</h3><button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
      <div className="body">{children}</div>
      {footer && <footer>{footer}</footer>}
    </aside>
  </>)
}

export function Modal({ open, onClose, children }) {
  if (!open) return null
  return (<><div className="scrim" onClick={onClose} /><div className="modal" role="dialog">{children}</div></>)
}

/* ---------------- dashboard shell ---------------- */
export function DashShell({ role, color, icon: RoleIcon, nav, children }) {
  const { session, logout, reset } = useStore()
  const go = useNavigate()
  return (
    <div className="shell">
      <aside className="side">
        <div className="logo" style={{ cursor: 'default' }}><span className="mark"><Repeat2 size={19} strokeWidth={2.6} /></span><span>Food<em>Loop</em></span></div>
        <div className="role">
          <span className="ic" style={{ background: color }}><RoleIcon size={18} /></span>
          <div style={{ minWidth: 0 }}><div className="b" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{session?.name}</div><div className="xs muted">{role}</div></div>
        </div>
        {nav.map(({ to, label, icon: I, pill, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => 'navlink' + (isActive ? ' on' : '')}>
            <I size={19} />{label}{pill ? <span className="pill">{pill}</span> : null}
          </NavLink>
        ))}
        <div className="foot">
          {role === 'Admin' && <button className="navlink" onClick={() => { reset(); }}><RotateCcw size={19} />Reset demo data</button>}
          <button className="navlink" onClick={() => { logout(); go('/') }}><LogOut size={19} />Sign out</button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}

export const PageHead = ({ title, sub, children }) => (
  <div className="pagehead"><div><h1>{title}</h1>{sub && <p>{sub}</p>}</div><div className="row">{children}</div></div>
)

/* ---------------- charts (dependency-free SVG) ---------------- */
export function StackedBars({ data, keys, colors, height = 230 }) {
  const W = 640, H = height, pl = 34, pb = 26, pt = 10
  const rawMax = Math.max(...data.map((d) => keys.reduce((s, k) => s + d[k], 0)))
  const step = Math.max(10, Math.ceil(rawMax / 4 / 10) * 10)
  const max = step * 4
  const bw = (W - pl) / data.length
  const y = (v) => pt + (H - pt - pb) * (1 - v / max)
  const ticks = [0, 1, 2, 3, 4].map((i) => i * step)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }} role="img" aria-label="Daily food recovered by channel">
      {ticks.map((t) => (<g key={t}><line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="#EDEDED" /><text x={pl - 6} y={y(t) + 4} fontSize="10.5" fill="#828282" textAnchor="end">{t}</text></g>))}
      {data.map((d, i) => {
        let acc = 0
        return (<g key={i}>
          {keys.map((k, j) => { const h = (H - pt - pb) * (d[k] / max); acc += d[k]; return <rect key={k} x={pl + i * bw + bw * 0.2} width={bw * 0.6} y={y(acc)} height={h} fill={colors[j]} rx={j === keys.length - 1 ? 3 : 0} /> })}
          {i % 2 === 0 && <text x={pl + i * bw + bw / 2} y={H - 8} fontSize="10.5" fill="#828282" textAnchor="middle">{d.date}</text>}
        </g>)
      })}
    </svg>
  )
}

export function Donut({ parts, size = 170, label, sub }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  const r = 62, c = 2 * Math.PI * r
  let off = 0
  return (
    <svg width={size} height={size} viewBox="0 0 160 160" role="img" aria-label="Decision mix">
      <circle cx="80" cy="80" r={r} fill="none" stroke="#F0F0F0" strokeWidth="20" />
      {parts.map((p, i) => {
        const len = (p.value / total) * c
        const el = <circle key={i} cx="80" cy="80" r={r} fill="none" stroke={p.color} strokeWidth="20" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-off} transform="rotate(-90 80 80)" />
        off += len; return el
      })}
      <text x="80" y="80" textAnchor="middle" fontSize="26" fontWeight="800" fill="#1C1C1C">{label}</text>
      <text x="80" y="99" textAnchor="middle" fontSize="11" fill="#828282">{sub}</text>
    </svg>
  )
}

export function HBars({ rows, color = '#E23744', fmt = (v) => v }) {
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <div className="col" style={{ gap: 14 }}>
      {rows.map((r) => (
        <div key={r.label}>
          <div className="row between sm" style={{ marginBottom: 5 }}><span className="b">{r.label}</span><span className="num muted">{fmt(r.value)}</span></div>
          <div className="progress"><i style={{ width: (r.value / max) * 100 + '%', background: color }} /></div>
        </div>
      ))}
    </div>
  )
}

/* ---------------- schematic route map ---------------- */
export function RouteMap({ base, stops, naive = [], height = 380 }) {
  const pts = [base, ...stops, ...naive].filter(Boolean)
  const W = 720, H = height, pad = 54
  const lats = pts.map((p) => p.lat), lngs = pts.map((p) => p.lng)
  const minLa = Math.min(...lats), maxLa = Math.max(...lats), minLn = Math.min(...lngs), maxLn = Math.max(...lngs)
  const sx = (W - pad * 2) / Math.max(maxLn - minLn, 0.01), sy = (H - pad * 2) / Math.max(maxLa - minLa, 0.01)
  const s = Math.min(sx, sy)
  const ox = (W - (maxLn - minLn) * s) / 2, oy = (H - (maxLa - minLa) * s) / 2
  const P = (p) => [ox + (p.lng - minLn) * s, H - oy - (p.lat - minLa) * s]
  const line = (arr) => arr.map((p) => P(p).join(',')).join(' ')
  const grid = []
  for (let i = 1; i < 9; i++) grid.push(<line key={'v' + i} x1={(W / 9) * i} x2={(W / 9) * i} y1="0" y2={H} stroke="#fff" strokeWidth="1.2" opacity=".75" />)
  for (let i = 1; i < 6; i++) grid.push(<line key={'h' + i} y1={(H / 6) * i} y2={(H / 6) * i} x1="0" x2={W} stroke="#fff" strokeWidth="1.2" opacity=".75" />)
  return (
    <>
    <div className="map">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Pickup route map">
        <rect width={W} height={H} fill="#EAF1EA" />
        <path d={`M0 ${H * 0.72} C ${W * 0.25} ${H * 0.55}, ${W * 0.5} ${H * 0.9}, ${W} ${H * 0.6} L ${W} ${H} L 0 ${H} Z`} fill="#DCEBE0" />
        {grid}
        {naive.length > 0 && <polyline points={line([base, ...naive])} fill="none" stroke="#9AA0A6" strokeWidth="2.5" strokeDasharray="6 6" />}
        {stops.length > 0 && <polyline points={line([base, ...stops])} fill="none" stroke="#E23744" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />}
        {stops.map((p, i) => { const [x, y] = P(p); return (<g key={i}><circle cx={x} cy={y} r="14" fill="#E23744" stroke="#fff" strokeWidth="3" /><text x={x} y={y + 4.5} textAnchor="middle" fontSize="12.5" fontWeight="800" fill="#fff">{i + 1}</text></g>) })}
        {(() => { const [x, y] = P(base); return (<g><rect x={x - 15} y={y - 15} width="30" height="30" rx="9" fill="#1C1C1C" stroke="#fff" strokeWidth="3" /><text x={x} y={y + 5} textAnchor="middle" fontSize="14" fill="#fff">🏠</text></g>) })()}
      </svg>
    </div>
    <div className="row xs" style={{ gap: 14, flexWrap: 'wrap' }}>
      <span className="row" style={{ gap: 6 }}><i style={{ width: 18, height: 4, background: '#E23744', borderRadius: 2 }} />Optimised route</span>
      {naive.length > 0 && <span className="row" style={{ gap: 6 }}><i style={{ width: 18, height: 0, borderTop: '3px dashed #9AA0A6' }} />Order accepted</span>}
      <span className="muted">Schematic map, not to scale</span>
    </div>
    </>
  )
}
