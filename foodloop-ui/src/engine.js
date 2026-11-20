// ---------------------------------------------------------------------------
// FoodLoop decision engine, routing and impact maths (front-end preview).
// In the full system these three functions are served by the FastAPI backend
// (XGBoost shelf-life model + OR-Tools routing). The interfaces are the same,
// so the UI can call the API later without changes to the pages.
// ---------------------------------------------------------------------------

// Documented assumption table: safe hours at 25 C, room temperature.
// Replace with the cited FSSAI / WHO table when it is finalised.
export const CATEGORIES = {
  cooked:  { label: 'Cooked meals',  base: 6,   emoji: '🍛', tint: ['#FFE3D3', '#FFB88C'] },
  bakery:  { label: 'Bakery',        base: 36,  emoji: '🥖', tint: ['#FFF0CF', '#F7CE74'] },
  dairy:   { label: 'Dairy',         base: 8,   emoji: '🥛', tint: ['#E6EEFF', '#B7CBFA'] },
  produce: { label: 'Fruit & veg',   base: 48,  emoji: '🥭', tint: ['#E0F6E2', '#9ADBA3'] },
  sweets:  { label: 'Sweets',        base: 24,  emoji: '🍮', tint: ['#FFE4EE', '#FAB0CB'] },
  packaged:{ label: 'Packaged',      base: 240, emoji: '🍪', tint: ['#EFE8FF', '#C9B5F5'] },
}

export const STORAGE = {
  room:   { label: 'Room temperature', factor: 1.0 },
  fridge: { label: 'Refrigerated',     factor: 3.5 },
  hot:    { label: 'Kept hot',         factor: 1.6 },
}

export const THRESHOLDS = { sell: 4, donate: 1 } // hours remaining

export function remainingHours({ category, storage, temp, hours }) {
  const base = CATEGORIES[category].base * STORAGE[storage].factor
  const life = base * Math.pow(0.5, (temp - 25) / 10)
  return +(life - hours).toFixed(1)
}

export function decide(input) {
  const rem = remainingHours(input)
  let decision = 'compost'
  if (rem >= THRESHOLDS.sell) decision = 'sell'
  else if (rem >= THRESHOLDS.donate) decision = 'donate'
  // discount deepens as remaining life shortens: 20% (>= 24 h) .. 70% (4 h)
  let discount = 0
  if (decision === 'sell') {
    const t = Math.min(1, Math.max(0, (rem - THRESHOLDS.sell) / (24 - THRESHOLDS.sell)))
    discount = Math.round((0.7 - t * 0.5) * 100)
  }
  return { remaining: rem, decision, discount }
}

// ---- geography ------------------------------------------------------------
const R = 6371
const rad = (d) => (d * Math.PI) / 180
export function haversine(a, b) {
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng)
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(x))
}
export const ROAD_FACTOR = 1.3
export const roadKm = (a, b) => haversine(a, b) * ROAD_FACTOR

export function routeLength(start, stops) {
  let km = 0, prev = start
  for (const s of stops) { km += roadKm(prev, s); prev = s }
  return km
}

// Nearest neighbour + 2-opt improvement, starting at the NGO base.
export function optimiseRoute(start, stops) {
  if (stops.length < 2) return { order: stops, km: routeLength(start, stops) }
  const left = [...stops], order = []
  let cur = start
  while (left.length) {
    let bi = 0, bd = Infinity
    left.forEach((s, i) => { const d = roadKm(cur, s); if (d < bd) { bd = d; bi = i } })
    cur = left.splice(bi, 1)[0]; order.push(cur)
  }
  let improved = true
  while (improved) {
    improved = false
    for (let i = 0; i < order.length - 1; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const cand = [...order.slice(0, i), ...order.slice(i, j + 1).reverse(), ...order.slice(j + 1)]
        if (routeLength(start, cand) + 1e-9 < routeLength(start, order)) { order.splice(0, order.length, ...cand); improved = true }
      }
    }
  }
  return { order, km: routeLength(start, order) }
}

// ---- impact ---------------------------------------------------------------
export const KG_PER_MEAL = 0.42      // WRAP meal equivalent
export const CO2_PER_KG = 2.5        // FAO food wastage footprint
export const CO2_PER_KM = 0.2521     // average diesel van, UK DESNZ 2025 factors
export const impactOf = (kg, km = 0) => ({
  kg,
  meals: Math.round(kg / KG_PER_MEAL),
  co2: +(kg * CO2_PER_KG - km * CO2_PER_KM).toFixed(1),
})

export const inr = (n) => '₹' + Math.round(n).toLocaleString('en-IN')
