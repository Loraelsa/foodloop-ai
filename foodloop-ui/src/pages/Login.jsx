import React, { useState } from 'react'
import { ShoppingBag, Store, HeartHandshake, ShieldCheck, ArrowRight } from 'lucide-react'
import { Logo } from '../components/ui.jsx'
import { useStore } from '../store.jsx'

export const HOME = { customer: '/shop', restaurant: '/restaurant', ngo: '/ngo', admin: '/admin' }

const ROLES = [
  { key: 'customer', title: 'Customer', sub: 'Buy surplus food at a discount', icon: ShoppingBag, color: '#E23744', email: 'aarav@example.com', name: 'Aarav Sharma', id: 'c1' },
  { key: 'restaurant', title: 'Restaurant', sub: 'List surplus before it spoils', icon: Store, color: '#F59E0B', email: 'manager@saffrontiffin.in', name: 'Saffron Tiffin Room', id: 'v1' },
  { key: 'ngo', title: 'NGO', sub: 'Claim donations, plan pickups', icon: HeartHandshake, color: '#3B6FE0', email: 'ops@annapurna.org', name: 'Annapurna Seva Trust', id: 'n1' },
  { key: 'admin', title: 'Admin', sub: 'Approve partners, track impact', icon: ShieldCheck, color: '#1C1C1C', email: 'admin@foodloop.ai', name: 'Platform Admin', id: 'a1' },
]

export default function Login() {
  const { login, toast } = useStore()
  const [role, setRole] = useState('customer')
  const r = ROLES.find((x) => x.key === role)

  const submit = (e) => {
    e.preventDefault()
    login({ role: r.key, name: r.name, id: r.id })
    toast('Signed in as ' + r.title)
  }

  return (
    <div className="login">
      <section className="left">
        <div className="logo" style={{ color: '#fff' }}>
          <span className="mark" style={{ background: '#fff', color: '#E23744' }}>⟳</span><span>FoodLoop AI</span>
        </div>
        <div className="art" aria-hidden>🍛</div>
        <h1>Good food shouldn't end up in the bin.</h1>
        <p>FoodLoop decides in seconds whether surplus should be sold, donated or composted, then plans the pickup route.</p>
        <div className="pts">
          <div><b>3 ways</b><span>Sell · Donate · Compost</span></div>
          <div><b>1 route</b><span>Optimised per NGO pickup</span></div>
          <div><b>4 SDGs</b><span>2 · 11 · 12 · 13</span></div>
        </div>
      </section>
      <section className="right">
        <form className="box" onSubmit={submit}>
          <h2 style={{ fontSize: 28, fontWeight: 800 }}>Welcome back</h2>
          <p className="muted" style={{ margin: '6px 0 0' }}>Choose how you use FoodLoop to continue.</p>
          <div className="roles" role="radiogroup" aria-label="Sign in as">
            {ROLES.map((x) => (
              <button type="button" key={x.key} role="radio" aria-checked={role === x.key} className={'rolecard' + (role === x.key ? ' on' : '')} onClick={() => setRole(x.key)}>
                <span className="ic" style={{ background: x.color }}><x.icon size={19} /></span>
                <span><span className="b" style={{ display: 'block' }}>{x.title}</span><span className="xs muted">{x.sub}</span></span>
              </button>
            ))}
          </div>
          <div className="col" style={{ gap: 14 }}>
            <div className="field"><label htmlFor="em">Email</label><input id="em" className="input" key={r.email} defaultValue={r.email} /></div>
            <div className="field"><label htmlFor="pw">Password</label><input id="pw" className="input" type="password" defaultValue="demo-password" /></div>
            <button className="btn primary lg block" type="submit">Sign in as {r.title.toLowerCase()} <ArrowRight size={18} /></button>
          </div>
          <p className="hint" style={{ marginTop: 14 }}>Demo mode: credentials are pre-filled and nothing is sent to a server. Production sign-in uses JWT roles on the FastAPI backend.</p>
        </form>
      </section>
    </div>
  )
}
