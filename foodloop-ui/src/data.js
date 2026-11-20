import { decide, CATEGORIES } from './engine.js'

export const SEED_VERSION = 'v1'

// Approximate locality centres in Bengaluru (for the demo map and routing).
export const LOCALITIES = {
  'Koramangala':  { lat: 12.9352, lng: 77.6245 },
  'Indiranagar':  { lat: 12.9784, lng: 77.6408 },
  'BTM Layout':   { lat: 12.9166, lng: 77.6101 },
  'Jayanagar':    { lat: 12.9250, lng: 77.5938 },
  'HSR Layout':   { lat: 12.9116, lng: 77.6389 },
  'Whitefield':   { lat: 12.9698, lng: 77.7500 },
  'Malleshwaram': { lat: 13.0035, lng: 77.5646 },
  'MG Road':      { lat: 12.9756, lng: 77.6068 },
  'Marathahalli': { lat: 12.9569, lng: 77.7011 },
  'JP Nagar':     { lat: 12.9063, lng: 77.5857 },
}

const jit = (n) => (((n * 9301 + 49297) % 233280) / 233280 - 0.5) * 0.01

const V = [
  ['Saffron Tiffin Room', 'Koramangala', 4.4, 'North Indian, Biryani', 450, false],
  ['Udupi Junction', 'Jayanagar', 4.3, 'South Indian, Tiffin', 250, true],
  ['The Bread Basket', 'Indiranagar', 4.5, 'Bakery, Cafe', 350, true],
  ['Mithai Mahal', 'Malleshwaram', 4.2, 'Sweets, Snacks', 300, true],
  ['Curd & Co.', 'BTM Layout', 4.1, 'Dairy, Desserts', 200, true],
  ['Biryani Boulevard', 'HSR Layout', 4.3, 'Biryani, Kebabs', 500, false],
  ['Green Basket Fresh', 'JP Nagar', 4.0, 'Fruit & Vegetables', 150, true],
  ['Dosa Dynasty', 'Marathahalli', 4.2, 'South Indian', 280, true],
  ['Punjab Rasoi', 'MG Road', 4.4, 'North Indian, Thali', 600, false],
  ['Malabar Meals', 'Whitefield', 4.3, 'Kerala, Seafood', 420, false],
]

export const seedVendors = () =>
  V.map(([name, locality, rating, cuisines, cost, veg], i) => ({
    id: 'v' + (i + 1), name, locality, rating, cuisines, cost, veg,
    lat: LOCALITIES[locality].lat + jit(i + 3),
    lng: LOCALITIES[locality].lng + jit(i + 11),
    status: i === 9 ? 'pending' : 'approved',
    joined: '2026-0' + (3 + (i % 5)) + '-1' + (i % 9),
  }))

export const seedNgos = () => [
  { id: 'n1', name: 'Annapurna Seva Trust', locality: 'Jayanagar', lat: 12.9299, lng: 77.5826, capacityKg: 120, status: 'verified', contact: '+91 98450 00112' },
  { id: 'n2', name: 'Robin Hood Collective', locality: 'Koramangala', lat: 12.9279, lng: 77.6271, capacityKg: 80, status: 'verified', contact: '+91 98860 00231' },
  { id: 'n3', name: 'Asha Kiran Foundation', locality: 'Whitefield', lat: 12.9857, lng: 77.7435, capacityKg: 60, status: 'pending', contact: '+91 99020 00378' },
]

// [vendor index, item, category, storage, temp, age hours, qty, unit, kg/unit, mrp/unit, listedMinutesAgo]
const L = [
  [0, 'Veg Dum Biryani', 'cooked', 'hot', 30, 1.5, 24, 'portions', 0.4, 220, 20],
  [0, 'Dal Makhani', 'cooked', 'hot', 30, 2.5, 18, 'portions', 0.35, 180, 35],
  [1, 'Idli & Sambar combo', 'cooked', 'room', 30, 2, 30, 'portions', 0.3, 90, 15],
  [1, 'Masala Dosa', 'cooked', 'room', 30, 1, 22, 'portions', 0.25, 110, 10],
  [2, 'Multigrain Loaf', 'bakery', 'room', 29, 10, 14, 'loaves', 0.4, 90, 40],
  [2, 'Butter Croissant', 'bakery', 'room', 29, 6, 26, 'pieces', 0.08, 85, 25],
  [3, 'Kaju Katli (250 g)', 'sweets', 'room', 29, 8, 20, 'boxes', 0.25, 320, 50],
  [3, 'Gulab Jamun tin', 'sweets', 'room', 29, 20, 12, 'tins', 0.5, 240, 55],
  [4, 'Set Curd (500 g)', 'dairy', 'fridge', 8, 20, 40, 'cups', 0.5, 60, 30],
  [4, 'Rasmalai box', 'dairy', 'fridge', 8, 28, 16, 'boxes', 0.4, 280, 45],
  [5, 'Chicken Biryani', 'cooked', 'hot', 31, 3.2, 28, 'portions', 0.45, 320, 12],
  [6, 'Seasonal fruit mix', 'produce', 'room', 30, 30, 20, 'kg', 1, 120, 60],
  [6, 'Fresh spinach & greens', 'produce', 'fridge', 10, 40, 35, 'kg', 1, 40, 22],
  [7, 'Pongal & Vada', 'cooked', 'hot', 31, 4.4, 15, 'portions', 0.35, 100, 18],
  [8, 'Veg Thali', 'cooked', 'room', 31, 5, 20, 'portions', 0.6, 260, 5],
  [8, 'Paneer Butter Masala', 'cooked', 'hot', 31, 3, 16, 'portions', 0.35, 280, 9],
]

export const makeListing = (id, vendorId, f) => {
  const { item, category, storage, temp, hours, qty, unit, kgPerUnit, mrp } = f
  const d = f.override ?? decide({ category, storage, temp, hours })
  const now = Date.now()
  return {
    id, vendorId, item, category, storage, temp, hours, qty, unit, kgPerUnit, mrp,
    remaining: d.remaining, decision: d.decision, discount: d.discount, source: f.override ? 'model' : 'rules',
    price: Math.round(mrp * (1 - d.discount / 100)),
    listedAt: f.listedAt ?? now,
    expiresAt: (f.listedAt ?? now) + Math.max(d.remaining, 0) * 3600 * 1000,
    status: 'live',
  }
}

export const seedListings = () => {
  const now = Date.now()
  return L.map(([vi, item, category, storage, temp, hours, qty, unit, kgPerUnit, mrp, ago], i) =>
    makeListing('l' + (i + 1), 'v' + (vi + 1), {
      item, category, storage, temp, hours, qty, unit, kgPerUnit, mrp,
      listedAt: now - ago * 60 * 1000,
    }))
}

// Sample history for the charts (clearly labelled as sample data in the UI).
export const seedHistory = () => {
  const out = []
  const base = new Date()
  for (let i = 13; i >= 0; i--) {
    const d = new Date(base); d.setDate(base.getDate() - i)
    const wk = [0, 6].includes(d.getDay()) ? 1.25 : 1
    const n = (s) => ((i * 37 + s * 53) % 17) / 17
    out.push({
      date: d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
      sold: Math.round((52 + n(1) * 26) * wk),
      donated: Math.round((30 + n(2) * 22) * wk),
      composted: Math.round((14 + n(3) * 12) * wk),
    })
  }
  return out
}

export const CATEGORY_LIST = Object.entries(CATEGORIES).map(([key, v]) => ({ key, ...v }))
