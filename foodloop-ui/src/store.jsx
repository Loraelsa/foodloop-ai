import React, { createContext, useContext, useEffect, useMemo, useReducer, useCallback } from 'react'
import { SEED_VERSION, seedVendors, seedNgos, seedListings, seedHistory, makeListing } from './data.js'

const KEY = 'foodloop-demo-' + SEED_VERSION
const Ctx = createContext(null)

const fresh = () => ({
  session: null,                 // { role, name, id }
  vendors: seedVendors(),
  ngos: seedNgos(),
  listings: seedListings(),
  orders: [],
  pickups: [],
  cart: [],                      // [{ listingId, qty }]
  history: seedHistory(),
  note: null,
})

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY))
    if (!s) return fresh()
    // Re-seed if nothing is live any more (demo data ages out).
    const live = s.listings.some((l) => l.status === 'live' && l.expiresAt > Date.now() + 3600e3)
    return live ? { ...s, note: null } : { ...fresh(), session: s.session }
  } catch { return fresh() }
}

let seq = 1000
const uid = (p) => p + (++seq).toString(36) + Math.random().toString(36).slice(2, 5)

function reducer(s, a) {
  switch (a.type) {
    case 'login': return { ...s, session: a.session }
    case 'logout': return { ...s, session: null, cart: [] }
    case 'toast': return { ...s, note: a.msg ? { msg: a.msg, id: Date.now() } : null }
    case 'addListing': return { ...s, listings: [a.listing, ...s.listings] }
    case 'setListing': return { ...s, listings: s.listings.map((l) => (l.id === a.id ? { ...l, ...a.patch } : l)) }
    case 'removeListing': return { ...s, listings: s.listings.filter((l) => l.id !== a.id) }
    case 'cartAdd': {
      const ex = s.cart.find((c) => c.listingId === a.listingId)
      const cart = ex
        ? s.cart.map((c) => (c.listingId === a.listingId ? { ...c, qty: Math.min(a.max, c.qty + 1) } : c))
        : [...s.cart, { listingId: a.listingId, qty: 1 }]
      return { ...s, cart }
    }
    case 'cartDec': return { ...s, cart: s.cart.flatMap((c) => c.listingId === a.listingId ? (c.qty > 1 ? [{ ...c, qty: c.qty - 1 }] : []) : [c]) }
    case 'cartClear': return { ...s, cart: [] }
    case 'placeOrder': {
      const listings = s.listings.map((l) => {
        const c = a.items.find((i) => i.listingId === l.id)
        if (!c) return l
        const qty = l.qty - c.qty
        return { ...l, qty, status: qty <= 0 ? 'sold' : l.status }
      })
      return { ...s, listings, orders: [...a.orders, ...s.orders], cart: [] }
    }
    case 'setOrder': return { ...s, orders: s.orders.map((o) => (o.id === a.id ? { ...o, ...a.patch } : o)) }
    case 'claim': {
      const ids = a.pickup.listingIds
      return {
        ...s,
        listings: s.listings.map((l) => (ids.includes(l.id) ? { ...l, status: 'claimed', ngoId: a.pickup.ngoId } : l)),
        pickups: [a.pickup, ...s.pickups],
      }
    }
    case 'setPickup': return { ...s, pickups: s.pickups.map((p) => (p.id === a.id ? { ...p, ...a.patch } : p)) }
    case 'setVendor': return { ...s, vendors: s.vendors.map((v) => (v.id === a.id ? { ...v, ...a.patch } : v)) }
    case 'setNgo': return { ...s, ngos: s.ngos.map((n) => (n.id === a.id ? { ...n, ...a.patch } : n)) }
    case 'reset': return { ...fresh(), session: s.session }
    default: return s
  }
}

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, undefined, load)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify({ ...state, note: null })) } catch {}
  }, [state])

  useEffect(() => {
    if (!state.note) return
    const t = setTimeout(() => dispatch({ type: 'toast', msg: null }), 3200)
    return () => clearTimeout(t)
  }, [state.note])

  const api = useMemo(() => ({
    login: (session) => dispatch({ type: 'login', session }),
    logout: () => dispatch({ type: 'logout' }),
    toast: (msg) => dispatch({ type: 'toast', msg }),
    addListing: (vendorId, f) => {
      const listing = makeListing(uid('l'), vendorId, f)
      dispatch({ type: 'addListing', listing }); return listing
    },
    setListing: (id, patch) => dispatch({ type: 'setListing', id, patch }),
    removeListing: (id) => dispatch({ type: 'removeListing', id }),
    cartAdd: (listingId, max) => dispatch({ type: 'cartAdd', listingId, max }),
    cartDec: (listingId) => dispatch({ type: 'cartDec', listingId }),
    placeOrder: (items, orders) => dispatch({ type: 'placeOrder', items, orders }),
    setOrder: (id, patch) => dispatch({ type: 'setOrder', id, patch }),
    claim: (pickup) => dispatch({ type: 'claim', pickup }),
    setPickup: (id, patch) => dispatch({ type: 'setPickup', id, patch }),
    setVendor: (id, patch) => dispatch({ type: 'setVendor', id, patch }),
    setNgo: (id, patch) => dispatch({ type: 'setNgo', id, patch }),
    reset: () => dispatch({ type: 'reset' }),
    uid,
  }), [])

  return <Ctx.Provider value={{ ...state, ...api }}>{children}</Ctx.Provider>
}

export const useStore = () => useContext(Ctx)
