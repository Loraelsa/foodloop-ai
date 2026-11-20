// Optional FoodLoop backend. If it cannot be reached the UI silently falls back to the
// built-in rule table (engine.js), so the page also works offline as a single HTML file.
export const API = (typeof localStorage !== 'undefined' && localStorage.getItem('foodloop-api')) || 'http://127.0.0.1:8000'

async function post(path, body, ms = 2500) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), ms)
  try {
    const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal })
    if (!r.ok) return null
    return await r.json()
  } catch { return null } finally { clearTimeout(t) }
}

export const apiDecide = (f, kg) =>
  post('/decide', { category: f.category, storage: f.storage, temp: f.temp, hours: f.hours, qty_kg: Math.max(kg, 0.01), mrp: f.mrp })

export const apiRoute = (depot, stops) =>
  post('/route', { depot: { id: 'depot', lat: depot.lat, lng: depot.lng }, stops: stops.map((s) => ({ id: s.id, lat: s.lat, lng: s.lng })), time_limit_ms: 200 }, 4000)
