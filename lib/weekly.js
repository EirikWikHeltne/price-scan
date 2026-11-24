import { weekMeta } from './isoWeek.js'
import { NON_PRICE_COLS } from './pivot.js'

// Slår sammen brede historikkrader (én per dato og produkt) til én rad per
// uke og produkt, med ukesnitt per kjede. `dato` settes til mandagen i uken,
// slik at radene kan brukes på samme måte som dagsradene.
export function aggregateWeekly(rows) {
  const groups = new Map()
  for (const row of rows) {
    const wm = weekMeta((row.dato || '').slice(0, 10))
    const vn = row.varenummer || row.produkt
    if (!wm || !vn) continue
    const key = `${wm.key}|${vn}`
    let g = groups.get(key)
    if (!g) {
      g = {
        row: { dato: wm.monday, varenummer: row.varenummer, produkt: row.produkt, kategori: row.kategori, merke: row.merke },
        sums: {},
        counts: {},
      }
      groups.set(key, g)
    }
    for (const k in row) {
      if (NON_PRICE_COLS.has(k)) continue
      const v = row[k]
      if (v == null || v === '' || isNaN(Number(v))) continue
      g.sums[k] = (g.sums[k] || 0) + Number(v)
      g.counts[k] = (g.counts[k] || 0) + 1
    }
  }
  return [...groups.values()]
    .map(g => {
      for (const k in g.sums) g.row[k] = +(g.sums[k] / g.counts[k]).toFixed(2)
      return g.row
    })
    .sort((a, b) => a.dato.localeCompare(b.dato))
}
