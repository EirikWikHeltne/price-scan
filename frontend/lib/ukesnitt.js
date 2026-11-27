import { weekMeta } from './isoWeek.js'
import { KNOWN_RETAILER_STYLES, FALLBACK_COLORS } from './retailers.js'

/**
 * Gjør svaret fra /api/ukesnitt om til det tabellen trenger:
 *   weeks:     ukene som finnes i dataene, nyeste først
 *   rows:      { vn, produkt, merke, kategori, niva1, niva2,
 *                weeks: { [ukenøkkel]: { [kjede]: snitt } } }
 *   retailers: kjedene som har minst ett ukesnitt, kjente kjeder først
 */
export function buildWeekly(data) {
  const weekByKey = {}
  const retailerKeys = new Set()

  const rows = (Array.isArray(data) ? data : []).map(p => {
    const weeks = {}
    Object.entries(p.uker || {}).forEach(([monday, prices]) => {
      const wm = weekMeta(monday)
      if (!wm) return
      weekByKey[wm.key] = wm
      const cell = {}
      Object.entries(prices || {}).forEach(([key, v]) => {
        if (v == null || v === '' || isNaN(Number(v))) return
        cell[key] = Number(v)
        retailerKeys.add(key)
      })
      weeks[wm.key] = cell
    })
    return {
      vn: p.varenummer,
      produkt: p.produkt || p.varenummer,
      merke: p.merke || '',
      kategori: p.kategori || '',
      niva1: p.niva1 || '',
      niva2: p.niva2 || '',
      weeks,
    }
  })

  const known = Object.keys(KNOWN_RETAILER_STYLES)
  const rank = k => (known.includes(k) ? known.indexOf(k) : known.length)
  let colorIdx = 0
  const retailers = [...retailerKeys]
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map(key => ({
      key,
      label: KNOWN_RETAILER_STYLES[key]?.label || (key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ')),
      color: KNOWN_RETAILER_STYLES[key]?.color || FALLBACK_COLORS[colorIdx++ % FALLBACK_COLORS.length],
    }))

  return {
    weeks: Object.values(weekByKey).sort((a, b) => b.key.localeCompare(a.key)),
    rows,
    retailers,
  }
}
